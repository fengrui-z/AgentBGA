"""Official action-card turn envelope for the staged Ark Nova engine.

This module owns the cross-action rules: slots, locked strength, X-token
allocation, Multiplier/Venom/Constriction tokens, card movement, and the
after-finishing boundary.  Action-specific modules consume the immutable
execution specification instead of re-deriving those rules.
"""

from __future__ import annotations

from copy import deepcopy
from itertools import product
from typing import Any, Mapping, Sequence

from .semantics import (
    SemanticEngine, SemanticRuleError, settle_turn_venom, simultaneous_effects,
)
from .state import ACTION_TYPES, clone_state, validate_semantic_state


ACTION_TOKEN_TYPES = frozenset({"multiplier", "venom", "constriction"})
ASSOCIATION_TASKS = (
    {"id": "gain-reputation", "strength": 2, "workers": 1},
    {"id": "partner-zoo", "strength": 3, "workers": 1},
    {"id": "university", "strength": 4, "workers": 1},
    {"id": "conservation-project", "strength": 5, "workers": 1},
)
CARDS_TABLES = {
    False: ((1, 1), (1, 0), (2, 1), (2, 0), (3, 1)),
    True: ((1, 0), (2, 1), (2, 0), (3, 1), (4, 1)),
}
ANIMALS_CARD_LIMITS = (0, 1, 1, 1, 2)
ANIMALS_CARD_LIMITS_UPGRADED = (1, 1, 2, 2, 2)


def _token_type(token: Any) -> str | None:
    if isinstance(token, str):
        return token
    if isinstance(token, Mapping):
        value = token.get("type")
        return value if isinstance(value, str) else None
    return None


def _count_token(card: Mapping[str, Any], token_type: str) -> int:
    return sum(_token_type(token) == token_type for token in card.get("tokens", []))


def _remove_tokens(card: dict[str, Any], token_type: str, count: int | None = None) -> int:
    removed = 0
    kept = []
    for token in card["tokens"]:
        if _token_type(token) == token_type and (count is None or removed < count):
            removed += 1
        else:
            kept.append(token)
    card["tokens"] = kept
    return removed


def _action_card(state: Mapping[str, Any], seat: int, card_id: str) -> Mapping[str, Any]:
    for card in state["players"][seat]["action_cards"]:
        if card.get("id") == card_id:
            return card
    raise SemanticRuleError(f"unknown action card: {card_id}")


def _require_turn_start(state: Mapping[str, Any], seat: int) -> None:
    if not isinstance(seat, int) or isinstance(seat, bool) or not 0 <= seat < state["player_count"]:
        raise SemanticRuleError("action seat is out of range")
    if state["active_seat"] != seat:
        raise SemanticRuleError("only the active player may start an action")
    if state["phase"] != "active":
        raise SemanticRuleError("an action may only start during the active phase")
    if state["turn"]["action_session"] is not None:
        raise SemanticRuleError("another action session is already in progress")
    resolution = state["resolution"]
    if resolution["queue"] or resolution["pending_choice"] is not None:
        raise SemanticRuleError("semantic effects must finish before an action starts")


def _x_allocations(executions: int, available: int) -> list[tuple[int, ...]]:
    return [
        allocation
        for allocation in product(range(available + 1), repeat=executions)
        if sum(allocation) <= available
    ]


