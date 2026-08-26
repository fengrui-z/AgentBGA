"""Deterministic Ark Nova controlled-core rules plugin.

The turn, action-card, Break, hidden-information, and decision-step machinery is
playable end to end. Zoo cards are generated research fixtures with no copied
publisher text or artwork; their special abilities are intentionally deferred to
the data-driven card-effect milestone.
"""

from __future__ import annotations

from copy import deepcopy
from itertools import combinations
import json
import random
from typing import Any

from .game import GameRuleError
from .mechanics import (
    ActionSpace,
    DecisionStep,
    action_accepted,
    adjust_resources,
    advance_track,
    assign_competition_ranks,
    hidden_items,
    axial_hex_distance,
    axial_hex_neighbors,
    reset_track,
    state_digest,
    validate_unique_items,
    private_items,
)
from .mechanics.zones import move_item
from .ark_nova_map import building_shape_variants, map_zero, valid_building_shape
from .ark_nova_tracks import appeal_income, reputation_display_slot, scoring_tracks_crossed
from .ark_nova_presentation import (
    association_display,
    map_display,
    player_public_summary,
    public_tracks,
)


RULES_VERSION = "base-1.2-controlled-core.6"
ACTION_TYPES = ("animals", "cards", "build", "association", "sponsors")
CONTINENTS = ("africa", "asia", "australia", "europe", "americas")
ANIMAL_TAGS = ("bird", "primate", "predator", "reptile", "herbivore", "bear", "petting_zoo")
BREAK_LIMITS = {2: 9, 3: 12, 4: 15}
ACTION_UPGRADE_MILESTONES = (2,)
CONSERVATION_BONUS_MILESTONES = (5, 8)
FINAL_CARD_CHOICE_CONSERVATION = 10
REPUTATION_UPGRADE_MILESTONE = 5
REPUTATION_CARDS_GATE = 10
REPUTATION_MAXIMUM = 15
DONATION_COSTS = (2, 5, 7, 10, 12)


class RuleError(GameRuleError):
    pass


def describe() -> dict[str, Any]:
    return {
        "id": "ark_nova",
        "name": "Ark Nova",
        "rules_version": RULES_VERSION,
        "players": {"minimum": 2, "maximum": 4},
        "hidden_information": True,
        "implementation_status": "controlled_core",
        "runnable": True,
        "decision_model": "player_turn_with_multiple_decision_steps",
        "action_types": list(ACTION_TYPES),
        "map": "map_zero_flat_top_polyhex_v3",
        "content_scope": (
            "complete research-card match with action upgrades, donations, release projects, "
            "partner discounts, primitive effects, and controlled final cards; publisher card "
            "text and maps beyond the supplied Map 0 transcription are deferred"
        ),
        "rules_sources": [
            "Ark Nova Rulebook, English, version 1.2",
            "Ark Nova FAQ/Errata, English, version 2",
        ],
        "win_condition": (
            "Opposing Appeal and Conservation markers meeting/crossing, or the controlled turn "
            "limit, followed by deterministic ranking with "
            "generated final-scoring objectives. Published final-scoring cards are deferred."
        ),
    }


def _research_zoo_cards() -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for index in range(1, 129):
        effects = []
        if index % 11 == 0:
            effects.append({"type": "gain_money", "amount": 3})
        if index % 19 == 0:
            effects.append({"type": "gain_x_token", "amount": 1})
        if index % 23 == 0:
            effects.append({"type": "move_break", "amount": 1})
        cards.append({
            "id": f"research-animal-{index:03d}", "card_type": "animal",
            "tags": [ANIMAL_TAGS[(index - 1) % len(ANIMAL_TAGS)]],
            "continent": CONTINENTS[(index - 1) % len(CONTINENTS)],
            "cost": 4 + (index % 10), "enclosure_size": 1 + (index % 5),
            "appeal": 2 + (index % 5), "conservation": 1 if index % 17 == 0 else 0,
            "reputation": 1 if index % 13 == 0 else 0,
            "effects": effects, "implementation": "controlled_effect_primitives",
        })
    for index in range(1, 65):
        effects = [{"type": "gain_money", "amount": 2}] if index % 10 == 0 else []
        cards.append({
            "id": f"research-sponsor-{index:03d}", "card_type": "sponsor", "tags": [],
            "level": 1 + (index % 5), "appeal": 1 if index % 3 == 0 else 0,
            "income": 1 + (index % 3), "effects": effects,
            "implementation": "controlled_income_and_effect_primitives",
        })
    for index in range(1, 21):
        tag = (*ANIMAL_TAGS, *CONTINENTS)[(index - 1) % (len(ANIMAL_TAGS) + len(CONTINENTS))]
        cards.append({
            "id": f"research-project-{index:03d}", "card_type": "conservation_project",
            "tags": [tag], "tag": tag, "levels": [2, 4, 5],
            "project_kind": "release_animal" if index % 5 == 0 else "tag",
            "implementation": "controlled_project",
        })
    return cards


def _final_cards() -> list[dict[str, Any]]:
    objectives = (
        ("animal_tags", 2), ("continents", 2), ("animals", 2),
        ("sponsors", 2), ("supported_projects", 1), ("buildings", 3),
    )
    return [{
        "id": f"research-final-{index:02d}",
        "objective": objectives[(index - 1) % len(objectives)][0],
        "per": objectives[(index - 1) % len(objectives)][1],
        "points_per_step": 2, "maximum": 8,
        "implementation": "controlled_final_scoring",
    } for index in range(1, 12)]


def _base_projects() -> list[dict[str, Any]]:
    tags = (*ANIMAL_TAGS, *CONTINENTS)
    return [{
        "id": f"research-base-{index:02d}", "tag": tags[index - 1],
        "levels": [2, 4, 5], "claims": [], "implementation": "controlled_tag_project",
    } for index in range(1, 13)]


def _bonus_tiles() -> list[dict[str, Any]]:
    effects = (
        {"type": "gain_money", "amount": 8},
        {"type": "gain_x_token", "amount": 3},
        {"type": "gain_reputation", "amount": 2},
        {"type": "gain_appeal", "amount": 3},
        {"type": "gain_conservation", "amount": 1},
    )
    return [{"id": f"research-bonus-{index:02d}", "effects": [effects[(index - 1) % len(effects)]],
             "implementation": "controlled_bonus_effect"} for index in range(1, 10)]


def _map_zero() -> dict[str, Any]:
    return map_zero()


