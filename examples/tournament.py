#!/usr/bin/env python3
"""AgentBGA tournament runner for ICLR-scale experiments.

Runs round-robin 2-agent matches on Splendor with controlled variables:
  Mode A (harness-fixed): fix one harness, vary models pairwise.
  Mode B (model-fixed):   fix one model, vary harnesses pairwise.

Each pair plays N seeds × 2 seat orders (A-first / B-first).
Results are written to CSV + a summary with Elo ratings.

Usage:
  python3 tournament.py --base-url https://your-gateway.example/v1 \\
    --parallel 30 --seeds 5 \\
    --mode both \\
    --harness opencode codex dsh \\
    --models glm-5.2 qwen3.7-max qwen3.7-plus qwen3.7-flash \\
              deepseek-v4-pro kimi-k2.7-code gpt-5.5

Environment:
  OPENAI_API_KEY  (required, shared by all models via the gateway)

Outputs:
  .agentbga/tournament/<timestamp>/results.csv   — one row per match
  .agentbga/tournament/<timestamp>/summary.txt   — aggregated stats + Elo
  .agentbga/tournament/<timestamp>/seed-*.log    — per-match JSONL log
  .agentbga/tournament/<timestamp>/seed-*.sqlite3 — per-match DB
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
API_KEY_ENV = "OPENAI_API_KEY"


# ───────────────────────── helpers ─────────────────────────


@dataclass(frozen=True)
class AgentSpec:
    """One seat configuration."""
    name: str
    backend: str        # opencode | codex | dsh
    model: str
    base_url: str
    api_key_env: str = API_KEY_ENV

    def to_player_dict(self) -> dict:
        return {
            "name": self.name,
            "backend": self.backend,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
        }


@dataclass(frozen=True)
class Matchup:
    """One pairwise matchup definition."""
    label: str
    seat0: AgentSpec
    seat1: AgentSpec

    def config_dict(self) -> dict:
        return {
            "schema_version": "agentbga.players.v1",
            "players": [self.seat0.to_player_dict(), self.seat1.to_player_dict()],
        }


def build_matchups(
    mode: str,
    harnesses: list[str],
    models: list[str],
    base_url: str,
    fixed_harness: str = "opencode",
    fixed_model: str = "deepseek-v4-pro",
) -> list[Matchup]:
    """Build the list of pairwise matchups for the selected mode.

    mode="harness": fix one harness, all model pairs.
    mode="model":   fix one model, all harness pairs.
    mode="both":    union of the two.
    """
    matchups: list[Matchup] = []

    def mk_label(a: AgentSpec, b: AgentSpec) -> str:
        return f"{a.backend}+{a.model}__vs__{b.backend}+{b.model}"

    if mode in ("harness", "both"):
        h = fixed_harness
        for m_a, m_b in itertools.combinations(models, 2):
            a = AgentSpec(f"{h}+{m_a}", h, m_a, base_url)
            b = AgentSpec(f"{h}+{m_b}", h, m_b, base_url)
            matchups.append(Matchup(mk_label(a, b), a, b))

    if mode in ("model", "both"):
        m = fixed_model
        for h_a, h_b in itertools.combinations(harnesses, 2):
            a = AgentSpec(f"{h_a}+{m}", h_a, m, base_url)
            b = AgentSpec(f"{h_b}+{m}", h_b, m, base_url)
            matchups.append(Matchup(mk_label(a, b), a, b))

    return matchups


# ───────────────────────── match runner ─────────────────────────


def run_match(
    matchup: Matchup,
    seat_order: str,   # "ab" (seat0=A seat1=B) or "ba" (swap)
    seed: int,
    out_dir: Path,
    max_turns: int,
    timeout_s: int,
) -> dict:
    """Run one match and return a result row."""
    if seat_order == "ba":
        players = [matchup.seat1, matchup.seat0]
        order_tag = "BA"
    else:
        players = [matchup.seat0, matchup.seat1]
        order_tag = "AB"

    tag = f"{matchup.label}__{order_tag}__s{seed}"
    db = out_dir / f"{tag}.sqlite3"
    log = out_dir / f"{tag}.log"
    db.unlink(missing_ok=True)

    config_path = out_dir / f"{tag}.json"
    config_path.write_text(
        json.dumps({
            "schema_version": "agentbga.players.v1",
            "players": [p.to_player_dict() for p in players],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    start = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "agentbga", "run",
             "--players-config", str(config_path),
             "--seed", str(seed),
             "--max-turns", str(max_turns),
             "--fallback", "fail",
             "--db", str(db),
             "--jsonl"],
            cwd=str(ROOT), env=env, capture_output=True, text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        duration = round(time.time() - start)
        log.write_text(f"TIMEOUT after {timeout_s}s", encoding="utf-8")
        return {"matchup": matchup.label, "order": order_tag, "seed": seed,
                "status": "timeout", "winner": "", "scores": "",
                "duration_s": duration, "error": f"timeout {timeout_s}s"}

    duration = round(time.time() - start)
    log.write_text(proc.stdout + "\n--- STDERR ---\n" + proc.stderr, encoding="utf-8")

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout)[-300:]
        return {"matchup": matchup.label, "order": order_tag, "seed": seed,
                "status": "error", "winner": "", "scores": "",
                "duration_s": duration, "error": err.replace("\n", " ")}

    # Parse match_finished from JSONL
    finished = None
    for line in proc.stdout.splitlines():
        if '"match_finished"' in line:
            try:
                finished = json.loads(line)
            except json.JSONDecodeError:
                continue
    if not finished:
        return {"matchup": matchup.label, "order": order_tag, "seed": seed,
                "status": "no_result", "winner": "", "scores": "",
                "duration_s": duration, "error": "no match_finished line"}

    rankings = finished.get("rankings", [])
    winner = rankings[0]["player"] if rankings else ""
    scores = "|".join(f"{r['player']}:{r.get('score', '?')}" for r in rankings)
    return {"matchup": matchup.label, "order": order_tag, "seed": seed,
            "status": "ok", "winner": winner, "scores": scores,
            "duration_s": duration, "error": ""}


# ───────────────────────── Elo (Bradley-Terry) ─────────────────────────


def compute_elo(results: list[dict], k: float = 32.0, base: float = 1500.0,
                iterations: int = 200) -> dict[str, dict]:
    """Simple iterative Elo from win/loss results.

    Returns {agent_name: {"elo": float, "wins": int, "games": int, "winrate": float}}.
    """
    stats: dict[str, dict] = {}
    for r in results:
        if r["status"] != "ok":
            continue
        # Determine winner and loser agent names from scores
        scores_parts = r["scores"].split("|") if r["scores"] else []
        if len(scores_parts) != 2:
            continue
        parts = [p.split(":") for p in scores_parts]
        names = [parts[0][0], parts[1][0]]
        scores = [int(parts[0][1]) if parts[0][1].isdigit() else 0,
                  int(parts[1][1]) if parts[1][1].isdigit() else 0]
        winner_idx = 0 if scores[0] > scores[1] else 1
        loser_idx = 1 - winner_idx
        winner_name = names[winner_idx]
        loser_name = names[loser_idx]
        for name in names:
            if name not in stats:
                stats[name] = {"elo": base, "wins": 0, "games": 0}
        stats[winner_name]["wins"] += 1
        stats[winner_name]["games"] += 1
        stats[loser_name]["games"] += 1

    # Iterative Elo update
    for _ in range(iterations):
        for r in results:
            if r["status"] != "ok":
                continue
            scores_parts = r["scores"].split("|") if r["scores"] else []
            if len(scores_parts) != 2:
                continue
            parts = [p.split(":") for p in scores_parts]
            names = [parts[0][0], parts[1][0]]
            scores = [int(parts[0][1]) if parts[0][1].isdigit() else 0,
                      int(parts[1][1]) if parts[1][1].isdigit() else 0]
            if scores[0] == scores[1]:
                continue
            winner_idx = 0 if scores[0] > scores[1] else 1
            loser_idx = 1 - winner_idx
            wn, ln = names[winner_idx], names[loser_idx]
            we = stats[wn]["elo"]
            le = stats[ln]["elo"]
            expected_w = 1 / (1 + 10 ** ((le - we) / 400))
            stats[wn]["elo"] += k * (1 - expected_w)
            stats[ln]["elo"] -= k * (1 - expected_w)

    for s in stats.values():
        s["winrate"] = round(s["wins"] / s["games"], 3) if s["games"] else 0

    return stats


# ───────────────────────── main ─────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="AgentBGA tournament runner")
    ap.add_argument("--base-url", required=True,
                    help="model API base URL; explicitly choose a trusted endpoint")
    ap.add_argument("--parallel", type=int, default=30, help="concurrent matches")
    ap.add_argument("--seeds", type=int, default=5,
                    help="seeds per seat order (total = seeds × 2 orders)")
    ap.add_argument("--mode", choices=["harness", "model", "both"], default="both",
                    help="harness=fix harness vary model; model=fix model vary harness")
    ap.add_argument("--harness", nargs="+", default=["opencode", "codex", "dsh"],
                    help="harness backends to test")
    ap.add_argument("--models", nargs="+",
                    default=["glm-5.2", "qwen3.7-max", "qwen3.7-plus", "qwen3.7-flash",
                             "deepseek-v4-pro", "kimi-k2.7-code", "gpt-5.5"],
                    help="model IDs to test")
    ap.add_argument("--fixed-harness", default="opencode",
                    help="harness for mode=harness (default: opencode)")
    ap.add_argument("--fixed-model", default="deepseek-v4-pro",
                    help="model for mode=model (default: deepseek-v4-pro)")
    ap.add_argument("--max-turns", type=int, default=250)
    ap.add_argument("--timeout", type=int, default=3600, help="per-match timeout (s)")
    ap.add_argument("--out-dir", help="output directory (default: auto timestamp)")
    args = ap.parse_args()

    # Check API key
    if not os.environ.get(API_KEY_ENV):
        print(f"Error: {API_KEY_ENV} not set in environment", file=sys.stderr)
        return 1

    # Build matchups
    matchups = build_matchups(
        mode=args.mode,
        harnesses=args.harness,
        models=args.models,
        base_url=args.base_url,
        fixed_harness=args.fixed_harness,
        fixed_model=args.fixed_model,
    )

    # Build task list: (matchup, seat_order, seed)
    tasks = []
    for mu in matchups:
        for seed in range(1, args.seeds + 1):
            tasks.append((mu, "ab", seed))
            tasks.append((mu, "ba", seed))

    total = len(tasks)
    if total == 0:
        print("No matchups generated. Check --mode / --models / --harness.", file=sys.stderr)
        return 1

    # Output dir
    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = ROOT / ".agentbga" / "tournament" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save experiment config
    (out_dir / "experiment_config.json").write_text(
        json.dumps({
            "base_url": args.base_url,
            "mode": args.mode,
            "harnesses": args.harness,
            "models": args.models,
            "fixed_harness": args.fixed_harness,
            "fixed_model": args.fixed_model,
            "seeds": args.seeds,
            "seat_orders": ["ab", "ba"],
            "parallel": args.parallel,
            "max_turns": args.max_turns,
            "timeout_s": args.timeout,
            "total_matches": total,
            "matchups": [mu.label for mu in matchups],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"=== AgentBGA Tournament ===")
    print(f"Mode: {args.mode}")
    print(f"Matchups: {len(matchups)}")
    print(f"Seeds: {args.seeds} × 2 orders = {args.seeds * 2} games per matchup")
    print(f"Total matches: {total}")
    print(f"Parallel: {args.parallel}")
    print(f"Output: {out_dir}")
    print()

    # CSV writer (incremental)
    csv_path = out_dir / "results.csv"
    fieldnames = ["matchup", "order", "seed", "status", "winner", "scores",
                  "duration_s", "error"]
    with csv_path.open("w", newline="") as f:
        csv.DictWriter(f, fieldnames=fieldnames).writeheader()

    # Run
    results: list[dict] = []
    completed = 0
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futures = {
            pool.submit(run_match, mu, order, seed, out_dir, args.max_turns, args.timeout): (mu, order, seed)
            for mu, order, seed in tasks
        }
        for fut in as_completed(futures):
            try:
                res = fut.result()
            except Exception as e:
                mu, order, seed = futures[fut]
                res = {"matchup": mu.label, "order": order, "seed": seed,
                       "status": "crash", "winner": "", "scores": "",
                       "duration_s": 0, "error": str(e)}
            results.append(res)
            with csv_path.open("a", newline="") as f:
                csv.DictWriter(f, fieldnames=fieldnames).writerow(res)
            completed += 1
            elapsed = round(time.time() - start_time)
            eta = round((time.time() - start_time) / completed * (total - completed))
            status_icon = "OK" if res["status"] == "ok" else res["status"].upper()[:4]
            print(f"[{completed:>4}/{total}] {status_icon:>4} {res['matchup'][:40]:>40} "
                  f"{res['order']} s{res['seed']}  {res['duration_s']:>5}s  "
                  f"winner={res['winner'][:30]:>30}  "
                  f"elapsed={elapsed}s eta={eta}s")

    # ── Summary ──
    results.sort(key=lambda r: (r["matchup"], r["order"], r["seed"]))
    ok = [r for r in results if r["status"] == "ok"]
    err = [r for r in results if r["status"] != "ok"]

    summary_lines = []
    summary_lines.append(f"=== Tournament Summary ===")
    summary_lines.append(f"Total: {total}  OK: {len(ok)}  Errors: {len(err)}")
    summary_lines.append(f"Wall time: {round(time.time() - start_time)}s")
    summary_lines.append("")

    # Per-matchup win rates
    summary_lines.append(f"{'Matchup':>50} {'AB_wins':>7} {'BA_wins':>7} {'total':>5}")
    summary_lines.append("-" * 75)
    matchup_groups: dict[str, list[dict]] = {}
    for r in ok:
        matchup_groups.setdefault(r["matchup"], []).append(r)
    for mu_label in sorted(matchup_groups):
        rows = matchup_groups[mu_label]
        # In AB order, seat0 is the first agent in label; in BA, seat0 is the second.
        # Winner is by player name. We count how often the "first agent in label" wins.
        label_parts = mu_label.split("__vs__")
        agent_a, agent_b = label_parts[0], label_parts[1]
        a_wins = sum(1 for r in rows if agent_a in r["winner"])
        b_wins = sum(1 for r in rows if agent_b in r["winner"])
        total_mu = len(rows)
        summary_lines.append(
            f"{mu_label[:50]:>50} {a_wins:>7} {b_wins:>7} {total_mu:>5}"
        )

    # Elo
    summary_lines.append("")
    summary_lines.append("=== Elo Ratings (Bradley-Terry) ===")
    summary_lines.append(f"{'Agent':>50} {'Elo':>6} {'Wins':>4} {'Games':>5} {'WinRate':>7}")
    summary_lines.append("-" * 75)
    elo = compute_elo(results)
    for name in sorted(elo, key=lambda n: -elo[n]["elo"]):
        s = elo[name]
        summary_lines.append(
            f"{name[:50]:>50} {round(s['elo']):>6} {s['wins']:>4} {s['games']:>5} {s['winrate']:>7}"
        )

    if err:
        summary_lines.append("")
        summary_lines.append(f"=== Failed matches ({len(err)}) ===")
        for r in err[:20]:
            summary_lines.append(f"  {r['matchup']} {r['order']} s{r['seed']}: {r['status']} {r['error'][:80]}")
        if len(err) > 20:
            summary_lines.append(f"  ... and {len(err) - 20} more")

    summary = "\n".join(summary_lines)
    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")
    print()
    print(summary)
    print(f"\nResults CSV: {csv_path}")
    print(f"Summary:     {out_dir / 'summary.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
