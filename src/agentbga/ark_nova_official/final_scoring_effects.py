"""Reviewed compiler and executor for the 11 base-game Final Scoring cards."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from ..mechanics import axial_hex_neighbors


_THRESHOLD_METRICS = {
    "001": "large_animal_count",
    "002": "small_animal_count",
    "003": "research_icon_count",
    "005": "supported_project_count",
    "006": "empty_building_space_count",
    "007": "reputation",
    "008": "sponsor_card_count",
    "010": "rock_icon_count",
    "011": "water_icon_count",
}


def compile_final_scoring_facts(row: Mapping[str, Any]) -> dict[str, Any]:
    """Compile one structured transcription into a closed scoring expression."""
    component_id = str(row.get("id", ""))
    raw_tiers = row.get("tiers")
    if not isinstance(raw_tiers, list):
        raise ValueError(f"Final Scoring card {component_id} tiers must be an array")
    if component_id in _THRESHOLD_METRICS:
        if len(raw_tiers) != 4:
            raise ValueError(f"Final Scoring card {component_id} must contain four thresholds")
        thresholds = []
        for tier in raw_tiers:
            if not isinstance(tier, Mapping):
                raise ValueError(f"Final Scoring card {component_id} tier must be an object")
            requirement = tier.get("requirement")
            conservation = tier.get("conservation")
            if (
                not isinstance(requirement, int) or isinstance(requirement, bool)
                or not isinstance(conservation, int) or isinstance(conservation, bool)
            ):
                raise ValueError(f"Final Scoring card {component_id} threshold must be numeric")
            thresholds.append({
                "requirement": requirement,
                "conservation": conservation,
            })
        scoring = {
            "mode": "threshold",
            "metric": _THRESHOLD_METRICS[component_id],
            "thresholds": thresholds,
        }
    elif component_id == "004":
        if len(raw_tiers) != 2:
            raise ValueError("Architectural Zoo must contain its each/max records")
        scoring = {
            "mode": "conditions",
            "maximum_conservation": 4,
            "conditions": [
                "water_spaces_connected",
                "rock_spaces_connected",
                "all_border_building_spaces_covered",
                "all_building_spaces_covered",
            ],
        }
    elif component_id == "009":
        if len(raw_tiers) != 2:
            raise ValueError("Diverse Species Zoo must contain its each/max records")
        scoring = {
            "mode": "right_neighbor_categories",
            "categories": [
                "bear", "bird", "herbivore", "pet", "predator", "primate", "reptile",
            ],
            "conservation_each": 1,
            "maximum_conservation": 4,
            "solo_policy": "discard_and_redraw",
        }
    else:
        raise ValueError(f"unknown base-game Final Scoring card: {component_id}")
    return {
        "scoring": deepcopy(scoring),
        "compiled_tier_count": len(raw_tiers),
        "unresolved_tiers": [],
        "semantic_compile_status": "compiled",
    }


def compiled_final_scoring_tier_count(row: Mapping[str, Any]) -> int:
    return int(compile_final_scoring_facts(row)["compiled_tier_count"])


def score_final_card(
    state: Mapping[str, Any], seat: int, card: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return an auditable conservation award for one compiled Final Scoring card."""
    facts = card.get("facts")
    scoring = facts.get("scoring") if isinstance(facts, Mapping) else None
    if not isinstance(scoring, Mapping):
        return None
    player = state["players"][seat]
    mode = scoring.get("mode")
    metric_value: int | None = None
    details: dict[str, Any]
    if mode == "threshold":
        metric = str(scoring.get("metric", ""))
        metric_value = _metric_value(player, metric)
        thresholds = scoring.get("thresholds")
        if not isinstance(thresholds, list):
            raise ValueError("compiled Final Scoring thresholds are malformed")
        conservation = max(
            (
                int(tier["conservation"]) for tier in thresholds
                if metric_value >= int(tier["requirement"])
            ),
            default=0,
        )
        details = {"metric": metric, "metric_value": metric_value}
    elif mode == "conditions":
        condition_ids = scoring.get("conditions")
        if not isinstance(condition_ids, list):
            raise ValueError("compiled Final Scoring conditions are malformed")
        achieved = {
            str(condition): _map_condition(player, str(condition))
            for condition in condition_ids
        }
        conservation = min(
            sum(achieved.values()), int(scoring.get("maximum_conservation", 4)),
        )
        details = {"conditions": achieved}
    elif mode == "right_neighbor_categories":
        if state["player_count"] == 1:
            conservation = 0
            details = {"solo_policy": "discard_and_redraw", "winning_categories": []}
        else:
            categories = scoring.get("categories")
            if not isinstance(categories, list):
                raise ValueError("compiled category comparison is malformed")
            neighbor_seat = (seat + 1) % int(state["player_count"])
            neighbor = state["players"][neighbor_seat]
            winning = [
                str(category) for category in categories
                if int(player["icons"].get(str(category), 0))
                > int(neighbor["icons"].get(str(category), 0))
            ]
            conservation = min(
                len(winning), int(scoring.get("maximum_conservation", 4)),
            )
            details = {
                "right_neighbor_seat": neighbor_seat,
                "winning_categories": winning,
            }
    else:
        raise ValueError(f"unknown compiled Final Scoring mode: {mode}")
    return {
        "card_id": str(card.get("id", card.get("entry_id", "unknown-final-scoring"))),
        "conservation": conservation,
        **details,
    }


