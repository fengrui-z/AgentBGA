"""Deterministic CATAN base-game engine, with the flexible trade/build variant.

All random choices are in trusted state and replay from accepted actions. The
public observation contains neither the seed, future deck order, nor other
players' hands. Trade bundles and discards are entered as small staged choices.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import math
import random
from typing import Any

from .game import GameRuleError
from .mechanics import ActionSpace, action_accepted, assign_competition_ranks, state_digest

RULES_VERSION = "catan-2020-base-flexible-1.0"
SCHEMA_VERSION = "agentbga.catan.state.v1"
RESOURCES = ("brick", "lumber", "wool", "grain", "ore")
RESOURCE_COUNTS = {"brick": 3, "lumber": 4, "wool": 4, "grain": 4, "ore": 3}
NUMBER_TOKENS = (2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12)
COSTS = {
    "road": {"brick": 1, "lumber": 1},
    "settlement": {"brick": 1, "lumber": 1, "wool": 1, "grain": 1},
    "city": {"grain": 2, "ore": 3},
    "development_card": {"wool": 1, "grain": 1, "ore": 1},
}
DEVELOPMENT_COUNTS = {"knight": 14, "victory_point": 5, "road_building": 2,
                      "year_of_plenty": 2, "monopoly": 2}
DEVELOPMENT_CARDS = {
    f"{kind}-{number:02d}": kind
    for kind, count in DEVELOPMENT_COUNTS.items() for number in range(1, count + 1)
}
PHASES = {"setup_settlement", "setup_road", "roll", "main", "discard", "robber",
          "steal", "free_roads", "year_of_plenty", "trade_give", "trade_receive",
          "trade_response", "finished"}
ACTION_TYPES = ["place_settlement", "place_road", "roll_dice", "build_road",
                "build_settlement", "build_city", "buy_development_card", "play_knight",
                "play_road_building", "play_year_of_plenty", "play_monopoly",
                "maritime_trade", "end_turn", "discard", "move_robber", "steal",
                "free_road", "finish_road_building", "take_resource", "propose_trade",
                "trade_amount", "cancel_trade", "respond_trade", "counter_trade"]


class RuleError(GameRuleError):
    """A stable, user-correctable rule rejection."""


def describe() -> dict[str, Any]:
    return {
        "id": "catan", "name": "CATAN", "rules_version": RULES_VERSION,
        "players": {"minimum": 3, "maximum": 4}, "hidden_information": True,
        "implementation_status": "playable_beta", "runnable": True,
        "decision_model": "staged_structured_decisions", "default_max_turns": 3000,
        "action_types": list(ACTION_TYPES), "resources": list(RESOURCES),
        "rules_sources": [
            "https://www.catan.com/sites/default/files/2021-06/catan_base_rules_2020_200707.pdf",
            "https://www.catan.com/faq/basegame",
        ],
        "content_scope": (
            "Three or four player base game, random island with separated 6/8 tokens, "
            "snake placement, finite resources, robber, development cards, roads and awards. "
            "Uses the official flexible trade/build turn variant. Domestic trades use "
            "bilateral offers, counteroffers, and accept/reject decisions. "
            "No expansions, free-form negotiation, or publisher artwork."
        ),
        "win_condition": "Reach ten victory points during your own turn; victory is immediate.",
    }


def _empty_resources() -> dict[str, int]:
    return dict.fromkeys(RESOURCES, 0)


def _make_board(rng: random.Random) -> dict[str, Any]:
    # Integer corner coordinates prevent rounding from merging distinct vertices.
    corners = ((1, 1), (0, 2), (-1, 1), (-1, -1), (0, -2), (1, -1))
    hexes: list[dict[str, Any]] = []
    vertices: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    by_xy: dict[tuple[int, int], int] = {}
    by_ends: dict[tuple[int, int], int] = {}
    for r in range(-2, 3):
        for q in range(-2, 3):
            if abs(q + r) > 2:
                continue
            hx, hy = 2 * q + r, 3 * r
            tile = {"id": len(hexes), "q": q, "r": r,
                    "x": hx * math.sqrt(3) / 2, "y": hy / 2,
                    "vertices": [], "edges": []}
            for dx, dy in corners:
                key = (hx + dx, hy + dy)
                if key not in by_xy:
                    vid = len(vertices)
                    by_xy[key] = vid
                    vertices.append({"id": vid, "x": key[0] * math.sqrt(3) / 2,
                                     "y": key[1] / 2, "hexes": [], "edges": [],
                                     "building": None, "port": None})
                vid = by_xy[key]
                vertices[vid]["hexes"].append(tile["id"])
                tile["vertices"].append(vid)
            for i in range(6):
                ends = tuple(sorted((tile["vertices"][i], tile["vertices"][(i + 1) % 6])))
                if ends not in by_ends:
                    eid = len(edges)
                    by_ends[ends] = eid
                    edges.append({"id": eid, "vertices": list(ends), "owner": None})
                    for vid in ends:
                        vertices[vid]["edges"].append(eid)
                tile["edges"].append(by_ends[ends])
            hexes.append(tile)
    terrains = [resource for resource, count in RESOURCE_COUNTS.items() for _ in range(count)] + ["desert"]
    rng.shuffle(terrains)
    for tile, terrain in zip(hexes, terrains, strict=True):
        tile["terrain"] = terrain
        tile["number"] = None
    fertile = [tile for tile in hexes if tile["terrain"] != "desert"]
    numbers = list(NUMBER_TOKENS)
    while True:
        rng.shuffle(numbers)
        for tile, number in zip(fertile, numbers, strict=True):
            tile["number"] = number
        red_edges: set[int] = set()
        valid = True
        for tile in fertile:
            if tile["number"] in (6, 8):
                if red_edges.intersection(tile["edges"]):
                    valid = False
                    break
                red_edges.update(tile["edges"])
        if valid:
            break
    edge_use = Counter(eid for tile in hexes for eid in tile["edges"])
    boundary = [edge for edge in edges if edge_use[edge["id"]] == 1]
    boundary.sort(key=lambda edge: math.atan2(
        sum(vertices[v]["y"] for v in edge["vertices"]),
        sum(vertices[v]["x"] for v in edge["vertices"])))
    port_types = ["any"] * 4 + list(RESOURCES)
    rng.shuffle(port_types)
    ports = []
    for i, boundary_index in enumerate((0, 3, 6, 10, 13, 16, 20, 23, 26)):
        ends = boundary[boundary_index]["vertices"]
        resource = port_types[i]
        ports.append({"id": i, "vertices": list(ends), "resource": resource})
        for vid in ends:
            vertices[vid]["port"] = resource
    return {"hexes": hexes, "vertices": vertices, "edges": edges, "ports": ports}


def new_game(players: int, seed: int, config: dict[str, Any] | None = None) -> dict[str, Any]:
    if config not in (None, {}):
        raise RuleError("CATAN does not accept game setup options")
    if type(players) is not int or players not in (3, 4):
        raise RuleError("CATAN requires 3 or 4 players")
    if type(seed) is not int:
        raise RuleError("seed must be an integer")
    rng = random.Random(seed)
    board = _make_board(rng)
    deck = list(DEVELOPMENT_CARDS)
    rng.shuffle(deck)
    state = {
        "schema_version": SCHEMA_VERSION, "rules_version": RULES_VERSION,
        "seed": seed, "rng_counter": 0, "player_count": players,
        "turn_count": 0, "decision_count": 0, "active_seat": 0, "turn_seat": 0,
        "phase": "setup_settlement", "status": "active", "winner": None,
        "board": board, "bank": {resource: 19 for resource in RESOURCES},
        "robber_hex": next(tile["id"] for tile in board["hexes"] if tile["terrain"] == "desert"),
        "last_roll": None, "setup_order": list(range(players)) + list(reversed(range(players))),
        "setup_index": 0, "setup_vertex": None,
        "development_deck": deck, "development_discard": [], "development_played": False,
        "effect_return_phase": None, "free_roads_remaining": 0, "year_of_plenty_remaining": 0,
        "discard_remaining": [0] * players, "trade": None,
        "longest_road_seat": None, "largest_army_seat": None,
        "players": [{"seat": seat, "resources": _empty_resources(),
                     "development_cards": [], "played_knights": 0} for seat in range(players)],
    }
    validate_state(state)
    return state


def state_hash(state: dict[str, Any]) -> str:
    return state_digest(state)


def decision_seats(state: dict[str, Any]) -> list[int]:
    return [state["active_seat"]] if state["status"] == "active" else []


def _draw_random(state: dict[str, Any], upper: int) -> int:
    material = f"{RULES_VERSION}:{state['seed']}:{state['rng_counter']}"
    state["rng_counter"] += 1
    return random.Random(int.from_bytes(hashlib.sha256(material.encode()).digest(), "big")).randrange(upper)


def _piece_counts(state: dict[str, Any], seat: int) -> dict[str, int]:
    counts = {"road": sum(edge["owner"] == seat for edge in state["board"]["edges"]),
              "settlement": 0, "city": 0}
    for vertex in state["board"]["vertices"]:
        building = vertex["building"]
        if building is not None and building["seat"] == seat:
            counts[building["type"]] += 1
    return counts


def public_score(state: dict[str, Any], seat: int) -> int:
    pieces = _piece_counts(state, seat)
    return (pieces["settlement"] + 2 * pieces["city"]
            + 2 * (state["longest_road_seat"] == seat) + 2 * (state["largest_army_seat"] == seat))


def score(state: dict[str, Any], seat: int) -> int:
    return public_score(state, seat) + sum(
        card["type"] == "victory_point" for card in state["players"][seat]["development_cards"])


def longest_road_length(state: dict[str, Any], seat: int) -> int:
    board = state["board"]
    owned = [edge for edge in board["edges"] if edge["owner"] == seat]
    adjacency: dict[int, list[tuple[int, int]]] = {}
    for index, edge in enumerate(owned):
        a, b = edge["vertices"]
        adjacency.setdefault(a, []).append((b, 1 << index))
        adjacency.setdefault(b, []).append((a, 1 << index))
    blocked = {v["id"] for v in board["vertices"]
               if v["building"] is not None and v["building"]["seat"] != seat}

    def walk(vertex: int, used: int) -> int:
        if used and vertex in blocked:
            return 0
        return max((1 + walk(other, used | bit) for other, bit in adjacency.get(vertex, [])
                    if not used & bit), default=0)

    return max((walk(vertex, 0) for vertex in adjacency), default=0)


def _award_holder(values: list[int], incumbent: int | None, minimum: int) -> int | None:
    best = max(values)
    if best < minimum:
        return None
    leaders = [seat for seat, value in enumerate(values) if value == best]
    if incumbent in leaders:
        return incumbent
    return leaders[0] if len(leaders) == 1 else None


def _update_awards(state: dict[str, Any]) -> None:
    state["longest_road_seat"] = _award_holder(
        [longest_road_length(state, seat) for seat in range(state["player_count"])],
        state["longest_road_seat"], 5)
    state["largest_army_seat"] = _award_holder(
        [player["played_knights"] for player in state["players"]], state["largest_army_seat"], 3)


def _check_winner(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    if state["status"] != "active" or state["setup_index"] < 2 * state["player_count"]:
        return
    seat = state["turn_seat"]
    if score(state, seat) >= 10:
        state.update(status="finished", phase="finished", winner=seat, active_seat=seat,
                     trade=None, effect_return_phase=None, free_roads_remaining=0,
                     year_of_plenty_remaining=0, discard_remaining=[0] * state["player_count"])
        events.append({"type": "game_finished", "winner": seat, "score": score(state, seat)})


def _can_pay(resources: dict[str, int], cost: dict[str, int]) -> bool:
    return all(resources[resource] >= amount for resource, amount in cost.items())


def _transfer(source: dict[str, int], destination: dict[str, int], bundle: dict[str, int]) -> None:
    for resource, amount in bundle.items():
        source[resource] -= amount
        destination[resource] += amount


def _settlement_vertices(state: dict[str, Any], seat: int, *, setup: bool = False) -> list[int]:
    vertices, edges = state["board"]["vertices"], state["board"]["edges"]
    if _piece_counts(state, seat)["settlement"] >= 5:
        return []
    result = []
    for vertex in vertices:
        if vertex["building"] is not None:
            continue
        neighbors = {v for eid in vertex["edges"] for v in edges[eid]["vertices"] if v != vertex["id"]}
        if any(vertices[v]["building"] is not None for v in neighbors):
            continue
        if setup or any(edges[eid]["owner"] == seat for eid in vertex["edges"]):
            result.append(vertex["id"])
    return result


def _road_edges(state: dict[str, Any], seat: int, *, setup_vertex: int | None = None) -> list[int]:
    board = state["board"]
    if _piece_counts(state, seat)["road"] >= 15:
        return []
    result = []
    for edge in board["edges"]:
        if edge["owner"] is not None:
            continue
        if setup_vertex is not None:
            if setup_vertex in edge["vertices"]:
                result.append(edge["id"])
            continue
        for vid in edge["vertices"]:
            vertex = board["vertices"][vid]
            if vertex["building"] is not None:
                connected = vertex["building"]["seat"] == seat
            else:
                connected = any(board["edges"][eid]["owner"] == seat for eid in vertex["edges"])
            if connected:
                result.append(edge["id"])
                break
    return result


def maritime_ratio(state: dict[str, Any], seat: int, resource: str) -> int:
    ports = {vertex["port"] for vertex in state["board"]["vertices"]
             if vertex["building"] is not None and vertex["building"]["seat"] == seat}
    return 2 if resource in ports else 3 if "any" in ports else 4


def _robber_victims(state: dict[str, Any]) -> list[int]:
    seats = {state["board"]["vertices"][vid]["building"]["seat"]
             for vid in state["board"]["hexes"][state["robber_hex"]]["vertices"]
             if state["board"]["vertices"][vid]["building"] is not None}
    return sorted(seats - {state["turn_seat"]})


def _development_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    if state["development_played"]:
        return []
    playable = {card["type"] for card in state["players"][seat]["development_cards"]
                if card["bought_turn"] < state["turn_count"] and card["type"] != "victory_point"}
    actions = []
    if "knight" in playable:
        actions.append({"type": "play_knight"})
    if "road_building" in playable and _road_edges(state, seat):
        actions.append({"type": "play_road_building"})
    if "year_of_plenty" in playable and sum(state["bank"].values()):
        actions.append({"type": "play_year_of_plenty"})
    if "monopoly" in playable:
        actions.extend({"type": "play_monopoly", "resource": resource} for resource in RESOURCES)
    return actions


def _action_space(state: dict[str, Any], actions: list[dict[str, Any]]) -> ActionSpace:
    return ActionSpace.from_actions(state["phase"], state["decision_count"], actions)


def legal_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    if type(seat) is not int or state["status"] != "active" or seat != state["active_seat"]:
        return []
    phase = state["phase"]
    player = state["players"][seat]
    actions: list[dict[str, Any]] = []
    if phase == "setup_settlement":
        actions = [{"type": "place_settlement", "vertex": vertex}
                   for vertex in _settlement_vertices(state, seat, setup=True)]
    elif phase == "setup_road":
        actions = [{"type": "place_road", "edge": edge}
                   for edge in _road_edges(state, seat, setup_vertex=state["setup_vertex"])]
    elif phase == "roll":
        actions = [{"type": "roll_dice"}] + _development_actions(state, seat)
    elif phase == "main":
        actions = [{"type": "end_turn"}] + _development_actions(state, seat)
        for piece in ("road", "settlement", "city"):
            if not _can_pay(player["resources"], COSTS[piece]):
                continue
            if piece == "road":
                actions.extend({"type": "build_road", "edge": edge} for edge in _road_edges(state, seat))
            elif piece == "settlement":
                actions.extend({"type": "build_settlement", "vertex": vertex}
                               for vertex in _settlement_vertices(state, seat))
            elif _piece_counts(state, seat)["city"] < 4:
                actions.extend({"type": "build_city", "vertex": vertex["id"]}
                               for vertex in state["board"]["vertices"]
                               if vertex["building"] == {"seat": seat, "type": "settlement"})
        if state["development_deck"] and _can_pay(player["resources"], COSTS["development_card"]):
            actions.append({"type": "buy_development_card"})
        for give in RESOURCES:
            ratio = maritime_ratio(state, seat, give)
            if player["resources"][give] >= ratio:
                actions.extend({"type": "maritime_trade", "give": give, "receive": receive, "ratio": ratio}
                               for receive in RESOURCES if receive != give and state["bank"][receive] > 0)
        if sum(player["resources"].values()):
            actions.extend({"type": "propose_trade", "partner": other["seat"]}
                           for other in state["players"]
                           if other["seat"] != seat and sum(other["resources"].values()))
    elif phase == "discard":
        actions = [{"type": "discard", "resource": resource}
                   for resource in RESOURCES if player["resources"][resource] > 0]
    elif phase == "robber":
        actions = [{"type": "move_robber", "hex": tile["id"]}
                   for tile in state["board"]["hexes"] if tile["id"] != state["robber_hex"]]
    elif phase == "steal":
        actions = [{"type": "steal", "victim": victim} for victim in _robber_victims(state)]
    elif phase == "free_roads":
        actions = [{"type": "free_road", "edge": edge} for edge in _road_edges(state, seat)]
        actions.append({"type": "finish_road_building"})
    elif phase == "year_of_plenty":
        actions = [{"type": "take_resource", "resource": resource}
                   for resource in RESOURCES if state["bank"][resource] > 0]
    elif phase in ("trade_give", "trade_receive"):
        trade = state["trade"]
        resource = RESOURCES[trade["resource_index"]]
        if phase == "trade_give":
            limit = player["resources"][resource]
        else:
            # Only publicly known totals bound requests. Never inspect the
            # partner's private composition while constructing the offer menu.
            partner_total = sum(state["players"][trade["partner"]]["resources"].values())
            limit = min(19, partner_total - sum(trade["receive"].values()))
            if trade["give"][resource]:
                limit = 0
        actions = [{"type": "trade_amount", "resource": resource, "amount": amount}
                   for amount in range(limit + 1)] + [{"type": "cancel_trade"}]
    elif phase == "trade_response":
        trade = state["trade"]
        actions = [{"type": "respond_trade", "accept": False}]
        if sum(player["resources"].values()):
            actions.append({"type": "counter_trade"})
        if _can_pay(player["resources"], trade["receive"]):
            actions.append({"type": "respond_trade", "accept": True})
    return _action_space(state, actions).wrapped()


def _produce(state: dict[str, Any], roll: int, events: list[dict[str, Any]]) -> None:
    owed = [_empty_resources() for _ in state["players"]]
    for tile in state["board"]["hexes"]:
        if tile["number"] != roll or tile["id"] == state["robber_hex"] or tile["terrain"] == "desert":
            continue
        for vid in tile["vertices"]:
            building = state["board"]["vertices"][vid]["building"]
            if building is not None:
                owed[building["seat"]][tile["terrain"]] += 2 if building["type"] == "city" else 1
    received = [_empty_resources() for _ in state["players"]]
    for resource in RESOURCES:
        recipients = [seat for seat, bundle in enumerate(owed) if bundle[resource]]
        total = sum(bundle[resource] for bundle in owed)
        available = state["bank"][resource]
        if total <= available or len(recipients) == 1:
            for seat in recipients:
                amount = min(available, owed[seat][resource])
                _transfer(state["bank"], state["players"][seat]["resources"], {resource: amount})
                received[seat][resource] = amount
    events.append({"type": "resources_produced", "roll": roll,
                   "received": [{"seat": seat, "resources": bundle} for seat, bundle in enumerate(received)
                                if sum(bundle.values())]})


def _resume_effect(state: dict[str, Any]) -> None:
    state["phase"] = state["effect_return_phase"] or "main"
    state["effect_return_phase"] = None
    state["active_seat"] = state["turn_seat"]
    state["free_roads_remaining"] = 0
    state["year_of_plenty_remaining"] = 0


def _advance_discard(state: dict[str, Any]) -> None:
    pending = [seat for seat, remaining in enumerate(state["discard_remaining"]) if remaining]
    if pending:
        state["phase"] = "discard"
        state["active_seat"] = pending[0]
    else:
        state["phase"] = "robber"
        state["active_seat"] = state["turn_seat"]


def _finish_trade(state: dict[str, Any]) -> None:
    state["trade"] = None
    state["phase"] = "main"
    state["active_seat"] = state["turn_seat"]


def apply_action(state: dict[str, Any], seat: int, action: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    action = _action_space(state, [item["action"] for item in legal_actions(state, seat)]).require(
        action, error_factory=RuleError)
    next_state = deepcopy(state)
    state = next_state
    player = state["players"][seat]
    kind = action["type"]
    # The accepted input is a trusted audit/replay record. Random hidden
    # outcomes are deliberately absent from all supplementary events.
    events: list[dict[str, Any]] = [action_accepted(seat, deepcopy(action))]
    state["decision_count"] += 1
    if kind in ("place_settlement", "build_settlement", "build_city"):
        vertex = state["board"]["vertices"][action["vertex"]]
        piece = "city" if kind == "build_city" else "settlement"
        vertex["building"] = {"seat": seat, "type": piece}
        if kind == "place_settlement":
            state["setup_vertex"] = action["vertex"]
            state["phase"] = "setup_road"
            if state["setup_index"] >= state["player_count"]:
                for hid in vertex["hexes"]:
                    resource = state["board"]["hexes"][hid]["terrain"]
                    if resource != "desert" and state["bank"][resource]:
                        _transfer(state["bank"], player["resources"], {resource: 1})
        else:
            _transfer(player["resources"], state["bank"], COSTS[piece])
        _update_awards(state)
        events.append({"type": "building_placed", "seat": seat, "piece": piece, "vertex": action["vertex"]})
    elif kind in ("place_road", "build_road", "free_road"):
        state["board"]["edges"][action["edge"]]["owner"] = seat
        if kind == "place_road":
            state["setup_index"] += 1
            state["setup_vertex"] = None
            if state["setup_index"] == len(state["setup_order"]):
                state.update(phase="roll", active_seat=0, turn_seat=0)
            else:
                state["active_seat"] = state["setup_order"][state["setup_index"]]
                state["turn_seat"] = state["active_seat"]
                state["phase"] = "setup_settlement"
        elif kind == "build_road":
            _transfer(player["resources"], state["bank"], COSTS["road"])
        else:
            state["free_roads_remaining"] -= 1
            if state["free_roads_remaining"] == 0 or not _road_edges(state, seat):
                _resume_effect(state)
        _update_awards(state)
        events.append({"type": "road_placed", "seat": seat, "edge": action["edge"]})
    elif kind == "roll_dice":
        state["last_roll"] = [_draw_random(state, 6) + 1, _draw_random(state, 6) + 1]
        total = sum(state["last_roll"])
        events.append({"type": "dice_rolled", "seat": seat, "dice": list(state["last_roll"]), "total": total})
        if total == 7:
            state["discard_remaining"] = [sum(p["resources"].values()) // 2
                                           if sum(p["resources"].values()) > 7 else 0 for p in state["players"]]
            state["effect_return_phase"] = "main"
            _advance_discard(state)
        else:
            _produce(state, total, events)
            state["phase"] = "main"
    elif kind == "discard":
        _transfer(player["resources"], state["bank"], {action["resource"]: 1})
        state["discard_remaining"][seat] -= 1
        _advance_discard(state)
        events.append({"type": "resource_discarded", "seat": seat, "count": 1})
    elif kind == "move_robber":
        state["robber_hex"] = action["hex"]
        if _robber_victims(state):
            state["phase"] = "steal"
        else:
            _resume_effect(state)
        events.append({"type": "robber_moved", "seat": seat, "hex": action["hex"]})
    elif kind == "steal":
        victim = state["players"][action["victim"]]
        cards = [resource for resource in RESOURCES for _ in range(victim["resources"][resource])]
        if cards:
            resource = cards[_draw_random(state, len(cards))]
            _transfer(victim["resources"], player["resources"], {resource: 1})
        events.append({"type": "resource_stolen", "seat": seat, "victim": action["victim"], "count": int(bool(cards))})
        _resume_effect(state)
    elif kind == "buy_development_card":
        _transfer(player["resources"], state["bank"], COSTS["development_card"])
        card_id = state["development_deck"].pop()
        player["development_cards"].append({"id": card_id, "type": DEVELOPMENT_CARDS[card_id],
                                             "bought_turn": state["turn_count"]})
        events.append({"type": "development_card_bought", "seat": seat})
    elif kind.startswith("play_"):
        card_type = kind.removeprefix("play_")
        card = next(card for card in player["development_cards"]
                    if card["type"] == card_type and card["bought_turn"] < state["turn_count"])
        player["development_cards"].remove(card)
        state["development_discard"].append(card["id"])
        state["development_played"] = True
        state["effect_return_phase"] = state["phase"]
        events.append({"type": "development_card_played", "seat": seat, "card_type": card_type})
        if card_type == "knight":
            player["played_knights"] += 1
            _update_awards(state)
            state["phase"] = "robber"
        elif card_type == "road_building":
            state["phase"] = "free_roads"
            state["free_roads_remaining"] = min(2, 15 - _piece_counts(state, seat)["road"])
        elif card_type == "year_of_plenty":
            state["phase"] = "year_of_plenty"
            state["year_of_plenty_remaining"] = min(2, sum(state["bank"].values()))
        elif card_type == "monopoly":
            resource = action["resource"]
            count = 0
            for other in state["players"]:
                if other["seat"] != seat:
                    amount = other["resources"][resource]
                    _transfer(other["resources"], player["resources"], {resource: amount})
                    count += amount
            events.append({"type": "monopoly_collected", "seat": seat, "resource": resource, "count": count})
            _resume_effect(state)
    elif kind == "finish_road_building":
        _resume_effect(state)
    elif kind == "take_resource":
        _transfer(state["bank"], player["resources"], {action["resource"]: 1})
        state["year_of_plenty_remaining"] -= 1
        if not state["year_of_plenty_remaining"] or not sum(state["bank"].values()):
            _resume_effect(state)
    elif kind == "maritime_trade":
        _transfer(player["resources"], state["bank"], {action["give"]: action["ratio"]})
        _transfer(state["bank"], player["resources"], {action["receive"]: 1})
    elif kind in ("propose_trade", "counter_trade"):
        partner = action["partner"] if kind == "propose_trade" else state["trade"]["proposer"]
        state["trade"] = {"proposer": seat, "partner": partner, "give": _empty_resources(),
                          "receive": _empty_resources(), "resource_index": 0}
        state["phase"] = "trade_give"
    elif kind == "trade_amount":
        trade = state["trade"]
        side = "give" if state["phase"] == "trade_give" else "receive"
        trade[side][action["resource"]] = action["amount"]
        trade["resource_index"] += 1
        if trade["resource_index"] == len(RESOURCES):
            if not sum(trade[side].values()):
                events.append({"type": "trade_cancelled", "seat": seat, "reason": "empty_bundle"})
                _finish_trade(state)
            elif side == "give":
                state["phase"] = "trade_receive"
                trade["resource_index"] = 0
            else:
                state["phase"] = "trade_response"
                state["active_seat"] = trade["partner"]
                events.append({"type": "trade_offered", "seat": seat, "partner": trade["partner"],
                               "give": dict(trade["give"]), "receive": dict(trade["receive"])})
    elif kind == "cancel_trade":
        _finish_trade(state)
    elif kind == "respond_trade":
        trade = state["trade"]
        if action["accept"]:
            proposer = state["players"][trade["proposer"]]
            _transfer(proposer["resources"], player["resources"], trade["give"])
            _transfer(player["resources"], proposer["resources"], trade["receive"])
        events.append({"type": "trade_resolved", "seat": seat, "proposer": trade["proposer"],
                       "accepted": action["accept"]})
        _finish_trade(state)
    elif kind == "end_turn":
        _check_winner(state, events)
        if state["status"] == "active":
            state["turn_count"] += 1
            state["turn_seat"] = (state["turn_seat"] + 1) % state["player_count"]
            state["active_seat"] = state["turn_seat"]
            state["phase"] = "roll"
            state["last_roll"] = None
            state["development_played"] = False
    _check_winner(state, events)
    validate_state(state)
    return next_state, events


def rankings(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [{"seat": seat, "score": score(state, seat) if state["status"] == "finished" else public_score(state, seat), "public_score": public_score(state, seat),
             "winner": state["winner"] == seat} for seat in range(state["player_count"])]
    return assign_competition_ranks(
        rows, sort_key=lambda row: (not row["winner"], -row["score"], row["seat"]),
        tie_key=lambda row: (row["winner"], row["score"]))


def observe(state: dict[str, Any], seat: int) -> dict[str, Any]:
    if type(seat) is not int or not 0 <= seat < state["player_count"]:
        raise RuleError("seat is out of range")
    players = []
    for player in state["players"]:
        own = player["seat"] == seat
        pieces = _piece_counts(state, player["seat"])
        players.append({
            "seat": player["seat"], "resource_count": sum(player["resources"].values()),
            "resources": dict(player["resources"]) if own else None,
            "development_count": len(player["development_cards"]),
            "development_cards": deepcopy(player["development_cards"]) if own else None,
            "played_knights": player["played_knights"],
            "longest_road_length": longest_road_length(state, player["seat"]),
            "public_score": public_score(state, player["seat"]),
            "score": score(state, player["seat"]) if own or state["status"] == "finished" else None,
            "roads_remaining": 15 - pieces["road"], "settlements_remaining": 5 - pieces["settlement"],
            "cities_remaining": 4 - pieces["city"],
        })
    return {
        "game": "catan", "rules_version": state["rules_version"], "viewer_seat": seat,
        "status": state["status"], "phase": state["phase"], "turn_count": state["turn_count"],
        "decision_count": state["decision_count"], "active_seat": state["active_seat"],
        "turn_seat": state["turn_seat"], "board": deepcopy(state["board"]), "bank": dict(state["bank"]),
        "robber_hex": state["robber_hex"], "last_roll": deepcopy(state["last_roll"]),
        "players": players, "trade": deepcopy(state["trade"]),
        "setup_index": state["setup_index"], "setup_vertex": state["setup_vertex"],
        "discard_remaining": list(state["discard_remaining"]),
        "free_roads_remaining": state["free_roads_remaining"],
        "year_of_plenty_remaining": state["year_of_plenty_remaining"],
        "development_deck_count": len(state["development_deck"]),
        "development_played": state["development_played"],
        "longest_road_seat": state["longest_road_seat"], "largest_army_seat": state["largest_army_seat"],
        "winner": state["winner"], "rankings": rankings(state) if state["status"] == "finished" else None,
        "costs": deepcopy(COSTS), "maritime_ratios": {r: maritime_ratio(state, seat, r) for r in RESOURCES},
    }


def validate_state(state: dict[str, Any]) -> None:
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(message)

    def integer(value: Any, minimum: int = 0, maximum: int | None = None) -> bool:
        return type(value) is int and value >= minimum and (maximum is None or value <= maximum)

    n = state.get("player_count")
    require(type(n) is int and n in (3, 4), "invalid CATAN player count")
    require(state.get("schema_version") == SCHEMA_VERSION and state.get("rules_version") == RULES_VERSION,
            "invalid CATAN state version")
    require(state.get("status") in ("active", "finished"), "invalid CATAN status")
    require(state.get("phase") in PHASES, "invalid CATAN phase")
    require((state["phase"] == "finished") == (state["status"] == "finished"), "phase/status mismatch")
    require(integer(state.get("active_seat"), 0, n - 1) and integer(state.get("turn_seat"), 0, n - 1),
            "invalid CATAN active seat")
    for key in ("turn_count", "decision_count", "rng_counter"):
        require(integer(state.get(key)), f"invalid {key}")
    require(type(state.get("seed")) is int, "invalid CATAN random seed")
    require(type(state.get("development_played")) is bool, "invalid development-played flag")
    players = state.get("players", [])
    require(len(players) == n, "invalid CATAN players")
    for seat, player in enumerate(players):
        require(player.get("seat") == seat and type(player.get("seat")) is int, "invalid player seat")
        require(integer(player.get("played_knights"), 0, 14), "invalid knight count")
    pools = [state.get("bank")] + [player.get("resources") for player in players]
    for pool in pools:
        require(isinstance(pool, dict) and set(pool) == set(RESOURCES), "invalid resource pool")
        require(all(integer(value, 0, 19) for value in pool.values()), "invalid resource quantity")
    for resource in RESOURCES:
        require(sum(pool[resource] for pool in pools) == 19, f"resource conservation failed for {resource}")
    board = state.get("board", {})
    hexes, vertices, edges, ports = (board.get(key, []) for key in ("hexes", "vertices", "edges", "ports"))
    require((len(hexes), len(vertices), len(edges), len(ports)) == (19, 54, 72, 9), "invalid CATAN board size")
    require([tile.get("id") for tile in hexes] == list(range(19)), "invalid hex ids")
    require([vertex.get("id") for vertex in vertices] == list(range(54)), "invalid vertex ids")
    require([edge.get("id") for edge in edges] == list(range(72)), "invalid edge ids")
    require(Counter(tile.get("terrain") for tile in hexes) == Counter({**RESOURCE_COUNTS, "desert": 1}),
            "invalid CATAN terrain distribution")
    require(Counter(tile.get("number") for tile in hexes if tile.get("terrain") != "desert") == Counter(NUMBER_TOKENS),
            "invalid CATAN number tokens")
    require(all(tile["number"] is None for tile in hexes if tile["terrain"] == "desert"), "desert has a number")
    require(integer(state.get("robber_hex"), 0, 18), "invalid robber hex")
    require(len({(tile.get("q"), tile.get("r")) for tile in hexes}) == 19, "duplicate hex coordinates")
    for tile in hexes:
        require(integer(tile.get("q"), -2, 2) and integer(tile.get("r"), -2, 2)
                and abs(tile["q"] + tile["r"]) <= 2, "invalid hex coordinates")
        require(len(tile.get("vertices", [])) == 6 and len(set(tile["vertices"])) == 6
                and all(integer(v, 0, 53) for v in tile["vertices"]), "invalid hex vertices")
        require(len(tile.get("edges", [])) == 6 and len(set(tile["edges"])) == 6
                and all(integer(e, 0, 71) for e in tile["edges"]), "invalid hex edges")
        for i, eid in enumerate(tile["edges"]):
            require(set(edges[eid]["vertices"]) == {tile["vertices"][i], tile["vertices"][(i + 1) % 6]},
                    "hex edge topology mismatch")
    endpoints = set()
    for edge in edges:
        ends = edge.get("vertices", [])
        require(len(ends) == 2 and all(integer(v, 0, 53) for v in ends) and ends[0] < ends[1], "invalid edge endpoints")
        require(tuple(ends) not in endpoints, "duplicate edge")
        endpoints.add(tuple(ends))
        require(edge.get("owner") is None or integer(edge["owner"], 0, n - 1), "invalid road owner")
        require(any(edge["id"] in tile["edges"] for tile in hexes), "edge belongs to no hex")
    for vertex in vertices:
        require(set(vertex.get("edges", [])) == {edge["id"] for edge in edges if vertex["id"] in edge["vertices"]}
                and len(vertex["edges"]) in (2, 3), "vertex edge topology mismatch")
        require(set(vertex.get("hexes", [])) == {tile["id"] for tile in hexes if vertex["id"] in tile["vertices"]}
                and len(vertex["hexes"]) in (1, 2, 3), "vertex hex topology mismatch")
        for axis in ("x", "y"):
            require(type(vertex.get(axis)) in (int, float) and math.isfinite(vertex[axis]), "invalid vertex position")
        building = vertex.get("building")
        require(building is None or (isinstance(building, dict) and set(building) == {"seat", "type"}
                and integer(building["seat"], 0, n - 1) and building["type"] in ("settlement", "city")),
                "invalid building")
        if building is not None:
            require(all(vertices[other]["building"] is None for eid in vertex["edges"]
                        for other in edges[eid]["vertices"] if other != vertex["id"]), "settlement distance rule violated")
        require(vertex.get("port") in (None, "any", *RESOURCES), "invalid vertex port")
    require([port.get("id") for port in ports] == list(range(9)), "invalid port ids")
    require(Counter(port.get("resource") for port in ports) == Counter({"any": 4, **dict.fromkeys(RESOURCES, 1)}),
            "invalid ports")
    port_vertices = []
    for port in ports:
        ends = port.get("vertices", [])
        require(len(ends) == 2 and all(integer(v, 0, 53) for v in ends), "invalid port vertices")
        matching = [edge for edge in edges if set(edge["vertices"]) == set(ends)]
        require(len(matching) == 1 and sum(matching[0]["id"] in tile["edges"] for tile in hexes) == 1,
                "port must occupy a coastal edge")
        require(all(vertices[v]["port"] == port["resource"] for v in ends), "port ownership mismatch")
        port_vertices.extend(ends)
    require(len(set(port_vertices)) == 18, "ports overlap")
    require(all(vertex["port"] is None for vertex in vertices if vertex["id"] not in port_vertices), "unlisted vertex port")
    for seat in range(n):
        pieces = _piece_counts(state, seat)
        require(pieces["road"] <= 15 and pieces["settlement"] <= 5 and pieces["city"] <= 4, "piece supply exceeded")
    deck, discard = state.get("development_deck", []), state.get("development_discard", [])
    require(isinstance(deck, list) and isinstance(discard, list), "invalid development deck")
    all_cards = list(deck) + list(discard)
    for player in players:
        require(isinstance(player.get("development_cards"), list), "invalid development hand")
        for card in player["development_cards"]:
            require(isinstance(card, dict) and set(card) == {"id", "type", "bought_turn"}, "invalid development card")
            require(card["id"] in DEVELOPMENT_CARDS and card["type"] == DEVELOPMENT_CARDS[card["id"]], "unknown development card")
            require(integer(card["bought_turn"], 0, state["turn_count"]), "invalid development purchase turn")
            all_cards.append(card["id"])
    require(Counter(all_cards) == Counter(DEVELOPMENT_CARDS.keys()), "development card conservation failed")
    require(not any(DEVELOPMENT_CARDS[c] == "victory_point" for c in discard), "victory points cannot be discarded")
    require(sum(player["played_knights"] for player in players) == sum(DEVELOPMENT_CARDS[c] == "knight" for c in discard),
            "played knight conservation failed")
    for key, values, minimum in (
        ("longest_road_seat", [longest_road_length(state, seat) for seat in range(n)], 5),
        ("largest_army_seat", [player["played_knights"] for player in players], 3),
    ):
        holder = state.get(key)
        require(holder is None or integer(holder, 0, n - 1), "invalid award holder")
        require(_award_holder(values, holder, minimum) == holder, "award holder inconsistent with board")
    require(state.get("setup_order") == list(range(n)) + list(reversed(range(n))), "invalid setup order")
    require(integer(state.get("setup_index"), 0, 2 * n), "invalid setup progress")
    setup = state["setup_index"] < 2 * n
    require(setup == state["phase"].startswith("setup_"), "invalid setup phase")
    if setup:
        require(state["active_seat"] == state["setup_order"][state["setup_index"]]
                and state["turn_seat"] == state["active_seat"], "incorrect setup seat")
        if state["phase"] == "setup_road":
            require(integer(state.get("setup_vertex"), 0, 53)
                    and vertices[state["setup_vertex"]]["building"] == {"seat": state["active_seat"], "type": "settlement"},
                    "invalid pending setup road")
        else:
            require(state.get("setup_vertex") is None, "unexpected pending setup vertex")
    else:
        require(state.get("setup_vertex") is None, "setup vertex after setup")
    last_roll = state.get("last_roll")
    require(last_roll is None or (isinstance(last_roll, list) and len(last_roll) == 2
            and all(integer(die, 1, 6) for die in last_roll)), "invalid dice")
    discards = state.get("discard_remaining", [])
    require(isinstance(discards, list) and len(discards) == n
            and all(integer(value) for value in discards), "invalid discard counts")
    require(all(value <= sum(players[seat]["resources"].values()) for seat, value in enumerate(discards)),
            "discard exceeds hand")
    require((sum(discards) > 0) == (state["phase"] == "discard"), "discard phase mismatch")
    if state["phase"] == "discard":
        require(discards[state["active_seat"]] > 0, "discard actor has no pending discards")
    effect = state.get("effect_return_phase")
    require(effect in (None, "roll", "main"), "invalid effect return phase")
    resolving = state["phase"] in ("discard", "robber", "steal", "free_roads", "year_of_plenty")
    require(resolving == (effect is not None), "effect phase mismatch")
    if state["phase"] == "steal":
        require(bool(_robber_victims(state)), "steal has no eligible victims")
    require(integer(state.get("free_roads_remaining"), 0, 2)
            and ((state["free_roads_remaining"] > 0) == (state["phase"] == "free_roads")), "invalid free-road phase")
    require(integer(state.get("year_of_plenty_remaining"), 0, 2)
            and ((state["year_of_plenty_remaining"] > 0) == (state["phase"] == "year_of_plenty")), "invalid plenty phase")
    trade = state.get("trade")
    trading = state["phase"] in ("trade_give", "trade_receive", "trade_response")
    require(trading == (trade is not None), "trade phase mismatch")
    if trading:
        require(isinstance(trade, dict) and integer(trade.get("proposer"), 0, n - 1)
                and state["turn_seat"] in (trade.get("proposer"), trade.get("partner"))
                and integer(trade.get("partner"), 0, n - 1) and trade["partner"] != trade["proposer"], "invalid trade parties")
        require(integer(trade.get("resource_index"), 0, 5), "invalid trade progress")
        require(trade["resource_index"] == 5 if state["phase"] == "trade_response" else trade["resource_index"] < 5,
                "invalid trade index for phase")
        for side in ("give", "receive"):
            bundle = trade.get(side)
            require(isinstance(bundle, dict) and set(bundle) == set(RESOURCES)
                    and all(integer(value, 0, 19) for value in bundle.values()), "invalid trade bundle")
        require(_can_pay(players[trade["proposer"]]["resources"], trade["give"]), "unfunded trade offer")
        require(all(not trade["give"][r] or not trade["receive"][r] for r in RESOURCES), "same resource on both trade sides")
        if state["phase"] in ("trade_receive", "trade_response"):
            require(sum(trade["give"].values()) > 0, "trade gives no resources")
        if state["phase"] == "trade_response":
            require(sum(trade["receive"].values()) > 0 and state["active_seat"] == trade["partner"], "invalid trade response")
    if state["phase"] in ("trade_give", "trade_receive"):
        require(state["active_seat"] == trade["proposer"], "invalid trade proposer actor")
    if state["phase"] not in ("discard", "trade_response", "trade_give", "trade_receive"):
        require(state["active_seat"] == state["turn_seat"], "decision actor differs from turn owner")
    winner = state.get("winner")
    if state["status"] == "finished":
        require(integer(winner, 0, n - 1) and winner == state["turn_seat"] and score(state, winner) >= 10,
                "invalid CATAN winner")
    else:
        require(winner is None, "active game has winner")
