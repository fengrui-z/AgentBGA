"""Deterministic Century: Spice Road base-game rules engine.

The implementation models the published 2017 base-game card values and rules,
but deliberately contains no publisher artwork or card scans.
"""

from __future__ import annotations

from copy import deepcopy
from itertools import product
import random
from typing import Any

from .game import GameRuleError
from .mechanics import (
    ActionSpace,
    action_accepted,
    assign_competition_ranks,
    state_digest,
    validate_resource_pool,
)


RULES_VERSION = "plan-b-2017-base-1.0"
SPICES = ("turmeric", "saffron", "cardamom", "cinnamon")
CARAVAN_LIMIT = 10
MARKET_SIZE = 6
POINT_MARKET_SIZE = 5


class RuleError(GameRuleError):
    """A stable, user-correctable rules rejection."""


def _pool(values: tuple[int, int, int, int] = (0, 0, 0, 0)) -> dict[str, int]:
    return dict(zip(SPICES, values, strict=True))


# kind, upgrades, input spices, output spices. The first two are shared
# starting abilities; the remaining 43 form the shuffled merchant deck.
_MERCHANT_DATA = (
    ("gain", 0, (0, 0, 0, 0), (2, 0, 0, 0)),
    ("upgrade", 2, (0, 0, 0, 0), (0, 0, 0, 0)),
    ("trade", 0, (3, 0, 0, 0), (0, 0, 0, 1)),
    ("trade", 0, (0, 1, 0, 0), (3, 0, 0, 0)),
    ("gain", 0, (0, 0, 0, 0), (1, 1, 0, 0)),
    ("gain", 0, (0, 0, 0, 0), (0, 0, 1, 0)),
    ("gain", 0, (0, 0, 0, 0), (3, 0, 0, 0)),
    ("upgrade", 3, (0, 0, 0, 0), (0, 0, 0, 0)),
    ("trade", 0, (0, 0, 2, 0), (2, 3, 0, 0)),
    ("trade", 0, (0, 0, 2, 0), (2, 1, 0, 1)),
    ("trade", 0, (0, 0, 0, 1), (3, 0, 1, 0)),
    ("trade", 0, (0, 2, 0, 0), (3, 0, 1, 0)),
    ("trade", 0, (0, 3, 0, 0), (2, 0, 2, 0)),
    ("trade", 0, (0, 0, 0, 1), (2, 2, 0, 0)),
    ("trade", 0, (4, 0, 0, 0), (0, 0, 2, 0)),
    ("gain", 0, (0, 0, 0, 0), (2, 1, 0, 0)),
    ("gain", 0, (0, 0, 0, 0), (4, 0, 0, 0)),
    ("gain", 0, (0, 0, 0, 0), (0, 0, 0, 1)),
    ("gain", 0, (0, 0, 0, 0), (0, 2, 0, 0)),
    ("gain", 0, (0, 0, 0, 0), (1, 0, 1, 0)),
    ("trade", 0, (2, 0, 0, 0), (0, 0, 1, 0)),
    ("trade", 0, (1, 1, 0, 0), (0, 0, 0, 1)),
    ("trade", 0, (0, 0, 1, 0), (0, 2, 0, 0)),
    ("trade", 0, (0, 2, 0, 0), (2, 0, 0, 1)),
    ("trade", 0, (3, 0, 0, 0), (0, 1, 1, 0)),
    ("trade", 0, (0, 0, 2, 0), (0, 2, 0, 1)),
    ("trade", 0, (0, 3, 0, 0), (1, 0, 1, 1)),
    ("trade", 0, (0, 0, 0, 1), (0, 3, 0, 0)),
    ("trade", 0, (0, 3, 0, 0), (0, 0, 0, 2)),
    ("trade", 0, (0, 0, 0, 1), (1, 1, 1, 0)),
    ("trade", 0, (0, 0, 1, 0), (1, 2, 0, 0)),
    ("trade", 0, (0, 0, 1, 0), (4, 1, 0, 0)),
    ("trade", 0, (5, 0, 0, 0), (0, 0, 0, 2)),
    ("trade", 0, (4, 0, 0, 0), (0, 0, 1, 1)),
    ("trade", 0, (0, 0, 0, 2), (0, 3, 2, 0)),
    ("trade", 0, (0, 0, 0, 2), (1, 1, 3, 0)),
    ("trade", 0, (5, 0, 0, 0), (0, 0, 3, 0)),
    ("trade", 0, (2, 0, 1, 0), (0, 0, 0, 2)),
    ("trade", 0, (0, 0, 3, 0), (0, 0, 0, 3)),
    ("trade", 0, (0, 3, 0, 0), (0, 0, 3, 0)),
    ("trade", 0, (3, 0, 0, 0), (0, 3, 0, 0)),
    ("trade", 0, (2, 0, 0, 0), (0, 2, 0, 0)),
    ("trade", 0, (0, 0, 2, 0), (0, 0, 0, 2)),
    ("trade", 0, (0, 2, 0, 0), (0, 0, 2, 0)),
    ("trade", 0, (0, 0, 0, 1), (0, 0, 2, 0)),
)


