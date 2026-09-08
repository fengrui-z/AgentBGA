"""Concrete resolver for Animals I/II card and enclosure choices."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Mapping

from ..mechanics import axial_hex_neighbors
from .actions import complete_action_execution, current_action_execution, defer_after_finishing
from .cards import entry_is_eligible, play_entry_semantics
from .cards_action import reputation_display_limit
from .content import ContentEntry
from .semantics import EvaluationContext, SemanticEngine, SemanticRuleError
from .state import clone_state, reputation_track_limit, validate_semantic_state


_SPECIAL_BUILDING_NAMES = {
    "Petting Zoo": "petting_zoo",
    "Reptile House": "reptile_house",
    "Large Bird Aviary": "large_bird_aviary",
}
_BUILDING_DISPLAY_NAMES = {
    "standard_enclosure": "standard enclosure",
    "petting_zoo": "Petting Zoo",
    "reptile_house": "Reptile House",
    "large_bird_aviary": "Large Bird Aviary",
}
_DISPLAY_REFILL_EFFECT = {
    "op": "refill_card_display", "timing": "after_finishing", "args": {"target_size": 6},
}


def legal_animals_execution_actions(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    entries: Mapping[str, ContentEntry],
) -> list[dict[str, Any]]:
    """Enumerate the next card-first Animals action decisions."""
    try:
        execution, resolution = _animals_context(state, seat)
    except SemanticRuleError:
        return []
    if state["resolution"]["queue"] or state["resolution"]["pending_choice"] is not None:
        return []
    if resolution is None:
        if not _candidate_cards(engine, state, seat, entries, execution, projected=True):
            return []
        return [{
            "id": "animals:begin", "label": "Begin Animals action",
            "action": {"type": "begin_animals_action"},
        }]
    if resolution.get("waza_stage") == "take_display":
        result = []
        for card in state["card_display"]:
            content_id = card.get("entry_id", card.get("id"))
            entry = entries.get(content_id) if isinstance(content_id, str) else None
            if entry is None or entry.kind != "animal" or _animal_size_class(entry) != "small":
                continue
            instance_id = _instance_id(card)
            result.append({
                "id": f"animals:waza-take:{instance_id}",
                "label": f"Take small Animal {entry.display_title} from display",
                "action": {"type": "take_waza_small_animal", "instance_id": instance_id},
            })
        result.append({
            "id": "animals:waza-take:decline",
            "label": "Do not take a small Animal from the display",
            "action": {"type": "finish_animals_action"},
        })
        return result
    if resolution["selected"] is not None:
        selected = resolution["selected"]
        entry = _entry_for_id(entries, selected["entry_id"])
        options = _enclosure_options(state["players"][seat], entry)
        return [{
            "id": f"animals:enclosure:{option['building_id']}",
            "label": _enclosure_option_label(entry, option),
            "presentation": {
                "animal": entry.display_title,
                "housing_mode": option["housing_mode"],
                "building_type": option["building_type"],
                "building_id": option["building_id"],
                "space_used": option["space"],
                "capacity_before": option["capacity_before"],
                "capacity_after": option["capacity_after"],
                "capacity_total": option["capacity_total"],
            },
            "action": {
                "type": "play_selected_animal",
                "building_id": option["building_id"],
            },
        } for option in options]
    result = [{
        "id": f"animals:select:{candidate['instance_id']}",
        "label": _animal_candidate_label(candidate),
        "action": {
            "type": "select_animal_card",
            "instance_id": candidate["instance_id"],
            "source": candidate["source"],
        },
    } for candidate in _candidate_cards(engine, state, seat, entries, execution)]
    if resolution["played"]:
        result.append({
            "id": "animals:finish", "label": (
                "Decline the extra small Animal"
                if resolution.get("waza_stage") == "extra" else "Finish Animals action"
            ),
            "action": {"type": "finish_animals_action"},
        })
    return result


def _animal_candidate_label(candidate: Mapping[str, Any]) -> str:
    entry = candidate["entry"]
    facts = entry.facts
    enclosure = f"standard enclosure {facts.get('enclosure_size', '?')}"
    if facts.get("special_enclosure"):
        enclosure += f" or {facts['special_enclosure']}"
    terrain = []
    if int(facts.get("rock_requirement", 0) or 0):
        terrain.append(f"rock-adjacent {facts['rock_requirement']}")
    if int(facts.get("water_requirement", 0) or 0):
        terrain.append(f"water-adjacent {facts['water_requirement']}")
    details = f" · {enclosure}"
    if terrain:
        details += " · " + ", ".join(terrain)
    if entry.requirements:
        details += " · printed prerequisites satisfied"
    return (
        f"Select {entry.display_title} from {candidate['source']} "
        f"({candidate['cost']} money){details}"
    )


def _enclosure_option_label(
    entry: ContentEntry, option: Mapping[str, Any],
) -> str:
    building_name = _BUILDING_DISPLAY_NAMES.get(
        str(option["building_type"]), str(option["building_type"]),
    )
    if option["housing_mode"] == "standard":
        capacity = (
            f"uses the full size-{option['capacity_total']} enclosure; "
            f"printed requirement {option['space']}"
        )
    else:
        capacity = (
            f"uses {option['space']} capacity; "
            f"{option['capacity_after']}/{option['capacity_total']} remains"
        )
    return (
        f"House {entry.display_title} in {building_name} "
        f"{option['building_id']} ({capacity})"
    )


def apply_animals_execution_action(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    entries: Mapping[str, ContentEntry],
    action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply one backend-issued Animals action decision."""
    if not isinstance(action, Mapping) or not isinstance(action.get("type"), str):
        raise SemanticRuleError("Animals execution action must contain a type")
    requested = dict(action)
    legal = [
        item["action"] for item in legal_animals_execution_actions(
            engine, state, seat, entries,
        )
    ]
    if requested not in legal:
        raise SemanticRuleError("Animals execution choice is not currently legal")
    if requested["type"] == "begin_animals_action":
        return _begin_animals(engine, state, seat)
    if requested["type"] == "select_animal_card":
        return _select_animal(engine, state, seat, entries, requested)
    if requested["type"] == "play_selected_animal":
        return _play_selected_animal(engine, state, seat, entries, requested["building_id"])
    if requested["type"] == "take_waza_small_animal":
        return _take_waza_small_animal(engine, state, seat, entries, requested["instance_id"])
    if requested["type"] == "finish_animals_action":
        return _finish_animals(engine, state, seat, entries)
    raise SemanticRuleError(f"unknown Animals execution action: {requested['type']}")


