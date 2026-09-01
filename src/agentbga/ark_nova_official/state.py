"""State contract for the staged high-fidelity Ark Nova implementation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from ..ark_nova_map import SUPPORTED_MAP_IDS, map_for_id, normalize_map_id, valid_building_shape


STATE_SCHEMA_VERSION = "agentbga.ark_nova.state.v3"
SEMANTIC_RULES_VERSION = "base-1.2-faq-v2-map0.1"
ACTION_TYPES = ("animals", "cards", "build", "association", "sponsors")
BREAK_LIMITS = {2: 9, 3: 12, 4: 15}
TRACK_LIMITS = {"appeal": 113, "conservation": 41, "reputation": 15}
DONATION_COSTS = (2, 5, 7, 10, 12)
PROJECT_TOKEN_SLOTS = (
    {"id": "card", "recurring": True},
    {"id": "enclosure-2", "recurring": True},
    {"id": "money-5", "recurring": True},
    {"id": "conservation-1", "recurring": True},
    {"id": "worker-1", "recurring": False},
    {"id": "money-12", "recurring": False},
    {"id": "x-3", "recurring": False},
)
MAP_A_PROJECT_TOKEN_SLOTS = tuple(
    {"id": "reputation-2", "recurring": False}
    if slot["id"] == "worker-1" else slot
    for slot in PROJECT_TOKEN_SLOTS
)


def project_token_slots_for_map(map_id: str) -> tuple[dict[str, Any], ...]:
    """Return the printed player-board Conservation rewards for one map."""

    return MAP_A_PROJECT_TOKEN_SLOTS if map_id == "map-a" else PROJECT_TOKEN_SLOTS


def reputation_track_limit(player: Mapping[str, Any]) -> int:
    """Return the reputation ceiling imposed by the Cards action card."""

    cards = next((
        card for card in player.get("action_cards", [])
        if isinstance(card, Mapping) and card.get("action") == "cards"
    ), None)
    return 15 if isinstance(cards, Mapping) and cards.get("upgraded") is True else 9


def next_donation_cost(state: Mapping[str, Any]) -> int:
    """Return the cheapest currently open Association donation amount.

    The four finite spaces may be occupied by either a player donation or a
    solo-tile blocking token.  The 12-money space remains repeatable, so it is
    returned once every finite space is occupied.
    """

    finite_costs = DONATION_COSTS[:-1]
    occupied = {
        int(item["cost"])
        for item in state.get("donations_made", [])
        if isinstance(item, Mapping) and item.get("cost") in finite_costs
    }
    return next((cost for cost in finite_costs if cost not in occupied), DONATION_COSTS[-1])


def new_semantic_state(
    players: int, *, seed: int = 0, map_id: str = "map-0",
) -> dict[str, Any]:
    """Create an empty mechanics state for rule scenarios and staged setup.

    This is deliberately not a complete game setup: maps, decks, projects, and
    starting cards must come from a validated content pack before the official
    plugin can be registered as runnable.
    """
    if players not in (1, 2, 3, 4):
        raise ValueError("Ark Nova supports one to four players")
    map_id = normalize_map_id(map_id)
    rows = []
    for seat in range(players):
        rows.append({
            "seat": seat,
            "money": 25,
            "x_tokens": 0,
            "tracks": {"appeal": 0, "conservation": 0, "reputation": 0},
            "tags": {},
            "icons": {},
            "flags": {},
            "hand": [],
            "hand_limit": 3,
            "played_cards": [],
            "final_scoring_cards": [],
            "supported_projects": [],
            "partner_zoos": [],
            "universities": [],
            "association_asset_icons_accounted": True,
            "project_tokens_available": 7,
            "project_tokens_supply": 0,
            "project_token_slots": [
                {**deepcopy(slot), "claimed": False}
                for slot in project_token_slots_for_map(map_id)
            ],
            "action_cards": [
                {
                    "id": action,
                    "action": action,
                    "position": position,
                    "upgraded": False,
                    "tokens": [],
                }
                for position, action in enumerate(ACTION_TYPES, start=1)
            ],
            "association_workers": {"active": 1, "reserve": 3, "committed": []},
            "income": {"appeal": 0, "kiosks": 0, "other": 0},
            "modifiers": [],
            "claimed_milestones": [],
            "score_entries": [],
            "map": map_for_id(map_id),
        })
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "game_id": "ark_nova",
        "rules_version": SEMANTIC_RULES_VERSION,
        "implementation_status": "semantic_engine_staging",
        "seed": seed,
        "player_count": players,
        "map_id": map_id,
        "solo_starting_appeal": 20 if players == 1 else None,
        "status": "setup",
        "phase": "semantic_scenario",
        "active_seat": 0,
        "players": rows,
        "break": {
            "mode": "solo_round" if players == 1 else "shared_track",
            "position": 0,
            "limit": BREAK_LIMITS.get(players),
            "pending": False,
            "initiator": None,
            "count": 0,
            "solo_round": 1 if players == 1 else None,
            "solo_total_tokens": 7 if players == 1 else None,
            "solo_tokens_left": 7 if players == 1 else None,
            "solo_donation_blocks": [],
        },
        "zoo_deck": [],
        "zoo_discard": [],
        "card_display": [],
        "association_board": {
            "partner_zoos": {
                continent: {"available": 1, "owners": []}
                for continent in ("africa", "europe", "asia", "americas", "australia")
            },
            "universities": {
                "research-2": {"available": 1, "owners": []},
                "research-reputation": {"available": 1, "owners": []},
                "research-hand-limit": {"available": 1, "owners": []},
            },
        },
        "donation_costs": list(DONATION_COSTS),
        "donations_made": [],
        "conservation_projects": [],
        "base_project_supply": [],
        "track_limits": dict(TRACK_LIMITS),
        "official_track_income": False,
        "milestones": [],
        "claimed_global_milestones": [],
        "conservation_bonus_slots": {"5": [], "8": []},
        "final_scoring_discard": [],
        "final_scoring_deck": [],
        "turn": {
            "number": 0,
            "venom_removed_this_turn": False,
            "venom_reserved_money": 0,
            "action_session": None,
            "extra_action": None,
            "hypnosis_action": None,
            "bonus_sponsor_play": None,
            "history": [],
        },
        "resolution": {
            "queue": [],
            "pending_choice": None,
            "next_choice_id": 1,
            "completion": None,
        },
        "endgame": {
            "triggered": False,
            "triggered_by": None,
            "trigger_boundary": None,
            "final_scoring_discard_completed": False,
            "results": None,
        },
    }
    validate_semantic_state(state)
    return state


def clone_state(state: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(state)


def validate_semantic_state(state: dict[str, Any]) -> None:
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise AssertionError("invalid semantic Ark Nova state schema")
    player_count = state.get("player_count")
    if player_count not in (1, 2, 3, 4) or len(state.get("players", [])) != player_count:
        raise AssertionError("invalid semantic Ark Nova player count")
    state_map_id = state.get("map_id", "map-0")
    if state_map_id not in SUPPORTED_MAP_IDS:
        raise AssertionError("invalid Ark Nova map selection")
    if not 0 <= state.get("active_seat", -1) < player_count:
        raise AssertionError("invalid semantic Ark Nova active seat")
    resolution = state.get("resolution")
    if not isinstance(resolution, dict) or not isinstance(resolution.get("queue"), list):
        raise AssertionError("invalid semantic resolution queue")
    if resolution.get("pending_choice") is not None and resolution["queue"] is None:
        raise AssertionError("invalid semantic pending choice")
    turn = state.get("turn")
    if not isinstance(turn, dict) or not isinstance(turn.get("number"), int):
        raise AssertionError("invalid semantic turn state")
    if turn["number"] < 0 or not isinstance(turn.get("history"), list):
        raise AssertionError("invalid semantic turn history")
    if (
        not isinstance(turn.get("venom_removed_this_turn"), bool)
        or turn.get("venom_reserved_money") not in (0, 2)
    ):
        raise AssertionError("invalid turn-level Venom settlement")
    if turn.get("action_session") is not None and not isinstance(turn["action_session"], dict):
        raise AssertionError("invalid semantic action session")
    extra_action = turn.get("extra_action")
    if extra_action is not None and (
        not isinstance(extra_action, dict)
        or extra_action.get("seat") != state.get("active_seat")
        or (
            extra_action.get("excluded_action") not in ACTION_TYPES
            and extra_action.get("action") not in ACTION_TYPES
        )
        or (
            extra_action.get("excluded_action") in ACTION_TYPES
            and extra_action.get("action") in ACTION_TYPES
        )
    ):
        raise AssertionError("invalid pending extra action")
    hypnosis_action = turn.get("hypnosis_action")
    if hypnosis_action is not None and (
        not isinstance(hypnosis_action, dict)
        or hypnosis_action.get("seat") != state.get("active_seat")
        or hypnosis_action.get("action") not in ACTION_TYPES
        or not isinstance(hypnosis_action.get("target_seat"), int)
        or isinstance(hypnosis_action.get("target_seat"), bool)
        or not 0 <= hypnosis_action["target_seat"] < player_count
        or hypnosis_action["target_seat"] == hypnosis_action.get("seat")
        or not isinstance(hypnosis_action.get("target_action_card_id"), str)
        or hypnosis_action.get("position") not in (1, 2, 3, 4, 5)
        or not isinstance(hypnosis_action.get("upgraded"), bool)
        or not isinstance(hypnosis_action.get("constricted"), bool)
        or not isinstance(hypnosis_action.get("venom"), bool)
        or extra_action is not None
    ):
        raise AssertionError("invalid pending Hypnosis action")
    bonus_sponsor = turn.get("bonus_sponsor_play")
    if bonus_sponsor is not None and (
        not isinstance(bonus_sponsor, dict)
        or bonus_sponsor.get("seat") != state.get("active_seat")
        or not isinstance(bonus_sponsor.get("source_instance_id"), str)
        or not isinstance(bonus_sponsor.get("remaining_triggers"), int)
        or isinstance(bonus_sponsor.get("remaining_triggers"), bool)
        or bonus_sponsor["remaining_triggers"] < 1
    ):
        raise AssertionError("invalid pending bonus Sponsor play")
    action_session = turn.get("action_session")
    if action_session is not None:
        if action_session.get("kind") != "regular":
            raise AssertionError("invalid semantic action-session kind")
        if action_session.get("seat") != state["active_seat"]:
            raise AssertionError("action session must belong to the active seat")
        if action_session.get("action") not in ACTION_TYPES:
            raise AssertionError("invalid action-session action")
        if action_session.get("position_locked") not in (1, 2, 3, 4, 5):
            raise AssertionError("invalid locked action-card position")
        strengths = action_session.get("strengths")
        current = action_session.get("current_execution")
        executions = action_session.get("executions")
        if (
            not isinstance(strengths, list) or not strengths
            or any(not isinstance(value, int) or value < 1 for value in strengths)
            or not isinstance(current, int) or not 0 <= current < len(strengths)
            or not isinstance(executions, list) or len(executions) != current
        ):
            raise AssertionError("invalid action execution progress")
        if not isinstance(action_session.get("after_finishing_effects"), list):
            raise AssertionError("invalid after-finishing effect collection")
    bonus_slots = state.get("conservation_bonus_slots")
    if not isinstance(bonus_slots, dict) or any(
        not isinstance(bonus_slots.get(key), list) for key in ("5", "8")
    ):
        raise AssertionError("invalid Conservation bonus slots")
    if not isinstance(state.get("final_scoring_deck"), list):
        raise AssertionError("invalid Final Scoring deck")
    if not isinstance(state.get("base_project_supply"), list):
        raise AssertionError("invalid unused base-project supply")
    if state.get("donation_costs") != list(DONATION_COSTS) or not isinstance(
        state.get("donations_made"), list
    ):
        raise AssertionError("invalid Association donation track")
    if state.get("player_count") == 1 and state.get("solo_starting_appeal") not in {0, 10, 20}:
        raise AssertionError("invalid solo starting Appeal")
    for seat, player in enumerate(state["players"]):
        if player.get("seat") != seat:
            raise AssertionError("player seats must be stable and ordered")
        if player.get("money", -1) < 0 or not 0 <= player.get("x_tokens", -1) <= 5:
            raise AssertionError("invalid player resources")
        tracks = player.get("tracks", {})
        for track, limit in TRACK_LIMITS.items():
            if not 0 <= tracks.get(track, -1) <= limit:
                raise AssertionError(f"invalid {track} track")
        if tracks.get("reputation", -1) > reputation_track_limit(player):
            raise AssertionError("reputation exceeds the Cards action limit")
        zoo_map = player.get("map")
        if not isinstance(zoo_map, dict) or zoo_map.get("id") != state_map_id:
            raise AssertionError("invalid player zoo map")
        cells = zoo_map.get("cells")
        buildings = zoo_map.get("buildings")
        if not isinstance(cells, list) or len(cells) != 58 or not isinstance(buildings, list):
            raise AssertionError("invalid zoo-map cell or building collection")
        terrain = {
            (cell.get("q"), cell.get("r")): cell.get("terrain")
            for cell in cells if isinstance(cell, dict)
        }
        if len(terrain) != 58 or any(
            value not in {"buildable", "water", "rock"} for value in terrain.values()
        ):
            raise AssertionError("invalid zoo-map terrain")
        occupied: set[tuple[int, int]] = set()
        building_ids: set[str] = set()
        may_cover_terrain = any(
            modifier.get("kind") == "diversity_researcher"
            for modifier in player.get("modifiers", [])
        )
        for building in buildings:
            if (
                not isinstance(building, dict)
                or not isinstance(building.get("id"), str)
                or building["id"] in building_ids
                or not valid_building_shape(building)
            ):
                raise AssertionError("invalid zoo-map building")
            building_ids.add(building["id"])
            footprint = {(cell.get("q"), cell.get("r")) for cell in building["cells"]}
            allowed_terrain = (
                {"buildable", "water", "rock"} if may_cover_terrain else {"buildable"}
            )
            if footprint & occupied or any(
                terrain.get(coordinate) not in allowed_terrain for coordinate in footprint
            ):
                raise AssertionError("zoo-map building occupies an illegal cell")
            occupied |= footprint
        if player.get("hand_limit", 0) < 0:
            raise AssertionError("invalid hand limit")
        project_slots = player.get("project_token_slots")
        if (
            not isinstance(project_slots, list)
            or {slot.get("id") for slot in project_slots} != {
                slot["id"] for slot in project_token_slots_for_map(state_map_id)
            }
            or any(
                not isinstance(slot.get("claimed"), bool)
                or not isinstance(slot.get("recurring"), bool)
                for slot in project_slots
            )
        ):
            raise AssertionError("invalid conservation-project token slots")
        action_cards = player.get("action_cards", [])
        if {card.get("action") for card in action_cards} != set(ACTION_TYPES):
            raise AssertionError("player must have the five base action cards")
        if sorted(card.get("position") for card in action_cards) != [1, 2, 3, 4, 5]:
            raise AssertionError("player action cards must occupy slots one through five")
        if any(not isinstance(card.get("tokens"), list) for card in action_cards):
            raise AssertionError("invalid action-card token collection")
        workers = player.get("association_workers", {})
        if workers.get("active", -1) < 0 or workers.get("reserve", -1) < 0:
            raise AssertionError("invalid association workers")
        if not isinstance(workers.get("committed"), list):
            raise AssertionError("invalid committed worker collection")
        if not isinstance(player.get("partner_zoos"), list) or not isinstance(
            player.get("universities"), list
        ):
            raise AssertionError("invalid association assets")
