"""Deterministic Brass: Birmingham rules plugin under active implementation."""

from __future__ import annotations

from copy import deepcopy
from itertools import combinations
import random
from typing import Any

from .game import GameRuleError
from .mechanics import (
    ActionBudget,
    ActionSpace,
    MarketTrack,
    action_accepted,
    assign_competition_ranks,
    domain_event,
    private_items,
    shortest_distances,
    stable_metric_order,
    state_digest,
    validate_unique_items,
)


RULES_VERSION = "roxley-2018.11-playable-beta.2"
ACTION_TYPES = ("build", "network", "develop", "sell", "loan", "scout", "pass")
INDUSTRY_TYPES = (
    "cotton_mill", "coal_mine", "iron_works", "manufacturer", "pottery", "brewery",
)
LOCATIONS = (
    "belper", "birmingham", "burton_on_trent", "cannock", "coalbrookdale", "coventry",
    "derby", "dudley", "kidderminster", "leek", "nuneaton", "redditch", "stafford",
    "stoke_on_trent", "stone", "tamworth", "uttoxeter", "walsall", "wolverhampton",
    "worcester",
)
MERCHANT_LOCATIONS = ("warrington", "nottingham", "shrewsbury", "gloucester", "oxford")
MERCHANT_LOCATION_DATA = {
    "shrewsbury": {"slots": 1, "minimum_players": 2, "bonus": {"type": "vp", "amount": 4}},
    "gloucester": {"slots": 2, "minimum_players": 2, "bonus": {"type": "develop", "amount": 1}},
    "oxford": {"slots": 2, "minimum_players": 2, "bonus": {"type": "income_spaces", "amount": 2}},
    "warrington": {"slots": 2, "minimum_players": 3, "bonus": {"type": "money", "amount": 5}},
    "nottingham": {"slots": 2, "minimum_players": 4, "bonus": {"type": "vp", "amount": 3}},
}
INDUSTRY_TILE_COUNTS = {
    "cotton_mill": 11, "coal_mine": 7, "iron_works": 4,
    "manufacturer": 11, "pottery": 5, "brewery": 7,
}
# level, copies, money, coal, iron, beer-to-sell, vp, income spaces, link icons,
# developable, produced in canal, produced in rail
INDUSTRY_TILE_LEVELS = {
    "cotton_mill": (
        (1, 3, 12, 0, 0, 1, 5, 5, 1, True, 0, 0),
        (2, 2, 14, 1, 0, 1, 5, 4, 2, True, 0, 0),
        (3, 3, 16, 1, 1, 1, 9, 3, 1, True, 0, 0),
        (4, 3, 18, 1, 1, 1, 12, 2, 1, True, 0, 0),
    ),
    "coal_mine": (
        (1, 1, 5, 0, 0, 0, 1, 4, 2, True, 2, 2),
        (2, 2, 7, 0, 0, 0, 2, 7, 1, True, 3, 3),
        (3, 2, 8, 0, 1, 0, 3, 6, 1, True, 4, 4),
        (4, 2, 10, 0, 1, 0, 4, 5, 1, True, 5, 5),
    ),
    "iron_works": (
        (1, 1, 5, 1, 0, 0, 3, 3, 1, True, 4, 4),
        (2, 1, 7, 1, 0, 0, 5, 3, 1, True, 4, 4),
        (3, 1, 9, 1, 0, 0, 7, 2, 1, True, 5, 5),
        (4, 1, 12, 1, 0, 0, 9, 1, 1, True, 6, 6),
    ),
    "manufacturer": (
        (1, 1, 8, 1, 0, 1, 3, 5, 2, True, 0, 0),
        (2, 2, 10, 0, 1, 1, 5, 1, 1, True, 0, 0),
        (3, 1, 12, 2, 0, 0, 4, 4, 0, True, 0, 0),
        (4, 1, 8, 0, 1, 1, 3, 6, 1, True, 0, 0),
        (5, 2, 16, 1, 0, 2, 8, 2, 2, True, 0, 0),
        (6, 1, 20, 0, 0, 1, 7, 6, 1, True, 0, 0),
        (7, 1, 16, 1, 1, 0, 9, 4, 0, True, 0, 0),
        (8, 2, 20, 0, 2, 1, 11, 1, 1, True, 0, 0),
    ),
    "pottery": (
        (1, 1, 17, 0, 1, 1, 10, 5, 1, False, 0, 0),
        (2, 1, 0, 1, 0, 1, 1, 1, 1, True, 0, 0),
        (3, 1, 22, 2, 0, 2, 11, 5, 1, False, 0, 0),
        (4, 1, 0, 1, 0, 1, 1, 1, 1, True, 0, 0),
        (5, 1, 24, 2, 0, 2, 20, 5, 1, True, 0, 0),
    ),
    "brewery": (
        (1, 2, 5, 0, 1, 0, 4, 4, 2, True, 1, 0),
        (2, 2, 7, 0, 1, 0, 5, 5, 2, True, 1, 2),
        (3, 2, 9, 0, 1, 0, 7, 5, 2, True, 1, 2),
        (4, 1, 9, 0, 1, 0, 10, 5, 2, True, 0, 2),
    ),
}
CITY_SLOTS = {
    "belper": (("cotton_mill", "manufacturer"), ("coal_mine",), ("pottery",)),
    "derby": (("cotton_mill", "brewery"), ("cotton_mill", "manufacturer"), ("iron_works",)),
    "leek": (("cotton_mill", "manufacturer"), ("cotton_mill", "coal_mine")),
    "stoke_on_trent": (("cotton_mill", "manufacturer"), ("pottery", "iron_works"), ("manufacturer",)),
    "stone": (("cotton_mill", "brewery"), ("manufacturer", "coal_mine")),
    "uttoxeter": (("manufacturer", "brewery"), ("cotton_mill", "brewery")),
    "stafford": (("manufacturer", "brewery"), ("pottery",)),
    "burton_on_trent": (("manufacturer", "coal_mine"), ("brewery",)),
    "cannock": (("manufacturer", "coal_mine"), ("coal_mine",)),
    "tamworth": (("cotton_mill", "coal_mine"), ("cotton_mill", "coal_mine")),
    "walsall": (("iron_works", "manufacturer"), ("manufacturer", "brewery")),
    "wolverhampton": (("manufacturer",), ("manufacturer", "coal_mine")),
    "coalbrookdale": (("iron_works", "brewery"), ("iron_works",), ("coal_mine",)),
    "dudley": (("coal_mine",), ("iron_works",)),
    "kidderminster": (("cotton_mill", "coal_mine"), ("cotton_mill",)),
    "worcester": (("cotton_mill",), ("cotton_mill",)),
    "birmingham": (("cotton_mill", "manufacturer"), ("manufacturer",), ("iron_works",), ("manufacturer",)),
    "coventry": (("pottery",), ("manufacturer", "coal_mine"), ("iron_works", "manufacturer")),
    "nuneaton": (("manufacturer", "brewery"), ("cotton_mill", "coal_mine")),
    "redditch": (("manufacturer", "coal_mine"), ("iron_works",)),
}
ROUNDS_PER_ERA = {2: 10, 3: 9, 4: 8}
_BOTH_ERAS = ("canal", "rail")
CONNECTION_DATA = (
    (("belper", "derby"), _BOTH_ERAS), (("belper", "leek"), ("rail",)),
    (("birmingham", "coventry"), _BOTH_ERAS), (("birmingham", "dudley"), _BOTH_ERAS),
    (("birmingham", "nuneaton"), ("rail",)), (("birmingham", "oxford"), _BOTH_ERAS),
    (("birmingham", "redditch"), ("rail",)), (("birmingham", "tamworth"), _BOTH_ERAS),
    (("birmingham", "walsall"), _BOTH_ERAS), (("birmingham", "worcester"), _BOTH_ERAS),
    (("burton_on_trent", "cannock"), ("rail",)), (("burton_on_trent", "derby"), _BOTH_ERAS),
    (("burton_on_trent", "stone"), _BOTH_ERAS), (("burton_on_trent", "tamworth"), _BOTH_ERAS),
    (("burton_on_trent", "walsall"), ("canal",)), (("cannock", "stafford"), _BOTH_ERAS),
    (("cannock", "farm_brewery_cannock"), _BOTH_ERAS), (("cannock", "walsall"), _BOTH_ERAS),
    (("cannock", "wolverhampton"), _BOTH_ERAS), (("coalbrookdale", "kidderminster"), _BOTH_ERAS),
    (("coalbrookdale", "shrewsbury"), _BOTH_ERAS), (("coalbrookdale", "wolverhampton"), _BOTH_ERAS),
    (("coventry", "nuneaton"), ("rail",)), (("derby", "nottingham"), _BOTH_ERAS),
    (("derby", "uttoxeter"), ("rail",)), (("dudley", "kidderminster"), _BOTH_ERAS),
    (("dudley", "wolverhampton"), _BOTH_ERAS), (("gloucester", "redditch"), _BOTH_ERAS),
    (("gloucester", "worcester"), _BOTH_ERAS),
    (("kidderminster", "worcester", "farm_brewery_kidderminster_worcester"), _BOTH_ERAS),
    (("leek", "stoke_on_trent"), _BOTH_ERAS), (("nuneaton", "tamworth"), _BOTH_ERAS),
    (("redditch", "oxford"), _BOTH_ERAS), (("stafford", "stone"), _BOTH_ERAS),
    (("stoke_on_trent", "stone"), _BOTH_ERAS), (("stoke_on_trent", "warrington"), _BOTH_ERAS),
    (("stone", "uttoxeter"), ("rail",)), (("tamworth", "walsall"), ("rail",)),
    (("walsall", "wolverhampton"), _BOTH_ERAS),
)
CONNECTION_ENDPOINTS = tuple(endpoints for endpoints, _eras in CONNECTION_DATA)

