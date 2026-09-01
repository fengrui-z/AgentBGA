"""Structured Map 0 / Map A geometry and polyhex building templates.

The coordinate data is a mechanics-first transcription of the Map 0
reference supplied for this project. It deliberately uses original colours,
labels, and generated geometry instead of publisher artwork.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


# Map 0 is a 58-hex flat-top axial footprint.  Rows are inclusive axial-q
# ranges keyed by r; (0, 0) is the central 10-money placement bonus.
_MAP_ROWS = {
    -4: (3, 4),
    -3: (1, 4),
    -2: (-1, 4),
    -1: (-3, 4),
    0: (-4, 4),
    1: (-4, 4),
    2: (-4, 3),
    3: (-4, 1),
    4: (-4, -1),
    5: (-4, -3),
}

_WATER = {
    (-3, -1), (-4, 0), (-4, 1), (-1, -2), (1, -1),
    (-2, 2), (-3, 4), (4, 0), (4, 1), (3, 2),
}
_ROCK = {
    (-2, -1), (-1, -1), (2, -2), (1, 1), (2, 1),
    (2, 2), (1, 3), (-4, 5), (-3, 5),
}
_PLACEMENT_BONUSES: dict[tuple[int, int], dict[str, Any]] = {
    (-3, 0): {"type": "take_card", "amount": 1},
    (-2, 1): {"type": "take_card", "amount": 1},
    (-1, 4): {"type": "take_card", "amount": 1},
    (0, -2): {"type": "gain_x_token", "amount": 1},
    (-1, 2): {"type": "gain_x_token", "amount": 1},
    (1, 2): {"type": "gain_x_token", "amount": 1},
    (3, -3): {"type": "gain_money", "amount": 5},
    (0, 0): {"type": "gain_money", "amount": 10},
    (4, -1): {"type": "gain_money", "amount": 5},
    (-4, 4): {"type": "gain_reputation", "amount": 2},
    (3, 1): {"type": "gain_reputation", "amount": 2},
    (1, 0): {"type": "clever", "target_strength": 1},
}
_BUILD_II_CELLS = {(3, -2), (2, -1)}


# Map A uses the same 58-space player-board rules and building templates, but
# has its own footprint, terrain, placement rewards, Build-II spaces, and two
# printed setup buildings.  Coordinates are transcribed in the same flat-top
# axial system as Map 0, with the central X-token reward at (0, 0).
_MAP_A_ROWS = {
    -5: (3, 4),
    -4: (1, 4),
    -3: (-1, 4),
    -2: (-3, 4),
    -1: (-4, 4),
    0: (-4, 4),
    1: (-4, 3),
    2: (-4, 1),
    3: (-4, -1),
    4: (-4, -3),
}
_MAP_A_WATER = {
    (-2, -2), (0, -3), (3, -5), (4, -5), (4, -4),
    (2, -1), (1, 0), (-2, 3), (-1, 3),
}
_MAP_A_ROCK = {
    (-3, -2), (-3, -1), (-2, -1), (-1, -3),
    (1, -2), (2, 0), (-3, 4),
}
_MAP_A_PLACEMENT_BONUSES: dict[tuple[int, int], dict[str, Any]] = {
    (-4, -1): {"type": "gain_reputation", "amount": 2},
    (3, 0): {"type": "gain_reputation", "amount": 2},
    (-4, 0): {"type": "gain_x_token", "amount": 1},
    (0, 0): {"type": "gain_x_token", "amount": 1},
    (1, -4): {"type": "gain_x_token", "amount": 1},
    (-2, 0): {"type": "take_card", "amount": 1},
    (1, -1): {"type": "take_card", "amount": 1},
    (1, 1): {"type": "take_card", "amount": 1},
    (-1, -2): {"type": "gain_money", "amount": 5},
    (-2, 2): {"type": "gain_money", "amount": 5},
    (4, -3): {"type": "gain_money", "amount": 10},
    (3, -4): {"type": "gain_association_worker", "amount": 1},
}
_MAP_A_BUILD_II_CELLS = {(3, 1), (4, 0)}
_MAP_A_STARTING_ENCLOSURE = ((-4, 3), (-4, 4), (-3, 3))
_MAP_A_STARTING_KIOSK = (-4, 2)

SUPPORTED_MAP_IDS = ("map-0", "map-a")


# Canonical polyhexes. Rotation zero is presentation-friendly; rules never rely
# on a particular orientation because all unique sixty-degree rotations are used.
_BUILDING_SHAPES: dict[tuple[str, int], tuple[tuple[int, int], ...]] = {
    ("pavilion", 1): ((0, 0),),
    ("kiosk", 1): ((0, 0),),
    ("standard_enclosure", 1): ((0, 0),),
    ("standard_enclosure", 2): ((0, 0), (1, 0)),
    ("standard_enclosure", 3): ((0, 0), (1, 0), (0, 1)),
    ("standard_enclosure", 4): ((0, 0), (1, 0), (0, 1), (-1, 1)),
    # The size-five standard enclosure is the two-column 2+3 polyhex shown on
    # the player board, not the branched Large Bird Aviary footprint.
    ("standard_enclosure", 5): ((0, 0), (0, 1), (1, -1), (1, 0), (1, 1)),
    ("petting_zoo", 3): ((0, 0), (0, 1), (1, 1)),
    # The two five-space special enclosures have different silhouettes on the
    # player board.  Reptile House is the symmetric bow-tie: a centre hex with
    # two cells on either side.  Large Bird Aviary has three cells around its
    # centre plus a fourth cell extending the lower branch.  Keeping these as
    # separate canonical polyhexes is important: both used to be approximated
    # by compact/zig-zag shapes that did not match the physical tiles.
    ("reptile_house", 5): (
        (0, 0), (-1, 0), (-1, 1), (1, -1), (1, 0),
    ),
    ("large_bird_aviary", 5): (
        (0, 0), (-1, 0), (-1, 1), (1, -1), (0, 1),
    ),
    # Sponsor 243-257 unique buildings. These are mechanics-only axial
    # transcriptions of the printed silhouettes. They may be rotated but never
    # flipped, matching the physical tiles.
    ("unique_sponsor_243", 3): ((0, 0), (-1, 0), (1, -1)),
    ("unique_sponsor_244", 4): ((0, 0), (-1, 0), (0, -1), (0, 1)),
    ("unique_sponsor_245", 4): ((0, 0), (-1, 0), (1, 0), (1, 1)),
    ("unique_sponsor_246", 4): ((0, 0), (1, 0), (2, 0), (3, 0)),
    ("unique_sponsor_247", 4): ((0, 0), (-1, 0), (-1, 1), (1, 0)),
    # Rhesus Monkey Park is the four-hex bent chain printed on card 248:
    # one step north-east followed by two south-east steps.  It is not the
    # compact two-by-two zig-zag used by earlier development builds.
    ("unique_sponsor_248", 4): ((0, 0), (1, -1), (2, -1), (3, -1)),
    ("unique_sponsor_249", 3): ((0, 0), (1, 0), (2, 0)),
    ("unique_sponsor_250", 4): ((0, 0), (-1, 0), (1, -1), (0, 1)),
    ("unique_sponsor_251", 4): ((0, 0), (1, -1), (2, -1), (3, -2)),
    ("unique_sponsor_252", 4): ((0, 0), (-1, 0), (1, -1), (2, -2)),
    ("unique_sponsor_253", 4): ((0, 0), (1, 0), (2, -1), (3, -1)),
    ("unique_sponsor_254", 3): ((0, 0), (-1, 0), (1, -1)),
    ("unique_sponsor_255", 2): ((0, 0), (1, 0)),
    ("unique_sponsor_256", 2): ((0, 0), (1, 0)),
    ("unique_sponsor_257", 2): ((0, 0), (1, 0)),
}


# Base-game Sponsor cards 243-257 each place one mandatory unique building.
# Terrain requirements count distinct adjacent terrain hexes. Tiles rotate in
# sixty-degree steps but are never reflected.
_UNIQUE_SPONSOR_BUILDINGS: dict[int, dict[str, Any]] = {
    243: {"name": "Meerkat Den", "building_type": "unique_sponsor_243", "size": 3,
          "placement": {"min_adjacent_rock_spaces": 1}},
    244: {"name": "Penguin Pool", "building_type": "unique_sponsor_244", "size": 4,
          "placement": {"min_adjacent_water_spaces": 1}},
    245: {"name": "Aquarium", "building_type": "unique_sponsor_245", "size": 4,
          "placement": {"min_adjacent_water_spaces": 2}},
    246: {"name": "Aerial Cableway", "building_type": "unique_sponsor_246", "size": 4,
          "placement": {"min_adjacent_rock_spaces": 2}},
    247: {"name": "Baboon Rock", "building_type": "unique_sponsor_247", "size": 4,
          "placement": {"min_adjacent_rock_spaces": 1}},
    248: {"name": "Rhesus Monkey Park", "building_type": "unique_sponsor_248", "size": 4,
          "placement": {}},
    249: {"name": "Barred Owl Hut", "building_type": "unique_sponsor_249", "size": 3,
          "placement": {}},
    250: {"name": "Sea Turtle Tank", "building_type": "unique_sponsor_250", "size": 4,
          "placement": {"min_adjacent_water_spaces": 1}},
    251: {"name": "Polar Bear Exhibit", "building_type": "unique_sponsor_251", "size": 4,
          "placement": {"min_adjacent_water_spaces": 1}},
    252: {"name": "Spotted Hyena Compound", "building_type": "unique_sponsor_252", "size": 4,
          "placement": {"min_adjacent_rock_spaces": 1}},
    253: {"name": "Okapi Stable", "building_type": "unique_sponsor_253", "size": 4,
          "placement": {}},
    254: {"name": "Zoo School", "building_type": "unique_sponsor_254", "size": 3,
          "placement": {"min_border_spaces": 2}},
    255: {"name": "Adventure Playground", "building_type": "unique_sponsor_255", "size": 2,
          "placement": {"min_adjacent_rock_spaces": 1}},
    256: {"name": "Water Playground", "building_type": "unique_sponsor_256", "size": 2,
          "placement": {"min_adjacent_water_spaces": 1}},
    257: {"name": "Side Entrance", "building_type": "unique_sponsor_257", "size": 2,
          "placement": {"min_border_spaces": 2,
                        "requires_adjacency_to_existing_building": False}},
}


def unique_sponsor_building_spec(card_id: int) -> dict[str, Any] | None:
    """Return a defensive, self-contained unique-building specification."""

    spec = _UNIQUE_SPONSOR_BUILDINGS.get(card_id)
    if spec is None:
        return None
    result = deepcopy(spec)
    result["card_id"] = card_id
    result["canonical_cells"] = deepcopy(
        _BUILDING_SHAPES[(result["building_type"], result["size"])]
    )
    return result


def unique_sponsor_shape_variants(card_id: int) -> list[dict[str, Any]]:
    """Return every distinct rotation of Sponsor ``card_id``'s building."""

    spec = _UNIQUE_SPONSOR_BUILDINGS.get(card_id)
    if spec is None:
        return []
    return building_shape_variants(spec["building_type"], spec["size"])

