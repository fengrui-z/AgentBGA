"""Matched self-play with persistent versus fresh native harness sessions.

Each independent series is an experimental unit. Resume is supported only at
acknowledged match boundaries, including both terminal reviews. An uncertain
native invocation must never be replayed against already-mutated memory.
"""

from __future__ import annotations

from dataclasses import replace
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import secrets
import shutil
import subprocess
from typing import Any

from .agents import PlayerConfig, harness_executable_name
from .experiment import _identifier, _utc_now, _write_atomic
from .harness import HarnessAgent
from .registry import get_game
from .runner import run_match
from .store import Store

SCHEMA = "agentbga.longterm.v1"
BACKENDS = {"qwen", "opencode", "dsh"}
MEMORY_PATHS = (
    "strategy-notes.md", "agentbga-harness-session.json",
    ".qwen-home", ".dsh-home", ".opencode-data", ".opencode-state",
)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def validate(config: dict) -> None:
    if config.get("schema_version") != SCHEMA:
        raise ValueError(f"schema_version must be {SCHEMA}")
    _identifier(config.get("experiment_id"), "experiment_id")
    if config.get("game") != "splendor" or not config.get("rules_version"):
        raise ValueError("this experiment requires Splendor and a pinned rules_version")
    get_game("splendor", config["rules_version"])
    agents = config.get("agents")
    if not isinstance(agents, list) or not agents:
        raise ValueError("agents must be a nonempty list")
    seen = set()
    for agent in agents:
        identifier = _identifier(agent.get("id"), "agent id")
        if identifier in seen:
            raise ValueError("duplicate agent id")
        seen.add(identifier)
        player = agent["player"]
        if set(player) != {"backend", "model", "base_url", "api_key_env", "reasoning_effort"}:
            raise ValueError("player must specify only backend/model/base_url/api_key_env/reasoning_effort")
        if player["backend"] not in BACKENDS or not all(player.values()):
            raise ValueError("use an explicitly configured Qwen, OpenCode or DSh API harness")
        PlayerConfig.from_dict({**player, "name": "Player A", "participant_id": "player-a"}, 0)
    stages = config.get("stages", {})
    if not stages:
        raise ValueError("at least one stage is required")
    for name, stage in stages.items():
        _identifier(name, "stage")
        if stage.get("length") not in {10, 20}:
            raise ValueError("series length must be 10 or 20")
        if type(stage.get("replicates")) is not int or stage["replicates"] < 1:
            raise ValueError("replicates must be a positive integer")
        for key in ("base_seed", "order_seed"):
            if type(stage.get(key)) is not int:
                raise ValueError(f"stage {key} must be an integer")
    intervals = sorted((s["base_seed"], s["base_seed"] + s["length"] * s["replicates"] - 1)
                       for s in stages.values())
    if any(a[1] >= b[0] for a, b in zip(intervals, intervals[1:])):
        raise ValueError("stage seed ranges must be disjoint")
    if set(config["run"]) != {"timeout_seconds", "max_turns"}:
        raise ValueError("run must specify timeout_seconds and max_turns")
    for value in config["run"].values():
        if type(value) is not int or value <= 0:
            raise ValueError("timeouts and turn caps must be positive integers")


def schedule(config: dict, stage_name: str) -> list[dict]:
    validate(config)
    if stage_name not in config["stages"]:
        raise ValueError(f"unknown stage: {stage_name}")
    stage = config["stages"][stage_name]
    rng = random.Random(stage["order_seed"])
    # Balance which anonymous identity owns memory, without telling the model.
    first_identity = rng.randrange(2)
    identities = [(i + first_identity) % 2 for i in range(stage["replicates"])]
    rng.shuffle(identities)
    starts = [rng.randrange(2) for _ in identities]
    rows = []
    for replicate in range(stage["replicates"]):
        for agent in config["agents"]:
            for index in range(stage["length"]):
                seed = stage["base_seed"] + replicate * stage["length"] + index
                if not -(2**63) <= seed < 2**63:
                    raise ValueError("seed exceeds SQLite signed 64-bit range")
                rows.append({
                    "ordinal": len(rows) + 1, "agent_id": agent["id"],
                    "replicate": replicate + 1, "game_index": index + 1,
                    "series_id": f"{config['experiment_id']}:{stage_name}:{agent['id']}:r{replicate + 1}",
                    "seed": seed, "persistent_identity": identities[replicate],
                    "persistent_seat": (starts[replicate] + index) % 2,
                })
    return rows