def _metric_value(player: Mapping[str, Any], metric: str) -> int:
    played = player["played_cards"]
    if metric in {"large_animal_count", "small_animal_count"}:
        large = metric == "large_animal_count"
        total = 0
        for card in played:
            if card.get("kind") != "animal":
                continue
            facts = card.get("facts", {})
            size = facts.get("enclosure_size") if isinstance(facts, Mapping) else None
            if not isinstance(size, int) or isinstance(size, bool):
                continue
            total += size >= 4 if large else size <= 2
        return total
    if metric == "research_icon_count":
        return int(player["icons"].get("science", player["icons"].get("research", 0)))
    if metric == "supported_project_count":
        return len(player["supported_projects"])
    if metric == "empty_building_space_count":
        zoo_map = player["map"]
        occupied = _occupied_cells(player)
        return sum(
            cell["terrain"] == "buildable" and (cell["q"], cell["r"]) not in occupied
            for cell in zoo_map["cells"]
        )
    if metric == "reputation":
        return int(player["tracks"]["reputation"])
    if metric == "sponsor_card_count":
        return sum(card.get("kind") == "sponsor" for card in played)
    if metric in {"rock_icon_count", "water_icon_count"}:
        terrain = metric.removesuffix("_icon_count")
        # This authoritative counter includes printed terrain-adjacency symbols
        # and is maintained when their Animal/Sponsor enters or leaves play.
        return int(player["icons"].get(terrain, 0))
    raise ValueError(f"unknown Final Scoring metric: {metric}")


def _occupied_cells(player: Mapping[str, Any]) -> set[tuple[int, int]]:
    return {
        (cell["q"], cell["r"])
        for building in player["map"]["buildings"] for cell in building["cells"]
    }


def _map_condition(player: Mapping[str, Any], condition: str) -> bool:
    zoo_map = player["map"]
    occupied = _occupied_cells(player)
    coordinates = {(cell["q"], cell["r"]) for cell in zoo_map["cells"]}
    buildable = {
        (cell["q"], cell["r"])
        for cell in zoo_map["cells"] if cell["terrain"] == "buildable"
    }
    if condition == "all_building_spaces_covered":
        return buildable <= occupied
    if condition == "all_border_building_spaces_covered":
        border = {
            cell for cell in buildable
            if any(neighbor not in coordinates for neighbor in axial_hex_neighbors(cell))
        }
        return border <= occupied
    if condition in {"water_spaces_connected", "rock_spaces_connected"}:
        terrain = condition.removesuffix("_spaces_connected")
        terrain_cells = {
            (cell["q"], cell["r"])
            for cell in zoo_map["cells"] if cell["terrain"] == terrain
        }
        return all(axial_hex_neighbors(cell) & occupied for cell in terrain_cells)
    raise ValueError(f"unknown Final Scoring map condition: {condition}")
