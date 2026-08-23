#!/usr/bin/env python3
"""Run the balanced Qwen/Codex three-game pilot with bounded concurrency."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import itertools
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agentbga.agents import HARNESS_BACKENDS, PlayerConfig  # noqa: E402
from agentbga.ratings import score_matches  # noqa: E402
from agentbga.registry import get_game  # noqa: E402
from agentbga.runner import run_match  # noqa: E402
from agentbga.store import Store  # noqa: E402


SCHEMA_VERSION = "agentbga.qwen-codex-pilot.v1"
DEFAULT_CONFIG = ROOT / "examples" / "qwen-codex-pilot.json"


def _command_version(executable: str) -> str | None:
    try:
        completed = subprocess.run(
            [executable, "--version"], capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (completed.stdout or completed.stderr).strip()[:500] or None


def _codex_subscription_status(executable: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [executable, "login", "status"], capture_output=True, text=True,
            timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"configured": False, "status": str(error)}
    status = (completed.stdout or completed.stderr).strip()[:500]
    return {
        "configured": completed.returncode == 0 and "chatgpt" in status.lower(),
        "status": status or f"codex login status exited {completed.returncode}",
    }


def runtime_report(config: dict[str, Any]) -> dict[str, Any]:
    participants = config["participants"]
    key_names = sorted({
        str(row["player"].get("api_key_env"))
        for row in participants if row["player"].get("api_key_env")
    })
    harnesses = sorted({str(row["player"]["backend"]).lower() for row in participants})
    binaries: dict[str, dict[str, Any]] = {}
    for harness in harnesses:
        executable = shutil.which(harness)
        binaries[harness] = {
            "path": executable,
            "version": _command_version(executable) if executable else None,
        }
    codex = binaries.get("codex", {}).get("path")
    return {
        "schema_version": "agentbga.qwen-codex-runtime.v1",
        "python": {"version": sys.version.split()[0], "executable": sys.executable},
        "credentials": {name: {"configured": bool(os.environ.get(name))} for name in key_names},
        "codex_subscription": _codex_subscription_status(codex) if codex else {
            "configured": False, "status": "codex executable not found",
        },
        "harnesses": binaries,
        "endpoints": sorted({
            str(row["player"].get("base_url"))
            for row in participants if row["player"].get("base_url")
        }),
    }


def validate_runtime(report: dict[str, Any]) -> None:
    missing_keys = [
        name for name, row in report["credentials"].items() if not row["configured"]
    ]
    missing_harnesses = [
        name for name, row in report["harnesses"].items() if not row["path"]
    ]
    problems: list[str] = []
    if missing_keys:
        problems.append("missing environment variable(s): " + ", ".join(missing_keys))
    if missing_harnesses:
        problems.append("missing harness executable(s): " + ", ".join(missing_harnesses))
    if not report["codex_subscription"]["configured"]:
        problems.append("Codex is not logged in with a ChatGPT subscription")
    if problems:
        raise RuntimeError("; ".join(problems))


def load_config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"config must use schema_version {SCHEMA_VERSION}")
    participants = value.get("participants")
    if not isinstance(participants, list) or len(participants) < 4:
        raise ValueError("config requires at least four participants")
    seen: set[str] = set()
    for index, participant in enumerate(participants):
        if not isinstance(participant, dict):
            raise ValueError(f"participant {index} must be an object")
        identifier = participant.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", identifier,
        ):
            raise ValueError(f"participant {index} has an invalid id")
        if identifier in seen:
            raise ValueError(f"duplicate participant id: {identifier}")
        seen.add(identifier)
        player = participant.get("player")
        if not isinstance(player, dict):
            raise ValueError(f"participant {identifier} requires a player object")
        probe = dict(player)
        if str(probe.get("backend", "")).lower() in HARNESS_BACKENDS:
            probe["participant_id"] = identifier
        PlayerConfig.from_dict(probe, index)

    schedule = value.get("schedule", {})
    if not isinstance(schedule, dict):
        raise ValueError("schedule must be an object")
    appearances = schedule.get("appearances_per_condition", 2)
    workers = schedule.get("workers", 10)
    if not isinstance(appearances, int) or appearances < 1:
        raise ValueError("schedule.appearances_per_condition must be a positive integer")
    if not isinstance(workers, int) or not 1 <= workers <= 64:
        raise ValueError("schedule.workers must be between 1 and 64")
    games = schedule.get("games")
    if not isinstance(games, dict) or not games:
        raise ValueError("schedule.games must be a non-empty object")
    for game_id, counts in games.items():
        description = get_game(game_id).describe()
        minimum = int(description.get("min_players", 2))
        maximum = min(4, int(description.get("max_players", 4)))
        if not isinstance(counts, list) or not counts:
            raise ValueError(f"game {game_id} requires player counts")
        for count in counts:
            if not isinstance(count, int) or not minimum <= count <= maximum:
                raise ValueError(f"invalid player count for {game_id}: {count}")
            if count > len(participants):
                raise ValueError(f"game {game_id} needs at least {count} participants")
            if len(participants) * appearances % count:
                raise ValueError(
                    "participants × appearances_per_condition must be divisible by "
                    f"every player count; {len(participants)} × {appearances} is not "
                    f"divisible by {count}"
                )
    run_config = value.get("run", {})
    if not isinstance(run_config, dict):
        raise ValueError("run must be an object")
    if str(run_config.get("fallback", "fail")) not in {"fail", "random"}:
        raise ValueError("run.fallback must be fail or random")
    return value


def _balanced_rosters(
    identifiers: list[str], player_count: int, appearances: int, rng: random.Random,
    pair_count: dict[tuple[str, str], int] | None = None,
) -> list[tuple[str, ...]]:
    match_count = len(identifiers) * appearances // player_count
    combinations = list(itertools.combinations(identifiers, player_count))
    appearance_count = {identifier: 0 for identifier in identifiers}
    pair_count = pair_count if pair_count is not None else {}
    roster_count: dict[tuple[str, ...], int] = {}
    result: list[tuple[str, ...]] = []

    for _ in range(match_count):
        candidates = [
            roster for roster in combinations
            if all(appearance_count[identifier] < appearances for identifier in roster)
        ]
        if not candidates:
            raise RuntimeError("balanced roster construction reached a dead end")

        def score(roster: tuple[str, ...]) -> tuple[int, int, int, float]:
            repeated_pairs = sum(
                pair_count.get(tuple(sorted(pair)), 0)
                for pair in itertools.combinations(roster, 2)
            )
            future_imbalance = sum(
                (appearance_count[identifier] + 1) ** 2 for identifier in roster
            )
            return roster_count.get(roster, 0), repeated_pairs, future_imbalance, rng.random()

        selected = min(candidates, key=score)
        result.append(selected)
        roster_count[selected] = roster_count.get(selected, 0) + 1
        for identifier in selected:
            appearance_count[identifier] += 1
        for pair in itertools.combinations(selected, 2):
            key = tuple(sorted(pair))
            pair_count[key] = pair_count.get(key, 0) + 1

    if set(appearance_count.values()) != {appearances}:
        raise RuntimeError(f"unbalanced appearances: {appearance_count}")
    return result


def _assign_seats(
    roster: tuple[str, ...], seat_counts: dict[str, list[int]], rng: random.Random,
) -> tuple[str, ...]:
    permutations = list(itertools.permutations(roster))

    def score(order: tuple[str, ...]) -> tuple[int, int, float]:
        counts = [seat_counts[identifier][seat] for seat, identifier in enumerate(order)]
        return sum(counts), max(counts), rng.random()

    selected = min(permutations, key=score)
    for seat, identifier in enumerate(selected):
        seat_counts[identifier][seat] += 1
    return selected


def build_schedule(config: dict[str, Any]) -> list[dict[str, Any]]:
    identifiers = [participant["id"] for participant in config["participants"]]
    schedule_config = config["schedule"]
    appearances = int(schedule_config["appearances_per_condition"])
    base_seed = int(schedule_config.get("base_seed", 20260823))
    rng = random.Random(base_seed)
    matches: list[dict[str, Any]] = []
    pair_count: dict[tuple[str, str], int] = {}
    for game_index, (game_id, counts) in enumerate(schedule_config["games"].items(), start=1):
        for player_count in counts:
            rosters = _balanced_rosters(
                identifiers, player_count, appearances, rng, pair_count,
            )
            seat_counts = {identifier: [0] * player_count for identifier in identifiers}
            for block_index, roster in enumerate(rosters, start=1):
                matches.append({
                    "game": game_id,
                    "player_count": player_count,
                    "seed": base_seed + game_index * 1_000_000 + player_count * 10_000 + block_index,
                    "participants": list(_assign_seats(roster, seat_counts, rng)),
                })
    rng.shuffle(matches)
    for ordinal, match in enumerate(matches, start=1):
        match["ordinal"] = ordinal
    return matches


def _public_participants(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {participant["id"]: participant for participant in config["participants"]}


def run_one(
    match: dict[str, Any], participants: dict[str, dict[str, Any]], output: Path,
    *, retries: int, fallback: str, max_turns: int | None,
) -> dict[str, Any]:
    ordinal = int(match["ordinal"])
    store = Store(str(output / "matches" / f"match-{ordinal:06d}.sqlite3"))
    participant_rows: list[dict[str, Any]] = []
    try:
        players: list[PlayerConfig] = []
        for seat, identifier in enumerate(match["participants"]):
            raw = dict(participants[identifier]["player"])
            if str(raw.get("backend", "")).lower() in HARNESS_BACKENDS:
                raw["participant_id"] = identifier
            player = PlayerConfig.from_dict(raw, seat)
            players.append(player)
            participant_rows.append({
                "participant_id": identifier,
                "seat": seat,
                "player": player.public_dict(),
            })
        match_id, _, _ = store.create(len(players), int(match["seed"]), str(match["game"]))
        result = run_match(
            store, match_id, players, retries=retries,
            fallback=fallback, max_turns=max_turns,
        )
        return {
            "ordinal": ordinal,
            "status": "ok",
            "game": match["game"],
            "seed": match["seed"],
            "player_count": match["player_count"],
            "participants": participant_rows,
            "result": result,
        }
    except Exception as error:
        return {
            "ordinal": ordinal,
            "status": "error",
            "game": match["game"],
            "seed": match["seed"],
            "player_count": match["player_count"],
            "participants": participant_rows,
            "error": str(error),
        }
    finally:
        store.close()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} is not a JSON object")
        rows.append(value)
    return rows


def write_scores(rows: list[dict[str, Any]], output: Path) -> list[dict[str, Any]]:
    leaderboard = score_matches(rows)
    summary = {
        "schema_version": "agentbga.qwen-codex-scores.v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "matches": {
            "reported": len(rows),
            "completed": sum(row.get("status") == "ok" for row in rows),
            "failed": sum(row.get("status") != "ok" for row in rows),
        },
        "rating": {
            "method": "batch-pairwise-bradley-terry",
            "centre": 1500,
            "failed_matches": "excluded and reported as failed exposures",
        },
        "leaderboard": leaderboard,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    fieldnames = [
        "rating_rank", "participant_id", "elo", "pws", "average_rank",
        "first_place_equivalent", "scheduled", "completed", "failed_exposures",
        "pairwise_comparisons",
    ]
    with (output / "leaderboard.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(leaderboard)
    return leaderboard


def print_leaderboard(leaderboard: list[dict[str, Any]]) -> None:
    print(f"{'#':>3}  {'participant':<30} {'elo':>7} {'pws':>7} {'done':>6} {'failed':>7}")
    for row in leaderboard:
        pws = "-" if row["pws"] is None else f"{row['pws']:.3f}"
        print(
            f"{row['rating_rank']:>3}  {row['participant_id'][:30]:<30} "
            f"{row['elo']:>7.1f} {pws:>7} {row['completed']:>6} "
            f"{row['failed_exposures']:>7}"
        )


def command_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    report = runtime_report(config)
    if not args.dry_run:
        validate_runtime(report)
    schedule = build_schedule(config)
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be a positive integer")
        schedule = schedule[:args.limit]
    workers = (
        args.workers
        if args.workers is not None
        else int(config["schedule"].get("workers", 10))
    )
    if not 1 <= workers <= 64:
        raise ValueError("--workers must be between 1 and 64")
    workers = min(workers, len(schedule))
    output: Path = args.out
    results_path = output / "matches.jsonl"
    if results_path.exists() and not args.overwrite:
        raise ValueError(f"refusing to overwrite existing results: {results_path}")
    if output.exists() and args.overwrite:
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "matches").mkdir(exist_ok=True)
    (output / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (output / "schedule.json").write_text(
        json.dumps(schedule, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (output / "runtime.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"Scheduled {len(schedule)} matches with {workers} workers in {output}")
    if args.dry_run:
        return 0

    run_config = config.get("run", {})
    retries = int(run_config.get("retries", 0))
    fallback = str(run_config.get("fallback", "fail"))
    max_turns = run_config.get("max_turns")
    participants = _public_participants(config)
    rows: list[dict[str, Any]] = []
    with results_path.open("w", encoding="utf-8") as handle:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="qwen-codex-pilot") as pool:
            futures = {
                pool.submit(
                    run_one, match, participants, output,
                    retries=retries, fallback=fallback, max_turns=max_turns,
                ): match
                for match in schedule
            }
            for completed, future in enumerate(as_completed(futures), start=1):
                match = futures[future]
                row = future.result()
                rows.append(row)
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush()
                state = "ok" if row["status"] == "ok" else f"error: {row.get('error', '')[:80]}"
                print(
                    f"[{completed:>3}/{len(schedule)}] #{match['ordinal']:02d} "
                    f"{match['game']} {match['player_count']}p {state}"
                )

    rows.sort(key=lambda row: int(row.get("ordinal", 0)))
    leaderboard = write_scores(rows, output)
    print()
    print_leaderboard(leaderboard)
    print(f"\nResults: {results_path}")
    print(f"Scores:  {output / 'leaderboard.csv'}")
    return 0


def command_check(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    schedule = build_schedule(config)
    report = runtime_report(config)
    print(json.dumps({
        "config": str(args.config),
        "participants": len(config["participants"]),
        "matches": len(schedule),
        "workers": config["schedule"].get("workers", 10),
        "runtime": report,
    }, ensure_ascii=False, indent=2))
    validate_runtime(report)
    return 0


def command_score(args: argparse.Namespace) -> int:
    rows = read_jsonl(args.results)
    output = args.out or args.results.parent
    output.mkdir(parents=True, exist_ok=True)
    leaderboard = write_scores(rows, output)
    print_leaderboard(leaderboard)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="generate, run concurrently, and score the pilot")
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--workers", type=int, help="concurrent matches; default comes from config")
    run.add_argument("--limit", type=int, help="run only the first N shuffled matches")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--overwrite", action="store_true")
    score = commands.add_parser("score", help="re-score an existing matches.jsonl")
    score.add_argument("--results", type=Path, required=True)
    score.add_argument("--out", type=Path)
    check = commands.add_parser("check", help="validate schedule, key, CLIs, and Codex login")
    check.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        if args.command == "run":
            return command_run(args)
        if args.command == "score":
            return command_score(args)
        return command_check(args)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
