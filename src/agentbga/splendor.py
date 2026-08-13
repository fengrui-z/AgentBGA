"""Deterministic, JSON-serializable Splendor rules engine.

The module intentionally has no I/O.  State plus an action is sufficient to
derive the next state, which keeps replays portable and easy to audit.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from itertools import combinations, product
import hashlib
import json
import random
from typing import Any

from .game import GameRuleError

COLORS = ("white", "blue", "green", "red", "black")
# Rinascimento's source CSV uses a historical suit index order which differs
# from its cost-column order. Keep this explicit; merging the enums corrupts
# card bonuses while leaving deck sizes deceptively correct.
SOURCE_SUITS = ("black", "blue", "white", "green", "red")
TOKENS = COLORS + ("gold",)
RULES_VERSION = "classic-1.0"


class RuleError(GameRuleError):
    """A stable, user-correctable rule rejection."""


def card_catalog() -> dict[str, dict[str, Any]]:
    """Build the exact 40/30/20 research deck used by Rinascimento."""
    rows = {
        1: """
0,0,1,1,1,1,0;0,0,1,2,1,1,0;0,0,2,2,0,1,0;0,0,0,0,1,3,1;0,0,0,0,2,1,0;0,0,2,0,2,0,0;0,0,0,0,3,0,0;0,1,0,4,0,0,0
1,0,1,0,1,1,1;1,0,1,0,1,2,1;1,0,1,0,2,2,0;1,0,0,1,3,1,0;1,0,1,0,0,0,2;1,0,0,0,2,0,2;1,0,0,0,0,0,3;1,1,0,0,0,4,0
2,0,0,1,1,1,1;2,0,0,1,2,1,1;2,0,0,2,2,0,1;2,0,3,1,0,0,1;2,0,0,0,0,2,1;2,0,0,2,0,0,2;2,0,0,3,0,0,0;2,1,0,0,4,0,0
3,0,1,1,0,1,1;3,0,1,1,0,1,2;3,0,0,1,0,2,2;3,0,1,3,1,0,0;3,0,2,1,0,0,0;3,0,0,2,0,2,0;3,0,0,0,0,3,0;3,1,0,0,0,0,4
4,0,1,1,1,0,1;4,0,2,1,1,0,1;4,0,2,0,1,0,2;4,0,1,0,0,1,3;4,0,0,2,1,0,0;4,0,2,0,0,2,0;4,0,3,0,0,0,0;4,1,4,0,0,0,0
""",
        2: """
0,1,3,2,2,0,0;0,1,3,0,3,0,2;0,2,0,1,4,2,0;0,2,0,0,5,3,0;0,2,5,0,0,0,0;0,3,0,0,0,0,6
1,1,0,2,2,3,0;1,1,0,2,3,0,3;1,2,5,3,0,0,0;1,2,2,0,0,1,4;1,2,0,5,0,0,0;1,3,0,6,0,0,0
2,1,0,0,3,2,2;2,1,2,3,0,3,0;2,2,0,0,1,4,2;2,2,0,0,0,5,3;2,2,0,0,0,5,0;2,3,6,0,0,0,0
3,1,3,0,2,3,0;3,1,2,3,0,0,2;3,2,4,2,0,0,1;3,2,0,5,3,0,0;3,2,0,0,5,0,0;3,3,0,0,6,0,0
4,1,2,0,0,2,3;4,1,0,3,0,2,3;4,2,1,4,2,0,0;4,2,3,0,0,0,5;4,2,0,0,0,0,5;4,3,0,0,0,6,0
""",
        3: """
