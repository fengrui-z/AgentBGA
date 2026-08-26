"""Concrete resolver for the official Cards action.

The generic action envelope locks strength and Action-card side.  This module
owns the domain choices that follow: draw versus Snap, deck/display sources,
the mandatory discard, and the after-finishing display refill.
"""

from __future__ import annotations

from copy import deepcopy
import random
from typing import Any, Mapping

from .actions import complete_action_execution, current_action_execution, defer_after_finishing
from .semantics import SemanticEngine, SemanticRuleError
from .state import clone_state, validate_semantic_state


_DISPLAY_REFILL_EFFECT = {
    "op": "refill_card_display",
    "timing": "after_finishing",
    "args": {"target_size": 6},
}


def reputation_display_limit(reputation: int) -> int:
    """Return how many display positions are covered by a Reputation value."""
    if not isinstance(reputation, int) or isinstance(reputation, bool) or reputation < 0:
        raise SemanticRuleError("Reputation must be a non-negative integer")
    if reputation <= 1:
        return 1
    if reputation <= 3:
        return 2
    if reputation <= 6:
        return 3
    if reputation <= 9:
        return 4
    if reputation <= 12:
        return 5
    return 6


def legal_cards_execution_actions(state: Mapping[str, Any], seat: int) -> list[dict[str, Any]]:
    """Enumerate authoritative next choices for the active Cards execution."""
    try:
        execution, resolution = _cards_context(state, seat)
    except SemanticRuleError:
        return []
    spec = execution["spec"]
    if resolution is None:
        actions: list[dict[str, Any]] = []
        if _available_draw_count(state, seat, bool(execution["upgraded"])) >= spec["draw_count"]:
            actions.append({
                "id": "cards:draw",
                "label": f"Draw {spec['draw_count']} card(s)",
                "action": {"type": "begin_cards_draw"},
            })
        if "snap" in spec["modes"]:
            positions = state["turn"]["action_session"].get("cards_display_position_by_id", {})
            actions.extend(
                {
                    "id": f"cards:snap:{card_id}",
                    "label": f"Snap display card {positions.get(card_id, index) + 1}",
                    "action": {"type": "snap_cards_action_card", "card_id": card_id},
                }
                for index, card_id in enumerate(_unique_card_ids(state["card_display"], "display"))
            )
        return actions
    if resolution["mode"] != "draw":
        raise SemanticRuleError("unknown Cards action resolution mode")
    if resolution["remaining_draws"] > 0:
        actions = []
        if state["zoo_deck"] or state["zoo_discard"]:
            actions.append({
                "id": "cards:draw:deck",
                "label": "Draw from deck",
                "action": {"type": "draw_cards_action_card", "source": "deck"},
            })
        if execution["upgraded"]:
            limit = reputation_display_limit(state["players"][seat]["tracks"]["reputation"])
            positions = state["turn"]["action_session"]["cards_display_position_by_id"]
            accessible = [
                (card, positions.get(card.get("id"), 99)) for card in state["card_display"]
                if positions.get(card.get("id"), 99) < limit
            ]
            _unique_card_ids([card for card, _ in accessible], "Reputation-range display")
            actions.extend(
                {
                    "id": f"cards:draw:display:{card_id}",
                    "label": f"Take display card {position + 1}",
                    "action": {
                        "type": "draw_cards_action_card", "source": "display", "card_id": card_id,
                    },
                }
                for card, position in accessible
                for card_id in [card["id"]]
            )
        return actions
    if resolution["remaining_discards"] > 0:
        return [
            {
                "id": f"cards:discard:{card_id}",
                "label": f"Discard {card_id}",
                "action": {"type": "discard_cards_action_card", "card_id": card_id},
            }
            for card_id in _unique_card_ids(state["players"][seat]["hand"], "hand")
        ]
    raise SemanticRuleError("completed Cards resolution was not closed")