CARD_DECK_COUNTS = {
    2: {
        "locations": {
            "stafford": 2, "burton_on_trent": 2, "cannock": 2, "tamworth": 1,
            "walsall": 1, "coalbrookdale": 3, "dudley": 2, "kidderminster": 2,
            "wolverhampton": 2, "worcester": 2, "birmingham": 3, "coventry": 3,
            "nuneaton": 1, "redditch": 1,
        },
        "industries": {"iron_works": 4, "coal_mine": 2, "pottery": 2, "brewery": 5},
        "dual": 0,
    },
    3: {
        "locations": {
            "leek": 2, "stoke_on_trent": 3, "stone": 2, "uttoxeter": 1,
            "stafford": 2, "burton_on_trent": 2, "cannock": 2, "tamworth": 1,
            "walsall": 1, "coalbrookdale": 3, "dudley": 2, "kidderminster": 2,
            "wolverhampton": 2, "worcester": 2, "birmingham": 3, "coventry": 3,
            "nuneaton": 1, "redditch": 1,
        },
        "industries": {"iron_works": 4, "coal_mine": 2, "pottery": 2, "brewery": 5},
        "dual": 6,
    },
    4: {
        "locations": {
            "belper": 2, "derby": 3, "leek": 2, "stoke_on_trent": 3, "stone": 2,
            "uttoxeter": 2, "stafford": 2, "burton_on_trent": 2, "cannock": 2,
            "tamworth": 1, "walsall": 1, "coalbrookdale": 3, "dudley": 2,
            "kidderminster": 2, "wolverhampton": 2, "worcester": 2,
            "birmingham": 3, "coventry": 3, "nuneaton": 1, "redditch": 1,
        },
        "industries": {"iron_works": 4, "coal_mine": 3, "pottery": 3, "brewery": 5},
        "dual": 8,
    },
}


class RuleError(GameRuleError):
    pass


def describe() -> dict[str, Any]:
    return {
        "id": "brass_birmingham",
        "name": "Brass: Birmingham",
        "rules_version": RULES_VERSION,
        "players": {"minimum": 2, "maximum": 4},
        "hidden_information": True,
        "implementation_status": "playable_beta",
        "runnable": True,
        "decision_model": "two_actions_per_turn_with_multiple_decision_steps",
        "action_types": list(ACTION_TYPES),
        "rules_sources": ["Roxley Brass: Birmingham Rulebook, version 2018.11"],
        "content_scope": (
            "Deterministic official deck, city, connection, merchant, market, and industry data. "
            "Build and Sell use explicit resource-source decisions; Canal Network, Develop, "
            "Loan, Scout, single/double Rail Network, liquidation, and both scoring phases are "
            "implemented with replay-safe decision steps."
        ),
    }


def _card_deck(players: int) -> list[dict[str, Any]]:
    """Create the player-count card deck as identifiers, without publisher artwork."""
    cards: list[dict[str, Any]] = []
    counts = CARD_DECK_COUNTS[players]
    for target, copies in counts["locations"].items():
        for copy in range(1, copies + 1):
            cards.append({
                "id": f"location-{target}-{copy}", "card_type": "location",
                "location": target,
            })
    for target, copies in counts["industries"].items():
        for copy in range(1, copies + 1):
            cards.append({
                "id": f"industry-{target}-{copy}", "card_type": "industry",
                "industry": target, "industries": [target],
            })
    for copy in range(1, counts["dual"] + 1):
        cards.append({
            "id": f"industry-cotton-manufacturer-{copy}", "card_type": "industry",
            "industries": ["cotton_mill", "manufacturer"],
        })
    return cards


def _industry_stacks() -> dict[str, list[dict[str, Any]]]:
    stacks: dict[str, list[dict[str, Any]]] = {}
    for industry in INDUSTRY_TYPES:
        stack = []
        sequence = 0
        for (level, copies, money, coal, iron, beer_to_sell, vp, income,
             link_icons, developable, canal_production, rail_production) in INDUSTRY_TILE_LEVELS[industry]:
            for _ in range(copies):
                sequence += 1
                stack.append({
                    "id": f"{industry}-{sequence:02d}", "industry": industry,
                    "sequence_index": sequence, "level": level, "money_cost": money,
                    "coal_cost": coal, "iron_cost": iron, "beer_to_sell": beer_to_sell,
                    "vp": vp, "income_spaces": income, "link_icons": link_icons,
                    "developable": developable,
                    "production": {"canal": canal_production, "rail": rail_production},
                    "allowed_eras": (["canal", "rail"] if (industry, level) == ("pottery", 1) else
                                      ["canal"] if level == 1 else
                                      ["rail"] if (industry, level) in {
                                          ("pottery", 5), ("brewery", 4),
                                      } else ["canal", "rail"]),
                    "state": "player_mat", "data_status": "verified_player_mat",
                })
        stacks[industry] = stack
    return stacks


def _merchant_locations(players: int, rng: random.Random) -> list[dict[str, Any]]:
    tile_faces = ["blank", "blank", "any", "cotton_mill", "manufacturer"]
    if players >= 3:
        tile_faces.extend(["pottery", "manufacturer"])
    if players >= 4:
        tile_faces.extend(["any", "cotton_mill"])
    rng.shuffle(tile_faces)
    locations = []
    for location in MERCHANT_LOCATIONS:
        data = MERCHANT_LOCATION_DATA[location]
        if players < data["minimum_players"]:
            continue
        slots = []
        for index in range(1, data["slots"] + 1):
            buys = tile_faces.pop()
            slots.append({
                "id": f"{location}-merchant-{index}", "buys": buys,
                "beer": 0 if buys == "blank" else 1,
            })
        locations.append({
            "id": location, "bonus": deepcopy(data["bonus"]), "slots": slots,
            "data_status": "verified_merchant_tiles_and_location_bonus",
        })
    if tile_faces:
        raise AssertionError("merchant tile setup did not consume the active tile pool")
    return locations


def _market_state(resource: str) -> dict[str, Any]:
    if resource == "coal":
        prices = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7]
        occupied = [False] + [True] * 13
        external_price = 8
    else:
        prices = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
        occupied = [False, False, True, True, True, True, True, True, True, True]
        external_price = 6
    return {
        "prices": prices, "occupied": occupied, "external_price": external_price,
        "purchase_order": list(range(len(prices))),
        "refill_order": list(reversed(range(len(prices)))),
    }


def _market_track(state: dict[str, Any], resource: str) -> MarketTrack:
    market = state["markets"][resource]
    return MarketTrack(
        prices=tuple(market["prices"]), occupied=market["occupied"],
        purchase_order=tuple(market["purchase_order"]),
        refill_order=tuple(market["refill_order"]), external_price=market["external_price"],
    )


def _connection_spaces() -> list[dict[str, Any]]:
    return [{
        "id": f"connection-{index:02d}", "endpoints": list(endpoints),
        "available_eras": list(eras), "data_status": "verified_from_official_board",
    } for index, (endpoints, eras) in enumerate(CONNECTION_DATA, 1)]


def new_game(players: int, seed: int, config: dict[str, Any] | None = None) -> dict[str, Any]:
    if players not in (2, 3, 4):
        raise RuleError("Brass: Birmingham requires 2, 3, or 4 players")
    if config:
        raise RuleError("Brass: Birmingham does not accept game configuration")
    rng = random.Random(seed)
    deck = _card_deck(players)
    rng.shuffle(deck)
    rows = []
    for seat in range(players):
        hand = [deck.pop() for _ in range(8)]
        initial_discard = deck.pop()
        initial_discard["face_up"] = False
        rows.append({
            "seat": seat, "money": 17, "income_position": 10, "vp": 0,
            "spent_this_round": 0, "hand": hand, "discard": [initial_discard],
            "wild_cards": {"location": 0, "industry": 0},
            "removed_industries": [],
            "industry_stacks": _industry_stacks(), "links_remaining": 14,
        })
    turn_order = list(range(players))
    rng.shuffle(turn_order)
    active_seat = turn_order[0]
    state = {
        "schema_version": "agentbga.brass_birmingham.state.v1",
        "game_id": "brass_birmingham", "rules_version": RULES_VERSION,
        "implementation_status": "playable_beta", "seed": seed,
        "player_count": players, "status": "active", "phase": "choose_action",
        "era": "canal", "round": 1, "round_limit": ROUNDS_PER_ERA[players],
        "turn_count": 0, "decision_count": 0,
        "shuffle_count": 1,
        "turn_order": turn_order, "active_seat": active_seat,
        "pending_action": None, "pending_card": None, "pending_build": None,
        "pending_sell": None, "pending_network": None, "pending_develop": None,
        "pending_round_transition": None, "pending_income": None,
        "turn": {
            "active_seat": active_seat, "decision": "choose_action", "phase": "choose_action",
            "actions_total": 1, "actions_remaining": 1,
        },
        "draw_deck": deck,
        "wild_cards": {"location": 4, "industry": 4},
        "markets": {
            "coal": _market_state("coal"), "iron": _market_state("iron"),
        },
        "general_supply": {"coal": "unlimited", "iron": "unlimited", "beer": "unlimited"},
        "board": {
            "map_status": "verified_city_slots_and_link_eras",
            "locations": [{
                "id": location, "kind": "industry",
                "industry_slots": [{
                    "id": f"{location}-slot-{index}", "accepts": list(accepts),
                    "industry_id": None,
                } for index, accepts in enumerate(CITY_SLOTS[location], 1)],
            } for location in LOCATIONS] + [{
                "id": "farm_brewery_cannock", "kind": "farm_brewery",
                "industry_slots": [{"id": "farm_brewery_cannock-slot-1", "accepts": ["brewery"], "industry_id": None}],
            }, {
                "id": "farm_brewery_kidderminster_worcester", "kind": "farm_brewery",
                "industry_slots": [{"id": "farm_brewery_kidderminster_worcester-slot-1", "accepts": ["brewery"], "industry_id": None}],
            }],
            "merchant_locations": _merchant_locations(players, rng),
            "connection_spaces": _connection_spaces(), "industries": [], "links": [],
        },
        "players": rows,
    }
    validate_state(state)
    return state