def new_game(players: int, seed: int, config: dict[str, Any] | None = None) -> dict[str, Any]:
    if players not in (2, 3, 4):
        raise RuleError("Ark Nova requires 2, 3, or 4 players")
    config = config or {}
    if set(config) - {"map", "turn_limit"} or config.get("map", "0") not in ("0", "map-0"):
        raise RuleError("the controlled core supports only Map 0 and turn_limit")
    turn_limit = config.get("turn_limit", players * 30)
    if not isinstance(turn_limit, int) or turn_limit < players:
        raise RuleError("turn_limit must be an integer at least equal to player count")
    rng = random.Random(seed)
    zoo_cards = _research_zoo_cards()
    rng.shuffle(zoo_cards)
    display = [zoo_cards.pop() for _ in range(6)]
    finals = _final_cards()
    rng.shuffle(finals)
    projects = _base_projects()
    rng.shuffle(projects)
    bonus_tiles = _bonus_tiles()
    rng.shuffle(bonus_tiles)
    rows = []
    for seat in range(players):
        initial_draw = [zoo_cards.pop() for _ in range(8)]
        other_actions = list(ACTION_TYPES[1:])
        rng.shuffle(other_actions)
        rows.append({
            "seat": seat, "money": 25, "x_tokens": 0, "appeal": seat,
            "conservation": 0, "reputation": 1,
            "action_cards": [{"action": action, "strength": position, "upgraded": False, "tokens": []}
                             for position, action in enumerate(["animals", *other_actions], 1)],
            "association_workers": {"active": 1, "reserve": 3, "committed": []},
            "partner_zoos": [], "universities": [], "map": _map_zero(), "hand": [],
            "initial_draw": initial_draw, "initial_keep_required": 4, "played_cards": [],
            "final_scoring_cards": [finals.pop() for _ in range(2)],
            "conservation_tokens_on_map": 7, "supported_projects": [],
            "upgrade_rewards_claimed": [], "conservation_rewards_claimed": [],
            "upgrade_sources_claimed": [], "final_card_choice_resolved": False,
        })
    project_count = 4 if players == 4 else 3
    state = {
        "schema_version": "agentbga.ark_nova.state.v2", "game_id": "ark_nova",
        "rules_version": RULES_VERSION, "implementation_status": "controlled_core",
        "seed": seed, "player_count": players, "turn_limit": turn_limit,
        "status": "active", "phase": "initial_hand_selection", "turn_count": 0,
        "decision_count": 0, "active_seat": 0, "pending_action": None,
        "pending_rewards": [],
        "end_after_turn": None, "end_reason": None,
        "turn": {"active_seat": 0, "decision": "choose_initial_hand", "action_card": None,
                 "remaining_plays": 0},
        "break_track": {"position": 0, "limit": BREAK_LIMITS[players],
                        "start_marker": f"players-{players}", "triggered": False,
                        "next_seat": None},
        "recycle_count": 0, "game_board_bonus_tiles": bonus_tiles[:4],
        "unused_bonus_tiles": bonus_tiles[4:], "card_display": display,
        "zoo_deck": zoo_cards, "zoo_discard": [], "final_scoring_deck": finals,
        "base_conservation_projects": projects[:project_count],
        "base_conservation_deck": projects[project_count:],
        "association_board": {
            "partner_zoos": {continent: 1 for continent in CONTINENTS},
            "universities": {"research-2": 1, "research-reputation": 1, "hand-limit-5": 1},
            "blocked_two_player": (["project-left", "project-middle", "project-right",
                                    "donation-left-1", "donation-left-2", "donation-left-3"]
                                   if players == 2 else []),
            "donations": [],
        },
        "players": rows,
    }
    validate_state(state)
    return state


def state_hash(state: dict[str, Any]) -> str:
    return state_digest(state)


def _hidden_cards(count: int) -> list[dict[str, bool]]:
    return hidden_items(count)


def _action_space(state: dict[str, Any], actions: list[dict[str, Any]]) -> ActionSpace:
    return ActionSpace.from_actions(state["phase"], state["decision_count"], actions)