def runtime_signature(config: dict) -> dict:
    """Record local code and executable versions without logging credentials."""
    versions = {}
    for row in config["agents"]:
        player = row["player"]
        if not os.environ.get(player["api_key_env"]):
            raise ValueError(f"missing credential environment variable: {player['api_key_env']}")
        backend = player["backend"]
        if backend in versions:
            continue
        executable = shutil.which(harness_executable_name(backend))
        if not executable:
            raise ValueError(f"missing harness executable: {backend}")
        result = subprocess.run([executable, "--version"], capture_output=True,
                                text=True, timeout=15, check=True)
        versions[backend] = {"path": executable, "version": result.stdout.strip()}
        if not versions[backend]["version"]:
            raise ValueError(f"could not identify harness version: {backend}")
    root = Path(__file__).parent
    sources = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(root.rglob("*")) if p.suffix in {".py", ".mjs"}}
    return {"code_sha256": digest(sources), "harnesses": versions}


def memory_snapshot(workspace: Path) -> dict:
    """Fingerprint native memory, without copying API credentials or following links."""
    files = {}
    for name in MEMORY_PATHS:
        base = workspace / name
        paths = [base] if base.is_file() else sorted(base.rglob("*")) if base.is_dir() else []
        for path in paths:
            if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != workspace):
                continue
            if path.is_file():
                with path.open("rb") as handle:
                    files[str(path.relative_to(workspace))] = hashlib.file_digest(handle, "sha256").hexdigest()
    return {"workspace": str(workspace), "files": files, "sha256": digest(files)}


def player_configs(config: dict, row: dict, run_id: str) -> list[PlayerConfig]:
    shared = next(a["player"] for a in config["agents"] if a["id"] == row["agent_id"])
    players = []
    for seat in range(2):
        persistent = seat == row["persistent_seat"]
        identity = row["persistent_identity"] if persistent else 1 - row["persistent_identity"]
        value = {**shared, "name": "Player A" if identity == 0 else "Player B",
                 "participant_id": "player-a" if identity == 0 else "player-b"}
        if persistent:
            value["series_id"] = row["series_id"]
        players.append(replace(PlayerConfig.from_dict(value, seat), memory_namespace=run_id))
    return players


def summarize(rows: list[dict], plan: list[dict]) -> dict:
    """Descriptive per-series readout; games are not independent replications."""
    series = []
    for series_id in dict.fromkeys(p["series_id"] for p in plan):
        scheduled = [p for p in plan if p["series_id"] == series_id]
        observed = [r for r in rows if r["series_id"] == series_id]
        windows = {}
        for name, lo, hi in (("games_1_10", 1, 10), ("games_11_20", 11, 20)):
            expected = sum(lo <= p["game_index"] <= hi for p in scheduled)
            selected = [r for r in observed if lo <= r["game_index"] <= hi]
            scores = []
            for row in selected:
                if row.get("terminal"):
                    ranks = {r["seat"]: r["rank"] for r in row["result"]["rankings"]}
                    own = row["persistent_seat"]
                    scores.append(1.0 if ranks[own] < ranks[1-own] else
                                  0.5 if ranks[own] == ranks[1-own] else 0.0)
            windows[name] = {
                "scheduled": expected, "reported": len(selected), "terminal": len(scores),
                "protocol_failures": sum(r["status"] != "ok" for r in selected),
                "persistent_win_score_completed": sum(scores) / len(scores) if scores else None,
                "complete_window": bool(expected) and len(scores) == expected,
                "protocol_complete_window": bool(expected) and len(selected) == expected
                    and all(r["status"] == "ok" for r in selected),
                "win_score_bounds_all_scheduled": (
                    [sum(scores) / expected, (sum(scores) + expected - len(scores)) / expected]
                    if expected else None
                ),
            }
        series.append({"series_id": series_id, "agent_id": scheduled[0]["agent_id"],
                       "replicate": scheduled[0]["replicate"], "windows": windows})
    return {"scheduled": len(plan), "reported": len(rows),
            "protocol_complete": sum(r["status"] == "ok" for r in rows),
            "independent_unit": "series", "series": series}