def state_hash(state: dict[str, Any]) -> str:
    return state_digest(state)


def _action_space(state: dict[str, Any], actions: list[dict[str, Any]]) -> ActionSpace:
    return ActionSpace.from_actions(
        f"{state['era']}:{state['turn']['decision']}", state["decision_count"], actions,
        prefix="brass",
    )


def legal_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    if state["status"] != "active" or seat != state["active_seat"]:
        return []
    player = state["players"][seat]
    if state["phase"] == "choose_action":
        actions = [{"type": "select_action", "action": "pass"}]
        build_cards = list(player["hand"])
        build_cards.extend(
            {"card_type": f"wild_{kind}"} for kind, count in player["wild_cards"].items()
            if count
        )
        if any(_build_placements(state, seat, card) for card in build_cards):
            actions.append({"type": "select_action", "action": "build"})
        if (player["links_remaining"] and player["money"] >= (3 if state["era"] == "canal" else 5)
                and _network_link_actions(state, seat)):
            actions.append({"type": "select_action", "action": "network"})
        if _develop_choices(state, seat):
            actions.append({"type": "select_action", "action": "develop"})
        if _sell_targets(state, seat):
            actions.append({"type": "select_action", "action": "sell"})
        if _income_level(player["income_position"]) > -10:
            actions.append({"type": "select_action", "action": "loan"})
        if (len(player["hand"]) >= 3 and not any(player["wild_cards"].values())
                and all(state["wild_cards"][kind] > 0 for kind in ("location", "industry"))):
            actions.append({"type": "select_action", "action": "scout"})
    elif state["phase"] == "choose_discard_card":
        cards = player["hand"]
        wilds = [kind for kind, count in player["wild_cards"].items() if count]
        if state["pending_action"] == "build":
            cards = [card for card in cards if _build_placements(state, seat, card)]
            wilds = [kind for kind in wilds if _build_placements(
                state, seat, {"card_type": f"wild_{kind}"},
            )]
        actions = [{"type": "discard_card", "card_id": card["id"]} for card in cards]
        actions.extend({"type": "discard_wild", "wild_type": kind} for kind in wilds)
    elif state["phase"] == "build_choose_placement":
        actions = _build_placements(state, seat, state["pending_card"])
    elif state["phase"] in {"build_choose_coal_source", "build_choose_iron_source"}:
        resource = "coal" if state["phase"] == "build_choose_coal_source" else "iron"
        pending = state["pending_build"]
        actions = _resource_source_actions(
            state, resource, pending["location_id"],
            player["money"] - pending["total_cost"],
        )
    elif state["phase"] in {"sell_choose_industry", "sell_continue"}:
        actions = _sell_targets(state, seat)
        if state["phase"] == "sell_continue":
            actions.append({"type": "finish_sell"})
    elif state["phase"] == "sell_choose_beer_source":
        actions = _beer_source_actions(state, seat, state["pending_sell"])
    elif state["phase"] == "sell_choose_merchant_develop":
        actions = [{"type": "merchant_bonus_develop", "industry": industry}
                   for industry in INDUSTRY_TYPES
                   if player["industry_stacks"][industry]
                   and player["industry_stacks"][industry][0]["developable"]]
    elif state["phase"] == "scout_choose_extra_cards":
        actions = [{"type": "scout_discard_extra", "card_ids": sorted(card["id"] for card in pair)}
                   for pair in combinations(player["hand"], 2)]
    elif state["phase"] == "develop_choose_tiles":
        actions = _develop_choices(state, seat)
    elif state["phase"] == "develop_choose_iron_source":
        actions = _resource_source_actions(
            state, "iron", "", player["money"] - state["pending_develop"]["total_cost"],
        )
    elif state["phase"] == "network_choose_link":
        pending = state.get("pending_network")
        actions = (_double_rail_first_actions(state, seat)
                   if state["era"] == "rail" and pending
                   and pending.get("links_total") == 2 and not pending["links"]
                   else _network_link_actions(state, seat))
    elif state["phase"] == "network_choose_mode":
        actions = [{"type": "select_network_count", "count": 1, "cost": 5}]
        if (player["links_remaining"] >= 2 and player["money"] >= 15
                and _double_rail_first_actions(state, seat)):
            actions.append({"type": "select_network_count", "count": 2, "cost": 15})
    elif state["phase"] == "network_choose_coal_source":
        pending = state["pending_network"]
        current = pending["links"][-1]
        connection = next(space for space in state["board"]["connection_spaces"]
                          if space["id"] == current["connection_id"])
        confirmed = [link["connection_id"] for link in pending["links"][:-1]
                     if link["coal_consumed"]]
        actions = _coal_source_actions_for_nodes(
            state, connection["endpoints"], player["money"] - pending["total_cost"],
            confirmed,
        )
        if pending["links_total"] == 2 and len(pending["links"]) == 1:
            actions = [action for action in actions
                       if _double_rail_continues_after_first_coal(state, seat, action)]
    elif state["phase"] == "network_choose_beer_source":
        actions = _network_beer_source_actions(state, seat, state["pending_network"])
    elif state["phase"] == "income_choose_liquidation":
        actions = [{
            "type": "liquidate_industry", "industry_id": industry["id"],
            "value": industry["money_cost"] // 2,
        } for industry in state["board"]["industries"] if industry["owner"] == seat]
    else:
        actions = []
    return _action_space(state, actions).wrapped()


def _set_decision(state: dict[str, Any], decision: str) -> None:
    state["phase"] = decision
    state["turn"]["phase"] = decision
    state["turn"]["decision"] = decision


def _location(state: dict[str, Any], location_id: str) -> dict[str, Any]:
    return next(location for location in state["board"]["locations"]
                if location["id"] == location_id)


def _card_allows_build(
    card: dict[str, Any], industry: str, location_id: str, network: set[str],
) -> bool:
    card_type = card["card_type"]
    if card_type == "location":
        return card["location"] == location_id
    if card_type == "wild_location":
        return not location_id.startswith("farm_brewery_")
    if card_type == "industry":
        return (industry in card.get("industries", [card.get("industry")])
                and (location_id in network or not network))
    if card_type == "wild_industry":
        return location_id in network or not network
    return False


def _connection_adjacency(
    state: dict[str, Any], extra_connection_ids: list[str] | tuple[str, ...] = (),
) -> dict[str, set[str]]:
    spaces = {space["id"]: space for space in state["board"]["connection_spaces"]}
    adjacency: dict[str, set[str]] = {}
    connection_ids = [link["connection_id"] for link in state["board"]["links"]]
    connection_ids.extend(extra_connection_ids)
    for connection_id in connection_ids:
        endpoints = spaces[connection_id]["endpoints"]
        for first, second in combinations(endpoints, 2):
            adjacency.setdefault(first, set()).add(second)
            adjacency.setdefault(second, set()).add(first)
    return adjacency


def _connected_distances(state: dict[str, Any], location_id: str) -> dict[str, int]:
    return shortest_distances([location_id], _connection_adjacency(state))


def _merchant_space_ids() -> set[str]:
    """Return every printed merchant space, including those without a tile."""
    return set(MERCHANT_LOCATIONS)


