#!/usr/bin/env python3
"""Run N harness-vs-harness matches in parallel and aggregate results.

Usage: python3 batch-duel.py <players-config.json> <N> <parallel>
Reads DEEPSEEK_API_KEY from ~/.dsh/.credentials.yaml if not in env.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = sys.argv[1]
N = int(sys.argv[2])
PARALLEL = int(sys.argv[3]) if len(sys.argv) > 3 else 5

OUT_DIR = ROOT / ".agentbga" / "duels" / Path(CONFIG).stem
OUT_DIR.mkdir(parents=True, exist_ok=True)

api_key = os.environ.get("DEEPSEEK_API_KEY", "")
if not api_key:
    print("DEEPSEEK_API_KEY not set in environment", file=sys.stderr)
    sys.exit(1)

# Verify every api_key_env referenced in the players config is set
_config_data = json.loads(Path(ROOT / CONFIG).read_text())
for p in _config_data.get("players", []):
    env_var = p.get("api_key_env")
    if env_var and not os.environ.get(env_var):
        print(f"{env_var} (needed by {p.get('name','?')}) not set in environment", file=sys.stderr)
        sys.exit(1)


def run_one(seed: int) -> dict:
    db = OUT_DIR / f"seed-{seed}.sqlite3"
    log = OUT_DIR / f"seed-{seed}.log"
    db.unlink(missing_ok=True)
    start = time.time()
    env = {**os.environ, "DEEPSEEK_API_KEY": api_key, "PYTHONPATH": str(ROOT / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "agentbga", "run",
         "--players-config", str(CONFIG), "--seed", str(seed),
         "--max-turns", "250", "--fallback", "fail",
         "--db", str(db), "--jsonl"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=3600,
    )
    duration = round(time.time() - start)
    log.write_text(proc.stdout + "\n---STDERR---\n" + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        return {"seed": seed, "status": "error", "winner": "?", "scores": "",
                "duration_s": duration, "error": proc.stderr[-200:] or proc.stdout[-200:]}
    # Parse final rankings from JSONL
    rankings_line = ""
    for line in proc.stdout.splitlines():
        if '"type":"rankings"' in line or '"rankings"' in line:
            rankings_line = line
    if rankings_line:
        try:
            data = json.loads(rankings_line)
            r = data.get("data", {}).get("rankings", [])
            winner = r[0]["player"] if r else "?"
            scores = "|".join(f"{x['player']}:{x.get('score', '?')}" for x in r)
        except (json.JSONDecodeError, KeyError, IndexError):
            winner, scores = "?", "?"
    else:
        winner, scores = "?", "?"
    return {"seed": seed, "status": "ok", "winner": winner, "scores": scores,
            "duration_s": duration, "error": ""}


csv_path = OUT_DIR / "results.csv"
with csv_path.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["seed", "status", "winner", "scores", "duration_s", "error"])
    w.writeheader()

print(f"Running {N} matches, {PARALLEL} in parallel. Output: {OUT_DIR}")
print(f"{'seed':>4} {'status':>7} {'winner':>50} {'dur':>6} {'scores'}")
print("-" * 100)

results = []
with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
    futures = {pool.submit(run_one, seed): seed for seed in range(1, N + 1)}
    for fut in as_completed(futures):
        res = fut.result()
        results.append(res)
        with csv_path.open("a", newline="") as f:
            csv.DictWriter(f, fieldnames=["seed", "status", "winner", "scores", "duration_s", "error"]).writerow(res)
        print(f"{res['seed']:>4} {res['status']:>7} {res['winner'][:50]:>50} {res['duration_s']:>5}s {res['scores']}")

# Summary
results.sort(key=lambda r: r["seed"])
ok = [r for r in results if r["status"] == "ok"]
err = [r for r in results if r["status"] == "error"]
seat0_name = "dsh"
seat1_name = "opencode"
dsh_wins = sum(1 for r in ok if seat0_name in r["winner"].lower())
opencode_wins = sum(1 for r in ok if seat1_name in r["winner"].lower())
other = sum(1 for r in ok if seat0_name not in r["winner"].lower() and seat1_name not in r["winner"].lower())

print("\n" + "=" * 60)
print(f"SUMMARY: dsh vs opencode (both deepseek-v4-flash)")
print("=" * 60)
print(f"  Completed: {len(ok)}/{N}  Errors: {len(err)}")
print(f"  dsh (seat 0) wins:      {dsh_wins}")
print(f"  opencode (seat 1) wins: {opencode_wins}")
print(f"  other/tie:              {other}")
if err:
    print(f"  Failed seeds: {', '.join(str(r['seed']) for r in err)}")
print(f"\nDetailed CSV: {csv_path}")
