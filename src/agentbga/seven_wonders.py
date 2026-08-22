"""Deterministic 7 Wonders (Second Edition base game) rules engine.

The physical game asks every player to choose simultaneously.  AgentBGA has a
single-active-seat protocol, so choices are collected one seat at a time and
kept sealed.  They are revealed and resolved only after every seat submitted.
This preserves the draft's information boundary while keeping every decision
individually auditable and replayable.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from itertools import product
import random
from typing import Any

from .game import GameRuleError
from .mechanics import ActionSpace, action_accepted, assign_competition_ranks, state_digest


RULES_VERSION = "second-edition-base-1.0"
RESOURCES = ("wood", "stone", "clay", "ore", "glass", "papyrus", "cloth")
COMMON = RESOURCES[:4]
RARE = RESOURCES[4:]
COLORS = ("brown", "gray", "blue", "yellow", "red", "green", "purple")
SCIENCE = ("compass", "gear", "tablet")
WONDER_NAMES = ("giza", "alexandria", "olympia", "babylon", "halikarnassos", "ephesus", "rhodos")


class RuleError(GameRuleError):
    """A stable, user-correctable rule rejection."""


def _cost(**amounts: int) -> dict[str, int]:
    return {resource: amounts.get(resource, 0) for resource in RESOURCES}


def _stage(cost: dict[str, int], **effect: Any) -> dict[str, Any]:
    return {"cost": cost, **effect}


# The Day/Night boards are the complete seven-board base set.  Resource
# choices produced by stages are usable by their owner but cannot be traded.
WONDERS: dict[str, dict[str, Any]] = {
    "giza": {
        "name": "Giza", "starting_resource": "stone",
        "day": [
            _stage(_cost(wood=2), points=3),
            _stage(_cost(clay=2, glass=1), points=5),
            _stage(_cost(stone=4), points=7),
        ],
        "night": [
            _stage(_cost(wood=2), points=3),
            _stage(_cost(stone=3), points=5),
            _stage(_cost(clay=3), points=5),
            _stage(_cost(stone=4, papyrus=1), points=7),
        ],
    },
    "alexandria": {
        "name": "Alexandria", "starting_resource": "glass",
        "day": [
            _stage(_cost(stone=2), points=3),
            _stage(_cost(ore=2), production=[list(COMMON)]),
            _stage(_cost(papyrus=1, cloth=1), points=7),
        ],
        "night": [
            _stage(_cost(clay=2), production=[list(COMMON)]),
            _stage(_cost(stone=3), production=[list(RARE)]),
            _stage(_cost(wood=4), points=7),
        ],
    },
    "olympia": {
        "name": "Olympia", "starting_resource": "clay",
        "day": [
            _stage(_cost(stone=2), points=3),
            _stage(_cost(wood=2), special="free_first_color"),
            _stage(_cost(clay=3), points=7),
        ],
        "night": [
            _stage(_cost(ore=2), points=2, special="free_first_age"),
            _stage(_cost(clay=3), points=3, special="free_last_age"),
            _stage(_cost(glass=1, papyrus=1, cloth=1), points=5),
        ],
    },
    "babylon": {
        "name": "Babylon", "starting_resource": "wood",
        "day": [
            _stage(_cost(clay=2), points=3),
            _stage(_cost(papyrus=1, cloth=1), science_wild=1),
            _stage(_cost(wood=4), points=7),
        ],
        "night": [
            _stage(_cost(cloth=1), special="play_seventh"),
            _stage(_cost(clay=2, glass=1), science_wild=1),
        ],
    },
    "halikarnassos": {
        "name": "Halikarnassos", "starting_resource": "cloth",
        "day": [
            _stage(_cost(ore=2), points=3),
            _stage(_cost(clay=1, glass=1), special="build_discard"),
            _stage(_cost(stone=3), points=7),
        ],
        "night": [
            _stage(_cost(clay=2), points=2, special="build_discard"),
            _stage(_cost(papyrus=1), points=1, special="build_discard"),
            _stage(_cost(wood=3), special="build_discard"),
        ],
    },
    "ephesus": {
        "name": "Ephesus", "starting_resource": "papyrus",
        "day": [
            _stage(_cost(clay=2), points=3),
            _stage(_cost(wood=2), coins=9),
            _stage(_cost(ore=2, glass=1), points=7),
        ],
        "night": [
            _stage(_cost(stone=2), coins=4, points=2),
            _stage(_cost(wood=2), coins=4, points=3),
            _stage(_cost(ore=1, clay=1, cloth=1), coins=4, points=5),
        ],
    },
    "rhodos": {
        "name": "Rhodos", "starting_resource": "ore",
        "day": [
            _stage(_cost(wood=2), points=3),
            _stage(_cost(clay=3), military=2),
            _stage(_cost(ore=4), points=7),
        ],
        "night": [
            _stage(_cost(stone=3), points=3, coins=3, military=1),
            _stage(_cost(ore=4), points=4, coins=4, military=1),
        ],
    },
}


def _make_card(
    cards: dict[str, dict[str, Any]], age: int, name: str, color: str,
    minimums: tuple[int, ...], *, cost: dict[str, int] | None = None,
    coin_cost: int = 0, production: list[list[str]] | None = None,
    points: int = 0, military: int = 0, science: str | None = None,
    effect: str | None = None, chain_from: tuple[str, ...] = (),
) -> None:
    slug = name.lower().replace(" ", "-")
    for minimum in minimums:
        card_id = f"age{age}-{slug}-{minimum}"
        cards[card_id] = {
            "id": card_id, "name": name, "age": age, "color": color,
            "minimum_players": minimum, "cost": cost or _cost(),
            "coin_cost": coin_cost, "production": production or [],
            "points": points, "military": military, "science": science,
            "effect": effect, "chain_from": list(chain_from),
        }


def card_catalog() -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    add = lambda age, name, color, mins, **kw: _make_card(cards, age, name, color, mins, **kw)

    # Age I - 49 physical cards.
    add(1, "Lumber Yard", "brown", (3, 4), production=[["wood"]])
    add(1, "Stone Pit", "brown", (3, 5), production=[["stone"]])
    add(1, "Clay Pool", "brown", (3, 5), production=[["clay"]])
    add(1, "Ore Vein", "brown", (3, 4), production=[["ore"]])
    add(1, "Tree Farm", "brown", (6,), coin_cost=1, production=[["wood", "clay"]])
    add(1, "Excavation", "brown", (4,), coin_cost=1, production=[["stone", "clay"]])
    add(1, "Clay Pit", "brown", (3,), coin_cost=1, production=[["ore", "clay"]])
    add(1, "Timber Yard", "brown", (3,), coin_cost=1, production=[["wood", "stone"]])
    add(1, "Forest Cave", "brown", (5,), coin_cost=1, production=[["wood", "ore"]])
    add(1, "Mine", "brown", (6,), coin_cost=1, production=[["stone", "ore"]])
    add(1, "Glassworks", "gray", (3, 6), production=[["glass"]])
    add(1, "Press", "gray", (3, 6), production=[["papyrus"]])
    add(1, "Loom", "gray", (3, 6), production=[["cloth"]])
    add(1, "Well", "blue", (4, 7), coin_cost=1, points=3)
    add(1, "Baths", "blue", (3, 7), cost=_cost(stone=1), points=3)
    add(1, "Altar", "blue", (3, 5), points=3)
    add(1, "Theater", "blue", (3, 6), points=3)
    add(1, "Tavern", "yellow", (4, 5, 7), effect="coins_5")
    add(1, "Marketplace", "yellow", (3, 6), effect="discount_rare")
    add(1, "West Trading Post", "yellow", (3, 7), effect="discount_left_common")
    add(1, "East Trading Post", "yellow", (3, 7), effect="discount_right_common")
    add(1, "Stockade", "red", (3, 7), cost=_cost(wood=1), military=1)
    add(1, "Barracks", "red", (3, 5), cost=_cost(ore=1), military=1)
    add(1, "Guard Tower", "red", (3, 4), cost=_cost(clay=1), military=1)
    add(1, "Apothecary", "green", (3, 5), cost=_cost(cloth=1), science="compass")
    add(1, "Workshop", "green", (3, 7), cost=_cost(glass=1), science="gear")
    add(1, "Scriptorium", "green", (3, 4), cost=_cost(papyrus=1), science="tablet")

    # Age II - 49 physical cards.
    add(2, "Sawmill", "brown", (3, 4), coin_cost=1, production=[["wood"], ["wood"]])
    add(2, "Quarry", "brown", (3, 4), coin_cost=1, production=[["stone"], ["stone"]])
    add(2, "Brickyard", "brown", (3, 4), coin_cost=1, production=[["clay"], ["clay"]])
    add(2, "Foundry", "brown", (3, 4), coin_cost=1, production=[["ore"], ["ore"]])
    add(2, "Glassworks", "gray", (3, 5), coin_cost=1, production=[["glass"]])
    add(2, "Press", "gray", (3, 5), coin_cost=1, production=[["papyrus"]])
    add(2, "Loom", "gray", (3, 5), coin_cost=1, production=[["cloth"]])
    add(2, "Statue", "blue", (3, 7), cost=_cost(ore=2), points=4, chain_from=("Well",))
    add(2, "Aqueduct", "blue", (3, 7), cost=_cost(stone=3), points=5, chain_from=("Baths",))
    add(2, "Temple", "blue", (3, 6), cost=_cost(wood=1, clay=1, glass=1), points=4)
    add(2, "Courthouse", "blue", (3, 5), cost=_cost(clay=2, papyrus=1), points=4, chain_from=("Scriptorium",))
    add(2, "Caravansery", "yellow", (3, 5, 6), cost=_cost(wood=2),
        production=[list(COMMON)], chain_from=("Marketplace",))
    add(2, "Forum", "yellow", (3, 6, 7), cost=_cost(clay=2),
        production=[list(RARE)], chain_from=("East Trading Post", "West Trading Post"))
    add(2, "Vineyard", "yellow", (3, 6), effect="coins_neighbor_brown")
    add(2, "Bazar", "yellow", (4, 7), effect="coins_neighbor_gray")
    add(2, "Stables", "red", (3, 5), cost=_cost(wood=1, ore=1, clay=1),
        military=2, chain_from=("Apothecary",))
    add(2, "Archery Range", "red", (3, 6), cost=_cost(wood=2, ore=1),
        military=2, chain_from=("Workshop",))
    add(2, "Walls", "red", (3, 7), cost=_cost(stone=3), military=2)
    add(2, "Training Ground", "red", (4, 6, 7), cost=_cost(wood=1, ore=2), military=2)
    add(2, "Dispensary", "green", (3, 4), cost=_cost(ore=2, glass=1),
        science="compass", chain_from=("Apothecary",))
    add(2, "Laboratory", "green", (3, 5), cost=_cost(clay=2, papyrus=1),
        science="gear", chain_from=("Workshop",))
    add(2, "Library", "green", (3, 6), cost=_cost(stone=2, cloth=1),
        science="tablet", chain_from=("Scriptorium",))
    add(2, "School", "green", (3, 7), cost=_cost(wood=1, papyrus=1), science="tablet")

    # Age III non-guild cards plus ten guilds.
    add(3, "Pantheon", "blue", (3, 6), cost=_cost(clay=2, ore=1, glass=1, papyrus=1, cloth=1),
        points=7, chain_from=("Altar",))
    add(3, "Gardens", "blue", (3, 4), cost=_cost(clay=2, wood=1), points=5, chain_from=("Theater",))
    add(3, "Town Hall", "blue", (3, 6), cost=_cost(stone=2, ore=1, glass=1), points=6)
    add(3, "Palace", "blue", (3, 7), cost=_cost(**{resource: 1 for resource in RESOURCES}), points=8)
    add(3, "Senate", "blue", (3, 5), cost=_cost(wood=2, stone=1, ore=1),
        points=6, chain_from=("Courthouse",))
    add(3, "Lighthouse", "yellow", (3, 6), cost=_cost(stone=1, glass=1),
        effect="score_yellow", chain_from=("Caravansery",))
    add(3, "Haven", "yellow", (3, 4), cost=_cost(wood=1, ore=1, cloth=1),
        effect="score_brown", chain_from=("Forum",))
    add(3, "Chamber of Commerce", "yellow", (4, 6), cost=_cost(clay=2, papyrus=1), effect="score_gray")
    add(3, "Ludus", "yellow", (5, 7), cost=_cost(stone=1, ore=1), effect="score_red")
    add(3, "Arena", "yellow", (3, 5), cost=_cost(stone=2, ore=1),
        effect="score_stages", chain_from=("Stables",))
    add(3, "Castrum", "red", (4, 7), cost=_cost(clay=3), military=3)
    add(3, "Fortifications", "red", (3, 7), cost=_cost(ore=3), military=3, chain_from=("Walls",))
    add(3, "Circus", "red", (4, 6), cost=_cost(stone=3), military=3, chain_from=("Training Ground",))
    add(3, "Arsenal", "red", (3, 5), cost=_cost(wood=2, ore=1, cloth=1), military=3)
    add(3, "Siege Workshop", "red", (3, 5), cost=_cost(wood=1, clay=3),
        military=3, chain_from=("Archery Range",))
    add(3, "Lodge", "green", (3, 6), cost=_cost(clay=2, papyrus=1, cloth=1),
        science="compass", chain_from=("Dispensary",))
    add(3, "Academy", "green", (3, 7), cost=_cost(stone=3, glass=1),
        science="compass", chain_from=("School",))
    add(3, "Observatory", "green", (3, 7), cost=_cost(ore=2, glass=1, cloth=1),
        science="gear", chain_from=("Laboratory",))
    add(3, "Study", "green", (3, 5), cost=_cost(wood=1, papyrus=1, cloth=1),
        science="gear", chain_from=("School",))
    add(3, "University", "green", (3, 4), cost=_cost(wood=2, glass=1, papyrus=1),
        science="tablet", chain_from=("Library",))
    guilds = (
        ("Workers Guild", _cost(wood=1, stone=1, clay=1, ore=2), "guild_workers"),
        ("Craftsmens Guild", _cost(stone=2, ore=2), "guild_craftsmens"),
        ("Magistrates Guild", _cost(wood=3, stone=1, cloth=1), "guild_magistrates"),
        ("Traders Guild", _cost(glass=1, papyrus=1, cloth=1), "guild_traders"),
        ("Builders Guild", _cost(stone=2, clay=2, glass=1), "guild_builders"),
        ("Spies Guild", _cost(clay=3, glass=1), "guild_spies"),
        ("Philosophers Guild", _cost(clay=3, papyrus=1, cloth=1), "guild_philosophers"),
        ("Decorators Guild", _cost(wood=2, ore=2, stone=1), "guild_decorators"),
        ("Scientists Guild", _cost(wood=2, ore=2, papyrus=1), "guild_scientists"),
        ("Shipowners Guild", _cost(wood=3, glass=1, papyrus=1), "guild_shipowners"),
    )
    for name, cost, effect in guilds:
        add(3, name, "purple", (3,), cost=cost, effect=effect)
    return cards


CARDS = card_catalog()


CHAIN_TO: dict[str, list[str]] = {
    name: sorted({
        candidate["name"] for candidate in CARDS.values()
        if name in candidate["chain_from"]
    })
    for name in {card["name"] for card in CARDS.values()}
}


EFFECT_BENEFITS: dict[str, list[dict[str, Any]]] = {
    "coins_5": [{"type": "coins", "amount": 5}],
    "discount_rare": [{
        "type": "trade_discount", "directions": ["left", "right"],
        "resources": list(RARE), "coin_cost": 1,
    }],
    "discount_left_common": [{
        "type": "trade_discount", "directions": ["left"],
        "resources": list(COMMON), "coin_cost": 1,
    }],
    "discount_right_common": [{
        "type": "trade_discount", "directions": ["right"],
        "resources": list(COMMON), "coin_cost": 1,
    }],
    "coins_neighbor_brown": [{
        "type": "coins_per_card", "scope": ["self", "left", "right"],
        "color": "brown", "amount": 1,
    }],
    "coins_neighbor_gray": [{
        "type": "coins_per_card", "scope": ["self", "left", "right"],
        "color": "gray", "amount": 2,
    }],
    "score_yellow": [
        {"type": "coins_per_card", "scope": ["self"], "color": "yellow", "amount": 1},
        {"type": "points_per_card", "scope": ["self"], "color": "yellow", "amount": 1},
    ],
    "score_brown": [
        {"type": "coins_per_card", "scope": ["self"], "color": "brown", "amount": 1},
        {"type": "points_per_card", "scope": ["self"], "color": "brown", "amount": 1},
    ],
    "score_gray": [
        {"type": "coins_per_card", "scope": ["self"], "color": "gray", "amount": 2},
        {"type": "points_per_card", "scope": ["self"], "color": "gray", "amount": 2},
    ],
    "score_red": [
        {"type": "coins_per_card", "scope": ["self"], "color": "red", "amount": 3},
        {"type": "points_per_card", "scope": ["self"], "color": "red", "amount": 1},
    ],
    "score_stages": [
        {"type": "coins_per_stage", "scope": ["self"], "amount": 3},
        {"type": "points_per_stage", "scope": ["self"], "amount": 1},
    ],
    "guild_workers": [{
        "type": "points_per_card", "scope": ["left", "right"],
        "color": "brown", "amount": 1,
    }],
    "guild_craftsmens": [{
        "type": "points_per_card", "scope": ["left", "right"],
        "color": "gray", "amount": 2,
    }],
    "guild_magistrates": [{
        "type": "points_per_card", "scope": ["left", "right"],
        "color": "blue", "amount": 1,
    }],
    "guild_traders": [{
        "type": "points_per_card", "scope": ["left", "right"],
        "color": "yellow", "amount": 1,
    }],
    "guild_builders": [{
        "type": "points_per_stage", "scope": ["self", "left", "right"], "amount": 1,
    }],
    "guild_spies": [{
        "type": "points_per_card", "scope": ["left", "right"],
        "color": "red", "amount": 1,
    }],
    "guild_philosophers": [{
        "type": "points_per_card", "scope": ["left", "right"],
        "color": "green", "amount": 1,
    }],
    "guild_decorators": [{"type": "points_if_wonder_complete", "amount": 7}],
    "guild_scientists": [{"type": "science_wild", "amount": 1}],
    "guild_shipowners": [{
        "type": "points_per_card", "scope": ["self"],
        "colors": ["brown", "gray", "purple"], "amount": 1,
    }],
}


def describe() -> dict[str, Any]:
    return {
        "id": "seven_wonders",
        "name": "7 Wonders",
        "rules_version": RULES_VERSION,
        "players": {"minimum": 3, "maximum": 7},
        "hidden_information": True,
        "implementation_status": "playable",
        "runnable": True,
        "decision_model": "sealed_choices_resolved_simultaneously",
        "edition": "Second Edition (2020)",
        "rules_sources": [
            "Repos Production 7 Wonders Second Edition English rulebook",
            "Repos Production Description of Effects and List of Chains & Cards",
        ],
        "action_types": ["build_card", "build_wonder", "sell_card", "build_discard"],
        "wonder_sides": ["day", "night"],
        "win_condition": (
            "After Age III, highest total score wins; ties break on remaining coins, "
            "then remain shared."
        ),
    }


def _normalize_config(players: int, config: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    config = {} if config is None else config
    if set(config) - {"wonders", "wonder_sides"}:
        raise RuleError("7 Wonders accepts only wonders and wonder_sides setup options")
    selected = config.get("wonders")
    if selected is not None:
        if not isinstance(selected, list) or len(selected) != players:
            raise RuleError("wonders must be a list with one entry per player")
        if any(wonder not in WONDERS for wonder in selected) or len(set(selected)) != players:
            raise RuleError("wonders must contain distinct base-game wonder ids")
        wonders = list(selected)
    else:
        wonders = []
    raw_sides = config.get("wonder_sides", "day")
    if isinstance(raw_sides, str):
        sides = [raw_sides] * players
    elif isinstance(raw_sides, list) and len(raw_sides) == players:
        sides = list(raw_sides)
    else:
        raise RuleError("wonder_sides must be day/night or a list with one entry per player")
    if any(side not in ("day", "night") for side in sides):
        raise RuleError("wonder sides must be day or night")
    return wonders, sides


def _deck_for_age(age: int, players: int, rng: random.Random) -> list[str]:
    if age != 3:
        deck = [card_id for card_id, card in CARDS.items()
                if card["age"] == age and card["minimum_players"] <= players]
    else:
        normal = [card_id for card_id, card in CARDS.items()
                  if card["age"] == 3 and card["color"] != "purple"
                  and card["minimum_players"] <= players]
        guilds = [card_id for card_id, card in CARDS.items() if card["color"] == "purple"]
        rng.shuffle(guilds)
        deck = normal + guilds[:players + 2]
    if len(deck) != players * 7:
        raise AssertionError(f"Age {age} deck has {len(deck)} cards for {players} players")
    rng.shuffle(deck)
    return deck


def _deal_age(state: dict[str, Any], age: int) -> None:
    deck = state["age_decks"][str(age)]
    state["hands"] = [[] for _ in range(state["player_count"])]
    for _ in range(7):
        for seat in range(state["player_count"]):
            state["hands"][seat].append(deck.pop())
    state["age"] = age
    state["pick"] = 1
    state["phase"] = "draft"
    state["active_seat"] = 0
    state["pending_choices"] = {}


def new_game(players: int, seed: int, config: dict[str, Any] | None = None) -> dict[str, Any]:
    if players < 3 or players > 7:
        raise RuleError("7 Wonders requires 3 to 7 players")
    configured_wonders, sides = _normalize_config(players, config)
    rng = random.Random(seed)
    wonders = list(WONDER_NAMES)
    rng.shuffle(wonders)
    if configured_wonders:
        wonders = configured_wonders
    else:
        wonders = wonders[:players]
    age_decks = {str(age): _deck_for_age(age, players, rng) for age in (1, 2, 3)}
    state: dict[str, Any] = {
        "schema_version": "agentbga.seven_wonders.state.v1",
        "rules_version": RULES_VERSION,
        "seed": seed,
        "player_count": players,
        "turn_count": 0,
        "decision_count": 0,
        "status": "active",
        "phase": "draft",
        "active_seat": 0,
        "age": 1,
        "pick": 1,
        "age_decks": age_decks,
        "hands": [],
        "discard": [],
        "pending_choices": {},
        "pending_free_builds": [],
        "pending_seventh": [],
        "resume_after_special": None,
        "players": [
            {
                "seat": seat, "coins": 3, "wonder": wonders[seat], "wonder_side": sides[seat],
                "wonder_stages": [], "city": [], "military_tokens": [],
                "military_tokens_by_age": [[], [], []],
                "free_first_age_used": [], "free_last_age_used": [],
            }
            for seat in range(players)
        ],
    }
    state["card_pool"] = [card_id for deck in age_decks.values() for card_id in deck]
    _deal_age(state, 1)
    validate_state(state)
    return state


def state_hash(state: dict[str, Any]) -> str:
    return state_digest(state)


def _left(state: dict[str, Any], seat: int) -> int:
    return (seat - 1) % state["player_count"]


def _right(state: dict[str, Any], seat: int) -> int:
    return (seat + 1) % state["player_count"]


def _city_names(state: dict[str, Any], seat: int) -> set[str]:
    return {CARDS[card_id]["name"] for card_id in state["players"][seat]["city"]}


def _has_effect(state: dict[str, Any], seat: int, effect: str) -> bool:
    for card_id in state["players"][seat]["city"]:
        if CARDS[card_id]["effect"] == effect:
            return True
    player = state["players"][seat]
    wonder = WONDERS[player["wonder"]][player["wonder_side"]]
    return any(stage.get("special") == effect for stage in wonder[:len(player["wonder_stages"])])


def _production_units(state: dict[str, Any], seat: int, *, tradeable: bool) -> list[tuple[str, ...]]:
    player = state["players"][seat]
    units: list[tuple[str, ...]] = [(WONDERS[player["wonder"]]["starting_resource"],)]
    for card_id in player["city"]:
        card = CARDS[card_id]
        if tradeable and card["color"] not in ("brown", "gray"):
            continue
        units.extend(tuple(options) for options in card["production"])
    if not tradeable:
        stages = WONDERS[player["wonder"]][player["wonder_side"]]
        for stage in stages[:len(player["wonder_stages"])]:
            units.extend(tuple(options) for options in stage.get("production", []))
    return units


def _can_produce(units: list[tuple[str, ...]], requested: Counter[str]) -> bool:
    needs = [resource for resource in RESOURCES for _ in range(requested[resource])]
    needs.sort(key=lambda resource: sum(resource in unit for unit in units))

    def visit(index: int, used: int) -> bool:
        if index == len(needs):
            return True
        resource = needs[index]
        for unit_index, options in enumerate(units):
            if not used & (1 << unit_index) and resource in options:
                if visit(index + 1, used | (1 << unit_index)):
                    return True
        return False

    return visit(0, 0)


def _trade_price(state: dict[str, Any], seat: int, direction: str, resource: str) -> int:
    if resource in RARE and _has_effect(state, seat, "discount_rare"):
        return 1
    if resource in COMMON and direction == "left" and _has_effect(state, seat, "discount_left_common"):
        return 1
    if resource in COMMON and direction == "right" and _has_effect(state, seat, "discount_right_common"):
        return 1
    return 2


def _payment_plans(
    state: dict[str, Any], seat: int, cost: dict[str, int], coin_cost: int = 0,
) -> list[dict[str, Any]]:
    required = [resource for resource in RESOURCES for _ in range(cost.get(resource, 0))]
    local_units = _production_units(state, seat, tradeable=False)
    left_units = _production_units(state, _left(state, seat), tradeable=True)
    right_units = _production_units(state, _right(state, seat), tradeable=True)
    plans: dict[tuple[Any, ...], dict[str, Any]] = {}
    for assignments in product(("self", "left", "right"), repeat=len(required)):
        requests = {source: Counter() for source in ("self", "left", "right")}
        for resource, source in zip(required, assignments, strict=True):
            requests[source][resource] += 1
        if not _can_produce(local_units, requests["self"]):
            continue
        if not _can_produce(left_units, requests["left"]):
            continue
        if not _can_produce(right_units, requests["right"]):
            continue
        left = sum(amount * _trade_price(state, seat, "left", resource)
                   for resource, amount in requests["left"].items())
        right = sum(amount * _trade_price(state, seat, "right", resource)
                    for resource, amount in requests["right"].items())
        if coin_cost + left + right <= state["players"][seat]["coins"]:
            left_resources = tuple(sorted(requests["left"].items()))
            right_resources = tuple(sorted(requests["right"].items()))
            key = (coin_cost, left, right, left_resources, right_resources)
            purchases = []
            for direction, neighbor, coins, resources in (
                ("left", _left(state, seat), left, requests["left"]),
                ("right", _right(state, seat), right, requests["right"]),
            ):
                if resources:
                    purchases.append({
                        "direction": direction, "seat": neighbor, "coins": coins,
                        "resources": dict(sorted(resources.items())),
                    })
            plans[key] = {
                "payment": {"bank": coin_cost, "left": left, "right": right},
                "purchases": purchases,
            }
    ordered = [plans[key] for key in sorted(plans, key=lambda item: (sum(item[:3]), item))]
    if not ordered:
        return []
    minimum = sum(ordered[0]["payment"].values())
    return [plan for plan in ordered if sum(plan["payment"].values()) == minimum]


def _free_sources(state: dict[str, Any], seat: int, card: dict[str, Any]) -> list[str]:
    sources: list[str] = []
    names = _city_names(state, seat)
    if any(name in names for name in card["chain_from"]):
        sources.append("chain")
    player = state["players"][seat]
    if (_has_effect(state, seat, "free_first_color")
            and not any(CARDS[card_id]["color"] == card["color"] for card_id in player["city"])):
        sources.append("wonder_first_color")
    if (_has_effect(state, seat, "free_first_age")
            and state["pick"] == 1 and state["age"] not in player["free_first_age_used"]):
        sources.append("wonder_first_age")
    if (_has_effect(state, seat, "free_last_age") and state["pick"] == 6
            and state["age"] not in player["free_last_age_used"]):
        sources.append("wonder_last_age")
    return sources


def _actions_for_card(state: dict[str, Any], seat: int, card_id: str) -> list[dict[str, Any]]:
    card = CARDS[card_id]
    actions: list[dict[str, Any]] = [{"type": "sell_card", "card_id": card_id}]
    if card["name"] not in _city_names(state, seat):
        free_sources = _free_sources(state, seat, card)
        for source in free_sources:
            actions.append({"type": "build_card", "card_id": card_id, "free_source": source,
                            "payment": {"bank": 0, "left": 0, "right": 0}, "purchases": []})
        if not free_sources:
            for plan in _payment_plans(state, seat, card["cost"], card["coin_cost"]):
                actions.append({"type": "build_card", "card_id": card_id, **plan})
    player = state["players"][seat]
    stages = WONDERS[player["wonder"]][player["wonder_side"]]
    stage_index = len(player["wonder_stages"])
    if stage_index < len(stages):
        for plan in _payment_plans(state, seat, stages[stage_index]["cost"]):
            actions.append({
                "type": "build_wonder", "card_id": card_id,
                "stage": stage_index + 1, **plan,
            })
    return actions


def _action_space(state: dict[str, Any], actions: list[dict[str, Any]]) -> ActionSpace:
    return ActionSpace.from_actions(state["phase"], state["decision_count"], actions)


def decision_seats(state: dict[str, Any]) -> list[int]:
    """Seats allowed to choose from one sealed observation snapshot."""
    if state["status"] != "active":
        return []
    if state["phase"] == "draft":
        return [
            seat for seat in range(state["player_count"])
            if str(seat) not in state["pending_choices"]
        ]
    return [state["active_seat"]]


def legal_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    if seat not in decision_seats(state):
        return []
    actions: list[dict[str, Any]] = []
    if state["phase"] in ("draft", "seventh_card"):
        for card_id in state["hands"][seat]:
            actions.extend(_actions_for_card(state, seat, card_id))
    elif state["phase"] == "build_from_discard":
        for card_id in state["discard"]:
            if CARDS[card_id]["name"] not in _city_names(state, seat):
                actions.append({"type": "build_discard", "card_id": card_id})
        if not actions:
            actions.append({"type": "skip_discard"})
    return _action_space(state, actions).wrapped()


def _pay(state: dict[str, Any], seat: int, payment: dict[str, int]) -> None:
    total = sum(payment.values())
    state["players"][seat]["coins"] -= total
    state["players"][_left(state, seat)]["coins"] += payment["left"]
    state["players"][_right(state, seat)]["coins"] += payment["right"]


def _consume_free_source(state: dict[str, Any], seat: int, source: str | None) -> None:
    player = state["players"][seat]
    if source == "wonder_first_age":
        player["free_first_age_used"].append(state["age"])
    elif source == "wonder_last_age":
        player["free_last_age_used"].append(state["age"])


def _card_count(state: dict[str, Any], seat: int, color: str) -> int:
    return sum(CARDS[card_id]["color"] == color for card_id in state["players"][seat]["city"])


def _immediate_card_effect(state: dict[str, Any], seat: int, card_id: str) -> int:
    effect = CARDS[card_id]["effect"]
    gained = 0
    if effect == "coins_5":
        gained = 5
    elif effect == "coins_neighbor_brown":
        gained = sum(_card_count(state, other, "brown") for other in (seat, _left(state, seat), _right(state, seat)))
    elif effect == "coins_neighbor_gray":
        gained = 2 * sum(_card_count(state, other, "gray") for other in (seat, _left(state, seat), _right(state, seat)))
    elif effect == "score_yellow":
        gained = _card_count(state, seat, "yellow")
    elif effect == "score_brown":
        gained = _card_count(state, seat, "brown")
    elif effect == "score_gray":
        gained = 2 * _card_count(state, seat, "gray")
    elif effect == "score_red":
        gained = 3 * _card_count(state, seat, "red")
    elif effect == "score_stages":
        gained = 3 * len(state["players"][seat]["wonder_stages"])
    state["players"][seat]["coins"] += gained
    return gained


def _reveal_choices(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    choices = {int(seat): action for seat, action in state["pending_choices"].items()}
    free_builds: list[int] = []
    built_cards: list[tuple[int, str]] = []
    for seat in range(state["player_count"]):
        action = choices[seat]
        kind = action["type"]
        card_id = action["card_id"]
        if kind == "sell_card":
            state["discard"].append(card_id)
            state["players"][seat]["coins"] += 3
            events.append({"type": "card_sold", "seat": seat, "card_id": card_id, "coins": 3})
        elif kind == "build_card":
            _pay(state, seat, action["payment"])
            _consume_free_source(state, seat, action.get("free_source"))
            state["players"][seat]["city"].append(card_id)
            built_cards.append((seat, card_id))
            events.append({
                "type": "building_constructed", "seat": seat, "card_id": card_id,
                "name": CARDS[card_id]["name"], "payment": action["payment"],
                "free_source": action.get("free_source"),
            })
        elif kind == "build_wonder":
            _pay(state, seat, action["payment"])
            player = state["players"][seat]
            stage_index = len(player["wonder_stages"])
            player["wonder_stages"].append(card_id)
            stage = WONDERS[player["wonder"]][player["wonder_side"]][stage_index]
            player["coins"] += stage.get("coins", 0)
            if stage.get("special") == "build_discard":
                free_builds.append(seat)
            events.append({
                "type": "wonder_stage_constructed", "seat": seat,
                "wonder": player["wonder"], "stage": stage_index + 1,
                "payment": action["payment"],
            })
    # Immediate commercial effects see all cards constructed in the same turn.
    for seat, card_id in built_cards:
        gained = _immediate_card_effect(state, seat, card_id)
        if gained:
            events.append({"type": "coins_gained", "seat": seat, "amount": gained, "card_id": card_id})
    state["pending_choices"] = {}
    if free_builds:
        # On the sixth turn, the unchosen seventh cards are discarded before
        # end-of-turn Wonder effects resolve.  Babylon Night keeps its card.
        if state["pick"] == 6:
            for seat, hand in enumerate(state["hands"]):
                if not _has_seventh_power(state, seat):
                    state["discard"].extend(hand)
                    hand.clear()
        state["pending_free_builds"] = free_builds
        state["phase"] = "build_from_discard"
        state["active_seat"] = free_builds[0]
        state["resume_after_special"] = "after_draft"
    else:
        _after_draft_turn(state, events)


def _has_seventh_power(state: dict[str, Any], seat: int) -> bool:
    return _has_effect(state, seat, "play_seventh")


def _after_draft_turn(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    if state["pick"] < 6:
        direction_left = state["age"] in (1, 3)
        old_hands = state["hands"]
        new_hands = [[] for _ in range(state["player_count"])]
        for seat, hand in enumerate(old_hands):
            recipient = _left(state, seat) if direction_left else _right(state, seat)
            new_hands[recipient] = hand
        state["hands"] = new_hands
        state["pick"] += 1
        state["turn_count"] += 1
        state["phase"] = "draft"
        state["active_seat"] = 0
        return

    seventh: list[int] = []
    for seat, hand in enumerate(state["hands"]):
        if hand and _has_seventh_power(state, seat):
            seventh.append(seat)
        else:
            state["discard"].extend(hand)
            hand.clear()
    state["turn_count"] += 1
    if seventh:
        state["pending_seventh"] = seventh
        state["phase"] = "seventh_card"
        state["active_seat"] = seventh[0]
    else:
        _end_age(state, events)


def _military_strength(state: dict[str, Any], seat: int) -> int:
    player = state["players"][seat]
    strength = sum(CARDS[card_id]["military"] for card_id in player["city"])
    stages = WONDERS[player["wonder"]][player["wonder_side"]]
    strength += sum(stage.get("military", 0) for stage in stages[:len(player["wonder_stages"])])
    return strength


def _end_age(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    victory = {1: 1, 2: 3, 3: 5}[state["age"]]
    strengths = [_military_strength(state, seat) for seat in range(state["player_count"])]
    for seat in range(state["player_count"]):
        other = _right(state, seat)
        if strengths[seat] == strengths[other]:
            continue
        winner, loser = (seat, other) if strengths[seat] > strengths[other] else (other, seat)
        state["players"][winner]["military_tokens"].append(victory)
        state["players"][loser]["military_tokens"].append(-1)
        state["players"][winner]["military_tokens_by_age"][state["age"] - 1].append(victory)
        state["players"][loser]["military_tokens_by_age"][state["age"] - 1].append(-1)
        events.append({
            "type": "military_conflict", "age": state["age"],
            "winner": winner, "loser": loser, "victory_points": victory,
        })
    if state["age"] == 3:
        state["status"] = "finished"
        state["phase"] = "finished"
        state["active_seat"] = 0
        events.append({"type": "game_finished", "rankings": rankings(state)})
    else:
        _deal_age(state, state["age"] + 1)


def _continue_after_free_build(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    if state["pending_free_builds"]:
        state["phase"] = "build_from_discard"
        state["active_seat"] = state["pending_free_builds"][0]
        return
    resume = state["resume_after_special"]
    state["resume_after_special"] = None
    if resume == "after_draft":
        _after_draft_turn(state, events)
    elif resume == "seventh_card":
        _continue_seventh(state, events)
    else:  # pragma: no cover - invariant guarded
        raise AssertionError("invalid special-action continuation")


def _continue_seventh(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    if state["pending_seventh"]:
        state["phase"] = "seventh_card"
        state["active_seat"] = state["pending_seventh"][0]
    else:
        _end_age(state, events)


def _apply_seventh(state: dict[str, Any], seat: int, action: dict[str, Any], events: list[dict[str, Any]]) -> None:
    card_id = action["card_id"]
    state["hands"][seat].remove(card_id)
    kind = action["type"]
    free_build = False
    if kind == "sell_card":
        state["discard"].append(card_id)
        state["players"][seat]["coins"] += 3
        events.append({"type": "card_sold", "seat": seat, "card_id": card_id, "coins": 3})
    elif kind == "build_card":
        _pay(state, seat, action["payment"])
        _consume_free_source(state, seat, action.get("free_source"))
        state["players"][seat]["city"].append(card_id)
        gained = _immediate_card_effect(state, seat, card_id)
        events.append({"type": "building_constructed", "seat": seat, "card_id": card_id,
                       "name": CARDS[card_id]["name"], "payment": action["payment"],
                       "free_source": action.get("free_source")})
        if gained:
            events.append({"type": "coins_gained", "seat": seat, "amount": gained, "card_id": card_id})
    elif kind == "build_wonder":
        _pay(state, seat, action["payment"])
        player = state["players"][seat]
        stage_index = len(player["wonder_stages"])
        player["wonder_stages"].append(card_id)
        stage = WONDERS[player["wonder"]][player["wonder_side"]][stage_index]
        player["coins"] += stage.get("coins", 0)
        free_build = stage.get("special") == "build_discard"
        events.append({"type": "wonder_stage_constructed", "seat": seat,
                       "wonder": player["wonder"], "stage": stage_index + 1,
                       "payment": action["payment"]})
    state["pending_seventh"].remove(seat)
    if free_build:
        state["pending_free_builds"] = [seat]
        state["resume_after_special"] = "seventh_card"
        state["phase"] = "build_from_discard"
        state["active_seat"] = seat
    else:
        _continue_seventh(state, events)


def apply_action(
    state: dict[str, Any], seat: int, action: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    legal = [item["action"] for item in legal_actions(state, seat)]
    canonical = _action_space(state, legal).require(action, error_factory=RuleError)
    next_state = deepcopy(state)
    events: list[dict[str, Any]] = [action_accepted(seat, canonical)]
    phase = next_state["phase"]

    if phase == "draft":
        next_state["hands"][seat].remove(canonical["card_id"])
        next_state["pending_choices"][str(seat)] = canonical
        missing = [candidate for candidate in range(next_state["player_count"])
                   if str(candidate) not in next_state["pending_choices"]]
        if missing:
            next_state["active_seat"] = missing[0]
        else:
            _reveal_choices(next_state, events)
    elif phase == "seventh_card":
        _apply_seventh(next_state, seat, canonical, events)
    elif phase == "build_from_discard":
        if canonical["type"] == "build_discard":
            card_id = canonical["card_id"]
            next_state["discard"].remove(card_id)
            next_state["players"][seat]["city"].append(card_id)
            gained = _immediate_card_effect(next_state, seat, card_id)
            events.append({"type": "discard_building_constructed", "seat": seat,
                           "card_id": card_id, "name": CARDS[card_id]["name"]})
            if gained:
                events.append({"type": "coins_gained", "seat": seat, "amount": gained, "card_id": card_id})
        else:
            events.append({"type": "discard_build_skipped", "seat": seat})
        next_state["pending_free_builds"].pop(0)
        _continue_after_free_build(next_state, events)
    else:  # pragma: no cover - legal action gate prevents this
        raise RuleError("no action is available in the current phase")

    next_state["decision_count"] += 1
    validate_state(next_state)
    return next_state, events


def _science_score(counts: Counter[str], wilds: int) -> int:
    best = 0
    for compass in range(wilds + 1):
        for gear in range(wilds - compass + 1):
            tablet = wilds - compass - gear
            values = [counts["compass"] + compass, counts["gear"] + gear, counts["tablet"] + tablet]
            best = max(best, sum(value * value for value in values) + 7 * min(values))
    return best


def _guild_card_points(state: dict[str, Any], seat: int, card: dict[str, Any]) -> int:
    effect = card.get("effect")
    neighbors = (_left(state, seat), _right(state, seat))
    color_by_guild = {
        "guild_workers": ("brown", 1), "guild_craftsmens": ("gray", 2),
        "guild_magistrates": ("blue", 1), "guild_traders": ("yellow", 1),
        "guild_spies": ("red", 1), "guild_philosophers": ("green", 1),
    }
    if effect in color_by_guild:
        color, value = color_by_guild[effect]
        return value * sum(_card_count(state, other, color) for other in neighbors)
    if effect == "guild_builders":
        return sum(len(state["players"][other]["wonder_stages"])
                   for other in (seat, *neighbors))
    if effect == "guild_decorators":
        player = state["players"][seat]
        total = len(WONDERS[player["wonder"]][player["wonder_side"]])
        return 7 if len(player["wonder_stages"]) == total else 0
    if effect == "guild_shipowners":
        return sum(_card_count(state, seat, color) for color in ("brown", "gray", "purple"))
    if effect == "guild_scientists":
        player = state["players"][seat]
        city = [CARDS[card_id] for card_id in player["city"]]
        counts = Counter(candidate["science"] for candidate in city if candidate["science"])
        stages = WONDERS[player["wonder"]][player["wonder_side"]][:len(player["wonder_stages"])]
        wilds = sum(stage.get("science_wild", 0) for stage in stages)
        wilds += sum(candidate["effect"] == "guild_scientists" for candidate in city)
        return _science_score(counts, wilds) - _science_score(counts, max(0, wilds - 1))
    return 0


def score_breakdown(state: dict[str, Any], seat: int) -> dict[str, int]:
    player = state["players"][seat]
    city = [CARDS[card_id] for card_id in player["city"]]
    stages = WONDERS[player["wonder"]][player["wonder_side"]][:len(player["wonder_stages"])]
    science = Counter(card["science"] for card in city if card["science"])
    wilds = sum(stage.get("science_wild", 0) for stage in stages)
    wilds += sum(card["effect"] == "guild_scientists" for card in city)
    yellow = 0
    guild = 0
    for card in city:
        effect = card["effect"]
        if effect == "score_yellow":
            yellow += _card_count(state, seat, "yellow")
        elif effect == "score_brown":
            yellow += _card_count(state, seat, "brown")
        elif effect == "score_gray":
            yellow += 2 * _card_count(state, seat, "gray")
        elif effect == "score_red":
            yellow += _card_count(state, seat, "red")
        elif effect == "score_stages":
            yellow += len(player["wonder_stages"])
        elif effect and effect.startswith("guild_"):
            if effect != "guild_scientists":
                guild += _guild_card_points(state, seat, card)
    result = {
        "wonder": sum(stage.get("points", 0) for stage in stages),
        "treasure": player["coins"] // 3,
        "military": sum(player["military_tokens"]),
        "civil": sum(card["points"] for card in city),
        "commercial": yellow,
        "science": _science_score(science, wilds),
        "guilds": guild,
    }
    result["total"] = sum(result.values())
    return result


def score(state: dict[str, Any], seat: int) -> int:
    return score_breakdown(state, seat)["total"]


def rankings(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {"seat": seat, "score": score(state, seat), "coins": player["coins"],
         "breakdown": score_breakdown(state, seat)}
        for seat, player in enumerate(state["players"])
    ]
    return assign_competition_ranks(
        rows, sort_key=lambda row: (-row["score"], -row["coins"], row["seat"]),
        tie_key=lambda row: (row["score"], row["coins"]),
    )


def _direct_benefits(values: dict[str, Any]) -> list[dict[str, Any]]:
    benefits: list[dict[str, Any]] = []
    for options in values.get("production", []):
        benefits.append({"type": "production", "resources": list(options)})
    for field, kind in (
        ("points", "points"), ("coins", "coins"), ("military", "military"),
        ("science_wild", "science_wild"),
    ):
        if values.get(field):
            benefits.append({"type": kind, "amount": values[field]})
    if values.get("science"):
        benefits.append({"type": "science", "symbol": values["science"]})
    if values.get("special"):
        benefits.append({"type": "special", "effect": values["special"]})
    return benefits


def _card_view(card_id: str) -> dict[str, Any]:
    card = deepcopy(CARDS[card_id])
    benefits = _direct_benefits(card)
    benefits.extend(deepcopy(EFFECT_BENEFITS.get(card.get("effect"), [])))
    card["benefits"] = benefits
    card["chain_to"] = CHAIN_TO.get(card["name"], [])
    return card


def _city_card_view(state: dict[str, Any], seat: int, card_id: str) -> dict[str, Any]:
    card = _card_view(card_id)
    if card["color"] == "purple":
        card["current_points"] = _guild_card_points(state, seat, CARDS[card_id])
    return card


def _resource_units_view(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    player = state["players"][seat]
    wonder = WONDERS[player["wonder"]]
    units = [{
        "source_type": "wonder_start", "source_id": player["wonder"],
        "source_name": wonder["name"],
        "options": [wonder["starting_resource"]], "tradeable": True,
    }]
    for card_id in player["city"]:
        card = CARDS[card_id]
        for index, options in enumerate(card["production"]):
            units.append({
                "source_type": "card", "source_id": card_id,
                "source_name": card["name"], "unit": index + 1,
                "source_color": card["color"],
                "options": list(options), "tradeable": card["color"] in ("brown", "gray"),
            })
        for benefit in EFFECT_BENEFITS.get(card.get("effect"), []):
            if benefit["type"] == "trade_discount":
                units.append({
                    "source_type": "card", "source_id": card_id,
                    "source_name": card["name"], "source_color": card["color"],
                    "kind": "trade_discount", "directions": list(benefit["directions"]),
                    "options": list(benefit["resources"]), "tradeable": False,
                })
    stages = wonder[player["wonder_side"]]
    for stage_index, stage in enumerate(stages[:len(player["wonder_stages"])]):
        for unit_index, options in enumerate(stage.get("production", [])):
            units.append({
                "source_type": "wonder_stage",
                "source_id": f"{player['wonder']}-{player['wonder_side']}-{stage_index + 1}",
                "source_name": f"{wonder['name']} stage {stage_index + 1}",
                "stage": stage_index + 1, "unit": unit_index + 1,
                "options": list(options), "tradeable": False,
            })
    return units


def observe(state: dict[str, Any], seat: int) -> dict[str, Any]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    players = []
    for player in state["players"]:
        stages = WONDERS[player["wonder"]][player["wonder_side"]]
        players.append({
            "seat": player["seat"], "coins": player["coins"],
            "wonder": player["wonder"], "wonder_name": WONDERS[player["wonder"]]["name"],
            "wonder_side": player["wonder_side"],
            "starting_resource": WONDERS[player["wonder"]]["starting_resource"],
            "wonder_stages": [
                {
                    **deepcopy(stage), "stage": index + 1,
                    "built": index < len(player["wonder_stages"]),
                    "benefits": _direct_benefits(stage),
                }
                for index, stage in enumerate(stages)
            ],
            "city": [_city_card_view(state, player["seat"], card_id) for card_id in player["city"]],
            "resource_units": _resource_units_view(state, player["seat"]),
            "military_strength": _military_strength(state, player["seat"]),
            "military_tokens": list(player["military_tokens"]),
            "military_tokens_by_age": [list(tokens) for tokens in player["military_tokens_by_age"]],
            "score": score(state, player["seat"]),
            "score_breakdown": score_breakdown(state, player["seat"]),
            "hand_count": len(state["hands"][player["seat"]]),
            "hand": ([_card_view(card_id) for card_id in state["hands"][player["seat"]]]
                     if player["seat"] == seat else [{"hidden": True}] * len(state["hands"][player["seat"]])),
            "choice_submitted": str(player["seat"]) in state["pending_choices"],
        })
    return {
        "game": "seven_wonders", "rules_version": state["rules_version"],
        "viewer_seat": seat, "status": state["status"], "phase": state["phase"],
        "age": state["age"], "pick": state["pick"], "turn_count": state["turn_count"],
        "decision_count": state["decision_count"], "active_seat": state["active_seat"],
        "decision_seats": decision_seats(state),
        "pass_direction": "left" if state["age"] in (1, 3) else "right",
        "discard_count": len(state["discard"]),
        "pending_choice_seats": sorted(int(value) for value in state["pending_choices"]),
        "players": players, "rankings": rankings(state),
    }


def validate_state(state: dict[str, Any]) -> None:
    if state.get("schema_version") != "agentbga.seven_wonders.state.v1":
        raise AssertionError("invalid 7 Wonders state schema")
    if state.get("rules_version") != RULES_VERSION:
        raise AssertionError("rules version mismatch")
    count = state.get("player_count")
    if not isinstance(count, int) or count < 3 or count > 7:
        raise AssertionError("invalid player count")
    if len(state.get("players", [])) != count or len(state.get("hands", [])) != count:
        raise AssertionError("player collections do not match player count")
    if state["status"] not in ("active", "finished"):
        raise AssertionError("invalid game status")
    if state["phase"] not in ("draft", "build_from_discard", "seventh_card", "finished"):
        raise AssertionError("invalid game phase")
    if state["age"] not in (1, 2, 3) or state["pick"] not in range(1, 7):
        raise AssertionError("invalid age or pick")
    if state["status"] == "active" and state["active_seat"] not in range(count):
        raise AssertionError("active seat out of range")
    if len({player["wonder"] for player in state["players"]}) != count:
        raise AssertionError("wonders must be unique")
    for seat, player in enumerate(state["players"]):
        if player["seat"] != seat or player["wonder"] not in WONDERS:
            raise AssertionError("invalid player identity")
        if player["wonder_side"] not in ("day", "night"):
            raise AssertionError("invalid wonder side")
        total_stages = len(WONDERS[player["wonder"]][player["wonder_side"]])
        if len(player["wonder_stages"]) > total_stages:
            raise AssertionError("too many wonder stages")
        if not isinstance(player["coins"], int) or player["coins"] < 0:
            raise AssertionError("coins cannot be negative")
        if any(token not in (-1, 1, 3, 5) for token in player["military_tokens"]):
            raise AssertionError("invalid military token")
        tokens_by_age = player.get("military_tokens_by_age")
        if (not isinstance(tokens_by_age, list) or len(tokens_by_age) != 3
                or any(not isinstance(tokens, list) for tokens in tokens_by_age)):
            raise AssertionError("invalid military token age groups")
        if [token for tokens in tokens_by_age for token in tokens] != player["military_tokens"]:
            raise AssertionError("military token age groups do not match tokens")
        for age, tokens in enumerate(tokens_by_age, start=1):
            allowed = {-1, {1: 1, 2: 3, 3: 5}[age]}
            if len(tokens) > 2 or any(token not in allowed for token in tokens):
                raise AssertionError("military token is assigned to the wrong age")
        names = [CARDS[card_id]["name"] for card_id in player["city"]]
        if len(names) != len(set(names)):
            raise AssertionError("a city cannot contain duplicate building names")
    located: list[str] = []
    for deck in state["age_decks"].values():
        located.extend(deck)
    for hand in state["hands"]:
        located.extend(hand)
    located.extend(state["discard"])
    for player in state["players"]:
        located.extend(player["city"])
        located.extend(player["wonder_stages"])
    for action in state["pending_choices"].values():
        located.append(action["card_id"])
    if len(located) != len(set(located)):
        raise AssertionError("physical cards must remain unique")
    if set(located) != set(state["card_pool"]):
        raise AssertionError("card conservation failed")
    if any(card_id not in CARDS for card_id in located):
        raise AssertionError("unknown card id")
    if state["phase"] == "draft":
        expected = [seat for seat in range(count) if str(seat) not in state["pending_choices"]]
        if not expected or state["active_seat"] != expected[0]:
            raise AssertionError("draft active seat is inconsistent")
    if state["phase"] == "build_from_discard":
        if not state["pending_free_builds"] or state["active_seat"] != state["pending_free_builds"][0]:
            raise AssertionError("discard build queue is inconsistent")
    if state["phase"] == "seventh_card":
        if not state["pending_seventh"] or state["active_seat"] != state["pending_seventh"][0]:
            raise AssertionError("seventh-card queue is inconsistent")