def _wrap_actions(state: dict[str, Any], actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _action_space(state, actions).wrapped()


def _action_card(player: dict[str, Any], name: str) -> dict[str, Any]:
    return next(card for card in player["action_cards"] if card["action"] == name)


def _occupied_cells(player: dict[str, Any]) -> set[tuple[int, int]]:
    return {(cell["q"], cell["r"]) for building in player["map"]["buildings"] for cell in building["cells"]}


def _neighbors(cell: tuple[int, int]) -> set[tuple[int, int]]:
    return axial_hex_neighbors(cell)


def _hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return axial_hex_distance(a, b)


def _build_actions(
    player: dict[str, Any], strength: int, upgraded: bool = False,
    excluded_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    buildable = {(cell["q"], cell["r"]) for cell in player["map"]["cells"]
                 if cell["terrain"] == "buildable"}
    map_coordinates = {(cell["q"], cell["r"]) for cell in player["map"]["cells"]}
    border_buildable = {
        cell for cell in buildable if any(neighbor not in map_coordinates for neighbor in _neighbors(cell))
    }
    build_ii = {(cell["q"], cell["r"]) for cell in player["map"]["cells"]
                if cell.get("requires_build_upgrade", False)}
    occupied = _occupied_cells(player)
    existing_kiosks = [tuple((building["cells"][0][key] for key in ("q", "r")))
                        for building in player["map"]["buildings"] if building["type"] == "kiosk"]
    choices: dict[str, dict[str, Any]] = {}
    types = [("pavilion", 1), ("kiosk", 1), ("petting_zoo", 3)] + [("standard_enclosure", size)
                                                for size in range(1, min(5, strength) + 1)]
    if upgraded:
        types.extend([("reptile_house", 5), ("large_bird_aviary", 5)])
    unique_types = {"petting_zoo", "reptile_house", "large_bird_aviary"}
    existing_types = {building["type"] for building in player["map"]["buildings"]}
    excluded_types = excluded_types or set()
    for building_type, size in types:
        if building_type in excluded_types or (building_type in unique_types and building_type in existing_types):
            continue
        if size > strength or player["money"] < size * 2:
            continue
        for start in sorted(buildable):
            for variant in building_shape_variants(building_type, size):
                cells = [(start[0] + q, start[1] + r) for q, r in variant["cells"]]
                cell_set = set(cells)
                if len(cell_set) != size or not cell_set <= buildable or cell_set & occupied:
                    continue
                if cell_set & build_ii and not upgraded:
                    continue
                if occupied and not any(_neighbors(cell) & occupied for cell in cell_set):
                    continue
                if not occupied and not cell_set & border_buildable:
                    continue
                if building_type == "kiosk" and any(_hex_distance(cells[0], other) < 3 for other in existing_kiosks):
                    continue
                action = {"type": "place_building", "building_type": building_type, "size": size,
                          "shape_id": variant["shape_id"], "rotation": variant["rotation"],
                          "anchor": {"q": start[0], "r": start[1]},
                          "cost": size * 2, "cells": [{"q": q, "r": r} for q, r in sorted(cells)]}
                choices[json.dumps(action, sort_keys=True)] = action
    return list(choices.values())


def _playable_animals(state: dict[str, Any], player: dict[str, Any], upgraded: bool = False) -> list[dict[str, Any]]:
    empty = [building for building in player["map"]["buildings"]
             if building["type"] == "standard_enclosure" and not building["occupied"]]
    actions = []
    candidates = [(card, "hand", None) for card in player["hand"]]
    if upgraded:
        maximum_slot = reputation_display_slot(player["reputation"])
        candidates.extend((card, "display", slot) for slot, card in enumerate(state["card_display"], 1)
                          if slot <= maximum_slot)
    for card, source, slot in candidates:
        cost = _animal_cost(player, card) if card["card_type"] == "animal" else 0
        if card["card_type"] != "animal" or cost > player["money"]:
            continue
        for enclosure in empty:
            if enclosure["size"] >= card["enclosure_size"]:
                actions.append({"type": "play_animal", "card_id": card["id"],
                                "enclosure_id": enclosure["id"], "cost": cost,
                                "discount": card["cost"] - cost, "source": source,
                                **({"display_slot": slot} if slot is not None else {})})
    return actions


def _tag_count(player: dict[str, Any], tag: str) -> int:
    count = sum(tag in card.get("tags", []) for card in player["played_cards"])
    count += sum(zoo == tag for zoo in player["partner_zoos"])
    return count


def _animal_cost(player: dict[str, Any], card: dict[str, Any]) -> int:
    return max(0, card["cost"] - (3 if card.get("continent") in player["partner_zoos"] else 0))


def _upgrade_actions(player: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"type": "upgrade_action_card", "action_card": card["action"]}
            for card in player["action_cards"] if not card["upgraded"]]


def _donation_cost(state: dict[str, Any]) -> int | None:
    index = len(state["association_board"]["donations"])
    return DONATION_COSTS[index] if index < len(DONATION_COSTS) else None


def _release_project_actions(state: dict[str, Any], player: dict[str, Any]) -> list[dict[str, Any]]:
    actions = []
    for project in player["hand"]:
        if project.get("project_kind") != "release_animal":
            continue
        for card in player["played_cards"]:
            if card.get("card_type") != "animal":
                continue
            for level in project["levels"]:
                if card.get("enclosure_size", 0) >= level:
                    actions.append({
                        "type": "association_task", "task": "release_animal", "value": 5,
                        "workers": 1, "project_card_id": project["id"], "level": level,
                        "card_id": card["id"], "enclosure_id": card["enclosure_id"],
                    })
    return actions


def _association_actions(
    state: dict[str, Any], player: dict[str, Any], strength: int,
    excluded_tasks: set[str] | None = None,
) -> list[dict[str, Any]]:
    if player["association_workers"]["active"] < 1:
        return []
    actions = []
    excluded_tasks = excluded_tasks or set()
    if strength >= 2 and "reputation" not in excluded_tasks:
        actions.append({"type": "association_task", "task": "reputation", "value": 2,
                        "workers": 1})
    association_upgraded = next(
        card["upgraded"] for card in player["action_cards"]
        if card["action"] == "association"
    )
    can_take_partner_zoo = len(player["partner_zoos"]) < 2 or association_upgraded
    if strength >= 3 and can_take_partner_zoo and "partner_zoo" not in excluded_tasks:
        for continent, available in state["association_board"]["partner_zoos"].items():
            if available and continent not in player["partner_zoos"]:
                actions.append({"type": "association_task", "task": "partner_zoo", "value": 3,
                                "workers": 1, "continent": continent})
    if strength >= 4 and "university" not in excluded_tasks:
        for university, available in state["association_board"]["universities"].items():
            if available and university not in player["universities"]:
                actions.append({"type": "association_task", "task": "university", "value": 4,
                                "workers": 1, "university": university})
    if strength >= 5 and player["conservation_tokens_on_map"] and "conservation" not in excluded_tasks:
        for project in state["base_conservation_projects"]:
            if project.get("project_kind", "tag") != "tag":
                continue
            claimed = {claim["level"] for claim in project["claims"]}
            for level in project["levels"]:
                if level <= _tag_count(player, project["tag"]) and level not in claimed:
                    actions.append({"type": "association_task", "task": "conservation_project",
                                    "value": 5, "workers": 1, "project_id": project["id"],
                                    "level": level})
        actions.extend(_release_project_actions(state, player))
    return actions


def _can_start_action(state: dict[str, Any], player: dict[str, Any], name: str, strength: int) -> bool:
    if name == "cards":
        return bool(state["zoo_deck"] or state["zoo_discard"] or state["card_display"])
    if name == "build":
        return bool(_build_actions(player, strength, _action_card(player, "build")["upgraded"]))
    if name == "animals":
        return bool(_playable_animals(state, player, _action_card(player, "animals")["upgraded"]))
    if name == "association":
        return bool(_association_actions(state, player, strength))
    return True  # Sponsors can always advance Break and gain money.


def legal_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    if state["status"] != "active" or seat != state["active_seat"]:
        return []
    player = state["players"][seat]
    phase = state["phase"]
    if phase == "initial_hand_selection":
        actions = [{"type": "choose_initial_hand", "card_ids": sorted(card["id"] for card in chosen)}
                   for chosen in combinations(player["initial_draw"], player["initial_keep_required"])]
        return _wrap_actions(state, actions)
    if phase == "choose_action":
        actions = []
        for card in sorted(player["action_cards"], key=lambda item: item["strength"]):
            for x_tokens in range(player["x_tokens"] + 1):
                strength = card["strength"] + x_tokens
                if card["action"] == "animals" and card["upgraded"] and strength >= 5:
                    strength += 1
                if _can_start_action(state, player, card["action"], strength):
                    actions.append({"type": "select_action", "action_card": card["action"],
                                    "base_strength": card["strength"], "x_tokens": x_tokens,
                                    "strength": strength})
            if player["x_tokens"] < 5:
                actions.append({"type": "take_x_token", "action_card": card["action"]})
        return _wrap_actions(state, actions)
    pending = state["pending_action"] or {}
    strength = pending.get("strength", 0)
    if phase == "cards_choose":
        draw_count = ((strength + 1) // 2) + (1 if pending.get("upgraded", False) else 0)
        discard_count = 1 if (strength % 2 or pending.get("upgraded", False)) else 0
        actions = [{"type": "draw_cards", "draw_count": min(4, draw_count),
                    "discard_count": discard_count}]
        snap_at = 3 if pending.get("upgraded") else 5
        if strength >= snap_at:
            actions.extend({"type": "snap_card", "card_id": card["id"]}
                           for slot, card in enumerate(state["card_display"], 1)
                           if slot <= reputation_display_slot(player["reputation"]))
        actions.append({"type": "cancel_action", "action_card": "cards"})
        return _wrap_actions(state, actions)
    if phase == "cards_discard":
        return _wrap_actions(state, [{"type": "discard_card", "card_id": card["id"]}
                                     for card in player["hand"]])
    if phase == "build_place":
        actions = _build_actions(
            player, pending.get("remaining_strength", strength), pending.get("upgraded", False),
            set(pending.get("built_types", [])),
        )
        if pending.get("builds_done", 0) > 0:
            actions.append({"type": "finish_action"})
        else:
            actions.append({"type": "cancel_action", "action_card": "build"})
        return _wrap_actions(state, actions)
    if phase == "animals_play":
        actions = _playable_animals(state, player, pending.get("upgraded", False))
        if pending.get("plays_done", 0) > 0:
            actions.append({"type": "finish_action"})
        else:
            actions.append({"type": "cancel_action", "action_card": "animals"})
        return _wrap_actions(state, actions)
    if phase == "association_task":
        actions = _association_actions(
            state, player, pending.get("remaining_strength", strength),
            set(pending.get("tasks_done", [])),
        )
        if pending.get("upgraded", False) and pending.get("tasks_done"):
            actions.append({"type": "finish_association_tasks"})
        if not pending.get("tasks_done"):
            actions.append({"type": "cancel_action", "action_card": "association"})
        return _wrap_actions(state, actions)
    if phase == "association_donation":
        actions = [{"type": "finish_action"}]
        cost = _donation_cost(state)
        if cost is not None and player["money"] >= cost and player["conservation_tokens_on_map"]:
            actions.insert(0, {"type": "make_donation", "cost": cost})
        return _wrap_actions(state, actions)
    if phase == "sponsors_choose":
        actions = ([{"type": "advance_break", "steps": strength,
                     "money": strength * (2 if pending.get("upgraded", False) else 1)}]
                   if not pending.get("sponsors_played") else [{"type": "finish_action"}])
        remaining_strength = pending.get("remaining_strength", strength + (1 if pending.get("upgraded") else 0))
        actions.extend({"type": "play_sponsor", "card_id": card["id"]}
                       for card in player["hand"]
                       if card["card_type"] == "sponsor" and card["level"] <= remaining_strength)
        if pending.get("upgraded", False):
            maximum_slot = reputation_display_slot(player["reputation"])
            actions.extend({"type": "play_sponsor", "card_id": card["id"],
                            "source": "display", "display_slot": slot}
                           for slot, card in enumerate(state["card_display"], 1)
                           if slot <= maximum_slot and card["card_type"] == "sponsor"
                           and card["level"] <= remaining_strength)
        if not pending.get("sponsors_played"):
            actions.append({"type": "cancel_action", "action_card": "sponsors"})
        return _wrap_actions(state, actions)
    if phase == "break_discard":
        limit = 5 if "hand-limit-5" in player["universities"] else 3
        surplus = len(player["hand"]) - limit
        actions = [{"type": "break_discard", "card_ids": sorted(card["id"] for card in chosen)}
                   for chosen in combinations(player["hand"], surplus)] if surplus > 0 else []
        return _wrap_actions(state, actions)
    if phase == "choose_action_upgrade":
        return _wrap_actions(state, _upgrade_actions(player))
    if phase == "choose_conservation_bonus":
        actions = [{"type": "choose_conservation_bonus", "choice": "money", "amount": 5}]
        actions.extend({"type": "choose_conservation_bonus", "choice": "bonus_tile",
                        "tile_id": tile["id"]} for tile in state["game_board_bonus_tiles"])
        return _wrap_actions(state, actions)
    if phase == "choose_map_card":
        actions = []
        if state["zoo_deck"] or state["zoo_discard"]:
            actions.append({"type": "take_map_card", "source": "deck"})
        maximum_slot = reputation_display_slot(player["reputation"])
        actions.extend({
            "type": "take_map_card", "source": "display", "card_id": card["id"],
            "display_slot": slot,
        } for slot, card in enumerate(state["card_display"], 1) if slot <= maximum_slot)
        return _wrap_actions(state, actions)
    if phase == "choose_clever_action":
        return _wrap_actions(state, [{
            "type": "clever_action_card", "action_card": card["action"], "target_strength": 1,
        } for card in sorted(player["action_cards"], key=lambda item: item["strength"])])
    if phase == "choose_final_card":
        return _wrap_actions(state, [{"type": "keep_final_card", "card_id": card["id"]}
                                     for card in player["final_scoring_cards"]])
    return []


def _set_phase(state: dict[str, Any], phase: str, decision: str, *, action_card: str | None = None,
               remaining_plays: int = 0) -> None:
    state["phase"] = phase
    state["turn"] = DecisionStep(
        active_seat=state["active_seat"], decision=decision, phase=phase,
        action_card=action_card, remaining_plays=remaining_plays,
    ).to_dict()


def _move_action_card(player: dict[str, Any], name: str) -> None:
    chosen = _action_card(player, name)
    old_strength = chosen["strength"]
    for card in player["action_cards"]:
        if card["strength"] < old_strength:
            card["strength"] += 1
    chosen["strength"] = 1


def _draw_zoo_card(state: dict[str, Any]) -> dict[str, Any] | None:
    if not state["zoo_deck"] and state["zoo_discard"]:
        state["recycle_count"] += 1
        deck = state["zoo_discard"]
        state["zoo_discard"] = []
        random.Random(state["seed"] + 10_000 * state["recycle_count"]).shuffle(deck)
        state["zoo_deck"] = deck
    return state["zoo_deck"].pop() if state["zoo_deck"] else None


def _refill_display(state: dict[str, Any]) -> None:
    while len(state["card_display"]) < 6:
        card = _draw_zoo_card(state)
        if card is None:
            return
        state["card_display"].append(card)


def _move_break(state: dict[str, Any], steps: int) -> int:
    return advance_track(state["break_track"], steps)


def _controlled_income(player: dict[str, Any]) -> int:
    appeal_money = appeal_income(player["appeal"])
    sponsor_income = sum(card.get("income", 0) for card in player["played_cards"]
                         if card["card_type"] == "sponsor")
    return appeal_money + sponsor_income


def _gain_reputation(
    state: dict[str, Any], player: dict[str, Any], amount: int,
    events: list[dict[str, Any]], source_id: str,
) -> int:
    """Advance Reputation, applying its gate, printed rewards, and overflow."""

    before = player["reputation"]
    requested_target = before + max(0, amount)
    cards_upgraded = _action_card(player, "cards")["upgraded"]
    gated_target = (min(REPUTATION_CARDS_GATE - 1, requested_target)
                    if before < REPUTATION_CARDS_GATE and not cards_upgraded
                    else requested_target)
    target = min(REPUTATION_MAXIMUM, gated_target)
    player["reputation"] = target

    for milestone in range(before + 1, target + 1):
        if milestone == REPUTATION_UPGRADE_MILESTONE:
            _queue_upgrade_source(state, player, "reputation")
        elif milestone == 8:
            workers = player["association_workers"]
            if workers["reserve"]:
                workers["reserve"] -= 1
                workers["active"] += 1
        elif milestone in (10, 13):
            state["pending_rewards"].append({
                "type": "map_take_card", "seat": player["seat"],
                "source_id": f"reputation:{milestone}",
            })
        elif milestone in (11, 14):
            conservation_before = player["conservation"]
            adjust_resources(player, {"conservation": 1})
            _queue_conservation_rewards(state, player, conservation_before)
        elif milestone in (12, 15):
            player["x_tokens"] = min(5, player["x_tokens"] + 1)

    overflow = max(0, gated_target - REPUTATION_MAXIMUM)
    if overflow:
        adjust_resources(player, {"appeal": overflow})
    gained = target - before
    events.append({
        "type": "reputation_advanced", "seat": player["seat"], "source_id": source_id,
        "before": before, "after": target, "gained": gained, "appeal_overflow": overflow,
        "cards_ii_gate_blocked": requested_target > gated_target,
    })
    return gained


def _apply_effects(
    state: dict[str, Any], player: dict[str, Any], effects: list[dict[str, Any]],
    events: list[dict[str, Any]], source_id: str,
) -> None:
    applied = []
    for effect in effects:
        kind = effect["type"]
        amount = effect["amount"]
        if kind == "gain_money":
            adjust_resources(player, {"money": amount})
        elif kind == "gain_appeal":
            adjust_resources(player, {"appeal": amount})
        elif kind == "gain_conservation":
            adjust_resources(player, {"conservation": amount})
        elif kind == "gain_reputation":
            amount = _gain_reputation(state, player, amount, events, source_id)
        elif kind == "gain_x_token":
            before = player["x_tokens"]
            player["x_tokens"] = min(5, before + amount)
            amount = player["x_tokens"] - before
        elif kind == "move_break":
            _move_break(state, amount)
        elif kind == "draw_cards":
            drawn = []
            for _ in range(amount):
                card = _draw_zoo_card(state)
                if card:
                    player["hand"].append(card)
                    drawn.append(card["id"])
            amount = len(drawn)
        else:  # pragma: no cover - generated content is validated below
            raise RuleError(f"unsupported controlled effect: {kind}")
        applied.append({"type": kind, "amount": amount})
    if applied:
        events.append({"type": "effects_resolved", "seat": player["seat"],
                       "source_id": source_id, "effects": applied})


def _resolve_map_bonuses(
    state: dict[str, Any], player: dict[str, Any], cells: list[dict[str, int]],
    events: list[dict[str, Any]],
) -> None:
    by_coordinate = {(cell["q"], cell["r"]): cell for cell in player["map"]["cells"]}
    for coordinate in ((cell["q"], cell["r"]) for cell in cells):
        map_cell = by_coordinate[coordinate]
        bonus = map_cell.pop("placement_bonus", None)
        if bonus:
            source_id = f"map:{coordinate[0]}:{coordinate[1]}"
            if bonus["type"] == "take_card":
                state["pending_rewards"].append({
                    "type": "map_take_card", "seat": player["seat"], "source_id": source_id,
                })
            elif bonus["type"] == "clever":
                state["pending_rewards"].append({
                    "type": "map_clever", "seat": player["seat"], "source_id": source_id,
                    "target_strength": bonus["target_strength"],
                })
            else:
                _apply_effects(state, player, [bonus], events, source_id)
    buildable = {
        (cell["q"], cell["r"]) for cell in player["map"]["cells"]
        if cell["terrain"] == "buildable"
    }
    occupied = _occupied_cells(player)
    if buildable <= occupied and not player["map"].get("completion_reward_claimed", False):
        reward = player["map"].get("completion_reward")
        if reward:
            player["map"]["completion_reward_claimed"] = True
            _apply_effects(state, player, [reward], events, "map:completion")
            events.append({"type": "zoo_map_completed", "seat": player["seat"],
                           "reward": deepcopy(reward)})


def _queue_conservation_rewards(
    state: dict[str, Any], player: dict[str, Any], before: int,
) -> None:
    for milestone in ACTION_UPGRADE_MILESTONES:
        if before < milestone <= player["conservation"] and milestone not in player["upgrade_rewards_claimed"]:
            player["upgrade_rewards_claimed"].append(milestone)
            state["pending_rewards"].append({"type": "action_upgrade", "seat": player["seat"],
                                             "milestone": milestone})
    for milestone in CONSERVATION_BONUS_MILESTONES:
        if (before < milestone <= player["conservation"]
                and milestone not in player["conservation_rewards_claimed"]):
            player["conservation_rewards_claimed"].append(milestone)
            state["pending_rewards"].append({"type": "conservation_bonus", "seat": player["seat"],
                                             "milestone": milestone})
    if (before < FINAL_CARD_CHOICE_CONSERVATION <= player["conservation"]
            and not player["final_card_choice_resolved"]
            and len(player["final_scoring_cards"]) > 1):
        for other in state["players"]:
            if not other["final_card_choice_resolved"] and len(other["final_scoring_cards"]) > 1:
                state["pending_rewards"].append({"type": "final_card_choice", "seat": other["seat"]})


def _queue_upgrade_source(state: dict[str, Any], player: dict[str, Any], source: str) -> None:
    if source not in player["upgrade_sources_claimed"] and _upgrade_actions(player):
        player["upgrade_sources_claimed"].append(source)
        state["pending_rewards"].append({"type": "action_upgrade", "seat": player["seat"],
                                         "milestone": source})


def _begin_pending_reward(state: dict[str, Any]) -> bool:
    if not state["pending_rewards"]:
        return False
    reward = state["pending_rewards"][0]
    state["active_seat"] = reward["seat"]
    if reward["type"] == "action_upgrade":
        _set_phase(state, "choose_action_upgrade", "choose_action_card_to_upgrade")
    elif reward["type"] == "conservation_bonus":
        _set_phase(state, "choose_conservation_bonus", "choose_conservation_track_bonus")
    elif reward["type"] == "map_take_card":
        _set_phase(state, "choose_map_card", "choose_map_card_from_reputation_range")
    elif reward["type"] == "map_clever":
        _set_phase(state, "choose_clever_action", "choose_action_card_for_clever")
    elif reward["type"] == "final_card_choice":
        _set_phase(state, "choose_final_card", "choose_final_scoring_card")
    else:  # pragma: no cover - state validation guards pending reward kinds
        raise RuleError(f"unsupported pending reward: {reward['type']}")
    return True


def _resolve_break(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    for player in state["players"]:
        for card in player["action_cards"]:
            card["tokens"] = []
        workers = player["association_workers"]
        workers["active"] += sum(item.get("workers", 1) for item in workers["committed"])
        workers["committed"] = []
    for continent in CONTINENTS:
        state["association_board"]["partner_zoos"][continent] = int(
            not all(continent in player["partner_zoos"] for player in state["players"])
        )
    for university in state["association_board"]["universities"]:
        state["association_board"]["universities"][university] = int(
            not all(university in player["universities"] for player in state["players"])
        )
    removed = state["card_display"][:2]
    state["card_display"] = state["card_display"][2:]
    state["zoo_discard"].extend(removed)
    _refill_display(state)
    incomes = []
    for player in state["players"]:
        amount = _controlled_income(player)
        adjust_resources(player, {"money": amount})
        incomes.append({"seat": player["seat"], "money": amount})
    reset_track(state["break_track"])
    state["break_track"]["next_seat"] = None
    events.append({"type": "break_resolved", "income": incomes})
    _set_phase(state, "choose_action", "choose_action_card")


def _begin_or_resolve_break(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    for player in state["players"]:
        limit = 5 if "hand-limit-5" in player["universities"] else 3
        if len(player["hand"]) > limit:
            state["active_seat"] = player["seat"]
            _set_phase(state, "break_discard", "discard_to_hand_limit")
            return
    state["active_seat"] = state["break_track"]["next_seat"]
    _resolve_break(state, events)


def _controlled_end_triggered(player: dict[str, Any]) -> bool:
    return scoring_tracks_crossed(player["appeal"], player["conservation"])


def _finish_player_turn(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    player = state["players"][state["active_seat"]]
    pending = state["pending_action"]
    if pending:
        _move_action_card(player, pending["action_card"])
    _refill_display(state)
    state["pending_action"] = None
    state["turn_count"] += 1
    if state["end_after_turn"] is None and _controlled_end_triggered(player):
        state["end_after_turn"] = ((state["turn_count"] - 1) // state["player_count"] + 1) * state["player_count"]
        state["end_reason"] = "controlled_score_threshold"
    if state["turn_count"] >= state["turn_limit"] and state["end_after_turn"] is None:
        state["end_after_turn"] = state["turn_count"]
        state["end_reason"] = "controlled_turn_limit"
    if state["end_after_turn"] is not None and state["turn_count"] >= state["end_after_turn"]:
        for other in state["players"]:
            if not other["final_card_choice_resolved"] and len(other["final_scoring_cards"]) > 1:
                state["pending_rewards"].append({"type": "final_card_choice", "seat": other["seat"],
                                                 "resume_seat": 0, "finish_after": True})
        if state["pending_rewards"]:
            _begin_pending_reward(state)
            return
        state["status"] = "finished"
        _set_phase(state, "finished", "finished")
        events.append({"type": "match_end_triggered", "reason": state["end_reason"]})
        return
    next_seat = state["turn_count"] % state["player_count"]
    if state["pending_rewards"]:
        for reward in state["pending_rewards"]:
            reward["resume_seat"] = next_seat
        _begin_pending_reward(state)
        return
    if state["break_track"]["triggered"]:
        state["break_track"]["next_seat"] = next_seat
        events.append({"type": "break_triggered", "seat": player["seat"]})
        _begin_or_resolve_break(state, events)
    else:
        state["active_seat"] = next_seat
        _set_phase(state, "choose_action", "choose_action_card")


def _finish_selected_action(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    _finish_player_turn(state, events)


def _canonical_action(state: dict[str, Any], seat: int, action: dict[str, Any]) -> dict[str, Any]:
    legal = [item["action"] for item in legal_actions(state, seat)]
    return _action_space(state, legal).require(
        action, error_factory=RuleError, message="action is not legal in the current decision step",
    )


def apply_action(state: dict[str, Any], seat: int, action: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    action = _canonical_action(state, seat, action)
    next_state = deepcopy(state)
    player = next_state["players"][seat]
    phase = next_state["phase"]
    kind = action["type"]
    events: list[dict[str, Any]] = [action_accepted(
        seat, action, decision=next_state["turn"]["decision"],
    )]
    next_state["decision_count"] += 1

    if kind == "cancel_action":
        pending = next_state["pending_action"] or {}
        player["x_tokens"] += pending.get("x_tokens", 0)
        if pending.get("action_card") == "cards":
            track = next_state["break_track"]
            track["position"] = max(0, track["position"] - pending.get("break_steps", 0))
            track["triggered"] = track["position"] >= track["limit"]
        cancelled = pending.get("action_card")
        next_state["pending_action"] = None
        _set_phase(next_state, "choose_action", "choose_action_card")
        events.append({"type": "selected_action_cancelled", "seat": seat,
                       "action_card": cancelled})
    elif phase == "choose_action_upgrade":
        card = _action_card(player, action["action_card"])
        card["upgraded"] = True
        reward = next_state["pending_rewards"].pop(0)
        events.append({"type": "action_card_upgraded", "seat": seat,
                       "action_card": card["action"], "milestone": reward["milestone"]})
        if not _begin_pending_reward(next_state):
            next_state["active_seat"] = reward["resume_seat"]
            _set_phase(next_state, "choose_action", "choose_action_card")
    elif phase == "choose_conservation_bonus":
        reward = next_state["pending_rewards"].pop(0)
        if action["choice"] == "money":
            adjust_resources(player, {"money": action["amount"]})
        else:
            tile = next(tile for tile in next_state["game_board_bonus_tiles"]
                        if tile["id"] == action["tile_id"])
            next_state["game_board_bonus_tiles"].remove(tile)
            next_state["unused_bonus_tiles"].append(tile)
            _apply_effects(next_state, player, tile["effects"], events, tile["id"])
        events.append({"type": "conservation_bonus_chosen", "seat": seat,
                       "milestone": reward["milestone"], "choice": action["choice"]})
        if not _begin_pending_reward(next_state):
            next_state["active_seat"] = reward["resume_seat"]
            _set_phase(next_state, "choose_action", "choose_action_card")
    elif phase == "choose_map_card":
        reward = next_state["pending_rewards"].pop(0)
        if action["source"] == "display":
            card = next(card for card in next_state["card_display"] if card["id"] == action["card_id"])
            next_state["card_display"].remove(card)
            player["hand"].append(card)
            _refill_display(next_state)
        else:
            card = _draw_zoo_card(next_state)
            if card is None:  # pragma: no cover - legal action requires a drawable card
                raise RuleError("no zoo card is available")
            player["hand"].append(card)
        events.append({
            "type": "map_card_taken", "seat": seat, "card_id": card["id"],
            "source": action["source"], "source_id": reward["source_id"],
        })
        if not _begin_pending_reward(next_state):
            next_state["active_seat"] = reward["resume_seat"]
            _set_phase(next_state, "choose_action", "choose_action_card")
    elif phase == "choose_clever_action":
        reward = next_state["pending_rewards"].pop(0)
        _move_action_card(player, action["action_card"])
        events.append({
            "type": "map_clever_resolved", "seat": seat,
            "action_card": action["action_card"], "target_strength": reward["target_strength"],
            "source_id": reward["source_id"],
        })
        if not _begin_pending_reward(next_state):
            next_state["active_seat"] = reward["resume_seat"]
            _set_phase(next_state, "choose_action", "choose_action_card")
    elif phase == "choose_final_card":
        kept = action["card_id"]
        discarded = [card for card in player["final_scoring_cards"] if card["id"] != kept]
        player["final_scoring_cards"] = [card for card in player["final_scoring_cards"] if card["id"] == kept]
        next_state["final_scoring_deck"].extend(discarded)
        player["final_card_choice_resolved"] = True
        reward = next_state["pending_rewards"].pop(0)
        events.append({"type": "final_scoring_card_chosen", "seat": seat, "card_id": kept})
        if not _begin_pending_reward(next_state):
            if reward.get("finish_after"):
                next_state["status"] = "finished"
                _set_phase(next_state, "finished", "finished")
                events.append({"type": "match_end_triggered", "reason": next_state["end_reason"]})
            else:
                next_state["active_seat"] = reward["resume_seat"]
                _set_phase(next_state, "choose_action", "choose_action_card")
    elif phase == "initial_hand_selection":
        selected = set(action["card_ids"])
        player["hand"] = [card for card in player["initial_draw"] if card["id"] in selected]
        discarded = [card for card in player["initial_draw"] if card["id"] not in selected]
        next_state["zoo_discard"].extend(discarded)
        player["initial_draw"] = []
        events.append({"type": "initial_hand_chosen", "seat": seat, "kept": len(selected),
                       "discarded": len(discarded)})
        unfinished = [row["seat"] for row in next_state["players"] if row["initial_draw"]]
        if unfinished:
            next_state["active_seat"] = unfinished[0]
            _set_phase(next_state, "initial_hand_selection", "choose_initial_hand")
        else:
            next_state["active_seat"] = 0
            _set_phase(next_state, "choose_action", "choose_action_card")
            events.append({"type": "setup_completed"})
    elif phase == "choose_action":
        if kind == "take_x_token":
            _move_action_card(player, action["action_card"])
            player["x_tokens"] += 1
            next_state["pending_action"] = None
            _finish_player_turn(next_state, events)
        else:
            card = _action_card(player, action["action_card"])
            player["x_tokens"] -= action["x_tokens"]
            next_state["pending_action"] = {
                "action_card": action["action_card"], "strength": action["strength"],
                "base_strength": action["base_strength"], "x_tokens": action["x_tokens"],
                "upgraded": card["upgraded"], "plays_done": 0,
            }
            if card["upgraded"] and card["action"] == "build":
                next_state["pending_action"].update({"remaining_strength": action["strength"],
                                                     "builds_done": 0, "built_types": []})
            elif card["upgraded"] and card["action"] == "association":
                next_state["pending_action"].update({"remaining_strength": action["strength"],
                                                     "tasks_done": []})
            elif card["upgraded"] and card["action"] == "sponsors":
                next_state["pending_action"].update({"remaining_strength": action["strength"] + 1,
                                                     "sponsors_played": 0})
            phase_for = {"cards": ("cards_choose", "choose_cards_mode"),
                         "build": ("build_place", "place_building"),
                         "animals": ("animals_play", "choose_animal"),
                         "association": ("association_task", "choose_association_task"),
                         "sponsors": ("sponsors_choose", "choose_sponsor_or_break")}
            new_phase, decision = phase_for[action["action_card"]]
            if action["action_card"] == "cards":
                next_state["pending_action"]["break_steps"] = _move_break(next_state, 2)
            remaining = 2 if action["action_card"] == "animals" and action["strength"] >= 5 else 1
            _set_phase(next_state, new_phase, decision, action_card=action["action_card"],
                       remaining_plays=remaining)
    elif phase == "cards_choose":
        if kind == "snap_card":
            card = next(card for card in next_state["card_display"] if card["id"] == action["card_id"])
            next_state["card_display"].remove(card)
            player["hand"].append(card)
            events.append({"type": "card_snapped", "seat": seat, "card_id": card["id"]})
            _finish_selected_action(next_state, events)
        else:
            drawn = []
            for _ in range(action["draw_count"]):
                card = _draw_zoo_card(next_state)
                if card:
                    player["hand"].append(card)
                    drawn.append(card["id"])
            events.append({"type": "cards_drawn", "seat": seat, "count": len(drawn)})
            if action["discard_count"] and player["hand"]:
                _set_phase(next_state, "cards_discard", "discard_after_cards", action_card="cards")
            else:
                _finish_selected_action(next_state, events)
    elif phase == "cards_discard":
        card = next(card for card in player["hand"] if card["id"] == action["card_id"])
        player["hand"].remove(card)
        next_state["zoo_discard"].append(card)
        events.append({"type": "card_discarded", "seat": seat, "card_id": card["id"]})
        _finish_selected_action(next_state, events)
    elif phase == "build_place":
        if kind == "finish_action":
            _finish_selected_action(next_state, events)
            validate_state(next_state)
            return next_state, events
        building = {"id": f"building-{player['map']['next_building_id']}",
                    "type": action["building_type"], "size": action["size"],
                    "shape_id": action["shape_id"], "rotation": action["rotation"],
                    "occupied": False, "cells": action["cells"]}
        player["map"]["next_building_id"] += 1
        player["map"]["buildings"].append(building)
        adjust_resources(player, {"money": -action["cost"]})
        if action["building_type"] == "pavilion":
            adjust_resources(player, {"appeal": 1})
        _resolve_map_bonuses(next_state, player, action["cells"], events)
        events.append({"type": "building_placed", "seat": seat, "building": building,
                       "cost": action["cost"]})
        if next_state["pending_action"].get("upgraded"):
            next_state["pending_action"]["remaining_strength"] -= action["size"]
            next_state["pending_action"]["builds_done"] += 1
            next_state["pending_action"]["built_types"].append(action["building_type"])
            if _build_actions(
                player, next_state["pending_action"]["remaining_strength"], True,
                set(next_state["pending_action"]["built_types"]),
            ):
                _set_phase(next_state, "build_place", "place_building", action_card="build")
            else:
                _finish_selected_action(next_state, events)
        else:
            _finish_selected_action(next_state, events)
    elif phase == "animals_play":
        if kind == "finish_action":
            _finish_selected_action(next_state, events)
        else:
            source = next_state["card_display"] if action.get("source") == "display" else player["hand"]
            card = next(card for card in source if card["id"] == action["card_id"])
            enclosure = next(building for building in player["map"]["buildings"]
                             if building["id"] == action["enclosure_id"])
            move_item(source, player["played_cards"], card["id"])
            played = {**card, "enclosure_id": enclosure["id"]}
            player["played_cards"][-1] = played
            enclosure["occupied"] = True
            conservation_before = player["conservation"]
            adjust_resources(player, {
                "money": -action["cost"], "appeal": card["appeal"],
                "conservation": card["conservation"],
            })
            if card["reputation"]:
                _gain_reputation(next_state, player, card["reputation"], events, card["id"])
            _apply_effects(next_state, player, card.get("effects", []), events, card["id"])
            _queue_conservation_rewards(next_state, player, conservation_before)
            next_state["pending_action"]["plays_done"] += 1
            remaining = (2 if next_state["pending_action"]["strength"] >= 5 else 1) - next_state["pending_action"]["plays_done"]
            events.append({"type": "animal_played", "seat": seat, "card_id": card["id"],
                           "enclosure_id": enclosure["id"]})
            if remaining > 0 and _playable_animals(
                next_state, player, next_state["pending_action"].get("upgraded", False),
            ):
                _set_phase(next_state, "animals_play", "choose_animal", action_card="animals",
                           remaining_plays=remaining)
            else:
                _finish_selected_action(next_state, events)
    elif phase == "association_task":
        if kind == "finish_association_tasks":
            _set_phase(next_state, "association_donation", "choose_optional_donation",
                       action_card="association")
            validate_state(next_state)
            return next_state, events
        task = action["task"]
        workers = player["association_workers"]
        workers["active"] -= action["workers"]
        workers["committed"].append({"task": task, "workers": action["workers"]})
        conservation_before = player["conservation"]
        if task == "reputation":
            _gain_reputation(next_state, player, 2, events, "association:reputation")
        elif task == "partner_zoo":
            player["partner_zoos"].append(action["continent"])
            next_state["association_board"]["partner_zoos"][action["continent"]] = 0
            if len(player["partner_zoos"]) == 2:
                _queue_upgrade_source(next_state, player, "second_partner_zoo")
            elif len(player["partner_zoos"]) == 3 and workers["reserve"]:
                workers["reserve"] -= 1
                workers["active"] += 1
            elif len(player["partner_zoos"]) == 4:
                adjust_resources(player, {"conservation": 2})
        elif task == "university":
            university = action["university"]
            player["universities"].append(university)
            next_state["association_board"]["universities"][university] = 0
            if university == "research-reputation":
                _gain_reputation(next_state, player, 2, events, f"university:{university}")
            if len(player["universities"]) == 2:
                _queue_upgrade_source(next_state, player, "second_university")
            elif len(player["universities"]) == 3:
                adjust_resources(player, {"conservation": 2})
        elif task == "conservation_project":
            project = next(project for project in next_state["base_conservation_projects"]
                           if project["id"] == action["project_id"])
            reward = {2: 2, 4: 3, 5: 4}[action["level"]]
            project["claims"].append({"seat": seat, "level": action["level"]})
            player["supported_projects"].append(project["id"])
            adjust_resources(player, {"conservation_tokens_on_map": -1, "conservation": reward})
        else:  # release_animal
            project_card = next(card for card in player["hand"]
                                if card["id"] == action["project_card_id"])
            player["hand"].remove(project_card)
            player["played_cards"].append(project_card)
            animal = next(card for card in player["played_cards"] if card["id"] == action["card_id"])
            player["played_cards"].remove(animal)
            next_state["zoo_discard"].append(animal)
            enclosure = next(building for building in player["map"]["buildings"]
                             if building["id"] == action["enclosure_id"])
            enclosure["occupied"] = False
            reward = {2: 2, 4: 3, 5: 4}[action["level"]]
            player["supported_projects"].append(project_card["id"])
            adjust_resources(player, {"conservation_tokens_on_map": -1,
                                      "conservation": reward, "appeal": -animal["appeal"]})
            events.append({"type": "animal_released", "seat": seat, "card_id": animal["id"],
                           "project_card_id": project_card["id"]})
        _queue_conservation_rewards(next_state, player, conservation_before)
        events.append({"type": "association_task_completed", "seat": seat, "task": task})
        if _action_card(player, "association")["upgraded"]:
            task_group = "conservation" if task in ("conservation_project", "release_animal") else task
            next_state["pending_action"]["remaining_strength"] -= action["value"]
            next_state["pending_action"]["tasks_done"].append(task_group)
            if _association_actions(
                next_state, player, next_state["pending_action"]["remaining_strength"],
                set(next_state["pending_action"]["tasks_done"]),
            ):
                _set_phase(next_state, "association_task", "choose_association_task",
                           action_card="association")
            else:
                _set_phase(next_state, "association_donation", "choose_optional_donation",
                           action_card="association")
        else:
            _finish_selected_action(next_state, events)
    elif phase == "association_donation":
        if kind == "make_donation":
            conservation_before = player["conservation"]
            adjust_resources(player, {"money": -action["cost"], "conservation_tokens_on_map": -1,
                                      "conservation": 1})
            next_state["association_board"]["donations"].append({"seat": seat, "cost": action["cost"]})
            _queue_conservation_rewards(next_state, player, conservation_before)
            events.append({"type": "donation_made", "seat": seat, "cost": action["cost"]})
        _finish_selected_action(next_state, events)
    elif phase == "sponsors_choose":
        if kind == "finish_action":
            _finish_selected_action(next_state, events)
        elif kind == "advance_break":
            _move_break(next_state, action["steps"])
            adjust_resources(player, {"money": action["money"]})
            events.append({"type": "sponsors_break_advanced", "seat": seat,
                           "steps": action["steps"], "money": action["money"]})
        else:
            if action.get("source") == "display":
                card = move_item(next_state["card_display"], player["played_cards"], action["card_id"])
            else:
                card = move_item(player["hand"], player["played_cards"], action["card_id"])
            adjust_resources(player, {"appeal": card["appeal"]})
            _apply_effects(next_state, player, card.get("effects", []), events, card["id"])
            events.append({"type": "sponsor_played", "seat": seat, "card_id": card["id"]})
        if kind == "play_sponsor" and next_state["pending_action"].get("upgraded"):
            next_state["pending_action"]["remaining_strength"] -= card["level"]
            next_state["pending_action"]["sponsors_played"] += 1
            _set_phase(next_state, "sponsors_choose", "choose_sponsor_or_break",
                       action_card="sponsors")
        else:
            _finish_selected_action(next_state, events)
    elif phase == "break_discard":
        selected = set(action["card_ids"])
        discarded = [card for card in player["hand"] if card["id"] in selected]
        player["hand"] = [card for card in player["hand"] if card["id"] not in selected]
        next_state["zoo_discard"].extend(discarded)
        events.append({"type": "break_cards_discarded", "seat": seat, "count": len(discarded)})
        _begin_or_resolve_break(next_state, events)
    else:  # pragma: no cover
        raise RuleError(f"unsupported decision phase: {phase}")
    validate_state(next_state)
    return next_state, events


def _final_card_points(player: dict[str, Any], card: dict[str, Any]) -> int:
    objective = card["objective"]
    if objective == "animal_tags":
        value = len({tag for played in player["played_cards"] if played.get("card_type") == "animal"
                     for tag in played.get("tags", [])})
    elif objective == "continents":
        value = len({played["continent"] for played in player["played_cards"]
                     if played.get("card_type") == "animal"})
    elif objective == "animals":
        value = sum(played.get("card_type") == "animal" for played in player["played_cards"])
    elif objective == "sponsors":
        value = sum(played.get("card_type") == "sponsor" for played in player["played_cards"])
    elif objective == "supported_projects":
        value = len(player["supported_projects"])
    else:
        value = sum(
            building.get("counts_for_controlled_scoring", True)
            for building in player["map"]["buildings"]
        )
    steps = value // card["per"]
    return min(card["maximum"], steps * card["points_per_step"])


def _controlled_score(player: dict[str, Any]) -> tuple[int, int]:
    base = player["appeal"] + 5 * player["conservation"] + player["reputation"] + len(player["played_cards"])
    card_scores = [_final_card_points(player, card) for card in player["final_scoring_cards"]]
    final = sum(card_scores) if player["final_card_choice_resolved"] else max(card_scores, default=0)
    return base, final


def rankings(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for player in state["players"]:
        base_score, final_card_points = _controlled_score(player)
        rows.append({"seat": player["seat"], "appeal": player["appeal"],
                     "conservation": player["conservation"], "reputation": player["reputation"],
                     "base_score": base_score, "final_card_points": final_card_points,
                     "controlled_score": base_score + final_card_points, "rank": None})
    return assign_competition_ranks(
        rows,
        sort_key=lambda row: (-row["controlled_score"], -row["conservation"], row["seat"]),
        tie_key=lambda row: (row["controlled_score"], row["conservation"]),
    )


def _observe(state: dict[str, Any], seat: int, *, reveal_all_private: bool) -> dict[str, Any]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    rows = []
    for player in state["players"]:
        own = reveal_all_private or player["seat"] == seat
        row = deepcopy(player)
        row["hand_count"] = len(player["hand"])
        row["initial_draw_count"] = len(player["initial_draw"])
        row["hand"] = private_items(player["hand"], own)
        row["initial_draw"] = private_items(player["initial_draw"], own)
        row["final_scoring_cards"] = private_items(player["final_scoring_cards"], own)
        row["public_summary"] = player_public_summary(player)
        row["map_display"] = map_display(player)
        rows.append(row)
    return {
        "game": "ark_nova", "rules_version": state["rules_version"],
        "implementation_status": state["implementation_status"], "viewer_seat": seat,
        "status": state["status"], "phase": state["phase"], "turn_count": state["turn_count"],
        "decision_count": state["decision_count"], "active_seat": state["active_seat"],
        "turn": deepcopy(state["turn"]), "break_track": deepcopy(state["break_track"]),
        "card_display": (_hidden_cards(len(state["card_display"]))
                         if state["phase"] == "initial_hand_selection" else deepcopy(state["card_display"])),
        "game_board_bonus_tiles": deepcopy(state["game_board_bonus_tiles"]),
        "deck_count": len(state["zoo_deck"]), "discard_count": len(state["zoo_discard"]),
        "base_conservation_projects": deepcopy(state["base_conservation_projects"]),
        "association_board": deepcopy(state["association_board"]),
        "association_display": association_display(state),
        "public_tracks": public_tracks(state), "players": rows,
        "rankings": rankings(state) if state["status"] == "finished" else None,
        "end_reason": state["end_reason"],
    }


def observe(state: dict[str, Any], seat: int) -> dict[str, Any]:
    """Return the seat-isolated observation used by human and agent players."""
    return _observe(state, seat, reveal_all_private=False)


def observe_spectator(state: dict[str, Any]) -> dict[str, Any]:
    """Return an omniscient view for the Web observer in agent-only matches.

    This function is deliberately separate from ``observe`` so the runner cannot
    accidentally include another seat's private cards in an agent prompt.
    """
    view = _observe(state, 0, reveal_all_private=True)
    view["viewer_mode"] = "spectator"
    return view


def validate_state(state: dict[str, Any]) -> None:
    if state.get("schema_version") != "agentbga.ark_nova.state.v2":
        raise AssertionError("invalid Ark Nova state schema")
    if state["player_count"] not in (2, 3, 4) or len(state["players"]) != state["player_count"]:
        raise AssertionError("invalid Ark Nova player count")
    if not 0 <= state["active_seat"] < state["player_count"]:
        raise AssertionError("invalid active seat")
    seen: list[str] = [card["id"] for card in state["card_display"] + state["zoo_deck"] + state["zoo_discard"]]
    for player in state["players"]:
        if (player["money"] < 0 or player["appeal"] < 0 or player["conservation"] < 0
                or not 0 <= player["reputation"] <= REPUTATION_MAXIMUM
                or not 0 <= player["x_tokens"] <= 5):
            raise AssertionError("invalid player resources")
        if sorted(card["strength"] for card in player["action_cards"]) != [1, 2, 3, 4, 5]:
            raise AssertionError("action cards must occupy strengths 1 through 5")
        if {card["action"] for card in player["action_cards"]} != set(ACTION_TYPES):
            raise AssertionError("player must have all five action cards")
        if len(player["upgrade_rewards_claimed"]) != len(set(player["upgrade_rewards_claimed"])) or any(
            milestone not in ACTION_UPGRADE_MILESTONES for milestone in player["upgrade_rewards_claimed"]
        ):
            raise AssertionError("invalid action upgrade rewards")
        seen.extend(card["id"] for card in player["hand"] + player["initial_draw"] + player["played_cards"])
        buildings = player["map"]["buildings"]
        building_cells = [(cell["q"], cell["r"]) for building in buildings for cell in building["cells"]]
        if len(building_cells) != len(set(building_cells)):
            raise AssertionError("map buildings overlap")
        terrain = {(cell["q"], cell["r"]): cell["terrain"] for cell in player["map"]["cells"]}
        if any(cell not in terrain or terrain[cell] != "buildable" for cell in building_cells):
            raise AssertionError("building occupies illegal terrain")
        if player["map"].get("schema_version") != "agentbga.ark_nova.map.v3":
            raise AssertionError("invalid Ark Nova map schema")
        if (player["map"].get("id") != "map-0"
                or player["map"].get("coordinate_system") != "flat_top_axial"
                or len(terrain) != 58
                or sum(value == "buildable" for value in terrain.values()) != 39
                or sum(value == "water" for value in terrain.values()) != 10
                or sum(value == "rock" for value in terrain.values()) != 9):
            raise AssertionError("invalid Map 0 geometry")
        build_ii_coordinates = {
            (cell["q"], cell["r"]) for cell in player["map"]["cells"]
            if cell.get("requires_build_upgrade", False)
        }
        if build_ii_coordinates != {(3, -2), (2, -1)}:
            raise AssertionError("invalid Map 0 Build II cells")
        if any(not valid_building_shape(building) for building in buildings):
            raise AssertionError("building does not match its fixed polyhex shape")
        placement_slots = player["map"].get("placement_bonus_slots", [])
        placement_coordinates = [(slot["q"], slot["r"]) for slot in placement_slots]
        if len(placement_coordinates) != 12 or len(placement_coordinates) != len(set(placement_coordinates)) or any(
            coordinate not in terrain for coordinate in placement_coordinates
        ):
            raise AssertionError("invalid map placement bonus slots")
        conservation_slots = player["map"].get("conservation_reward_slots", [])
        if [slot["milestone"] for slot in conservation_slots] != [2, 5, 8, 10]:
            raise AssertionError("invalid map conservation reward slots")
        if not isinstance(player["map"].get("completion_reward_claimed"), bool):
            raise AssertionError("invalid map completion reward state")
        workers = player["association_workers"]
        if workers["active"] < 0 or workers["active"] + workers["reserve"] + sum(
            item["workers"] for item in workers["committed"]
        ) != 4:
            raise AssertionError("association worker conservation failed")
    try:
        validate_unique_items([seen], expected_count=212, label="Ark Nova zoo cards")
    except AssertionError as error:
        raise AssertionError("Ark Nova must conserve all 212 unique zoo cards") from error
    bonus_seen = [tile["id"] for tile in state["game_board_bonus_tiles"] + state["unused_bonus_tiles"]]
    if len(bonus_seen) != 9 or len(bonus_seen) != len(set(bonus_seen)):
        raise AssertionError("invalid game-board bonus tiles")
    final_seen = [card["id"] for card in state["final_scoring_deck"]]
    for player in state["players"]:
        final_seen.extend(card["id"] for card in player["final_scoring_cards"])
    if len(final_seen) != 11 or len(final_seen) != len(set(final_seen)):
        raise AssertionError("invalid final scoring deck")
    projects = state["base_conservation_projects"] + state["base_conservation_deck"]
    if len(projects) != 12 or len({project["id"] for project in projects}) != 12:
        raise AssertionError("invalid base conservation project deck")
