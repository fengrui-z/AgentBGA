"""Deterministic official-base setup from the validated semantic content pack."""

from __future__ import annotations

from copy import deepcopy
from itertools import combinations
from pathlib import Path
import random
from typing import Any, Mapping

from .content import ContentEntry, ContentPack, load_content_pack
from .build_action import legal_setup_building_placements
from .milestones import install_official_conservation_milestones
from .projects import install_base_projects
from .semantics import SemanticRuleError
from .state import ACTION_TYPES, new_semantic_state, validate_semantic_state


DEFAULT_CONTENT_ROOT = (
    Path(__file__).resolve().parents[3] / "content-packs" / "ark-nova" / "base-en-draft"
)


def load_official_base_pack() -> ContentPack:
    return load_content_pack(DEFAULT_CONTENT_ROOT)


def card_instance(entry: ContentEntry) -> dict[str, Any]:
    """Project one physical base-game card without publisher prose or artwork."""
    component = entry.official_component_id or entry.id.rsplit("-", 1)[-1]
    prefix = "final" if entry.kind == "final_scoring" else "zoo"
    facts = deepcopy(dict(entry.facts))
    card_type = {
        "animal": "animal",
        "sponsor": "sponsor",
        "zoo_conservation_project": "conservation_project",
        "final_scoring": "final_scoring",
    }.get(entry.kind, entry.kind)
    card = {
        "id": f"{prefix}-{component}",
        "entry_id": entry.id,
        "kind": entry.kind,
        "card_type": card_type,
        "display_title": entry.display_title,
        "display_summary": entry.display_summary,
        "facts": facts,
        "effects": deepcopy(list(entry.effects)),
    }
    for key in (
        "cost", "enclosure_size", "appeal", "conservation", "reputation",
        "level", "tags", "icons", "rock_requirement", "water_requirement",
        "special_enclosure", "scoring", "levels",
    ):
        if key in facts:
            card[key] = deepcopy(facts[key])
    continents = facts.get("continents")
    if isinstance(continents, list) and continents:
        card["continent"] = continents[0]
    return card


def _bonus_tiles() -> list[dict[str, Any]]:
    # Mechanics-only reward faces. Four are installed each game (two at each
    # printed Conservation milestone); the remaining faces stay out of play.
    definitions = (
        ("money-8", "Gain 8 money", "gain_money", {"amount": 8}),
        ("x-3", "Gain 3 X-tokens", "gain_x_token", {"amount": 3}),
        ("reputation-2", "Gain 2 reputation", "move_track", {"track": "reputation", "amount": 2}),
        ("appeal-3", "Gain 3 appeal", "move_track", {"track": "appeal", "amount": 3}),
        ("conservation-1", "Gain 1 conservation", "move_track", {"track": "conservation", "amount": 1}),
        ("cards-3", "Draw 3 cards", "draw_cards", {"amount": 3}),
        ("worker-1", "Activate 1 worker", "gain_association_worker", {"amount": 1}),
        ("card", "Take a card", "take_map_reward_card", {}),
        ("enclosure-2", "Build a free size-2 enclosure", "place_free_building", {"building_types": ["standard_enclosure_2"]}),
    )
    return [
        {
            "id": f"bonus:{tile_id}", "label": label,
            "effects": [{"op": op, "timing": "immediate", "args": args}],
        }
        for tile_id, label, op, args in definitions
    ]