def legal_action_starts(state: Mapping[str, Any], seat: int) -> list[dict[str, Any]]:
    """Enumerate the concrete cross-action start parameters visible to a seat.

    These are envelope-level candidates.  A runnable plugin must intersect them
    with the action-specific legal choices so that an execution cannot be empty.
    """
    try:
        _require_turn_start(state, seat)
    except SemanticRuleError:
        return []
    player = state["players"][seat]
    hypnosis = state["turn"].get("hypnosis_action")
    if hypnosis is not None:
        card = next(
            item for item in player["action_cards"]
            if item["action"] == hypnosis["action"]
        )
        base_strength = hypnosis["position"] - (2 if hypnosis["constricted"] else 0)
        result = []
        for x_tokens in range(player["x_tokens"] + 1):
            strength = base_strength + x_tokens
            if strength < 1 or not _inherent_execution_available(
                card["action"], strength, hypnosis["upgraded"],
            ):
                continue
            action = {
                "type": "start_action", "action_card_id": card["id"],
                "x_by_execution": [x_tokens], "multiplier_tokens": 0,
            }
            result.append({
                "id": f"hypnosis:{card['id']}:x{x_tokens}",
                "label": f"Hypnosis {card['action']} · {strength}",
                "action": action,
                "execution_spec": action_execution_spec(
                    card["action"], hypnosis["upgraded"], strength,
                ),
            })
        return result
    extra_action = state["turn"].get("extra_action")
    excluded_action = extra_action.get("excluded_action") if extra_action is not None else None
    fixed_action = extra_action.get("action") if extra_action is not None else None
    result: list[dict[str, Any]] = []
    for card in sorted(player["action_cards"], key=lambda item: item["position"]):
        if card["action"] == excluded_action:
            continue
        if fixed_action is not None and card["action"] != fixed_action:
            continue
        multiplier_count = _count_token(card, "multiplier")
        if not _can_reserve_venom(player, card, state["turn"]):
            continue
        constricted = bool(_count_token(card, "constriction"))
        base_strength = card["position"] - (2 if constricted else 0)
        for used_multiplier in range(multiplier_count + 1):
            executions = 1 + used_multiplier
            for allocation in _x_allocations(executions, player["x_tokens"]):
                strengths = [base_strength + amount for amount in allocation]
                if min(strengths) < 1:
                    continue
                if any(not _inherent_execution_available(
                    card["action"], strength, bool(card["upgraded"]),
                ) for strength in strengths):
                    continue
                allocation_id = "-".join(str(value) for value in allocation)
                action = {
                    "type": "start_action",
                    "action_card_id": card["id"],
                    "x_by_execution": list(allocation),
                    "multiplier_tokens": used_multiplier,
                }
                result.append({
                    "id": f"start:{card['id']}:m{used_multiplier}:x{allocation_id}",
                    "label": f"{card['action']} · {strengths}",
                    "action": action,
                    "execution_spec": action_execution_spec(
                        card["action"], bool(card["upgraded"]), strengths[0],
                    ),
                })
        if player["x_tokens"] < 5:
            result.append({
                "id": f"take-x:{card['id']}",
                "label": f"Take 1 X-token with {card['action']}",
                "action": {"type": "take_x_token_action", "action_card_id": card["id"]},
            })
    return result


