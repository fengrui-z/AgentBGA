"""Deterministic small-scale random-baseline release matrix for Ark Nova."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Iterable

from .plugin import ArkNovaOfficialPlugin


BASELINE_SCHEMA_VERSION = "agentbga.ark_nova.release_baselines.v1"
DEFAULT_SEEDS = {1: 202608281, 2: 202608282, 3: 202608283, 4: 202608284}


def run_random_baseline(
    players: int, seed: int, *, maximum_turns: int = 1000,
) -> dict[str, Any]:
    plugin = ArkNovaOfficialPlugin()
    state = plugin.setup(players, seed)
    rng = random.Random(f"ark-nova-map0-release:{players}:{seed}")
    submitted = 0
    while state["status"] != "finished":
        turn_count = int(state["turn"].get("number", state.get("turn_count", 0)))
        if turn_count > maximum_turns:
            raise AssertionError(
                f"{players}P baseline exceeded {maximum_turns} turns at decision {submitted}"
            )
        seats = plugin.decision_seats(state)
        if not seats:
            raise AssertionError(
                f"{players}P baseline has no decision seat in phase {state['phase']}"
            )
        # Setup can expose multiple simultaneous seats. Apply one decision and
        # recompute the snapshot, matching the transactional runner protocol.
        seat = int(seats[0])
        actions = plugin.legal_actions(state, seat)
        if not actions:
            raise AssertionError(
                f"{players}P baseline has no legal action for seat {seat} in {state['phase']}"
            )
        selected = actions[rng.randrange(len(actions))]["action"]
        state, _ = plugin.apply_action(state, seat, selected)
        plugin.validate_state(state)
        submitted += 1
    result = {
        "players": players,
        "seed": seed,
        "turns": int(state["turn"].get("number", state.get("turn_count", 0))),
        "decisions": submitted,
        "state_hash": plugin.state_hash(state),
        "winner_seats": [
            row["seat"] for row in state["endgame"]["results"] if row["rank"] == 1
        ],
    }
    result["result_sha256"] = hashlib.sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return result


def run_release_baseline_matrix() -> dict[str, Any]:
    plugin = ArkNovaOfficialPlugin()
    results = [
        run_random_baseline(players, seed)
        for players, seed in DEFAULT_SEEDS.items()
    ]
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "rules_version": plugin.rules_version,
        "content_sha256": plugin.pack.content_sha256,
        "executed_on": "2026-08-28",
        "results": results,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Ark Nova Map 0 release baseline matrix")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = run_release_baseline_matrix()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
