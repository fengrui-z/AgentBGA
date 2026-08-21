"""Deterministic, JSON-serializable Azul base-game rules engine.

The plugin implements the colored-wall base game for two to four players.
Publisher artwork and rulebook prose are deliberately not stored here.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import random
from typing import Any

from .game import GameRuleError
from .mechanics import (
    ActionSpace,
    action_accepted,
    assign_competition_ranks,
    domain_event,
    state_digest,
    validate_unique_items,
)


RULES_VERSION = "next-move-2018-base-colored-wall-1.0"
SCHEMA_VERSION = "agentbga.azul.state.v1"

COLORS = ("blue", "yellow", "red", "black", "white")
TILES_PER_COLOR = 20
TOTAL_TILES = len(COLORS) * TILES_PER_COLOR
FACTORY_COUNTS = {2: 5, 3: 7, 4: 9}
FACTORY_SIZE = 4
FLOOR_PENALTIES = (-1, -1, -2, -2, -2, -3, -3)
START_MARKER = "start-player-marker"

WALL_PATTERN = (
    ("blue", "yellow", "red", "black", "white"),
    ("white", "blue", "yellow", "red", "black"),
    ("black", "white", "blue", "yellow", "red"),
    ("red", "black", "white", "blue", "yellow"),
    ("yellow", "red", "black", "white", "blue"),
)


class RuleError(GameRuleError):
    """A stable, user-correctable Azul rule rejection."""


def tile_catalog() -> dict[str, str]:
    return {
        f"{color}-{number:02d}": color
        for color in COLORS
        for number in range(1, TILES_PER_COLOR + 1)
    }


TILES = tile_catalog()


def describe() -> dict[str, Any]:
    return {
        "id": "azul",
        "name": "Azul",
        "rules_version": RULES_VERSION,
        "players": {"minimum": 2, "maximum": 4},
        "hidden_information": False,
        "implementation_status": "playable_beta",
        "runnable": True,
        "decision_model": "one_structured_decision_per_player_turn",
        "default_max_turns": 300,
        "action_types": ["draft_tiles"],
        "wall_variant": "colored",
        "rules_sources": ["Next Move Games Azul base-game English rulebook"],
        "content_scope": (
            "Base game for the colored wall with deterministic physical tiles; "
            "publisher artwork, gray-wall play, and expansions are not included."
        ),
        "win_condition": (
            "Finish after wall-tiling when a player completes a horizontal row; "
            "highest score wins, then most completed horizontal rows."
        ),
    }


def _factory_rows(players: int) -> list[dict[str, Any]]:
    return [
        {"id": f"factory-{index:02d}", "tiles": []}
        for index in range(1, FACTORY_COUNTS[players] + 1)
    ]


def _player_board(seat: int) -> dict[str, Any]:
    return {
        "seat": seat,
        "score": 0,
        "pattern_lines": [
            {"line": line, "capacity": line, "tiles": []}
            for line in range(1, 6)
        ],
        "wall": [[None for _ in range(5)] for _ in range(5)],
        "floor": [],
    }


def _derived_shuffle_seed(state: dict[str, Any]) -> int:
    material = (
        f"{state['rules_version']}:{state['seed']}:"
        f"azul-refill:{state['shuffle_count']}"
    )
    return int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big")


def _refill_bag_from_lid(
    state: dict[str, Any], events: list[dict[str, Any]] | None = None,
) -> bool:
    if state["bag"] or not state["lid"]:
        return False
    state["shuffle_count"] += 1
    tiles = list(state["lid"])
    state["lid"] = []
    random.Random(_derived_shuffle_seed(state)).shuffle(tiles)
    state["bag"] = tiles
    if events is not None:
        events.append(domain_event(
            "bag_refilled",
            round=state["round"],
            shuffle_count=state["shuffle_count"],
            tile_count=len(tiles),
        ))
    return True


def _fill_factories(
    state: dict[str, Any], events: list[dict[str, Any]] | None = None,
) -> None:
    for factory in state["factories"]:
        if factory["tiles"]:
            raise AssertionError("factories must be empty before refilling")
        while len(factory["tiles"]) < FACTORY_SIZE:
            if not state["bag"] and not _refill_bag_from_lid(state, events):
                break
            factory["tiles"].append(state["bag"].pop())


def new_game(
    players: int, seed: int, config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if config not in (None, {}):
        raise RuleError("Azul does not accept game setup options")
    if players not in FACTORY_COUNTS:
        raise RuleError("Azul requires 2, 3, or 4 players")
    bag = list(TILES)
    random.Random(seed).shuffle(bag)
    state = {
        "schema_version": SCHEMA_VERSION,
        "rules_version": RULES_VERSION,
        "seed": seed,
        "player_count": players,
        "status": "active",
        "phase": "factory_offer",
        "round": 1,
        "turn_count": 0,
        "active_seat": 0,
        "shuffle_count": 0,
        "bag": bag,
        "lid": [],
        "factories": _factory_rows(players),
        "center": [],
        "center_has_start_marker": True,
        "start_marker_holder_seat": None,
        "players": [_player_board(seat) for seat in range(players)],
    }
    _fill_factories(state)
    validate_state(state)
    return state


def state_hash(state: dict[str, Any]) -> str:
    return state_digest(state)


def _tile_color(tile_id: str) -> str:
    try:
        return TILES[tile_id]
    except KeyError as error:
        raise AssertionError(f"unknown tile: {tile_id}") from error


def _color_counts(tile_ids: list[str]) -> dict[str, int]:
    counts = dict.fromkeys(COLORS, 0)
    for tile_id in tile_ids:
        counts[_tile_color(tile_id)] += 1
    return counts


def _source_tiles(state: dict[str, Any], source: str) -> list[str]:
    if source == "center":
        return state["center"]
    for factory in state["factories"]:
        if factory["id"] == source:
            return factory["tiles"]
    raise RuleError("unknown tile source")


def _line_color(line: dict[str, Any]) -> str | None:
    return _tile_color(line["tiles"][0]) if line["tiles"] else None


def _wall_has_color(player: dict[str, Any], row: int, color: str) -> bool:
    column = WALL_PATTERN[row].index(color)
    return player["wall"][row][column] is not None


def _legal_destinations(player: dict[str, Any], color: str) -> list[str]:
    destinations = []
    for line in player["pattern_lines"]:
        row = line["line"] - 1
        if len(line["tiles"]) >= line["capacity"]:
            continue
        if line["tiles"] and _line_color(line) != color:
            continue
        if _wall_has_color(player, row, color):
            continue
        destinations.append(f"pattern-line-{line['line']}")
    destinations.append("floor")
    return destinations


def _action_space(state: dict[str, Any], actions: list[dict[str, Any]]) -> ActionSpace:
    return ActionSpace.from_actions(
        state["phase"], state["turn_count"], actions, prefix="azul",
    )


def legal_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    if state["status"] != "active" or seat != state["active_seat"]:
        return []
    player = state["players"][seat]
    actions: list[dict[str, Any]] = []
    sources = [factory["id"] for factory in state["factories"]]
    sources.append("center")
    for source in sources:
        tiles = _source_tiles(state, source)
        present = set(_tile_color(tile_id) for tile_id in tiles)
        for color in COLORS:
            if color not in present:
                continue
            for destination in _legal_destinations(player, color):
                actions.append({
                    "type": "draft_tiles",
                    "source": source,
                    "color": color,
                    "destination": destination,
                })
    return _action_space(state, actions).wrapped()


def _claim_start_marker(state: dict[str, Any], seat: int) -> tuple[int | None, bool]:
    if not state["center_has_start_marker"]:
        return None, False
    state["center_has_start_marker"] = False
    floor = state["players"][seat]["floor"]
    if len(floor) < len(FLOOR_PENALTIES):
        floor.append(START_MARKER)
        return len(floor), False
    state["start_marker_holder_seat"] = seat
    return None, True


def _place_on_floor(
    state: dict[str, Any], player: dict[str, Any], tiles: list[str],
) -> tuple[int, int]:
    room = max(0, len(FLOOR_PENALTIES) - len(player["floor"]))
    floor_tiles = tiles[:room]
    lid_tiles = tiles[room:]
    player["floor"].extend(floor_tiles)
    state["lid"].extend(lid_tiles)
    return len(floor_tiles), len(lid_tiles)


def _offer_empty(state: dict[str, Any]) -> bool:
    return not state["center"] and all(
        not factory["tiles"] for factory in state["factories"]
    )


def _connection_length(
    wall: list[list[str | None]], row: int, column: int, dr: int, dc: int,
) -> int:
    length = 1
    r, c = row + dr, column + dc
    while 0 <= r < 5 and 0 <= c < 5 and wall[r][c] is not None:
        length += 1
        r += dr
        c += dc
    r, c = row - dr, column - dc
    while 0 <= r < 5 and 0 <= c < 5 and wall[r][c] is not None:
        length += 1
        r -= dr
        c -= dc
    return length


def _wall_placement_score(
    wall: list[list[str | None]], row: int, column: int,
) -> int:
    horizontal = _connection_length(wall, row, column, 0, 1)
    vertical = _connection_length(wall, row, column, 1, 0)
    if horizontal == 1 and vertical == 1:
        return 1
    return (horizontal if horizontal > 1 else 0) + (vertical if vertical > 1 else 0)


def completed_rows(player: dict[str, Any]) -> int:
    return sum(all(tile is not None for tile in row) for row in player["wall"])


def completed_columns(player: dict[str, Any]) -> int:
    return sum(
        all(player["wall"][row][column] is not None for row in range(5))
        for column in range(5)
    )


def completed_colors(player: dict[str, Any]) -> int:
    completed = 0
    for color in COLORS:
        if all(
            player["wall"][row][WALL_PATTERN[row].index(color)] is not None
            for row in range(5)
        ):
            completed += 1
    return completed


def _resolve_player_board(
    state: dict[str, Any], player: dict[str, Any], events: list[dict[str, Any]],
) -> int | None:
    seat = player["seat"]
    for line in player["pattern_lines"]:
        if len(line["tiles"]) != line["capacity"]:
            continue
        row = line["line"] - 1
        color = _line_color(line)
        if color is None:  # pragma: no cover - a completed line cannot be empty
            raise AssertionError("completed pattern line has no color")
        column = WALL_PATTERN[row].index(color)
        wall_tile, *lid_tiles = line["tiles"]
        player["wall"][row][column] = wall_tile
        state["lid"].extend(lid_tiles)
        line["tiles"] = []
        points = _wall_placement_score(player["wall"], row, column)
        player["score"] += points
        events.append(domain_event(
            "wall_tile_scored",
            seat=seat,
            line=row + 1,
            color=color,
            row=row,
            column=column,
            points=points,
        ))

    score_before = player["score"]
    floor_item_count = len(player["floor"])
    penalty = sum(FLOOR_PENALTIES[:floor_item_count])
    marker_here = START_MARKER in player["floor"]
    for item in player["floor"]:
        if item != START_MARKER:
            state["lid"].append(item)
    player["floor"] = []
    player["score"] = max(0, player["score"] + penalty)
    events.append(domain_event(
        "floor_penalty_applied",
        seat=seat,
        item_count=floor_item_count,
        penalty=penalty,
        score_before=score_before,
        score_after=player["score"],
    ))
    return seat if marker_here else None


def _endgame_bonus(player: dict[str, Any]) -> dict[str, int]:
    rows = completed_rows(player)
    columns = completed_columns(player)
    colors = completed_colors(player)
    row_points = rows * 2
    column_points = columns * 7
    color_points = colors * 10
    return {
        "completed_rows": rows,
        "completed_columns": columns,
        "completed_colors": colors,
        "row_points": row_points,
        "column_points": column_points,
        "color_points": color_points,
        "total": row_points + column_points + color_points,
    }


def _resolve_round(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    next_start = state["start_marker_holder_seat"]
    for player in state["players"]:
        marker_seat = _resolve_player_board(state, player, events)
        if marker_seat is not None:
            if next_start is not None:
                raise AssertionError("start marker has multiple owners")
            next_start = marker_seat
    if next_start is None:
        raise AssertionError("round ended without a start-marker owner")
    state["start_marker_holder_seat"] = next_start
    events.append(domain_event("round_finished", round=state["round"]))

    if any(completed_rows(player) for player in state["players"]):
        for player in state["players"]:
            bonus = _endgame_bonus(player)
            player["score"] += bonus["total"]
            events.append(domain_event(
                "endgame_bonus_scored", seat=player["seat"], **bonus,
            ))
        state["status"] = "finished"
        state["phase"] = "finished"
        events.append(domain_event("match_finished", rankings=rankings(state)))
        return

    state["round"] += 1
    state["active_seat"] = next_start
    state["center_has_start_marker"] = True
    state["start_marker_holder_seat"] = None
    _fill_factories(state, events)
    events.append(domain_event(
        "round_started",
        round=state["round"],
        active_seat=state["active_seat"],
        bag_count=len(state["bag"]),
        lid_count=len(state["lid"]),
    ))


def apply_action(
    state: dict[str, Any], seat: int, action: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    legal = [item["action"] for item in legal_actions(state, seat)]
    canonical = _action_space(state, legal).require(
        action,
        error_factory=RuleError,
        message="action is not legal in the current state",
    )
    next_state = deepcopy(state)
    player = next_state["players"][seat]
    events: list[dict[str, Any]] = [action_accepted(seat, canonical)]
    source = canonical["source"]
    color = canonical["color"]
    source_tiles = list(_source_tiles(next_state, source))
    selected = [tile_id for tile_id in source_tiles if _tile_color(tile_id) == color]
    remainder = [tile_id for tile_id in source_tiles if _tile_color(tile_id) != color]

    if source == "center":
        next_state["center"] = remainder
        floor_position, overflow = _claim_start_marker(next_state, seat)
        if floor_position is not None or overflow:
            events.append(domain_event(
                "start_player_marker_taken",
                seat=seat,
                floor_position=floor_position,
                overflow=overflow,
            ))
    else:
        factory = next(
            row for row in next_state["factories"] if row["id"] == source
        )
        factory["tiles"] = []
        next_state["center"].extend(remainder)
        if remainder:
            events.append(domain_event(
                "factory_remainder_moved",
                source=source,
                counts=_color_counts(remainder),
            ))

    events.append(domain_event(
        "tiles_drafted",
        seat=seat,
        source=source,
        color=color,
        count=len(selected),
    ))

    destination = canonical["destination"]
    pattern_count = 0
    if destination == "floor":
        overflow = selected
    else:
        line_number = int(destination.removeprefix("pattern-line-"))
        line = player["pattern_lines"][line_number - 1]
        room = line["capacity"] - len(line["tiles"])
        placed, overflow = selected[:room], selected[room:]
        line["tiles"].extend(placed)
        pattern_count = len(placed)
    floor_count, lid_count = _place_on_floor(next_state, player, overflow)
    events.append(domain_event(
        "tiles_placed",
        seat=seat,
        destination=destination,
        color=color,
        pattern_count=pattern_count,
        floor_count=floor_count,
        lid_count=lid_count,
    ))

    next_state["turn_count"] += 1
    if _offer_empty(next_state):
        _resolve_round(next_state, events)
    else:
        next_state["active_seat"] = (seat + 1) % next_state["player_count"]
    validate_state(next_state)
    return next_state, events


def score(state: dict[str, Any], seat: int) -> int:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    return state["players"][seat]["score"]


def rankings(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "seat": player["seat"],
            "score": player["score"],
            "completed_rows": completed_rows(player),
            "completed_columns": completed_columns(player),
            "completed_colors": completed_colors(player),
        }
        for player in state["players"]
    ]
    return assign_competition_ranks(
        rows,
        sort_key=lambda row: (-row["score"], -row["completed_rows"], row["seat"]),
        tie_key=lambda row: (row["score"], row["completed_rows"]),
    )


def _wall_view(player: dict[str, Any]) -> list[list[dict[str, Any]]]:
    return [
        [
            {"color": WALL_PATTERN[row][column], "occupied": tile_id is not None}
            for column, tile_id in enumerate(wall_row)
        ]
        for row, wall_row in enumerate(player["wall"])
    ]


def observe(state: dict[str, Any], seat: int) -> dict[str, Any]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    players = []
    for player in state["players"]:
        floor = [
            item if item == START_MARKER else _tile_color(item)
            for item in player["floor"]
        ]
        players.append({
            "seat": player["seat"],
            "score": player["score"],
            "pattern_lines": [
                {
                    "line": line["line"],
                    "capacity": line["capacity"],
                    "color": _line_color(line),
                    "count": len(line["tiles"]),
                    "complete": len(line["tiles"]) == line["capacity"],
                }
                for line in player["pattern_lines"]
            ],
            "wall": _wall_view(player),
            "floor": floor,
            "completed_rows": completed_rows(player),
        })
    return {
        "game": "azul",
        "rules_version": state["rules_version"],
        "implementation_status": "playable_beta",
        "viewer_seat": seat,
        "status": state["status"],
        "phase": state["phase"],
        "round": state["round"],
        "turn_count": state["turn_count"],
        "active_seat": state["active_seat"],
        "bag_count": len(state["bag"]),
        "lid_count": len(state["lid"]),
        "center_has_start_marker": state["center_has_start_marker"],
        "start_marker_holder_seat": state["start_marker_holder_seat"],
        "factories": [
            {"id": factory["id"], "tiles": _color_counts(factory["tiles"])}
            for factory in state["factories"]
        ],
        "center": _color_counts(state["center"]),
        "wall_pattern": [list(row) for row in WALL_PATTERN],
        "players": players,
        "rankings": rankings(state) if state["status"] == "finished" else None,
    }


def validate_state(state: dict[str, Any]) -> None:
    if state.get("schema_version") != SCHEMA_VERSION:
        raise AssertionError("invalid Azul state schema version")
    if state.get("rules_version") != RULES_VERSION:
        raise AssertionError("invalid Azul rules version")
    players = state.get("player_count")
    if players not in FACTORY_COUNTS or len(state.get("players", [])) != players:
        raise AssertionError("invalid Azul player count")
    if state.get("status") not in {"active", "finished"}:
        raise AssertionError("invalid Azul status")
    expected_phase = "factory_offer" if state["status"] == "active" else "finished"
    if state.get("phase") != expected_phase:
        raise AssertionError("invalid Azul phase")
    if not isinstance(state.get("round"), int) or state["round"] < 1:
        raise AssertionError("invalid Azul round")
    if not isinstance(state.get("turn_count"), int) or state["turn_count"] < 0:
        raise AssertionError("invalid Azul turn count")
    if not isinstance(state.get("shuffle_count"), int) or state["shuffle_count"] < 0:
        raise AssertionError("invalid Azul shuffle count")
    if not isinstance(state.get("seed"), int):
        raise AssertionError("invalid Azul seed")
    if not isinstance(state.get("active_seat"), int) or not 0 <= state["active_seat"] < players:
        raise AssertionError("invalid Azul active seat")

    factories = state.get("factories", [])
    expected_ids = [f"factory-{index:02d}" for index in range(1, FACTORY_COUNTS[players] + 1)]
    if [factory.get("id") for factory in factories] != expected_ids:
        raise AssertionError("invalid Azul factories")
    if any(len(factory.get("tiles", [])) > FACTORY_SIZE for factory in factories):
        raise AssertionError("Azul factory exceeds four tiles")

    tile_zones: list[list[str]] = [state.get("bag", []), state.get("lid", []), state.get("center", [])]
    tile_zones.extend(factory["tiles"] for factory in factories)
    marker_count = 0
    for expected_seat, player in enumerate(state["players"]):
        if player.get("seat") != expected_seat:
            raise AssertionError("invalid Azul player seat")
        if not isinstance(player.get("score"), int) or player["score"] < 0:
            raise AssertionError("invalid Azul score")
        lines = player.get("pattern_lines", [])
        if len(lines) != 5:
            raise AssertionError("Azul player must have five pattern lines")
        for line_number, line in enumerate(lines, 1):
            if line.get("line") != line_number or line.get("capacity") != line_number:
                raise AssertionError("invalid Azul pattern line")
            tiles = line.get("tiles", [])
            if len(tiles) > line_number:
                raise AssertionError("Azul pattern line exceeds capacity")
            colors = {_tile_color(tile_id) for tile_id in tiles}
            if len(colors) > 1:
                raise AssertionError("Azul pattern line must be monochrome")
            if colors and _wall_has_color(player, line_number - 1, next(iter(colors))):
                raise AssertionError("Azul pattern color already exists in wall row")
            tile_zones.append(tiles)
        wall = player.get("wall", [])
        if len(wall) != 5 or any(len(row) != 5 for row in wall):
            raise AssertionError("Azul wall must be five by five")
        for row in range(5):
            for column in range(5):
                tile_id = wall[row][column]
                if tile_id is not None:
                    if _tile_color(tile_id) != WALL_PATTERN[row][column]:
                        raise AssertionError("Azul wall tile is in the wrong color cell")
                    tile_zones.append([tile_id])
        floor = player.get("floor", [])
        if len(floor) > len(FLOOR_PENALTIES):
            raise AssertionError("Azul floor exceeds seven positions")
        if floor.count(START_MARKER) > 1:
            raise AssertionError("Azul floor contains duplicate start marker")
        marker_count += floor.count(START_MARKER)
        tile_zones.append([item for item in floor if item != START_MARKER])

    try:
        validate_unique_items(tile_zones, expected_count=TOTAL_TILES, label="Azul tiles")
    except AssertionError as error:
        raise AssertionError("Azul tile conservation failed") from error
    if any(tile_id not in TILES for zone in tile_zones for tile_id in zone):
        raise AssertionError("Azul state contains an unknown tile")

    center_marker = state.get("center_has_start_marker")
    holder = state.get("start_marker_holder_seat")
    if not isinstance(center_marker, bool):
        raise AssertionError("invalid Azul center marker flag")
    holder_valid = isinstance(holder, int) and not isinstance(holder, bool) and 0 <= holder < players
    valid_marker_state = (
        (center_marker and marker_count == 0 and holder is None)
        or (not center_marker and marker_count == 1 and holder is None)
        or (not center_marker and marker_count == 0 and holder_valid)
    )
    if not valid_marker_state:
        raise AssertionError("Azul start marker must have exactly one location")

    if state["status"] == "active" and _offer_empty(state):
        raise AssertionError("active Azul state has no tiles in the factory offer")
    if state["status"] == "finished" and not any(
        completed_rows(player) for player in state["players"]
    ):
        raise AssertionError("finished Azul state has no completed horizontal row")