def setup_official_game(
    players: int, seed: int, *, pack: ContentPack | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if players not in (1, 2, 3, 4):
        raise SemanticRuleError("Ark Nova supports one to four players")
    config = dict(config or {})
    if set(config) - {"map", "turn_limit", "solo_starting_appeal"} or config.get("map", "map-0") not in {"0", "map-0"}:
        raise SemanticRuleError("the official-base plugin currently supports Map 0")
    solo_starting_appeal = config.get("solo_starting_appeal", 20)
    if players == 1 and solo_starting_appeal not in {0, 10, 20}:
        raise SemanticRuleError("solo_starting_appeal must be 0, 10, or 20")
    content = pack or load_official_base_pack()
    rng = random.Random(seed)
    state = new_semantic_state(players, seed=seed)
    state.update({
        "implementation_status": "official_base_candidate",
        "content_pack_id": content.manifest.pack_id,
        "content_version": content.manifest.content_version,
        "content_sha256": content.content_sha256,
        "content_hash": content.content_sha256,
        "official_track_income": True,
        "status": "active",
        "phase": "initial_hand_selection",
        "setup_pending_seats": list(range(players)),
        "decision_count": 0,
        "turn_count": 0,
    })

    zoo_cards = [
        card_instance(entry)
        for collection in ("animals", "sponsors", "zoo_conservation_projects")
        for entry in content.collections[collection]
    ]
    if len(zoo_cards) != 212:
        raise SemanticRuleError("official Zoo deck must contain exactly 212 physical cards")
    rng.shuffle(zoo_cards)
    state["card_display"] = [zoo_cards.pop() for _ in range(6)]

    finals = [card_instance(entry) for entry in content.collections["final_scoring"]]
    rng.shuffle(finals)
    for action_order, player in enumerate(state["players"]):
        if players == 1:
            player["tracks"]["appeal"] = int(solo_starting_appeal)
        else:
            # Seats are assigned in the initial action order.  The printed
            # setup gives each later player one additional Appeal.
            player["tracks"]["appeal"] = action_order
        player["tracks"]["reputation"] = 1
        player["initial_draw"] = [zoo_cards.pop() for _ in range(8)]
        player["initial_keep_required"] = 4
        player["final_scoring_cards"] = _draw_two_final_cards(finals, players, rng)
        other_actions = list(ACTION_TYPES[1:])
        rng.shuffle(other_actions)
        for position, action in enumerate(("animals", *other_actions), 1):
            card = next(item for item in player["action_cards"] if item["action"] == action)
            card["position"] = position
    state["zoo_deck"] = zoo_cards
    state["final_scoring_deck"] = finals

    projects = list(content.collections["base_conservation_projects"])
    rng.shuffle(projects)
    project_count = 4 if players == 4 else 3
    state = install_base_projects(state, projects[:project_count])
    state["base_project_supply"] = [entry.id for entry in projects[project_count:]]

    bonuses = _bonus_tiles()
    rng.shuffle(bonuses)
    state = install_official_conservation_milestones(
        state, bonuses_at_5=bonuses[:2], bonuses_at_8=bonuses[2:4],
    )
    state["unused_conservation_bonus_tiles"] = bonuses[4:]
    validate_semantic_state(state)
    return state


def legal_initial_hand_actions(state: Mapping[str, Any], seat: int) -> list[dict[str, Any]]:
    if state.get("phase") != "initial_hand_selection" or seat not in state.get("setup_pending_seats", []):
        return []
    cards = state["players"][seat].get("initial_draw", [])
    required = int(state["players"][seat].get("initial_keep_required", 4))
    return [
        {
            "id": "setup:keep:" + ":".join(card_ids),
            "action": {"type": "choose_initial_hand", "card_ids": list(card_ids)},
        }
        for card_ids in combinations((card["id"] for card in cards), required)
    ]


def choose_initial_hand(
    state: dict[str, Any], seat: int, card_ids: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    legal = [item["action"] for item in legal_initial_hand_actions(state, seat)]
    requested = {"type": "choose_initial_hand", "card_ids": list(card_ids)}
    if requested not in legal:
        raise SemanticRuleError("initial hand selection is not currently legal")
    next_state = deepcopy(state)
    player = next_state["players"][seat]
    selected = set(card_ids)
    player["hand"] = [card for card in player["initial_draw"] if card["id"] in selected]
    discarded = [card for card in player["initial_draw"] if card["id"] not in selected]
    next_state["zoo_discard"].extend(discarded)
    player["initial_draw"] = []
    next_state["setup_pending_seats"].remove(seat)
    if not next_state["setup_pending_seats"]:
        next_state["phase"] = "initial_map_setup"
        next_state["setup_pending_seats"] = list(range(next_state["player_count"]))
        for row in next_state["players"]:
            row["initial_map_setup_stage"] = "enclosure"
        next_state["active_seat"] = 0
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "initial_hand_selected", "seat": seat,
        "kept": len(player["hand"]), "discarded": len(discarded),
    }]


def legal_initial_map_actions(state: Mapping[str, Any], seat: int) -> list[dict[str, Any]]:
    if state.get("phase") != "initial_map_setup" or seat not in state.get("setup_pending_seats", []):
        return []
    player = state["players"][seat]
    stage = player.get("initial_map_setup_stage")
    building_type, size = (
        ("standard_enclosure", 3) if stage == "enclosure" else ("kiosk", 1)
    )
    return [
        {
            "id": f"setup:{stage}:{index}",
            "action": {
                **action, "type": "place_building", "setup_stage": stage,
            },
        }
        for index, action in enumerate(
            legal_setup_building_placements(player, building_type, size), 1,
        )
    ]


def place_initial_map_building(
    state: dict[str, Any], seat: int, action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    requested = dict(action)
    if requested not in [item["action"] for item in legal_initial_map_actions(state, seat)]:
        raise SemanticRuleError("starter building placement is not currently legal")
    next_state = deepcopy(state)
    player = next_state["players"][seat]
    building = {
        "id": f"building-{player['map']['next_building_id']}",
        "type": requested["building_type"], "size": requested["size"],
        "shape_id": requested["shape_id"], "rotation": requested["rotation"],
        "occupied": False, "cells": deepcopy(requested["cells"]),
    }
    player["map"]["next_building_id"] += 1
    player["map"]["buildings"].append(building)
    if building["type"] == "kiosk":
        player["initial_map_setup_stage"] = "complete"
        next_state["setup_pending_seats"].remove(seat)
    else:
        player["initial_map_setup_stage"] = "kiosk"
    if not next_state["setup_pending_seats"]:
        next_state["phase"] = "active"
        next_state["active_seat"] = 0
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "initial_map_building_placed", "seat": seat,
        "stage": requested["setup_stage"], "building": deepcopy(building),
    }]


def _draw_two_final_cards(
    deck: list[dict[str, Any]], players: int, rng: random.Random,
) -> list[dict[str, Any]]:
    result = []
    while len(result) < 2:
        if not deck:
            raise SemanticRuleError("Final Scoring deck is exhausted during setup")
        card = deck.pop()
        if players == 1 and card.get("entry_id") == "ark-nova:final-009":
            deck.insert(0, card)
            rng.shuffle(deck)
            continue
        result.append(card)
    return result