0,3,3,3,5,3,0;0,4,0,0,0,7,0;0,4,0,0,3,6,3;0,5,0,0,0,7,3
1,3,3,0,3,3,5;1,4,7,0,0,0,0;1,4,6,3,0,0,3;1,5,7,3,0,0,0
2,3,0,3,3,5,3;2,4,0,0,0,0,7;2,4,3,0,0,3,6;2,5,3,0,0,0,7
3,3,5,3,0,3,3;3,4,0,7,0,0,0;3,4,3,6,3,0,0;3,5,0,7,3,0,0
4,3,3,5,3,0,3;4,4,0,0,7,0,0;4,4,0,3,6,3,0;4,5,0,0,7,3,0
""",
    }
    cards: dict[str, dict[str, Any]] = {}
    counters = Counter()
    for tier, raw in rows.items():
        for encoded in raw.replace("\n", ";").split(";"):
            if not encoded.strip():
                continue
            suit, points, *amounts = (int(value) for value in encoded.strip().split(","))
            bonus = SOURCE_SUITS[suit]
            counters[(tier, bonus)] += 1
            number = counters[(tier, bonus)]
            card_id = f"t{tier}-{bonus}-{number}"
            cards[card_id] = {
                "id": card_id, "tier": tier, "bonus": bonus, "points": points,
                "cost": dict(zip(COLORS, amounts, strict=True)),
            }
    return cards


def noble_catalog() -> dict[str, dict[str, Any]]:
    requirements = (
        (0, 0, 3, 3, 3), (3, 3, 3, 0, 0), (3, 3, 0, 0, 3),
        (0, 3, 3, 3, 0), (3, 0, 0, 3, 3), (4, 4, 0, 0, 0),
        (0, 4, 4, 0, 0), (0, 0, 4, 4, 0), (4, 0, 0, 0, 4),
        (0, 0, 0, 4, 4),
    )
    return {
        f"noble-{index + 1}": {
            "id": f"noble-{index + 1}", "points": 3,
            "required": dict(zip(COLORS, amounts, strict=True)),
        }
        for index, amounts in enumerate(requirements)
    }


CARDS = card_catalog()
NOBLES = noble_catalog()


def describe() -> dict[str, Any]:
    return {
        "id": "splendor",
        "name": "Splendor",
        "rules_version": RULES_VERSION,
        "players": {"minimum": 2, "maximum": 4},
        "hidden_information": True,
        "implementation_status": "playable",
        "runnable": True,
        "decision_model": "one_decision_per_player_turn",
        "action_types": [
            "take_tokens", "reserve_visible", "reserve_deck",
            "buy_visible", "buy_reserved", "choose_noble", "pass",
        ],
        "colors": list(COLORS),
        "win_condition": (
            "Finish the round after a player reaches 15 prestige; highest prestige wins, "
            "then fewest purchased cards."
        ),
    }


def new_game(
    players: int, seed: int, config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if config not in (None, {}):
        raise RuleError("Splendor does not accept game setup options")
    if players not in (2, 3, 4):
        raise RuleError("Splendor requires 2, 3, or 4 players")
    rng = random.Random(seed)
    decks: dict[str, list[str]] = {}
    market: dict[str, list[str]] = {}
    for tier in (1, 2, 3):
        deck = [card_id for card_id, card in CARDS.items() if card["tier"] == tier]
        rng.shuffle(deck)
        market[str(tier)] = [deck.pop() for _ in range(4)]
        decks[str(tier)] = deck
    noble_ids = list(NOBLES)
    rng.shuffle(noble_ids)
    token_count = {2: 4, 3: 5, 4: 7}[players]
    return {
        "schema_version": "agentbga.splendor.state.v1",
        "rules_version": RULES_VERSION,
        "seed": seed,
        "player_count": players,
        "turn_count": 0,
        "active_seat": 0,
        "phase": "main",
        "pending_nobles": [],
        "status": "active",
        "end_after_turn": None,
        "bank": {**{color: token_count for color in COLORS}, "gold": 5},
        "decks": decks,
        "market": market,
        "available_nobles": noble_ids[: players + 1],
        "players": [
            {
                "seat": seat,
                "tokens": {token: 0 for token in TOKENS},
                "purchased": [],
                "reserved": [],
                "nobles": [],
            }
            for seat in range(players)
        ],
    }


def state_hash(state: dict[str, Any]) -> str:
    raw = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def bonuses(state: dict[str, Any], seat: int) -> dict[str, int]:
    result = {color: 0 for color in COLORS}
    for card_id in state["players"][seat]["purchased"]:
        result[CARDS[card_id]["bonus"]] += 1
    return result


def score(state: dict[str, Any], seat: int) -> int:
    player = state["players"][seat]
    return sum(CARDS[c]["points"] for c in player["purchased"]) + sum(
        NOBLES[n]["points"] for n in player["nobles"]
    )


def _token_total(tokens: dict[str, int]) -> int:
    return sum(tokens.values())


def _bounded_returns(tokens: dict[str, int], amount: int) -> list[dict[str, int]]:
    if amount <= 0:
        return [{}]
    results: list[dict[str, int]] = []

    def visit(index: int, remaining: int, chosen: dict[str, int]) -> None:
        if index == len(TOKENS):
            if remaining == 0:
                results.append(dict(chosen))
            return
        token = TOKENS[index]
        for count in range(min(tokens[token], remaining) + 1):
            if count:
                chosen[token] = count
            else:
                chosen.pop(token, None)
            visit(index + 1, remaining - count, chosen)
        chosen.pop(token, None)

    visit(0, amount, {})
    return results


def _post_take_returns(player_tokens: dict[str, int], gained: dict[str, int]) -> list[dict[str, int]]:
    after = {token: player_tokens[token] + gained.get(token, 0) for token in TOKENS}
    return _bounded_returns(after, max(0, _token_total(after) - 10))


def _payments(state: dict[str, Any], seat: int, card_id: str) -> list[dict[str, int]]:
    card = CARDS[card_id]
    player = state["players"][seat]
    discount = bonuses(state, seat)
    due = {color: max(0, card["cost"][color] - discount[color]) for color in COLORS}
    choices = [range(min(due[color], player["tokens"][color]) + 1) for color in COLORS]
    results: list[dict[str, int]] = []
    for amounts in product(*choices):
        gold_needed = sum(due[color] - amounts[index] for index, color in enumerate(COLORS))
        if gold_needed > player["tokens"]["gold"]:
            continue
        payment = {color: amounts[index] for index, color in enumerate(COLORS) if amounts[index]}
        if gold_needed:
            payment["gold"] = gold_needed
        results.append(payment)
    # Prefer spending colored tokens first; deterministic agents see the common
    # payment before strategically unusual gold-preserving alternatives.
    results.sort(key=lambda payment: (payment.get("gold", 0), json.dumps(payment, sort_keys=True)))
    return results


def _action_id(state: dict[str, Any], action: dict[str, Any]) -> str:
    material = json.dumps(action, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f'{state["turn_count"]}:{state["phase"]}:{material}'.encode()).hexdigest()[:12]
    return f"a-{digest}"


def legal_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    if state["status"] != "active" or seat != state["active_seat"]:
        return []
    if state["phase"] == "choose_noble":
        actions = [{"type": "choose_noble", "noble_id": noble} for noble in state["pending_nobles"]]
        return [{"id": _action_id(state, action), "action": action} for action in actions]

    player = state["players"][seat]
    actions: list[dict[str, Any]] = []
    available = [color for color in COLORS if state["bank"][color] > 0]
    # If fewer than three colors remain, the player takes one of every available
    # color. They may not voluntarily take fewer when three or more are present.
    if available:
        take_count = min(3, len(available))
        for selected in combinations(available, take_count):
            gained = dict.fromkeys(selected, 1)
            for returned in _post_take_returns(player["tokens"], gained):
                actions.append({"type": "take_tokens", "take": gained, "return": returned})
    for color in COLORS:
        if state["bank"][color] >= 4:
            gained = {color: 2}
            for returned in _post_take_returns(player["tokens"], gained):
                actions.append({"type": "take_tokens", "take": gained, "return": returned})

    if len(player["reserved"]) < 3:
        gained = {"gold": 1} if state["bank"]["gold"] else {}
        returns = _post_take_returns(player["tokens"], gained)
        for tier in (1, 2, 3):
            tier_key = str(tier)
            for card_id in state["market"][tier_key]:
                for returned in returns:
                    actions.append({
                        "type": "reserve_visible", "tier": tier, "card_id": card_id,
                        "return": returned,
                    })
            if state["decks"][tier_key]:
                for returned in returns:
                    actions.append({"type": "reserve_deck", "tier": tier, "return": returned})

    for tier in (1, 2, 3):
        for card_id in state["market"][str(tier)]:
            for payment in _payments(state, seat, card_id):
                actions.append({"type": "buy_visible", "tier": tier, "card_id": card_id, "payment": payment})
    for card_id in player["reserved"]:
        for payment in _payments(state, seat, card_id):
            actions.append({"type": "buy_reserved", "card_id": card_id, "payment": payment})

    # The printed rules omit this pathological state, but it is reachable when
    # every gem is held, a player's reserve is full, and they can buy nothing.
    # Digital implementations need a total transition function, so pass exists
    # only when no printed-rule action exists; it can never be chosen otherwise.
    if not actions:
        actions.append({"type": "pass", "reason": "no_legal_main_action"})

    return [{"id": _action_id(state, action), "action": action} for action in actions]


def _eligible_nobles(state: dict[str, Any], seat: int) -> list[str]:
    owned = bonuses(state, seat)
    return [
        noble_id for noble_id in state["available_nobles"]
        if all(owned[color] >= amount for color, amount in NOBLES[noble_id]["required"].items())
    ]


def _finish_turn(state: dict[str, Any]) -> None:
    just_played = state["active_seat"]
    if score(state, just_played) >= 15 and state["end_after_turn"] is None:
        state["end_after_turn"] = ((state["turn_count"] // state["player_count"]) + 1) * state["player_count"]
    state["turn_count"] += 1
    if state["end_after_turn"] is not None and state["turn_count"] >= state["end_after_turn"]:
        state["status"] = "finished"
        state["phase"] = "finished"
        return
    state["active_seat"] = state["turn_count"] % state["player_count"]
    state["phase"] = "main"
    state["pending_nobles"] = []


def apply_action(state: dict[str, Any], seat: int, action: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    legal = {item["id"]: item["action"] for item in legal_actions(state, seat)}
    canonical = json.dumps(action, sort_keys=True, separators=(",", ":"))
    allowed = {json.dumps(item, sort_keys=True, separators=(",", ":")): item for item in legal.values()}
    if canonical not in allowed:
        raise RuleError("action is not legal in the current state")
    action = allowed[canonical]
    next_state = deepcopy(state)
    player = next_state["players"][seat]
    kind = action["type"]
    events: list[dict[str, Any]] = [{"type": "action_accepted", "seat": seat, "action": action}]

    if kind == "choose_noble":
        noble = action["noble_id"]
        next_state["available_nobles"].remove(noble)
        player["nobles"].append(noble)
        events.append({"type": "noble_acquired", "seat": seat, "noble_id": noble})
        _finish_turn(next_state)
        return next_state, events

    if kind == "take_tokens":
        for token, count in action["take"].items():
            next_state["bank"][token] -= count
            player["tokens"][token] += count
    elif kind in ("reserve_visible", "reserve_deck"):
        tier = str(action["tier"])
        if kind == "reserve_visible":
            card_id = action["card_id"]
            next_state["market"][tier].remove(card_id)
            if next_state["decks"][tier]:
                next_state["market"][tier].append(next_state["decks"][tier].pop())
        else:
            card_id = next_state["decks"][tier].pop()
        player["reserved"].append(card_id)
        if next_state["bank"]["gold"]:
            next_state["bank"]["gold"] -= 1
            player["tokens"]["gold"] += 1
        events.append({
            "type": "card_reserved", "seat": seat,
            "card_id": card_id if kind == "reserve_visible" else None,
            "tier": int(tier), "visibility": "public" if kind == "reserve_visible" else "private",
        })
    elif kind in ("buy_visible", "buy_reserved"):
        card_id = action["card_id"]
        for token, count in action["payment"].items():
            player["tokens"][token] -= count
            next_state["bank"][token] += count
        if kind == "buy_visible":
            tier = str(action["tier"])
            next_state["market"][tier].remove(card_id)
            if next_state["decks"][tier]:
                next_state["market"][tier].append(next_state["decks"][tier].pop())
        else:
            player["reserved"].remove(card_id)
        player["purchased"].append(card_id)
        events.append({"type": "card_purchased", "seat": seat, "card_id": card_id})
    elif kind == "pass":
        events.append({"type": "turn_passed", "seat": seat, "reason": action["reason"]})
    else:  # pragma: no cover - legal action construction prevents this
        raise RuleError(f"unknown action type: {kind}")

    for token, count in action.get("return", {}).items():
        player["tokens"][token] -= count
        next_state["bank"][token] += count

    eligible = _eligible_nobles(next_state, seat)
    if len(eligible) == 1:
        noble = eligible[0]
        next_state["available_nobles"].remove(noble)
        player["nobles"].append(noble)
        events.append({"type": "noble_acquired", "seat": seat, "noble_id": noble})
        _finish_turn(next_state)
    elif len(eligible) > 1:
        next_state["phase"] = "choose_noble"
        next_state["pending_nobles"] = eligible
    else:
        _finish_turn(next_state)
    validate_state(next_state)
    return next_state, events


def rankings(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "seat": seat,
            "score": score(state, seat),
            "development_cards": len(player["purchased"]),
            "nobles": len(player["nobles"]),
        }
        for seat, player in enumerate(state["players"])
    ]
    rows.sort(key=lambda row: (-row["score"], row["development_cards"], row["seat"]))
    rank = 0
    previous: tuple[int, int] | None = None
    for index, row in enumerate(rows):
        key = (row["score"], row["development_cards"])
        if key != previous:
            rank = index + 1
            previous = key
        row["rank"] = rank
    return rows


def observe(state: dict[str, Any], seat: int) -> dict[str, Any]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    players = []
    for player in state["players"]:
        own = player["seat"] == seat
        players.append({
            "seat": player["seat"],
            "tokens": dict(player["tokens"]),
            "bonuses": bonuses(state, player["seat"]),
            "score": score(state, player["seat"]),
            "purchased_count": len(player["purchased"]),
            "purchased": [CARDS[c] for c in player["purchased"]],
            "reserved_count": len(player["reserved"]),
            "reserved": [CARDS[c] for c in player["reserved"]] if own else [
                {"hidden": True} for _ in player["reserved"]
            ],
            "nobles": [NOBLES[n] for n in player["nobles"]],
        })
    return {
        "game": "splendor",
        "rules_version": state["rules_version"],
        "viewer_seat": seat,
        "status": state["status"],
        "turn_count": state["turn_count"],
        "active_seat": state["active_seat"],
        "phase": state["phase"],
        "bank": dict(state["bank"]),
        "market": {tier: [CARDS[c] for c in cards] for tier, cards in state["market"].items()},
        "deck_counts": {tier: len(cards) for tier, cards in state["decks"].items()},
        "available_nobles": [NOBLES[n] for n in state["available_nobles"]],
        "players": players,
        "rankings": rankings(state) if state["status"] == "finished" else None,
    }


def validate_state(state: dict[str, Any]) -> None:
    for location, tokens in [("bank", state["bank"])] + [
        (f"player {p['seat']}", p["tokens"]) for p in state["players"]
    ]:
        if set(tokens) != set(TOKENS) or any(not isinstance(v, int) or v < 0 for v in tokens.values()):
            raise AssertionError(f"invalid tokens at {location}")
    expected_color = {2: 4, 3: 5, 4: 7}[state["player_count"]]
    for token in COLORS:
        actual = state["bank"][token] + sum(p["tokens"][token] for p in state["players"])
        if actual != expected_color:
            raise AssertionError(f"token conservation failed for {token}: {actual}")
    actual_gold = state["bank"]["gold"] + sum(p["tokens"]["gold"] for p in state["players"])
    if actual_gold != 5:
        raise AssertionError(f"token conservation failed for gold: {actual_gold}")
    all_cards: list[str] = []
    for values in state["decks"].values():
        all_cards.extend(values)
    for values in state["market"].values():
        all_cards.extend(values)
    for player in state["players"]:
        all_cards.extend(player["reserved"])
        all_cards.extend(player["purchased"])
        if len(player["reserved"]) > 3 or _token_total(player["tokens"]) > 10:
            raise AssertionError("player limit exceeded")
    if len(all_cards) != len(CARDS) or len(set(all_cards)) != len(CARDS):
        raise AssertionError("development card conservation failed")
    all_nobles = list(state["available_nobles"])
    for player in state["players"]:
        all_nobles.extend(player["nobles"])
    if len(all_nobles) != state["player_count"] + 1 or len(set(all_nobles)) != len(all_nobles):
        raise AssertionError("noble conservation failed")
