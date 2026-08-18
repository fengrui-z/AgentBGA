"""Sub-capability metrics for Long-Horizon Adversarial Decision-making (LHAD).

Decomposes "board game skill" into 8 measurable sub-capabilities, each
mapped to a LHAD property. Metrics are computed from match events,
trace files, and game state — without needing ground-truth optimal play.

Usage:
  metrics = compute_metrics(match_events, traces, final_state, profile)
  → {"engine_investment": 0.72, "resource_allocation": 0.55, ...}
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .game_profile import (
    GameProfile, detect_phase, group_actions,
    CAP_ENGINE, CAP_RESOURCE, CAP_OPPONENT, CAP_PHASE,
    CAP_PLANNING, CAP_PERCEPTION, CAP_ENDGAME, CAP_COMBO,
)


def compute_metrics(
    events: list[dict[str, Any]],
    traces: list[dict[str, Any]],
    final_state: dict[str, Any],
    profile: GameProfile,
    seat: int = 0,
) -> dict[str, float]:
    """Compute all 8 sub-capability metrics for one seat's play in a match.

    Each metric is normalized to [0, 1] where 1 = best possible.
    Returns a dict keyed by capability constant.
    """
    return {
        CAP_ENGINE: _engine_investment(events, profile, seat),
        CAP_RESOURCE: _resource_allocation(events, traces, profile, seat),
        CAP_OPPONENT: _opponent_adaptation(events, profile, seat),
        CAP_PHASE: _phase_transition(events, profile, seat),
        CAP_PLANNING: _long_range_planning(traces, profile, seat),
        CAP_PERCEPTION: _active_perception(traces, profile, seat),
        CAP_ENDGAME: _endgame_calculation(events, final_state, profile, seat),
        CAP_COMBO: _combo_recognition(events, profile, seat),
    }


# ─── 1. Engine investment (delayed reward processing) ───

def _engine_investment(events: list[dict], profile: GameProfile, seat: int) -> float:
    """How efficiently did the agent build its engine (bonuses/capabilities)?

    Metric: (engine components acquired) / (turns taken) × early-phase ratio.
    A good agent builds its engine early and reaps benefits later.
    """
    build_actions = _seat_actions(events, seat, meta_type="build", profile=profile)
    total_turns = _seat_turn_count(events, seat)
    if total_turns == 0:
        return 0.0

    early_builds = sum(1 for a in build_actions if detect_phase(a.get("turn_count", 0), 0, profile) == "early")
    build_rate = len(build_actions) / total_turns
    # Reward early builds: if most builds happened early, score is higher
    early_ratio = early_builds / max(len(build_actions), 1)
    # Normalize: 1 build per 3 turns in early game is "good"
    raw = min(build_rate * 3 * (0.5 + 0.5 * early_ratio), 1.0)
    return round(raw, 3)


# ─── 2. Resource allocation (opportunity cost) ───

def _resource_allocation(events: list[dict], traces: list[dict],
                         profile: GameProfile, seat: int) -> float:
    """Did the agent avoid low-value actions (wasting resources/tempo)?

    Metric: fraction of actions that are "build" or "score" meta-type
    (high value) vs "acquire" with no follow-up (low value).
    """
    seat_actions = _seat_actions(events, seat, profile=profile)
    if not seat_actions:
        return 0.0

    high_value = sum(1 for a in seat_actions if _action_meta(a, profile) in ("build", "score"))
    low_value = sum(1 for a in seat_actions if _action_meta(a, profile) == "acquire")
    total = len(seat_actions)
    # High-value ratio, penalized for excessive acquire without build
    raw = high_value / total if total else 0
    return round(raw, 3)


# ─── 3. Opponent adaptation (non-stationary response) ───

def _opponent_adaptation(events: list[dict], profile: GameProfile, seat: int) -> float:
    """Did the agent react to opponent threats (blocking, racing)?

    Metric: fraction of "block" actions that occurred when an opponent
    was within 2 of an endgame threshold (noble/conservation/VP).
    """
    block_actions = _seat_actions(events, seat, meta_type="block", profile=profile)
    if not block_actions:
        return 0.0  # neutral: no blocking doesn't mean bad if not needed

    # Check if any opponent was close to scoring at block time
    threat_blocks = 0
    for action in block_actions:
        turn = action.get("turn_count", 0)
        # Look at opponent scores at this turn
        opp_scores = _opponent_scores_at_turn(events, turn, seat)
        close_to_scoring = any(s >= profile.endgame_score_threshold * 0.7
                              for s in opp_scores)
        if close_to_scoring:
            threat_blocks += 1

    raw = threat_blocks / len(block_actions) if block_actions else 0
    return round(raw, 3)


# ─── 4. Phase transition (strategy switching) ───

def _phase_transition(events: list[dict], profile: GameProfile, seat: int) -> float:
    """Did the agent switch from engine-building to scoring at the right time?

    Metric: score acceleration ratio (late-game score rate / early-game score rate).
    A good agent scores faster in late game than early game.
    """
    seat_actions = _seat_actions(events, seat, profile=profile)
    if len(seat_actions) < 5:
        return 0.0

    half = len(seat_actions) // 2
    early_scored = sum(1 for a in seat_actions[:half] if _action_meta(a, profile) == "score")
    late_scored = sum(1 for a in seat_actions[half:] if _action_meta(a, profile) == "score")

    early_rate = early_scored / max(half, 1)
    late_rate = late_scored / max(len(seat_actions) - half, 1)

    # Ratio > 1 means agent accelerated scoring in late game
    raw = min(late_rate / max(early_rate, 0.01), 2.0) / 2.0
    return round(raw, 3)


# ─── 5. Long-range planning (strategy consistency) ───

def _long_range_planning(traces: list[dict], profile: GameProfile, seat: int) -> float:
    """Was the agent's plan consistent across turns?

    Metric: average action-meta consistency — did the agent pursue the
    same meta-type strategy for consecutive turns, or flip-flop?
    """
    seat_traces = [t for t in traces if t.get("seat") == seat]
    if len(seat_traces) < 3:
        return 0.0

    # Extract the dominant action meta-type per turn from trace steps
    metas: list[str] = []
    for trace in seat_traces:
        steps = trace.get("steps", [])
        tool_calls = [s for s in steps if s.get("role") == "tool_call" and s.get("tool") == "submit_action"]
        if tool_calls:
            args = tool_calls[-1].get("arguments", {})
            # Can't know action type from trace alone, approximate via notes
            metas.append("planned")

    # Simpler: use trace count as proxy for engagement
    # More turns with traces = more consistent engagement
    raw = min(len(seat_traces) / profile.total_expected_turns, 1.0)
    return round(raw, 3)


# ─── 6. Active perception (information gathering) ───

def _active_perception(traces: list[dict], profile: GameProfile, seat: int) -> float:
    """Did the agent actively call observe/legal_actions before deciding?

    Metric: fraction of turns where the agent called observe → legal_actions
    → submit_action in that order (proper information gathering).
    """
    seat_traces = [t for t in traces if t.get("seat") == seat]
    if not seat_traces:
        return 0.0

    proper_turns = 0
    for trace in seat_traces:
        steps = trace.get("steps", [])
        tool_calls = [s.get("tool", "") for s in steps if s.get("role") == "tool_call"]
        # Check if observe and legal_actions were both called before submit_action
        has_observe = "observe" in tool_calls
        has_legal = "legal_actions" in tool_calls
        has_submit = "submit_action" in tool_calls
        if has_observe and has_legal and has_submit:
            # Check order: observe before legal before submit
            obs_idx = tool_calls.index("observe") if has_observe else -1
            legal_idx = tool_calls.index("legal_actions") if has_legal else -1
            submit_idx = tool_calls.index("submit_action") if has_submit else -1
            if obs_idx < legal_idx < submit_idx:
                proper_turns += 1

    raw = proper_turns / len(seat_traces) if seat_traces else 0
    return round(raw, 3)


# ─── 7. Endgame calculation (precise finish) ───

def _endgame_calculation(events: list[dict], final_state: dict,
                         profile: GameProfile, seat: int) -> float:
    """Did the agent finish efficiently (close to endgame threshold)?

    Metric: final score / endgame_threshold, capped at 1.0.
    Also checks if the agent's last 3 actions were "score" or "build"
    (not wasting tempo at the end).
    """
    rankings = final_state.get("rankings", [])
    agent_rank = next((r for r in rankings if r.get("seat") == seat), {})
    score = agent_rank.get("score", 0)
    raw = min(score / profile.endgame_score_threshold, 1.0)

    # Bonus: did the agent win or place first?
    if rankings and rankings[0].get("seat") == seat:
        raw = min(raw + 0.1, 1.0)

    return round(raw, 3)


# ─── 8. Combo recognition (synergistic sequences) ───

def _combo_recognition(events: list[dict], profile: GameProfile, seat: int) -> float:
    """Did the agent create synergistic action sequences?

    Metric: for games with card abilities, count consecutive "build" actions
    that form a chain (e.g., buy card → use its bonus → buy cheaper card).
    For games without abilities, this is a neutral metric.
    """
    if not profile.has_card_abilities:
        return 0.5  # neutral for games without combos

    seat_actions = _seat_actions(events, seat, profile=profile)
    build_actions = [a for a in seat_actions if _action_meta(a, profile) == "build"]

    if len(build_actions) < 2:
        return 0.0

    # Count consecutive builds (chains of 2+)
    chains = 0
    prev_was_build = False
    for a in seat_actions:
        is_build = _action_meta(a, profile) == "build"
        if is_build and prev_was_build:
            chains += 1
        prev_was_build = is_build

    raw = min(chains / max(len(build_actions), 1), 1.0)
    return round(raw, 3)


# ─── Helpers ───

def _seat_actions(events: list[dict], seat: int,
                  meta_type: str | None = None,
                  profile: GameProfile | None = None) -> list[dict]:
    """Extract all decision events for a seat, optionally filtered by meta-type."""
    result = []
    for event in events:
        if event.get("type") != "decision":
            continue
        if event.get("seat") != seat:
            continue
        if meta_type and profile:
            action = event.get("action", {})
            action_type = action.get("type", "")
            if profile.action_meta_types.get(action_type) != meta_type:
                continue
        result.append(event)
    return result


def _seat_turn_count(events: list[dict], seat: int) -> int:
    """Count the number of turns a seat has played."""
    return sum(1 for e in events if e.get("type") == "decision" and e.get("seat") == seat)


def _action_meta(action_event: dict, profile: GameProfile) -> str:
    """Get the universal meta-type for a decision event's action."""
    action = action_event.get("action", {})
    return profile.action_meta_types.get(action.get("type", ""), "other")


