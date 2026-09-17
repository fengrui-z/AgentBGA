"""Deterministic Carcassonne base game with modern field scoring.

One decision places the drawn tile; a second deploys or skips a follower.
Scoring happens only after that second decision. No hidden deck order or
seed is exposed to seats, spectators, or domain events.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import random
from typing import Any

from ..game import GameRuleError
from ..mechanics import ActionSpace, action_accepted, assign_competition_ranks, state_digest
from .catalog import CATALOG, SOURCE, START_TILE, TILES, oriented

RULES_VERSION = "hig-base-farmers-1.0"
SCHEMA_VERSION = "agentbga.carcassonne.state.v1"
DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))
RULES = {
    "turn": "Place the drawn tile, then optionally place one of your seven followers on that tile; scoring follows.",
    "placement": "Rotate clockwise in quarter turns (0–3). Touch at least one existing tile by an edge; every adjacent edge must match. Coordinates: x east, y south.",
    "followers": "A follower may occupy only an unoccupied connected city, road, field, or monastery. Merging previously occupied features is allowed.",
    "completion": "Completed roads score 1 per tile; completed cities 2 per tile and shield; monasteries 9 when surrounded by all eight neighbors. Return all followers on scored features.",
    "majority": "Only the greatest follower count scores a feature; tied players each receive its full value. Tiles in the same feature count once even if several segments reconnect.",
    "farmers": "Farmers stay until game end. Each field scores 3 per distinct completed city touching it, using the same majority rule.",
    "end": "When the deck is exhausted, incomplete roads score 1 per tile, cities 1 per tile and shield, monasteries 1 plus occupied neighbors. Highest score wins; ties are shared.",
    "draw": "A tile with no legal placement is discarded publicly and replaced for the same player. Future draw order is hidden.",
}


class RuleError(GameRuleError):
    pass


def describe() -> dict[str, Any]:
    return {"id": "carcassonne", "name": "Carcassonne", "rules_version": RULES_VERSION,
            "players": {"minimum": 2, "maximum": 5}, "hidden_information": True,
            "implementation_status": "playable_beta", "runnable": True,
            "decision_model": "tile_then_optional_follower", "default_max_turns": 160,
            "action_types": ["place_tile", "place_meeple", "skip_meeple"],
            "rules_sources": [SOURCE],
            "content_scope": "72 base tiles, seven followers per player, modern farmer scoring. No River, Abbot, expansions, or publisher artwork.",
            "win_condition": "Highest score after final scoring; tied scores share victory."}


def _key(x: int, y: int) -> str:
    return f"{x},{y}"


def _node(key: str, feature_id: str) -> str:
    return f"{key}:{feature_id}"


def _geometry(tile: dict) -> dict:
    return oriented(TILES[tile["tile_id"]], tile["rotation"])


def placements(state: dict, tile_id: str) -> list[dict]:
    board = state["board"]
    frontier = {(t["x"] + dx, t["y"] + dy) for t in board.values() for dx, dy in DIRECTIONS
                if _key(t["x"] + dx, t["y"] + dy) not in board}
    result = []
    for x, y in sorted(frontier, key=lambda p: (p[1], p[0])):
        for rotation in range(4):
            edges = oriented(TILES[tile_id], rotation)["edges"]
            if all((other := board.get(_key(x + dx, y + dy))) is None
                   or edges[i] == _geometry(other)["edges"][(i + 2) % 4]
                   for i, (dx, dy) in enumerate(DIRECTIONS)):
                result.append({"type": "place_tile", "x": x, "y": y, "rotation": rotation})
    return result


def feature_graph(state: dict) -> tuple[list[dict], dict[str, int]]:
    """Rebuild the small public topology; never store mutable derived caches in state."""
    board = state["board"]
    nodes, ports, neighbors, open_ports = {}, {}, {}, {}
    for key, tile in board.items():
        for feature in _geometry(tile)["features"]:
            node = _node(key, feature["id"])
            nodes[node] = (key, feature)
            neighbors[node], open_ports[node] = set(), 0
            for port in feature["ports"]:
                ports[(key, feature["kind"], port)] = node
    for node, (key, feature) in nodes.items():
        tile = board[key]
        for port in feature["ports"]:
            field = feature["kind"] == "field"
            edge = port // 2 if field else port
            dx, dy = DIRECTIONS[edge]
            other_key = _key(tile["x"] + dx, tile["y"] + dy)
            opposite = ((edge + 2) % 4) * 2 + (1 - port % 2) if field else (edge + 2) % 4
            other = ports.get((other_key, feature["kind"], opposite))
            if other is not None:
                neighbors[node].add(other)
            else:
                open_ports[node] += 1
    components, lookup = [], {}
    for start in nodes:
        if start in lookup:
            continue
        members, pending = set(), [start]
        while pending:
            node = pending.pop()
            if node in members:
                continue
            members.add(node)
            pending.extend(neighbors[node] - members)
        kind = nodes[start][1]["kind"]
        keys = {nodes[n][0] for n in members}
        missing = sum(open_ports[n] for n in members)
        if kind == "monastery":
            tile = board[nodes[start][0]]
            missing = sum(_key(tile["x"] + dx, tile["y"] + dy) not in board
                          for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)
        component = {"id": min(members), "kind": kind, "nodes": sorted(members),
                     "tiles": sorted(keys), "open_edges": missing,
                     "complete": kind != "field" and missing == 0,
                     "shields": sum(nodes[n][1]["shields"] for n in members),
                     "meeples": [], "adjacent_cities": []}
        for node in members:
            lookup[node] = len(components)
        components.append(component)
    for token in state["meeples"]:
        components[lookup[_node(token["tile"], token["feature"])]]["meeples"].append(token)
    for component in components:
        if component["kind"] == "field":
            cities = {lookup[_node(nodes[n][0], c)] for n in component["nodes"]
                      for c in nodes[n][1].get("cities", [])}
            component["adjacent_cities"] = sorted(components[c]["id"] for c in cities if components[c]["complete"])
        component["followers"] = dict(sorted(Counter(t["seat"] for t in component["meeples"]).items()))
        maximum = max(component["followers"].values(), default=0)
        component["owners"] = [s for s, n in component["followers"].items() if n == maximum]
        if component["kind"] == "city":
            points = (len(component["tiles"]) + component["shields"]) * (2 if component["complete"] else 1)
        elif component["kind"] == "road":
            points = len(component["tiles"])
        elif component["kind"] == "monastery":
            points = 9 - component["open_edges"]
        else:
            points = 3 * len(component["adjacent_cities"])
        component["points"] = points
    return components, lookup


def _score_features(state: dict, events: list[dict], *, final: bool = False) -> None:
    components, _ = feature_graph(state)
    returned = []
    for component in components:
        if not component["meeples"] or (not final and not component["complete"]):
            continue
        for seat in component["owners"]:
            player = state["players"][seat]
            player["score"] += component["points"]
            player["score_breakdown"][component["kind"]] += component["points"]
        for token in component["meeples"]:
            state["players"][token["seat"]]["meeples_available"] += 1
            returned.append(token)
        events.append({"type": "feature_scored", "feature": component["id"], "kind": component["kind"],
                       "points": component["points"], "seats": component["owners"],
                       "tiles": component["tiles"], "returned": deepcopy(component["meeples"]), "final": final})
    state["meeples"] = [m for m in state["meeples"] if m not in returned]


def _draw(state: dict, events: list[dict]) -> None:
    while state["deck"]:
        tile_id = state["deck"].pop()
        if placements(state, tile_id):
            state["current_tile"] = tile_id
            state["phase"] = "place_tile"
            events.append({"type": "tile_drawn", "tile_id": tile_id, "seat": state["active_seat"]})
            return
        state["discarded"].append(tile_id)
        events.append({"type": "tile_discarded", "tile_id": tile_id, "reason": "no_legal_placement"})
    state["current_tile"] = None
    _score_features(state, events, final=True)
    state["status"], state["phase"] = "finished", "finished"
    events.append({"type": "game_finished", "rankings": rankings(state)})


def new_game(players: int, seed: int, config: dict | None = None) -> dict:
    if type(players) is not int or not 2 <= players <= 5:
        raise RuleError("Carcassonne requires 2–5 players")
    if config not in (None, {}):
        raise RuleError("Carcassonne base game does not accept setup options")
    deck = [t for t in TILES if t != START_TILE]
    random.Random(seed).shuffle(deck)
    state = {"schema_version": SCHEMA_VERSION, "rules_version": RULES_VERSION, "seed": seed,
             "player_count": players, "status": "active", "phase": "place_tile", "active_seat": 0,
             "turn_count": 0, "completed_turns": 0, "deck": deck, "discarded": [],
             "current_tile": None, "last_placed": None,
             "board": {"0,0": {"tile_id": START_TILE, "x": 0, "y": 0, "rotation": 0}}, "meeples": [],
             "players": [{"seat": seat, "score": 0, "meeples_available": 7,
                          "score_breakdown": dict.fromkeys(("road", "city", "monastery", "field"), 0)}
                         for seat in range(players)]}
    _draw(state, [])
    validate_state(state)
    return state


def _seat(state: dict, seat: int) -> None:
    if type(seat) is not int or not 0 <= seat < state["player_count"]:
        raise RuleError("seat is out of range")


def _actions(state: dict, seat: int) -> list[dict]:
    _seat(state, seat)
    if state["status"] != "active" or seat != state["active_seat"]:
        return []
    if state["phase"] == "place_tile":
        return placements(state, state["current_tile"])
    result = [{"type": "skip_meeple"}]
    if state["players"][seat]["meeples_available"]:
        components, lookup = feature_graph(state)
        key = state["last_placed"]
        for feature in _geometry(state["board"][key])["features"]:
            if not components[lookup[_node(key, feature["id"])]]["meeples"]:
                result.append({"type": "place_meeple", "feature": feature["id"]})
    return result


def _space(state: dict, actions: list[dict]) -> ActionSpace:
    return ActionSpace.from_actions(state["phase"], state["turn_count"], actions, prefix="carcassonne")


def legal_actions(state: dict, seat: int) -> list[dict]:
    return _space(state, _actions(state, seat)).wrapped()


def apply_action(state: dict, seat: int, action: dict) -> tuple[dict, list[dict]]:
    canonical = _space(state, _actions(state, seat)).require(action, error_factory=RuleError)
    next_state = deepcopy(state)
    events = [action_accepted(seat, canonical)]
    next_state["turn_count"] += 1
    if canonical["type"] == "place_tile":
        x, y = canonical["x"], canonical["y"]
        key = _key(x, y)
        tile = {"tile_id": next_state["current_tile"], "x": x, "y": y, "rotation": canonical["rotation"]}
        next_state["board"][key] = tile
        next_state["current_tile"] = None
        next_state["last_placed"] = key
        next_state["phase"] = "place_meeple"
        events.append({"type": "tile_placed", "seat": seat, **tile})
    else:
        if canonical["type"] == "place_meeple":
            token = {"tile": next_state["last_placed"], "feature": canonical["feature"], "seat": seat}
            next_state["meeples"].append(token)
            next_state["players"][seat]["meeples_available"] -= 1
            events.append({"type": "meeple_placed", **token})
        _score_features(next_state, events)
        next_state["completed_turns"] += 1
        next_state["active_seat"] = (seat + 1) % next_state["player_count"]
        _draw(next_state, events)
    validate_state(next_state)
    return next_state, events


def rankings(state: dict) -> list[dict]:
    return assign_competition_ranks(
        [{"seat": p["seat"], "score": p["score"]} for p in state["players"]],
        sort_key=lambda p: (-p["score"], p["seat"]), tie_key=lambda p: (p["score"],))


def _tile_view(tile: dict) -> dict:
    return {**tile, "code": TILES[tile["tile_id"]], **deepcopy(_geometry(tile))}


def observe(state: dict, seat: int) -> dict:
    _seat(state, seat)
    components, _ = feature_graph(state)
    return {"game": "carcassonne", "rules_version": RULES_VERSION, "viewer_seat": seat,
            **{key: state[key] for key in ("status", "phase", "active_seat", "turn_count", "completed_turns", "last_placed")},
            "current_tile": _tile_view({"tile_id": state["current_tile"], "rotation": 0}) if state["current_tile"] else None,
            "deck_count": len(state["deck"]), "discarded": list(state["discarded"]),
            "board": [_tile_view(t) for t in state["board"].values()],
            "meeples": deepcopy(state["meeples"]), "players": deepcopy(state["players"]),
            "features": [{k: deepcopy(v) for k, v in c.items() if k != "meeples"} for c in components],
            "rules": dict(RULES), "rankings": rankings(state)}


def state_hash(state: dict) -> str:
    return state_digest(state)


def validate_state(state: dict) -> None:
    assert state["schema_version"] == SCHEMA_VERSION and state["rules_version"] == RULES_VERSION
    assert 2 <= state["player_count"] <= 5 and len(state["players"]) == state["player_count"]
    assert state["status"] in ("active", "finished")
    assert type(state["active_seat"]) is int and 0 <= state["active_seat"] < state["player_count"]
    assert type(state["turn_count"]) is int and state["turn_count"] >= 0
    board = state["board"]
    assert board.get("0,0") == {"tile_id": START_TILE, "x": 0, "y": 0, "rotation": 0}
    all_tiles = [t["tile_id"] for t in board.values()] + state["deck"] + state["discarded"]
    if state["current_tile"]:
        all_tiles.append(state["current_tile"])
    assert Counter(all_tiles) == Counter(TILES.keys()), "tile conservation"
    reached, pending = set(), ["0,0"]
    while pending:
        key = pending.pop()
        if key in reached:
            continue
        reached.add(key)
        tile = board[key]
        assert type(tile["x"]) is int and type(tile["y"]) is int
        assert key == _key(tile["x"], tile["y"])
        assert type(tile["rotation"]) is int and 0 <= tile["rotation"] < 4
        for edge, (dx, dy) in enumerate(DIRECTIONS):
            other_key = _key(tile["x"] + dx, tile["y"] + dy)
            if other_key in board:
                assert _geometry(tile)["edges"][edge] == _geometry(board[other_key])["edges"][(edge + 2) % 4], "edge mismatch"
                if other_key not in reached:
                    pending.append(other_key)
    assert reached == set(board), "disconnected board"
    occupied_tiles = set()
    for token in state["meeples"]:
        assert token["tile"] in board and token["tile"] not in occupied_tiles
        occupied_tiles.add(token["tile"])
        assert token["feature"] in {f["id"] for f in _geometry(board[token["tile"]])["features"]}
        assert type(token["seat"]) is int and 0 <= token["seat"] < state["player_count"]
    for seat, player in enumerate(state["players"]):
        assert player["seat"] == seat
        assert type(player["score"]) is int and player["score"] >= 0
        assert set(player["score_breakdown"]) == {"city", "road", "monastery", "field"}
        assert all(type(v) is int and v >= 0 for v in player["score_breakdown"].values())
        assert player["score"] == sum(player["score_breakdown"].values())
        assert type(player["meeples_available"]) is int and 0 <= player["meeples_available"] <= 7
        assert player["meeples_available"] + sum(t["seat"] == seat for t in state["meeples"]) == 7, "follower conservation"
    assert state["completed_turns"] == len(board) - 1 - (state["phase"] == "place_meeple")
    assert state["turn_count"] == 2 * state["completed_turns"] + (state["phase"] == "place_meeple")
    assert state["active_seat"] == state["completed_turns"] % state["player_count"]
    if len(board) == 1:
        assert state["last_placed"] is None
    else:
        assert state["last_placed"] in board and state["last_placed"] != "0,0"
    if state["status"] == "finished":
        assert state["phase"] == "finished" and not state["deck"] and not state["current_tile"] and not state["meeples"]
    else:
        assert state["phase"] in ("place_tile", "place_meeple")
        assert bool(state["current_tile"]) == (state["phase"] == "place_tile")
        if state["phase"] == "place_tile":
            assert placements(state, state["current_tile"]), "unplaceable draw"
            assert all(not c["complete"] or not c["meeples"] for c in feature_graph(state)[0])
