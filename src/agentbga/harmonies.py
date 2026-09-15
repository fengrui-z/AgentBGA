"""Deterministic Harmonies base game, with optional Nature's Spirits.

Independent rules implementation. Card geometry/numbers are converted from the
Apache-2.0 harmonies-bot catalog; see THIRD_PARTY_NOTICES.md for provenance.
Stacks are bottom-to-top. Coordinates are flat-top axial hexes.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import random
from typing import Any

from .game import GameRuleError
from .mechanics import ActionSpace, action_accepted, assign_competition_ranks, domain_event, state_digest
from .mechanics.topology import axial_hex_neighbors, shortest_distances

RULES_VERSION = "libellud-2024-base-1.0"
SCHEMA_VERSION = "agentbga.harmonies.state.v1"
TOKEN_COUNTS = {"blue": 23, "gray": 23, "brown": 21, "green": 19, "yellow": 19, "red": 15}
COLORS = tuple(TOKEN_COUNTS)
CARDS = {card["id"]: card for card in json.loads(
    (Path(__file__).parent / "data" / "harmonies-cards.json").read_text(encoding="utf-8")
)}
CELLS = tuple((q, row - q // 2) for q in range(5) for row in range(5 - q % 2))
CELL_INDEX = {cell: index for index, cell in enumerate(CELLS)}
NEIGHBORS = {
    index: sorted(CELL_INDEX[c] for c in axial_hex_neighbors(cell) if c in CELL_INDEX)
    for index, cell in enumerate(CELLS)
}
SPIRIT_RULES = {
    "h33": "Each yellow group: 10 points at size 3+, otherwise 2.",
    "h34": "5 points per yellow group, including singletons.",
    "h35": "4 points per tree of height 2 or 3.",
    "h36": "Each tree: 3 points at height 1 or 2, otherwise 1.",
    "h37": "4 points per connected group of buildings, including singletons.",
    "h38": "6 points per connected group of at least 2 buildings (corrected printing).",
    "h39": "4 points per mountain of height 2 or 3, including isolated mountains.",
    "h40": "Each mountain: 3 points at height 1 or 2, otherwise 1, including isolated mountains.",
    "h41": "7 points per connected group of at least 2 water tokens.",
    "h42": "2 points per water token.",
}
RULES = {
    "turn": "Take one token group and place every token, in any order. You may take one animal card and settle animals before, between, or after placements. End turn explicitly.",
    "stacking": "Any color on empty. Gray on 1/2 gray; brown on 1 brown; green on 1/2 brown; red on exactly 1 red/brown/gray. No other stacking. Cubes lock their cell.",
    "habitat": "Match exact stacks under one of six rotations, never reflection. Buildings require two tokens, with red on red/brown/gray. Only the marked target must be cube-free. Other habitat cells may be shared; cubes stay even if the supporting habitat changes.",
    "cards": "At most 4 incomplete cards including your spirit; completed cards free a slot. Animal points are the highest uncovered value, not the sum. Unstarted cards score zero.",
    "scoring": "Trees 1/3/7 by height; mountains 1/3/7 only beside another mountain; each yellow group size 2+ scores 5; each 2-high building beside 3+ distinct top colors scores 5. Bare brown and single red score zero.",
    "water": "A: longest shortest path within water, counting endpoints: 0/2/5/8/11/15 for lengths 1–6, then +4 per extra token. B: 5 per connected non-water region, including empty cells.",
    "end": "Trigger at turn end with 2 or fewer empty cells or insufficient bag tokens to refill. Finish the current round so all players have equal turns. Highest score, then most animal cubes (excluding spirits); remaining ties share victory.",
    "solo": "Three token groups and three market cards. Discard the other six tokens at turn end and refill all groups. If no card was taken, optionally replace one market card at turn end.",
}


class RuleError(GameRuleError):
    """A user-correctable illegal Harmonies decision."""


def describe() -> dict[str, Any]:
    return {
        "id": "harmonies", "name": "Harmonies · 自然和弦", "rules_version": RULES_VERSION,
        "players": {"minimum": 1, "maximum": 4}, "runnable": True,
        "hidden_information": True, "implementation_status": "playable_beta",
        "decision_model": "interleaved_turn_steps", "default_max_turns": 1200,
        "action_types": ["choose_spirit", "take_tokens", "place_token", "take_animal", "place_animal", "end_turn"],
        "setup_options": {"board_side": ["A", "B"], "nature_spirits": [False, True]},
        "content_scope": "32 numbered animal cards, 10 optional Nature's Spirits, both boards and solo rules. No expansions or publisher artwork. Card data is community-transcribed; not publisher certified.",
        "rules_sources": ["https://cdn.svc.asmodee.net/production-libellud/uploads/2024/12/HARMONIES_Rules_EN.pdf"],
        "win_condition": "Highest landscape + animal + spirit score; ties use animal cube count, then shared victory.",
    }


def new_game(players: int, seed: int, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = {} if config is None else config
    if type(players) is not int or not 1 <= players <= 4:
        raise RuleError("Harmonies requires 1 to 4 players")
    if not isinstance(config, dict) or set(config) - {"board_side", "nature_spirits"}:
        raise RuleError("supported setup options: board_side, nature_spirits")
    side, spirits = config.get("board_side", "A"), config.get("nature_spirits", False)
    if side not in ("A", "B") or type(spirits) is not bool or type(seed) is not int:
        raise RuleError("board_side must be A/B, nature_spirits a boolean, seed an integer")
    rng = random.Random(seed)
    bag = [color for color, count in TOKEN_COUNTS.items() for _ in range(count)]
    deck = [key for key, card in CARDS.items() if not card["spirit"]]
    spirit_deck = [key for key, card in CARDS.items() if card["spirit"]]
    rng.shuffle(bag)
    rng.shuffle(deck)
    rng.shuffle(spirit_deck)
    size = 3 if players == 1 else 5
    state = {
        "schema_version": SCHEMA_VERSION, "rules_version": RULES_VERSION,
        "seed": seed, "player_count": players, "board_side": side, "nature_spirits": spirits,
        "status": "active", "phase": "turn", "active_seat": 0, "round": 1,
        "turn_count": 0, "completed_turns": 0, "final_round": None,
        "end_reason": None, "bag": bag, "discarded_tokens": [], "deck": deck,
        "spirit_deck": spirit_deck, "discarded_cards": [],
        "token_groups": [[bag.pop() for _ in range(3)] for _ in range(size)],
        "market": [deck.pop() for _ in range(size)],
        "pending_tokens": [], "taken_group": None, "took_card": False,
        "players": [{
            "seat": seat, "board": [[] for _ in CELLS], "cubes": [None for _ in CELLS],
            "cards": [], "spirit_choices": [spirit_deck.pop() for _ in range(2)] if spirits else [],
            "turns": 0, "score": 0,
        } for seat in range(players)],
    }
    _update_scores(state)
    validate_state(state)
    return state


def state_hash(state: dict[str, Any]) -> str:
    return state_digest(state)


def can_stack(stack: list[str], color: str, cube: str | None = None) -> bool:
    if cube is not None or color not in COLORS:
        return False
    if not stack:
        return True
    if color == "gray":
        return stack in (["gray"], ["gray", "gray"])
    if color == "brown":
        return stack == ["brown"]
    if color == "green":
        return stack in (["brown"], ["brown", "brown"])
    if color == "red":
        return stack in (["gray"], ["brown"], ["red"])
    return False


def _rotate(q: int, r: int, rotation: int) -> tuple[int, int]:
    for _ in range(rotation):
        q, r = -r, q + r
    return q, r


@lru_cache(maxsize=None)
def pattern_placements(card_id: str) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """All in-bounds orientations, with the marked cube cell first. No reflection."""
    pattern = CARDS[card_id]["pattern"]
    target = next(i for i, step in enumerate(pattern) if step["animal"])
    found = set()
    for rotation in range(6):
        offsets = [_rotate(step["q"], step["r"], rotation) for step in pattern]
        for q, r in CELLS:
            coords = [(q + dq, r + dr) for dq, dr in offsets]
            if all(coord in CELL_INDEX for coord in coords):
                cells = tuple(CELL_INDEX[coord] for coord in coords)
                found.add((cells[target], cells))
    return tuple(sorted(found))


def _matches(stack: list[str], required: list[str]) -> bool:
    if required == ["base", "red"]:
        return len(stack) == 2 and stack[1] == "red" and stack[0] in ("red", "brown", "gray")
    return stack == required


def animal_targets(player: dict[str, Any], card_id: str) -> list[int]:
    pattern = CARDS[card_id]["pattern"]
    return sorted({target for target, cells in pattern_placements(card_id)
                   if player["cubes"][target] is None and all(
                       _matches(player["board"][cell], step["stack"])
                       for cell, step in zip(cells, pattern)
                   )})


def _incomplete(player: dict[str, Any]) -> int:
    return sum(card["placed"] < len(CARDS[card["id"]]["points"]) for card in player["cards"])


def _check_seat(state: dict[str, Any], seat: int) -> None:
    if type(seat) is not int or not 0 <= seat < state["player_count"]:
        raise RuleError("seat is out of range")


def legal_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    _check_seat(state, seat)
    if state["status"] != "active" or seat != state["active_seat"]:
        return []
    player = state["players"][seat]
    actions = []
    if player["spirit_choices"]:
        actions = [{"type": "choose_spirit", "card_id": key} for key in player["spirit_choices"]]
    else:
        if state["taken_group"] is None:
            actions.extend({"type": "take_tokens", "group": i}
                           for i, group in enumerate(state["token_groups"]) if group)
        for color in COLORS:
            if color in state["pending_tokens"]:
                actions.extend({"type": "place_token", "color": color, "cell": cell}
                               for cell, stack in enumerate(player["board"])
                               if can_stack(stack, color, player["cubes"][cell]))
        if not state["took_card"] and _incomplete(player) < 4:
            actions.extend({"type": "take_animal", "card_id": key} for key in state["market"])
        for card in player["cards"]:
            if card["placed"] < len(CARDS[card["id"]]["points"]):
                actions.extend({"type": "place_animal", "card_id": card["id"], "cell": target}
                               for target in animal_targets(player, card["id"]))
        if state["taken_group"] is not None and not state["pending_tokens"]:
            actions.append({"type": "end_turn"})
            if state["player_count"] == 1 and not state["took_card"] and state["deck"]:
                actions.extend({"type": "end_turn", "discard_card": key} for key in state["market"])
    return ActionSpace.from_actions(state["phase"], state["turn_count"], actions, prefix="harmonies").wrapped()


def _groups(cells: set[int]) -> list[set[int]]:
    remaining = set(cells)
    groups = []
    while remaining:
        group = {min(remaining)}
        queue = list(group)
        remaining.difference_update(group)
        while queue:
            for neighbor in NEIGHBORS[queue.pop()]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    group.add(neighbor)
                    queue.append(neighbor)
        groups.append(group)
    return groups


def _spirit_score(card_id: str, board: list[list[str]], features: dict[str, set[int]]) -> int:
    trees, mountains = features["green"], features["gray"]
    if card_id == "h33":
        return sum(10 if len(g) >= 3 else 2 for g in _groups(features["yellow"]))
    if card_id == "h34":
        return 5 * len(_groups(features["yellow"]))
    if card_id in ("h35", "h39"):
        return 4 * sum(len(board[i]) >= 2 for i in (trees if card_id == "h35" else mountains))
    if card_id in ("h36", "h40"):
        return sum(3 if len(board[i]) <= 2 else 1 for i in (trees if card_id == "h36" else mountains))
    if card_id == "h37":
        return 4 * len(_groups(features["building"]))
    if card_id == "h38":
        return 6 * sum(len(g) >= 2 for g in _groups(features["building"]))
    if card_id == "h41":
        return 7 * sum(len(g) >= 2 for g in _groups(features["blue"]))
    if card_id == "h42":
        return 2 * len(features["blue"])
    return 0


def score_breakdown(player: dict[str, Any], board_side: str) -> dict[str, int]:
    board = player["board"]
    features = {color: {i for i, stack in enumerate(board) if stack and stack[-1] == color} for color in COLORS}
    features["building"] = {i for i in features["red"] if len(board[i]) == 2}
    water = features["blue"]
    adjacency = {i: [j for j in NEIGHBORS[i] if j in water] for i in water}
    river_length = max((max(shortest_distances([i], adjacency).values()) + 1 for i in water), default=0)
    result = {
        "trees": sum((0, 1, 3, 7)[len(board[i])] for i in features["green"]),
        "mountains": sum((0, 1, 3, 7)[len(board[i])] for i in features["gray"] if set(NEIGHBORS[i]) & features["gray"]),
        "fields": 5 * sum(len(g) >= 2 for g in _groups(features["yellow"])),
        "buildings": 5 * sum(len({board[j][-1] for j in NEIGHBORS[i] if board[j]}) >= 3 for i in features["building"]),
        "water": ((0, 0, 2, 5, 8, 11, 15)[min(6, river_length)] + 4 * max(0, river_length - 6)
                  if board_side == "A" else 5 * len(_groups(set(range(len(CELLS))) - water))),
        "animals": 0, "spirits": 0,
    }
    for card in player["cards"]:
        if card["placed"]:
            if CARDS[card["id"]]["spirit"]:
                result["spirits"] += _spirit_score(card["id"], board, features)
            else:
                result["animals"] += CARDS[card["id"]]["points"][card["placed"] - 1]
    result["total"] = sum(result.values())
    return result


def _update_scores(state: dict[str, Any]) -> None:
    for player in state["players"]:
        player["score"] = score_breakdown(player, state["board_side"])["total"]


def rankings(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [{"seat": p["seat"], "score": p["score"],
             "animal_cubes": sum(c is not None and not CARDS[c]["spirit"] for c in p["cubes"]),
             "score_breakdown": score_breakdown(p, state["board_side"])} for p in state["players"]]
    return assign_competition_ranks(rows,
        sort_key=lambda row: (-row["score"], -row["animal_cubes"], row["seat"]),
        tie_key=lambda row: (row["score"], row["animal_cubes"]))


def solo_suns(state: dict[str, Any]) -> int | None:
    if state["player_count"] != 1:
        return None
    player = state["players"][0]
    suns = sum(player["score"] >= threshold for threshold in (40, 70, 90, 110, 130, 140, 150, 160))
    suns += state["board_side"] == "A"
    spirit = next((c["id"] for c in player["cards"] if CARDS[c["id"]]["spirit"]), None)
    # Official score aid: no spirit +2; group-scoring spirit +1; individual +0.
    suns += 2 if not state["nature_spirits"] else int(spirit in ("h33", "h34", "h37", "h38", "h41"))
    return suns


def _end_turn(state: dict[str, Any], action: dict[str, Any], events: list[dict[str, Any]]) -> None:
    player = state["players"][state["active_seat"]]
    player["turns"] += 1
    state["completed_turns"] += 1
    if sum(not stack for stack in player["board"]) <= 2 and state["final_round"] is None:
        state["final_round"], state["end_reason"] = state["round"], "board_full"
    if state["player_count"] == 1:
        for group in state["token_groups"]:
            state["discarded_tokens"].extend(group)
            group.clear()
    for group in state["token_groups"]:
        while len(group) < 3:
            if not state["bag"]:
                if state["final_round"] is None:
                    state["final_round"], state["end_reason"] = state["round"], "bag_empty"
                break
            group.append(state["bag"].pop())
    if "discard_card" in action:
        state["market"].remove(action["discard_card"])
        state["discarded_cards"].append(action["discard_card"])
    market_size = 3 if state["player_count"] == 1 else 5
    while len(state["market"]) < market_size and state["deck"]:
        state["market"].append(state["deck"].pop())
    events.append(domain_event("harmonies_turn_ended", seat=player["seat"], round=state["round"],
                               score_breakdown=score_breakdown(player, state["board_side"])))
    state["taken_group"], state["took_card"] = None, False
    if state["active_seat"] == state["player_count"] - 1:
        if state["final_round"] is not None:
            state["status"] = state["phase"] = "finished"
            events.append(domain_event("match_finished", rankings=rankings(state), reason=state["end_reason"]))
            return
        state["round"] += 1
    state["active_seat"] = (state["active_seat"] + 1) % state["player_count"]


def apply_action(state: dict[str, Any], seat: int, action: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    space = ActionSpace.from_actions(state["phase"], state["turn_count"],
                                     [item["action"] for item in legal_actions(state, seat)], prefix="harmonies")
    canonical = space.require(action, error_factory=RuleError)
    result = deepcopy(state)
    player = result["players"][seat]
    events = [action_accepted(seat, canonical)]
    kind = canonical["type"]
    if kind == "choose_spirit":
        key = canonical["card_id"]
        player["cards"].append({"id": key, "placed": 0})
        result["discarded_cards"].extend(c for c in player["spirit_choices"] if c != key)
        player["spirit_choices"] = []
    elif kind == "take_tokens":
        group = canonical["group"]
        result["pending_tokens"] = result["token_groups"][group]
        result["token_groups"][group] = []
        result["taken_group"] = group
    elif kind == "place_token":
        result["pending_tokens"].remove(canonical["color"])
        player["board"][canonical["cell"]].append(canonical["color"])
    elif kind == "take_animal":
        key = canonical["card_id"]
        result["market"].remove(key)
        player["cards"].append({"id": key, "placed": 0})
        result["took_card"] = True
    elif kind == "place_animal":
        key = canonical["card_id"]
        player["cubes"][canonical["cell"]] = key
        next(card for card in player["cards"] if card["id"] == key)["placed"] += 1
    _update_scores(result)
    result["turn_count"] += 1
    if kind == "end_turn":
        _end_turn(result, canonical, events)
    else:
        events.append(domain_event(f"harmonies_{kind}", seat=seat, **{k: v for k, v in canonical.items() if k != "type"}))
    validate_state(result)
    return result, events


def card_view(card_id: str, placed: int = 0) -> dict[str, Any]:
    card = deepcopy(CARDS[card_id])
    card.update({"placed": placed, "remaining": len(card["points"]) - placed,
                 "complete": placed == len(card["points"]),
                 "name": f"{'Spirit' if card['spirit'] else 'Animal'} {card['number']:02d}"})
    if card["spirit"]:
        card["scoring_rule"] = SPIRIT_RULES[card_id]
    return card


def observe(state: dict[str, Any], seat: int) -> dict[str, Any]:
    _check_seat(state, seat)
    players = []
    for player in state["players"]:
        players.append({
            "seat": player["seat"], "score": player["score"], "turns": player["turns"],
            "score_breakdown": score_breakdown(player, state["board_side"]),
            "empty_spaces": sum(not stack for stack in player["board"]),
            "active_cards": _incomplete(player),
            "cells": [{"id": i, "q": q, "r": r, "stack": list(player["board"][i]), "cube": player["cubes"][i]} for i, (q, r) in enumerate(CELLS)],
            "cards": [card_view(c["id"], c["placed"]) for c in player["cards"]],
            "spirit_choices": [card_view(key) for key in player["spirit_choices"]] if player["seat"] == seat else [],
        })
    return {
        "game": "harmonies", "rules_version": RULES_VERSION, "viewer_seat": seat,
        **{key: state[key] for key in ("status", "phase", "active_seat", "turn_count", "completed_turns", "round", "board_side", "nature_spirits", "final_round", "end_reason", "taken_group", "took_card")},
        "token_groups": deepcopy(state["token_groups"]), "pending_tokens": list(state["pending_tokens"]),
        "bag_count": len(state["bag"]), "deck_count": len(state["deck"]),
        "market": [card_view(key) for key in state["market"]], "players": players,
        "rules": dict(RULES), "rankings": rankings(state) if state["status"] == "finished" else None,
        "solo_suns": solo_suns(state),
    }


def validate_state(state: dict[str, Any]) -> None:
    if state.get("schema_version") != SCHEMA_VERSION or state.get("rules_version") != RULES_VERSION:
        raise AssertionError("invalid Harmonies version")
    count = state.get("player_count")
    if type(count) is not int or not 1 <= count <= 4 or len(state["players"]) != count:
        raise AssertionError("invalid player count")
    if state["board_side"] not in ("A", "B") or type(state["nature_spirits"]) is not bool:
        raise AssertionError("invalid setup options")
    if state["status"] not in ("active", "finished") or state["phase"] != ("turn" if state["status"] == "active" else "finished"):
        raise AssertionError("invalid phase")
    if type(state["active_seat"]) is not int or not 0 <= state["active_seat"] < count:
        raise AssertionError("invalid active seat")
    if any(type(state[key]) is not int or state[key] < 0 for key in ("turn_count", "completed_turns")):
        raise AssertionError("invalid counters")
    size = 3 if count == 1 else 5
    if len(state["token_groups"]) != size or any(len(g) > 3 for g in state["token_groups"]):
        raise AssertionError("invalid token market")
    if len(state["market"]) > size or len(state["pending_tokens"]) > 3:
        raise AssertionError("invalid market or pending tokens")
    taken = state["taken_group"]
    if taken is None:
        if state["pending_tokens"]:
            raise AssertionError("pending tokens require a taken group")
    elif type(taken) is not int or not 0 <= taken < size or state["token_groups"][taken]:
        raise AssertionError("invalid taken group")
    tokens = state["bag"] + state["discarded_tokens"] + state["pending_tokens"]
    for group in state["token_groups"]:
        tokens += group
    cards = state["deck"] + state["market"] + state["spirit_deck"] + state["discarded_cards"]
    for seat, player in enumerate(state["players"]):
        if player["seat"] != seat or len(player["board"]) != len(CELLS) or len(player["cubes"]) != len(CELLS):
            raise AssertionError("invalid personal board")
        owned = {card["id"] for card in player["cards"]}
        if not owned <= CARDS.keys() or _incomplete(player) > 4:
            raise AssertionError("invalid animal cards")
        for stack, cube in zip(player["board"], player["cubes"]):
            if any(not can_stack(stack[:i], color) for i, color in enumerate(stack)):
                raise AssertionError("invalid token stack")
            if cube is not None and (not stack or cube not in owned):
                raise AssertionError("invalid animal cube")
            tokens += stack
        cube_counts = Counter(c for c in player["cubes"] if c is not None)
        for card in player["cards"]:
            if type(card["placed"]) is not int or not 0 <= card["placed"] <= len(CARDS[card["id"]]["points"]) or cube_counts[card["id"]] != card["placed"]:
                raise AssertionError("animal cube conservation failed")
            # Habitat support may have changed since placement; the target never can.
            target = next(s["stack"] for s in CARDS[card["id"]]["pattern"] if s["animal"])
            if any(not _matches(player["board"][i], target) for i, cube in enumerate(player["cubes"]) if cube == card["id"]):
                raise AssertionError("animal target stack changed")
        if player["score"] != score_breakdown(player, state["board_side"])["total"]:
            raise AssertionError("cached score mismatch")
        cards += [card["id"] for card in player["cards"]] + player["spirit_choices"]
    if Counter(tokens) != Counter(TOKEN_COUNTS):
        raise AssertionError("landscape token conservation failed")
    if Counter(cards) != Counter(CARDS.keys()):
        raise AssertionError("card conservation failed")
    if sum(p["turns"] for p in state["players"]) != state["completed_turns"]:
        raise AssertionError("completed turn count mismatch")
    if state["status"] == "finished" and (state["final_round"] is None or len({p["turns"] for p in state["players"]}) != 1):
        raise AssertionError("game must finish after equal turns")