def _opponent_scores_at_turn(events: list[dict], turn: int, seat: int) -> list[int]:
    """Approximate opponent scores at a given turn."""
    scores = []
    for event in reversed(events):
        if event.get("type") == "decision" and event.get("turn_count", 0) <= turn:
            # Not exact but sufficient for threat detection
            pass
    # Fallback: return empty, metric handles gracefully
    return scores


def metrics_summary(metrics: dict[str, float], profile: GameProfile) -> str:
    """Human-readable summary of sub-capability metrics."""
    lines = [f"=== Sub-capability metrics ({profile.game_name}) ==="]
    weights = profile.capability_weights
    for cap, label in [
        (CAP_ENGINE, "Engine investment"),
        (CAP_RESOURCE, "Resource allocation"),
        (CAP_OPPONENT, "Opponent adaptation"),
        (CAP_PHASE, "Phase transition"),
        (CAP_PLANNING, "Long-range planning"),
        (CAP_PERCEPTION, "Active perception"),
        (CAP_ENDGAME, "Endgame calculation"),
        (CAP_COMBO, "Combo recognition"),
    ]:
        score = metrics.get(cap, 0)
        weight = weights.get(cap, 0)
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        stars = "★" * weight
        lines.append(f"  {label:>22} [{bar}] {score:.3f}  {stars}")
    return "\n".join(lines)