def _animals_context(
    state: Mapping[str, Any], seat: int,
) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    execution = current_action_execution(state, seat)
    if execution["action"] != "animals":
        raise SemanticRuleError("the active execution is not an Animals action")
    resolution = state["turn"]["action_session"].get("animals_resolution")
    if resolution is not None and not isinstance(resolution, Mapping):
        raise SemanticRuleError("invalid Animals action resolution state")
    return execution, resolution


def _begin_animals(
    engine: SemanticEngine, state: dict[str, Any], seat: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    execution, resolution = _animals_context(state, seat)
    if resolution is not None:
        raise SemanticRuleError("Animals action has already started")
    next_state = clone_state(state)
    next_state["turn"]["action_session"]["animals_resolution"] = {
        "remaining_cards": execution["spec"]["maximum_cards"],
        "played": [],
        "selected": None,
        "display_position_by_id": {
            card_id: index for index, card_id in enumerate(
                _unique_instance_ids(next_state["card_display"], "display")
            )
        },
        "display_changed": False,
        "waza_stage": None,
        "waza_program_used": False,
    }
    events = [{
        "type": "animals_action_started", "seat": seat,
        "maximum_cards": execution["spec"]["maximum_cards"],
    }]
    if execution["spec"]["reputation_before_play"]:
        next_state, semantic_events = engine.start_effects(next_state, seat, [{
            "op": "move_track", "timing": "immediate",
            "args": {"track": "reputation", "amount": 1},
        }], source_id="action:animals:reputation")
        events.extend(semantic_events)
    validate_semantic_state(next_state)
    return next_state, events


def _select_animal(
    engine: SemanticEngine,
    state: dict[str, Any], seat: int, entries: Mapping[str, ContentEntry], action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    next_state = clone_state(state)
    card = _find_zone_card(next_state, seat, action["source"], action["instance_id"])
    entry = _entry_for_card(entries, card)
    folder_cost = 0
    if action["source"] == "display":
        positions = next_state["turn"]["action_session"]["animals_resolution"][
            "display_position_by_id"
        ]
        folder_cost = int(positions[_instance_id(card)]) + 1
    cost = _animal_cost(next_state["players"][seat], entry) + folder_cost
    next_state["turn"]["action_session"]["animals_resolution"]["selected"] = {
        "instance_id": _instance_id(card),
        "entry_id": entry.id,
        "source": action["source"],
        "cost": cost,
        "folder_cost": folder_cost,
        "ignored_prerequisite": not entry_is_eligible(engine, next_state, seat, entry),
        "waza_extra": (
            next_state["turn"]["action_session"]["animals_resolution"].get("waza_stage")
            == "extra"
        ),
    }
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "animal_selected", "seat": seat, "instance_id": _instance_id(card),
        "entry_id": entry.id, "source": action["source"], "cost": cost,
        "folder_cost": folder_cost,
    }]


