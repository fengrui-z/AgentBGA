"""Structured Map 0 geometry and polyhex building templates.

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
    ("reptile_house", 5): ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1)),
    ("large_bird_aviary", 5): ((0, 0), (1, 0), (1, 1), (2, 1), (2, 2)),
    # Sponsor 243-257 unique buildings. These are mechanics-only axial
    # transcriptions of the printed silhouettes. They may be rotated but never
    # flipped, matching the physical tiles.
    ("unique_sponsor_243", 3): ((0, 0), (-1, 0), (1, -1)),
    ("unique_sponsor_244", 4): ((0, 0), (-1, 0), (0, -1), (0, 1)),
    ("unique_sponsor_245", 4): ((0, 0), (-1, 0), (1, 0), (1, 1)),
    ("unique_sponsor_246", 4): ((0, 0), (1, 0), (2, 0), (3, 0)),
    ("unique_sponsor_247", 4): ((0, 0), (-1, 0), (1, -1), (0, 1)),
    ("unique_sponsor_248", 4): ((0, 0), (-1, 0), (0, -1), (1, -1)),
    ("unique_sponsor_249", 3): ((0, 0), (1, 0), (2, 0)),
    ("unique_sponsor_250", 4): ((0, 0), (-1, 0), (0, -1), (0, 1)),
    ("unique_sponsor_251", 4): ((0, 0), (-1, 1), (1, -1), (2, -1)),
    ("unique_sponsor_252", 4): ((0, 0), (-1, 0), (1, -1), (2, -2)),
    ("unique_sponsor_253", 4): ((0, 0), (-1, 0), (0, 1), (1, 1)),
    ("unique_sponsor_254", 3): ((0, 0), (-1, 0), (1, -1)),
    ("unique_sponsor_255", 2): ((0, 0), (1, 0)),
    ("unique_sponsor_256", 2): ((0, 0), (1, 0)),
    ("unique_sponsor_257", 2): ((0, 0), (1, 0)),
}

# The supplied physical size-four enclosure reference contains a second fixed
# footprint that is not a rotation of the compact rhombus above.  Keep it as a
# named template rather than weakening placement validation to arbitrary
# connected four-hex shapes.
_ALTERNATE_BUILDING_SHAPES: dict[
    tuple[str, int], tuple[tuple[tuple[int, int], ...], ...]
] = {
    ("standard_enclosure", 4): (
        ((0, 0), (0, 1), (1, -1), (1, 1)),
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
    templates = (template, *_ALTERNATE_BUILDING_SHAPES.get((building_type, size), ()))
    for template_index, source_template in enumerate(templates):
        rotated = source_template
        for rotation in range(6):
            signature = _normalise(rotated)
            if signature not in seen:
                seen.add(signature)
                suffix = "" if template_index == 0 else f"-variant-{template_index + 1}"
                variants.append({
                    "shape_id": f"{building_type}-{size}{suffix}",
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
    return any(
        normalised == _normalise(variant["cells"])
        for variant in building_shape_variants(building["type"], building["size"])
    )


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