def start_action(
    state: dict[str, Any],
    seat: int,
    action_card_id: str,
    *,
    x_by_execution: Sequence[int] = (0,),
    multiplier_tokens: int = 0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Lock one regular action before any of its effects are executed."""
    _require_turn_start(state, seat)
    if not isinstance(multiplier_tokens, int) or isinstance(multiplier_tokens, bool) or multiplier_tokens < 0:
        raise SemanticRuleError("multiplier token count must be a non-negative integer")
    card = _action_card(state, seat, action_card_id)
    extra_action = state["turn"].get("extra_action")
    hypnosis = state["turn"].get("hypnosis_action")
    if hypnosis is not None:
        if card["action"] != hypnosis["action"]:
            raise SemanticRuleError("Hypnosis must use the copied action type")
        if multiplier_tokens != 0 or len(x_by_execution) != 1:
            raise SemanticRuleError("Hypnosis cannot use a Multiplier")
    if extra_action is not None and card["action"] == extra_action.get("excluded_action"):
        raise SemanticRuleError("the extra action must use a different Action card")
    if extra_action is not None and (
        extra_action.get("action") is not None
        and card["action"] != extra_action["action"]
    ):
        raise SemanticRuleError("the extra action must use the specified Action card")
    available_multiplier = 0 if hypnosis is not None else _count_token(card, "multiplier")
    if multiplier_tokens > available_multiplier:
        raise SemanticRuleError("action card does not have that many multiplier tokens")
    executions = 1 + multiplier_tokens
    allocation = list(x_by_execution)
    if len(allocation) != executions:
        raise SemanticRuleError("X-token allocation must contain one amount per execution")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in allocation):
        raise SemanticRuleError("X-token allocation must contain non-negative integers")
    if sum(allocation) > state["players"][seat]["x_tokens"]:
        raise SemanticRuleError("player does not have enough X-tokens")
    constricted = (
        bool(hypnosis["constricted"]) if hypnosis is not None
        else bool(_count_token(card, "constriction"))
    )
    position_locked = int(hypnosis["position"]) if hypnosis is not None else int(card["position"])
    upgraded_locked = bool(hypnosis["upgraded"]) if hypnosis is not None else bool(card["upgraded"])
    base_strength = position_locked - (2 if constricted else 0)
    strengths = [base_strength + amount for amount in allocation]
    if min(strengths) < 1:
        raise SemanticRuleError("Constriction requires enough X-tokens to reach strength one")
    if any(not _inherent_execution_available(
        card["action"], strength, upgraded_locked,
    ) for strength in strengths):
        raise SemanticRuleError("the locked strength cannot perform this action")

    next_state = clone_state(state)
    is_hypnosis_action = hypnosis is not None
    is_extra_action = extra_action is not None or is_hypnosis_action
    next_state["turn"]["extra_action"] = None
    next_state["turn"]["hypnosis_action"] = None
    next_player = next_state["players"][seat]
    _reserve_venom_payment(next_state, seat, next_player, card)
    next_player["x_tokens"] -= sum(allocation)
    next_state["phase"] = "action"
    next_state["turn"]["action_session"] = {
        "seat": seat,
        "kind": "regular",
        "action_card_id": card["id"],
        "action": card["action"],
        "position_locked": position_locked,
        "upgraded_locked": upgraded_locked,
        "constricted": constricted,
        "venom_selected": (
            bool(hypnosis["venom"]) if hypnosis is not None
            else bool(_count_token(card, "venom"))
        ),
        "multiplier_tokens_used": multiplier_tokens,
        "x_by_execution": allocation,
        "strengths": strengths,
        "current_execution": 0,
        "executions": [],
        "after_finishing_effects": [],
        "is_extra_action": is_extra_action,
        "is_hypnosis_action": is_hypnosis_action,
        "hypnosis_target_seat": None if hypnosis is None else hypnosis["target_seat"],
        "hypnosis_target_action_card_id": (
            None if hypnosis is None else hypnosis["target_action_card_id"]
        ),
    }
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "action_started",
        "seat": seat,
        "action": card["action"],
        "action_card_id": card["id"],
        "position": position_locked,
        "strengths": strengths,
        "x_spent": sum(allocation),
        "multiplier_tokens": multiplier_tokens,
        "upgraded": upgraded_locked,
        "constricted": constricted,
    }]


def current_action_execution(state: Mapping[str, Any], seat: int) -> dict[str, Any]:
    session = state["turn"].get("action_session")
    if session is None or session.get("seat") != seat or session.get("kind") != "regular":
        raise SemanticRuleError("there is no regular action execution for this seat")
    index = session["current_execution"]
    return {
        "index": index,
        "number": index + 1,
        "total": len(session["strengths"]),
        "action": session["action"],
        "strength": session["strengths"][index],
        "upgraded": session["upgraded_locked"],
        "spec": action_execution_spec(
            session["action"], session["upgraded_locked"], session["strengths"][index],
        ),
    }


def defer_after_finishing(
    state: dict[str, Any], seat: int, effects: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Append effects that must wait until the selected Action card reaches slot 1."""
    next_state = clone_state(state)
    session = next_state["turn"].get("action_session")
    if session is None or session.get("seat") != seat or session.get("kind") != "regular":
        raise SemanticRuleError("after-finishing effects require an active regular action")
    for effect in effects:
        if not isinstance(effect, Mapping):
            raise SemanticRuleError("after-finishing effects must be operation objects")
        session["after_finishing_effects"].append(deepcopy(dict(effect)))
    validate_semantic_state(next_state)
    return next_state


def complete_action_execution(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    summary: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Record one non-empty execution and advance or finish the action session."""
    session = state["turn"].get("action_session")
    if session is None or session.get("seat") != seat or session.get("kind") != "regular":
        raise SemanticRuleError("there is no regular action execution for this seat")
    if not isinstance(summary, Mapping) or summary.get("performed") is not True:
        raise SemanticRuleError("an Ark Nova action execution may not do nothing")
    next_state = clone_state(state)
    next_session = next_state["turn"]["action_session"]
    index = next_session["current_execution"]
    recorded = deepcopy(dict(summary))
    recorded["execution"] = index + 1
    recorded["strength"] = next_session["strengths"][index]
    next_session["executions"].append(recorded)
    events = [{
        "type": "action_execution_completed",
        "seat": seat,
        "action": next_session["action"],
        "execution": index + 1,
        "total": len(next_session["strengths"]),
        "summary": recorded,
    }]
    if index + 1 < len(next_session["strengths"]):
        next_session["current_execution"] += 1
        events.append({
            "type": "action_execution_started",
            "seat": seat,
            "action": next_session["action"],
            "execution": next_session["current_execution"] + 1,
            "strength": next_session["strengths"][next_session["current_execution"]],
        })
        validate_semantic_state(next_state)
        return next_state, events
    finished, finish_events = _finish_regular_action(engine, next_state, seat)
    return finished, [*events, *finish_events]


def take_x_token_action(
    state: dict[str, Any], seat: int, action_card_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Perform the official alternative action, independent of slot strength."""
    _require_turn_start(state, seat)
    player = state["players"][seat]
    if player["x_tokens"] >= 5:
        raise SemanticRuleError("a player with five X-tokens cannot take the alternative action")
    selected = _action_card(state, seat, action_card_id)
    extra_action = state["turn"].get("extra_action")
    if extra_action is not None and selected["action"] == extra_action.get("excluded_action"):
        raise SemanticRuleError("the extra action must use a different Action card")
    next_state = clone_state(state)
    is_extra_action = extra_action is not None
    next_state["turn"]["extra_action"] = None
    next_card = _action_card(next_state, seat, action_card_id)
    _reserve_venom_payment(next_state, seat, next_state["players"][seat], next_card)
    venom_selected = bool(_count_token(next_card, "venom"))
    removed = {
        "venom": _remove_tokens(next_card, "venom"),
        "constriction": _remove_tokens(next_card, "constriction"),
        "multiplier": 0,
    }
    if removed["venom"]:
        next_state["turn"]["venom_removed_this_turn"] = True
    settle_turn_venom(next_state, seat)
    old_position = _move_action_card(next_state, seat, action_card_id)
    next_state["players"][seat]["x_tokens"] += 1
    _finish_turn_state(next_state, seat, {
        "kind": "take_x_token",
        "extra_action": is_extra_action,
        "action_card_id": action_card_id,
        "action": selected["action"],
        "position": old_position,
    }, increment_turn=not is_extra_action)
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "x_token_action_completed",
        "seat": seat,
        "action_card_id": action_card_id,
        "position": old_position,
        "tokens_removed": removed,
        "x_tokens": next_state["players"][seat]["x_tokens"],
    }, _turn_finished_event(next_state, seat)]