def _play_selected_animal(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    entries: Mapping[str, ContentEntry],
    building_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    next_state = clone_state(state)
    resolution = next_state["turn"]["action_session"]["animals_resolution"]
    selected = deepcopy(resolution["selected"])
    entry = _entry_for_id(entries, selected["entry_id"])
    card = _remove_zone_card(
        next_state, seat, selected["source"], selected["instance_id"],
    )
    building = next(
        item for item in next_state["players"][seat]["map"]["buildings"]
        if item["id"] == building_id
    )
    space = _animal_space_in_building(entry, building)
    building.setdefault("animal_ids", []).append(selected["instance_id"])
    if building["type"] == "standard_enclosure":
        building["occupied"] = True
        building["used_capacity"] = building["size"]
    else:
        building["used_capacity"] = int(building.get("used_capacity", 0)) + space
        building["occupied"] = building["used_capacity"] >= building["size"]
    player = next_state["players"][seat]
    player["money"] -= selected["cost"]
    resolution["remaining_cards"] -= 1
    resolution["played"].append({
        "instance_id": selected["instance_id"], "entry_id": entry.id,
        "building_id": building_id, "cost": selected["cost"], "space": space,
        "folder_cost": selected.get("folder_cost", 0),
        "size_class": _animal_size_class(entry),
        "waza_extra": bool(selected.get("waza_extra")),
    })
    resolution["selected"] = None
    if selected["source"] == "display":
        resolution["display_changed"] = True
        next_state = _defer_display_refill(next_state, seat)
    next_state, semantic_events = play_entry_semantics(
        engine, next_state, seat, entry, instance_id=selected["instance_id"],
        requirements_already_authorized=bool(selected.get("ignored_prerequisite")),
    )
    played = next(
        item for item in next_state["players"][seat]["played_cards"]
        if item["id"] == selected["instance_id"]
    )
    played.update({
        "enclosure_id": building_id, "enclosure_space": space,
        "card_source": selected["source"],
    })
    if selected.get("waza_extra"):
        next_state["turn"]["action_session"]["animals_resolution"][
            "waza_stage"
        ] = "take_display"
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "animal_played", "seat": seat,
        "instance_id": selected["instance_id"], "entry_id": entry.id,
        "building_id": building_id, "cost": selected["cost"], "space": space,
        "folder_cost": selected.get("folder_cost", 0),
    }, *semantic_events]


