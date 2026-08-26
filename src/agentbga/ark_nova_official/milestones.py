"""Official base-game Conservation track milestone flows."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from .semantics import SemanticEngine, SemanticRuleError
from .state import clone_state, validate_semantic_state


OFFICIAL_CONSERVATION_MILESTONE_IDS = frozenset({
    "conservation-2",
    "conservation-5",
    "conservation-8",
    "conservation-10",
})


def _system_effect(op: str, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"op": op, "args": dict(args or {}), "timing": "system"}


def official_conservation_milestones() -> list[dict[str, Any]]:
    """Return the four data-driven base-game Conservation milestones."""
    return [
        {
            "id": "conservation-2",
            "track": "conservation",
            "at": 2,
            "scope": "player",
            "effects": [_system_effect("choose_action_upgrade_or_worker")],
        },
        {
            "id": "conservation-5",
            "track": "conservation",
            "at": 5,
            "scope": "player",
            "effects": [_system_effect("choose_conservation_reward", {"at": 5})],
        },
        {
            "id": "conservation-8",
            "track": "conservation",
            "at": 8,
            "scope": "player",
            "effects": [_system_effect("choose_conservation_reward", {"at": 8})],
        },
        {
            "id": "conservation-10",
            "track": "conservation",
            "at": 10,
            "scope": "global",
            "effects": [_system_effect("for_each_player", {
                "effects": [_system_effect("discard_final_scoring_card")],
            }), _system_effect("mark_final_scoring_discard_complete")],
        },
    ]


def install_official_conservation_milestones(
    state: dict[str, Any],
    *,
    bonuses_at_5: Sequence[Mapping[str, Any]] = (),
    bonuses_at_8: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Install the official 2/5/8/10 flows and the two shared bonus pools.

    Bonus entries use project-authored labels and semantic effects::

        {"id": "bonus-reputation", "label": "Gain reputation",
         "effects": [{"op": "move_track", ...}]}

    Publisher art and prose are intentionally not part of the state contract.
    """
    next_state = clone_state(state)
    existing = {item.get("id") for item in next_state.get("milestones", [])}
    if existing & OFFICIAL_CONSERVATION_MILESTONE_IDS:
        raise SemanticRuleError("official Conservation milestones are already installed")
    next_state["milestones"].extend(official_conservation_milestones())
    next_state["conservation_bonus_slots"] = {
        "5": _prepare_bonus_tiles(bonuses_at_5),
        "8": _prepare_bonus_tiles(bonuses_at_8),
    }
    validate_semantic_state(next_state)
    return next_state


def queue_endgame_final_scoring_discard(
    engine: SemanticEngine, state: dict[str, Any], *, starting_seat: int = 0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Open the rulebook fallback discard if nobody reached 10 Conservation.

    The choice moves clockwise from ``starting_seat`` and must finish before
    final card effects and track-distance scoring are calculated.
    """
    if state["endgame"].get("final_scoring_discard_completed"):
        return clone_state(state), []
    if not isinstance(starting_seat, int) or isinstance(starting_seat, bool) or not 0 <= starting_seat < state["player_count"]:
        raise SemanticRuleError("Final Scoring discard starting seat is out of range")
    if any(len(player["final_scoring_cards"]) < 1 for player in state["players"]):
        raise SemanticRuleError("every player must hold a Final Scoring card before the discard")
    prepared = clone_state(state)
    resume_phase = prepared["phase"]
    prepared["phase"] = "final_scoring_discard"
    effects = [
        _system_effect("for_each_player", {
            "effects": [_system_effect("discard_final_scoring_card")],
        }),
        _system_effect("mark_final_scoring_discard_complete"),
    ]
    return engine.start_effects(
        prepared,
        starting_seat,
        effects,
        source_id="system:endgame-final-scoring-discard",
        completion={
            "type": "finish_final_scoring_discard",
            "resume_phase": resume_phase,
        },
    )


def _prepare_bonus_tiles(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if len(values) > 2:
        raise SemanticRuleError("each Conservation milestone accepts at most two bonus tiles")
    result = []
    seen = set()
    for raw in values:
        if not isinstance(raw, Mapping):
            raise SemanticRuleError("Conservation bonus tile must be an object")
        tile_id = raw.get("id")
        effects = raw.get("effects")
        if not isinstance(tile_id, str) or not tile_id or tile_id in seen:
            raise SemanticRuleError("Conservation bonus tile IDs must be non-empty and unique")
        if not isinstance(effects, list):
            raise SemanticRuleError("Conservation bonus tile effects must be an array")
        seen.add(tile_id)
        result.append({
            "id": tile_id,
            "label": str(raw.get("label", tile_id)),
            "effects": deepcopy(effects),
            "available": True,
        })
    return result
