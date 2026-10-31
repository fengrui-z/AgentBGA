#!/usr/bin/env python3
"""Run complete, replay-verified algorithm matches without model credentials."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agentbga.agents import PlayerConfig
from agentbga.baselines.config import BASELINE_BACKENDS
from agentbga.registry import get_game, game_ids
from agentbga.runner import run_match
from agentbga.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backends",
        nargs="+",
        choices=sorted(BASELINE_BACKENDS),
        default=sorted(BASELINE_BACKENDS),
    )
    parser.add_argument(
        "--games", nargs="+", choices=game_ids(), default=list(game_ids())
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[42])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--params",
        type=json.loads,
        default={},
        help="JSON parameter overrides, shared by selected backends",
    )
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--opponent", choices=["self", "random"], default="self")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    # A fresh directory prevents accidental replacement of earlier evidence.
    if (args.out / "validation.json").exists():
        parser.error("--out already contains validation.json; use a fresh directory")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], text=True
    ).strip()
    report = {
        "schema_version": "agentbga.baseline-validation.v1",
        "revision": revision,
        "matches": [],
    }
    for backend in args.backends:
        for name in args.games:
            game = get_game(name)
            count = max(2, game.describe()["players"]["minimum"])
            for seed in args.seeds:
                # Against random, cover every seat. Self-play already exercises all seats.
                for baseline_seat in (
                    range(count) if args.opponent == "random" else [None]
                ):
                    ordinal = len(report["matches"]) + 1
                    database = args.out / f"match-{ordinal:04d}.sqlite3"
                    store = Store(database)
                    started = time.monotonic()
                    row = {
                        "game": name,
                        "rules_version": game.rules_version,
                        "backend": backend,
                        "seed": seed,
                        "players": count,
                        "baseline_seat": baseline_seat,
                        "opponent": args.opponent,
                        "database": database.name,
                    }
                    try:
                        configs = []
                        for seat in range(count):
                            selected = (
                                backend
                                if baseline_seat is None or baseline_seat == seat
                                else "random"
                            )
                            config = {"name": f"{selected}-{seat}", "backend": selected}
                            if selected != "random":
                                config["algorithm_params"] = args.params
                            configs.append(PlayerConfig.from_dict(config, seat))
                        match_id, _, _ = store.create(count, seed, name)
                        result = run_match(
                            store,
                            match_id,
                            configs,
                            max_turns=args.max_turns,
                            retries=0,
                            fallback="fail",
                        )
                        frames = store.replay(match_id)
                        row.update(
                            status="ok",
                            match_id=match_id,
                            turns=result["turns"],
                            decisions=result["decisions"],
                            rankings=result["rankings"],
                            baseline_metrics=result["baseline_metrics"],
                            replay_verified=True,
                            final_state_hash=frames[-1]["state_hash"],
                        )
                    except Exception as error:
                        row.update(
                            status="error", error=f"{type(error).__name__}: {error}"
                        )
                    finally:
                        store.close()
                    row["seconds"] = round(time.monotonic() - started, 3)
                    report["matches"].append(row)
                    temporary = args.out / "validation.json.tmp"
                    temporary.write_text(json.dumps(report, indent=2) + "\n")
                    temporary.replace(args.out / "validation.json")
                    print(json.dumps(row), flush=True)
    return int(any(row["status"] != "ok" for row in report["matches"]))


if __name__ == "__main__":
    raise SystemExit(main())
