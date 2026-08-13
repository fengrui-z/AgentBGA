"""Deterministic Ark Nova base-game setup skeleton.

This first milestone models setup and seat-scoped observations. The action state
machine and card effects deliberately remain unavailable until their rule tests
land, so callers cannot mistake placeholder transitions for the published game.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import random
from typing import Any

from .game import GameRuleError


RULES_VERSION = "base-1.2-setup.1"
ACTION_TYPES = ("animals", "cards", "build", "association", "sponsors")
CONTINENTS = ("africa", "asia", "australia", "europe", "americas")


class RuleError(GameRuleError):
    pass


def describe() -> dict[str, Any]:
    return {
        "id": "ark_nova",
        "name": "Ark Nova",
        "rules_version": RULES_VERSION,
        "players": {"minimum": 2, "maximum": 4},
        "hidden_information": True,
        "implementation_status": "setup_only",
        "runnable": False,
        "decision_model": "player_turn_with_multiple_decision_steps",
        "action_types": list(ACTION_TYPES),
        "map": "symmetric_beginner_map_a",
        "content_scope": "structural research identifiers; no card art or scanned text",
        "rules_sources": [
            "Ark Nova Rulebook, English, version 1.2",
            "Ark Nova FAQ/Errata, English, version 2",
        ],
        "win_condition": (
            "Trigger the end when appeal and conservation scoring counters meet; "
            "final scoring is implemented in a later rules milestone."
        ),
    }


def _research_zoo_cards() -> list[dict[str, Any]]:
    """Create non-publisher placeholder records for deterministic setup testing."""
    tags = ("bird", "primate", "predator", "reptile", "herbivore")
    cards = []
    for kind, count in (("animal", 128), ("sponsor", 64), ("conservation_project", 20)):
        cards.extend({
            "id": f"research-{kind}-{index:03d}",
            "card_type": kind,
            "tags": [tags[(index - 1) % len(tags)]] if kind == "animal" else [],
            "implementation": "structural_placeholder",
        } for index in range(1, count + 1))
    return cards


def _final_cards() -> list[dict[str, Any]]:
    return [
        {"id": f"research-final-{index:02d}", "implementation": "structural_placeholder"}
        for index in range(1, 12)
    ]


def _base_projects() -> list[dict[str, Any]]:
    return [
        {
            "id": f"research-base-{index:02d}", "tag": f"research-tag-{index:02d}",
            "levels": [2, 4, 5], "implementation": "structural_placeholder",
        }
        for index in range(1, 13)
    ]


def _bonus_tiles() -> list[dict[str, Any]]:
    return [
        {"id": f"research-bonus-{index:02d}", "implementation": "structural_placeholder"}
        for index in range(1, 10)
    ]


def _map_a() -> dict[str, Any]:
    cells = []
    water = {(-2, 0), (2, 0)}
    rock = {(0, -2), (0, 2)}
    starter = {(-1, 0), (0, 0), (1, 0)}
    for q in range(-3, 4):
        for r in range(-3, 4):
            if abs(q + r) > 3:
                continue
            terrain = "water" if (q, r) in water else "rock" if (q, r) in rock else "buildable"
            cells.append({"q": q, "r": r, "terrain": terrain})
    return {
        "id": "map-a",
        "name": "Beginner Map A",
        "geometry_status": "schematic_pending_verified_footprints",
        "cells": cells,
        "buildings": [{
            "id": "starting-enclosure-3", "type": "standard_enclosure",
            "size": 3, "occupied": False,
            "cells": [{"q": q, "r": r} for q, r in sorted(starter)],
        }],
    }


def new_game(
    players: int, seed: int, config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if players not in (2, 3, 4):
        raise RuleError("Ark Nova requires 2, 3, or 4 players")
    if config not in (None, {}, {"map": "a"}):
        raise RuleError("the setup milestone currently supports only beginner map A")
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
    project_count = 4 if players == 4 else 3
    player_rows = []
    for seat in range(players):
        initial_draw = [zoo_cards.pop() for _ in range(8)]
        final_scoring = [finals.pop() for _ in range(2)]
        other_actions = list(ACTION_TYPES[1:])
        rng.shuffle(other_actions)
        ordered_actions = ["animals", *other_actions]
        player_rows.append({
            "seat": seat,
            "money": 25,
            "x_tokens": 0,
            "appeal": seat,
            "conservation": 0,
            "reputation": 0,
            "action_cards": [
                {"action": action, "strength": position, "upgraded": False, "tokens": []}
                for position, action in enumerate(ordered_actions, 1)
            ],
            "association_workers": {"active": 1, "reserve": 3, "committed": []},
            "partner_zoos": [],
            "universities": [],
            "map": _map_a(),
            "hand": [],
            "initial_draw": initial_draw,
            "initial_keep_required": 4,
            "played_cards": [],
            "final_scoring_cards": final_scoring,
            "conservation_tokens_on_map": 7,
            "supported_projects": [],
        })
    state = {
        "schema_version": "agentbga.ark_nova.state.v1",
        "game_id": "ark_nova",
        "rules_version": RULES_VERSION,
        "implementation_status": "setup_only",
        "seed": seed,
        "player_count": players,
        "status": "setup",
        "phase": "initial_hand_selection",
        "turn_count": 0,
        "decision_count": 0,
        "active_seat": 0,
        "turn": {
            "active_seat": 0,
            "decision": "choose_initial_hand",
            "action_card": None,
            "remaining_plays": 0,
        },
        "break_track": {
            "position": 0, "start_marker": f"players-{players}", "triggered": False,
        },
        "game_board_bonus_tiles": bonus_tiles[:4],
        "unused_bonus_tiles": bonus_tiles[4:],
        "card_display": display,
        "zoo_deck": zoo_cards,
        "zoo_discard": [],
        "final_scoring_deck": finals,
        "base_conservation_projects": projects[:project_count],
        "base_conservation_deck": projects[project_count:],
        "association_board": {
            "partner_zoos": {continent: 1 for continent in CONTINENTS},
            "universities": {
                "research-2": 1, "research-reputation": 1, "hand-limit-5": 1,
            },
            "blocked_two_player": (
                ["project-left", "project-middle", "project-right",
                 "donation-left-1", "donation-left-2", "donation-left-3"]
                if players == 2 else []
            ),
        },
        "players": player_rows,
    }
    validate_state(state)
    return state


def state_hash(state: dict[str, Any]) -> str:
    raw = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _hidden_cards(count: int) -> list[dict[str, bool]]:
    return [{"hidden": True} for _ in range(count)]


def observe(state: dict[str, Any], seat: int) -> dict[str, Any]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    rows = []
    for player in state["players"]:
        own = player["seat"] == seat
        row = deepcopy(player)
        row["hand_count"] = len(player["hand"])
        row["initial_draw_count"] = len(player["initial_draw"])
        row["hand"] = deepcopy(player["hand"]) if own else _hidden_cards(len(player["hand"]))
        row["initial_draw"] = (
            deepcopy(player["initial_draw"]) if own else _hidden_cards(len(player["initial_draw"]))
        )
        row["final_scoring_cards"] = (
            deepcopy(player["final_scoring_cards"])
            if own else _hidden_cards(len(player["final_scoring_cards"]))
        )
        rows.append(row)
    return {
        "game": "ark_nova",
        "rules_version": state["rules_version"],
        "implementation_status": state["implementation_status"],
        "viewer_seat": seat,
        "status": state["status"],
        "phase": state["phase"],
        "turn_count": state["turn_count"],
        "decision_count": state["decision_count"],
        "active_seat": state["active_seat"],
        "turn": deepcopy(state["turn"]),
        "break_track": deepcopy(state["break_track"]),
        "card_display": (
            _hidden_cards(len(state["card_display"]))
            if state["phase"] == "initial_hand_selection"
            else deepcopy(state["card_display"])
        ),
        "game_board_bonus_tiles": deepcopy(state["game_board_bonus_tiles"]),
        "deck_count": len(state["zoo_deck"]),
        "discard_count": len(state["zoo_discard"]),
        "base_conservation_projects": deepcopy(state["base_conservation_projects"]),
        "association_board": deepcopy(state["association_board"]),
        "players": rows,
        "rankings": None,
    }


def legal_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    return []


def apply_action(
    state: dict[str, Any], seat: int, action: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    del state, seat, action
    raise RuleError(
        "Ark Nova currently provides a deterministic setup/observation skeleton; "
        "the multi-step action state machine is not implemented yet"
    )


def rankings(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "seat": player["seat"],
            "appeal": player["appeal"],
            "conservation": player["conservation"],
            "reputation": player["reputation"],
            "rank": None,
        }
        for player in state["players"]
    ]


def validate_state(state: dict[str, Any]) -> None:
    if state.get("schema_version") != "agentbga.ark_nova.state.v1":
        raise AssertionError("invalid Ark Nova state schema")
    if state["player_count"] not in (2, 3, 4) or len(state["players"]) != state["player_count"]:
        raise AssertionError("invalid Ark Nova player count")
    seen: list[str] = []
    seen.extend(card["id"] for card in state["card_display"])
    seen.extend(card["id"] for card in state["zoo_deck"])
    seen.extend(card["id"] for card in state["zoo_discard"])
    for player in state["players"]:
        if player["money"] < 0 or not 0 <= player["x_tokens"] <= 5:
            raise AssertionError("invalid player resources")
        if sorted(card["strength"] for card in player["action_cards"]) != [1, 2, 3, 4, 5]:
            raise AssertionError("action cards must occupy strengths 1 through 5")
        if {card["action"] for card in player["action_cards"]} != set(ACTION_TYPES):
            raise AssertionError("player must have all five action cards")
        if next(card for card in player["action_cards"] if card["strength"] == 1)["action"] != "animals":
            raise AssertionError("Animals must start at strength 1")
        seen.extend(card["id"] for card in player["hand"])
        seen.extend(card["id"] for card in player["initial_draw"])
        seen.extend(card["id"] for card in player["played_cards"])
    if len(seen) != 212:
        raise AssertionError("Ark Nova setup must conserve all 212 zoo cards")
    if len(seen) != len(set(seen)):
        raise AssertionError("a zoo card appears in more than one location")
    bonus_seen = [tile["id"] for tile in state["game_board_bonus_tiles"] + state["unused_bonus_tiles"]]
    if len(bonus_seen) != 9 or len(bonus_seen) != len(set(bonus_seen)):
        raise AssertionError("invalid game-board bonus tiles")
    final_seen = [card["id"] for card in state["final_scoring_deck"]]
    for player in state["players"]:
        final_seen.extend(card["id"] for card in player["final_scoring_cards"])
    if len(final_seen) != len(set(final_seen)):
        raise AssertionError("a final scoring card appears in more than one location")
    projects = state["base_conservation_projects"] + state["base_conservation_deck"]
    if len(projects) != 12 or len({project["id"] for project in projects}) != 12:
        raise AssertionError("invalid base conservation project deck")