# points, turmeric, saffron, cardamom, cinnamon
_POINT_DATA = (
    (6, 2, 2, 0, 0), (7, 3, 2, 0, 0), (8, 0, 4, 0, 0),
    (8, 2, 0, 2, 0), (8, 2, 3, 0, 0), (9, 3, 0, 2, 0),
    (10, 0, 2, 2, 0), (10, 0, 5, 0, 0), (10, 2, 0, 0, 2),
    (11, 2, 0, 3, 0), (11, 3, 0, 0, 2), (12, 0, 0, 4, 0),
    (12, 0, 2, 0, 2), (12, 0, 3, 2, 0), (13, 0, 2, 3, 0),
    (14, 0, 0, 2, 2), (14, 0, 3, 0, 2), (14, 2, 0, 0, 3),
    (15, 0, 0, 5, 0), (16, 0, 0, 0, 4), (16, 0, 2, 0, 3),
    (17, 0, 0, 3, 2), (18, 0, 0, 2, 3), (20, 0, 0, 0, 5),
    (9, 2, 1, 0, 1), (12, 0, 2, 1, 1), (12, 1, 0, 2, 1),
    (13, 2, 2, 2, 0), (15, 2, 2, 0, 2), (17, 2, 0, 2, 2),
    (19, 0, 2, 2, 2), (12, 1, 1, 1, 1), (14, 3, 1, 1, 1),
    (16, 1, 3, 1, 1), (18, 1, 1, 3, 1), (20, 1, 1, 1, 3),
)


def merchant_catalog() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, (kind, upgrades, inputs, outputs) in enumerate(_MERCHANT_DATA):
        card_id = ("start-gain" if index == 0 else "start-upgrade" if index == 1
                   else f"merchant-{index - 1:02d}")
        result[card_id] = {
            "id": card_id,
            "kind": kind,
            "upgrades": upgrades,
            "input": _pool(inputs),
            "output": _pool(outputs),
        }
    return result


def point_catalog() -> dict[str, dict[str, Any]]:
    return {
        f"point-{index + 1:02d}": {
            "id": f"point-{index + 1:02d}",
            "points": row[0],
            "cost": _pool(row[1:]),
        }
        for index, row in enumerate(_POINT_DATA)
    }


MERCHANTS = merchant_catalog()
POINT_CARDS = point_catalog()


def describe() -> dict[str, Any]:
    return {
        "id": "century_spice_road",
        "name": "Century: Spice Road",
        "rules_version": RULES_VERSION,
        "players": {"minimum": 2, "maximum": 5},
        "hidden_information": False,
        "implementation_status": "playable",
        "runnable": True,
        "decision_model": "one_structured_decision_per_player_turn",
        "default_max_turns": 3000,
        "action_types": ["play_merchant", "acquire_merchant", "claim_point", "rest"],
        "spices": list(SPICES),
        "win_condition": (
            "Trigger the final round with a sixth point card at 2-3 players or a fifth "
            "at 4-5 players; score point cards, coins, and non-turmeric spices."
        ),
    }


