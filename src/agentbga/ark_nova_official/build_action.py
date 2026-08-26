"""Concrete Map 0 resolver for the official Build action."""

from __future__ import annotations

from copy import deepcopy
import random
from typing import Any, Mapping

from ..ark_nova_map import building_shape_variants
from ..mechanics import axial_hex_distance, axial_hex_neighbors
from .actions import complete_action_execution, current_action_execution, defer_after_finishing
from .cards_action import reputation_display_limit
from .semantics import SemanticEngine, SemanticRuleError
from .state import clone_state, validate_semantic_state


_UNIQUE_ZOO_BUILDINGS = frozenset({"petting_zoo", "reptile_house", "large_bird_aviary"})


def legal_build_execution_actions(state: Mapping[str, Any], seat: int) -> list[dict[str, Any]]:
    """Enumerate legal placements and pending Map 0 reward choices."""
    try:
        execution, resolution = _build_context(state, seat)
    except SemanticRuleError:
        return []
    if state["resolution"]["queue"] or state["resolution"]["pending_choice"] is not None:
        return []
    if resolution is not None and resolution["pending_rewards"]:
        return _reward_actions(state, seat, resolution["pending_rewards"][0])
    if resolution is not None and resolution.get("pending_migration") is not None:
        return _special_enclosure_migration_actions(
            state["players"][seat], str(resolution["pending_migration"]),
        )
    spec = execution["spec"]
    remaining = spec["maximum_total_size"] if resolution is None else resolution["remaining_strength"]
    built_keys = set() if resolution is None else {
        tuple(value) for value in resolution["built_keys"]
    }
    maximum_buildings = spec["maximum_buildings"]
    at_limit = (
        resolution is not None and maximum_buildings is not None
        and len(resolution["buildings"]) >= maximum_buildings
    )
    placements = [] if at_limit else _placement_actions(
        state["players"][seat], remaining, bool(execution["upgraded"]), built_keys,
    )
    if (
        resolution is not None and resolution["buildings"]
        and not resolution.get("engineer_used", False)
        and any(
            modifier.get("kind") == "engineer_extra_building"
            for modifier in state["players"][seat].get("modifiers", [])
        )
    ):
        copyable = sorted({
            (building["type"], building["size"])
            for building in resolution["buildings"]
            if building["type"] not in {"reptile_house", "large_bird_aviary"}
        })
        engineer = _placement_actions(
            state["players"][seat], 5, bool(execution["upgraded"]), set(),
            candidate_types=copyable,
        )
        for action in engineer:
            action["type"] = "place_engineer_building"
        placements.extend(engineer)
    result = [{
        "id": _placement_id(action),
        "label": _placement_label(action),
        "action": action,
    } for action in placements]
    if resolution is not None and resolution["buildings"]:
        result.append({
            "id": "build:finish",
            "label": "Finish Build action",
            "action": {"type": "finish_build_action"},
        })
    return result