def decline_unavailable_hypnosis_action(
    state: dict[str, Any], seat: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Close a mandatory Hypnosis window when the copied action has no legal execution.

    The unified domain router exposes this only after every strength/X-token
    candidate has been checked against the concrete action domain.  It prevents
    a stale or unusable copied card from trapping a human player.
    """
    _require_turn_start(state, seat)
    hypnosis = state["turn"].get("hypnosis_action")
    if hypnosis is None:
        raise SemanticRuleError("there is no unavailable Hypnosis action to close")
    next_state = clone_state(state)
    next_state["turn"]["hypnosis_action"] = None
    next_state["turn"]["history"].append({
        "kind": "hypnosis_unavailable", "extra_action": True,
        "action": hypnosis["action"], "target_seat": hypnosis["target_seat"],
    })
    venom = settle_turn_venom(next_state, seat)
    _activate_next_or_break(next_state, seat)
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "hypnosis_action_unavailable", "seat": seat,
        "target_seat": hypnosis["target_seat"], "action": hypnosis["action"],
    }, {**_turn_finished_event(next_state, seat), "venom": venom}]


def _finish_regular_action(
    engine: SemanticEngine, state: dict[str, Any], seat: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    session = deepcopy(state["turn"]["action_session"])
    card = _action_card(state, seat, session["action_card_id"])
    if session.get("is_hypnosis_action"):
        target_card = _action_card(
            state, session["hypnosis_target_seat"],
            session["hypnosis_target_action_card_id"],
        )
        removed = {
            "venom": _remove_tokens(target_card, "venom"),
            "constriction": _remove_tokens(target_card, "constriction"),
            "multiplier": 0,
        }
    else:
        removed = {
            "venom": _remove_tokens(card, "venom"),
            "constriction": _remove_tokens(card, "constriction"),
            "multiplier": _remove_tokens(card, "multiplier", session["multiplier_tokens_used"]),
        }
    if removed["venom"]:
        state["turn"]["venom_removed_this_turn"] = True
    old_position = _move_action_card(state, seat, session["action_card_id"])
    history = {
        "kind": "regular",
        "extra_action": bool(session.get("is_extra_action")),
        "action_card_id": session["action_card_id"],
        "action": session["action"],
        "position": old_position,
        "strengths": session["strengths"],
        "executions": session["executions"],
        "hypnosis_target_seat": session.get("hypnosis_target_seat"),
    }
    after_effects = session["after_finishing_effects"]
    state["turn"]["action_session"] = None
    if not session.get("is_extra_action"):
        state["turn"]["number"] += 1
    state["turn"]["history"].append(history)
    events = [{
        "type": "action_finished",
        "seat": seat,
        "action": session["action"],
        "action_card_id": session["action_card_id"],
        "moved_from": old_position,
        "moved_to": 1,
        "tokens_removed": removed,
    }]
    if after_effects:
        state["phase"] = "after_finishing"
        resolved, semantic_events = engine.start_effects(
            state,
            seat,
            simultaneous_effects(
                after_effects,
                label="Order after-finishing effects",
                timing="after_finishing",
            ),
            source_id=f"action:{session['action']}:after-finishing",
            completion={"type": "finish_turn", "seat": seat},
        )
        return resolved, [*events, *semantic_events]
    venom = settle_turn_venom(state, seat)
    _activate_next_or_break(state, seat)
    validate_semantic_state(state)
    return state, [*events, {**_turn_finished_event(state, seat), "venom": venom}]


def _can_reserve_venom(
    player: Mapping[str, Any], selected: Mapping[str, Any], turn: Mapping[str, Any],
) -> bool:
    if (
        turn.get("venom_removed_this_turn")
        or turn.get("venom_reserved_money") == 2
        or _count_token(selected, "venom")
    ):
        return True
    venom_remains = any(_count_token(card, "venom") for card in player["action_cards"])
    return not venom_remains or player["money"] >= 2


def _reserve_venom_payment(
    state: dict[str, Any], seat: int, player: dict[str, Any], selected: Mapping[str, Any],
) -> None:
    turn = state["turn"]
    if (
        turn.get("venom_removed_this_turn")
        or turn.get("venom_reserved_money") == 2
        or _count_token(selected, "venom")
    ):
        return
    if not any(_count_token(card, "venom") for card in player["action_cards"]):
        return
    if player["money"] < 2:
        raise SemanticRuleError("the Venom payment must remain affordable for this turn")
    player["money"] -= 2
    turn["venom_reserved_money"] = 2


def _move_action_card(state: dict[str, Any], seat: int, action_card_id: str) -> int:
    player = state["players"][seat]
    selected = _action_card(state, seat, action_card_id)
    old_position = int(selected["position"])
    for card in player["action_cards"]:
        if int(card["position"]) < old_position:
            card["position"] += 1
    selected["position"] = 1
    return old_position


def _finish_turn_state(
    state: dict[str, Any], seat: int, history: Mapping[str, Any], *, increment_turn: bool = True,
) -> None:
    if increment_turn:
        state["turn"]["number"] += 1
    state["turn"]["history"].append(deepcopy(dict(history)))
    _activate_next_or_break(state, seat)


def _activate_next_or_break(state: dict[str, Any], seat: int) -> None:
    if state["break"]["pending"]:
        state["phase"] = "break_pending"
        state["active_seat"] = seat
    else:
        state["phase"] = "active"
        state["active_seat"] = (seat + 1) % state["player_count"]


def _turn_finished_event(state: Mapping[str, Any], seat: int) -> dict[str, Any]:
    return {
        "type": "turn_finished",
        "seat": seat,
        "turn": state["turn"]["number"],
        "next_seat": state["active_seat"],
        "break_pending": bool(state["break"]["pending"]),
    }


def action_execution_spec(action: str, upgraded: bool, strength: int) -> dict[str, Any]:
    """Return a compact, UI-readable contract for one locked execution.

    The contract contains only rules that are independent of map geometry and
    card content.  Detailed card/building choices remain authoritative in their
    action-domain resolvers.
    """
    if action not in ACTION_TYPES:
        raise SemanticRuleError(f"unknown Ark Nova action type: {action}")
    if not isinstance(strength, int) or isinstance(strength, bool) or strength < 1:
        raise SemanticRuleError("action strength must be a positive integer")
    common = {"action": action, "side": "II" if upgraded else "I", "strength": strength}
    if action == "cards":
        draw_count, discard_count = CARDS_TABLES[bool(upgraded)][min(strength, 5) - 1]
        return {
            **common,
            "break_steps": 2,
            "modes": ["draw", "snap"] if strength >= (3 if upgraded else 5) else ["draw"],
            "draw_count": draw_count,
            "discard_count": discard_count,
            "draw_sources": "deck_or_within_reputation" if upgraded else "deck_only",
            "snap_source": "any_display_card",
            "defer_display_refill": True,
        }
    if action == "build":
        return {
            **common,
            "maximum_total_size": strength,
            "maximum_buildings": None if upgraded else 1,
            "buildings_must_be_different": bool(upgraded),
            "building_types": [
                "kiosk", "pavilion", "standard_enclosure", "petting_zoo",
                *(["reptile_house", "large_bird_aviary"] if upgraded else []),
            ],
            "cost_per_space": 2,
            "may_move_animals_into_new_special_enclosure": bool(upgraded),
        }
    if action == "animals":
        limits = ANIMALS_CARD_LIMITS_UPGRADED if upgraded else ANIMALS_CARD_LIMITS
        return {
            **common,
            "mode": "play_animals",
            "maximum_cards": limits[min(strength, 5) - 1],
            "display_sources": "within_reputation" if upgraded else "hand_only",
            "display_surcharge": "folder_number" if upgraded else None,
            "reputation_before_play": 1 if upgraded and strength >= 5 else 0,
            "requires_nonempty_execution": True,
        }
    if action == "association":
        available_tasks = [
            deepcopy(task) for task in ASSOCIATION_TASKS if task["strength"] <= strength
        ]
        return {
            **common,
            "tasks": available_tasks,
            "maximum_tasks": None if upgraded else 1,
            "tasks_must_be_different": bool(upgraded),
            "maximum_total_strength": strength,
            "donation_allowed": bool(upgraded),
            "new_project_sources": (
                "hand_or_within_reputation" if upgraded else "hand_only"
            ),
            "display_project_surcharge": "folder_number" if upgraded else None,
        }
    return {
        **common,
        "modes": ["play_sponsors", "advance_break"],
        "maximum_level_total": strength + (1 if upgraded else 0),
        "maximum_cards": None if upgraded else 1,
        "display_sources": "within_reputation" if upgraded else "hand_only",
        "display_surcharge": "folder_number" if upgraded else None,
        "break_steps": strength,
        "break_money": strength * (2 if upgraded else 1),
    }


def _inherent_execution_available(action: str, strength: int, upgraded: bool = False) -> bool:
    if action == "animals":
        limits = ANIMALS_CARD_LIMITS_UPGRADED if upgraded else ANIMALS_CARD_LIMITS
        return limits[min(strength, 5) - 1] > 0
    if action == "association":
        return strength >= min(task["strength"] for task in ASSOCIATION_TASKS)
    return True