def _play(config: dict, row: dict, out: Path, run_id: str, expected_memory: dict | None) -> dict:
    players = player_configs(config, row, run_id)
    agents = {}
    before = {}
    result_row = {**row, "status": "running", "terminal": False, "started_at": _utc_now()}
    database = out / "matches" / f"match-{row['ordinal']:04d}.sqlite3"
    store = Store(database)
    try:
        match_id, _, _ = store.create(2, row["seed"], "splendor", rules_version=config["rules_version"])
        result_row["match_id"] = match_id

        def factory(player, match_id, seat, event_sink):
            agent = HarnessAgent(player, match_id, seat, event_sink=event_sink,
                                 timeout=config["run"]["timeout_seconds"], runs_root=out / "runtime")
            snapshot = memory_snapshot(agent.session.workspace)
            if seat == row["persistent_seat"] and expected_memory:
                if snapshot != expected_memory:
                    raise ValueError("persistent native memory changed or is missing at the match boundary")
            elif snapshot["files"]:
                raise ValueError("new identity unexpectedly inherited native memory")
            before[seat] = {"session_id": agent.session.session_id, "memory": snapshot}
            agent.new_match_context = (
                f"A new Splendor match is starting: {match_id}. Your stable identity is {player.name}; "
                f"you are now seat {seat}, and your opponent is {players[1-seat].name} at seat {1-seat}. "
                "The board and action IDs are new. Earlier boards, scores and action IDs do not apply. "
                "Use only your own available notes and observations. Maximize your chance of winning this match."
            )
            agents[seat] = agent
            return agent

        result = run_match(store, match_id, players, retries=0, fallback="fail",
                           max_turns=config["run"]["max_turns"], harness_factory=factory)
        version, state, _ = store.load(match_id)
        if state["status"] != "finished":
            raise ValueError("runner returned without a terminal state")
        result_row.update(result=result, terminal=True)
        reviews = {}
        # Alternate review order too; this does not change the finished board.
        for seat in (row["game_index"] % 2, 1 - row["game_index"] % 2):
            observation = store.game(match_id).observe(state, seat)
            observation["state_version"] = version
            feedback = {
                "match_id": match_id, "your_identity": players[seat].name, "your_seat": seat,
                "rankings": [{"identity": players[r["seat"]].name, "seat": r["seat"],
                              "rank": r["rank"], "score": r.get("score")}
                             for r in result["rankings"]],
            }
            # Persist feedback BEFORE sending it; this is not an acknowledgement.
            _write_atomic(out / "feedback" / f"{row['ordinal']:04d}-seat-{seat}.json", feedback)
            # run_match has finished; route review events directly to SQLite.
            agents[seat].event_sink = lambda event: store.record_harness_event(match_id, version, event)
            reviews[seat] = agents[seat].review_match(observation, feedback)
            result_row["reviews"] = dict(reviews)
            if not agents[seat].session.session_id:
                raise ValueError("harness did not return a native session ID")
            old_id = before[seat]["session_id"]
            if old_id and agents[seat].session.session_id != old_id:
                raise ValueError("native harness silently replaced an existing session")
        result_row["reviews"] = reviews
        result_row["status"] = "ok"
    except Exception as exc:
        result_row["status"] = "error"
        # Harness errors are redacted at their origin; keep the error type here.
        result_row["error_type"] = type(exc).__name__
        result_row["error"] = "Match or terminal review failed; inspect the local SQLite and traces."
        if isinstance(exc, ValueError):
            result_row["error"] = str(exc)
    finally:
        result_row["memory_before"] = before
        result_row["memory_after"] = {
            seat: {"session_id": a.session.session_id, "memory": memory_snapshot(a.session.workspace)}
            for seat, a in agents.items()
        }
        for seat, agent in agents.items():
            notes = agent.session.workspace / "strategy-notes.md"
            if notes.is_file() and not notes.is_symlink():
                _write_atomic(out / "feedback" / f"{row['ordinal']:04d}-seat-{seat}-notes.json",
                              {"seat": seat, "notes": notes.read_text(encoding="utf-8")})
        result_row["finished_at"] = _utc_now()
        store.close()
    return result_row