def apply_cards_execution_action(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply one action returned by :func:`legal_cards_execution_actions`."""
    if not isinstance(action, Mapping) or not isinstance(action.get("type"), str):
        raise SemanticRuleError("Cards execution action must contain a type")
    legal = {item["id"]: item["action"] for item in legal_cards_execution_actions(state, seat)}
    requested = dict(action)
    if requested not in legal.values():
        raise SemanticRuleError("Cards execution choice is not currently legal")
    action_type = requested["type"]
    if action_type == "begin_cards_draw":
        return _begin_draw(engine, state, seat)
    if action_type == "draw_cards_action_card":
        return _draw_one(engine, state, seat, requested)
    if action_type == "discard_cards_action_card":
        return _discard_one(engine, state, seat, requested["card_id"])
    if action_type == "snap_cards_action_card":
        return _snap(engine, state, seat, requested["card_id"])
    raise SemanticRuleError(f"unknown Cards execution action: {action_type}")


def _cards_context(
    state: Mapping[str, Any], seat: int,
) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    execution = current_action_execution(state, seat)
    if execution["action"] != "cards":
        raise SemanticRuleError("the active execution is not a Cards action")
    resolution = state["turn"]["action_session"].get("cards_resolution")
    if resolution is not None and not isinstance(resolution, Mapping):
        raise SemanticRuleError("invalid Cards action resolution state")
    return execution, resolution


def _begin_draw(
    engine: SemanticEngine, state: dict[str, Any], seat: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    execution, resolution = _cards_context(state, seat)
    if resolution is not None:
        raise SemanticRuleError("Cards draw resolution has already started")
    next_state, events = _advance_break(engine, state, seat, execution["spec"]["break_steps"])
    _ensure_action_display_positions(next_state)
    next_state["turn"]["action_session"]["cards_resolution"] = {
        "mode": "draw",
        "remaining_draws": execution["spec"]["draw_count"],
        "remaining_discards": execution["spec"]["discard_count"],
        "drawn_card_ids": [],
        "discarded_card_ids": [],
        "display_changed": False,
    }
    validate_semantic_state(next_state)
    return next_state, [*events, {
        "type": "cards_draw_started",
        "seat": seat,
        "draw_count": execution["spec"]["draw_count"],
        "discard_count": execution["spec"]["discard_count"],
    }]


def _draw_one(
    engine: SemanticEngine, state: dict[str, Any], seat: int, action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    next_state = clone_state(state)
    resolution = next_state["turn"]["action_session"]["cards_resolution"]
    source = action["source"]
    if source == "deck":
        recycled = _recycle_discard_if_needed(next_state)
        card = next_state["zoo_deck"].pop()
        position = None
    else:
        card, _ = _remove_card(next_state["card_display"], action["card_id"], "display")
        position = next_state["turn"]["action_session"]["cards_display_position_by_id"][card["id"]]
        resolution["display_changed"] = True
        recycled = False
    next_state["players"][seat]["hand"].append(card)
    resolution["remaining_draws"] -= 1
    resolution["drawn_card_ids"].append(card["id"])
    events = [{
        "type": "cards_action_card_drawn",
        "seat": seat,
        "source": source,
        "card_id": card["id"],
        "display_position": None if position is None else position + 1,
        "remaining_draws": resolution["remaining_draws"],
        "deck_recycled": recycled,
    }]
    if resolution["remaining_draws"] == 0 and resolution["remaining_discards"] == 0:
        return _complete_cards_resolution(engine, next_state, seat, events)
    validate_semantic_state(next_state)
    return next_state, events


def _discard_one(
    engine: SemanticEngine, state: dict[str, Any], seat: int, card_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    next_state = clone_state(state)
    resolution = next_state["turn"]["action_session"]["cards_resolution"]
    card, _ = _remove_card(next_state["players"][seat]["hand"], card_id, "hand")
    next_state["zoo_discard"].append(card)
    resolution["remaining_discards"] -= 1
    resolution["discarded_card_ids"].append(card_id)
    events = [{
        "type": "cards_action_card_discarded",
        "seat": seat,
        "card_id": card_id,
        "remaining_discards": resolution["remaining_discards"],
    }]
    return _complete_cards_resolution(engine, next_state, seat, events)


def _snap(
    engine: SemanticEngine, state: dict[str, Any], seat: int, card_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    execution, resolution = _cards_context(state, seat)
    if resolution is not None:
        raise SemanticRuleError("Snap must be selected before a draw resolution starts")
    next_state, events = _advance_break(engine, state, seat, execution["spec"]["break_steps"])
    _ensure_action_display_positions(next_state)
    card, position = _remove_card(next_state["card_display"], card_id, "display")
    position = next_state["turn"]["action_session"]["cards_display_position_by_id"][card_id]
    next_state["players"][seat]["hand"].append(card)
    next_state = _ensure_display_refill_deferred(next_state, seat)
    completed, completion_events = complete_action_execution(engine, next_state, seat, {
        "performed": True,
        "mode": "snap",
        "card_id": card_id,
        "display_position": position + 1,
    })
    return completed, [*events, {
        "type": "cards_action_card_snapped", "seat": seat,
        "card_id": card_id, "display_position": position + 1,
    }, *completion_events]


def _complete_cards_resolution(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    events: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolution = deepcopy(state["turn"]["action_session"]["cards_resolution"])
    next_state = clone_state(state)
    del next_state["turn"]["action_session"]["cards_resolution"]
    if resolution["display_changed"]:
        next_state = _ensure_display_refill_deferred(next_state, seat)
    completed, completion_events = complete_action_execution(engine, next_state, seat, {
        "performed": True,
        "mode": "draw",
        "drawn_card_ids": resolution["drawn_card_ids"],
        "discarded_card_ids": resolution["discarded_card_ids"],
    })
    return completed, [*events, *completion_events]


def _advance_break(
    engine: SemanticEngine, state: dict[str, Any], seat: int, amount: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if state["break"]["mode"] == "solo_round":
        return clone_state(state), [{
            "type": "cards_break_advance_skipped_in_solo", "seat": seat, "amount": amount,
        }]
    return engine.start_effects(state, seat, [{
        "op": "advance_break", "timing": "immediate", "args": {"amount": amount},
    }], source_id="action:cards")


def _ensure_display_refill_deferred(state: dict[str, Any], seat: int) -> dict[str, Any]:
    session = state["turn"]["action_session"]
    if any(effect.get("op") == "refill_card_display" for effect in session["after_finishing_effects"]):
        return state
    return defer_after_finishing(state, seat, [_DISPLAY_REFILL_EFFECT])


def _ensure_action_display_positions(state: dict[str, Any]) -> None:
    session = state["turn"]["action_session"]
    if "cards_display_position_by_id" in session:
        return
    session["cards_display_position_by_id"] = {
        card_id: index for index, card_id in enumerate(
            _unique_card_ids(state["card_display"], "display")
        )
    }


def _available_draw_count(state: Mapping[str, Any], seat: int, upgraded: bool) -> int:
    count = len(state["zoo_deck"]) + len(state["zoo_discard"])
    if upgraded:
        limit = reputation_display_limit(state["players"][seat]["tracks"]["reputation"])
        positions = state["turn"]["action_session"].get("cards_display_position_by_id")
        if positions is None:
            count += min(limit, len(state["card_display"]))
        else:
            count += sum(
                positions.get(card.get("id"), 99) < limit for card in state["card_display"]
            )
    return count


def _unique_card_ids(cards: list[Any], label: str) -> list[str]:
    ids = [card.get("id") if isinstance(card, Mapping) else None for card in cards]
    if any(not isinstance(card_id, str) or not card_id for card_id in ids):
        raise SemanticRuleError(f"{label} cards require stable IDs")
    if len(ids) != len(set(ids)):
        raise SemanticRuleError(f"{label} card IDs must be unique")
    return ids


def _remove_card(cards: list[Any], card_id: str, label: str) -> tuple[dict[str, Any], int]:
    _unique_card_ids(cards, label)
    for index, card in enumerate(cards):
        if card["id"] == card_id:
            return cards.pop(index), index
    raise SemanticRuleError(f"unknown {label} card: {card_id}")


def _recycle_discard_if_needed(state: dict[str, Any]) -> bool:
    if state["zoo_deck"]:
        return False
    cards = state["zoo_discard"]
    if not cards:
        raise SemanticRuleError("the Zoo deck and discard pile are empty")
    seed = f"{state['seed']}:cards:{state['turn']['number']}:{len(cards)}"
    random.Random(seed).shuffle(cards)
    state["zoo_deck"] = cards
    state["zoo_discard"] = []
    return True