def _finish_animals(
    engine: SemanticEngine, state: dict[str, Any], seat: int,
    entries: Mapping[str, ContentEntry],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    current = state["turn"]["action_session"]["animals_resolution"]
    stage = current.get("waza_stage")
    if stage == "extra":
        next_state = clone_state(state)
        next_state["turn"]["action_session"]["animals_resolution"]["waza_stage"] = "take_display"
        validate_semantic_state(next_state)
        return next_state, [{"type": "waza_extra_small_animal_declined", "seat": seat}]
    if stage is None and _waza_small_program_active(state["players"][seat]):
        played = current["played"]
        if (
            played and not current.get("waza_program_used")
            and all(card.get("size_class") == "small" for card in played)
        ):
            next_state = clone_state(state)
            resolution = next_state["turn"]["action_session"]["animals_resolution"]
            resolution["waza_program_used"] = True
            resolution["waza_stage"] = "extra"
            resolution["remaining_cards"] = 1
            validate_semantic_state(next_state)
            return next_state, [{
                "type": "waza_small_animal_window_opened", "seat": seat,
                "small_animals_played": len(played),
            }]
    resolution = deepcopy(state["turn"]["action_session"]["animals_resolution"])
    next_state = clone_state(state)
    del next_state["turn"]["action_session"]["animals_resolution"]
    return complete_action_execution(engine, next_state, seat, {
        "performed": True,
        "cards": resolution["played"],
        "money_spent": sum(card["cost"] for card in resolution["played"]),
    })


def _take_waza_small_animal(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    entries: Mapping[str, ContentEntry],
    instance_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolution = state["turn"]["action_session"]["animals_resolution"]
    if resolution.get("waza_stage") != "take_display":
        raise SemanticRuleError("WAZA display take is not pending")
    next_state = clone_state(state)
    card = _find_zone_card(next_state, seat, "display", instance_id)
    entry = _entry_for_card(entries, card)
    if entry.kind != "animal" or _animal_size_class(entry) != "small":
        raise SemanticRuleError("WAZA may take only a small Animal")
    next_state["card_display"].remove(card)
    next_state["players"][seat]["hand"].append(card)
    next_state["turn"]["action_session"]["animals_resolution"]["display_changed"] = True
    next_state = _defer_display_refill(next_state, seat)
    completed, events = _finish_animals(engine, next_state, seat, entries)
    return completed, [{
        "type": "waza_small_animal_taken", "seat": seat,
        "instance_id": instance_id, "entry_id": entry.id,
    }, *events]


def _candidate_cards(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    entries: Mapping[str, ContentEntry],
    execution: Mapping[str, Any],
    *,
    projected: bool = False,
) -> list[dict[str, Any]]:
    resolution = state["turn"]["action_session"].get("animals_resolution")
    if resolution is not None and resolution["remaining_cards"] < 1:
        return []
    player = state["players"][seat]
    candidates = [(card, "hand", None) for card in player["hand"]]
    if execution["upgraded"]:
        reputation = player["tracks"]["reputation"]
        if projected:
            reputation = min(
                reputation_track_limit(player),
                reputation + execution["spec"]["reputation_before_play"],
            )
        limit = reputation_display_limit(reputation)
        positions = None if resolution is None else resolution["display_position_by_id"]
        for index, card in enumerate(state["card_display"]):
            position = index if positions is None else positions.get(_instance_id(card), 99)
            if position < limit:
                candidates.append((card, "display", position))
    result = []
    for card, source, display_position in candidates:
        content_id = card.get("entry_id", card.get("id"))
        entry = entries.get(content_id) if isinstance(content_id, str) else None
        if entry is None:
            continue
        if entry.kind != "animal" or not _animal_entry_is_eligible(engine, state, seat, entry):
            continue
        if resolution is not None and resolution.get("waza_stage") == "extra":
            if _animal_size_class(entry) != "small":
                continue
        folder_cost = 0 if display_position is None else int(display_position) + 1
        cost = _animal_cost(player, entry) + folder_cost
        if cost > player["money"] or not _enclosure_options(player, entry):
            continue
        result.append({
            "instance_id": _instance_id(card), "source": source,
            "entry": entry, "cost": cost, "folder_cost": folder_cost,
        })
    return result


def _animal_entry_is_eligible(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    entry: ContentEntry,
) -> bool:
    size_class = _animal_size_class(entry)
    flags = state["players"][seat]["flags"]
    if flags.get("waza_small_only") and size_class != "small":
        return False
    if flags.get("waza_large_only") and size_class != "large":
        return False
    if entry_is_eligible(engine, state, seat, entry):
        return True
    if int(entry.facts.get("enclosure_size", 0)) < 4 or not any(
        modifier.get("kind") == "large_animal_ignore_prerequisite"
        for modifier in state["players"][seat].get("modifiers", [])
    ):
        return False
    card = {"id": entry.id, "kind": entry.kind, "facts": dict(entry.facts)}
    context = EvaluationContext(state=state, actor_seat=seat, card=card)
    return sum(not engine.evaluate(requirement, context) for requirement in entry.requirements) == 1


def _enclosure_options(player: Mapping[str, Any], entry: ContentEntry) -> list[dict[str, Any]]:
    result = []
    for building in player["map"]["buildings"]:
        building_type = building["type"]
        if building_type == "standard_enclosure":
            if not entry.facts.get("can_use_standard_enclosure", True):
                continue
            if building.get("occupied"):
                flock_size = _flock_minimum_size(entry)
                if (
                    flock_size is None or building["size"] < flock_size
                    or not _enclosure_contains_icon(player, building, "herbivore")
                ):
                    continue
            elif building["size"] < int(entry.facts.get("enclosure_size", 0)):
                continue
        else:
            expected, _ = _special_enclosure(entry)
            if expected != building_type:
                continue
            space = _animal_space_in_building(entry, building)
            if int(building.get("used_capacity", 0)) + space > int(building["size"]):
                continue
        if not _terrain_requirement_met(player, building, "rock", entry.facts.get("rock_requirement", 0)):
            continue
        if not _terrain_requirement_met(player, building, "water", entry.facts.get("water_requirement", 0)):
            continue
        space = _animal_space_in_building(entry, building)
        used_before = int(building.get("used_capacity", 0))
        capacity_total = int(building["size"])
        result.append({
            "building_id": building["id"], "building_type": building_type,
            "housing_mode": (
                "standard" if building_type == "standard_enclosure" else "special"
            ),
            "space": space,
            "capacity_before": used_before,
            "capacity_after": (
                0 if building_type == "standard_enclosure"
                else capacity_total - used_before - space
            ),
            "capacity_total": capacity_total,
        })
    return result


def _terrain_requirement_met(
    player: Mapping[str, Any], building: Mapping[str, Any], terrain: str, required: Any,
) -> bool:
    amount = int(required or 0)
    if amount <= 0:
        return True
    if any(
        modifier.get("kind") == "diversity_researcher"
        for modifier in player.get("modifiers", [])
    ):
        return True
    terrain_cells = {
        (cell["q"], cell["r"]) for cell in player["map"]["cells"]
        if cell["terrain"] == terrain
    }
    adjacent = set().union(*(
        axial_hex_neighbors((cell["q"], cell["r"])) for cell in building["cells"]
    ))
    return len(adjacent & terrain_cells) >= amount


def _animal_cost(player: Mapping[str, Any], entry: ContentEntry) -> int:
    base = int(entry.facts.get("cost", 0))
    zoos = {
        value if isinstance(value, str) else value.get("continent")
        for value in player["partner_zoos"]
        if isinstance(value, (str, Mapping))
    }
    discount = 3 * sum(
        continent in zoos for continent in entry.facts.get("continents", [])
    )
    enclosure_size = int(entry.facts.get("enclosure_size", 0))
    for modifier in player.get("modifiers", []):
        if modifier.get("kind") == "animal_cost_discount":
            size_class = modifier.get("animal_size")
            if size_class == "small" and enclosure_size > 2:
                continue
            if size_class == "large" and enclosure_size < 4:
                continue
            discount += int(modifier.get("amount", 0))
    return max(0, base - discount)


def _animal_size_class(entry: ContentEntry) -> str:
    size = entry.facts.get("enclosure_size")
    if not isinstance(size, int) or isinstance(size, bool):
        raise SemanticRuleError(f"Animal card has no enclosure size: {entry.id}")
    if size <= 2:
        return "small"
    if size >= 4:
        return "large"
    return "medium"


def _waza_small_program_active(player: Mapping[str, Any]) -> bool:
    return any(
        modifier.get("kind") == "waza_small_animal_program"
        for modifier in player.get("modifiers", [])
    )


def _special_enclosure(entry: ContentEntry) -> tuple[str | None, int]:
    raw = entry.facts.get("special_enclosure")
    if not isinstance(raw, str) or not raw:
        return None, 0
    for name, building_type in _SPECIAL_BUILDING_NAMES.items():
        if raw.startswith(name):
            suffix = raw[len(name):].strip()
            return building_type, int(suffix or 0)
    raise SemanticRuleError(f"unknown special enclosure fact: {raw}")


def _animal_space_in_building(entry: ContentEntry, building: Mapping[str, Any]) -> int:
    building_type = building["type"]
    if building_type == "standard_enclosure" and building.get("occupied"):
        if _flock_minimum_size(entry) is not None:
            return 0
    expected, printed = _special_enclosure(entry)
    if expected == building_type:
        return printed
    if building_type == "standard_enclosure":
        return int(entry.facts.get("enclosure_size", 0))
    return math.ceil(int(entry.facts.get("enclosure_size", 0)) / 2)


def _flock_minimum_size(entry: ContentEntry) -> int | None:
    for ability in entry.facts.get("abilities", []):
        if ability.get("key") == "flock_animal":
            value = ability.get("value")
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return value
    return None


def _enclosure_contains_icon(
    player: Mapping[str, Any], building: Mapping[str, Any], icon: str,
) -> bool:
    occupants = set(building.get("animal_ids", []))
    for card in player["played_cards"]:
        if card.get("id") not in occupants:
            continue
        facts = card.get("facts", {})
        icons = facts.get("icons", []) if isinstance(facts, Mapping) else []
        if icon in icons:
            return True
    return False


def _find_zone_card(
    state: Mapping[str, Any], seat: int, source: str, instance_id: str,
) -> Mapping[str, Any]:
    cards = state["players"][seat]["hand"] if source == "hand" else state["card_display"]
    matches = [card for card in cards if _instance_id(card) == instance_id]
    if len(matches) != 1:
        raise SemanticRuleError("selected animal instance is no longer available")
    return matches[0]


def _remove_zone_card(state: dict[str, Any], seat: int, source: str, instance_id: str) -> dict[str, Any]:
    cards = state["players"][seat]["hand"] if source == "hand" else state["card_display"]
    card = _find_zone_card(state, seat, source, instance_id)
    cards.remove(card)
    return card


def _entry_for_card(entries: Mapping[str, ContentEntry], card: Mapping[str, Any]) -> ContentEntry:
    content_id = card.get("entry_id", card.get("id"))
    return _entry_for_id(entries, content_id)


def _entry_for_id(entries: Mapping[str, ContentEntry], content_id: Any) -> ContentEntry:
    if not isinstance(content_id, str) or content_id not in entries:
        raise SemanticRuleError(f"animal content entry is unavailable: {content_id}")
    return entries[content_id]


def _instance_id(card: Mapping[str, Any]) -> str:
    value = card.get("instance_id", card.get("id"))
    if not isinstance(value, str) or not value:
        raise SemanticRuleError("zoo card requires a stable physical instance ID")
    return value


def _unique_instance_ids(cards: list[Any], label: str) -> list[str]:
    values = [_instance_id(card) for card in cards]
    if len(values) != len(set(values)):
        raise SemanticRuleError(f"{label} physical card IDs must be unique")
    return values


def _defer_display_refill(state: dict[str, Any], seat: int) -> dict[str, Any]:
    session = state["turn"]["action_session"]
    if any(effect.get("op") == "refill_card_display" for effect in session["after_finishing_effects"]):
        return state
    return defer_after_finishing(state, seat, [_DISPLAY_REFILL_EFFECT])