def _merchant_slot(
    state: dict[str, Any], slot_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    for merchant in state["board"]["merchant_locations"]:
        for slot in merchant["slots"]:
            if slot["id"] == slot_id:
                return merchant, slot
    raise RuleError("unknown merchant slot")


def _beer_source_actions(
    state: dict[str, Any], seat: int, pending: dict[str, Any],
) -> list[dict[str, Any]]:
    distances = _connected_distances(state, pending["location_id"])
    actions = []
    for industry in state["board"]["industries"]:
        if industry["industry"] != "brewery" or industry["resources"] <= 0:
            continue
        if industry["owner"] == seat or industry["location"] in distances:
            actions.append({
                "type": "take_resource", "resource": "beer", "source": "industry",
                "source_id": industry["id"], "owner": industry["owner"], "cost": 0,
            })
    _merchant, slot = _merchant_slot(state, pending["merchant_slot_id"])
    if slot["beer"]:
        actions.append({
            "type": "take_resource", "resource": "beer", "source": "merchant",
            "source_id": slot["id"], "cost": 0,
        })
    return actions


def _sell_targets(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    actions = []
    for industry in state["board"]["industries"]:
        if (industry["owner"] != seat or industry.get("flipped")
                or industry["industry"] not in {"cotton_mill", "manufacturer", "pottery"}):
            continue
        distances = _connected_distances(state, industry["location"])
        for merchant in state["board"]["merchant_locations"]:
            if merchant["id"] not in distances:
                continue
            for slot in merchant["slots"]:
                if slot["buys"] not in {"any", industry["industry"]}:
                    continue
                pending = {
                    "industry_id": industry["id"], "location_id": industry["location"],
                    "merchant_location_id": merchant["id"], "merchant_slot_id": slot["id"],
                    "beer_remaining": industry["beer_to_sell"],
                }
                available_beer = slot["beer"] + sum(
                    brewery["resources"] for brewery in state["board"]["industries"]
                    if brewery["industry"] == "brewery" and brewery["resources"] > 0
                    and (brewery["owner"] == seat or brewery["location"] in distances)
                )
                if available_beer >= industry["beer_to_sell"]:
                    actions.append({"type": "sell_industry", **pending})
    return actions


def _resource_source_actions(
    state: dict[str, Any], resource: str, location_id: str, available_money: int,
) -> list[dict[str, Any]]:
    if resource == "coal":
        return _coal_source_actions_for_nodes(state, [location_id], available_money)
    else:
        sources = [
            industry for industry in state["board"]["industries"]
            if industry["industry"] == "iron_works" and industry["resources"] > 0
        ]
        if sources:
            return [{
                "type": "take_resource", "resource": "iron", "source": "industry",
                "source_id": source["id"], "owner": source["owner"], "cost": 0,
            } for source in sources]
    quote = _market_track(state, resource).quote(1)
    if quote.total_price > available_money:
        return []
    return [{
        "type": "take_resource", "resource": resource, "source": "market",
        "source_id": f"{resource}_market", "cost": quote.total_price,
    }]


def _coal_source_actions_for_nodes(
    state: dict[str, Any], nodes: list[str], available_money: int,
    extra_connection_ids: list[str] | tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    distances = shortest_distances(nodes, _connection_adjacency(state, extra_connection_ids))
    sources = [
        industry for industry in state["board"]["industries"]
        if industry["industry"] == "coal_mine" and industry["resources"] > 0
        and industry["location"] in distances
    ]
    if sources:
        nearest = min(distances[source["location"]] for source in sources)
        return [{
            "type": "take_resource", "resource": "coal", "source": "industry",
            "source_id": source["id"], "owner": source["owner"], "cost": 0,
        } for source in sources if distances[source["location"]] == nearest]
    if not _merchant_space_ids().intersection(distances):
        return []
    quote = _market_track(state, "coal").quote(1)
    if quote.total_price > available_money:
        return []
    return [{
        "type": "take_resource", "resource": "coal", "source": "market",
        "source_id": "coal_market", "cost": quote.total_price,
    }]


def _develop_choices(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    player = state["players"][seat]
    available = [industry for industry in INDUSTRY_TYPES
                 if player["industry_stacks"][industry]
                 and player["industry_stacks"][industry][0]["developable"]]
    choices = [(industry,) for industry in available]
    choices.extend(pair for pair in combinations(available, 2))
    choices.extend((industry, industry) for industry in available
                   if len(player["industry_stacks"][industry]) >= 2
                   and player["industry_stacks"][industry][1]["developable"])
    board_iron = sum(
        industry["resources"] for industry in state["board"]["industries"]
        if industry["industry"] == "iron_works" and industry["resources"] > 0
    )
    actions = []
    for industries in choices:
        market_units = max(0, len(industries) - board_iron)
        quote = _market_track(state, "iron").quote(market_units)
        if quote.total_price <= player["money"]:
            actions.append({
                "type": "develop_tiles", "industries": list(industries),
                "estimated_market_cost": quote.total_price,
            })
    return actions


def _build_resources_feasible(
    state: dict[str, Any], tile: dict[str, Any], location_id: str, money: int,
) -> bool:
    distances = _connected_distances(state, location_id)
    connected_coal = sum(
        industry["resources"] for industry in state["board"]["industries"]
        if industry["industry"] == "coal_mine" and industry["location"] in distances
    )
    coal_shortage = max(0, tile["coal_cost"] - connected_coal)
    if coal_shortage and not _merchant_space_ids().intersection(distances):
        return False
    board_iron = sum(
        industry["resources"] for industry in state["board"]["industries"]
        if industry["industry"] == "iron_works"
    )
    iron_shortage = max(0, tile["iron_cost"] - board_iron)
    market_cost = (_market_track(state, "coal").quote(coal_shortage).total_price
                   + _market_track(state, "iron").quote(iron_shortage).total_price)
    return tile["money_cost"] + market_cost <= money


def _build_placements(
    state: dict[str, Any], seat: int, card: dict[str, Any],
) -> list[dict[str, Any]]:
    """List legal card, city-slot, era, network, and affordable placements."""
    player = state["players"][seat]
    network = _player_network_nodes(state, seat)
    board_by_id = {industry["id"]: industry for industry in state["board"]["industries"]}
    owned_locations = {industry["location"] for industry in board_by_id.values()
                       if industry["owner"] == seat}
    actions = []
    for industry in INDUSTRY_TYPES:
        stack = player["industry_stacks"][industry]
        if not stack:
            continue
        tile = stack[0]
        if state["era"] not in tile["allowed_eras"] or tile["money_cost"] > player["money"]:
            continue
        for location in state["board"]["locations"]:
            location_id = location["id"]
            if not _card_allows_build(card, industry, location_id, network):
                continue
            if not _build_resources_feasible(state, tile, location_id, player["money"]):
                continue
            matching = [slot for slot in location["industry_slots"]
                        if industry in slot["accepts"]]
            empty = [slot for slot in matching if slot["industry_id"] is None]
            if state["era"] == "canal" and location_id in owned_locations:
                candidates = [
                    slot for slot in matching
                    if slot["industry_id"] is not None
                    and board_by_id[slot["industry_id"]]["owner"] == seat
                ]
            elif empty:
                single_icon = [slot for slot in empty if len(slot["accepts"]) == 1]
                candidates = single_icon or empty
            else:
                candidates = matching
            for slot in candidates:
                replaced = None
                if slot["industry_id"] is not None:
                    replaced = board_by_id[slot["industry_id"]]
                    opponent_allowed = (
                        replaced["owner"] != seat and industry in {"coal_mine", "iron_works"}
                        and not any(row["industry"] == industry and row["resources"] > 0
                                    for row in board_by_id.values())
                        and not any(state["markets"]["coal" if industry == "coal_mine" else "iron"]["occupied"])
                    )
                    if (replaced["industry"] != industry or tile["level"] <= replaced["level"]
                            or not (replaced["owner"] == seat or opponent_allowed)):
                        continue
                actions.append({
                    "type": "build_industry", "tile_id": tile["id"],
                    "industry": industry, "location_id": location_id,
                    "slot_id": slot["id"], "cost": tile["money_cost"],
                    "overbuild_industry_id": replaced["id"] if replaced else None,
                })
    return actions


def _player_network_nodes(state: dict[str, Any], seat: int) -> set[str]:
    nodes = {industry["location"] for industry in state["board"]["industries"]
             if industry["owner"] == seat}
    connections = {space["id"]: space for space in state["board"]["connection_spaces"]}
    for link in state["board"]["links"]:
        if link["owner"] == seat:
            nodes.update(connections[link["connection_id"]]["endpoints"])
    return nodes


def _network_link_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    pending = state.get("pending_network") or {"links": [], "total_cost": 5}
    selected_ids = {link["connection_id"] for link in pending["links"]}
    built_ids = {link["connection_id"] for link in state["board"]["links"]
                 if link["era"] == state["era"]}
    network = _player_network_nodes(state, seat)
    spaces = {space["id"]: space for space in state["board"]["connection_spaces"]}
    for link in pending["links"]:
        if link.get("coal_consumed"):
            network.update(spaces[link["connection_id"]]["endpoints"])
    no_network = not network
    actions = []
    for connection in state["board"]["connection_spaces"]:
        if (state["era"] not in connection["available_eras"]
                or connection["id"] in built_ids | selected_ids
                or not (no_network or network.intersection(connection["endpoints"]))):
            continue
        if state["era"] == "canal":
            actions.append({
                "type": "build_link", "connection_id": connection["id"],
                "link_kind": "canal", "cost": 3,
            })
            continue
        confirmed = [link["connection_id"] for link in pending["links"]
                     if link.get("coal_consumed")]
        if _coal_source_actions_for_nodes(
            state, connection["endpoints"],
            state["players"][seat]["money"] - pending["total_cost"], confirmed,
        ):
            actions.append({
                "type": "select_network_link", "connection_id": connection["id"],
                "link_kind": "rail",
            })
    if state["era"] != "rail" or pending.get("links_total") != 2:
        return actions
    if len(pending["links"]) == 1:
        viable = []
        for action in actions:
            simulated = deepcopy(state)
            simulated["pending_network"]["links"].append({
                "connection_id": action["connection_id"], "coal_consumed": True,
            })
            if _network_beer_source_actions(
                simulated, seat, simulated["pending_network"],
            ):
                viable.append(action)
        return viable
    return actions


def _double_rail_first_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    simulated = deepcopy(state)
    simulated["pending_network"] = {"links_total": 2, "links": [], "total_cost": 15}
    first_actions = _network_link_actions(simulated, seat)
    viable = []
    for action in first_actions:
        first_sources = _coal_source_actions_for_nodes(
            simulated,
            next(space["endpoints"] for space in simulated["board"]["connection_spaces"]
                 if space["id"] == action["connection_id"]),
            simulated["players"][seat]["money"] - 15,
        )
        if any(_double_first_source_viable(simulated, seat, action, source)
               for source in first_sources):
            viable.append(action)
    return viable


def _double_first_source_viable(
    state: dict[str, Any], seat: int, link_action: dict[str, Any], source_action: dict[str, Any],
) -> bool:
    simulated = deepcopy(state)
    pending = simulated["pending_network"]
    pending["links"].append({
        "connection_id": link_action["connection_id"], "coal_consumed": True,
    })
    if source_action["source"] == "market":
        quote = _market_track(simulated, "coal").consume(1)
        pending["total_cost"] += quote.total_price
    else:
        source = next(industry for industry in simulated["board"]["industries"]
                      if industry["id"] == source_action["source_id"])
        source["resources"] -= 1
    return bool(_network_link_actions(simulated, seat))


def _double_rail_continues_after_first_coal(
    state: dict[str, Any], seat: int, source_action: dict[str, Any],
) -> bool:
    simulated = deepcopy(state)
    pending = simulated["pending_network"]
    if source_action["source"] == "market":
        quote = _market_track(simulated, "coal").consume(1)
        pending["total_cost"] += quote.total_price
    else:
        source = next(industry for industry in simulated["board"]["industries"]
                      if industry["id"] == source_action["source_id"])
        source["resources"] -= 1
    pending["links"][-1]["coal_consumed"] = True
    return bool(_network_link_actions(simulated, seat))


def _network_beer_source_actions(
    state: dict[str, Any], seat: int, pending: dict[str, Any],
) -> list[dict[str, Any]]:
    selected = [link["connection_id"] for link in pending["links"]]
    spaces = {space["id"]: space for space in state["board"]["connection_spaces"]}
    second_link_nodes = spaces[selected[-1]]["endpoints"]
    distances = shortest_distances(second_link_nodes, _connection_adjacency(state, selected))
    return [{
        "type": "take_resource", "resource": "beer", "source": "industry",
        "source_id": industry["id"], "owner": industry["owner"], "cost": 0,
    } for industry in state["board"]["industries"]
        if industry["industry"] == "brewery" and industry["resources"] > 0
        and (industry["owner"] == seat or industry["location"] in distances)]


def _finalize_rail_network(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    seat = state["active_seat"]
    player = state["players"][seat]
    pending = state["pending_network"]
    player["money"] -= pending["total_cost"]
    player["spent_this_round"] += pending["total_cost"]
    for selected in pending["links"]:
        player["links_remaining"] -= 1
        link = {
            "id": f"seat-{seat}-link-{14 - player['links_remaining']:02d}",
            "connection_id": selected["connection_id"], "owner": seat, "era": "rail",
        }
        state["board"]["links"].append(link)
        events.append(domain_event(
            "network_link_built", seat=seat, connection_id=link["connection_id"],
            link_kind="rail", cost=pending["total_cost"] if len(pending["links"]) == 1 else None,
        ))
    _finish_action(state, events)


def _start_turn(state: dict[str, Any], seat: int) -> None:
    nominal = 1 if state["era"] == "canal" and state["round"] == 1 else 2
    total = min(nominal, _hand_size(state["players"][seat]))
    budget = ActionBudget.start(total)
    state["active_seat"] = seat
    state["pending_action"] = None
    state["pending_card"] = None
    state["pending_build"] = None
    state["pending_sell"] = None
    state["pending_network"] = None
    state["pending_develop"] = None
    state["turn"] = {
        "active_seat": seat, "decision": "choose_action", "phase": "choose_action",
        "actions_total": budget.total, "actions_remaining": budget.remaining,
    }
    state["phase"] = "choose_action"


def _hand_size(player: dict[str, Any]) -> int:
    return len(player["hand"]) + sum(player["wild_cards"].values())


def _income_level(position: int) -> int:
    if position <= 10:
        return position - 10
    if position <= 30:
        return (position - 9) // 2
    if position <= 60:
        return 11 + (position - 31) // 3
    if position <= 96:
        return 21 + (position - 61) // 4
    return 30


def _position_after_income_level_drop(position: int, levels: int) -> int:
    target = max(-10, _income_level(position) - levels)
    return max(candidate for candidate in range(100) if _income_level(candidate) == target
               and candidate <= position)


def _discard_card(
    state: dict[str, Any], player: dict[str, Any], action: dict[str, Any],
    events: list[dict[str, Any]],
) -> None:
    if action["type"] == "discard_wild":
        kind = action["wild_type"]
        player["wild_cards"][kind] -= 1
        state["wild_cards"][kind] += 1
        events.append(domain_event("wild_card_returned", seat=player["seat"], wild_type=kind))
        return
    card = next(card for card in player["hand"] if card["id"] == action["card_id"])
    player["hand"].remove(card)
    card["face_up"] = True
    player["discard"].append(card)
    events.append(domain_event("card_discarded", seat=player["seat"], card_id=card["id"]))


def _finish_action(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    completed = state["pending_action"]
    budget = ActionBudget(
        state["turn"]["actions_total"], state["turn"]["actions_remaining"],
    ).spend()
    state["turn"]["actions_remaining"] = budget.remaining
    state["pending_action"] = None
    state["pending_card"] = None
    state["pending_build"] = None
    state["pending_sell"] = None
    state["pending_network"] = None
    state["pending_develop"] = None
    events.append(domain_event("brass_action_completed", seat=state["active_seat"], action=completed))
    if budget.complete or _hand_size(state["players"][state["active_seat"]]) == 0:
        state["turn"]["actions_remaining"] = 0
        _finish_turn(state, events)
    else:
        _set_decision(state, "choose_action")


def _flip_industry(
    state: dict[str, Any], industry: dict[str, Any], events: list[dict[str, Any]],
) -> None:
    if industry.get("flipped"):
        return
    industry["flipped"] = True
    owner = state["players"][industry["owner"]]
    owner["income_position"] = min(99, owner["income_position"] + industry["income_spaces"])
    events.append(domain_event(
        "industry_flipped", seat=industry["owner"], industry_id=industry["id"],
        income_spaces=industry["income_spaces"], income_position=owner["income_position"],
    ))


def _auto_sell_production(
    state: dict[str, Any], industry: dict[str, Any], events: list[dict[str, Any]],
) -> None:
    resource = {"coal_mine": "coal", "iron_works": "iron"}.get(industry["industry"])
    if resource is None or industry["resources"] <= 0:
        return
    if resource == "coal":
        distances = _connected_distances(state, industry["location"])
        if not _merchant_space_ids().intersection(distances):
            return
    quote = _market_track(state, resource).refill(industry["resources"])
    sold = quote.track_units
    if not sold:
        return
    industry["resources"] -= sold
    owner = state["players"][industry["owner"]]
    owner["money"] += quote.total_price
    events.append(domain_event(
        "production_sold_to_market", seat=industry["owner"], industry_id=industry["id"],
        resource=resource, quantity=sold, revenue=quote.total_price,
    ))
    if industry["resources"] == 0:
        _flip_industry(state, industry, events)


def _finalize_build(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    seat = state["active_seat"]
    player = state["players"][seat]
    pending = state["pending_build"]
    stack = player["industry_stacks"][pending["industry"]]
    tile = stack.pop(0)
    if tile["id"] != pending["tile_id"]:
        raise RuleError("industry stack changed before Build resolution")
    player["money"] -= pending["total_cost"]
    player["spent_this_round"] += pending["total_cost"]
    resource = tile["production"][state["era"]]
    replaced_id = pending.get("overbuild_industry_id")
    if replaced_id is not None:
        replaced = next(
            industry for industry in state["board"]["industries"]
            if industry["id"] == replaced_id
        )
        state["board"]["industries"].remove(replaced)
        replaced["state"] = "removed_by_overbuild"
        state["players"][replaced["owner"]]["removed_industries"].append(replaced)
        events.append(domain_event(
            "industry_overbuilt", seat=seat, replaced_industry_id=replaced_id,
            replaced_owner=replaced["owner"],
        ))
    industry = deepcopy(tile)
    industry.update({
        "id": f"seat-{seat}-{tile['id']}", "tile_id": tile["id"],
        "owner": seat, "location": pending["location_id"],
        "slot_id": pending["slot_id"], "state": "board",
        "resources": resource, "flipped": False,
    })
    state["board"]["industries"].append(industry)
    slot = next(
        slot for slot in _location(state, pending["location_id"])["industry_slots"]
        if slot["id"] == pending["slot_id"]
    )
    slot["industry_id"] = industry["id"]
    events.append(domain_event(
        "industry_built", seat=seat, tile_id=tile["id"], industry_id=industry["id"],
        industry=tile["industry"], location_id=pending["location_id"],
        slot_id=pending["slot_id"], cost=pending["total_cost"], resources=resource,
    ))
    _auto_sell_production(state, industry, events)
    _finish_action(state, events)


def _advance_build_resolution(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    pending = state["pending_build"]
    if pending["coal_remaining"]:
        _set_decision(state, "build_choose_coal_source")
    elif pending["iron_remaining"]:
        _set_decision(state, "build_choose_iron_source")
    else:
        _finalize_build(state, events)


def _finish_sale(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    pending = state["pending_sell"]
    industry = next(
        industry for industry in state["board"]["industries"]
        if industry["id"] == pending["industry_id"]
    )
    _flip_industry(state, industry, events)
    events.append(domain_event(
        "industry_sold", seat=state["active_seat"], industry_id=industry["id"],
        merchant_location_id=pending["merchant_location_id"],
        merchant_slot_id=pending["merchant_slot_id"],
    ))
    state["pending_sell"] = None
    _set_decision(state, "sell_continue")


def _advance_sell_resolution(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    if state["pending_sell"]["beer_remaining"]:
        _set_decision(state, "sell_choose_beer_source")
    else:
        _finish_sale(state, events)


def _apply_merchant_bonus(
    state: dict[str, Any], merchant: dict[str, Any], events: list[dict[str, Any]],
) -> bool:
    player = state["players"][state["active_seat"]]
    bonus = merchant["bonus"]
    if bonus["type"] == "money":
        player["money"] += bonus["amount"]
    elif bonus["type"] == "vp":
        player["vp"] += bonus["amount"]
    elif bonus["type"] == "income_spaces":
        player["income_position"] = min(99, player["income_position"] + bonus["amount"])
    elif bonus["type"] == "develop":
        choices = [industry for industry in INDUSTRY_TYPES
                   if player["industry_stacks"][industry]
                   and player["industry_stacks"][industry][0]["developable"]]
        if not choices:
            events.append(domain_event(
                "merchant_bonus_skipped", seat=player["seat"], merchant=merchant["id"],
                bonus="develop", reason="no_developable_industry",
            ))
            return False
        _set_decision(state, "sell_choose_merchant_develop")
        events.append(domain_event(
            "merchant_bonus_pending", seat=player["seat"], merchant=merchant["id"],
            bonus="develop",
        ))
        return True
    events.append(domain_event(
        "merchant_bonus_resolved", seat=player["seat"], merchant=merchant["id"],
        bonus=bonus["type"], amount=bonus["amount"],
    ))
    return False


def _finish_turn(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    seat = state["active_seat"]
    player = state["players"][seat]
    while _hand_size(player) < 8 and state["draw_deck"]:
        player["hand"].append(state["draw_deck"].pop())
    state["turn_count"] += 1
    position = state["turn_order"].index(seat)
    for next_seat in state["turn_order"][position + 1:]:
        if _hand_size(state["players"][next_seat]) > 0:
            _start_turn(state, next_seat)
            return

    previous = list(state["turn_order"])
    metrics = {row["seat"]: row["spent_this_round"] for row in state["players"]}
    state["turn_order"] = stable_metric_order(previous, metrics)
    for row in state["players"]:
        row["spent_this_round"] = 0
    events.append(domain_event(
        "round_order_determined", order=list(state["turn_order"]), metric="money_spent",
    ))
    final_round = not state["draw_deck"] and all(_hand_size(row) == 0 for row in state["players"])
    state["pending_round_transition"] = {
        "final_round": final_round, "income_seats": list(state["turn_order"]),
        "income_index": 0,
    }
    if final_round and state["era"] == "rail":
        _complete_round_transition(state, events)
    else:
        _resume_income_resolution(state, events)


def _complete_round_transition(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    transition = state["pending_round_transition"]
    state["pending_round_transition"] = None
    state["pending_income"] = None
    if transition["final_round"]:
        _finish_era(state, events)
        return
    state["round"] += 1
    next_seat = next(
        candidate for candidate in state["turn_order"]
        if _hand_size(state["players"][candidate]) > 0
    )
    _start_turn(state, next_seat)


def _resume_income_resolution(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    transition = state["pending_round_transition"]
    while transition["income_index"] < len(transition["income_seats"]):
        seat = transition["income_seats"][transition["income_index"]]
        player = state["players"][seat]
        income = _income_level(player["income_position"])
        if income >= 0:
            player["money"] += income
            events.append(domain_event("income_collected", seat=player["seat"], amount=income))
            transition["income_index"] += 1
            continue
        owed = -income
        if player["money"] >= owed:
            player["money"] -= owed
            events.append(domain_event("income_paid", seat=seat, amount=owed))
            transition["income_index"] += 1
            continue
        industries = [industry for industry in state["board"]["industries"]
                      if industry["owner"] == seat]
        if industries:
            state["pending_income"] = {"seat": seat, "owed": owed}
            state["active_seat"] = seat
            state["turn"]["active_seat"] = seat
            _set_decision(state, "income_choose_liquidation")
            events.append(domain_event(
                "income_liquidation_required", seat=seat, owed=owed,
                available_money=player["money"],
            ))
            return
        shortfall = owed - player["money"]
        paid = player["money"]
        player["money"] = 0
        lost = min(player["vp"], shortfall)
        player["vp"] -= lost
        events.append(domain_event(
            "income_shortfall", seat=seat, amount=shortfall, vp_lost=lost,
            liquidation_status="no_industries_remaining",
        ))
        events.append(domain_event("income_paid", seat=seat, amount=paid))
        transition["income_index"] += 1
    _complete_round_transition(state, events)


def _score_era(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    spaces = {space["id"]: space for space in state["board"]["connection_spaces"]}
    merchant_spaces = _merchant_space_ids()

    def link_value(link: dict[str, Any]) -> int:
        endpoints = spaces[link["connection_id"]]["endpoints"]
        value = 2 * sum(endpoint in merchant_spaces for endpoint in endpoints)
        value += sum(
            industry["link_icons"] for industry in state["board"]["industries"]
            if industry["location"] in endpoints
        )
        return value

    for player in state["players"]:
        industry_points = sum(
            industry.get("vp", 0) for industry in state["board"]["industries"]
            if industry["owner"] == player["seat"] and industry.get("flipped", False)
        )
        link_points = sum(
            link_value(link) for link in state["board"]["links"]
            if link["owner"] == player["seat"] and link["era"] == state["era"]
        )
        player["vp"] += industry_points + link_points
        events.append(domain_event(
            "era_scored", seat=player["seat"], era=state["era"],
            industry_points=industry_points, link_points=link_points,
        ))


def _finish_era(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    _score_era(state, events)
    era = state["era"]
    events.append(domain_event("era_finished", era=era, round=state["round"]))
    if era == "rail":
        state["status"] = "finished"
        state["phase"] = "finished"
        state["pending_action"] = None
        state["turn"]["phase"] = "finished"
        state["turn"]["decision"] = "finished"
        events.append(domain_event("match_finished", rankings=rankings(state)))
        return

    for player in state["players"]:
        returned = sum(1 for link in state["board"]["links"]
                       if link["owner"] == player["seat"] and link["era"] == "canal")
        player["links_remaining"] += returned
    state["board"]["links"] = [link for link in state["board"]["links"] if link["era"] != "canal"]
    level_one = [
        industry for industry in state["board"]["industries"] if industry.get("level") == 1
    ]
    removed_ids = {industry["id"] for industry in level_one}
    for industry in level_one:
        removed = deepcopy(industry)
        removed["state"] = "removed_end_canal"
        state["players"][industry["owner"]]["removed_industries"].append(removed)
    state["board"]["industries"] = [
        industry for industry in state["board"]["industries"] if industry["id"] not in removed_ids
    ]
    for location in state["board"]["locations"]:
        for slot in location["industry_slots"]:
            if slot["industry_id"] in removed_ids:
                slot["industry_id"] = None
    for merchant in state["board"]["merchant_locations"]:
        for slot in merchant["slots"]:
            slot["beer"] = 0 if slot["buys"] == "blank" else 1

    cards = []
    for player in state["players"]:
        for card in player["discard"]:
            card.pop("face_up", None)
            cards.append(card)
        player["discard"] = []
    rng = random.Random(state["seed"] + 104729 * state["shuffle_count"])
    rng.shuffle(cards)
    state["shuffle_count"] += 1
    state["draw_deck"] = cards
    for player in state["players"]:
        while len(player["hand"]) < 8:
            player["hand"].append(state["draw_deck"].pop())
    state["era"] = "rail"
    state["round"] = 1
    events.append(domain_event("era_started", era="rail"))
    _start_turn(state, state["turn_order"][0])


def apply_action(
    state: dict[str, Any], seat: int, action: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    canonical = _action_space(
        state, [item["action"] for item in legal_actions(state, seat)],
    ).require(action, error_factory=RuleError, message="action is not legal in the current decision step")
    next_state = deepcopy(state)
    player = next_state["players"][seat]
    next_state["decision_count"] += 1
    events = [action_accepted(seat, canonical, decision=state["phase"])]
    if state["phase"] == "choose_action":
        next_state["pending_action"] = canonical["action"]
        _set_decision(next_state, "choose_discard_card")
        events.append(domain_event(
            "brass_action_selected", seat=seat, action=canonical["action"],
        ))
    elif state["phase"] == "choose_discard_card":
        if canonical["type"] == "discard_wild":
            next_state["pending_card"] = {"card_type": f"wild_{canonical['wild_type']}"}
        else:
            next_state["pending_card"] = deepcopy(next(
                card for card in player["hand"] if card["id"] == canonical["card_id"]
            ))
        _discard_card(next_state, player, canonical, events)
        pending = next_state["pending_action"]
        if pending == "loan":
            player["money"] += 30
            player["income_position"] = _position_after_income_level_drop(
                player["income_position"], 3,
            )
            events.append(domain_event(
                "loan_taken", seat=seat, amount=30, income_position=player["income_position"],
                income_level=_income_level(player["income_position"]),
            ))
            _finish_action(next_state, events)
        elif pending == "scout":
            _set_decision(next_state, "scout_choose_extra_cards")
        elif pending == "develop":
            _set_decision(next_state, "develop_choose_tiles")
        elif pending == "network":
            _set_decision(next_state, "network_choose_link" if next_state["era"] == "canal"
                          else "network_choose_mode")
        elif pending == "build":
            _set_decision(next_state, "build_choose_placement")
        elif pending == "sell":
            _set_decision(next_state, "sell_choose_industry")
        else:
            events.append(domain_event("brass_action_passed", seat=seat))
            _finish_action(next_state, events)
    elif state["phase"] == "scout_choose_extra_cards":
        for card_id in canonical["card_ids"]:
            _discard_card(next_state, player, {"type": "discard_card", "card_id": card_id}, events)
        for kind in ("location", "industry"):
            next_state["wild_cards"][kind] -= 1
            player["wild_cards"][kind] += 1
        events.append(domain_event("wild_cards_scouted", seat=seat, location=1, industry=1))
        _finish_action(next_state, events)
    elif state["phase"] == "develop_choose_tiles":
        next_state["pending_develop"] = {
            "industries": list(canonical["industries"]), "total_cost": 0,
            "removed_tile_ids": [],
        }
        events.append(domain_event(
            "develop_tiles_selected", seat=seat, industries=list(canonical["industries"]),
        ))
        _set_decision(next_state, "develop_choose_iron_source")
    elif state["phase"] == "develop_choose_iron_source":
        pending = next_state["pending_develop"]
        if canonical["source"] == "market":
            quote = _market_track(next_state, "iron").consume(1)
            if quote.total_price != canonical["cost"]:
                raise RuleError("iron market quote changed")
            pending["total_cost"] += quote.total_price
        else:
            source = next(
                industry for industry in next_state["board"]["industries"]
                if industry["id"] == canonical["source_id"]
            )
            source["resources"] -= 1
            if source["resources"] == 0:
                _flip_industry(next_state, source, events)
        industry = pending["industries"].pop(0)
        tile = player["industry_stacks"][industry].pop(0)
        tile["state"] = "removed_by_develop"
        player["removed_industries"].append(tile)
        pending["removed_tile_ids"].append(tile["id"])
        events.append(domain_event(
            "develop_iron_consumed", seat=seat, tile_id=tile["id"],
            source=canonical["source"], source_id=canonical["source_id"],
            cost=canonical["cost"],
        ))
        if pending["industries"]:
            _set_decision(next_state, "develop_choose_iron_source")
        else:
            player["money"] -= pending["total_cost"]
            player["spent_this_round"] += pending["total_cost"]
            events.append(domain_event(
                "industries_developed", seat=seat,
                tile_ids=list(pending["removed_tile_ids"]),
                iron=len(pending["removed_tile_ids"]), cost=pending["total_cost"],
            ))
            _finish_action(next_state, events)
    elif state["phase"] == "network_choose_link":
        if next_state["era"] == "canal":
            player["money"] -= canonical["cost"]
            player["spent_this_round"] += canonical["cost"]
            player["links_remaining"] -= 1
            link = {
                "id": f"seat-{seat}-link-{14 - player['links_remaining']:02d}",
                "connection_id": canonical["connection_id"], "owner": seat,
                "era": canonical["link_kind"],
            }
            next_state["board"]["links"].append(link)
            events.append(domain_event(
                "network_link_built", seat=seat, connection_id=link["connection_id"],
                link_kind=link["era"], cost=canonical["cost"],
            ))
            _finish_action(next_state, events)
        else:
            next_state["pending_network"]["links"].append({
                "connection_id": canonical["connection_id"], "coal_consumed": False,
            })
            events.append(domain_event(
                "rail_link_selected", seat=seat, connection_id=canonical["connection_id"],
            ))
            _set_decision(next_state, "network_choose_coal_source")
    elif state["phase"] == "network_choose_mode":
        next_state["pending_network"] = {
            "links_total": canonical["count"], "links": [], "total_cost": canonical["cost"],
        }
        events.append(domain_event(
            "rail_network_count_selected", seat=seat, count=canonical["count"],
            cost=canonical["cost"],
        ))
        _set_decision(next_state, "network_choose_link")
    elif state["phase"] == "network_choose_coal_source":
        pending = next_state["pending_network"]
        if canonical["source"] == "market":
            quote = _market_track(next_state, "coal").consume(1)
            if quote.total_price != canonical["cost"]:
                raise RuleError("coal market quote changed")
            pending["total_cost"] += quote.total_price
        else:
            source = next(
                industry for industry in next_state["board"]["industries"]
                if industry["id"] == canonical["source_id"]
            )
            source["resources"] -= 1
            if source["resources"] == 0:
                _flip_industry(next_state, source, events)
        pending["links"][-1]["coal_consumed"] = True
        events.append(domain_event(
            "rail_coal_consumed", seat=seat, source=canonical["source"],
            source_id=canonical["source_id"], cost=canonical["cost"],
        ))
        if len(pending["links"]) < pending["links_total"]:
            _set_decision(next_state, "network_choose_link")
        elif pending["links_total"] == 2:
            _set_decision(next_state, "network_choose_beer_source")
        else:
            _finalize_rail_network(next_state, events)
    elif state["phase"] == "network_choose_beer_source":
        source = next(
            industry for industry in next_state["board"]["industries"]
            if industry["id"] == canonical["source_id"]
        )
        source["resources"] -= 1
        if source["resources"] == 0:
            _flip_industry(next_state, source, events)
        events.append(domain_event(
            "rail_beer_consumed", seat=seat, source_id=source["id"], owner=source["owner"],
        ))
        _finalize_rail_network(next_state, events)
    elif state["phase"] == "build_choose_placement":
        tile = player["industry_stacks"][canonical["industry"]][0]
        next_state["pending_build"] = {
            **deepcopy(canonical), "coal_remaining": tile["coal_cost"],
            "iron_remaining": tile["iron_cost"], "total_cost": tile["money_cost"],
        }
        events.append(domain_event(
            "build_placement_selected", seat=seat, tile_id=tile["id"],
            location_id=canonical["location_id"], slot_id=canonical["slot_id"],
        ))
        _advance_build_resolution(next_state, events)
    elif state["phase"] in {"build_choose_coal_source", "build_choose_iron_source"}:
        pending = next_state["pending_build"]
        resource = canonical["resource"]
        if canonical["source"] == "market":
            quote = _market_track(next_state, resource).consume(1)
            if quote.total_price != canonical["cost"]:
                raise RuleError(f"{resource} market quote changed")
            pending["total_cost"] += quote.total_price
        else:
            source = next(
                industry for industry in next_state["board"]["industries"]
                if industry["id"] == canonical["source_id"]
            )
            source["resources"] -= 1
            if source["resources"] == 0:
                _flip_industry(next_state, source, events)
        pending[f"{resource}_remaining"] -= 1
        events.append(domain_event(
            "build_resource_consumed", seat=seat, resource=resource,
            source=canonical["source"], source_id=canonical["source_id"],
            cost=canonical["cost"],
        ))
        _advance_build_resolution(next_state, events)
    elif state["phase"] in {"sell_choose_industry", "sell_continue"}:
        if canonical["type"] == "finish_sell":
            _finish_action(next_state, events)
        else:
            next_state["pending_sell"] = deepcopy(canonical)
            events.append(domain_event(
                "sale_selected", seat=seat, industry_id=canonical["industry_id"],
                merchant_slot_id=canonical["merchant_slot_id"],
            ))
            _advance_sell_resolution(next_state, events)
    elif state["phase"] == "sell_choose_beer_source":
        pending = next_state["pending_sell"]
        bonus_pending = False
        if canonical["source"] == "industry":
            source = next(
                industry for industry in next_state["board"]["industries"]
                if industry["id"] == canonical["source_id"]
            )
            source["resources"] -= 1
            if source["resources"] == 0:
                _flip_industry(next_state, source, events)
        else:
            merchant, slot = _merchant_slot(next_state, canonical["source_id"])
            slot["beer"] -= 1
            bonus_pending = _apply_merchant_bonus(next_state, merchant, events)
        pending["beer_remaining"] -= 1
        events.append(domain_event(
            "sale_beer_consumed", seat=seat, source=canonical["source"],
            source_id=canonical["source_id"],
        ))
        if not bonus_pending:
            _advance_sell_resolution(next_state, events)
    elif state["phase"] == "sell_choose_merchant_develop":
        tile = player["industry_stacks"][canonical["industry"]].pop(0)
        tile["state"] = "removed_by_merchant_bonus"
        player["removed_industries"].append(tile)
        events.append(domain_event(
            "merchant_bonus_developed", seat=seat, tile_id=tile["id"],
        ))
        _advance_sell_resolution(next_state, events)
    elif state["phase"] == "income_choose_liquidation":
        pending = next_state["pending_income"]
        industry = next(
            row for row in next_state["board"]["industries"]
            if row["id"] == canonical["industry_id"] and row["owner"] == seat
        )
        next_state["board"]["industries"].remove(industry)
        slot = next(
            slot for slot in _location(next_state, industry["location"])["industry_slots"]
            if slot["id"] == industry["slot_id"]
        )
        slot["industry_id"] = None
        industry["state"] = "removed_for_income"
        player["removed_industries"].append(industry)
        player["money"] += canonical["value"]
        events.append(domain_event(
            "industry_liquidated", seat=seat, industry_id=industry["id"],
            value=canonical["value"], owed=pending["owed"],
        ))
        remaining_industries = [row for row in next_state["board"]["industries"]
                                if row["owner"] == seat]
        if player["money"] >= pending["owed"]:
            player["money"] -= pending["owed"]
            events.append(domain_event("income_paid", seat=seat, amount=pending["owed"]))
        elif remaining_industries:
            _set_decision(next_state, "income_choose_liquidation")
            validate_state(next_state)
            return next_state, events
        else:
            shortfall = pending["owed"] - player["money"]
            paid = player["money"]
            player["money"] = 0
            lost = min(player["vp"], shortfall)
            player["vp"] -= lost
            events.append(domain_event(
                "income_shortfall", seat=seat, amount=shortfall, vp_lost=lost,
                liquidation_status="all_industries_liquidated",
            ))
            events.append(domain_event("income_paid", seat=seat, amount=paid))
        next_state["pending_income"] = None
        next_state["pending_round_transition"]["income_index"] += 1
        _resume_income_resolution(next_state, events)
    validate_state(next_state)
    return next_state, events


def rankings(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [{
        "seat": player["seat"], "vp": player["vp"],
        "income_position": player["income_position"],
        "income_level": _income_level(player["income_position"]),
        "money": player["money"], "rank": None,
    } for player in state["players"]]
    return assign_competition_ranks(
        rows,
        sort_key=lambda row: (-row["vp"], -row["income_level"], -row["money"], row["seat"]),
        tie_key=lambda row: (row["vp"], row["income_level"], row["money"]),
    )


def observe(state: dict[str, Any], seat: int) -> dict[str, Any]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    players = []
    for player in state["players"]:
        row = deepcopy(player)
        row["hand_count"] = len(player["hand"])
        row["hand"] = private_items(player["hand"], player["seat"] == seat)
        row["discard"] = [deepcopy(card) if card.get("face_up", True) else {
            "hidden": True, "face_up": False,
        } for card in player["discard"]]
        players.append(row)
    return {
        "game": "brass_birmingham", "rules_version": state["rules_version"],
        "implementation_status": state["implementation_status"], "viewer_seat": seat,
        "status": state["status"], "phase": state["phase"], "era": state["era"],
        "round": state["round"], "turn_count": state["turn_count"],
        "decision_count": state["decision_count"], "active_seat": state["active_seat"],
        "turn_order": list(state["turn_order"]), "turn": deepcopy(state["turn"]),
        "deck_count": len(state["draw_deck"]), "wild_cards": deepcopy(state["wild_cards"]),
        "markets": deepcopy(state["markets"]), "board": deepcopy(state["board"]),
        "players": players, "rankings": rankings(state) if state["status"] == "finished" else None,
    }


def validate_state(state: dict[str, Any]) -> None:
    if state.get("schema_version") != "agentbga.brass_birmingham.state.v1":
        raise AssertionError("invalid Brass: Birmingham state schema")
    players = state.get("players", [])
    if state.get("player_count") not in (2, 3, 4) or len(players) != state["player_count"]:
        raise AssertionError("invalid Brass: Birmingham player count")
    seats = list(range(state["player_count"]))
    if sorted(state["turn_order"]) != seats or state["active_seat"] not in seats:
        raise AssertionError("invalid Brass: Birmingham turn order")
    if state["turn"]["active_seat"] != state["active_seat"]:
        raise AssertionError("turn active seat does not match state")
    ActionBudget(state["turn"]["actions_total"], state["turn"]["actions_remaining"])
    valid_phases = {
        "choose_action", "choose_discard_card", "scout_choose_extra_cards",
        "develop_choose_tiles", "develop_choose_iron_source", "build_choose_placement",
        "build_choose_coal_source", "build_choose_iron_source",
        "sell_choose_industry", "sell_choose_beer_source", "sell_continue",
        "sell_choose_merchant_develop",
        "network_choose_link", "network_choose_mode", "network_choose_coal_source",
        "network_choose_beer_source",
        "income_choose_liquidation",
    }
    if state["status"] == "finished":
        valid_phases.add("finished")
    if state["era"] not in {"canal", "rail"} or state["phase"] not in valid_phases:
        raise AssertionError("invalid Brass: Birmingham era")
    if state["round_limit"] != ROUNDS_PER_ERA[state["player_count"]] or state["round"] < 1:
        raise AssertionError("invalid Brass: Birmingham round")
    if len(state["board"]["merchant_locations"]) != {2: 3, 3: 4, 4: 5}[state["player_count"]]:
        raise AssertionError("invalid Brass: Birmingham merchant setup")
    merchant_slots = [
        slot for merchant in state["board"]["merchant_locations"] for slot in merchant["slots"]
    ]
    if len(merchant_slots) != {2: 5, 3: 7, 4: 9}[state["player_count"]]:
        raise AssertionError("invalid Brass: Birmingham merchant slot count")
    if sum(slot["buys"] == "blank" for slot in merchant_slots) != 2:
        raise AssertionError("invalid Brass: Birmingham blank merchant tiles")
    if any(slot["beer"] not in (0, 1) or (slot["buys"] == "blank" and slot["beer"])
           for slot in merchant_slots):
        raise AssertionError("invalid Brass: Birmingham merchant beer")
    spaces = state["board"]["connection_spaces"]
    if len(spaces) != len(CONNECTION_ENDPOINTS) or len({space["id"] for space in spaces}) != len(spaces):
        raise AssertionError("invalid Brass: Birmingham connection spaces")
    valid_connections = {space["id"] for space in spaces}
    if any(link["connection_id"] not in valid_connections for link in state["board"]["links"]):
        raise AssertionError("Brass: Birmingham link uses an unknown connection")
    if len({(link["connection_id"], link["era"]) for link in state["board"]["links"]}) != len(
        state["board"]["links"]
    ):
        raise AssertionError("Brass: Birmingham connection is occupied twice in one era")
    for resource, capacity in (("coal", 14), ("iron", 10)):
        market = state["markets"][resource]
        if len(market["occupied"]) != capacity or any(
            not isinstance(occupied, bool) for occupied in market["occupied"]
        ):
            raise AssertionError(f"invalid Brass: Birmingham {resource} market")
    board_ids = {industry["id"] for industry in state["board"]["industries"]}
    slot_ids = {
        slot["industry_id"] for location in state["board"]["locations"]
        for slot in location["industry_slots"] if slot["industry_id"] is not None
    }
    if board_ids != slot_ids:
        raise AssertionError("Brass: Birmingham board industries and slots disagree")
    for industry in state["board"]["industries"]:
        slot = next(
            slot for slot in _location(state, industry["location"])["industry_slots"]
            if slot["id"] == industry["slot_id"]
        )
        if slot["industry_id"] != industry["id"] or industry["industry"] not in slot["accepts"]:
            raise AssertionError("Brass: Birmingham industry occupies an invalid slot")
    for player in players:
        if player["seat"] not in seats or player["money"] < 0 or player["vp"] < 0:
            raise AssertionError("invalid Brass: Birmingham player resources")
        if not 0 <= player["income_position"] <= 99:
            raise AssertionError("invalid Brass: Birmingham income position")
        if player["spent_this_round"] < 0 or player["links_remaining"] < 0:
            raise AssertionError("invalid Brass: Birmingham player pieces")
        if set(player["wild_cards"]) != {"location", "industry"} or any(
            count not in (0, 1) for count in player["wild_cards"].values()
        ):
            raise AssertionError("invalid Brass: Birmingham wild cards")
        if set(player["industry_stacks"]) != set(INDUSTRY_TYPES):
            raise AssertionError("invalid Brass: Birmingham industry stacks")
        remaining = {industry: len(stack) for industry, stack in player["industry_stacks"].items()}
        removed = {industry: 0 for industry in INDUSTRY_TYPES}
        for tile in player["removed_industries"]:
            removed[tile["industry"]] += 1
        built = {industry: sum(
            board_tile["owner"] == player["seat"] and board_tile["industry"] == industry
            for board_tile in state["board"]["industries"]
        ) for industry in INDUSTRY_TYPES}
        if {industry: remaining[industry] + removed[industry] + built[industry]
            for industry in INDUSTRY_TYPES} != INDUSTRY_TILE_COUNTS:
            raise AssertionError("invalid Brass: Birmingham industry tile counts")
    zones = [state["draw_deck"]]
    zones.extend(player[zone] for player in players for zone in ("hand", "discard"))
    expected = len(_card_deck(state["player_count"]))
    validate_unique_items(zones, expected_count=expected)
    for kind in ("location", "industry"):
        if state["wild_cards"][kind] + sum(
            player["wild_cards"][kind] for player in players
        ) != 4:
            raise AssertionError("Brass: Birmingham wild cards are not conserved")
