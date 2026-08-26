"""Audited base-game Sponsor facts missing from the supplied transcription.

The user dataset deliberately used placeholders for card-face track conditions.
This small correction layer records the exact printed values without rewriting
the supplied reference artifact.  It also marks the fifteen cards whose play
requires a fixed unique-building placement workflow.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


UNIQUE_BUILDING_SPONSORS = frozenset(str(value) for value in range(243, 258))

UNIQUE_BUILDING_RULES: Mapping[str, Mapping[str, Any]] = {
    "243": {"size": 3, "adjacent_terrain": "rock", "adjacent_count": 1},
    "244": {"size": 4, "adjacent_terrain": "water", "adjacent_count": 1},
    "245": {"size": 4, "adjacent_terrain": "water", "adjacent_count": 2},
    "246": {"size": 4, "adjacent_terrain": "rock", "adjacent_count": 2},
    "247": {"size": 4, "adjacent_terrain": "rock", "adjacent_count": 1},
    "248": {"size": 4},
    "249": {"size": 3},
    "250": {"size": 4, "adjacent_terrain": "water", "adjacent_count": 1},
    "251": {"size": 4},
    "252": {"size": 4, "adjacent_terrain": "rock", "adjacent_count": 1},
    "253": {"size": 4},
    "254": {"size": 3, "border_count": 2},
    "255": {"size": 2, "adjacent_terrain": "rock", "adjacent_count": 1},
    "256": {"size": 2, "adjacent_terrain": "water", "adjacent_count": 1},
    "257": {"size": 2, "border_count": 2, "ignore_existing_adjacency": True},
}

_APPEAL_MAXIMUM_25 = frozenset({"207", "222", "258", "259", "260", "264"})
_REPUTATION_MINIMUM = {
    "227": 6,
    "228": 3,
    "243": 3,
    "244": 3,
    "245": 3,
    "263": 6,
}

DIRECT_REWARD_OVERRIDES: Mapping[str, Mapping[str, int]] = {
    "254": {"reputation": 1, "conservation": 1},
    "255": {"appeal": 4},
    "256": {"appeal": 4},
    "261": {"appeal": 1, "conservation": 1},
}

PRINTED_ICON_OVERRIDES: Mapping[str, tuple[str, ...]] = {
    "241": ("water",),
    "242": ("rock",),
    "243": ("herbivore",),
    "244": ("bird",),
    "245": ("water",),
    "246": ("rock",),
    "247": ("primate",),
    "248": ("primate",),
    "249": ("bird",),
    "250": ("reptile",),
    "251": ("bear", "predator"),
    "252": ("predator",),
    "253": ("herbivore",),
    "258": ("bird",),
    "259": ("reptile",),
    "260": ("herbivore",),
    "264": ("primate",),
}


def compile_sponsor_requirement(component_id: str, value: str) -> dict[str, Any] | None:
    """Compile an audited placeholder condition, or return ``None``."""
    if value == "Appeal threshold" and component_id in _APPEAL_MAXIMUM_25:
        return {
            "op": "compare",
            "args": {
                "left": {"ref": "actor.tracks.appeal"},
                "operator": "<=",
                "right": 25,
            },
        }
    if value == "Reputation threshold" and component_id in _REPUTATION_MINIMUM:
        return {
            "op": "compare",
            "args": {
                "left": {"ref": "actor.tracks.reputation"},
                "operator": ">=",
                "right": _REPUTATION_MINIMUM[component_id],
            },
        }
    return None


def unresolved_sponsor_requirements(row: Mapping[str, Any]) -> list[str]:
    component_id = str(row.get("id", ""))
    return [
        value for value in row.get("requirements", [])
        if value in {"Appeal threshold", "Reputation threshold"}
        and compile_sponsor_requirement(component_id, value) is None
    ]


def corrected_direct_rewards(row: Mapping[str, Any]) -> dict[str, int]:
    rewards = deepcopy(dict(row.get("direct_rewards", {})))
    rewards.update(DIRECT_REWARD_OVERRIDES.get(str(row.get("id", "")), {}))
    return rewards


def unique_building_rules(component_id: str) -> dict[str, Any] | None:
    rules = UNIQUE_BUILDING_RULES.get(component_id)
    if rules is None:
        return None
    return {
        "building_type": f"unique_sponsor_{component_id}",
        **deepcopy(dict(rules)),
    }


def corrected_printed_icons(component_id: str, icons: Mapping[str, int]) -> dict[str, int]:
    result = deepcopy(dict(icons))
    for icon in PRINTED_ICON_OVERRIDES.get(component_id, ()):
        result[icon] = result.get(icon, 0) + 1
    return result
