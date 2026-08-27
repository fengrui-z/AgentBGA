#!/usr/bin/env python3
"""Create the public Frontier12 data file consumed by the GitHub Pages UI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_public_data(source: Path) -> dict[str, Any]:
    summary = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    config = json.loads((source / "config.json").read_text(encoding="utf-8"))
    participants = {item["id"]: item["player"] for item in config.get("participants", [])}

    leaderboard = []
    for row in summary.get("leaderboard", []):
        player = participants.get(row["participant_id"], {})
        leaderboard.append(
            {
                **row,
                "display_name": player.get("name", row["participant_id"]),
                "backend": player.get("backend", "unknown"),
                "model": player.get("model", "unknown"),
            }
        )

    schedule = summary.get("schedule", {})
    return {
        "schema_version": "agentbga.frontier12-pages.v1",
        "dataset_id": source.name,
        "tournament_id": summary.get("tournament_id")
        or schedule.get("tournament_id")
        or config.get("tournament_id"),
        "generated_at": summary.get("generated_at"),
        "results": summary.get("results", {}),
        "rating": summary.get("rating", {}),
        "schedule": {
            key: schedule.get(key)
            for key in (
                "appearances_per_condition",
                "matches",
                "pair_exposures",
                "participant_exposures",
                "participants",
                "seat_exposures_per_stratum",
                "strata",
            )
        },
        "leaderboard": leaderboard,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Frontier12 result directory")
    parser.add_argument("output", type=Path, help="Public JSON destination")
    args = parser.parse_args()

    public_data = build_public_data(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
    temporary.write_text(
        json.dumps(public_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
