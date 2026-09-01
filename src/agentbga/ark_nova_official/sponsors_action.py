"""Concrete resolver for Sponsors I/II play and Break branches."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .actions import complete_action_execution, current_action_execution, defer_after_finishing
from .build_action import legal_unique_building_placements, place_unique_building
from .cards import entry_is_eligible, play_entry_semantics
from .cards_action import reputation_display_limit
from .content import ContentEntry
from .semantics import SemanticEngine, SemanticRuleError
from .state import clone_state, validate_semantic_state


_DISPLAY_REFILL_EFFECT = {
    "op": "refill_card_display", "timing": "after_finishing", "args": {"target_size": 6},
}


def legal_sponsors_execution_actions(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    entries: Mapping[str, ContentEntry],
) -> list[dict[str, Any]]:
    """Enumerate sponsor cards, the Break alternative, and finish."""
    try:
        execution, resolution = _sponsors_context(state, seat)
    except SemanticRuleError:
        return []
    if state["resolution"]["queue"] or state["resolution"]["pending_choice"] is not None:
        return []
    if resolution is None:
        result = [_candidate_action(candidate) for candidate in _candidate_cards(
            engine, state, seat, entries, execution,
        )]
        result.append({
            "id": "sponsors:advance-break",
            "label": (
                f"Advance Break {execution['spec']['break_steps']} and gain "
                f"{execution['spec']['break_money']} money"
            ),
            "action": {"type": "advance_sponsors_break"},
        })
        return result
    selected = resolution.get("selected")
    if selected is not None:
        entry = entries.get(selected.get("entry_id"))
        if entry is None:
            raise SemanticRuleError("selected unique Sponsor entry is unavailable")
        placements = legal_unique_building_placements(
            state["players"][seat], entry.facts["unique_building"],
        )
        return [_unique_placement_action(action) for action in placements]
    result = [_candidate_action(candidate) for candidate in _candidate_cards(
        engine, state, seat, entries, execution,
    )]
    if resolution["played"]:
        result.append({
            "id": "sponsors:finish", "label": "Finish Sponsors action",
            "action": {"type": "finish_sponsors_action"},
        })
    return result


def apply_sponsors_execution_action(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    entries: Mapping[str, ContentEntry],
    action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(action, Mapping) or not isinstance(action.get("type"), str):
        raise SemanticRuleError("Sponsors execution action must contain a type")
    requested = dict(action)
    legal = [
        item["action"] for item in legal_sponsors_execution_actions(
            engine, state, seat, entries,
        )
    ]
    if requested not in legal:
        raise SemanticRuleError("Sponsors execution choice is not currently legal")
    if requested["type"] == "play_sponsor_card":
        return _play_sponsor(engine, state, seat, entries, requested)
    if requested["type"] == "place_unique_sponsor_building":
        return _place_unique_sponsor(engine, state, seat, entries, requested)
    if requested["type"] == "advance_sponsors_break":
        return _advance_break_branch(engine, state, seat)
    if requested["type"] == "finish_sponsors_action":
        return _finish_sponsors(engine, state, seat)
    raise SemanticRuleError(f"unknown Sponsors action: {requested['type']}")


def legal_bonus_sponsor_actions(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    entries: Mapping[str, ContentEntry],
) -> list[dict[str, Any]]:
    """Enumerate the optional Okapi Stable Sponsor-play interrupt."""
    window = state["turn"].get("bonus_sponsor_play")
    if (
        not isinstance(window, Mapping) or window.get("seat") != seat
        or state["resolution"]["queue"]
        or state["resolution"]["pending_choice"] is not None
    ):
        return []
    selected = window.get("selected")
    if isinstance(selected, Mapping):
        entry = entries.get(selected.get("entry_id"))
        if entry is None or not isinstance(entry.facts.get("unique_building"), Mapping):
            raise SemanticRuleError("bonus unique Sponsor selection is invalid")
        return [{
            **_unique_placement_action(action),
            "action": {**deepcopy(dict(action)), "type": "place_bonus_sponsor_building"},
        } for action in legal_unique_building_placements(
            state["players"][seat], entry.facts["unique_building"],
        )]
    result = []
    player = state["players"][seat]
    for card in player["hand"]:
        entry_id = card.get("entry_id", card.get("id"))
        entry = entries.get(entry_id) if isinstance(entry_id, str) else None
        if entry is None or entry.kind != "sponsor":
            continue
        if entry.facts.get("semantic_compile_status") not in {None, "compiled"}:
            continue
        level = int(entry.facts.get("level", 0))
        if level > player["money"] or not entry_is_eligible(engine, state, seat, entry):
            continue
        unique_rules = entry.facts.get("unique_building")
        if unique_rules and not legal_unique_building_placements(player, unique_rules):
            continue
        instance_id = _instance_id(card)
        result.append({
            "id": f"okapi:play:{instance_id}",
            "label": f"Play {entry.display_title} for {level} money",
            "action": {"type": "play_bonus_sponsor_card", "instance_id": instance_id},
        })
    result.append({
        "id": "okapi:decline", "label": "Do not use this Okapi Stable token",
        "action": {"type": "decline_bonus_sponsor_play"},
    })
    return result


def apply_bonus_sponsor_action(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    entries: Mapping[str, ContentEntry],
    action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    requested = dict(action)
    if requested not in [
        item["action"] for item in legal_bonus_sponsor_actions(
            engine, state, seat, entries,
        )
    ]:
        raise SemanticRuleError("bonus Sponsor choice is not currently legal")
    if requested["type"] == "decline_bonus_sponsor_play":
        next_state = clone_state(state)
        remaining = _advance_bonus_sponsor_window(next_state)
        validate_semantic_state(next_state)
        return next_state, [{
            "type": "bonus_sponsor_play_declined", "seat": seat,
            "remaining_triggers": remaining,
        }]
    if requested["type"] == "play_bonus_sponsor_card":
        next_state = clone_state(state)
        card = _find_zone_card(next_state, seat, "hand", requested["instance_id"])
        entry = _entry_for_card(entries, card)
        level = int(entry.facts.get("level", 0))
        if entry.facts.get("unique_building"):
            next_state["turn"]["bonus_sponsor_play"]["selected"] = {
                "instance_id": requested["instance_id"], "entry_id": entry.id,
                "level": level,
            }
            validate_semantic_state(next_state)
            return next_state, [{
                "type": "bonus_unique_sponsor_selected", "seat": seat,
                "instance_id": requested["instance_id"], "entry_id": entry.id,
            }]
        _pay_and_remove_bonus_sponsor(next_state, seat, card, level)
        remaining = _advance_bonus_sponsor_window(next_state)
        next_state, semantic_events = play_entry_semantics(
            engine, next_state, seat, entry, instance_id=requested["instance_id"],
        )
        return next_state, [{
            "type": "bonus_sponsor_played", "seat": seat,
            "instance_id": requested["instance_id"], "entry_id": entry.id,
            "money_spent": level, "remaining_triggers": remaining,
        }, *semantic_events]
    if requested["type"] == "place_bonus_sponsor_building":
        window = state["turn"]["bonus_sponsor_play"]
        selected = window.get("selected")
        if not isinstance(selected, Mapping):
            raise SemanticRuleError("no bonus unique Sponsor is selected")
        entry = entries.get(selected.get("entry_id"))
        if entry is None:
            raise SemanticRuleError("bonus unique Sponsor entry is unavailable")
        next_state, map_effects, pending_rewards = place_unique_building(
            state, seat, {**requested, "type": "place_unique_sponsor_building"},
        )
        card = _find_zone_card(
            next_state, seat, "hand", str(selected.get("instance_id")),
        )
        level = int(selected.get("level", 0))
        _pay_and_remove_bonus_sponsor(next_state, seat, card, level)
        remaining = _advance_bonus_sponsor_window(next_state)
        _queue_unique_map_rewards(next_state, seat, map_effects, pending_rewards)
        next_state, semantic_events = play_entry_semantics(
            engine, next_state, seat, entry,
            instance_id=str(selected.get("instance_id")),
            additional_effects=map_effects,
        )
        building = next_state["players"][seat]["map"]["buildings"][-1]
        return next_state, [{
            "type": "bonus_unique_sponsor_played", "seat": seat,
            "instance_id": selected.get("instance_id"), "entry_id": entry.id,
            "building": deepcopy(building), "money_spent": level,
            "remaining_triggers": remaining,
        }, *semantic_events]
    raise SemanticRuleError(f"unknown bonus Sponsor action: {requested['type']}")


def _pay_and_remove_bonus_sponsor(
    state: dict[str, Any], seat: int, card: Mapping[str, Any], level: int,
) -> None:
    player = state["players"][seat]
    if player["money"] < level:
        raise SemanticRuleError("player cannot pay the bonus Sponsor level")
    source_id = state["turn"]["bonus_sponsor_play"]["source_instance_id"]
    source = next((
        played for played in player["played_cards"] if played.get("id") == source_id
    ), None)
    if source is None or int(source.get("stored_tokens", 0)) < 1:
        raise SemanticRuleError("Okapi Stable has no stored token to spend")
    source["stored_tokens"] -= 1
    player["money"] -= level
    player["hand"].remove(card)


def _advance_bonus_sponsor_window(state: dict[str, Any]) -> int:
    window = state["turn"].get("bonus_sponsor_play")
    if not isinstance(window, dict):
        raise SemanticRuleError("bonus Sponsor window is unavailable")
    remaining = int(window.get("remaining_triggers", 1)) - 1
    if remaining > 0:
        window["remaining_triggers"] = remaining
        window["selected"] = None
    else:
        state["turn"]["bonus_sponsor_play"] = None
    return max(0, remaining)


def _queue_unique_map_rewards(
    state: dict[str, Any], seat: int,
    effects: list[dict[str, Any]], rewards: list[dict[str, Any]],
) -> None:
    for reward in rewards:
        if reward["type"] == "take_card":
            effects.append({
                "op": "take_map_reward_card", "timing": "immediate", "args": {},
            })
        elif reward["type"] == "clever":
            operation = {
                "op": "reposition_action_card", "timing": "after_finishing",
                "args": {"target_slot": reward["target_strength"], "optional": False},
            }
            session = state["turn"].get("action_session")
            if session is not None and session.get("seat") == seat:
                session["after_finishing_effects"].append(operation)
            else:
                effects.append({**operation, "timing": "immediate"})
        else:
            raise SemanticRuleError("bonus unique Sponsor produced an unknown Map reward")


def _sponsors_context(
    state: Mapping[str, Any], seat: int,
) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    execution = current_action_execution(state, seat)
    if execution["action"] != "sponsors":
        raise SemanticRuleError("the active execution is not a Sponsors action")
    resolution = state["turn"]["action_session"].get("sponsors_resolution")
    if resolution is not None and not isinstance(resolution, Mapping):
        raise SemanticRuleError("invalid Sponsors action resolution state")
    return execution, resolution


def _candidate_cards(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    entries: Mapping[str, ContentEntry],
    execution: Mapping[str, Any],
) -> list[dict[str, Any]]:
    resolution = state["turn"]["action_session"].get("sponsors_resolution")
    budget = execution["spec"]["maximum_level_total"] if resolution is None else resolution["remaining_level"]
    if resolution is not None and execution["spec"]["maximum_cards"] is not None:
        if len(resolution["played"]) >= execution["spec"]["maximum_cards"]:
            return []
    player = state["players"][seat]
    candidates = [(card, "hand", None) for card in player["hand"]]
    if execution["upgraded"]:
        limit = reputation_display_limit(player["tracks"]["reputation"])
        positions = None if resolution is None else resolution["display_position_by_id"]
        for index, card in enumerate(state["card_display"]):
            position = index if positions is None else positions.get(_instance_id(card), 99)
            if position < limit:
                candidates.append((card, "display", position))
    result = []
    for card, source, display_position in candidates:
        entry_id = card.get("entry_id", card.get("id"))
        entry = entries.get(entry_id) if isinstance(entry_id, str) else None
        if entry is None:
            continue
        level = int(entry.facts.get("level", 0))
        folder_cost = 0 if display_position is None else int(display_position) + 1
        if entry.kind != "sponsor" or level > budget or folder_cost > player["money"]:
            continue
        compile_status = entry.facts.get("semantic_compile_status")
        if compile_status is not None and compile_status != "compiled":
            # Imported Sponsor cards advance from partial to compiled only when
            # every transcribed effect and printed prerequisite has executable
            # semantics.  Custom/test entries without this authoring marker are
            # unaffected.
            continue
        if not entry_is_eligible(engine, state, seat, entry):
            continue
        # These cards require a unique-map-building placement choice.  Their
        # fixed footprints are handled by the sponsor-effect batch rather than
        # silently treating the placement as completed.
        unique_rules = entry.facts.get("unique_building")
        if unique_rules and not legal_unique_building_placements(player, unique_rules):
            continue
        result.append({
            "instance_id": _instance_id(card), "entry": entry,
            "source": source, "level": level, "folder_cost": folder_cost,
        })
    return result


def _candidate_action(candidate: Mapping[str, Any]) -> dict[str, Any]:
    folder = int(candidate.get("folder_cost", 0))
    return {
        "id": f"sponsors:play:{candidate['instance_id']}",
        "label": (
            f"Play {candidate['entry'].display_title} from {candidate['source']} "
            f"(level {candidate['level']}"
            + (f", pay folder {folder}" if folder else "")
            + ")"
        ),
        "action": {
            "type": "play_sponsor_card", "instance_id": candidate["instance_id"],
            "source": candidate["source"],
        },
    }


def _unique_placement_action(action: Mapping[str, Any]) -> dict[str, Any]:
    anchor = action["anchor"]
    rewards = action.get("covered_rewards", [])
    reward_text = ""
    if rewards:
        shown = ", ".join(
            str(item.get("effect", {}).get("type", "reward"))
            + (
                f" +{item['effect']['amount']}"
                if isinstance(item.get("effect"), Mapping)
                and "amount" in item["effect"] else ""
            )
            for item in rewards if isinstance(item, Mapping)
        )
        reward_text = f" · covers {shown}"
    return {
        "id": (
            f"sponsors:unique:{action['building_type']}:r{action['rotation']}:"
            f"q{anchor['q']}:r{anchor['r']}"
        ),
        "label": (
            f"Place unique building at ({anchor['q']},{anchor['r']}) "
            f"rotation {action['rotation'] * 60}°{reward_text}"
        ),
        "action": deepcopy(dict(action)),
    }


def _play_sponsor(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    entries: Mapping[str, ContentEntry],
    action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    execution, old_resolution = _sponsors_context(state, seat)
    next_state = clone_state(state)
    if old_resolution is None:
        next_state["turn"]["action_session"]["sponsors_resolution"] = {
            "remaining_level": execution["spec"]["maximum_level_total"],
            "played": [],
            "selected": None,
            "display_position_by_id": {
                card_id: index for index, card_id in enumerate(
                    _unique_instance_ids(next_state["card_display"], "display")
                )
            },
            "display_changed": False,
        }
    resolution = next_state["turn"]["action_session"]["sponsors_resolution"]
    card = _find_zone_card(next_state, seat, action["source"], action["instance_id"])
    entry = _entry_for_card(entries, card)
    level = int(entry.facts["level"])
    folder_cost = 0
    if action["source"] == "display":
        folder_cost = int(resolution["display_position_by_id"][_instance_id(card)]) + 1
    if entry.facts.get("unique_building"):
        resolution["selected"] = {
            "instance_id": action["instance_id"], "entry_id": entry.id,
            "source": action["source"], "level": level,
            "folder_cost": folder_cost,
        }
        validate_semantic_state(next_state)
        return next_state, [{
            "type": "unique_sponsor_building_selected", "seat": seat,
            "instance_id": action["instance_id"], "entry_id": entry.id,
        }]
    _remove_zone_card(next_state, seat, action["source"], action["instance_id"])
    next_state["players"][seat]["money"] -= folder_cost
    resolution["remaining_level"] -= level
    resolution["played"].append({
        "instance_id": action["instance_id"], "entry_id": entry.id,
        "source": action["source"], "level": level,
        "folder_cost": folder_cost,
    })
    if action["source"] == "display":
        resolution["display_changed"] = True
        next_state = _defer_display_refill(next_state, seat)
    next_state, semantic_events = play_entry_semantics(
        engine, next_state, seat, entry, instance_id=action["instance_id"],
    )
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "sponsor_played", "seat": seat,
        "instance_id": action["instance_id"], "entry_id": entry.id,
        "source": action["source"], "level": level,
        "folder_cost": folder_cost,
        "remaining_level": resolution["remaining_level"],
    }, *semantic_events]


def _place_unique_sponsor(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    entries: Mapping[str, ContentEntry],
    action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _, resolution = _sponsors_context(state, seat)
    if resolution is None or not isinstance(resolution.get("selected"), Mapping):
        raise SemanticRuleError("no unique Sponsor building is selected")
    selected = dict(resolution["selected"])
    entry = entries.get(selected["entry_id"])
    if entry is None:
        raise SemanticRuleError("selected unique Sponsor entry is unavailable")
    legal = legal_unique_building_placements(
        state["players"][seat], entry.facts["unique_building"],
    )
    if dict(action) not in legal:
        raise SemanticRuleError("unique Sponsor building placement is no longer legal")

    next_state, map_effects, pending_rewards = place_unique_building(
        state, seat, action,
    )
    next_resolution = next_state["turn"]["action_session"]["sponsors_resolution"]
    card = _remove_zone_card(
        next_state, seat, selected["source"], selected["instance_id"],
    )
    if _entry_for_card(entries, card).id != entry.id:
        raise SemanticRuleError("selected unique Sponsor card changed before placement")
    next_resolution["remaining_level"] -= selected["level"]
    next_state["players"][seat]["money"] -= int(selected.get("folder_cost", 0))
    next_resolution["played"].append(deepcopy(selected))
    next_resolution["selected"] = None
    if selected["source"] == "display":
        next_resolution["display_changed"] = True
        next_state = _defer_display_refill(next_state, seat)
    for reward in pending_rewards:
        if reward["type"] == "take_card":
            map_effects.append({
                "op": "take_map_reward_card", "timing": "immediate", "args": {},
            })
        elif reward["type"] == "clever":
            next_state = defer_after_finishing(next_state, seat, [{
                "op": "reposition_action_card", "timing": "after_finishing",
                "args": {
                    "target_slot": reward["target_strength"], "optional": False,
                },
            }])
        else:
            raise SemanticRuleError(f"unsupported unique-building map reward: {reward['type']}")
    next_state, semantic_events = play_entry_semantics(
        engine, next_state, seat, entry, instance_id=selected["instance_id"],
        additional_effects=map_effects,
    )
    validate_semantic_state(next_state)
    building = next_state["players"][seat]["map"]["buildings"][-1]
    remaining_level = next_state["turn"]["action_session"]["sponsors_resolution"][
        "remaining_level"
    ]
    return next_state, [{
        "type": "unique_sponsor_building_placed", "seat": seat,
        "entry_id": entry.id, "instance_id": selected["instance_id"],
        "building": deepcopy(building),
        "folder_cost": int(selected.get("folder_cost", 0)),
        "remaining_level": remaining_level,
    }, *semantic_events]


def _advance_break_branch(
    engine: SemanticEngine, state: dict[str, Any], seat: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    execution, resolution = _sponsors_context(state, seat)
    if resolution is not None:
        raise SemanticRuleError("the Break branch cannot follow a played Sponsor")
    next_state = clone_state(state)
    events: list[dict[str, Any]] = []
    if next_state["break"]["mode"] == "shared_track":
        next_state, semantic_events = engine.start_effects(next_state, seat, [{
            "op": "advance_break", "timing": "immediate",
            "args": {"amount": execution["spec"]["break_steps"]},
        }, {
            "op": "gain_money", "timing": "immediate",
            "args": {"amount": execution["spec"]["break_money"]},
        }], source_id="action:sponsors:break")
        events.extend(semantic_events)
    else:
        next_state, semantic_events = engine.start_effects(next_state, seat, [{
            "op": "gain_money", "timing": "immediate",
            "args": {"amount": execution["spec"]["break_money"]},
        }], source_id="action:sponsors:break")
        events.extend([{
            "type": "sponsors_break_advance_skipped_in_solo", "seat": seat,
            "amount": execution["spec"]["break_steps"],
        }, *semantic_events])
    completed, completion_events = complete_action_execution(engine, next_state, seat, {
        "performed": True, "mode": "advance_break",
        "break_steps": execution["spec"]["break_steps"],
        "money": execution["spec"]["break_money"],
    })
    return completed, [*events, *completion_events]


def _finish_sponsors(
    engine: SemanticEngine, state: dict[str, Any], seat: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolution = deepcopy(state["turn"]["action_session"]["sponsors_resolution"])
    next_state = clone_state(state)
    del next_state["turn"]["action_session"]["sponsors_resolution"]
    return complete_action_execution(engine, next_state, seat, {
        "performed": True, "mode": "play_sponsors", "cards": resolution["played"],
        "level_spent": sum(card["level"] for card in resolution["played"]),
    })


def _entry_for_card(entries: Mapping[str, ContentEntry], card: Mapping[str, Any]) -> ContentEntry:
    entry_id = card.get("entry_id", card.get("id"))
    if not isinstance(entry_id, str) or entry_id not in entries:
        raise SemanticRuleError(f"Sponsor content entry is unavailable: {entry_id}")
    return entries[entry_id]


def _instance_id(card: Mapping[str, Any]) -> str:
    value = card.get("instance_id", card.get("id"))
    if not isinstance(value, str) or not value:
        raise SemanticRuleError("Sponsor card requires a physical instance ID")
    return value


def _unique_instance_ids(cards: list[Any], label: str) -> list[str]:
    values = [_instance_id(card) for card in cards]
    if len(values) != len(set(values)):
        raise SemanticRuleError(f"{label} physical card IDs must be unique")
    return values


def _remove_zone_card(
    state: dict[str, Any], seat: int, source: str, instance_id: str,
) -> Mapping[str, Any]:
    cards = state["players"][seat]["hand"] if source == "hand" else state["card_display"]
    card = _find_zone_card(state, seat, source, instance_id)
    cards.remove(card)
    return card


def _find_zone_card(
    state: Mapping[str, Any], seat: int, source: str, instance_id: str,
) -> Mapping[str, Any]:
    cards = state["players"][seat]["hand"] if source == "hand" else state["card_display"]
    matches = [card for card in cards if _instance_id(card) == instance_id]
    if len(matches) != 1:
        raise SemanticRuleError("selected Sponsor instance is no longer available")
    return matches[0]


def _defer_display_refill(state: dict[str, Any], seat: int) -> dict[str, Any]:
    session = state["turn"]["action_session"]
    if any(effect.get("op") == "refill_card_display" for effect in session["after_finishing_effects"]):
        return state
    return defer_after_finishing(state, seat, [_DISPLAY_REFILL_EFFECT])