# Older development builds could generate this branched size-four footprint.
# It is retained only to keep already-running matches loadable; it must never
# be offered as a new placement because the standard size-four enclosure is the
# compact rhombus declared in ``_BUILDING_SHAPES``.
_LEGACY_ACCEPTED_BUILDING_SHAPES: dict[
    tuple[str, int], tuple[tuple[tuple[int, int], ...], ...]
] = {
    ("standard_enclosure", 4): (
        ((0, 0), (0, 1), (1, -1), (1, 1)),
    ),
    # Compatibility for matches created before the special-enclosure
    # silhouettes were corrected.  These footprints validate when an old
    # match is loaded, but ``building_shape_variants`` never offers them for a
    # new placement.
    ("reptile_house", 5): (
        ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1)),
    ),
    ("large_bird_aviary", 5): (
        ((0, 0), (1, 0), (1, 1), (2, 1), (2, 2)),
    ),
    ("unique_sponsor_248", 4): (
        ((0, 0), (-1, 0), (0, -1), (1, -1)),
    ),
    ("unique_sponsor_247", 4): (
        ((0, 0), (-1, 0), (1, -1), (0, 1)),
    ),
    ("unique_sponsor_250", 4): (
        ((0, 0), (-1, 0), (0, -1), (0, 1)),
    ),
    ("unique_sponsor_251", 4): (
        ((0, 0), (-1, 1), (1, -1), (2, -1)),
    ),
    ("unique_sponsor_253", 4): (
        ((0, 0), (-1, 0), (0, 1), (1, 1)),
    ),
}


