"""Machine-readable command-line interface for AgentBGA."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from . import __version__
from .agents import AgentError, HARNESS_BACKENDS, load_players_config
from .game import GameRuleError
from .experiment import load_experiment, run_experiment, schedule_experiment
from .registry import game_ids, get_game, list_games
from .runner import run_match
from .store import ConflictError, MatchNotFound, Store

SCHEMA = "agentbga.cli.v1"


def _codex_subscription_status(executable: str) -> tuple[bool, str]:
    """Check the same local ChatGPT login that a subscription seat will reuse."""
    with tempfile.TemporaryDirectory(prefix="agentbga-codex-auth-") as directory:
        isolated_home = Path(directory)
        source_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        source_auth = source_home / "auth.json"
        if source_auth.is_file():
            (isolated_home / "auth.json").symlink_to(source_auth)
        environment = dict(os.environ)
        environment["CODEX_HOME"] = directory
        environment.pop("OPENAI_API_KEY", None)
        environment.pop("OPENAI_BASE_URL", None)
        try:
            result = subprocess.run(
                [executable, "login", "status"], capture_output=True, text=True,
                timeout=10, check=False, env=environment,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"login status check failed: {exc}"
    raw_detail = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    lines = [line.strip() for line in raw_detail.splitlines() if line.strip()]
    detail = next(
        (line for line in reversed(lines) if "logged in" in line.lower()),
        lines[-1] if lines else "login status unavailable",
    )
    return result.returncode == 0 and "chatgpt" in detail.lower(), detail


def envelope(data: Any, **extra: Any) -> dict[str, Any]:
    return {"schema_version": SCHEMA, **extra, "data": data}


def emit(value: Any, *, pretty: bool = False) -> None:
    print(json.dumps(value, indent=2 if pretty else None, ensure_ascii=False, sort_keys=pretty))


def error_payload(code: str, message: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA, "error": {"code": code, "message": message}}


def add_db(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", help="SQLite path (default: .agentbga/agentbga.sqlite3)")
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentbga", description="CLI-first board-game arena for LLM agents")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="group", required=True)

    games = commands.add_parser("games", help="discover games and schemas")
    games_sub = games.add_subparsers(dest="command", required=True)
    games_list = games_sub.add_parser("list")
    games_list.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    describe = games_sub.add_parser("describe")
    describe.add_argument("game", choices=game_ids())
    describe.add_argument("--rules-version", help="select an exact registered rules version")
    describe.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    match = commands.add_parser("match", help="create, inspect, and mutate matches")
    match_sub = match.add_subparsers(dest="command", required=True)
    create = match_sub.add_parser("create")
    create.add_argument("--game", default="splendor", choices=game_ids())
    create.add_argument("--rules-version", help="select an exact registered rules version")
    create.add_argument("--players", type=int, required=True, choices=range(2, 8))
    create.add_argument("--seed", type=int)
    create.add_argument("--game-config", help="game-specific JSON object, or @path/to/config.json")
    add_db(create)

    for name in ("observe", "legal-actions", "status", "verify", "replay", "harness-events"):
        item = match_sub.add_parser(name)
        item.add_argument("match_id")
        if name in ("observe", "legal-actions"):
            item.add_argument("--seat", type=int, required=True)
        add_db(item)

    traces = match_sub.add_parser("traces", help="list or export per-turn harness trace files")
    traces.add_argument("match_id")
    traces.add_argument("--seat", type=int)
    traces.add_argument("--turn", type=int, help="return the full trace for one seat+turn (requires --seat)")
    add_db(traces)

    act = match_sub.add_parser("act")
    act.add_argument("match_id")
    act.add_argument("--seat", type=int, required=True)
    act.add_argument("--expected-version", type=int, required=True)
    choice = act.add_mutually_exclusive_group(required=True)
    choice.add_argument("--action-id")
    choice.add_argument("--action", help="JSON action object, or @path/to/action.json")
    add_db(act)

    events = match_sub.add_parser("events")
    events.add_argument("match_id")
    events.add_argument("--after", type=int, default=-1)
    events.add_argument("--jsonl", action="store_true")
    add_db(events)

    run = commands.add_parser("run", help="create and run a complete match")
    run.add_argument("--game", choices=game_ids(), help="game for a new match (default: splendor)")
    run.add_argument("--rules-version", help="rules version for a new match")
    run.add_argument("--players", type=int, choices=range(2, 8))
    run.add_argument("--seed", type=int)
    run.add_argument("--match-id", help="resume an existing match instead of creating one")
    run.add_argument("--game-config", help="game-specific JSON object for a new match")
    run.add_argument(
        "--controllers",
        help="legacy comma-separated seats: random, openai, or human",
    )
    run.add_argument(
        "--players-config",
        help="JSON file with independently named/configured players (use - for stdin)",
    )
    run.add_argument("--model", help="model name for all openai seats")
    run.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    run.add_argument("--api-key-env", default="OPENAI_API_KEY")
    run.add_argument("--max-turns", type=int, default=None,
                     help="turn cap (default is selected by the game)")
    run.add_argument("--retries", type=int, default=1)
    run.add_argument("--fallback", choices=["random", "fail"], default="random")
    run.add_argument("--jsonl", action="store_true", help="stream every turn instead of only the result")
    add_db(run)

    experiment = commands.add_parser("experiment", help="validate or run reproducible experiment manifests")
    experiment_sub = experiment.add_subparsers(dest="command", required=True)
    experiment_validate = experiment_sub.add_parser("validate")
    experiment_validate.add_argument("--config", required=True)
    experiment_validate.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    experiment_run = experiment_sub.add_parser("run")
    experiment_run.add_argument("--config", required=True)
    experiment_run.add_argument("--out", required=True)
    experiment_run.add_argument("--max-turns", type=int)
    experiment_run.add_argument("--retries", type=int, default=1)
    experiment_run.add_argument("--fallback", choices=["random", "fail"], default="fail")
    experiment_run.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    doctor = commands.add_parser("doctor", help="check local and endpoint configuration")
    doctor.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    doctor.add_argument("--api-key-env", default="OPENAI_API_KEY")
    doctor.add_argument("--model")
    doctor.add_argument("--players-config", help="validate all players in a named multi-model config")
    add_db(doctor)

    web = commands.add_parser("web", help="run the local visual match table")
    web.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost", "::1"])
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--static-dir", help="built frontend directory (default: web/dist/client)")
    add_db(web)
    return parser


def _load_action(raw: str) -> dict[str, Any]:
    if raw.startswith("@"):
        raw = Path(raw[1:]).read_text()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("action must be a JSON object")
    return value


def execute(args: argparse.Namespace) -> int:
    if args.group == "experiment":
        manifest = load_experiment(args.config)
        if args.command == "validate":
            schedule = schedule_experiment(manifest)
            emit(envelope({
                "experiment_id": manifest["experiment_id"],
                "mode": manifest["mode"],
                "scheduled_matches": len(schedule),
            }))
        else:
            result = run_experiment(
                manifest, args.out, max_turns=args.max_turns,
                retries=args.retries, fallback=args.fallback,
            )
            emit(envelope({
                "experiment_id": result["experiment_id"],
                "run_id": result["run_id"],
                "summary": result["summary"],
                "results_file": str(Path(args.out) / "final.json"),
            }))
        return 0

    if args.group == "games":
        data = (list_games() if args.command == "list"
                else get_game(args.game, args.rules_version).describe())
        emit(envelope(data))
        return 0

    if args.group == "doctor":
        db = Path(args.db) if args.db else Path.cwd() / ".agentbga" / "agentbga.sqlite3"
        if args.players_config:
            players = load_players_config(args.players_config)
            player_checks = []
            for seat, player in enumerate(players):
                subscription_auth = player.backend == "codex" and player.auth_mode == "subscription"
                key_required = player.backend not in {"random", "human"} and not subscription_auth
                key_configured = not key_required or bool(os.environ.get(player.api_key_env or ""))
                harness_required = player.backend in HARNESS_BACKENDS
                # "minimal" runs in-process (no external binary needed)
                if player.backend == "minimal":
                    harness_executable = True
                    executable = None
                else:
                    executable = shutil.which(player.backend) if harness_required else None
                    harness_executable = not harness_required or bool(executable)
                auth_configured = key_configured
                auth_status = None
                if subscription_auth:
                    auth_configured, auth_status = (
                        _codex_subscription_status(executable) if executable
                        else (False, "codex executable not found")
                    )
                check = {
                    "seat": seat, **player.public_dict(),
                    "api_key_configured": None if subscription_auth else key_configured,
                    "authentication_configured": auth_configured,
                    "harness_executable": harness_executable,
                }
                if auth_status is not None:
                    check["authentication_status"] = auth_status
                player_checks.append(check)
            ready = sys.version_info >= (3, 11) and all(
                row["authentication_configured"] and row["harness_executable"]
                for row in player_checks
            )
            emit(envelope({
                "python": {"ok": sys.version_info >= (3, 11), "version": sys.version.split()[0]},
                "database": {"ok": True, "path": str(db)},
                "players": player_checks,
            }, ready_for_model=ready))
            return 0 if ready else 1
        checks = {
            "python": {"ok": sys.version_info >= (3, 11), "version": sys.version.split()[0]},
            "database": {"ok": True, "path": str(db)},
            "endpoint": {"configured": bool(args.base_url), "base_url": args.base_url},
            "api_key": {"configured": bool(os.environ.get(args.api_key_env)), "environment_variable": args.api_key_env},
            "model": {"configured": bool(args.model), "name": args.model},
        }
        ready = all(checks[name]["ok"] for name in ("python", "database")) and all(
            checks[name]["configured"] for name in ("endpoint", "api_key", "model")
        )
        emit(envelope(checks, ready_for_model=ready))
        return 0 if ready else 1

    if args.group == "web":
        from .web import serve
        serve(args.host, args.port, args.db, args.static_dir)
        return 0

    store = Store(args.db)
    try:
        if args.group == "match":
            if args.command == "create":
                seed = args.seed if args.seed is not None else secrets.randbits(63)
                game_config = _load_action(args.game_config) if args.game_config else None
                match_id, version, state = store.create(
                    args.players, seed, args.game, game_config,
                    rules_version=args.rules_version,
                )
                emit(envelope({
                    "match_id": match_id, "game": args.game, "rules_version": state["rules_version"],
                    "version": version, "seed": seed, "players": args.players,
                }))
            elif args.command in ("observe", "legal-actions", "status", "verify"):
                version, state, digest = store.load(args.match_id)
                game = store.game(args.match_id)
                if args.command == "observe":
                    data = game.observe(state, args.seat)
                    data["legal_actions"] = game.legal_actions(state, args.seat)
                elif args.command == "legal-actions":
                    data = game.legal_actions(state, args.seat)
                elif args.command == "status":
                    saved_players = store.players(args.match_id)
                    player_by_seat = {row["seat"]: row for row in saved_players}
                    ranked = [
                        {**row, **({"player": player_by_seat[row["seat"]]["name"],
                                   "backend": player_by_seat[row["seat"]]["backend"]}
                                  if row["seat"] in player_by_seat else {})}
                        for row in game.rankings(state)
                    ]
                    data = {
                        "game": game.game_id,
                        "status": state["status"], "turn_count": state["turn_count"],
                        "decision_count": state.get("decision_count", state["turn_count"]),
                        "active_seat": state["active_seat"], "phase": state["phase"],
                        "players": saved_players,
                        "rankings": ranked,
                    }
                else:
                    game.validate_state(state)
                    replay = store.replay(args.match_id)
                    computed = game.state_hash(state)
                    if computed != digest:
                        raise AssertionError("stored state hash does not match state")
                    data = {
                        "valid": True, "state_hash": digest,
                        "event_count": len(store.events(args.match_id)),
                        "replayed_versions": len(replay) - 1,
                    }
                emit(envelope(data, match_id=args.match_id, version=version))
            elif args.command == "replay":
                frames = store.replay(args.match_id)
                emit(envelope(frames, match_id=args.match_id, version=frames[-1]["version"]))
            elif args.command == "harness-events":
                version, _, _ = store.load(args.match_id)
                emit(envelope(store.harness_events(args.match_id), match_id=args.match_id, version=version))
            elif args.command == "traces":
                version, _, _ = store.load(args.match_id)
                root = Path.cwd() / ".agentbga" / "runs" / "_traces" / args.match_id
                if args.turn is not None:
                    if args.seat is None:
                        raise ValueError("--turn requires --seat")
                    target = root / f"seat-{args.seat}" / f"turn-{args.turn:04d}.json"
                    if not target.is_file():
                        raise FileNotFoundError(f"no trace file at {target}")
                    emit(json.loads(target.read_text(encoding="utf-8")))
                else:
                    entries = []
                    for seat_dir in sorted(root.glob("seat-*")) if root.is_dir() else []:
                        seat = int(seat_dir.name.split("-")[1])
                        if args.seat is not None and seat != args.seat:
                            continue
                        for trace_file in sorted(seat_dir.glob("turn-*.json")):
                            try:
                                trace = json.loads(trace_file.read_text(encoding="utf-8"))
                            except (json.JSONDecodeError, OSError):
                                continue
                            entries.append({
                                "seat": seat,
                                "version": trace.get("version"),
                                "status": trace.get("status"),
                                "action_id": (trace.get("submission") or {}).get("action_id"),
                                "latency_ms": trace.get("latency_ms"),
                                "action_latency_ms": trace.get("action_latency_ms"),
                                "process_latency_ms": trace.get("process_latency_ms", trace.get("latency_ms")),
                                "backend": trace.get("backend"),
                                "file": str(trace_file.relative_to(Path.cwd())),
                            })
                    emit(envelope(entries, match_id=args.match_id, version=version))
            elif args.command == "act":
                version, state, _ = store.load(args.match_id)
                game = store.game(args.match_id)
                if args.action_id:
                    item = next(
                        (item for item in game.legal_actions(state, args.seat) if item["id"] == args.action_id), None
                    )
                    if item is None:
                        raise GameRuleError("unknown or stale action ID")
                    action = item["action"]
                else:
                    action = _load_action(args.action)
                next_version, next_state, events = store.act(
                    args.match_id, args.seat, args.expected_version, action
                )
                if action.get("type") == "choose_initial_hand":
                    events = [
                        ({**event, "action": {"type": "choose_initial_hand", "kept_count": 4}}
                         if event.get("type") == "action_accepted" else event)
                        for event in events
                    ]
                emit(envelope({
                    "events": events, "status": next_state["status"],
                    "active_seat": next_state["active_seat"], "phase": next_state["phase"],
                }, match_id=args.match_id, version=next_version))
            elif args.command == "events":
                rows = store.events(args.match_id, args.after)
                if args.jsonl:
                    for row in rows:
                        emit({"schema_version": "agentbga.event.v1", "match_id": args.match_id, **row})
                else:
                    emit(envelope(rows, match_id=args.match_id))
            return 0

        if args.group == "run":
            if bool(args.players_config) == bool(args.controllers):
                raise ValueError("provide exactly one of --players-config or --controllers")
            if args.players_config:
                players_config = load_players_config(args.players_config)
            else:
                controllers = [part.strip() for part in args.controllers.split(",") if part.strip()]
                players_config = controllers
            if args.match_id:
                match_id = args.match_id
                _, state, _ = store.load(match_id)
                stored_game = store.game_id(match_id)
                if args.game is not None and args.game != stored_game:
                    raise ValueError("--game differs from resumed match")
                stored_rules_version = store.rules_version(match_id)
                if args.rules_version is not None and args.rules_version != stored_rules_version:
                    raise ValueError("--rules-version differs from resumed match")
                if args.players is not None and args.players != state["player_count"]:
                    raise ValueError("--players differs from resumed match")
            else:
                players = args.players if args.players is not None else len(players_config)
                if players != len(players_config):
                    raise ValueError("--players must equal the number of configured players")
                seed = args.seed if args.seed is not None else secrets.randbits(63)
                game_config = _load_action(args.game_config) if args.game_config else None
                match_id, _, _ = store.create(
                    players, seed, args.game or "splendor", game_config,
                    rules_version=args.rules_version,
                )
            sink = emit if args.jsonl else None
            result = run_match(
                store, match_id, players_config, model=args.model, base_url=args.base_url,
                api_key_env=args.api_key_env, max_turns=args.max_turns,
                retries=args.retries, fallback=args.fallback, sink=sink,
            )
            if not args.jsonl:
                emit(envelope(result))
            return 0
    finally:
        store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        return execute(parser.parse_args(argv))
    except MatchNotFound as error:
        emit(error_payload("match_not_found", str(error.args[0])))
        return 4
    except ConflictError as error:
        emit(error_payload("version_conflict", str(error)))
        return 5
    except GameRuleError as error:
        emit(error_payload("illegal_action", str(error)))
        return 6
    except AgentError as error:
        emit(error_payload("agent_error", str(error)))
        return 7
    except (ValueError, json.JSONDecodeError) as error:
        emit(error_payload("invalid_input", str(error)))
        return 2
    except (AssertionError, RuntimeError) as error:
        emit(error_payload("runtime_error", str(error)))
        return 8
