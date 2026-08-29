"""Deterministic The Castles of Burgundy 2019 base-game rules engine.

The module models the public rules and physical tile mix without publisher art
or reproduced rules text.  It uses the common no. 1 duchy for every player and
does not include the mini-expansions bundled with the 2019 edition.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import random
from typing import Any

from .game import GameRuleError
from .mechanics import ActionSpace, action_accepted, assign_competition_ranks, state_digest
from .mechanics.topology import axial_hex_distance, axial_hex_neighbors


RULES_VERSION = "ravensburger-2019-base-1.0"
SCHEMA_VERSION = "agentbga.castles_of_burgundy.state.v1"
COLORS = ("building", "livestock", "monastery", "castle", "mine", "ship")
BUILDINGS = (
    "market", "carpenters_workshop", "church", "warehouse",
    "boarding_house", "bank", "town_hall", "watchtower",
)
ANIMALS = ("sheep", "cattle", "pig", "chicken")
MONASTERY_BUILDINGS = {
    16: "town_hall",
    17: "watchtower",
    18: "church",
    19: "carpenters_workshop",
    20: "market",
    21: "warehouse",
    22: "bank",
    23: "boarding_house",
}
PHASE_BONUSES = (10, 8, 6, 4, 2)
AREA_POINTS = (0, 1, 3, 6, 10, 15, 21, 28, 36)


class RuleError(GameRuleError):
    """A stable, user-correctable rules rejection."""


def _cell_id(q: int, r: int) -> str:
    return f"{q:+d},{r:+d}"


# The 37 spaces printed on the common no. 1 duchy in the 2019 edition.
# Equal region identifiers form one contiguous scoring area.
_CELL_ROWS = (
    # q, r, color, region, die number
    (0, -3, "livestock", "pasture-nw", 6),
    (1, -3, "castle", "castle-n", 5), (2, -3, "castle", "castle-n", 4),
    (3, -3, "monastery", "abbey-ne", 3),
    (-1, -2, "livestock", "pasture-nw", 2), (0, -2, "livestock", "pasture-nw", 1),
    (1, -2, "castle", "castle-n", 6), (2, -2, "monastery", "abbey-ne", 5),
    (3, -2, "building", "town-ne", 4),
    (-2, -1, "livestock", "pasture-nw", 5),
    (-1, -1, "livestock", "pasture-nw", 4), (0, -1, "building", "town-center", 3),
    (1, -1, "monastery", "abbey-ne", 1), (2, -1, "building", "town-ne", 2),
    (3, -1, "building", "town-ne", 3),
    (-3, 0, "ship", "river", 6), (-2, 0, "ship", "river", 1),
    (-1, 0, "ship", "river", 2), (0, 0, "castle", "castle-center", 6),
    (1, 0, "ship", "river", 5), (2, 0, "ship", "river", 6),
    (3, 0, "ship", "river", 1),
    (-3, 1, "building", "town-sw", 2), (-2, 1, "building", "town-sw", 5),
    (-1, 1, "mine", "mine-s", 4), (0, 1, "building", "town-se", 3),
    (1, 1, "building", "town-se", 1), (2, 1, "livestock", "pasture-e", 2),
    (-3, 2, "building", "town-sw", 6), (-2, 2, "mine", "mine-s", 1),
    (-1, 2, "monastery", "abbey-s", 2), (0, 2, "building", "town-se", 5),
    (1, 2, "building", "town-se", 6),
    (-3, 3, "mine", "mine-s", 3), (-2, 3, "monastery", "abbey-s", 4),
    (-1, 3, "monastery", "abbey-s", 1), (0, 3, "building", "town-se", 3),
)


def _make_duchy() -> list[dict[str, Any]]:
    cells = []
    for q, r, color, region, number in _CELL_ROWS:
        cells.append({
            "id": _cell_id(q, r), "q": q, "r": r, "color": color,
            "region": region, "number": number,
            "tile_id": "starting-castle" if (q, r) == (0, 0) else None,
        })
    return cells


DUCHY_TEMPLATE = _make_duchy()
CELL_TEMPLATE = {cell["id"]: cell for cell in DUCHY_TEMPLATE}
REGIONS: dict[str, tuple[str, ...]] = {}
for _cell in DUCHY_TEMPLATE:
    REGIONS.setdefault(_cell["region"], tuple())
    REGIONS[_cell["region"]] += (_cell["id"],)


def _tile_catalog() -> dict[str, dict[str, Any]]:
    tiles: dict[str, dict[str, Any]] = {}

    def add(tile_id: str, color: str, source: str, **data: Any) -> None:
        tiles[tile_id] = {"id": tile_id, "color": color, "source": source, **data}

    for building in BUILDINGS:
        for copy in range(1, 6):
            add(f"building-{building}-{copy:02d}", "building", "regular", building=building)
        for copy in range(1, 3):
            add(f"black-building-{building}-{copy:02d}", "building", "black", building=building)
    animal_values = (2, 3, 3, 4, 4)
    for animal in ANIMALS:
        for copy, value in enumerate(animal_values, 1):
            add(f"livestock-{animal}-{copy:02d}", "livestock", "regular",
                animal=animal, animals=value)
        for copy, value in enumerate((2, 4), 1):
            add(f"black-livestock-{animal}-{copy:02d}", "livestock", "black",
                animal=animal, animals=value)
    for number in range(1, 21):
        add(f"monastery-{number:02d}", "monastery", "regular", monastery=number)
    for number in range(21, 27):
        add(f"black-monastery-{number:02d}", "monastery", "black", monastery=number)
    for color, regular, black in (("castle", 14, 2), ("mine", 10, 2), ("ship", 20, 6)):
        for copy in range(1, regular + 1):
            add(f"{color}-{copy:02d}", color, "regular")
        for copy in range(1, black + 1):
            add(f"black-{color}-{copy:02d}", color, "black")
    return tiles


TILES = _tile_catalog()
GOODS = {
    f"goods-{kind}-{copy:02d}": {"id": f"goods-{kind}-{copy:02d}", "kind": kind}
    for kind in range(1, 7) for copy in range(1, 8)
}


def describe() -> dict[str, Any]:
    return {
        "id": "castles_of_burgundy",
        "name": "The Castles of Burgundy",
        "rules_version": RULES_VERSION,
        "players": {"minimum": 2, "maximum": 4},
        "hidden_information": False,
        "implementation_status": "playable_beta",
        "runnable": True,
        "decision_model": "sequential_structured_decisions_with_nested_tile_effects",
        "default_max_turns": 5000,
        "action_types": [
            "take_tile", "place_tile", "sell_goods", "take_workers",
            "buy_tile", "choose_tile", "choose_goods", "skip_effect", "end_turn",
        ],
        "win_condition": "Highest score after five phases and twenty-five rounds.",
        "edition": "2019 base game using the common no. 1 duchy; expansions excluded",
    }


def _depot_layout(players: int, phase: int) -> list[list[str]]:
    """Return the colored regular spaces used at each numbered depot."""
    layouts = [
        ["monastery", "building"],
        ["castle", "ship"],
        ["mine", "building"],
        ["building", "ship"],
        ["livestock", "building"],
        ["livestock", "monastery"],
    ]
    if players >= 3:
        special = "castle" if phase % 2 == 0 else "mine"
        additions = ("ship", "building", "monastery", "livestock", "building", special)
        for layout, color in zip(layouts, additions, strict=True):
            layout.append(color)
    if players == 4:
        additions = ("livestock", "building", "building", "mine", "monastery", "ship")
        for layout, color in zip(layouts, additions, strict=True):
            layout.append(color)
    return layouts


def _regular_counts(players: int, phase: int) -> dict[str, int]:
    counts = Counter(color for layout in _depot_layout(players, phase) for color in layout)
    return {color: counts[color] for color in COLORS}


def _turn_order(state: dict[str, Any]) -> list[int]:
    return [
        player["seat"] for player in sorted(
            state["players"],
            key=lambda player: (-player["bridge"], -player["bridge_priority"]),
        )
    ]


def _refill_tiles(state: dict[str, Any]) -> None:
    for depot in state["depots"]:
        state["discarded_tiles"].extend(depot["tiles"])
        depot["tiles"] = []
    state["discarded_tiles"].extend(state["black_depot"])
    state["black_depot"] = []
    for depot, layout in zip(
        state["depots"], _depot_layout(state["player_count"], state["phase_index"]),
        strict=True,
    ):
        for color in layout:
            if state["tile_supply"][color]:
                depot["tiles"].append(state["tile_supply"][color].pop())
    black_count = {2: 4, 3: 6, 4: 8}[state["player_count"]]
    for _ in range(black_count):
        if state["black_supply"]:
            state["black_depot"].append(state["black_supply"].pop())


def _start_round(state: dict[str, Any]) -> None:
    rng = random.Random(f"burgundy:{state['seed']}:{state['phase_index']}:{state['round_index']}")
    state["white_die"] = rng.randint(1, 6)
    goods_id = state["phase_goods"][state["phase_index"]].pop(0)
    state["depots"][state["white_die"] - 1]["goods"].append(goods_id)
    state["round_order"] = _turn_order(state)
    state["round_dice"] = {
        str(seat): [rng.randint(1, 6), rng.randint(1, 6)] for seat in range(state["player_count"])
    }
    state["round_turn_index"] = 0
    state["active_seat"] = state["round_order"][0]
    state["remaining_dice"] = [
        {"index": index, "value": value}
        for index, value in enumerate(state["round_dice"][str(state["active_seat"])])
    ]
    state["free_actions"] = 0
    state["pending_effect"] = None
    state["bought_this_turn"] = False
    state["phase"] = "player_turn"


def new_game(
    players: int, seed: int, config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if config not in (None, {}):
        raise RuleError("The Castles of Burgundy base game does not accept setup options")
    if players < 2 or players > 4:
        raise RuleError("The Castles of Burgundy requires 2 to 4 players")
    rng = random.Random(seed)
    regular = {color: [] for color in COLORS}
    black: list[str] = []
    for tile_id, tile in TILES.items():
        (black if tile["source"] == "black" else regular[tile["color"]]).append(tile_id)
    for pile in regular.values():
        rng.shuffle(pile)
    rng.shuffle(black)
    goods = list(GOODS)
    rng.shuffle(goods)
    phase_goods = [[goods.pop() for _ in range(5)] for _ in range(5)]
    starting = rng.randrange(players)
    initial_order = [(starting + offset) % players for offset in range(players)]
    player_rows = []
    for seat in range(players):
        position = initial_order.index(seat)
        owned_goods = {str(kind): [] for kind in range(1, 7)}
        for _ in range(3):
            good = goods.pop()
            owned_goods[str(GOODS[good]["kind"])].append(good)
        player_rows.append({
            "seat": seat, "score": 0, "silver": 1, "workers": position + 1,
            "bridge": 0, "bridge_priority": players - position,
            "storage": [], "goods": owned_goods, "sold_goods": [],
            "duchy": deepcopy(DUCHY_TEMPLATE), "completed_regions": ["castle-center"],
        })
    state = {
        "schema_version": SCHEMA_VERSION, "rules_version": RULES_VERSION,
        "seed": seed, "player_count": players, "status": "active",
        "phase": "setup", "phase_index": 0, "round_index": 0,
        "turn_count": 0, "decision_count": 0, "active_seat": initial_order[0],
        "round_turn_index": 0, "round_order": initial_order,
        "round_dice": {}, "white_die": None, "remaining_dice": [],
        "free_actions": 0, "pending_effect": None, "bought_this_turn": False,
        "bridge_counter": players,
        "players": player_rows,
        "depots": [{"number": number, "tiles": [], "goods": []} for number in range(1, 7)],
        "black_depot": [], "tile_supply": regular, "black_supply": black,
        "discarded_tiles": [], "phase_goods": phase_goods,
        "discarded_goods": goods, "color_bonus_claims": {color: [] for color in COLORS},
    }
    _refill_tiles(state)
    _start_round(state)
    validate_state(state)
    return state


def state_hash(state: dict[str, Any]) -> str:
    return state_digest(state)


def _player(state: dict[str, Any], seat: int) -> dict[str, Any]:
    return state["players"][seat]


def _cell(player: dict[str, Any], cell_id: str) -> dict[str, Any]:
    return next(cell for cell in player["duchy"] if cell["id"] == cell_id)


def _tile_ids_in_duchy(player: dict[str, Any]) -> list[str]:
    return [cell["tile_id"] for cell in player["duchy"] if cell["tile_id"] not in (None, "starting-castle")]


def _monasteries(player: dict[str, Any]) -> set[int]:
    return {
        TILES[tile_id]["monastery"] for tile_id in _tile_ids_in_duchy(player)
        if TILES[tile_id]["color"] == "monastery"
    }


def _occupied_neighbors(player: dict[str, Any], cell: dict[str, Any]) -> bool:
    occupied = {(item["q"], item["r"]) for item in player["duchy"] if item["tile_id"] is not None}
    return bool(axial_hex_neighbors((cell["q"], cell["r"])) & occupied)


def _building_allowed(player: dict[str, Any], tile_id: str, target: dict[str, Any]) -> bool:
    tile = TILES[tile_id]
    if tile["color"] != "building" or 1 in _monasteries(player):
        return True
    for cell_id in REGIONS[target["region"]]:
        placed = _cell(player, cell_id)["tile_id"]
        if placed not in (None, "starting-castle") and TILES[placed].get("building") == tile["building"]:
            return False
    return True


def _worker_cost(player: dict[str, Any], rolled: int, target: int, purpose: str, color: str | None) -> int:
    distance = min((target - rolled) % 6, (rolled - target) % 6)
    monasteries = _monasteries(player)
    free = (
        (purpose == "take" and 12 in monasteries)
        or (purpose == "place" and color == "building" and 9 in monasteries)
        or (purpose == "place" and color in {"ship", "livestock"} and 10 in monasteries)
        or (purpose == "place" and color in {"castle", "mine", "monastery"} and 11 in monasteries)
    )
    distance = max(0, distance - int(free))
    power = 2 if 8 in monasteries else 1
    return (distance + power - 1) // power


def _source_actions(
    state: dict[str, Any], player: dict[str, Any], *, source: str, die_index: int | None,
    rolled: int | None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    prefix = {"source": source}
    if die_index is not None:
        prefix["die_index"] = die_index
    if source == "bonus":
        usable = [(target, 0) for target in range(1, 7)]
    else:
        assert rolled is not None
        usable = [(target, _worker_cost(player, rolled, target, "take", None)) for target in range(1, 7)]
    storage_full = len(player["storage"]) >= 3
    for depot_number, workers in usable:
        if workers > player["workers"]:
            continue
        for tile_id in state["depots"][depot_number - 1]["tiles"]:
            discards = player["storage"] if storage_full else [None]
            for discard in discards:
                action = {**prefix, "type": "take_tile", "depot": depot_number,
                          "tile_id": tile_id, "workers": workers}
                if discard is not None:
                    action["discard_tile_id"] = discard
                actions.append(action)
    for tile_id in player["storage"]:
        color = TILES[tile_id]["color"]
        for target in player["duchy"]:
            if target["tile_id"] is not None or target["color"] != color:
                continue
            if not _occupied_neighbors(player, target) or not _building_allowed(player, tile_id, target):
                continue
            candidates = [(target["number"], 0)] if source == "bonus" else [
                (target["number"], _worker_cost(player, rolled, target["number"], "place", color))
            ]
            for _number, workers in candidates:
                if workers <= player["workers"]:
                    actions.append({**prefix, "type": "place_tile", "tile_id": tile_id,
                                    "cell_id": target["id"], "workers": workers})
    goods_kinds = [int(kind) for kind, pile in player["goods"].items() if pile]
    if source == "bonus":
        sellable = [(kind, 0) for kind in goods_kinds]
    else:
        sellable = [(kind, _worker_cost(player, rolled, kind, "sell", None)) for kind in goods_kinds]
    for kind, workers in sellable:
        if workers <= player["workers"]:
            actions.append({**prefix, "type": "sell_goods", "goods_type": kind, "workers": workers})
    actions.append({**prefix, "type": "take_workers", "workers": 0})
    return actions


def _buy_actions(state: dict[str, Any], player: dict[str, Any]) -> list[dict[str, Any]]:
    if state["bought_this_turn"] or len(player["storage"]) >= 3:
        return []
    monastery_six = 6 in _monasteries(player)
    sources: list[tuple[str, int | None, list[str]]] = [("black", None, state["black_depot"])]
    if monastery_six:
        sources.extend(("depot", depot["number"], depot["tiles"]) for depot in state["depots"])
    payments = []
    for silver in range(min(2, player["silver"]) + 1):
        workers = 2 - silver
        if workers <= player["workers"] and (monastery_six or workers == 0):
            payments.append((silver, workers))
    return [
        {"type": "buy_tile", "source": source, "depot": depot, "tile_id": tile_id,
         "silver": silver, "workers": workers}
        for source, depot, tile_ids in sources for tile_id in tile_ids
        for silver, workers in payments
    ]


def _goods_choices(player: dict[str, Any], goods_ids: list[str]) -> list[list[int]]:
    available = sorted({GOODS[goods_id]["kind"] for goods_id in goods_ids})
    owned = {int(kind) for kind, pile in player["goods"].items() if pile}
    free = 3 - len(owned)
    mandatory = [kind for kind in available if kind in owned]
    new = [kind for kind in available if kind not in owned]
    if len(new) <= free:
        return [mandatory + new]
    from itertools import combinations
    return [mandatory + list(chosen) for chosen in combinations(new, free)]


def _pending_actions(state: dict[str, Any], player: dict[str, Any]) -> list[dict[str, Any]]:
    pending = state["pending_effect"] or {}
    kind = pending.get("kind")
    actions: list[dict[str, Any]] = []
    if kind == "choose_tile" and len(player["storage"]) < 3:
        allowed = set(pending["colors"])
        for depot in state["depots"]:
            for tile_id in depot["tiles"]:
                if TILES[tile_id]["color"] in allowed:
                    actions.append({"type": "choose_tile", "depot": depot["number"], "tile_id": tile_id})
    elif kind == "sell_goods":
        actions.extend({"type": "sell_goods_effect", "goods_type": int(goods_kind)}
                       for goods_kind, pile in player["goods"].items() if pile)
    elif kind == "place_tile":
        for tile_id in player["storage"]:
            color = TILES[tile_id]["color"]
            for target in player["duchy"]:
                if (target["tile_id"] is None and target["color"] == color
                        and _occupied_neighbors(player, target)
                        and _building_allowed(player, tile_id, target)):
                    actions.append({"type": "place_tile_effect", "tile_id": tile_id,
                                    "cell_id": target["id"]})
    elif kind == "choose_goods":
        monasteries = _monasteries(player)
        for first in state["depots"]:
            seconds = [None]
            if 5 in monasteries:
                seconds += [((first["number"] - 2) % 6) + 1, (first["number"] % 6) + 1]
            for second in seconds:
                goods_ids = list(first["goods"])
                if second is not None:
                    goods_ids += state["depots"][second - 1]["goods"]
                if not goods_ids:
                    continue
                for types in _goods_choices(player, goods_ids):
                    actions.append({"type": "choose_goods", "depot": first["number"],
                                    "adjacent_depot": second, "goods_types": types})
    actions.append({"type": "skip_effect"})
    return actions


def _action_space(state: dict[str, Any], actions: list[dict[str, Any]]) -> ActionSpace:
    unique = {state_digest(action): action for action in actions}
    return ActionSpace.from_actions(
        state["phase"], state["decision_count"], [unique[key] for key in sorted(unique)],
        prefix="burgundy",
    )


def legal_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    if state["status"] != "active" or seat != state["active_seat"]:
        return []
    player = _player(state, seat)
    if state["pending_effect"] is not None:
        return _action_space(state, _pending_actions(state, player)).wrapped()
    actions = _buy_actions(state, player)
    if state["free_actions"]:
        actions.extend(_source_actions(state, player, source="bonus", die_index=None, rolled=None))
    elif state["remaining_dice"]:
        for die in state["remaining_dice"]:
            actions.extend(_source_actions(
                state, player, source="die", die_index=die["index"], rolled=die["value"],
            ))
    else:
        actions.append({"type": "end_turn"})
    return _action_space(state, actions).wrapped()


def _sell_goods(state: dict[str, Any], player: dict[str, Any], goods_type: int,
                events: list[dict[str, Any]]) -> None:
    pile = player["goods"][str(goods_type)]
    if not pile:
        raise AssertionError("cannot sell an empty goods pile")
    count = len(pile)
    player["sold_goods"].extend(pile)
    pile.clear()
    monasteries = _monasteries(player)
    player["silver"] += 2 if 3 in monasteries else 1
    if 4 in monasteries:
        player["workers"] += 1
    points = state["player_count"] * count
    player["score"] += points
    events.append({"type": "goods_sold", "seat": player["seat"], "goods_type": goods_type,
                   "count": count, "points": points})


def _score_placement(state: dict[str, Any], player: dict[str, Any], target: dict[str, Any],
                     events: list[dict[str, Any]]) -> None:
    region = target["region"]
    if region not in player["completed_regions"] and all(
        _cell(player, cell_id)["tile_id"] is not None for cell_id in REGIONS[region]
    ):
        player["completed_regions"].append(region)
        size = len(REGIONS[region])
        points = AREA_POINTS[size] + PHASE_BONUSES[state["phase_index"]]
        player["score"] += points
        events.append({"type": "area_completed", "seat": player["seat"],
                       "region": region, "size": size, "points": points})
    color = target["color"]
    color_cells = [cell for cell in player["duchy"] if cell["color"] == color]
    claims = state["color_bonus_claims"][color]
    if player["seat"] not in claims and len(claims) < 2 and all(cell["tile_id"] is not None for cell in color_cells):
        claims.append(player["seat"])
        values = ({2: (5, 2), 3: (6, 3), 4: (7, 4)})[state["player_count"]]
        points = values[len(claims) - 1]
        player["score"] += points
        events.append({"type": "color_completed", "seat": player["seat"],
                       "color": color, "bonus": "large" if len(claims) == 1 else "small",
                       "points": points})


def _place_tile(state: dict[str, Any], player: dict[str, Any], tile_id: str, cell_id: str,
                events: list[dict[str, Any]]) -> None:
    player["storage"].remove(tile_id)
    target = _cell(player, cell_id)
    target["tile_id"] = tile_id
    tile = TILES[tile_id]
    events.append({"type": "tile_placed", "seat": player["seat"], "tile_id": tile_id,
                   "cell_id": cell_id, "color": tile["color"]})
    if tile["color"] == "livestock":
        matching = []
        for region_cell in REGIONS[target["region"]]:
            placed = _cell(player, region_cell)["tile_id"]
            if placed not in (None, "starting-castle") and TILES[placed].get("animal") == tile["animal"]:
                matching.append(TILES[placed]["animals"])
        points = sum(matching) + (len(matching) if 7 in _monasteries(player) else 0)
        player["score"] += points
        events.append({"type": "livestock_scored", "seat": player["seat"],
                       "animal": tile["animal"], "points": points})
    elif tile["color"] == "ship":
        state["bridge_counter"] += 1
        player["bridge"] = min(6, player["bridge"] + 1)
        player["bridge_priority"] = state["bridge_counter"]
        state["pending_effect"] = {"kind": "choose_goods"}
    elif tile["color"] == "castle":
        state["free_actions"] += 1
    elif tile["color"] == "building":
        building = tile["building"]
        if building == "market":
            state["pending_effect"] = {"kind": "choose_tile", "colors": ["ship", "livestock"]}
        elif building == "carpenters_workshop":
            state["pending_effect"] = {"kind": "choose_tile", "colors": ["building"]}
        elif building == "church":
            state["pending_effect"] = {"kind": "choose_tile", "colors": ["mine", "monastery", "castle"]}
        elif building == "warehouse":
            state["pending_effect"] = {"kind": "sell_goods"}
        elif building == "boarding_house":
            player["workers"] += 4
        elif building == "bank":
            player["silver"] += 2
        elif building == "town_hall":
            state["pending_effect"] = {"kind": "place_tile"}
        elif building == "watchtower":
            player["score"] += 4
    _score_placement(state, player, target, events)


def _finish_turn(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    state["turn_count"] += 1
    state["round_turn_index"] += 1
    if state["round_turn_index"] < state["player_count"]:
        state["active_seat"] = state["round_order"][state["round_turn_index"]]
        dice = state["round_dice"][str(state["active_seat"])]
        state["remaining_dice"] = [{"index": i, "value": value} for i, value in enumerate(dice)]
        state["free_actions"] = 0
        state["bought_this_turn"] = False
        return
    if state["round_index"] < 4:
        state["round_index"] += 1
        _start_round(state)
        events.append({"type": "round_started", "phase": state["phase_index"] + 1,
                       "round": state["round_index"] + 1})
        return
    for player in state["players"]:
        mines = sum(1 for cell in player["duchy"] if cell["tile_id"] not in (None, "starting-castle")
                    and TILES[cell["tile_id"]]["color"] == "mine")
        player["silver"] += mines
        if 2 in _monasteries(player):
            player["workers"] += mines
    events.append({"type": "phase_ended", "phase": state["phase_index"] + 1})
    if state["phase_index"] == 4:
        state["status"] = "finished"
        state["phase"] = "finished"
        state["remaining_dice"] = []
        events.append({"type": "game_finished", "rankings": rankings(state)})
        return
    state["phase_index"] += 1
    state["round_index"] = 0
    _refill_tiles(state)
    _start_round(state)
    events.append({"type": "phase_started", "phase": state["phase_index"] + 1})


def apply_action(
    state: dict[str, Any], seat: int, action: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if state["status"] != "active" or seat != state["active_seat"]:
        raise RuleError("seat is not active")
    legal = [item["action"] for item in legal_actions(state, seat)]
    canonical = _action_space(state, legal).require(action, error_factory=RuleError)
    next_state = deepcopy(state)
    next_state["decision_count"] += 1
    player = _player(next_state, seat)
    events: list[dict[str, Any]] = [action_accepted(seat, canonical)]
    kind = canonical["type"]

    if next_state["pending_effect"] is not None:
        next_state["pending_effect"] = None
        if kind == "choose_tile":
            depot = next_state["depots"][canonical["depot"] - 1]
            depot["tiles"].remove(canonical["tile_id"])
            player["storage"].append(canonical["tile_id"])
            events.append({"type": "tile_taken", "seat": seat, "tile_id": canonical["tile_id"],
                           "source": "building_effect"})
        elif kind == "sell_goods_effect":
            _sell_goods(next_state, player, canonical["goods_type"], events)
        elif kind == "place_tile_effect":
            _place_tile(next_state, player, canonical["tile_id"], canonical["cell_id"], events)
        elif kind == "choose_goods":
            depot_numbers = [canonical["depot"]]
            if canonical["adjacent_depot"] is not None:
                depot_numbers.append(canonical["adjacent_depot"])
            allowed = set(canonical["goods_types"])
            taken = []
            for number in depot_numbers:
                depot = next_state["depots"][number - 1]
                for goods_id in list(depot["goods"]):
                    goods_type = GOODS[goods_id]["kind"]
                    if goods_type in allowed:
                        depot["goods"].remove(goods_id)
                        player["goods"][str(goods_type)].append(goods_id)
                        taken.append(goods_id)
            events.append({"type": "goods_taken", "seat": seat, "goods_ids": taken})
    elif kind == "buy_tile":
        player["silver"] -= canonical["silver"]
        player["workers"] -= canonical["workers"]
        source = next_state["black_depot"] if canonical["source"] == "black" else next_state["depots"][canonical["depot"] - 1]["tiles"]
        source.remove(canonical["tile_id"])
        player["storage"].append(canonical["tile_id"])
        next_state["bought_this_turn"] = True
        events.append({"type": "tile_bought", "seat": seat, "tile_id": canonical["tile_id"]})
    elif kind == "end_turn":
        _finish_turn(next_state, events)
    else:
        if canonical["source"] == "bonus":
            next_state["free_actions"] -= 1
        else:
            die = next(item for item in next_state["remaining_dice"]
                       if item["index"] == canonical["die_index"])
            next_state["remaining_dice"].remove(die)
        player["workers"] -= canonical["workers"]
        if kind == "take_tile":
            if "discard_tile_id" in canonical:
                player["storage"].remove(canonical["discard_tile_id"])
                next_state["discarded_tiles"].append(canonical["discard_tile_id"])
            depot = next_state["depots"][canonical["depot"] - 1]
            depot["tiles"].remove(canonical["tile_id"])
            player["storage"].append(canonical["tile_id"])
            events.append({"type": "tile_taken", "seat": seat, "tile_id": canonical["tile_id"],
                           "source": f"depot-{canonical['depot']}"})
        elif kind == "place_tile":
            _place_tile(next_state, player, canonical["tile_id"], canonical["cell_id"], events)
        elif kind == "sell_goods":
            _sell_goods(next_state, player, canonical["goods_type"], events)
        elif kind == "take_workers":
            monasteries = _monasteries(player)
            player["workers"] += 4 if 14 in monasteries else 2
            if 13 in monasteries:
                player["silver"] += 1
            events.append({"type": "workers_taken", "seat": seat})
    validate_state(next_state)
    return next_state, events


def _final_points(state: dict[str, Any], player: dict[str, Any]) -> tuple[int, dict[str, int]]:
    goods = sum(len(pile) for pile in player["goods"].values())
    resources = goods + player["silver"] + player["workers"] // 2
    monasteries = _monasteries(player)
    tiles = [TILES[tile_id] for tile_id in _tile_ids_in_duchy(player)]
    yellow = 0
    if 15 in monasteries:
        yellow += 2 * len({GOODS[goods_id]["kind"] for goods_id in player["sold_goods"]})
    for number, building in MONASTERY_BUILDINGS.items():
        if number in monasteries:
            yellow += 4 * sum(tile.get("building") == building for tile in tiles)
    if 24 in monasteries:
        yellow += 4 * len({tile["animal"] for tile in tiles if tile["color"] == "livestock"})
    if 25 in monasteries:
        yellow += len(player["sold_goods"])
    if 26 in monasteries:
        yellow += 3 * sum(
            player["seat"] in seats for seats in state["color_bonus_claims"].values()
        )
    detail = {"board_score": player["score"], "resource_points": resources,
              "monastery_points": yellow}
    return player["score"] + resources + yellow, detail


def rankings(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for player in state["players"]:
        score, detail = _final_points(state, player)
        empty = sum(cell["tile_id"] is None for cell in player["duchy"])
        rows.append({"seat": player["seat"], "score": score, "empty_spaces": empty,
                     "bridge": player["bridge"], **detail})
    return assign_competition_ranks(
        rows,
        sort_key=lambda row: (-row["score"], -row["empty_spaces"], row["bridge"],
                              state["players"][row["seat"]]["bridge_priority"]),
        tie_key=lambda row: (row["score"], row["empty_spaces"], row["bridge"],
                             state["players"][row["seat"]]["bridge_priority"]),
    )


def observe(state: dict[str, Any], seat: int) -> dict[str, Any]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    return {
        "game": "castles_of_burgundy", "rules_version": RULES_VERSION,
        "implementation_status": "playable_beta", "viewer_seat": seat,
        "status": state["status"], "phase": state["phase"],
        "phase_number": state["phase_index"] + 1, "round_number": state["round_index"] + 1,
        "turn_count": state["turn_count"], "active_seat": state["active_seat"],
        "turn_order": _turn_order(state), "round_order": list(state["round_order"]),
        "white_die": state["white_die"], "round_dice": deepcopy(state["round_dice"]),
        "remaining_dice": deepcopy(state["remaining_dice"]),
        "free_actions": state["free_actions"], "pending_effect": deepcopy(state["pending_effect"]),
        "bought_this_turn": state["bought_this_turn"],
        "depots": deepcopy(state["depots"]), "black_depot": list(state["black_depot"]),
        "tile_supply_counts": {color: len(pile) for color, pile in state["tile_supply"].items()},
        "black_supply_count": len(state["black_supply"]),
        "color_bonus_claims": deepcopy(state["color_bonus_claims"]),
        "players": deepcopy(state["players"]),
        "rankings": rankings(state) if state["status"] == "finished" else None,
    }


def validate_state(state: dict[str, Any]) -> None:
    if state.get("schema_version") != SCHEMA_VERSION or state.get("rules_version") != RULES_VERSION:
        raise AssertionError("invalid Castles of Burgundy schema or rules version")
    players = state.get("player_count")
    if players not in (2, 3, 4) or len(state.get("players", [])) != players:
        raise AssertionError("invalid Castles of Burgundy player count")
    if state.get("status") not in {"active", "finished"}:
        raise AssertionError("invalid Castles of Burgundy status")
    if not 0 <= state.get("phase_index", -1) < 5 or not 0 <= state.get("round_index", -1) < 5:
        raise AssertionError("invalid phase or round")
    if not 0 <= state.get("active_seat", -1) < players:
        raise AssertionError("invalid active seat")
    if len(state.get("depots", [])) != 6 or [row["number"] for row in state["depots"]] != list(range(1, 7)):
        raise AssertionError("invalid depots")
    if sorted(state.get("round_order", [])) != list(range(players)):
        raise AssertionError("invalid round order")
    for expected, player in enumerate(state["players"]):
        if player.get("seat") != expected or min(player.get("score", -1), player.get("silver", -1), player.get("workers", -1)) < 0:
            raise AssertionError("invalid player resources")
        if len(player.get("storage", [])) > 3:
            raise AssertionError("hex storage exceeds three tiles")
        if len(player.get("duchy", [])) != 37:
            raise AssertionError("duchy must contain 37 cells")
        if any(
            {key: cell.get(key) for key in ("id", "q", "r", "color", "region", "number")}
            != {key: template[key] for key in ("id", "q", "r", "color", "region", "number")}
            for cell, template in zip(player["duchy"], DUCHY_TEMPLATE, strict=True)
        ):
            raise AssertionError("invalid duchy cells")
        if _cell(player, "+0,+0")["tile_id"] != "starting-castle":
            raise AssertionError("missing starting castle")
        goods_types = {int(kind) for kind, pile in player["goods"].items() if pile}
        if len(goods_types) > 3:
            raise AssertionError("goods storage exceeds three types")
    tile_zones: list[list[str]] = [state["black_supply"], state["black_depot"], state["discarded_tiles"]]
    tile_zones.extend(state["tile_supply"].values())
    tile_zones.extend(depot["tiles"] for depot in state["depots"])
    for player in state["players"]:
        tile_zones.append(player["storage"])
        tile_zones.append(_tile_ids_in_duchy(player))
    tile_ids = [tile for zone in tile_zones for tile in zone]
    if len(tile_ids) != len(TILES) or Counter(tile_ids) != Counter(TILES.keys()):
        raise AssertionError("Castles of Burgundy tile conservation failed")
    goods_zones = [state["discarded_goods"]]
    goods_zones.extend(state["phase_goods"])
    goods_zones.extend(depot["goods"] for depot in state["depots"])
    for player in state["players"]:
        goods_zones.extend(player["goods"].values())
        goods_zones.append(player["sold_goods"])
    goods_ids = [good for zone in goods_zones for good in zone]
    if len(goods_ids) != len(GOODS) or Counter(goods_ids) != Counter(GOODS.keys()):
        raise AssertionError("Castles of Burgundy goods conservation failed")
