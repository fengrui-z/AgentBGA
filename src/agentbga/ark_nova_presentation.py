"""Spectator-safe public projections for the Ark Nova table UI."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .ark_nova_tracks import (
    APPEAL_MAXIMUM,
    CONSERVATION_MAXIMUM,
    REPUTATION_DISPLAY_RANGES,
    REPUTATION_MAXIMUM,
    appeal_income,
    conservation_score_offset,
    conservation_target_appeal,
)


CONTINENTS = ("africa", "europe", "asia", "americas", "australia")
ANIMAL_TAGS = ("bird", "predator", "herbivore", "reptile", "primate")
EXTRA_TAGS = ("bear", "petting_zoo", "research", "rock", "water")
DONATION_COSTS = (2, 5, 7, 10, 12)


def _played_cards(player: dict[str, Any]) -> list[dict[str, Any]]:
    return [card for card in player["played_cards"] if isinstance(card, dict) and not card.get("hidden")]


def _tag_count(player: dict[str, Any], tag: str) -> int:
    return sum(tag in card.get("tags", []) for card in _played_cards(player))


def player_public_summary(player: dict[str, Any]) -> dict[str, Any]:
    """Return counters and assets that are public at the physical table."""

    cards = _played_cards(player)
    research_from_universities = (
        2 * sum(value == "research-2" for value in player["universities"])
        + sum(value == "research-reputation" for value in player["universities"])
        + sum(value == "hand-limit-5" for value in player["universities"])
    )
    tag_counts = {tag: _tag_count(player, tag) for tag in (*ANIMAL_TAGS, *EXTRA_TAGS)}
    tag_counts["research"] += research_from_universities
    continents = {
        continent: sum(
            card.get("card_type") == "animal" and card.get("continent") == continent
            for card in cards
        )
        for continent in CONTINENTS
    }
    hand_limit = int(player.get(
        "hand_limit",
        5 if any(
            value in {"hand-limit-5", "research-hand-limit"}
            for value in player["universities"]
        ) else 3,
    ))
    return {
        "seat": player["seat"],
        "resources": {
            "money": player["money"], "x_tokens": player["x_tokens"],
            "hand_count": len(player["hand"]), "hand_limit": hand_limit,
        },
        "tracks": {
            "appeal": player["appeal"], "conservation": player["conservation"],
            "reputation": player["reputation"],
            "current_score": (
                player["appeal"] + conservation_score_offset(player["conservation"])
            ),
        },
        "counters": {"continents": continents, "animals": tag_counts},
        "action_cards": sorted(deepcopy(player["action_cards"]), key=lambda card: card["strength"]),
        "association": {
            "workers": deepcopy(player["association_workers"]),
            "partner_zoos": list(player["partner_zoos"]),
            "universities": list(player["universities"]),
        },
        "conservation": {
            "tokens_on_map": player["conservation_tokens_on_map"],
            "action_upgrades_claimed": list(player["upgrade_rewards_claimed"]),
            "bonuses_claimed": list(player["conservation_rewards_claimed"]),
            "final_card_choice_resolved": player["final_card_choice_resolved"],
        },
        "supported_projects": list(player["supported_projects"]),
    }


def public_tracks(state: dict[str, Any]) -> dict[str, Any]:
    """Expose stable track ranges and marker positions to all renderers."""

    return {
        "break": {
            "minimum": 0, "maximum": state["break_track"]["limit"],
            "markers": [{"id": "break", "position": state["break_track"]["position"]}],
        },
        "appeal": {
            "minimum": 0, "maximum": APPEAL_MAXIMUM,
            "markers": [{"seat": player["seat"], "position": player["appeal"]} for player in state["players"]],
        },
        "conservation": {
            "minimum": 0, "maximum": CONSERVATION_MAXIMUM,
            "markers": [{"seat": player["seat"], "position": player["conservation"]} for player in state["players"]],
            "rewards": [
                {"position": 2, "symbol": "II/W", "kind": "action_upgrade_or_worker"},
                {"position": 5, "symbol": "◇", "kind": "choose_board_bonus"},
                {"position": 8, "symbol": "◇", "kind": "choose_board_bonus"},
                {"position": 10, "symbol": "F", "kind": "final_card_choice"},
            ],
        },
        "reputation": {
            "minimum": 1, "maximum": REPUTATION_MAXIMUM,
            "markers": [{"seat": player["seat"], "position": player["reputation"]} for player in state["players"]],
            "rewards": [
                {"position": 5, "symbol": "II", "kind": "action_upgrade"},
                {"position": 8, "symbol": "W", "kind": "gain_worker"},
                {"position": 10, "symbol": "▣", "kind": "take_card_or_deck"},
                {"position": 11, "symbol": "C+", "kind": "gain_conservation"},
                {"position": 12, "symbol": "X", "kind": "gain_x_token"},
                {"position": 13, "symbol": "▣", "kind": "take_card_or_deck"},
                {"position": 14, "symbol": "C+", "kind": "gain_conservation"},
                {"position": 15, "symbol": "X", "kind": "gain_x_token"},
            ],
            "display_access": [
                {
                    "slot": slot,
                    "minimum_reputation": minimum,
                    "maximum_reputation": maximum,
                    "requires_cards_upgrade": minimum >= 10,
                }
                for slot, (minimum, maximum) in enumerate(REPUTATION_DISPLAY_RANGES, 1)
            ],
        },
        "appeal_conservation": {
            "minimum": 0,
            "maximum": APPEAL_MAXIMUM + 1,
            "appeal_maximum": APPEAL_MAXIMUM,
            "conservation_maximum": CONSERVATION_MAXIMUM,
            "income": [
                {"appeal": appeal, "money": appeal_income(appeal)}
                for appeal in range(APPEAL_MAXIMUM + 1)
            ],
            "conservation_spaces": [
                {
                    "conservation": conservation,
                    "axis": conservation_target_appeal(conservation),
                    "score_offset": conservation_score_offset(conservation),
                }
                for conservation in range(CONSERVATION_MAXIMUM + 1)
            ],
            "appeal_markers": [
                {"seat": player["seat"], "position": player["appeal"]}
                for player in state["players"]
            ],
            "conservation_markers": [
                {
                    "seat": player["seat"],
                    "value": player["conservation"],
                    "position": conservation_target_appeal(player["conservation"]),
                    "score_offset": conservation_score_offset(player["conservation"]),
                }
                for player in state["players"]
            ],
        },
    }


def association_display(state: dict[str, Any]) -> dict[str, Any]:
    """Normalise stock, owners, workers, and donations without losing empty slots."""

    def owners(asset: str, value: str) -> list[int]:
        return [player["seat"] for player in state["players"] if value in player[asset]]

    workers = []
    for player in state["players"]:
        for item in player["association_workers"]["committed"]:
            workers.append({"seat": player["seat"], **deepcopy(item)})
    board = state["association_board"]
    donation_slots = []
    for index, cost in enumerate(DONATION_COSTS):
        donation = board["donations"][index] if index < len(board["donations"]) else None
        donation_slots.append({
            "position": index + 1, "cost": cost,
            "status": "claimed" if donation else "available",
            "seat": donation["seat"] if donation else None,
        })
    return {
        "partner_zoos": [
            {"id": value, "remaining": remaining, "owners": owners("partner_zoos", value)}
            for value, remaining in board["partner_zoos"].items()
        ],
        "universities": [
            {"id": value, "remaining": remaining, "owners": owners("universities", value)}
            for value, remaining in board["universities"].items()
        ],
        "workers": workers,
        "donations": deepcopy(board["donations"]),
        "donation_slots": donation_slots,
        "blocked_spaces": list(board["blocked_two_player"]),
    }


def map_display(player: dict[str, Any]) -> dict[str, Any]:
    """Keep map reward slots readable after the one-shot cell bonus is consumed."""

    cells = {(cell["q"], cell["r"]): cell for cell in player["map"]["cells"]}
    buildings = {
        (cell["q"], cell["r"]): building
        for building in player["map"]["buildings"]
        for cell in building["cells"]
    }
    rewards = []
    for slot in player["map"].get("placement_bonus_slots", []):
        coordinate = (slot["q"], slot["r"])
        available = "placement_bonus" in cells[coordinate]
        rewards.append({
            **deepcopy(slot), "status": "available" if available else "claimed",
            "building_id": None if available else buildings.get(coordinate, {}).get("id"),
        })
    conservation_slots = []
    for slot in player["map"].get("conservation_reward_slots", []):
        milestone = slot["milestone"]
        if slot["kind"] == "action_upgrade":
            claimed = milestone in player["upgrade_rewards_claimed"]
        elif slot["kind"] == "conservation_bonus":
            claimed = milestone in player["conservation_rewards_claimed"]
        else:
            claimed = player["final_card_choice_resolved"]
        conservation_slots.append({**deepcopy(slot), "status": "claimed" if claimed else "available"})
    buildable = {
        (cell["q"], cell["r"]) for cell in player["map"]["cells"]
        if cell["terrain"] == "buildable"
    }
    occupied = set(buildings)
    zoo_count = len(player["partner_zoos"])
    university_count = len(player["universities"])
    zoo_rewards = {
        1: None,
        2: {"type": "action_upgrade", "amount": 1},
        3: {"type": "gain_worker", "amount": 1},
        4: {"type": "gain_conservation", "amount": 2},
    }
    university_rewards = {
        1: None,
        2: {"type": "action_upgrade", "amount": 1},
        3: {"type": "gain_conservation", "amount": 2},
    }
    partner_ladder = [
        {
            "level": level,
            "asset": player["partner_zoos"][level - 1] if zoo_count >= level else None,
            "reward": deepcopy(zoo_rewards[level]),
            "status": "claimed" if zoo_count >= level else "empty",
        }
        for level in range(4, 0, -1)
    ]
    university_ladder = [
        {
            "level": level,
            "asset": player["universities"][level - 1] if university_count >= level else None,
            "reward": deepcopy(university_rewards[level]),
            "status": "claimed" if university_count >= level else "empty",
        }
        for level in range(3, 0, -1)
    ]
    committed_workers = sum(item.get("workers", 1) for item in player["association_workers"]["committed"])
    locked_workers = [
        {
            "slot": index + 1,
            "status": "locked",
            "unlock_reward": ({"type": "gain_conservation", "amount": 1}
                              if index == player["association_workers"]["reserve"] - 1 else None),
        }
        for index in range(player["association_workers"]["reserve"])
    ]
    return {
        "placement_rewards": rewards,
        "conservation_rewards": conservation_slots,
        "player_board": {
            "partner_zoo_ladder": partner_ladder,
            "university_ladder": university_ladder,
            "workers": {
                "available": player["association_workers"]["active"],
                "committed": committed_workers,
                "locked": locked_workers,
            },
            "conservation_programs": [
                {
                    "kind": "immediate_and_income",
                    "slots": [
                        {"id": "determination", "reward": {"type": "gain_determination", "amount": 1}, "status": "locked"},
                        {"id": "enclosure-2", "reward": {"type": "gain_enclosure", "amount": 2}, "status": "locked"},
                        {"id": "money-5", "reward": {"type": "gain_money", "amount": 5}, "status": "locked"},
                        {"id": "conservation-1", "reward": {"type": "gain_conservation", "amount": 1}, "status": "locked"},
                    ],
                },
                {
                    "kind": "immediate",
                    "slots": [
                        {"id": "worker-1", "reward": {"type": "gain_worker", "amount": 1}, "status": "locked"},
                        {"id": "money-12", "reward": {"type": "gain_money", "amount": 12}, "status": "locked"},
                        {"id": "x-3", "reward": {"type": "gain_x_token", "amount": 3}, "status": "locked"},
                    ],
                },
            ],
        },
        "coverage": {
            "covered": len(buildable & occupied), "total": len(buildable),
            "complete": bool(buildable) and buildable <= occupied,
            "reward": deepcopy(player["map"].get("completion_reward")),
            "status": ("claimed" if player["map"].get("completion_reward_claimed")
                       else "available"),
        },
    }
