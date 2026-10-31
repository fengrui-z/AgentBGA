"""Compute usage for algorithms separately from model token accounting."""

from .config import BASELINE_BACKENDS, BASELINE_VERSION


def baseline_metrics(configs, calls):
    players = []
    for seat, config in enumerate(configs):
        if config.backend not in BASELINE_BACKENDS:
            continue
        rows = [c["metadata"] for c in calls if c["seat"] == seat]
        players.append(
            {
                "seat": seat,
                "algorithm": config.backend,
                "algorithm_version": BASELINE_VERSION,
                "algorithm_params": config.algorithm_params,
                "decisions": len(rows),
                "fallbacks": sum(bool(r.get("fallback")) for r in rows),
                **{
                    key: sum(r.get(key, 0) for r in rows)
                    for key in (
                        "latency_ms",
                        "iterations",
                        "simulation_steps",
                        "nodes",
                        "evaluated_candidates",
                    )
                },
            }
        )
    return {"schema_version": "agentbga.baseline-metrics.v1", "players": players}
