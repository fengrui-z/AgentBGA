"""Reviewed compiler for the 32 base-game Conservation Project faces."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


_BASE_ICON_BY_ID = {
    "103": "africa", "104": "americas", "105": "australia",
    "106": "asia", "107": "europe", "108": "primate",
    "109": "reptile", "110": "predator", "111": "herbivore",
    "112": "bird",
}
_RELEASE_ICON_BY_ID = {
    "113": "europe", "114": "americas", "115": "asia",
    "116": "africa", "117": "australia", "118": "predator",
    "119": "bird", "120": "herbivore", "121": "reptile",
    "122": "primate",
}
_BREEDING_ICON_BY_ID = {
    "123": "bird", "124": "predator", "125": "reptile",
    "126": "herbivore", "127": "primate",
}


def _compare(path: str, threshold: int) -> dict[str, Any]:
    return {
        "op": "compare",
        "args": {
            "left": {"ref": f"actor.{path}"},
            "operator": ">=",
            "right": threshold,
        },
    }


def _level_id(index: int, tier: Mapping[str, Any]) -> str:
    if "support_slot" in tier:
        return f"slot-{int(tier['support_slot'])}"
    return ("high", "middle", "low")[index]


def compile_project_facts(row: Mapping[str, Any]) -> dict[str, Any]:
    """Compile all printed tiers and project-specific selector metadata."""
    component_id = str(row.get("id", ""))
    raw_tiers = row.get("tiers")
    if not isinstance(raw_tiers, list) or len(raw_tiers) != 3:
        raise ValueError(f"project {component_id} must contain exactly three tiers")
    levels: list[dict[str, Any]] = []
    release_levels: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_tiers):
        if not isinstance(raw, Mapping):
            raise ValueError(f"project {component_id} tier {index} must be an object")
        requirements: list[dict[str, Any]] = []
        if component_id == "101":
            requirements.append(_compare(
                "distinct_animal_category_count", int(raw["requirement"]),
            ))
        elif component_id == "102":
            requirements.append(_compare(
                "distinct_continent_count", int(raw["requirement"]),
            ))
        elif component_id in _BASE_ICON_BY_ID:
            requirements.append({
                "op": "has_icon",
                "args": {
                    "icon": _BASE_ICON_BY_ID[component_id],
                    "count": int(raw["requirement"]),
                },
            })
        elif component_id == "128":
            requirements.append(_compare("water_icon_total", int(raw["requirement"])))
        elif component_id == "129":
            requirements.append(_compare("rock_icon_total", int(raw["requirement"])))
        elif component_id == "130":
            requirements.append(_compare("small_animal_count", int(raw["requirement"])))
        elif component_id == "131":
            requirements.append(_compare("large_animal_count", int(raw["requirement"])))
        elif component_id == "132":
            requirements.append({
                "op": "has_icon",
                "args": {"icon": "science", "count": int(raw["requirement"])},
            })
        level: dict[str, Any] = {
            "id": _level_id(index, raw),
            "requirements": requirements,
            "conservation": int(raw["conservation"]),
            "reputation": int(raw.get("reputation", 0)),
        }
        if component_id in _RELEASE_ICON_BY_ID:
            size = str(raw["animal_size"])
            minimum, maximum = {
                "4+": (4, 5), "3": (3, 3), "1-2": (1, 2),
            }[size]
            release_levels[level["id"]] = {
                "icon": _RELEASE_ICON_BY_ID[component_id],
                "minimum_size": minimum,
                "maximum_size": maximum,
            }
        levels.append(level)
    result: dict[str, Any] = {
        "levels": levels,
        "compiled_tier_count": len(levels),
        "unresolved_tiers": [],
        "semantic_compile_status": "compiled",
    }
    if component_id in _RELEASE_ICON_BY_ID:
        result.update({
            "project_type": "release",
            "release_icon": _RELEASE_ICON_BY_ID[component_id],
            "release_levels": release_levels,
            "introduction_effects": [{
                "op": "move_track", "timing": "on_support",
                "args": {"track": "reputation", "amount": 1},
            }],
        })
    elif component_id in _BREEDING_ICON_BY_ID:
        result.update({
            "project_type": "breeding",
            "breeding_icon": _BREEDING_ICON_BY_ID[component_id],
        })
    return deepcopy(result)


def compiled_project_tier_count(row: Mapping[str, Any]) -> int:
    return len(compile_project_facts(row)["levels"])