def new_game(
    players: int, seed: int, config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if config not in (None, {}):
        raise RuleError("Century: Spice Road does not accept game setup options")
    if players < 2 or players > 5:
        raise RuleError("Century: Spice Road requires 2 to 5 players")
    rng = random.Random(seed)
    merchant_deck = [card_id for card_id in MERCHANTS if card_id.startswith("merchant-")]
    point_deck = list(POINT_CARDS)
    rng.shuffle(merchant_deck)
    rng.shuffle(point_deck)
    merchant_market = [
        {"card_id": merchant_deck.pop(), "spices": _pool()} for _ in range(MARKET_SIZE)
    ]
    point_market = [point_deck.pop() for _ in range(POINT_MARKET_SIZE)]
    starts = ((3, 0, 0, 0), (4, 0, 0, 0), (4, 0, 0, 0),
              (3, 1, 0, 0), (3, 1, 0, 0))
    state = {
        "schema_version": "agentbga.century_spice_road.state.v1",
        "rules_version": RULES_VERSION,
        "seed": seed,
        "player_count": players,
        "turn_count": 0,
        "active_seat": 0,
        "phase": "main",
        "status": "active",
        "end_after_turn": None,
        "merchant_deck": merchant_deck,
        "merchant_market": merchant_market,
        "point_deck": point_deck,
        "point_market": point_market,
        "coins": {"gold": 2 * players, "silver": 2 * players, "silver_position": 1},
        "players": [
            {
                "seat": seat,
                "spices": _pool(starts[seat]),
                "hand": ["start-gain", "start-upgrade"],
                "played": [],
                "point_cards": [],
                "coins": {"gold": 0, "silver": 0},
            }
            for seat in range(players)
        ],
    }
    validate_state(state)
    return state


def state_hash(state: dict[str, Any]) -> str:
    return state_digest(state)


def _action_space(state: dict[str, Any], actions: list[dict[str, Any]]) -> ActionSpace:
    unique = {state_digest(action): action for action in actions}
    ordered = [unique[key] for key in sorted(unique)]
    return ActionSpace.from_actions(state["phase"], state["turn_count"], ordered)


def _discard_options(spices: dict[str, int], amount: int) -> list[dict[str, int]]:
    if amount == 0:
        return [{}]
    results: list[dict[str, int]] = []

    def visit(index: int, remaining: int, chosen: dict[str, int]) -> None:
        if index == len(SPICES):
            if remaining == 0:
                results.append(dict(chosen))
            return
        spice = SPICES[index]
        for count in range(min(spices[spice], remaining) + 1):
            if count:
                chosen[spice] = count
            else:
                chosen.pop(spice, None)
            visit(index + 1, remaining - count, chosen)
        chosen.pop(spice, None)

    visit(0, amount, {})
    return results


def _payment_sequences(spices: dict[str, int], length: int) -> list[list[str]]:
    if length == 0:
        return [[]]
    results: list[list[str]] = []

    def visit(pool: dict[str, int], chosen: list[str]) -> None:
        if len(chosen) == length:
            results.append(list(chosen))
            return
        for spice in SPICES:
            if pool[spice] <= 0:
                continue
            pool[spice] -= 1
            chosen.append(spice)
            visit(pool, chosen)
            chosen.pop()
            pool[spice] += 1

    visit(dict(spices), [])
    return results


def _upgrade_sequences(spices: dict[str, int], limit: int) -> list[list[str]]:
    outcomes: dict[tuple[int, int, int, int], list[str]] = {
        tuple(spices[name] for name in SPICES): []
    }

    def visit(pool: dict[str, int], chosen: list[str]) -> None:
        if len(chosen) == limit:
            return
        for index, spice in enumerate(SPICES[:-1]):
            if pool[spice] <= 0:
                continue
            target = SPICES[index + 1]
            pool[spice] -= 1
            pool[target] += 1
            chosen.append(spice)
            key = tuple(pool[name] for name in SPICES)
            candidate = list(chosen)
            if key not in outcomes or tuple(candidate) < tuple(outcomes[key]):
                outcomes[key] = candidate
            visit(pool, chosen)
            chosen.pop()
            pool[target] -= 1
            pool[spice] += 1

    visit(dict(spices), [])
    return sorted(outcomes.values(), key=lambda item: (len(item), item))


def _after_discard_actions(
    base: dict[str, Any], resulting: dict[str, int],
) -> list[dict[str, Any]]:
    overflow = max(0, sum(resulting.values()) - CARAVAN_LIMIT)
    return [{**base, "discard": discard} for discard in _discard_options(resulting, overflow)]


def legal_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    if state["status"] != "active" or seat != state["active_seat"]:
        return []
    player = state["players"][seat]
    actions: list[dict[str, Any]] = []

    for card_id in player["hand"]:
        card = MERCHANTS[card_id]
        spices = dict(player["spices"])
        if card["kind"] == "gain":
            resulting = {name: spices[name] + card["output"][name] for name in SPICES}
            actions.extend(_after_discard_actions(
                {"type": "play_merchant", "card_id": card_id}, resulting,
            ))
        elif card["kind"] == "upgrade":
            for upgrades in _upgrade_sequences(spices, card["upgrades"]):
                actions.append({
                    "type": "play_merchant", "card_id": card_id, "upgrades": upgrades,
                    "discard": {},
                })
        else:
            inputs = card["input"]
            maximum = min(
                (spices[name] // amount for name, amount in inputs.items() if amount),
                default=0,
            )
            for repetitions in range(maximum + 1):
                resulting = {
                    name: spices[name] - inputs[name] * repetitions
                    + card["output"][name] * repetitions
                    for name in SPICES
                }
                actions.extend(_after_discard_actions({
                    "type": "play_merchant", "card_id": card_id,
                    "repetitions": repetitions,
                }, resulting))

    for position in range(len(state["merchant_market"])):
        for payment in _payment_sequences(player["spices"], position):
            resulting = dict(player["spices"])
            for spice in payment:
                resulting[spice] -= 1
            selected_spices = state["merchant_market"][position]["spices"]
            for name in SPICES:
                resulting[name] += selected_spices[name]
            actions.extend(_after_discard_actions({
                "type": "acquire_merchant", "position": position, "payment": payment,
            }, resulting))

    for position, point_id in enumerate(state["point_market"]):
        cost = POINT_CARDS[point_id]["cost"]
        if all(player["spices"][name] >= amount for name, amount in cost.items()):
            actions.append({"type": "claim_point", "position": position, "point_id": point_id})

    if player["played"]:
        actions.append({"type": "rest"})
    return _action_space(state, actions).wrapped()


def _finish_turn(state: dict[str, Any]) -> None:
    state["turn_count"] += 1
    if state["end_after_turn"] is not None and state["turn_count"] >= state["end_after_turn"]:
        state["status"] = "finished"
        state["phase"] = "finished"
        return
    state["active_seat"] = state["turn_count"] % state["player_count"]


def apply_action(
    state: dict[str, Any], seat: int, action: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    legal = [item["action"] for item in legal_actions(state, seat)]
    action = _action_space(state, legal).require(action, error_factory=RuleError)
    next_state = deepcopy(state)
    player = next_state["players"][seat]
    events: list[dict[str, Any]] = [action_accepted(seat, action)]
    kind = action["type"]

    if kind == "play_merchant":
        card_id = action["card_id"]
        card = MERCHANTS[card_id]
        player["hand"].remove(card_id)
        player["played"].append(card_id)
        if card["kind"] == "gain":
            for name in SPICES:
                player["spices"][name] += card["output"][name]
        elif card["kind"] == "upgrade":
            for source in action["upgrades"]:
                target = SPICES[SPICES.index(source) + 1]
                player["spices"][source] -= 1
                player["spices"][target] += 1
        else:
            repetitions = action["repetitions"]
            for name in SPICES:
                player["spices"][name] += (
                    card["output"][name] - card["input"][name]
                ) * repetitions
        for name, amount in action["discard"].items():
            player["spices"][name] -= amount
        events.append({
            "type": "merchant_played", "seat": seat, "card_id": card_id,
            "card_kind": card["kind"],
        })
        if action["discard"]:
            events.append({"type": "spices_discarded", "seat": seat, "spices": action["discard"]})

    elif kind == "acquire_merchant":
        position = action["position"]
        for market_position, spice in enumerate(action["payment"]):
            player["spices"][spice] -= 1
            next_state["merchant_market"][market_position]["spices"][spice] += 1
        acquired = next_state["merchant_market"].pop(position)
        for name in SPICES:
            player["spices"][name] += acquired["spices"][name]
        for name, amount in action["discard"].items():
            player["spices"][name] -= amount
        player["hand"].append(acquired["card_id"])
        if next_state["merchant_deck"]:
            next_state["merchant_market"].append({
                "card_id": next_state["merchant_deck"].pop(), "spices": _pool(),
            })
        events.append({
            "type": "merchant_acquired", "seat": seat, "card_id": acquired["card_id"],
            "position": position, "collected_spices": acquired["spices"],
        })
        if action["discard"]:
            events.append({"type": "spices_discarded", "seat": seat, "spices": action["discard"]})

    elif kind == "claim_point":
        position = action["position"]
        point_id = next_state["point_market"].pop(position)
        card = POINT_CARDS[point_id]
        for name, amount in card["cost"].items():
            player["spices"][name] -= amount
        player["point_cards"].append(point_id)
        coin = None
        if position == 0 and next_state["coins"]["gold"]:
            next_state["coins"]["gold"] -= 1
            player["coins"]["gold"] += 1
            coin = "gold"
            if next_state["coins"]["gold"] == 0:
                next_state["coins"]["silver_position"] = 0
        elif (position == next_state["coins"]["silver_position"]
              and next_state["coins"]["silver"]):
            next_state["coins"]["silver"] -= 1
            player["coins"]["silver"] += 1
            coin = "silver"
        if next_state["point_deck"]:
            next_state["point_market"].append(next_state["point_deck"].pop())
        threshold = 6 if next_state["player_count"] <= 3 else 5
        if len(player["point_cards"]) >= threshold and next_state["end_after_turn"] is None:
            next_state["end_after_turn"] = (
                (next_state["turn_count"] // next_state["player_count"] + 1)
                * next_state["player_count"]
            )
        events.append({
            "type": "point_card_claimed", "seat": seat, "point_id": point_id,
            "points": card["points"], "coin": coin,
        })

    elif kind == "rest":
        player["hand"].extend(player["played"])
        recovered = list(player["played"])
        player["played"] = []
        events.append({"type": "cards_recovered", "seat": seat, "card_ids": recovered})
    else:  # pragma: no cover - canonical legal actions prevent this
        raise RuleError(f"unknown action type: {kind}")

    _finish_turn(next_state)
    validate_state(next_state)
    return next_state, events


def score(state: dict[str, Any], seat: int) -> int:
    player = state["players"][seat]
    return (
        sum(POINT_CARDS[card_id]["points"] for card_id in player["point_cards"])
        + player["coins"]["gold"] * 3
        + player["coins"]["silver"]
        + sum(player["spices"][name] for name in SPICES[1:])
    )


def rankings(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "seat": seat,
            "score": score(state, seat),
            "point_cards": len(player["point_cards"]),
            "gold": player["coins"]["gold"],
            "silver": player["coins"]["silver"],
        }
        for seat, player in enumerate(state["players"])
    ]
    return assign_competition_ranks(
        rows,
        sort_key=lambda row: (-row["score"], -row["seat"]),
        tie_key=lambda row: (row["score"], row["seat"]),
    )


def _merchant_view(card_id: str) -> dict[str, Any]:
    return deepcopy(MERCHANTS[card_id])


def _point_view(card_id: str) -> dict[str, Any]:
    return deepcopy(POINT_CARDS[card_id])


def observe(state: dict[str, Any], seat: int) -> dict[str, Any]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    players = []
    for player in state["players"]:
        players.append({
            "seat": player["seat"],
            "spices": dict(player["spices"]),
            "hand": [_merchant_view(card_id) for card_id in player["hand"]],
            "played": [_merchant_view(card_id) for card_id in player["played"]],
            "point_cards": [_point_view(card_id) for card_id in player["point_cards"]],
            "coins": dict(player["coins"]),
            "score": score(state, player["seat"]),
        })
    return {
        "game": "century_spice_road",
        "rules_version": state["rules_version"],
        "viewer_seat": seat,
        "status": state["status"],
        "turn_count": state["turn_count"],
        "active_seat": state["active_seat"],
        "phase": state["phase"],
        "caravan_limit": CARAVAN_LIMIT,
        "merchant_deck_count": len(state["merchant_deck"]),
        "merchant_market": [
            {"card": _merchant_view(slot["card_id"]), "spices": dict(slot["spices"])}
            for slot in state["merchant_market"]
        ],
        "point_deck_count": len(state["point_deck"]),
        "point_market": [_point_view(card_id) for card_id in state["point_market"]],
        "coins": dict(state["coins"]),
        "players": players,
        "rankings": rankings(state) if state["status"] == "finished" else None,
    }


def validate_state(state: dict[str, Any]) -> None:
    players = state.get("player_count")
    if not isinstance(players, int) or players < 2 or players > 5:
        raise AssertionError("invalid player count")
    if len(state.get("players", [])) != players:
        raise AssertionError("player list does not match player count")
    if state.get("status") not in {"active", "finished"}:
        raise AssertionError("invalid status")
    if state.get("phase") not in {"main", "finished"}:
        raise AssertionError("invalid phase")
    if state["status"] == "active" and not 0 <= state.get("active_seat", -1) < players:
        raise AssertionError("invalid active seat")
    if len(state["merchant_market"]) > MARKET_SIZE or len(state["point_market"]) > POINT_MARKET_SIZE:
        raise AssertionError("market exceeds its slot count")
    if state["coins"]["gold"] < 0 or state["coins"]["silver"] < 0:
        raise AssertionError("coin supply cannot be negative")
    if state["coins"]["silver_position"] not in (0, 1):
        raise AssertionError("invalid silver coin position")

    merchant_ids: list[str] = list(state["merchant_deck"])
    merchant_ids.extend(slot["card_id"] for slot in state["merchant_market"])
    point_ids: list[str] = list(state["point_deck"]) + list(state["point_market"])
    for expected_seat, player in enumerate(state["players"]):
        if player.get("seat") != expected_seat:
            raise AssertionError("player seats must be contiguous")
        validate_resource_pool(
            player["spices"], expected_keys=set(SPICES), label=f"seat {expected_seat} caravan",
        )
        if sum(player["spices"].values()) > CARAVAN_LIMIT:
            raise AssertionError("caravan exceeds ten spices")
        for card_id in player["hand"] + player["played"]:
            if card_id not in MERCHANTS:
                raise AssertionError("unknown merchant card")
            if card_id.startswith("merchant-"):
                merchant_ids.append(card_id)
        for card_id in player["point_cards"]:
            if card_id not in POINT_CARDS:
                raise AssertionError("unknown point card")
            point_ids.append(card_id)
        if set(player["coins"]) != {"gold", "silver"}:
            raise AssertionError("invalid player coin pool")
        if any(not isinstance(value, int) or value < 0 for value in player["coins"].values()):
            raise AssertionError("player coins cannot be negative")
    for slot in state["merchant_market"]:
        validate_resource_pool(slot["spices"], expected_keys=set(SPICES), label="merchant market")
    if len(merchant_ids) != len(set(merchant_ids)):
        raise AssertionError("merchant cards must be unique outside shared starters")
    if len(point_ids) != len(set(point_ids)):
        raise AssertionError("point cards must be unique")
    if set(merchant_ids) != {card_id for card_id in MERCHANTS if card_id.startswith("merchant-")}:
        raise AssertionError("merchant deck conservation failed")
    if set(point_ids) != set(POINT_CARDS):
        raise AssertionError("point deck conservation failed")