def run(config: dict, stage: str, output: Path, *, resume: bool = False,
        limit_matches: int | None = None) -> dict:
    plan = schedule(config, stage)
    if limit_matches is not None and (type(limit_matches) is not int or limit_matches < 1):
        raise ValueError("limit_matches must be positive")
    runtime = runtime_signature(config)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / "run.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("another runner owns this output directory") from exc
        return _run_locked(config, stage, plan, output, runtime, resume, limit_matches)


def _run_locked(config, stage, plan, output, runtime, resume, limit):
    checkpoint_path = output / "checkpoint.json"
    frozen = {"config": config, "stage": stage, "schedule": plan, "runtime": runtime}
    if resume:
        checkpoint = json.loads(checkpoint_path.read_text())
        if json.loads((output / "plan.json").read_text()) != frozen:
            raise ValueError("config, stage, schedule or runtime changed; cannot resume this series")
        if checkpoint["status"] != "ready":
            raise ValueError("unacknowledged/failed match: native memory may have changed; automatic replay refused")
        for snapshot in checkpoint["memory"].values():
            if memory_snapshot(Path(snapshot["workspace"])) != snapshot:
                raise ValueError("checkpoint native memory changed or is missing")
    else:
        if any(p.name != "run.lock" for p in output.iterdir()):
            raise ValueError("output is not empty; use --resume for an acknowledged checkpoint")
        for name in ("matches", "results", "feedback", "runtime"):
            (output / name).mkdir()
        _write_atomic(output / "plan.json", frozen)
        checkpoint = {"run_id": secrets.token_hex(16), "status": "ready", "next_ordinal": 1,
                      "memory": {}, "result_hashes": {}}
        _write_atomic(checkpoint_path, checkpoint)
    rows = []
    for ordinal in range(1, checkpoint["next_ordinal"]):
        row = json.loads((output / "results" / f"match-{ordinal:04d}.json").read_text())
        if (row["status"] != "ok" or row["ordinal"] != ordinal
                or digest(row) != checkpoint["result_hashes"].get(str(ordinal))):
            raise ValueError("checkpoint result history is inconsistent")
        rows.append(row)
    remaining = plan[checkpoint["next_ordinal"] - 1:]
    if limit is not None:
        remaining = remaining[:limit]
    for scheduled in remaining:
        checkpoint.update(status="running", active_ordinal=scheduled["ordinal"])
        _write_atomic(checkpoint_path, checkpoint)
        row = _play(config, scheduled, output, checkpoint["run_id"],
                    checkpoint["memory"].get(scheduled["series_id"]))
        _write_atomic(output / "results" / f"match-{scheduled['ordinal']:04d}.json", row)
        rows.append(row)
        if row["status"] == "ok":
            checkpoint["result_hashes"][str(scheduled["ordinal"])] = digest(row)
            checkpoint["memory"][scheduled["series_id"]] = row["memory_after"][scheduled["persistent_seat"]]["memory"]
            checkpoint.update(status="ready", next_ordinal=scheduled["ordinal"] + 1)
            checkpoint.pop("active_ordinal", None)
        else:
            checkpoint["status"] = "failed"
        _write_atomic(checkpoint_path, checkpoint)
        _write_atomic(output / "summary.json", summarize(rows, plan))
        write_trajectory(output, rows)
        if checkpoint["status"] == "failed":
            raise RuntimeError(f"series stopped at match {scheduled['ordinal']}; see {output / 'results'}")
    summary = summarize(rows, plan)
    _write_atomic(output / "summary.json", summary)
    write_trajectory(output, rows)
    return summary


def write_trajectory(output: Path, rows: list[dict]) -> None:
    fields = ["agent_id", "replicate", "series_id", "game_index", "seed", "persistent_seat",
              "status", "terminal", "persistent_win_score", "persistent_score_margin"]
    temporary = output / "trajectory.csv.tmp"
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            record = {key: row[key] for key in fields if key in row}
            if row["terminal"]:
                ranks = {r["seat"]: r for r in row["result"]["rankings"]}
                own, other = ranks[row["persistent_seat"]], ranks[1-row["persistent_seat"]]
                record["persistent_win_score"] = (1 if own["rank"] < other["rank"] else
                                                  0.5 if own["rank"] == other["rank"] else 0)
                if isinstance(own.get("score"), (int, float)) and isinstance(other.get("score"), (int, float)):
                    record["persistent_score_margin"] = own["score"] - other["score"]
            writer.writerow(record)
    temporary.replace(output / "trajectory.csv")
