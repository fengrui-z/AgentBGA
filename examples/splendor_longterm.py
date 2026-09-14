#!/usr/bin/env python3
"""Plan or run persistent-vs-fresh Splendor series. Planning never calls APIs."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentbga.longterm import run, schedule  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("schedule", "run"))
    parser.add_argument("--config", type=Path, default=ROOT / "examples" / "splendor-longterm.json")
    parser.add_argument("--stage", choices=("pilot", "main"), default="pilot")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit-matches", type=int, help="pause after this many additional acknowledged matches")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    plan = schedule(config, args.stage)
    if args.command == "schedule":
        result = {"stage": args.stage, "matches": len(plan),
                  "independent_series": len({r["series_id"] for r in plan}), "schedule": plan}
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("x") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
        print(json.dumps({k: v for k, v in result.items() if k != "schedule"}, indent=2))
    else:
        if args.out is None:
            parser.error("run requires --out")
        result = run(config, args.stage, args.out, resume=args.resume, limit_matches=args.limit_matches)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