def apply_build_execution_action(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply one backend-issued Build action choice."""
    if not isinstance(action, Mapping) or not isinstance(action.get("type"), str):
        raise SemanticRuleError("Build execution action must contain a type")
    requested = dict(action)
    legal = [item["action"] for item in legal_build_execution_actions(state, seat)]
    if requested not in legal:
        raise SemanticRuleError("Build execution choice is not currently legal")
    if requested["type"] == "place_building":
        return _place_building(engine, state, seat, requested)
    if requested["type"] == "place_engineer_building":
        return _place_building(engine, state, seat, requested, engineer=True)
    if requested["type"] == "take_build_reward_card":
        return _take_reward_card(state, seat, requested)
    if requested["type"] == "move_animal_to_special_enclosure":
        return _move_animal_to_special_enclosure(state, seat, requested)
    if requested["type"] == "finish_special_enclosure_migration":
        return _finish_special_enclosure_migration(state, seat)
    if requested["type"] == "finish_build_action":
        return _finish_build(engine, state, seat)
    raise SemanticRuleError(f"unknown Build execution action: {requested['type']}")


def _build_context(
    state: Mapping[str, Any], seat: int,
) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    execution = current_action_execution(state, seat)
    if execution["action"] != "build":
        raise SemanticRuleError("the active execution is not a Build action")
    resolution = state["turn"]["action_session"].get("build_resolution")
    if resolution is not None and not isinstance(resolution, Mapping):
        raise SemanticRuleError("invalid Build action resolution state")
    return execution, resolution


def _placement_actions(
    player: Mapping[str, Any],
    maximum_size: int,
    upgraded: bool,
    excluded_keys: set[tuple[str, int]],
    *,
    free: bool = False,
    candidate_types: list[tuple[str, int]] | None = None,
) -> list[dict[str, Any]]:
    if maximum_size < 1:
        return []
    zoo_map = player["map"]
    may_cover_terrain = any(
        modifier.get("kind") == "diversity_researcher"
        for modifier in player.get("modifiers", [])
    )
    allowed_terrain = {"buildable", "water", "rock"} if may_cover_terrain else {"buildable"}
    buildable = {
        (cell["q"], cell["r"]) for cell in zoo_map["cells"]
        if cell["terrain"] in allowed_terrain
    }
    map_coordinates = {(cell["q"], cell["r"]) for cell in zoo_map["cells"]}
    border = {
        cell for cell in buildable
        if any(neighbor not in map_coordinates for neighbor in axial_hex_neighbors(cell))
    }
    build_two = {
        (cell["q"], cell["r"]) for cell in zoo_map["cells"]
        if cell.get("requires_build_upgrade")
    }
    occupied = {
        (cell["q"], cell["r"])
        for building in zoo_map["buildings"] for cell in building["cells"]
    }
    existing_types = {building["type"] for building in zoo_map["buildings"]}
    kiosks = [
        (building["cells"][0]["q"], building["cells"][0]["r"])
        for building in zoo_map["buildings"] if building["type"] == "kiosk"
    ]
    candidates = candidate_types
    if candidates is None:
        candidates = [("pavilion", 1), ("kiosk", 1), ("petting_zoo", 3)]
        candidates.extend(("standard_enclosure", size) for size in range(1, min(5, maximum_size) + 1))
        if upgraded:
            candidates.extend((("reptile_house", 5), ("large_bird_aviary", 5)))
    choices: dict[tuple[Any, ...], dict[str, Any]] = {}
    for building_type, size in candidates:
        building_key = (building_type, size)
        if (
            size > maximum_size or (not free and player["money"] < size * 2)
            or building_key in excluded_keys
        ):
            continue
        if building_type in _UNIQUE_ZOO_BUILDINGS and building_type in existing_types:
            continue
        for anchor in sorted(buildable):
            for variant in building_shape_variants(building_type, size):
                cells = tuple(sorted(
                    (anchor[0] + q, anchor[1] + r) for q, r in variant["cells"]
                ))
                footprint = set(cells)
                if len(footprint) != size or not footprint <= buildable or footprint & occupied:
                    continue
                if footprint & build_two and not upgraded:
                    continue
                if occupied and not any(axial_hex_neighbors(cell) & occupied for cell in footprint):
                    continue
                if not occupied and not footprint & border:
                    continue
                if building_type == "kiosk" and any(
                    axial_hex_distance(cells[0], other) < 3 for other in kiosks
                ):
                    continue
                action = {
                    "type": "place_building",
                    "building_type": building_type,
                    "size": size,
                    "shape_id": variant["shape_id"],
                    "rotation": variant["rotation"],
                    "anchor": {"q": anchor[0], "r": anchor[1]},
                    "cost": size * 2,
                    "cells": [{"q": q, "r": r} for q, r in cells],
                }
                signature = (building_type, size, cells)
                choices[signature] = action
    return list(choices.values())


def legal_free_building_placements(
    player: Mapping[str, Any], building_types: list[str] | tuple[str, ...],
) -> list[dict[str, Any]]:
    """Return zero-cost placements for animal/sponsor card effects."""
    definitions = {
        "kiosk": ("kiosk", 1),
        "pavilion": ("pavilion", 1),
        "standard_enclosure_1": ("standard_enclosure", 1),
        "standard_enclosure_2": ("standard_enclosure", 2),
        "standard_enclosure_3": ("standard_enclosure", 3),
        "standard_enclosure_5": ("standard_enclosure", 5),
        "large_bird_aviary": ("large_bird_aviary", 5),
        "reptile_house": ("reptile_house", 5),
    }
    if any(building_type not in definitions for building_type in building_types):
        raise SemanticRuleError("free building effect contains an unknown building type")
    build_upgraded = next(
        card["upgraded"] for card in player["action_cards"] if card["action"] == "build"
    )
    actions = _placement_actions(
        player, 5, bool(build_upgraded), set(), free=True,
        candidate_types=[definitions[value] for value in building_types],
    )
    for action in actions:
        action["cost"] = 0
    return actions


def legal_unique_building_placements(
    player: Mapping[str, Any], rules: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Enumerate rotations of one fixed Sponsor unique-building tile."""
    building_type = rules.get("building_type")
    size = rules.get("size")
    if (
        not isinstance(building_type, str) or not building_type.startswith("unique_sponsor_")
        or not isinstance(size, int) or isinstance(size, bool) or size < 1
    ):
        raise SemanticRuleError("unique Sponsor building rules are malformed")
    zoo_map = player["map"]
    may_cover_terrain = any(
        modifier.get("kind") == "diversity_researcher"
        for modifier in player.get("modifiers", [])
    )
    allowed_terrain = {"buildable", "water", "rock"} if may_cover_terrain else {"buildable"}
    buildable = {
        (cell["q"], cell["r"]) for cell in zoo_map["cells"]
        if cell["terrain"] in allowed_terrain
    }
    map_coordinates = {(cell["q"], cell["r"]) for cell in zoo_map["cells"]}
    border = {
        cell for cell in buildable
        if any(neighbor not in map_coordinates for neighbor in axial_hex_neighbors(cell))
    }
    occupied = {
        (cell["q"], cell["r"])
        for building in zoo_map["buildings"] for cell in building["cells"]
    }
    build_two = {
        (cell["q"], cell["r"]) for cell in zoo_map["cells"]
        if cell.get("requires_build_upgrade")
    }
    build_upgraded = next(
        card["upgraded"] for card in player["action_cards"] if card["action"] == "build"
    )
    if any(building.get("type") == building_type for building in zoo_map["buildings"]):
        return []
    terrain_kind = None if may_cover_terrain else rules.get("adjacent_terrain")
    adjacent_count = 0 if may_cover_terrain else int(rules.get("adjacent_count", 0))
    terrain_cells = {
        (cell["q"], cell["r"]) for cell in zoo_map["cells"]
        if cell["terrain"] == terrain_kind
    } if terrain_kind is not None else set()
    border_count = int(rules.get("border_count", 0))
    ignore_existing = bool(rules.get("ignore_existing_adjacency", False))
    result: dict[tuple[tuple[int, int], ...], dict[str, Any]] = {}
    for anchor in sorted(buildable):
        for variant in building_shape_variants(building_type, size):
            cells = tuple(sorted(
                (anchor[0] + q, anchor[1] + r) for q, r in variant["cells"]
            ))
            footprint = set(cells)
            # 1. canonical shape; 2. bounds/buildable terrain and occupancy.
            if len(footprint) != size or not footprint <= buildable or footprint & occupied:
                continue
            # 3. Map 0's restricted cells still require Build II when a Sponsor
            # places the building instead of a normal Build action.
            if footprint & build_two and not build_upgraded:
                continue
            # 4. normal connectivity. Side Entrance (257) is the sole override.
            if not ignore_existing:
                if occupied and not any(
                    axial_hex_neighbors(cell) & occupied for cell in footprint
                ):
                    continue
                if not occupied and not footprint & border:
                    continue
            # 5. printed terrain adjacency, counted as distinct terrain spaces.
            adjacent = set().union(*(axial_hex_neighbors(cell) for cell in footprint)) - footprint
            if len(adjacent & terrain_cells) < adjacent_count:
                continue
            # 6. printed map-border constraint.
            if len(footprint & border) < border_count:
                continue
            result[cells] = {
                "type": "place_unique_sponsor_building",
                "building_type": building_type,
                "size": size,
                "shape_id": variant["shape_id"],
                "rotation": variant["rotation"],
                "anchor": {"q": anchor[0], "r": anchor[1]},
                "cost": 0,
                "cells": [{"q": q, "r": r} for q, r in cells],
            }
    return list(result.values())


def place_unique_building(
    state: dict[str, Any], seat: int, action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Place a prevalidated unique building and claim covered Map 0 bonuses."""
    next_state = clone_state(state)
    player = next_state["players"][seat]
    building = {
        "id": f"building-{player['map']['next_building_id']}",
        "type": action["building_type"], "size": action["size"],
        "shape_id": action["shape_id"], "rotation": action["rotation"],
        "occupied": False, "cells": deepcopy(action["cells"]),
    }
    player["map"]["next_building_id"] += 1
    player["map"]["buildings"].append(building)
    effects, pending = _claim_map_rewards(player, action["cells"])
    if _map_is_complete(player) and not player["map"].get("completion_reward_claimed"):
        player["map"]["completion_reward_claimed"] = True
        reward = player["map"].get("completion_reward", {})
        if reward.get("type") == "gain_appeal":
            effects.append(_effect("move_track", {
                "track": "appeal", "amount": int(reward.get("amount", 0)),
            }))
    effects.append(_effect("trigger_building_placed", {"cells": deepcopy(action["cells"])}))
    return next_state, effects, pending


def place_free_building(
    state: dict[str, Any], seat: int, action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Place a validated free building and return direct/pending map rewards."""
    player = state["players"][seat]
    building = {
        "id": f"building-{player['map']['next_building_id']}",
        "type": action["building_type"], "size": action["size"],
        "shape_id": action["shape_id"], "rotation": action["rotation"],
        "occupied": False, "cells": deepcopy(action["cells"]),
    }
    player["map"]["next_building_id"] += 1
    player["map"]["buildings"].append(building)
    effects, pending = _claim_map_rewards(player, action["cells"])
    if action["building_type"] == "pavilion":
        effects.insert(0, _effect("move_track", {"track": "appeal", "amount": 1}))
    if _map_is_complete(player) and not player["map"].get("completion_reward_claimed"):
        player["map"]["completion_reward_claimed"] = True
        reward = player["map"].get("completion_reward", {})
        if reward.get("type") == "gain_appeal":
            effects.append(_effect("move_track", {
                "track": "appeal", "amount": int(reward.get("amount", 0)),
            }))
    effects.append(_effect("trigger_building_placed", {"cells": deepcopy(action["cells"])}))
    return building, effects, pending


def _place_building(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    action: Mapping[str, Any],
    *,
    engineer: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    execution, old_resolution = _build_context(state, seat)
    next_state = clone_state(state)
    player = next_state["players"][seat]
    if old_resolution is None:
        next_state["turn"]["action_session"]["build_resolution"] = {
            "remaining_strength": execution["spec"]["maximum_total_size"],
            "buildings": [],
            "built_keys": [],
            "pending_rewards": [],
            "pending_migration": None,
            "engineer_used": False,
        }
    resolution = next_state["turn"]["action_session"]["build_resolution"]
    building = {
        "id": f"building-{player['map']['next_building_id']}",
        "type": action["building_type"],
        "size": action["size"],
        "shape_id": action["shape_id"],
        "rotation": action["rotation"],
        "occupied": False,
        "cells": deepcopy(action["cells"]),
    }
    player["map"]["next_building_id"] += 1
    player["map"]["buildings"].append(building)
    player["money"] -= action["cost"]
    if engineer:
        resolution["engineer_used"] = True
    else:
        resolution["remaining_strength"] -= action["size"]
        resolution["built_keys"].append([action["building_type"], action["size"]])
    resolution["buildings"].append(deepcopy(building))
    if action["building_type"] in {"reptile_house", "large_bird_aviary"}:
        resolution["pending_migration"] = building["id"]
    direct_effects, pending_rewards = _claim_map_rewards(player, action["cells"])
    clever_rewards = [reward for reward in pending_rewards if reward["type"] == "clever"]
    pending_rewards = [reward for reward in pending_rewards if reward["type"] != "clever"]
    if action["building_type"] == "pavilion":
        direct_effects.insert(0, _effect("move_track", {"track": "appeal", "amount": 1}))
    resolution["pending_rewards"].extend(pending_rewards)
    if clever_rewards:
        next_state = defer_after_finishing(next_state, seat, [
            {
                "op": "reposition_action_card",
                "timing": "after_finishing",
                "args": {"target_slot": reward["target_strength"], "optional": False},
            }
            for reward in clever_rewards
        ])
    if _map_is_complete(player) and not player["map"].get("completion_reward_claimed"):
        player["map"]["completion_reward_claimed"] = True
        reward = player["map"].get("completion_reward", {})
        if reward.get("type") == "gain_appeal":
            direct_effects.append(_effect("move_track", {
                "track": "appeal", "amount": int(reward.get("amount", 0)),
            }))
    direct_effects.append(_effect(
        "trigger_building_placed", {"cells": deepcopy(action["cells"])},
    ))
    events = [{
        "type": "building_placed", "seat": seat, "building": deepcopy(building),
        "cost": action["cost"], "remaining_strength": resolution["remaining_strength"],
        "engineer_extra": engineer,
    }]
    if direct_effects:
        next_state, semantic_events = engine.start_effects(
            next_state, seat, direct_effects, source_id=f"map:{building['id']}",
        )
        events.extend(semantic_events)
    validate_semantic_state(next_state)
    return next_state, events


def _claim_map_rewards(
    player: dict[str, Any], cells: list[Mapping[str, int]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_coordinate = {(cell["q"], cell["r"]): cell for cell in player["map"]["cells"]}
    map_coordinates = set(by_coordinate)
    archeologist = any(
        modifier.get("kind") == "archeologist_bonus"
        for modifier in player.get("modifiers", [])
    )
    effects: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for coordinate in ((cell["q"], cell["r"]) for cell in cells):
        reward = by_coordinate[coordinate].pop("placement_bonus", None)
        if reward is None:
            continue
        if archeologist and any(
            neighbor not in map_coordinates for neighbor in axial_hex_neighbors(coordinate)
        ):
            effects.append(_effect("take_any_map_placement_bonus", {}))
        if reward["type"] in {"take_card", "clever"}:
            pending.append({**deepcopy(reward), "coordinate": list(coordinate)})
            continue
        operations = {
            "gain_money": ("gain_money", {"amount": reward["amount"]}),
            "gain_x_token": ("gain_x_token", {"amount": reward["amount"]}),
            "gain_reputation": (
                "move_track", {"track": "reputation", "amount": reward["amount"]},
            ),
        }
        if reward["type"] not in operations:
            raise SemanticRuleError(f"unsupported Map 0 reward: {reward['type']}")
        op, args = operations[reward["type"]]
        effects.append(_effect(op, args))
    return effects, pending


def _special_enclosure_migration_actions(
    player: Mapping[str, Any], special_building_id: str,
) -> list[dict[str, Any]]:
    special = next((
        building for building in player["map"]["buildings"]
        if building.get("id") == special_building_id
    ), None)
    if special is None or special.get("type") not in {"reptile_house", "large_bird_aviary"}:
        raise SemanticRuleError("pending special-enclosure migration is invalid")
    remaining = int(special.get("size", 5)) - int(special.get("used_capacity", 0))
    result = []
    for card in player["played_cards"]:
        if card.get("kind") != "animal" or not isinstance(card.get("facts"), Mapping):
            continue
        space = _special_enclosure_space(card["facts"], str(special["type"]))
        if space is None or space > remaining:
            continue
        source_id = card.get("enclosure_id")
        source = next((
            building for building in player["map"]["buildings"]
            if building.get("id") == source_id
        ), None)
        if source is None or source.get("type") != "standard_enclosure" or not source.get("occupied"):
            continue
        if not _special_enclosure_terrain_met(player, special, card["facts"]):
            continue
        action = {
            "type": "move_animal_to_special_enclosure",
            "instance_id": card["id"], "source_building_id": source["id"],
            "special_building_id": special_building_id, "space": space,
        }
        result.append({
            "id": f"build:migrate:{card['id']}",
            "label": f"Move {card.get('display_title', card['id'])} into {special['type']}",
            "action": action,
        })
    result.append({
        "id": "build:migrate:finish", "label": "Finish moving animals",
        "action": {"type": "finish_special_enclosure_migration"},
    })
    return result


def _move_animal_to_special_enclosure(
    state: dict[str, Any], seat: int, action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    next_state = clone_state(state)
    player = next_state["players"][seat]
    card = next(
        card for card in player["played_cards"] if card.get("id") == action["instance_id"]
    )
    source = next(
        building for building in player["map"]["buildings"]
        if building.get("id") == action["source_building_id"]
    )
    special = next(
        building for building in player["map"]["buildings"]
        if building.get("id") == action["special_building_id"]
    )
    source["animal_ids"] = [
        value for value in source.get("animal_ids", []) if value != card["id"]
    ]
    source["occupied"] = bool(source["animal_ids"])
    source["used_capacity"] = int(source["size"]) if source["occupied"] else 0
    special.setdefault("animal_ids", []).append(card["id"])
    special["used_capacity"] = int(special.get("used_capacity", 0)) + int(action["space"])
    special["occupied"] = special["used_capacity"] >= int(special["size"])
    card["enclosure_id"] = special["id"]
    card["enclosure_space"] = int(action["space"])
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "animal_moved_to_special_enclosure", "seat": seat,
        "instance_id": card["id"], "source_building_id": source["id"],
        "special_building_id": special["id"], "space": int(action["space"]),
    }]


def _finish_special_enclosure_migration(
    state: dict[str, Any], seat: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    next_state = clone_state(state)
    resolution = next_state["turn"]["action_session"]["build_resolution"]
    building_id = resolution.get("pending_migration")
    resolution["pending_migration"] = None
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "special_enclosure_migration_finished", "seat": seat,
        "building_id": building_id,
    }]


def _special_enclosure_space(facts: Mapping[str, Any], building_type: str) -> int | None:
    label = "Reptile House" if building_type == "reptile_house" else "Large Bird Aviary"
    raw = facts.get("special_enclosure")
    if not isinstance(raw, str) or not raw.startswith(label):
        return None
    suffix = raw[len(label):].strip()
    if not suffix:
        return 0
    try:
        value = int(suffix)
    except ValueError as error:
        raise SemanticRuleError("special-enclosure capacity fact is malformed") from error
    return value


def _special_enclosure_terrain_met(
    player: Mapping[str, Any], building: Mapping[str, Any], facts: Mapping[str, Any],
) -> bool:
    if any(
        modifier.get("kind") == "diversity_researcher"
        for modifier in player.get("modifiers", [])
    ):
        return True
    footprint = {(cell["q"], cell["r"]) for cell in building["cells"]}
    adjacent = set().union(*(axial_hex_neighbors(cell) for cell in footprint))
    for terrain in ("rock", "water"):
        required = int(facts.get(f"{terrain}_requirement", 0) or 0)
        terrain_cells = {
            (cell["q"], cell["r"]) for cell in player["map"]["cells"]
            if cell["terrain"] == terrain and (cell["q"], cell["r"]) not in footprint
        }
        if len(adjacent & terrain_cells) < required:
            return False
    return True


def _reward_actions(
    state: Mapping[str, Any], seat: int, reward: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if reward["type"] == "take_card":
        actions = []
        if state["zoo_deck"] or state["zoo_discard"]:
            actions.append({
                "id": "build:reward:card:deck", "label": "Draw reward card from deck",
                "action": {"type": "take_build_reward_card", "source": "deck"},
            })
        limit = reputation_display_limit(state["players"][seat]["tracks"]["reputation"])
        for index, card in enumerate(state["card_display"][:limit]):
            card_id = card.get("id")
            if not isinstance(card_id, str):
                raise SemanticRuleError("display cards require stable IDs")
            actions.append({
                "id": f"build:reward:card:display:{card_id}",
                "label": f"Take reward card from display position {index + 1}",
                "action": {
                    "type": "take_build_reward_card", "source": "display", "card_id": card_id,
                },
            })
        return actions
    raise SemanticRuleError(f"unknown pending Map 0 reward: {reward['type']}")


def _take_reward_card(
    state: dict[str, Any], seat: int, action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    next_state = clone_state(state)
    source = action["source"]
    recycled = False
    if source == "deck":
        recycled = _recycle_discard_if_needed(next_state)
        card = next_state["zoo_deck"].pop()
    else:
        card_id = action["card_id"]
        matches = [card for card in next_state["card_display"] if card.get("id") == card_id]
        if len(matches) != 1:
            raise SemanticRuleError("selected reward card is no longer in the display")
        card = matches[0]
        next_state["card_display"].remove(card)
        if next_state["zoo_deck"]:
            next_state["card_display"].append(next_state["zoo_deck"].pop())
    next_state["players"][seat]["hand"].append(card)
    _consume_reward(next_state)
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "map_card_reward_taken", "seat": seat, "card_id": card["id"],
        "source": source, "deck_recycled": recycled,
    }]


def _consume_reward(state: dict[str, Any]) -> None:
    state["turn"]["action_session"]["build_resolution"]["pending_rewards"].pop(0)


def _finish_build(
    engine: SemanticEngine, state: dict[str, Any], seat: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolution = deepcopy(state["turn"]["action_session"]["build_resolution"])
    next_state = clone_state(state)
    del next_state["turn"]["action_session"]["build_resolution"]
    return complete_action_execution(engine, next_state, seat, {
        "performed": True,
        "buildings": resolution["buildings"],
        "strength_spent": sum(building["size"] for building in resolution["buildings"]),
        "money_spent": sum(building["size"] * 2 for building in resolution["buildings"]),
    })


def _map_is_complete(player: Mapping[str, Any]) -> bool:
    buildable = {
        (cell["q"], cell["r"]) for cell in player["map"]["cells"]
        if cell["terrain"] == "buildable"
    }
    occupied = {
        (cell["q"], cell["r"])
        for building in player["map"]["buildings"] for cell in building["cells"]
    }
    return buildable <= occupied


def _recycle_discard_if_needed(state: dict[str, Any]) -> bool:
    if state["zoo_deck"]:
        return False
    if not state["zoo_discard"]:
        raise SemanticRuleError("the Zoo deck and discard pile are empty")
    cards = state["zoo_discard"]
    random.Random(f"{state['seed']}:map-reward:{state['turn']['number']}").shuffle(cards)
    state["zoo_deck"] = cards
    state["zoo_discard"] = []
    return True


def _effect(op: str, args: Mapping[str, Any]) -> dict[str, Any]:
    return {"op": op, "timing": "immediate", "args": dict(args)}


def _placement_id(action: Mapping[str, Any]) -> str:
    anchor = action["anchor"]
    return (
        f"build:place:{action['building_type']}:{action['size']}:"
        f"r{action['rotation']}:q{anchor['q']}:r{anchor['r']}"
    )


def _placement_label(action: Mapping[str, Any]) -> str:
    anchor = action["anchor"]
    return (
        f"{action['building_type']} {action['size']} · {action['rotation'] * 60}° "
        f"at ({anchor['q']},{anchor['r']}) · {action['cost']} money"
    )
