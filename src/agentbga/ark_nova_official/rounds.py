"""Official shared Break procedure expressed through semantic effects."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .semantics import SemanticEngine, SemanticRuleError
from .state import DONATION_COSTS, next_donation_cost


def _system_effect(op: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"op": op, "args": args or {}, "timing": "system"}


def queue_break(
    engine: SemanticEngine, state: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Begin the six ordered base-game Break steps.

    Hand-limit decisions pause in the same serializable choice-window mechanism
    used by cards. Income is resolved clockwise from the Break initiator so
    display-taking income effects can later be represented without a side channel.
    """
    track = state.get("break", {})
    if track.get("mode") != "shared_track":
        raise SemanticRuleError("the solo round procedure is separate from the shared Break")
    if not track.get("pending") or track.get("initiator") is None:
        raise SemanticRuleError("the shared Break has not been triggered")
    if state["resolution"]["queue"] or state["resolution"]["pending_choice"] is not None:
        raise SemanticRuleError("cannot begin a Break during another semantic resolution")
    initiator = int(track["initiator"])
    prepared = deepcopy(state)
    prepared["phase"] = "break"
    effects = [
        _system_effect("for_each_player", {"effects": [_system_effect("discard_to_hand_limit")]}),
        _system_effect("for_each_player", {"effects": [_system_effect("clear_action_tokens")]}),
        _system_effect("for_each_player", {"effects": [_system_effect("recall_association_workers")]}),
        _system_effect("replenish_association"),
        _system_effect("refresh_display"),
        _system_effect("for_each_player", {"effects": [_system_effect("take_income")]}),
        _system_effect("reset_break"),
    ]
    return engine.start_effects(
        prepared,
        initiator,
        effects,
        source_id="system:break",
        completion={"type": "finish_break", "initiator": initiator},
    )


def advance_solo_round_after_turn(
    state: dict[str, Any], seat: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Move one solo-tile token and open the next Break or final scoring."""
    track = state.get("break", {})
    if track.get("mode") != "solo_round" or state.get("player_count") != 1 or seat != 0:
        raise SemanticRuleError("solo round advancement requires the solo player")
    prepared = deepcopy(state)
    solo = prepared["break"]
    left = int(solo["solo_tokens_left"])
    total = int(solo["solo_total_tokens"])
    if left < 1 or total < 2 or left > total:
        raise SemanticRuleError("solo tile token state is invalid")
    solo["solo_tokens_left"] = left - 1
    events = [{
        "type": "solo_token_moved", "seat": seat,
        "round": int(solo["solo_round"]),
        "tokens_left": int(solo["solo_tokens_left"]),
        "round_size": total,
    }]
    if left > 1:
        return prepared, events
    if total == 2:
        prepared["endgame"].update({
            "triggered": True,
            "triggered_by": seat,
            "trigger_boundary": "solo_round_limit",
            "final_turn_seats": [],
        })
        events.append({"type": "solo_round_limit_reached", "seat": seat, "turns": 27})
        return prepared, events

    # A solo token occupies the cheapest *currently open* finite donation
    # space.  Player donations can therefore move this token farther along the
    # row; once 2/5/7/10 are full, the token sits beside the repeatable 12 space.
    cost = next_donation_cost(prepared)
    if cost != DONATION_COSTS[-1]:
        block = {
            "seat": None, "cost": cost, "source": "solo_tile",
            "position": DONATION_COSTS.index(cost) + 1,
        }
        prepared["donations_made"].append(block)
        solo["solo_donation_blocks"].append(deepcopy(block))
        events.append({"type": "solo_donation_space_blocked", "cost": cost})
    else:
        solo["solo_donation_blocks"].append({
            "seat": None, "cost": None, "source": "solo_tile_next_to_12",
            "position": "next_to_12",
        })
        events.append({"type": "solo_donation_token_placed_next_to_12"})
    solo["solo_total_tokens"] = total - 1
    solo["solo_tokens_left"] = total - 1
    solo["solo_round"] = int(solo["solo_round"]) + 1
    solo["pending"] = True
    solo["initiator"] = seat
    prepared["phase"] = "break_pending"
    return prepared, events


def queue_solo_break(
    engine: SemanticEngine, state: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve solo Break steps 1–5; the shared-track reset step is omitted."""
    track = state.get("break", {})
    if track.get("mode") != "solo_round" or not track.get("pending"):
        raise SemanticRuleError("the solo Break has not been triggered")
    if state["resolution"]["queue"] or state["resolution"]["pending_choice"] is not None:
        raise SemanticRuleError("cannot begin a solo Break during another resolution")
    prepared = deepcopy(state)
    prepared["phase"] = "break"
    prepared["break"]["pending"] = False
    prepared["break"]["count"] = int(prepared["break"]["count"]) + 1
    effects = [
        _system_effect("for_each_player", {"effects": [_system_effect("discard_to_hand_limit")]}),
        _system_effect("for_each_player", {"effects": [_system_effect("clear_action_tokens")]}),
        _system_effect("for_each_player", {"effects": [_system_effect("recall_association_workers")]}),
        _system_effect("replenish_association"),
        _system_effect("refresh_display"),
        _system_effect("for_each_player", {"effects": [_system_effect("take_income")]}),
    ]
    resolved, events = engine.start_effects(
        prepared, 0, effects, source_id="system:solo-break",
        completion={"type": "finish_break", "initiator": 0},
    )
    return resolved, [{
        "type": "solo_break_started",
        "round": int(prepared["break"]["solo_round"]) - 1,
        "break_count": int(prepared["break"]["count"]),
    }, *events]
