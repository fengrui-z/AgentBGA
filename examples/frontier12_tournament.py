#!/usr/bin/env python3
"""Run the balanced 12-participant AgentBGA frontier tournament.

The schedule follows PR #28's balanced design: in every game/player-count
stratum, every participant appears exactly N times. Results are written per
match so an interrupted server run can resume without replaying completed work.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import hashlib
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

from agentbga.agents import HARNESS_BACKENDS, PlayerConfig, harness_executable_name  # noqa: E402
from agentbga.ratings import score_matches  # noqa: E402
from agentbga.registry import get_game  # noqa: E402
from agentbga.runner import run_match  # noqa: E402
from agentbga.store import Store  # noqa: E402


SCHEMA_VERSION = "agentbga.balanced-tournament.v1"
DEFAULT_CONFIG = ROOT / "examples" / "frontier12-tournament.json"
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _player_value(raw: dict[str, Any], *, require_environment: bool) -> dict[str, Any]:
    value = dict(raw)
    base_url_env = value.pop("base_url_env", None)
    if base_url_env is not None:
        if not isinstance(base_url_env, str) or not ENVIRONMENT_NAME.fullmatch(base_url_env):
            raise ValueError("player base_url_env must be an environment variable name")
        base_url = os.environ.get(base_url_env)
        if not base_url and require_environment:
            raise RuntimeError(f"missing environment variable: {base_url_env}")
        value["base_url"] = base_url or "https://unconfigured.invalid/v1"
    return value


def load_config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"config must use schema_version {SCHEMA_VERSION}")
    tournament_id = value.get("tournament_id")
    if not isinstance(tournament_id, str) or not IDENTIFIER.fullmatch(tournament_id):
        raise ValueError("tournament_id is invalid")

    participants = value.get("participants")
    if not isinstance(participants, list) or len(participants) < 4:
        raise ValueError("config requires at least four participants")
    seen: set[str] = set()
    for index, participant in enumerate(participants):
        if not isinstance(participant, dict):
            raise ValueError(f"participant {index} must be an object")
        identifier = participant.get("id")
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise ValueError(f"participant {index} has an invalid id")
        if identifier in seen:
            raise ValueError(f"duplicate participant id: {identifier}")
        seen.add(identifier)
        player = participant.get("player")
        if not isinstance(player, dict):
            raise ValueError(f"participant {identifier} requires a player object")
        probe = _player_value(player, require_environment=False)
        if str(probe.get("backend", "")).lower() in HARNESS_BACKENDS:
            probe["participant_id"] = identifier
        PlayerConfig.from_dict(probe, index)

    schedule = value.get("schedule")
    if not isinstance(schedule, dict):
        raise ValueError("schedule must be an object")
    appearances = schedule.get("appearances_per_condition")
    workers = schedule.get("workers")
    if not isinstance(appearances, int) or appearances < 1:
        raise ValueError("schedule.appearances_per_condition must be a positive integer")
    if not isinstance(workers, int) or not 1 <= workers <= 64:
        raise ValueError("schedule.workers must be between 1 and 64")
    games = schedule.get("games")
    if not isinstance(games, dict) or not games:
        raise ValueError("schedule.games must be a non-empty object")
    for game_id, counts in games.items():
        description = get_game(str(game_id)).describe()
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


def _balanced_rosters_once(
    identifiers: list[str], player_count: int, appearances: int,
    rng: random.Random, pair_count: dict[tuple[str, str], int],
) -> list[tuple[str, ...]]:
    match_count = len(identifiers) * appearances // player_count
    combinations = list(itertools.combinations(identifiers, player_count))
    appearance_count = {identifier: 0 for identifier in identifiers}
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


def _balanced_rosters(
    identifiers: list[str], player_count: int, appearances: int,
    rng: random.Random, pair_count: dict[tuple[str, str], int],
) -> list[tuple[str, ...]]:
    for _ in range(100):
        candidate_pairs = dict(pair_count)
        attempt_rng = random.Random(rng.getrandbits(64))
        try:
            result = _balanced_rosters_once(
                identifiers, player_count, appearances, attempt_rng, candidate_pairs,
            )
        except RuntimeError:
            continue
        pair_count.clear()
        pair_count.update(candidate_pairs)
        return result
    raise RuntimeError("could not construct a balanced roster after 100 deterministic attempts")


def _assign_all_seats(
    rosters: list[tuple[str, ...]], player_count: int, appearances: int,
    rng: random.Random,
) -> list[tuple[str, ...]]:
    """Assign every roster an exactly balanced seat permutation when possible."""
    if appearances % player_count:
        raise ValueError(
            "appearances_per_condition must be divisible by player count for exact seat balance"
        )
    identifiers = sorted({identifier for roster in rosters for identifier in roster})
    target = appearances // player_count
    permutation_cache = {
        roster: list(itertools.permutations(roster)) for roster in set(rosters)
    }
    for _ in range(200):
        quotas = {identifier: [target] * player_count for identifier in identifiers}
        pending = set(range(len(rosters)))
        result: list[tuple[str, ...] | None] = [None] * len(rosters)
        attempt_rng = random.Random(rng.getrandbits(64))
        failed = False
        while pending:
            choices: list[tuple[int, list[tuple[str, ...]]]] = []
            fewest = None
            for index in pending:
                valid = [
                    order for order in permutation_cache[rosters[index]]
                    if all(quotas[identifier][seat] > 0 for seat, identifier in enumerate(order))
                ]
                if not valid:
                    failed = True
                    break
                if fewest is None or len(valid) < fewest:
                    fewest = len(valid)
                    choices = [(index, valid)]
                elif len(valid) == fewest:
                    choices.append((index, valid))
            if failed:
                break
            index, valid = attempt_rng.choice(choices)

            def score(order: tuple[str, ...]) -> tuple[int, int, float]:
                selected_quotas = [
                    quotas[identifier][seat] for seat, identifier in enumerate(order)
                ]
                # Spend the largest remaining quotas first. The minimum term
                # avoids exhausting a scarce seat for one participant early.
                return min(selected_quotas), sum(selected_quotas), attempt_rng.random()

            selected = max(valid, key=score)
            result[index] = selected
            pending.remove(index)
            for seat, identifier in enumerate(selected):
                quotas[identifier][seat] -= 1
        if not failed and all(value == 0 for counts in quotas.values() for value in counts):
            return [order for order in result if order is not None]
    raise RuntimeError("could not construct exact seat balance after 200 deterministic attempts")


def build_schedule(config: dict[str, Any]) -> list[dict[str, Any]]:
    identifiers = [participant["id"] for participant in config["participants"]]
    schedule_config = config["schedule"]
    appearances = int(schedule_config["appearances_per_condition"])
    base_seed = int(schedule_config.get("base_seed", 20260824))
    rng = random.Random(base_seed)
    matches: list[dict[str, Any]] = []
    pair_count: dict[tuple[str, str], int] = {}
    for game_index, (game_id, counts) in enumerate(schedule_config["games"].items(), start=1):
        for player_count in counts:
            rosters = _balanced_rosters(
                identifiers, player_count, appearances, rng, pair_count,
            )
            seat_orders = _assign_all_seats(rosters, player_count, appearances, rng)
            for block_index, seats in enumerate(seat_orders, start=1):
                matches.append({
                    "game": game_id,
                    "player_count": player_count,
                    "seed": base_seed + game_index * 1_000_000 + player_count * 10_000 + block_index,
                    "participants": list(seats),
                })
    rng.shuffle(matches)
    for ordinal, match in enumerate(matches, start=1):
        match["ordinal"] = ordinal
    return matches


def schedule_report(config: dict[str, Any], schedule: list[dict[str, Any]]) -> dict[str, Any]:
    identifiers = [participant["id"] for participant in config["participants"]]
    strata: dict[str, int] = {}
    exposures = {identifier: 0 for identifier in identifiers}
    seat_exposures: dict[str, dict[str, list[int]]] = {}
    pair_exposures = {
        tuple(sorted(pair)): 0 for pair in itertools.combinations(identifiers, 2)
    }
    for match in schedule:
        key = f"{match['game']}:{match['player_count']}p"
        strata[key] = strata.get(key, 0) + 1
        seat_exposures.setdefault(key, {identifier: [0] * match["player_count"] for identifier in identifiers})
        for seat, identifier in enumerate(match["participants"]):
            exposures[identifier] += 1
            seat_exposures[key][identifier][seat] += 1
        for pair in itertools.combinations(match["participants"], 2):
            pair_exposures[tuple(sorted(pair))] += 1
    seat_values = [
        count
        for by_participant in seat_exposures.values()
        for counts in by_participant.values()
        for count in counts
    ]
    expected_seat_exposures = {
        str(player_count): config["schedule"]["appearances_per_condition"] // player_count
        for player_count in sorted({match["player_count"] for match in schedule})
    }
    exact_seat_balance = all(
        count == expected_seat_exposures[key.rsplit(":", 1)[1][:-1]]
        for key, by_participant in seat_exposures.items()
        for counts in by_participant.values()
        for count in counts
    )
    pair_values = list(pair_exposures.values())
    return {
        "tournament_id": config["tournament_id"],
        "participants": len(identifiers),
        "matches": len(schedule),
        "workers": config["schedule"]["workers"],
        "appearances_per_condition": config["schedule"]["appearances_per_condition"],
        "strata": strata,
        "participant_exposures": {
            "minimum": min(exposures.values()),
            "maximum": max(exposures.values()),
            "by_participant": exposures,
        },
        "seat_exposures_per_stratum": {
            "exact": exact_seat_balance,
            "expected_by_player_count": expected_seat_exposures,
            "minimum": min(seat_values),
            "maximum": max(seat_values),
        },
        "pair_exposures": {
            "minimum": min(pair_values),
            "maximum": max(pair_values),
            "zero_pairs": sum(value == 0 for value in pair_values),
        },
        "schedule_digest": _digest(schedule),
    }


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
    endpoint_names = sorted({
        str(row["player"].get("base_url_env"))
        for row in participants if row["player"].get("base_url_env")
    })
    harnesses = sorted({str(row["player"]["backend"]).lower() for row in participants})
    binaries: dict[str, dict[str, Any]] = {}
    for harness in harnesses:
        executable = shutil.which(harness_executable_name(harness))
        binaries[harness] = {
            "path": executable,
            "version": _command_version(executable) if executable else None,
        }
    codex = binaries.get("codex", {}).get("path")
    needs_subscription = any(
        row["player"].get("backend") == "codex"
        and row["player"].get("auth_mode") == "subscription"
        for row in participants
    )
    return {
        "generated_at": _utc_now(),
        "python": {"version": sys.version.split()[0], "executable": sys.executable},
        "credentials": {name: {"configured": bool(os.environ.get(name))} for name in key_names},
        "endpoint_environment": {
            name: {"configured": bool(os.environ.get(name))} for name in endpoint_names
        },
        "codex_subscription": (
            _codex_subscription_status(codex) if codex and needs_subscription else
            {"configured": not needs_subscription, "status": "not required"}
        ),
        "harnesses": binaries,
    }


def validate_runtime(report: dict[str, Any]) -> None:
    problems: list[str] = []
    missing_keys = [name for name, row in report["credentials"].items() if not row["configured"]]
    missing_endpoints = [
        name for name, row in report["endpoint_environment"].items() if not row["configured"]
    ]
    missing_harnesses = [name for name, row in report["harnesses"].items() if not row["path"]]
    if missing_keys:
        problems.append("missing API key variable(s): " + ", ".join(missing_keys))
    if missing_endpoints:
        problems.append("missing endpoint variable(s): " + ", ".join(missing_endpoints))
    if missing_harnesses:
        problems.append("missing harness executable(s): " + ", ".join(missing_harnesses))
    if not report["codex_subscription"]["configured"]:
        problems.append("Codex is not logged in with a ChatGPT subscription")
    if problems:
        raise RuntimeError("; ".join(problems))


def _participant_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {participant["id"]: participant for participant in config["participants"]}


def _result_path(output: Path, ordinal: int) -> Path:
    return output / "results" / f"match-{ordinal:06d}.json"


def _existing_results(output: Path) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for path in sorted((output / "results").glob("match-*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(row, dict) and isinstance(row.get("ordinal"), int):
            result[row["ordinal"]] = row
    return result


def run_one(
    match: dict[str, Any], participants: dict[str, dict[str, Any]], output: Path, *,
    attempt: int, retries: int, fallback: str, max_turns: int | None,
) -> dict[str, Any]:
    ordinal = int(match["ordinal"])
    database = output / "matches" / f"match-{ordinal:06d}-attempt-{attempt:02d}.sqlite3"
    store = Store(str(database))
    participant_rows: list[dict[str, Any]] = []
    started_at = _utc_now()
    try:
        players: list[PlayerConfig] = []
        for seat, identifier in enumerate(match["participants"]):
            raw = _player_value(
                participants[identifier]["player"], require_environment=True,
            )
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
            "attempt": attempt,
            "status": "ok",
            "started_at": started_at,
            "finished_at": _utc_now(),
            "game": match["game"],
            "seed": match["seed"],
            "player_count": match["player_count"],
            "participants": participant_rows,
            "database": str(database.relative_to(output)),
            "result": result,
        }
    except Exception as error:
        return {
            "ordinal": ordinal,
            "attempt": attempt,
            "status": "error",
            "started_at": started_at,
            "finished_at": _utc_now(),
            "game": match["game"],
            "seed": match["seed"],
            "player_count": match["player_count"],
            "participants": participant_rows,
            "database": str(database.relative_to(output)),
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        store.close()


def write_artifacts(
    config: dict[str, Any], schedule: list[dict[str, Any]], rows: list[dict[str, Any]],
    output: Path, runtime: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = sorted(rows, key=lambda row: int(row["ordinal"]))
    jsonl = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows
    )
    _write_text(output / "matches.jsonl", jsonl)
    leaderboard = score_matches(rows)
    fieldnames = [
        "rating_rank", "participant_id", "elo", "pws", "average_rank",
        "first_place_equivalent", "scheduled", "completed", "failed_exposures",
        "pairwise_comparisons",
    ]
    temporary = output / "leaderboard.csv.tmp"
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(leaderboard)
    temporary.replace(output / "leaderboard.csv")
    summary = {
        "schema_version": "agentbga.balanced-tournament-results.v1",
        "generated_at": _utc_now(),
        "tournament_id": config["tournament_id"],
        "schedule": schedule_report(config, schedule),
        "results": {
            "scheduled": len(schedule),
            "reported": len(rows),
            "completed": sum(row.get("status") == "ok" for row in rows),
            "failed": sum(row.get("status") != "ok" for row in rows),
        },
        "rating": {
            "method": "batch-pairwise-bradley-terry",
            "centre": 1500,
            "failed_matches": "excluded and reported as failed exposures",
        },
        "runtime": runtime,
        "leaderboard": leaderboard,
    }
    _write_json(output / "summary.json", summary)
    return leaderboard


def _print_leaderboard(leaderboard: list[dict[str, Any]]) -> None:
    if not leaderboard:
        return
    print(f"{'#':>3}  {'participant':<32} {'elo':>7} {'pws':>7} {'done':>6} {'failed':>7}")
    for row in leaderboard:
        pws = "-" if row["pws"] is None else f"{row['pws']:.3f}"
        print(
            f"{row['rating_rank']:>3}  {row['participant_id'][:32]:<32} "
            f"{row['elo']:>7.1f} {pws:>7} {row['completed']:>6} "
            f"{row['failed_exposures']:>7}"
        )


def command_schedule(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    schedule = build_schedule(config)
    print(json.dumps(schedule_report(config, schedule), ensure_ascii=False, indent=2))
    return 0


def command_check(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    schedule = build_schedule(config)
    report = runtime_report(config)
    print(json.dumps({
        "schedule": schedule_report(config, schedule),
        "runtime": report,
    }, ensure_ascii=False, indent=2))
    validate_runtime(report)
    for participant in config["participants"]:
        _player_value(participant["player"], require_environment=True)
    return 0


def _prepare_output(
    output: Path, config: dict[str, Any], schedule: list[dict[str, Any]], *, resume: bool,
) -> None:
    if output.exists() and any(output.iterdir()) and not resume:
        raise ValueError(f"output exists; use --resume or choose a new directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "matches").mkdir(exist_ok=True)
    (output / "results").mkdir(exist_ok=True)
    config_path = output / "config.json"
    schedule_path = output / "schedule.json"
    if resume:
        if not config_path.is_file() or not schedule_path.is_file():
            raise ValueError("--resume requires an existing config.json and schedule.json")
        saved_config = json.loads(config_path.read_text(encoding="utf-8"))
        saved_schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
        if _digest(saved_config) != _digest(config):
            raise ValueError("refusing to resume: config does not match the saved run")
        if _digest(saved_schedule) != _digest(schedule):
            raise ValueError("refusing to resume: schedule does not match the saved run")
    else:
        _write_json(config_path, config)
        _write_json(schedule_path, schedule)


def _participant_probe(
    pending: list[dict[str, Any]], identifiers: set[str], covered: set[str],
) -> list[dict[str, Any]]:
    uncovered = identifiers - covered
    selected: list[dict[str, Any]] = []
    candidates = list(pending)
    while uncovered:
        useful = [
            match for match in candidates
            if uncovered.intersection(match["participants"])
        ]
        if not useful:
            raise RuntimeError(
                "could not build an all-participant probe; missing: "
                + ", ".join(sorted(uncovered))
            )
        match = max(
            useful,
            key=lambda row: (
                len(uncovered.intersection(row["participants"])),
                row["player_count"],
                -row["ordinal"],
            ),
        )
        selected.append(match)
        candidates.remove(match)
        uncovered.difference_update(match["participants"])
    return selected


def command_run(args: argparse.Namespace) -> int:
    if args.probe_all_participants and args.limit is not None:
        raise ValueError("--probe-all-participants and --limit cannot be combined")
    config = load_config(args.config)
    schedule = build_schedule(config)
    runtime = runtime_report(config)
    if not args.dry_run:
        validate_runtime(runtime)
        for participant in config["participants"]:
            _player_value(participant["player"], require_environment=True)
    _prepare_output(args.out, config, schedule, resume=args.resume)
    _write_json(args.out / "runtime.json", runtime)
    if args.dry_run:
        print(json.dumps(schedule_report(config, schedule), ensure_ascii=False, indent=2))
        return 0

    existing = _existing_results(args.out)
    pending = []
    for match in schedule:
        previous = existing.get(match["ordinal"])
        if previous is None:
            pending.append(match)
        elif previous.get("status") != "ok" and args.retry_errors:
            pending.append(match)
    if args.probe_all_participants:
        covered = {
            participant["participant_id"]
            for row in existing.values() if row.get("status") == "ok"
            for participant in row.get("participants", [])
            if isinstance(participant, dict) and isinstance(participant.get("participant_id"), str)
        }
        pending = _participant_probe(
            pending,
            {participant["id"] for participant in config["participants"]},
            covered,
        )
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be a positive integer")
        pending = pending[:args.limit]
    workers = args.workers or int(config["schedule"]["workers"])
    if not 1 <= workers <= 64:
        raise ValueError("--workers must be between 1 and 64")
    workers = min(workers, len(pending)) if pending else 0
    print(
        f"Schedule: {len(schedule)} matches; already reported: {len(existing)}; "
        f"pending now: {len(pending)}; workers: {workers}"
    )
    if not pending:
        leaderboard = write_artifacts(
            config, schedule, list(existing.values()), args.out, runtime,
        )
        _print_leaderboard(leaderboard)
        return 0

    participants = _participant_map(config)
    run_config = config.get("run", {})
    retries = int(run_config.get("retries", 0))
    fallback = str(run_config.get("fallback", "fail"))
    max_turns = run_config.get("max_turns")
    emit_every = int(config.get("results", {}).get("emit_every", 10))
    completed_since_emit = 0
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="frontier12") as pool:
        futures = {}
        for match in pending:
            previous = existing.get(match["ordinal"])
            attempt = int(previous.get("attempt", 0)) + 1 if previous else 1
            future = pool.submit(
                run_one, match, participants, args.out,
                attempt=attempt, retries=retries, fallback=fallback, max_turns=max_turns,
            )
            futures[future] = match
        for finished, future in enumerate(as_completed(futures), start=1):
            match = futures[future]
            row = future.result()
            existing[row["ordinal"]] = row
            _write_json(_result_path(args.out, row["ordinal"]), row)
            completed_since_emit += 1
            state = "ok" if row["status"] == "ok" else f"error: {row.get('error', '')[:100]}"
            print(
                f"[{finished:>3}/{len(pending)}] #{match['ordinal']:03d} "
                f"{match['game']} {match['player_count']}p attempt={row['attempt']} {state}",
                flush=True,
            )
            if completed_since_emit >= emit_every:
                write_artifacts(
                    config, schedule, list(existing.values()), args.out, runtime,
                )
                completed_since_emit = 0

    leaderboard = write_artifacts(
        config, schedule, list(existing.values()), args.out, runtime,
    )
    print()
    _print_leaderboard(leaderboard)
    print(f"\nResults: {args.out / 'matches.jsonl'}")
    print(f"Scores:  {args.out / 'leaderboard.csv'}")
    return 0


def command_score(args: argparse.Namespace) -> int:
    config_path = args.out / "config.json"
    schedule_path = args.out / "schedule.json"
    if not config_path.is_file() or not schedule_path.is_file():
        raise ValueError("output directory does not contain config.json and schedule.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    runtime_path = args.out / "runtime.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8")) if runtime_path.is_file() else None
    leaderboard = write_artifacts(
        config, schedule, list(_existing_results(args.out).values()), args.out, runtime,
    )
    _print_leaderboard(leaderboard)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    schedule = commands.add_parser("schedule", help="validate and summarize the deterministic schedule")
    schedule.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    check = commands.add_parser("check", help="validate schedule, credentials, endpoints, and CLIs")
    check.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run = commands.add_parser("run", help="run or resume the tournament")
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--workers", type=int, help="concurrent matches; default comes from config")
    run.add_argument("--limit", type=int, help="run only the first N pending matches")
    run.add_argument(
        "--probe-all-participants", action="store_true",
        help="run a small greedy subset that covers every participant at least once",
    )
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--retry-errors", action="store_true")
    score = commands.add_parser("score", help="rebuild summary and leaderboard from per-match results")
    score.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "schedule":
            return command_schedule(args)
        if args.command == "check":
            return command_check(args)
        if args.command == "run":
            return command_run(args)
        return command_score(args)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
