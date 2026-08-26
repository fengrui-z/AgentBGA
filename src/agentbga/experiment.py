"""Experiment manifests, balanced schedules, and standard result artifacts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import secrets
from typing import Any

from .agents import HARNESS_BACKENDS, PlayerConfig
from .registry import game_ids, get_game
from .runner import run_match
from .store import Store


EXPERIMENT_SCHEMA = "agentbga.experiment.v1"
RESULTS_SCHEMA = "agentbga.results.v1"
MODES = frozenset({"duel", "tournament", "series"})
SQLITE_INTEGER_MIN = -(2**63)
SQLITE_INTEGER_MAX = 2**63 - 1


@dataclass(frozen=True)
class Competitor:
    id: str
    player: dict[str, Any]
    memory_scope: str


@dataclass(frozen=True)
class ScheduledMatch:
    ordinal: int
    game: str
    seed: int
    competitors: tuple[Competitor, ...]
    rules_version: str
    series_id: str | None = None
    series_replicate: int | None = None
    series_game_index: int | None = None
    base_seed: int | None = None


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{label} must be a non-empty string of at most 128 characters")
    if not all(character.isalnum() or character in "._:-" for character in value):
        raise ValueError(f"{label} may contain only letters, digits, '.', '_', ':', and '-'")
    return value


def load_experiment(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_experiment(value)
    return value


def validate_experiment(value: Any) -> None:
    if not isinstance(value, dict) or value.get("schema_version") != EXPERIMENT_SCHEMA:
        raise ValueError(f"experiment config must use schema_version {EXPERIMENT_SCHEMA}")
    _identifier(value.get("experiment_id"), "experiment_id")
    mode = value.get("mode")
    if mode not in MODES:
        raise ValueError(f"experiment mode must be one of: {', '.join(sorted(MODES))}")
    raw_competitors = value.get("competitors")
    if not isinstance(raw_competitors, list) or len(raw_competitors) < 2:
        raise ValueError("experiment requires at least two competitors")
    competitors = _competitors(value)
    if mode in {"duel", "series"} and len(competitors) != 2:
        raise ValueError(f"{mode} requires exactly two competitors")
    if mode != "series" and any(item.memory_scope != "match" for item in competitors):
        raise ValueError(f"{mode} competitors must use match-scoped memory")
    if mode == "series" and not any(item.memory_scope == "series" for item in competitors):
        raise ValueError("series requires at least one competitor with series-scoped memory")
    schedule_experiment(value)
    results = value.get("results", {})
    if not isinstance(results, dict):
        raise ValueError("results must be an object")
    emit_every = results.get("emit_every", 1)
    if not isinstance(emit_every, int) or emit_every < 1:
        raise ValueError("results.emit_every must be a positive integer")
    token_env = results.get("submission_token_env")
    if token_env is not None and (
        not isinstance(token_env, str) or not token_env or not token_env.replace("_", "A").isalnum()
    ):
        raise ValueError("results.submission_token_env must be an environment variable name")


def _competitors(value: dict[str, Any]) -> list[Competitor]:
    result: list[Competitor] = []
    seen: set[str] = set()
    for index, raw in enumerate(value.get("competitors", [])):
        if not isinstance(raw, dict):
            raise ValueError(f"competitor {index} must be an object")
        competitor_id = _identifier(raw.get("id"), f"competitor {index} id")
        if competitor_id in seen:
            raise ValueError(f"duplicate competitor id: {competitor_id}")
        seen.add(competitor_id)
        player = raw.get("player")
        if not isinstance(player, dict):
            raise ValueError(f"competitor {competitor_id} requires a player object")
        memory = raw.get("memory", {})
        if not isinstance(memory, dict):
            raise ValueError(f"competitor {competitor_id} memory must be an object")
        scope = memory.get("scope", "match")
        if scope not in {"match", "series"}:
            raise ValueError(f"competitor {competitor_id} memory.scope must be match or series")
        # Validate the underlying player independently from its scheduled seat.
        probe = dict(player)
        if str(probe.get("backend", "")).lower() in HARNESS_BACKENDS:
            probe["participant_id"] = competitor_id
        PlayerConfig.from_dict(probe, index)
        if scope == "series" and str(player.get("backend", "")).lower() not in HARNESS_BACKENDS:
            raise ValueError(f"competitor {competitor_id} needs a harness backend for series memory")
        result.append(Competitor(competitor_id, dict(player), scope))
    return result


def _games(value: dict[str, Any]) -> list[str]:
    raw = value.get("games")
    if raw is None and value.get("game") is not None:
        raw = [value["game"]]
    if not isinstance(raw, list) or not raw:
        raise ValueError("experiment requires a non-empty games array")
    games = [str(game) for game in raw]
    unknown = set(games) - set(game_ids())
    if unknown:
        raise ValueError(f"unknown games: {', '.join(sorted(unknown))}")
    return games


def _seeds(schedule: dict[str, Any], default_count: int = 5) -> list[int]:
    raw = schedule.get("seeds")
    if raw is None:
        raw = list(range(1, default_count + 1))
    if not isinstance(raw, list) or not raw or any(
        not isinstance(seed, int) or isinstance(seed, bool) for seed in raw
    ):
        raise ValueError("schedule.seeds must be a non-empty integer array")
    if len(set(raw)) != len(raw):
        raise ValueError("schedule.seeds must not contain duplicates")
    if any(seed < SQLITE_INTEGER_MIN or seed > SQLITE_INTEGER_MAX for seed in raw):
        raise ValueError("schedule.seeds must fit SQLite signed 64-bit integers")
    return raw


def _rules_versions(value: dict[str, Any], games: list[str]) -> dict[str, str]:
    raw = value.get("rules_versions", {})
    if not isinstance(raw, dict):
        raise ValueError("rules_versions must be an object keyed by game ID")
    extra = set(raw) - set(games)
    if extra:
        raise ValueError(f"rules_versions contains games not in the schedule: {', '.join(sorted(extra))}")
    selected: dict[str, str] = {}
    for game_id in games:
        requested = raw.get(game_id)
        if requested is not None and (not isinstance(requested, str) or not requested):
            raise ValueError(f"rules_versions.{game_id} must be a non-empty string")
        selected[game_id] = get_game(game_id, requested).rules_version
    return selected


def _validate_player_count(game_id: str, player_count: int, rules_version: str) -> None:
    description = get_game(game_id, rules_version).describe()
    minimum = int(description.get("min_players", 2))
    maximum = min(4, int(description.get("max_players", 4)))
    if not minimum <= player_count <= maximum:
        raise ValueError(
            f"game {game_id} does not support configured player count {player_count}"
        )


def schedule_experiment(value: dict[str, Any]) -> list[ScheduledMatch]:
    mode = value.get("mode")
    competitors = _competitors(value)
    games = _games(value)
    rules_versions = _rules_versions(value, games)
    schedule = value.get("schedule", {})
    if not isinstance(schedule, dict):
        raise ValueError("schedule must be an object")
    matches: list[ScheduledMatch] = []

    def append(game: str, seed: int, seats: tuple[Competitor, ...], **series: Any) -> None:
        rules_version = rules_versions[game]
        _validate_player_count(game, len(seats), rules_version)
        matches.append(ScheduledMatch(
            len(matches) + 1, game, seed, seats, rules_version, **series,
        ))

    if mode == "duel":
        for game in games:
            for seed in _seeds(schedule):
                append(game, seed, tuple(competitors))
                append(game, seed, tuple(reversed(competitors)))
    elif mode == "tournament":
        raw_counts = schedule.get("player_counts", [2])
        if not isinstance(raw_counts, list) or not raw_counts:
            raise ValueError("schedule.player_counts must be a non-empty array")
        counts = [int(count) for count in raw_counts]
        if any(count not in {2, 3, 4} or count > len(competitors) for count in counts):
            raise ValueError("tournament player counts must be 2, 3, or 4 and fit the field")
        for game in games:
            for count in counts:
                _validate_player_count(game, count, rules_versions[game])
                for group in itertools.combinations(competitors, count):
                    for seed in _seeds(schedule):
                        for rotation in range(count):
                            seats = group[rotation:] + group[:rotation]
                            append(game, seed, seats)
    elif mode == "series":
        series = value.get("series", {})
        if not isinstance(series, dict):
            raise ValueError("series must be an object")
        length = series.get("length", 20)
        replicates = series.get("replicates", 1)
        if not isinstance(length, int) or length < 1:
            raise ValueError("series.length must be a positive integer")
        if not isinstance(replicates, int) or replicates < 1:
            raise ValueError("series.replicates must be a positive integer")
        base_seeds = _seeds(schedule, length)
        if len(base_seeds) < length:
            raise ValueError("series schedule needs at least series.length seeds")
        selected_seeds = base_seeds[:length]
        seed_stride = max(selected_seeds) - min(selected_seeds) + 1
        experiment_id = value["experiment_id"]
        for game in games:
            for replicate in range(1, replicates + 1):
                series_id = f"{experiment_id}:{game}:r{replicate}"
                for index in range(length):
                    reverse_order = (index + replicate - 1) % 2 == 1
                    seats = tuple(reversed(competitors)) if reverse_order else tuple(competitors)
                    # Use disjoint numeric intervals derived from the complete
                    # input range. Unlike a fixed offset, this is collision-free
                    # for every accepted set of unique signed integer seeds.
                    base_seed = selected_seeds[index]
                    seed = base_seed + (replicate - 1) * seed_stride
                    if seed < SQLITE_INTEGER_MIN or seed > SQLITE_INTEGER_MAX:
                        raise ValueError("series replicate seeds exceed SQLite signed 64-bit range")
                    append(
                        game, seed, seats, series_id=series_id,
                        series_replicate=replicate, series_game_index=index + 1,
                        base_seed=base_seed,
                    )
    else:
        raise ValueError(f"unsupported experiment mode: {mode}")
    return matches


def _player_for_match(
    competitor: Competitor, series_id: str | None, memory_namespace: str | None = None,
) -> PlayerConfig:
    value = dict(competitor.player)
    backend = str(value.get("backend", "")).lower()
    if backend in HARNESS_BACKENDS:
        value["participant_id"] = competitor.id
        if competitor.memory_scope == "series":
            value["series_id"] = series_id
        else:
            value.pop("series_id", None)
    config = PlayerConfig.from_dict(value, 0)
    if competitor.memory_scope == "series" and memory_namespace:
        config = replace(config, memory_namespace=memory_namespace)
    return config


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _artifact_digest(document: dict[str, Any]) -> str:
    content = {key: value for key, value in document.items() if key not in {"integrity", "submission"}}
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _write_atomic(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _results_document(
    manifest: dict[str, Any], run_id: str, matches: list[dict[str, Any]],
    scheduled_count: int, submission_token: str | None,
) -> dict[str, Any]:
    completed = sum(row["status"] == "ok" for row in matches)
    document: dict[str, Any] = {
        "schema_version": RESULTS_SCHEMA,
        "experiment_id": manifest["experiment_id"],
        "run_id": run_id,
        "mode": manifest["mode"],
        "generated_at": _utc_now(),
        "complete": len(matches) == scheduled_count,
        "summary": {
            "scheduled_matches": scheduled_count,
            "reported_matches": len(matches),
            "completed_matches": completed,
            "failed_matches": len(matches) - completed,
        },
        "matches": matches,
    }
    if submission_token:
        document["submission"] = {"token": submission_token}
    document["integrity"] = {
        "algorithm": "sha256",
        "content_digest": _artifact_digest(document),
    }
    return document


def run_experiment(
    manifest: dict[str, Any], output_dir: str | Path, *,
    max_turns: int | None = None, retries: int = 1, fallback: str = "fail",
) -> dict[str, Any]:
    validate_experiment(manifest)
    schedule = schedule_experiment(manifest)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
    result_config = manifest.get("results", {})
    emit_every = int(result_config.get("emit_every", 1))
    token_env = result_config.get("submission_token_env")
    submission_token = os.environ.get(token_env) if token_env else None
    if token_env and not submission_token:
        raise ValueError(f"missing submission token environment variable: {token_env}")
    rows: list[dict[str, Any]] = []
    matches_dir = output / "matches"
    matches_dir.mkdir(exist_ok=True)
    public_manifest = json.loads(json.dumps(manifest))
    if isinstance(public_manifest.get("results"), dict):
        public_manifest["results"].pop("submission_token", None)
    _write_atomic(output / "experiment.json", public_manifest)

    for scheduled in schedule:
        database = matches_dir / f"match-{scheduled.ordinal:06d}.sqlite3"
        store = Store(str(database))
        participants = []
        try:
            players = []
            for seat, competitor in enumerate(scheduled.competitors):
                player = _player_for_match(competitor, scheduled.series_id, run_id)
                players.append(player)
                participants.append({
                    "participant_id": competitor.id,
                    "seat": seat,
                    "memory_scope": competitor.memory_scope,
                    "player": player.public_dict(),
                })
            match_id, _, _ = store.create(
                len(players), scheduled.seed, scheduled.game,
                manifest.get("game_config"),
                rules_version=scheduled.rules_version,
            )
            result = run_match(
                store, match_id, players, max_turns=max_turns,
                retries=retries, fallback=fallback,
            )
            row = {
                "result_id": hashlib.sha256(
                    f"{run_id}:{scheduled.ordinal}".encode("utf-8")
                ).hexdigest(),
                "ordinal": scheduled.ordinal,
                "status": "ok",
                "game": scheduled.game,
                "rules_version": scheduled.rules_version,
                "seed": scheduled.seed,
                "player_count": len(players),
                "participants": participants,
                "series_id": scheduled.series_id,
                "series_replicate": scheduled.series_replicate,
                "series_game_index": scheduled.series_game_index,
                "base_seed": scheduled.base_seed,
                "result": result,
            }
        except Exception as error:
            row = {
                "result_id": hashlib.sha256(
                    f"{run_id}:{scheduled.ordinal}".encode("utf-8")
                ).hexdigest(),
                "ordinal": scheduled.ordinal,
                "status": "error",
                "game": scheduled.game,
                "rules_version": scheduled.rules_version,
                "seed": scheduled.seed,
                "player_count": len(scheduled.competitors),
                "participants": participants,
                "series_id": scheduled.series_id,
                "series_replicate": scheduled.series_replicate,
                "series_game_index": scheduled.series_game_index,
                "base_seed": scheduled.base_seed,
                "error": str(error),
            }
        finally:
            store.close()
        rows.append(row)
        if len(rows) % emit_every == 0:
            document = _results_document(
                manifest, run_id, rows, len(schedule), submission_token,
            )
            _write_atomic(output / "latest.json", document)
            _write_atomic(output / f"results-{len(rows):06d}.json", document)

    final = _results_document(manifest, run_id, rows, len(schedule), submission_token)
    _write_atomic(output / "latest.json", final)
    _write_atomic(output / "final.json", final)
    if len(rows) % emit_every:
        _write_atomic(output / f"results-{len(rows):06d}.json", final)
    return final