def _normalise(cells: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    values = tuple(cells)
    minimum_q = min(q for q, _ in values)
    minimum_r = min(r for _, r in values)
    return tuple(sorted((q - minimum_q, r - minimum_r) for q, r in values))


def _rotate(cell: tuple[int, int]) -> tuple[int, int]:
    """Rotate one axial coordinate clockwise by sixty degrees."""

    q, r = cell
    return -r, q + r


def building_shape_variants(building_type: str, size: int) -> list[dict[str, Any]]:
    """Return all unique rotations for a fixed building polyhex."""

    template = _BUILDING_SHAPES.get((building_type, size))
    if template is None:
        return []
    variants: list[dict[str, Any]] = []
    seen: set[tuple[tuple[int, int], ...]] = set()
    rotated = template
    for rotation in range(6):
        signature = _normalise(rotated)
        if signature not in seen:
            seen.add(signature)
            variants.append({
                "shape_id": f"{building_type}-{size}",
                "rotation": rotation,
                # Keep the template's (0, 0) member as the placement anchor.
                # Normalising each axis independently can create an anchor that
                # is not part of the polyhex and drops otherwise legal placements.
                "cells": tuple(sorted(rotated)),
            })
        rotated = tuple(_rotate(cell) for cell in rotated)
    return variants


def valid_building_shape(building: dict[str, Any]) -> bool:
    """Check that a placed building matches one of its canonical rotations."""

    cells = [(cell["q"], cell["r"]) for cell in building["cells"]]
    if len(cells) != building["size"] or len(cells) != len(set(cells)):
        return False
    normalised = _normalise(cells)
    if any(
        normalised == _normalise(variant["cells"])
        for variant in building_shape_variants(building["type"], building["size"])
    ):
        return True
    return any(
        normalised == _normalise(rotated)
        for template in _LEGACY_ACCEPTED_BUILDING_SHAPES.get(
            (building["type"], building["size"]), ()
        )
        for rotated in _rotations(template)
    )


def _rotations(
    template: tuple[tuple[int, int], ...],
) -> tuple[tuple[tuple[int, int], ...], ...]:
    result = []
    rotated = template
    for _ in range(6):
        result.append(rotated)
        rotated = tuple(_rotate(cell) for cell in rotated)
    return tuple(result)


def map_zero() -> dict[str, Any]:
    """Return a fresh, serialisable Map 0 instance for one player."""

    coordinates = {
        (q, r)
        for r, (minimum_q, maximum_q) in _MAP_ROWS.items()
        for q in range(minimum_q, maximum_q + 1)
    }
    cells: list[dict[str, Any]] = []
    for q, r in sorted(coordinates, key=lambda value: (value[1], value[0])):
        terrain = "water" if (q, r) in _WATER else "rock" if (q, r) in _ROCK else "buildable"
        cell: dict[str, Any] = {"q": q, "r": r, "terrain": terrain}
        if (q, r) in _PLACEMENT_BONUSES:
            cell["placement_bonus"] = deepcopy(_PLACEMENT_BONUSES[(q, r)])
        if (q, r) in _BUILD_II_CELLS:
            cell["requires_build_upgrade"] = True
        cells.append(cell)

    return {
        "schema_version": "agentbga.ark_nova.map.v3",
        "id": "map-0",
        "name": "Map 0",
        "coordinate_system": "flat_top_axial",
        "origin_landmark": "central_money_10",
        "geometry_status": "reference_transcribed_map_zero_geometry",
        "reference_status": "mechanics_transcription_from_supplied_map_zero_reference",
        "terrain_legend": ["buildable", "water", "rock"],
        "cells": cells,
        "placement_bonus_slots": [
            {"q": q, "r": r, "effect": deepcopy(effect)}
            for (q, r), effect in sorted(_PLACEMENT_BONUSES.items())
        ],
        "conservation_reward_slots": [
            {"milestone": 2, "kind": "action_upgrade"},
            {"milestone": 5, "kind": "conservation_bonus"},
            {"milestone": 8, "kind": "conservation_bonus"},
            {"milestone": 10, "kind": "final_card_choice"},
        ],
        "completion_reward": {"type": "gain_appeal", "amount": 7},
        "completion_reward_claimed": False,
        "buildings": [],
        "next_building_id": 1,
    }


def map_a() -> dict[str, Any]:
    """Return a fresh, serialisable Map A instance for one player.

    Map A's printed setup advantage is represented directly in ``buildings``:
    an empty size-three standard enclosure and a kiosk, both free and already
    placed.  They therefore participate in normal occupancy, connectivity,
    and Break-income calculations without a setup-only rules branch.
    """

    coordinates = {
        (q, r)
        for r, (minimum_q, maximum_q) in _MAP_A_ROWS.items()
        for q in range(minimum_q, maximum_q + 1)
    }
    cells: list[dict[str, Any]] = []
    for q, r in sorted(coordinates, key=lambda value: (value[1], value[0])):
        terrain = (
            "water" if (q, r) in _MAP_A_WATER
            else "rock" if (q, r) in _MAP_A_ROCK
            else "buildable"
        )
        cell: dict[str, Any] = {"q": q, "r": r, "terrain": terrain}
        if (q, r) in _MAP_A_PLACEMENT_BONUSES:
            cell["placement_bonus"] = deepcopy(_MAP_A_PLACEMENT_BONUSES[(q, r)])
        if (q, r) in _MAP_A_BUILD_II_CELLS:
            cell["requires_build_upgrade"] = True
        cells.append(cell)

    buildings = [
        {
            "id": "building-1",
            "type": "standard_enclosure",
            "size": 3,
            "shape_id": "standard_enclosure-3",
            "rotation": 0,
            "occupied": False,
            "used_capacity": 0,
            "animal_ids": [],
            "cells": [{"q": q, "r": r} for q, r in _MAP_A_STARTING_ENCLOSURE],
            "placed_during_setup": True,
            "cost_paid": 0,
            "source": "map_a_setup",
        },
        {
            "id": "building-2",
            "type": "kiosk",
            "size": 1,
            "shape_id": "kiosk-1",
            "rotation": 0,
            "occupied": False,
            "cells": [{"q": _MAP_A_STARTING_KIOSK[0], "r": _MAP_A_STARTING_KIOSK[1]}],
            "placed_during_setup": True,
            "cost_paid": 0,
            "source": "map_a_setup",
        },
    ]
    return {
        "schema_version": "agentbga.ark_nova.map.v3",
        "id": "map-a",
        "name": "Map A",
        "coordinate_system": "flat_top_axial",
        "origin_landmark": "central_x_token_bonus",
        "geometry_status": "reference_transcribed_map_a_geometry",
        "reference_status": "mechanics_transcription_from_supplied_map_a_reference",
        "terrain_legend": ["buildable", "water", "rock"],
        "cells": cells,
        "placement_bonus_slots": [
            {"q": q, "r": r, "effect": deepcopy(effect)}
            for (q, r), effect in sorted(_MAP_A_PLACEMENT_BONUSES.items())
        ],
        "build_upgrade_restricted_cells": [
            {"q": q, "r": r} for q, r in sorted(_MAP_A_BUILD_II_CELLS)
        ],
        "setup_rule": {
            "type": "preplaced_buildings",
            "cost": 0,
            "buildings": deepcopy(buildings),
        },
        "conservation_reward_slots": [
            {"milestone": 2, "kind": "action_upgrade"},
            {"milestone": 5, "kind": "conservation_bonus"},
            {"milestone": 8, "kind": "conservation_bonus"},
            {"milestone": 10, "kind": "final_card_choice"},
        ],
        "completion_reward": {"type": "gain_appeal", "amount": 7},
        "completion_reward_claimed": False,
        "buildings": buildings,
        "next_building_id": 3,
    }


def normalize_map_id(value: object = "map-0") -> str:
    """Return the canonical supported map ID for setup/user input."""

    aliases = {"0": "map-0", "map-0": "map-0", "a": "map-a", "map-a": "map-a"}
    try:
        return aliases[str(value).strip().lower()]
    except KeyError as error:
        raise ValueError("map must be map-0 or map-a") from error


def map_for_id(value: object = "map-0") -> dict[str, Any]:
    """Create a fresh supported zoo map from a setup identifier."""

    map_id = normalize_map_id(value)
    return map_zero() if map_id == "map-0" else map_a()
