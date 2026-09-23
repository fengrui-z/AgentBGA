"""Frozen matched-harness studies and seat-safe checkpoint continuations.

Run ``python -m agentbga.rq2 --help``. Planning never invokes a model. Runs
are serial, bounded by an explicit match limit, and preserve every attempt.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import fcntl
import itertools
import json
import math
import os
from pathlib import Path
import random
import shutil
import statistics
import sys
from typing import Any

from .agents import PlayerConfig
from .harness import HarnessAgent
from .registry import get_game
from .runner import run_match
from .store import Store


STUDY_SCHEMA = "agentbga.rq2.v1"
CHECKPOINT_SCHEMA = "agentbga.checkpoint.v1"
MODELS = {"qwen3.8-max", "qwen3.8-flash", "glm-5.2"}
HARNESSES = ("opencode", "qwen")
GAMES = ("splendor", "seven_wonders")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def integer(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or value >= 2**63:
        raise ValueError(f"{label} must be an integer in [{minimum}, 2**63)")
    return value


def exact_keys(value: Any, allowed: set[str], label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if set(value) - allowed:
        raise ValueError(f"{label} has unknown fields: {', '.join(sorted(set(value) - allowed))}")


def code_fingerprint() -> str:
    root = Path(__file__).parent
    return digest({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(root.rglob("*.py"))})


def validate_manifest(value: dict) -> None:
    exact_keys(value, {"schema_version", "study_id", "stage", "models", "anchors", "games",
                       "schedule", "budget", "checkpoint_files", "conditions", "history_window"}, "study")
    if value.get("schema_version") != STUDY_SCHEMA:
        raise ValueError(f"schema_version must be {STUDY_SCHEMA}")
    name = value.get("study_id")
    if not isinstance(name, str) or not name or len(name) > 80 or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in name):
        raise ValueError("study_id must contain 1-80 lowercase letters, digits, '-' or '_'")
    if value.get("stage") not in {"pilot", "confirmatory"}:
        raise ValueError("stage must be pilot or confirmatory")
    models = value.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("models must be a non-empty list")
    names = []
    for item in models:
        exact_keys(item, {"model", "base_url", "api_key_env", "reasoning_effort", "snapshot"}, "model")
        if item.get("model") not in MODELS:
            raise ValueError(f"focal model must be one of {sorted(MODELS)}")
        names.append(item["model"])
        if not all(isinstance(item.get(k), str) and item[k] for k in ("base_url", "api_key_env", "reasoning_effort", "snapshot")):
            raise ValueError("each model requires base_url, api_key_env, reasoning_effort and snapshot")
        if value["stage"] == "confirmatory" and item["snapshot"] == "unresolved":
            raise ValueError("resolve model snapshot provenance before a confirmatory run")
        for harness in HARNESSES:
            PlayerConfig.from_dict({k: v for k, v in {**item, "backend": harness}.items() if k != "snapshot"}, 0)
    if len(set(names)) != len(names):
        raise ValueError("duplicate focal models")
    anchors = value.get("anchors")
    if not isinstance(anchors, list) or len(anchors) != 2:
        raise ValueError("exactly two anchors are required")
    for seat, item in enumerate(anchors, 1):
        if not isinstance(item, dict):
            raise ValueError("each anchor must be a player object")
        if item.get("backend") not in {*HARNESSES, "random"}:
            raise ValueError("anchors must use opencode, qwen or random")
        if item.get("series_id") or item.get("participant_id"):
            raise ValueError("anchor memory is assigned by the study and must be match-scoped")
        PlayerConfig.from_dict(item, seat)
    games = value.get("games")
    if not isinstance(games, list) or not games or len(set(games)) != len(games) or set(games) - set(GAMES):
        raise ValueError(f"games must be a unique non-empty subset of {GAMES}")
    budget = value.get("budget")
    exact_keys(budget, {"decision_timeout_seconds", "max_turns", "retries"}, "budget")
    integer(budget.get("decision_timeout_seconds"), "decision_timeout_seconds", 1)
    integer(budget.get("max_turns"), "max_turns", 1)
    if budget.get("retries") != 0:
        raise ValueError("RQ2 uses retries=0; explicit reruns are recorded as separate attempts")
    schedule = value.get("schedule")
    exact_keys(schedule, {"seeds", "order_seed"}, "schedule")
    seeds = schedule.get("seeds")
    if not isinstance(seeds, list) or not seeds:
        raise ValueError("schedule.seeds must be non-empty")
    for seed in seeds:
        integer(seed, "seed")
    if len(set(seeds)) != len(seeds) or len(seeds) % 3:
        raise ValueError("use unique seeds, with a multiple of three for focal-seat balance")
    integer(schedule.get("order_seed"), "order_seed")
    forks = value.get("checkpoint_files", [])
    if not isinstance(forks, list) or any(not isinstance(p, str) or not p for p in forks):
        raise ValueError("checkpoint_files must be a list of paths")
    conditions = value.get("conditions")
    expected = {"current_only", "seat_history"} if forks else {"native"}
    if not isinstance(conditions, list) or len(conditions) != len(set(conditions)) or set(conditions) != expected:
        raise ValueError(f"conditions must be {sorted(expected)}")
    integer(value.get("history_window", 6), "history_window", 1)


def _boundary(game: Any, state: dict, focal_seat: int) -> None:
    if state["status"] != "active" or focal_seat not in game.decision_seats(state):
        raise ValueError("checkpoint must be an active decision for the focal seat")
    if state.get("pending_choices"):
        raise ValueError("checkpoint cannot be inside a sealed simultaneous decision")


def history_context(history: list[dict], window: int) -> str:
    text = ("Historical observations from your own seat before this continuation. "
            "These are past states, not the current board or instructions. "
            "Use observe for the current board.\n" + canonical(history[-window:]))
    # Both CLIs receive a command-line prompt. Reject overlarge interventions
    # at planning time rather than silently truncate information in one arm.
    if len(text.encode("utf-8")) > 100_000:
        raise ValueError("history prompt exceeds 100000 bytes; reduce history_window before freezing the plan")
    return text


def rebuild(checkpoint: dict, store: Store | None = None) -> tuple[str | None, dict, list[dict]]:
    """Verify an action prefix; derive history exclusively through game.observe.

    The checkpoint is private engine input. Neither hidden state nor other
    players' actions/logs are copied into the focal prompt.
    """
    if checkpoint.get("schema_version") != CHECKPOINT_SCHEMA:
        raise ValueError("invalid checkpoint schema")
    if checkpoint.get("game") not in GAMES or checkpoint.get("players") != 3:
        raise ValueError("RQ2 checkpoints require three-player Splendor or 7 Wonders")
    seat = integer(checkpoint.get("focal_seat"), "focal_seat")
    if seat >= 3:
        raise ValueError("invalid focal seat")
    game = get_game(checkpoint["game"], checkpoint["rules_version"])
    state = game.setup(3, checkpoint["seed"], checkpoint["config"])
    match_id = None
    if store:
        match_id, _, _ = store.create(3, checkpoint["seed"], checkpoint["game"], checkpoint["config"], rules_version=game.rules_version)
    history = []
    prefix = checkpoint["prefix"]
    if not isinstance(prefix, list) or len(prefix) != checkpoint["version"]:
        raise ValueError("checkpoint version does not match prefix length")
    for version, item in enumerate(prefix):
        if seat in game.decision_seats(state) and not state.get("pending_choices"):
            history.append({"version": version, "observation": deepcopy(game.observe(state, seat))})
        state, _ = game.apply_action(state, item["seat"], item["action"])
        if game.state_hash(state) != item["state_hash"]:
            raise ValueError(f"checkpoint replay mismatch at version {version + 1}")
        if store:
            store.act(match_id, item["seat"], version, item["action"])
    if game.state_hash(state) != checkpoint["state_hash"]:
        raise ValueError("checkpoint final hash mismatch")
    game.validate_state(state)
    _boundary(game, state, seat)
    return match_id, state, history


def export_checkpoint(database: Path, match_id: str, version: int | None, focal_seat: int,
                      decision_index: int | None = None) -> dict:
    if not database.is_file():
        raise ValueError("source database does not exist")
    source = Store(database)
    try:
        source.replay(match_id)
        current_version, state, _ = source.load(match_id)
        events = source.connection.execute("SELECT * FROM events WHERE match_id=? ORDER BY seq", (match_id,)).fetchall()
        created = json.loads(events[0]["event_json"])
        if decision_index is not None:
            integer(decision_index, "decision_index", 1)
            if version is not None:
                raise ValueError("select either a version or a focal decision index")
            game = source.game(match_id)
            probe = game.setup(state["player_count"], created["seed"], created["config"])
            seen = 0
            for row in events[1:]:
                event = json.loads(row["event_json"])
                if event.get("type") != "action_accepted":
                    continue
                if focal_seat in game.decision_seats(probe) and not probe.get("pending_choices"):
                    seen += 1
                    if seen == decision_index:
                        version = row["version"] - 1
                        break
                probe, _ = game.apply_action(probe, row["seat"], event["action"])
            if version is None:
                raise ValueError("source did not reach the requested focal decision index")
        if type(version) is not int or not 0 <= version <= current_version:
            raise ValueError("checkpoint version is outside the source trajectory")
        prefix = []
        final_hash = events[0]["state_hash"]
        for row in events[1:]:
            event = json.loads(row["event_json"])
            if row["version"] <= version and event.get("type") == "action_accepted":
                prefix.append({"seat": row["seat"], "action": event["action"], "state_hash": row["state_hash"]})
                final_hash = row["state_hash"]
        checkpoint = {
            "schema_version": CHECKPOINT_SCHEMA, "source_match_id": match_id,
            "game": source.game_id(match_id), "rules_version": source.rules_version(match_id),
            "players": state["player_count"], "seed": created["seed"], "config": created["config"],
            "version": version, "focal_seat": focal_seat, "prefix": prefix, "state_hash": final_hash,
            "selection": {"decision_index": decision_index, "version": version},
        }
        _, _, history = rebuild(checkpoint)
        if not history:
            raise ValueError("history intervention requires at least one prior focal observation")
        return checkpoint
    finally:
        source.close()


def make_plan(manifest: dict, base: Path) -> dict:
    validate_manifest(manifest)
    manifest = deepcopy(manifest)
    rng = random.Random(manifest["schedule"]["order_seed"])
    scenarios = []
    checkpoints = {}
    for path in manifest.get("checkpoint_files", []):
        checkpoint = read_json(base / path)
        _, _, history = rebuild(checkpoint)
        if not history:
            raise ValueError("history intervention requires a nonempty observation prefix")
        history_context(history, manifest.get("history_window", 6))
        if checkpoint["game"] not in manifest["games"]:
            raise ValueError("checkpoint game is not in the declared study")
        if checkpoint["seed"] not in manifest["schedule"]["seeds"]:
            raise ValueError("checkpoint seed is not in the preregistered seed list")
        key = digest(checkpoint)
        if key in checkpoints:
            raise ValueError("duplicate checkpoint")
        checkpoints[key] = checkpoint
        scenarios.append({"game": checkpoint["game"], "seed": checkpoint["seed"],
                          "focal_seat": checkpoint["focal_seat"], "checkpoint": key,
                          "source_cluster": checkpoint["source_match_id"]})
    if not scenarios:
        for game in manifest["games"]:
            for index, seed in enumerate(manifest["schedule"]["seeds"]):
                scenarios.append({"game": game, "seed": seed, "focal_seat": index % 3,
                                  "checkpoint": None, "source_cluster": f"{game}:{seed}"})
    else:
        for game in manifest["games"]:
            subset = [s for s in scenarios if s["game"] == game]
            if not subset or {s["seed"] for s in subset} != set(manifest["schedule"]["seeds"]):
                raise ValueError("each game must provide checkpoints for every declared seed")
        source_keys = [(s["game"], s["source_cluster"]) for s in scenarios]
        if len(set(source_keys)) != len(source_keys):
            raise ValueError("v1 uses one checkpoint per source match; do not pseudoreplicate trajectories")
        if len({(s["game"], s["seed"]) for s in scenarios}) != len(scenarios):
            raise ValueError("v1 uses one checkpoint per game/seed")
        for game in manifest["games"]:
            counts = [sum(s["game"] == game and s["focal_seat"] == seat for s in scenarios) for seat in range(3)]
            if len(set(counts)) != 1:
                raise ValueError("checkpoint focal seats must be balanced within each game")
    rows = []
    rng.shuffle(scenarios)
    for scenario in scenarios:
        scenario_id = digest(scenario)[:16]
        cells = list(itertools.product(manifest["models"], HARNESSES, manifest["conditions"]))
        rng.shuffle(cells)
        for model, harness, condition in cells:
            row = {**scenario, "scenario_id": scenario_id, "model": model["model"],
                   "harness": harness, "condition": condition,
                   "rules_version": checkpoints[scenario["checkpoint"]]["rules_version"] if scenario["checkpoint"] else get_game(scenario["game"]).rules_version}
            row["row_id"] = digest(row)[:20]
            row["ordinal"] = len(rows) + 1
            rows.append(row)
    payload = {"schema_version": "agentbga.rq2-plan.v1", "manifest": manifest,
               "code_fingerprint": code_fingerprint(), "rows": rows, "checkpoints": checkpoints}
    return {**payload, "plan_hash": digest(payload)}


def load_plan(directory: Path) -> dict:
    plan = read_json(directory / "plan.json")
    if digest({k: v for k, v in plan.items() if k != "plan_hash"}) != plan["plan_hash"]:
        raise ValueError("frozen plan hash mismatch")
    if plan["code_fingerprint"] != code_fingerprint():
        raise ValueError("engine/runner source changed; create a new plan instead of mixing executions")
    validate_manifest(plan["manifest"])
    return plan


def _players(plan: dict, row: dict, smoke: bool) -> list[PlayerConfig]:
    model = next(m for m in plan["manifest"]["models"] if m["model"] == row["model"])
    focal = {k: v for k, v in model.items() if k != "snapshot"}
    focal.update(name=f"focal-{row['model']}-{row['harness']}", backend=row["harness"], participant_id="focal")
    anchors = iter(deepcopy(plan["manifest"]["anchors"]))
    configs = []
    for seat in range(3):
        item = focal if seat == row["focal_seat"] else next(anchors)
        if smoke:
            item = {"name": f"smoke-seat-{seat}", "backend": "random"}
        configs.append(PlayerConfig.from_dict(item, seat))
    return configs


def pws(rankings: list[dict], seat: int) -> float:
    rank = next(r["rank"] for r in rankings if r["seat"] == seat)
    others = [r for r in rankings if r["seat"] != seat]
    return sum(1 if rank < r["rank"] else 0.5 if rank == r["rank"] else 0 for r in others) / len(others)


def _runtime_provenance(smoke: bool) -> dict:
    executables = {}
    if not smoke:
        for name in HARNESSES:
            binary = shutil.which(name)
            if not binary:
                raise ValueError(f"missing harness executable: {name}")
            # Avoid version commands that may contact providers or initialize sessions.
            path = Path(binary).resolve()
            executables[name] = {"path": str(path), "entrypoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return {"smoke": smoke, "executables": executables, "python": sys.version,
            "budget_scope": "per-decision wall-time limit; no claim of equal token/compute budgets"}


@contextmanager
def run_lock(directory: Path):
    with (directory / ".run.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("another process is executing this study") from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def run_study(directory: Path, *, max_matches: int, smoke: bool = False, retry_failed: bool = False) -> dict:
    with run_lock(directory):
        return _run_study(directory, max_matches=max_matches, smoke=smoke, retry_failed=retry_failed)


def _run_study(directory: Path, *, max_matches: int, smoke: bool, retry_failed: bool) -> dict:
    integer(max_matches, "max_matches", 1)
    plan = load_plan(directory)
    provenance = _runtime_provenance(smoke)
    runtime = directory / "runtime.json"
    if runtime.exists() and read_json(runtime) != provenance:
        raise ValueError("runtime changed (or smoke/live mixed); use a new output directory")
    if not smoke:
        configs = [c for row in plan["rows"] for c in _players(plan, row, False)]
        for config in configs:
            if config.api_key_env and not os.environ.get(config.api_key_env):
                raise ValueError(f"missing API key environment variable: {config.api_key_env}")
    write_json(runtime, provenance)
    executed = 0
    for row in plan["rows"]:
        row_directory = directory / "attempts" / row["row_id"]
        previous = sorted(row_directory.glob("*.json"))
        records = [read_json(p) for p in previous]
        if any(r["status"] == "finished" for r in records):
            continue
        if records and not retry_failed:
            continue
        if executed >= max_matches:
            break
        attempt = len(previous) + 1
        path = row_directory / f"{attempt:04d}.json"
        record = {"schema_version": "agentbga.rq2-attempt.v1", "plan_hash": plan["plan_hash"],
                  "row_id": row["row_id"], "attempt": attempt, "status": "running", "smoke": smoke,
                  "started_at": datetime.now(timezone.utc).isoformat(), "match_id": None}
        write_json(path, record)
        store = Store(directory / "matches.sqlite3")
        try:
            history = []
            if row["checkpoint"]:
                match_id, _, history = rebuild(plan["checkpoints"][row["checkpoint"]], store)
            else:
                match_id, _, _ = store.create(3, row["seed"], row["game"], rules_version=row["rules_version"])
            record["match_id"] = match_id
            write_json(path, record)
            players = _players(plan, row, smoke)
            context = ""
            if row["condition"] == "seat_history":
                context = history_context(history, plan["manifest"].get("history_window", 6))
            record["prefix_history_hash"] = digest(history)
            record["injected_context_hash"] = digest(context)
            record["injected_context_chars"] = len(context)
            write_json(path, record)

            # This intervention deliberately supplies the same frozen prefix on
            # each continuation turn. It does not transplant a native session.

            def factory(config: PlayerConfig, ident: str, seat: int, sink: Any) -> HarnessAgent:
                return HarnessAgent(config, ident, seat, event_sink=sink,
                                    runs_root=directory / "runs",
                                    timeout=plan["manifest"]["budget"]["decision_timeout_seconds"],
                                    turn_context=context if seat == row["focal_seat"] else "")

            # The JSONL is private research telemetry, not a public spectator feed.
            with (row_directory / f"{attempt:04d}.events.jsonl").open("w", encoding="utf-8") as stream:
                def sink(event: dict) -> None:
                    if event.get("type") not in {"agent_stream", "harness_output"}:
                        stream.write(canonical(event) + "\n")
                        stream.flush()
                result = run_match(store, match_id, players, retries=0, fallback="fail",
                                   max_turns=plan["manifest"]["budget"]["max_turns"], sink=sink,
                                   harness_factory=factory)
            store.replay(match_id)
            focal = next(r for r in result["rankings"] if r["seat"] == row["focal_seat"])
            record.update(status="finished", pws=pws(result["rankings"], row["focal_seat"]),
                          focal_ranking=focal, result=result)
        except Exception as error:
            # Error strings can include provider credentials. Preserve the type;
            # harness traces provide their existing redacted diagnostic detail.
            record.update(status="failed", error_type=type(error).__name__)
        finally:
            if record["match_id"]:
                record["controller_calls"] = store.controller_calls(record["match_id"])
            store.close()
            record["ended_at"] = datetime.now(timezone.utc).isoformat()
            write_json(path, record)
        executed += 1
    report = analyze(directory)
    write_json(directory / "summary.json", report)
    return {"executed": executed, "scheduled": len(plan["rows"]), "summary": str(directory / "summary.json")}


def _interval(values: list[float], rng: random.Random, draws: int) -> list[float] | None:
    if len(values) < 2:
        return None
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(draws))
    return [means[math.floor((draws - 1) * .025)], means[math.ceil((draws - 1) * .975)]]


def analyze(directory: Path, draws: int = 5000) -> dict:
    integer(draws, "bootstrap draws", 100)
    plan = load_plan(directory)
    first = {}
    attempts = []
    for row in plan["rows"]:
        paths = sorted((directory / "attempts" / row["row_id"]).glob("*.json"))
        for path in paths:
            record = read_json(path)
            if record["plan_hash"] != plan["plan_hash"] or record["row_id"] != row["row_id"]:
                raise ValueError("attempt does not belong to frozen plan")
            attempts.append(record)
        first[row["row_id"]] = read_json(paths[0]) if paths else None

    def outcome(row: dict) -> float | None:
        record = first[row["row_id"]]
        if record and record["status"] == "finished":
            value = record["pws"]
            if not isinstance(value, (float, int)) or not 0 <= value <= 1:
                raise ValueError("invalid PWS")
            return value
        return None

    cells = defaultdict(dict)
    for row in plan["rows"]:
        cells[(row["game"], row["scenario_id"])][(row["model"], row["harness"], row["condition"])] = outcome(row)
    rng = random.Random(plan["manifest"]["schedule"]["order_seed"])
    contrasts = []
    models = [m["model"] for m in plan["manifest"]["models"]]
    for game in plan["manifest"]["games"]:
        blocks = [v for (g, _), v in cells.items() if g == game]
        # Form a within-scenario contrast before resampling; interaction keeps
        # all four model-harness outcomes together. Games are never pooled.
        definitions = []
        for condition in plan["manifest"]["conditions"]:
            definitions.extend((model, condition, "Qwen Code minus OpenCode",
                                {(model, "qwen", condition): 1, (model, "opencode", condition): -1}) for model in models)
            for a, b in itertools.combinations(models, 2):
                definitions.append((f"{a} minus {b}", condition, "difference in harness gains",
                                    {(a, "qwen", condition): 1, (a, "opencode", condition): -1,
                                     (b, "qwen", condition): -1, (b, "opencode", condition): 1}))
        if plan["checkpoints"]:
            for model in models:
                for harness in HARNESSES:
                    definitions.append((f"{model}/{harness}", "history_intervention", "seat_history minus current_only",
                                        {(model, harness, "seat_history"): 1, (model, harness, "current_only"): -1}))
                definitions.append((model, "history_interaction", "change in Qwen Code minus OpenCode gap after history supplementation",
                                    {(model, "qwen", "seat_history"): 1, (model, "opencode", "seat_history"): -1,
                                     (model, "qwen", "current_only"): -1, (model, "opencode", "current_only"): 1}))
        for name, condition, direction, weights in definitions:
            complete = [sum(block[k] * w for k, w in weights.items()) for block in blocks if all(block[k] is not None for k in weights)]
            lower = [sum(w * block[k] if block[k] is not None else min(0, w) for k, w in weights.items()) for block in blocks]
            upper = [sum(w * block[k] if block[k] is not None else max(0, w) for k, w in weights.items()) for block in blocks]
            contrasts.append({"game": game, "condition": condition, "contrast": name,
                              "direction": direction, "scheduled_blocks": len(blocks),
                              "complete_first_attempt_blocks": len(complete),
                              "complete_case_mean_pp": 100 * statistics.fmean(complete) if complete else None,
                              "ci95_pp": _interval([100 * x for x in complete], rng, draws) if len(complete) == len(blocks) else None,
                              "missing_outcome_bounds_pp": [100 * statistics.fmean(lower), 100 * statistics.fmean(upper)]})
    return {"schema_version": "agentbga.rq2-summary.v1", "plan_hash": plan["plan_hash"],
            "smoke": any(r["smoke"] for r in attempts), "scheduled": len(plan["rows"]),
            "attempts": len(attempts), "finished_first_attempt": sum(bool(r and r["status"] == "finished") for r in first.values()),
            "not_started": sum(r is None for r in first.values()), "contrasts": contrasts,
            "inference": "Per-game pointwise scenario-bootstrap intervals only for fully observed first-attempt blocks; exploratory, unadjusted for multiplicity. Bounds are not confidence intervals. Smoke results are not model evidence.",
            "recovery_policy": "Later attempts remain separate and never replace first-attempt outcomes in the primary analysis."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan_parser = commands.add_parser("plan", help="freeze a manifest, randomized schedule and checkpoints; no model calls")
    plan_parser.add_argument("manifest", type=Path)
    plan_parser.add_argument("--out", type=Path, required=True)
    run_parser = commands.add_parser("run", help="execute bounded scheduled work; rerunning skips completed rows")
    run_parser.add_argument("directory", type=Path)
    run_parser.add_argument("--max-matches", type=int, required=True)
    run_parser.add_argument("--smoke", action="store_true", help="replace every controller with random; no model evidence")
    run_parser.add_argument("--retry-failed", action="store_true", help="record a fresh attempt, preserving the failed/interrupted first attempt")
    analysis_parser = commands.add_parser("analyze")
    analysis_parser.add_argument("directory", type=Path)
    analysis_parser.add_argument("--bootstrap-draws", type=int, default=5000)
    checkpoint_parser = commands.add_parser("checkpoint", help="export a verified private action prefix at a decision boundary")
    checkpoint_parser.add_argument("--db", type=Path, required=True)
    checkpoint_parser.add_argument("--match-id", required=True)
    position = checkpoint_parser.add_mutually_exclusive_group(required=True)
    position.add_argument("--version", type=int)
    position.add_argument("--decision-index", type=int, help="1-based focal decision index selected without looking at outcomes")
    checkpoint_parser.add_argument("--focal-seat", type=int, required=True)
    checkpoint_parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            plan = make_plan(read_json(args.manifest), args.manifest.resolve().parent)
            if args.out.exists() and any(args.out.iterdir()):
                raise ValueError("output directory is not empty; frozen plans cannot be overwritten")
            args.out.mkdir(parents=True, exist_ok=True)
            write_json(args.out / "plan.json", plan)
            result = {"scheduled": len(plan["rows"]), "plan_hash": plan["plan_hash"], "stage": plan["manifest"]["stage"]}
        elif args.command == "run":
            result = run_study(args.directory.resolve(), max_matches=args.max_matches, smoke=args.smoke, retry_failed=args.retry_failed)
        elif args.command == "analyze":
            result = analyze(args.directory, args.bootstrap_draws)
            write_json(args.directory / "summary.json", result)
        else:
            if args.out.exists():
                raise ValueError("checkpoint output already exists")
            checkpoint = export_checkpoint(args.db, args.match_id, args.version, args.focal_seat, args.decision_index)
            write_json(args.out, checkpoint)
            result = {"checkpoint_hash": digest(checkpoint), "version": checkpoint["version"]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, OSError) as error:
        print(f"RQ2: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
