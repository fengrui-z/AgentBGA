#!/usr/bin/env python3
"""Validate and export a matched harness bridge; never calls a model API.

Exported commands use the existing AgentBGA CLI. A shared scenario is reused
across focal models, and each pair changes only the focal harness/identity.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentbga.agents import PlayerConfig  # noqa: E402
from agentbga.registry import get_game  # noqa: E402

SCHEMA = "agentbga.matched-harness-bridge.v1"
DEFAULT_CONFIG = ROOT / "examples" / "matched-bridge-72.json"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode()).hexdigest()


def identifier(value: Any) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 128
            and value[0].isalnum()
            and all(c.isalnum() or c in "._-" for c in value))


def focal_player(model: dict, arm: dict) -> dict:
    return {
        **model["player"], "backend": arm["backend"],
        "name": f"{model['name']} · {arm['name']}",
        "participant_id": f"{model['id']}-{arm['backend']}",
    }


def validate(config: dict) -> None:
    if config.get("schema_version") != SCHEMA:
        raise ValueError(f"schema_version must be {SCHEMA}")
    if not identifier(config.get("experiment_id")):
        raise ValueError("invalid experiment_id")
    schedule = config["schedule"]
    if schedule["player_count"] != 3:
        raise ValueError("this bridge requires three players")
    blocks = schedule["paired_blocks_per_model_game"]
    if type(blocks) is not int or blocks < 3 or blocks % 3:
        raise ValueError("paired blocks must be a positive multiple of three")
    for field in ("base_seed", "order_seed"):
        if type(schedule[field]) is not int:
            raise ValueError(f"{field} must be an integer")
    anchors = config["anchors"]
    if len(anchors) != 2 or len({a["id"] for a in anchors}) != 2:
        raise ValueError("exactly two distinct anchors are required")
    for anchor in anchors:
        if not identifier(anchor["id"]):
            raise ValueError("invalid anchor id")
        PlayerConfig.from_dict({**anchor["player"], "participant_id": anchor["id"]}, 0)
    models = config["models"]
    if not models or len({m["id"] for m in models}) != len(models):
        raise ValueError("focal models must have unique ids")
    for model in models:
        if not identifier(model["id"]):
            raise ValueError("invalid model id")
        shared = model["player"]
        if not {"model", "base_url", "api_key_env", "reasoning_effort"} <= shared.keys():
            raise ValueError("freeze model, endpoint, credential variable and effort")
        if {"backend", "name", "participant_id", "series_id"} & shared.keys():
            raise ValueError("model player must contain only shared, match-scoped settings")
        arms = model["arms"]
        if len(arms) != 2 or len({a["id"] for a in arms}) != 2:
            raise ValueError("each model requires two distinct arms")
        if len({a["backend"] for a in arms}) != 2:
            raise ValueError("arms must use different harnesses")
        for arm in arms:
            if set(arm) != {"id", "name", "backend"} or not identifier(arm["id"]):
                raise ValueError("arms may change only harness and display identity")
            PlayerConfig.from_dict(focal_player(model, arm), 0)
    participants = [a["id"] for a in anchors] + [
        focal_player(m, a)["participant_id"] for m in models for a in m["arms"]
    ]
    if len(participants) != len(set(participants)):
        raise ValueError("anchor and focal participant ids must be disjoint")
    for player in [a["player"] for a in anchors]:
        if "series_id" in player:
            raise ValueError("cross-match anchor memory is not allowed")
    games = schedule["games"]
    if not games or len({g["id"] for g in games}) != len(games):
        raise ValueError("games must be nonempty and unique")
    for game in games:
        if not isinstance(game.get("rules_version"), str) or not game["rules_version"]:
            raise ValueError("each game must pin a rules_version")
        engine = get_game(game["id"], game["rules_version"])
        info = engine.describe()
        if not info.get("min_players", 2) <= 3 <= info.get("max_players", 4):
            raise ValueError(f"{game['id']} does not support three players")
    run = config["run"]
    if run != {"retries": 0, "fallback": "fail"}:
        raise ValueError("bridge requires retries=0 and fallback=fail")
    total = len(models) * len(games) * blocks * 2
    if config["expected_matches"] != total:
        raise ValueError(f"expected_matches differs from computed size {total}")


def build_schedule(config: dict) -> list[dict]:
    validate(config)
    spec = config["schedule"]
    rng = random.Random(spec["order_seed"])
    count = spec["paired_blocks_per_model_game"]
    pairs = []
    # Balance run order 4/5 (or exactly for even counts) independently per cell.
    first_arms = {}
    for game in spec["games"]:
        for mi, model in enumerate(config["models"]):
            orders = [(b + mi) % 2 for b in range(count)]
            rng.shuffle(orders)
            first_arms[(game["id"], model["id"])] = orders
    for gi, game in enumerate(spec["games"]):
        for block in range(count):
            seat = block % 3
            scenario_id = f"{game['id']}-3p-b{block + 1:02d}"
            seed = spec["base_seed"] + gi * count + block
            if not -(2**63) <= seed < 2**63:
                raise ValueError("generated seed must fit signed 64-bit SQLite integer")
            # Swap clockwise anchor order each full seat cycle. With nine
            # blocks each seat has a 2:1 orientation split, identical for models.
            anchors = list(config["anchors"])
            if (block // 3) % 2:
                anchors.reverse()
            for model in config["models"]:
                first = first_arms[(game["id"], model["id"])][block]
                pair = []
                for arm_index in (first, 1 - first):
                    arm = model["arms"][arm_index]
                    players = [None] * 3
                    players[seat] = focal_player(model, arm)
                    for offset, anchor in enumerate(anchors, 1):
                        players[(seat + offset) % 3] = {
                            **anchor["player"], "participant_id": anchor["id"],
                        }
                    pair.append({
                        "scenario_id": scenario_id,
                        "pair_id": f"{model['id']}-{scenario_id}",
                        "model_id": model["id"], "arm": arm["id"],
                        "contrast_sign": -1 if arm_index == 0 else 1,
                        "game": game["id"], "rules_version": game["rules_version"],
                        "player_count": 3, "seed": seed, "focal_seat": seat,
                        "players": players, "run": dict(config["run"]),
                    })
                pairs.append(pair)
    rng.shuffle(pairs)
    matches = [m for pair in pairs for m in pair]
    for ordinal, match in enumerate(matches, 1):
        match["ordinal"] = ordinal
        match["config_sha256"] = digest(config)
    return matches


def report(config: dict, schedule: list[dict]) -> dict:
    cells = defaultdict(lambda: {"matches": 0, "paired_blocks": 0,
                                 "focal_blocks_by_seat": Counter(),
                                 "first_arm_counts": Counter()})
    for index in range(0, len(schedule), 2):
        a, b = schedule[index:index + 2]
        cell = cells[f"{a['model_id']}:{a['game']}:3p"]
        cell["matches"] += 2
        cell["paired_blocks"] += 1
        cell["focal_blocks_by_seat"][a["focal_seat"]] += 1
        cell["first_arm_counts"][a["arm"]] += 1
        assert a["pair_id"] == b["pair_id"]
    return {"experiment_id": config["experiment_id"], "matches": len(schedule),
            "paired_blocks": len(schedule) // 2,
            "shared_scenarios": len({m["scenario_id"] for m in schedule}),
            "config_sha256": digest(config), "schedule_sha256": digest(schedule),
            "cells": dict(cells)}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def export(config: dict, schedule: list[dict], out: Path) -> None:
    out = out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("export directory must be empty; preserve previous plans")
    out.mkdir(parents=True, exist_ok=True)
    for directory in ("players", "matches", "results"):
        (out / directory).mkdir()
    write_json(out / "config.json", config)
    write_json(out / "schedule.json", schedule)
    write_json(out / "summary.json", report(config, schedule))
    with (out / "schedule.csv").open("w", newline="") as handle:
        fields = ["ordinal", "scenario_id", "pair_id", "model_id", "arm", "game",
                  "seed", "focal_seat", "seat_0", "seat_1", "seat_2"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for match in schedule:
            row = {field: match[field] for field in fields if field in match}
            row.update({f"seat_{seat}": p["participant_id"]
                        for seat, p in enumerate(match["players"])})
            writer.writerow(row)
    commands = []
    for match in schedule:
        key = f"match-{match['ordinal']:03d}"
        players_path = out / "players" / f"{key}.json"
        write_json(players_path, {"schema_version": "agentbga.players.v1",
                                  "players": match["players"]})
        commands.append({
            "ordinal": match["ordinal"], "pair_id": match["pair_id"],
            "arm": match["arm"], "cwd": str(ROOT),
            "argv": [sys.executable, "-m", "agentbga", "run",
                     "--game", match["game"], "--rules-version", match["rules_version"],
                     "--players", "3", "--seed", str(match["seed"]),
                     "--players-config", str(players_path), "--retries", "0",
                     "--fallback", "fail", "--db", str(out / "matches" / f"{key}.sqlite3")],
            "env": {"PYTHONPATH": str(ROOT / "src")},
            "stdout_path": str(out / "results" / f"{key}.json"),
            "stderr_path": str(out / "results" / f"{key}.stderr.txt"),
        })
    write_json(out / "commands.json", commands)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, help="export plan and per-match CLI inputs")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    schedule = build_schedule(config)
    if args.out:
        export(config, schedule, args.out)
    print(json.dumps(report(config, schedule), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
