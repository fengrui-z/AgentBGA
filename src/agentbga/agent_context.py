"""Seat-scoped compact agent contexts and on-demand resource projections.

The Web UI needs a complete game projection, but a persistent model session
should not receive the same maps and complete card programs on every decision.
This module turns an already privacy-filtered observation into a compact
decision working set while retaining detail in a fixed, seat-scoped resource
index.  It deliberately does not read game state or the content pack directly:
the normal game observation remains the security boundary.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .ark_nova_agent_rules import (
    action_card_summary,
    rule_topic,
    rules_catalog,
    rules_resource,
)
from .ark_nova_tracks import conservation_target_appeal


from .legal_action_query import GAME_FILTERS, query_actions, query_metadata


CONTEXT_V1 = "agentbga.seat-context.v1"
CONTEXT_V2 = "agentbga.seat-context.v2"
DEFAULT_ACTION_PAGE_SIZE = 20
MAX_ACTION_PAGE_SIZE = 50
MAX_HISTORY_ITEMS = 200


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _revision(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()[:12]


def _card_type(card: Mapping[str, Any]) -> str:
    return str(card.get("card_type") or card.get("kind") or "card")


def _card_ref(card: Mapping[str, Any]) -> str | None:
    card_id = card.get("id") or card.get("entry_id")
    return f"card:{card_id}" if isinstance(card_id, str) and card_id else None


def _animal_housing_options(card: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project a printed Animal enclosure line into explicit alternatives."""
    if _card_type(card) != "animal" and card.get("kind") != "animal":
        return []
    facts = card.get("facts") if isinstance(card.get("facts"), Mapping) else {}

    def fact(key: str, default: Any = None) -> Any:
        return card.get(key, facts.get(key, default))

    enclosure_size = fact("enclosure_size")
    if not isinstance(enclosure_size, int) or isinstance(enclosure_size, bool):
        return []
    result: list[dict[str, Any]] = []
    if fact("can_use_standard_enclosure", True):
        result.append({
            "building_type": "standard_enclosure",
            "minimum_size": enclosure_size,
            "capacity_used": enclosure_size,
            "description": f"May use one empty standard enclosure of size {enclosure_size} or larger.",
        })
    special = fact("special_enclosure")
    if isinstance(special, str) and special:
        name, separator, printed_space = special.rpartition(" ")
        if separator and printed_space.isdigit():
            result.append({
                "building_type": {
                    "Petting Zoo": "petting_zoo",
                    "Reptile House": "reptile_house",
                    "Large Bird Aviary": "large_bird_aviary",
                }.get(name, name),
                "capacity_used": int(printed_space),
                "description": (
                    f"Alternatively, may use {int(printed_space)} capacity "
                    f"in a {name}."
                ),
            })
    return result


def compact_card(card: Mapping[str, Any]) -> dict[str, Any]:
    """Return the decision-relevant face of one visible card."""
    result: dict[str, Any] = {
        "id": card.get("id"),
        "title": card.get("display_title") or card.get("title") or card.get("name"),
        "type": _card_type(card),
    }
    reference = _card_ref(card)
    if reference:
        result["detail_ref"] = reference
    for key in (
        "cost", "enclosure_size", "special_enclosure", "rock_requirement",
        "water_requirement", "level", "appeal", "reputation", "conservation",
        "icons", "project_type", "tag_or_criterion", "live_scoring",
    ):
        value = card.get(key)
        if value not in (None, [], {}, ""):
            result[key] = deepcopy(value)
    abilities = card.get("abilities")
    if isinstance(abilities, list):
        result["abilities"] = [
            item.get("keyword") or item.get("name_en") or item.get("key")
            for item in abilities if isinstance(item, Mapping)
        ]
    requirements = card.get("resolved_requirements")
    if isinstance(requirements, list):
        result["requirements"] = [
            item.get("description_cn") or item.get("description_en")
            for item in requirements if isinstance(item, Mapping)
        ]
    housing_options = _animal_housing_options(card)
    if housing_options:
        result["housing_options"] = housing_options
    mechanics = card.get("resolved_mechanics")
    if isinstance(mechanics, list) and mechanics:
        result["mechanics_preview"] = [
            {
                "timing": item.get("timing"),
                "description": item.get("description_cn") or item.get("description_en"),
            }
            for item in mechanics[:1] if isinstance(item, Mapping)
        ]
        if len(mechanics) > 1:
            result["more_mechanics"] = len(mechanics) - 1
    levels = card.get("levels")
    if isinstance(levels, list):
        compact_levels = [
            {
                key: deepcopy(item[key]) for key in
                ("id", "conservation", "reputation") if key in item
            }
            for item in levels if isinstance(item, Mapping)
        ]
        if compact_levels:
            result["levels"] = compact_levels
    return {key: value for key, value in result.items() if value is not None}


def _collect_cards(value: Any, cards: dict[str, dict[str, Any]]) -> None:
    if isinstance(value, Mapping):
        reference = _card_ref(value)
        if reference and (
            value.get("display_title") is not None
            or value.get("card_type") is not None
            or value.get("kind") in {
                "animal", "sponsor", "zoo_conservation_project", "final_scoring",
            }
        ):
            cards.setdefault(reference, deepcopy(dict(value)))
        for child in value.values():
            _collect_cards(child, cards)
    elif isinstance(value, list):
        for child in value:
            _collect_cards(child, cards)


def _map_summary(player: Mapping[str, Any]) -> dict[str, Any]:
    game_map = player.get("map") if isinstance(player.get("map"), Mapping) else {}
    display = (
        player.get("map_display")
        if isinstance(player.get("map_display"), Mapping) else {}
    )
    buildings = game_map.get("buildings", [])
    counts = Counter(
        str(item.get("type", "building")) for item in buildings
        if isinstance(item, Mapping)
    )
    occupied = sum(
        1 for item in buildings
        if isinstance(item, Mapping) and bool(item.get("occupied"))
    )
    coverage = display.get("coverage", {})
    rewards = display.get("placement_rewards", [])
    result = {
        "id": game_map.get("id"),
        "revision": _revision({"buildings": buildings, "rewards": rewards}),
        "building_count": len(buildings),
        "building_types": dict(sorted(counts.items())),
        "occupied_enclosures": occupied,
        "empty_enclosures": sum(
            1 for item in buildings if isinstance(item, Mapping)
            and "enclosure" in str(item.get("type", ""))
            and not bool(item.get("occupied"))
        ),
        "covered_spaces": coverage.get("covered"),
        "coverable_spaces": coverage.get("total"),
        "completion_reward_status": coverage.get("status"),
        "available_placement_rewards": sum(
            1 for item in rewards
            if isinstance(item, Mapping) and item.get("status") == "available"
        ),
        "detail_ref": f"map:seat-{player.get('seat')}",
    }
    return result


def _played_summary(player: Mapping[str, Any]) -> dict[str, Any]:
    cards = [
        item for item in player.get("played_cards", [])
        if isinstance(item, Mapping)
    ]
    counts = Counter(_card_type(card) for card in cards)
    result = {
        "revision": _revision([
            (card.get("id"), card.get("entry_id")) for card in cards
        ]),
        "counts": dict(sorted(counts.items())),
        "cards": [compact_card(card) for card in cards],
        "detail_ref": f"zone:seat-{player.get('seat')}:played",
    }
    return result


def _action_token_type(token: Any) -> str:
    if isinstance(token, Mapping):
        return str(token.get("type") or "unknown")
    return str(token)


def _action_token_details(card: Mapping[str, Any]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for token in card.get("tokens", []):
        token_type = _action_token_type(token)
        source_id = token.get("source_id") if isinstance(token, Mapping) else None
        if token_type == "constriction":
            effect = "This marked Action has -2 strength until X-tokens are added."
            removal = "Removed when this marked card is used/taken for X, or at the next Break."
        elif token_type == "venom":
            effect = "Using another Action while Venom remains costs 2 money at turn end."
            removal = "Removed when this marked card is used/taken for X, or at the next Break."
        elif token_type == "multiplier":
            effect = "May be spent to execute this marked Action twice."
            removal = "Removed when spent, or at the next Break."
        else:
            effect = "Unknown action-card interaction marker; inspect its source card."
            removal = "Check the originating effect for removal timing."
        detail = {"type": token_type, "effect": effect, "removal": removal}
        if source_id:
            detail["source_id"] = source_id
        details.append(detail)
    return details


def _action_token_status(player: Mapping[str, Any]) -> dict[str, Any]:
    affected: list[dict[str, Any]] = []
    for card in player.get("action_cards", []):
        if not isinstance(card, Mapping) or not card.get("tokens"):
            continue
        strength = int(card.get("strength", card.get("position", 1)) or 1)
        tokens = _action_token_details(card)
        constrictions = sum(item["type"] == "constriction" for item in tokens)
        affected.append({
            "action": card.get("action"),
            "printed_strength": strength,
            "effective_strength_before_x": max(0, strength - 2 * constrictions),
            "tokens": tokens,
        })
    return {
        "affected_cards": affected,
        "has_markers": bool(affected),
        "rules_topic": "interaction_tokens",
        "break_rule": "All Venom, Constriction, and Multiplier markers are cleared at the next Break.",
    }


def _compact_player(player: Mapping[str, Any], viewer_seat: int) -> dict[str, Any]:
    seat = int(player.get("seat", -1))
    private = seat == viewer_seat
    tracks = player.get("tracks", {})
    workers = player.get("association_workers", {})
    hand = player.get("hand", [])
    cards_action = next((
        card for card in player.get("action_cards", [])
        if isinstance(card, Mapping) and card.get("action") == "cards"
    ), {})
    cards_upgraded = bool(cards_action.get("upgraded"))
    row: dict[str, Any] = {
        "seat": seat,
        "money": player.get("money"),
        "x_tokens": player.get("x_tokens"),
        "tracks": deepcopy(tracks),
        "track_constraints": {
            "reputation_limit": 15 if cards_upgraded else 9,
            "reputation_rule": (
                "Cards II is upgraded: Reputation may advance through 15."
                if cards_upgraded else
                "Cards I is not upgraded: Reputation cannot exceed 9; upgrade Cards to II to reach 10-15."
            ),
        },
        "score": player.get("public_summary", {}).get("tracks", {}).get("current_score"),
        "action_token_status": _action_token_status(player),
        "hand_count": player.get("hand_count", len(hand)),
        "hand_limit": player.get("hand_limit"),
        "icons": deepcopy(player.get("icons", {})),
        "action_cards": [
            {
                "id": card.get("id"),
                "action": card.get("action"),
                "strength": card.get("strength", card.get("position")),
                "side": "II" if card.get("upgraded") else "I",
                "effect_at_current_strength": action_card_summary(
                    str(card.get("action")), bool(card.get("upgraded")),
                    int(card.get("strength", card.get("position", 1)) or 1),
                ),
                "rules_topic": str(card.get("action")),
                **({
                    "effective_strength_before_x": max(
                        0,
                        int(card.get("strength", card.get("position", 1)) or 1)
                        - 2 * sum(
                            _action_token_type(token) == "constriction"
                            for token in card.get("tokens", [])
                        ),
                    ),
                    "token_effects": _action_token_details(card),
                } if card.get("tokens") else {}),
                **({"tokens": deepcopy(card["tokens"])} if card.get("tokens") else {}),
            }
            for card in player.get("action_cards", [])
            if isinstance(card, Mapping)
        ],
        "association": {
            "workers_available": workers.get("active"),
            "workers_reserve": workers.get("reserve"),
            "workers_committed": len(workers.get("committed", [])),
            "project_tokens_available": player.get("project_tokens_available"),
            "partner_zoos": deepcopy(player.get("partner_zoos", [])),
            "universities": deepcopy(player.get("universities", [])),
        },
        "supported_projects": deepcopy(player.get("supported_project_details", [])),
        "map": _map_summary(player),
        "played_cards": _played_summary(player),
    }
    if private:
        row["hand"] = [
            compact_card(card) for card in hand if isinstance(card, Mapping)
        ]
        row["initial_draw"] = [
            compact_card(card) for card in player.get("initial_draw", [])
            if isinstance(card, Mapping)
        ]
        row["final_scoring_cards"] = [
            compact_card(card) for card in player.get("final_scoring_cards", [])
            if isinstance(card, Mapping)
        ]
        row["project_token_slots"] = deepcopy(player.get("project_token_slots", []))
        row["next_break_projection"] = deepcopy(
            player.get("next_break_projection", {})
        )
    else:
        # Card identities are public after play, but their complete executable
        # programs are available through inspect_card rather than repeated here.
        row["played_cards"]["cards"] = [
            {
                "id": card.get("id"), "entry_id": card.get("entry_id"),
                "title": card.get("title"), "type": card.get("type"),
                "detail_ref": card.get("detail_ref"),
            }
            for card in row["played_cards"]["cards"]
        ]
    return row


def _compact_project(project: Mapping[str, Any]) -> dict[str, Any]:
    card = compact_card(project)
    requirement = (
        project.get("criterion_en") or project.get("criterion_cn")
        or project.get("requirement_en") or project.get("requirement_cn")
    )
    if requirement:
        card["requirement"] = requirement
    for key in (
        "base", "claims", "blocked_levels", "slot_status", "tiers",
        "eligible_levels", "best_eligible_level", "current_metric", "current_value",
        "effective_action_strength_required", "workers_required",
        "project_token_available",
    ):
        if key in project:
            card[key] = deepcopy(project[key])
    return card


def _association_project_opportunities(
    observation: Mapping[str, Any],
    projects: list[dict[str, Any]],
    legal: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Summarize immediately scoreable displayed projects before Association starts."""
    viewer_seat = int(observation.get("viewer_seat", -1))
    player = next((
        item for item in observation.get("players", [])
        if isinstance(item, Mapping) and int(item.get("seat", -1)) == viewer_seat
    ), {})
    workers = player.get("association_workers", {})
    workers_available = int(workers.get("active", 0) or 0)
    project_tokens = int(player.get("project_tokens_available", 0) or 0)
    start_strengths = [
        int(item["execution_spec"].get("strength", 0) or 0)
        for item in legal
        if isinstance(item.get("execution_spec"), Mapping)
        and item["execution_spec"].get("action") == "association"
        and item.get("action", {}).get("type") == "start_action"
    ]
    exact_actions = {
        (str(action.get("project_id")), str(action.get("level_id")))
        for item in legal
        for action in [item.get("action", {})]
        if isinstance(action, Mapping)
        and action.get("type") == "perform_association_task"
        and action.get("task_id") == "conservation-project"
    }
    result = []
    for project in projects:
        eligible = [
            deepcopy(level) for level in project.get("eligible_levels", [])
            if isinstance(level, Mapping)
        ]
        if not eligible:
            continue
        best = max(
            eligible,
            key=lambda level: (
                int(level.get("conservation", 0) or 0),
                int(level.get("reputation", 0) or 0),
            ),
        )
        strength = int(project.get("effective_action_strength_required", 5) or 5)
        required_workers = int(project.get("workers_required", 1) or 1)
        exact_legal = (str(project.get("id")), str(best.get("id"))) in exact_actions
        start_legal = any(value >= strength for value in start_strengths)
        legal_now = bool(
            project_tokens > 0
            and workers_available >= required_workers
            and (exact_legal or start_legal)
        )
        blockers = []
        if project_tokens < 1:
            blockers.append("no conservation-project token available")
        if workers_available < required_workers:
            blockers.append(
                f"needs {required_workers} of your workers; {workers_available} available"
            )
        if not exact_legal and not start_legal:
            blockers.append(f"needs Association strength {strength}")
        result.append({
            "project_id": project.get("id"),
            "title": project.get("title"),
            "base": bool(project.get("base")),
            "criterion": project.get("requirement"),
            "current_metric": project.get("current_metric"),
            "current_value": project.get("current_value"),
            "eligible_levels": eligible,
            "best_option": best,
            "effective_action_strength_required": strength,
            "workers_required": required_workers,
            "workers_rule": (
                "Only this player's own earlier uses of the same Association task "
                "increase its worker cost; other players never increase it."
            ),
            "displayed_project_requires_card": False,
            "legal_now": legal_now,
            **({"blocked_by": blockers} if blockers else {}),
        })
    return result


def _annotate_association_starts(
    legal: list[dict[str, Any]], opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = deepcopy(legal)
    for item in result:
        spec = item.get("execution_spec")
        if not isinstance(spec, Mapping) or spec.get("action") != "association":
            continue
        strength = int(spec.get("strength", 0) or 0)
        available = [
            opportunity for opportunity in opportunities
            if opportunity.get("legal_now")
            and strength >= int(
                opportunity.get("effective_action_strength_required", 5) or 5
            )
        ]
        if not available:
            continue
        best = max(
            available,
            key=lambda opportunity: int(
                opportunity.get("best_option", {}).get("conservation", 0) or 0
            ),
        )
        option = best["best_option"]
        summary = (
            f"Can support displayed {best['title']} at {option['id']} for "
            f"+{option.get('conservation', 0)} Conservation; no project card required."
        )
        item["opportunity_summary"] = summary
        item["label"] = f"{item.get('label', 'association')} · {summary}"
        item["execution_spec"] = {**dict(spec), "best_project_opportunity": summary}
    return result


def action_group(item: Mapping[str, Any]) -> str:
    action = item.get("action", item)
    action_type = str(action.get("type", "other"))
    if action_type in {"place_building", "place_unique_sponsor_building"}:
        building = action.get("building_type", "building")
        size = action.get("size", "x")
        rotation = action.get("rotation", "x")
        return f"{action_type}:{building}:size-{size}:rotation-{rotation}"
    if action_type == "perform_association_task":
        return f"{action_type}:{action.get('task_id', 'task')}"
    if action_type in {"select_animal_card", "play_sponsor_card"}:
        return f"{action_type}:{action.get('source', 'unknown')}"
    if action_type == "resolve_semantic_choice":
        return f"{action_type}:{action.get('choice_id', 'choice')}"
    return action_type


def _flatten_legal(legal: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in legal:
        row = {
            "id": item["id"],
            **({"label": item["label"]} if item.get("label") else {}),
            **({key: deepcopy(item[key]) for key in (
                "benefit_summary", "benefit_summary_cn", "recurring",
                "reward_timing", "reward_timing_cn", "reward_timing_en",
                "execution_spec", "presentation", "opportunity_summary",
            ) if key in item}),
            **deepcopy(item["action"]),
        }
        spec = item.get("execution_spec")
        if isinstance(spec, Mapping):
            row["rule_summary"] = action_card_summary(
                str(spec.get("action")), spec.get("side") == "II",
                int(spec.get("strength", 1) or 1),
            )
            row["rules_topic"] = str(spec.get("action"))
        card_id = row.get("card_id") or row.get("instance_id")
        if isinstance(card_id, str):
            row["card_ref"] = f"card:{card_id}"
        rows.append(row)
    return rows


def legal_action_groups(legal: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in legal:
        grouped.setdefault(action_group(item), []).append(item)
    rows = []
    for group, items in grouped.items():
        label = items[0].get("label") or group.replace(":", " · ")
        rows.append({
            "group": group,
            "label": label,
            "count": len(items),
            "requires_paging": len(items) > DEFAULT_ACTION_PAGE_SIZE,
        })
    return sorted(rows, key=lambda row: row["group"])


def project_legal_actions(
    context: Mapping[str, Any], arguments: Mapping[str, Any] | None = None,
) -> Any:
    """Return v1 actions unchanged or a paginated v2 legal-action view."""
    if context.get("observation", {}).get("game") in GAME_FILTERS:
        return query_actions(context, arguments if arguments is not None else {})
    if arguments and "filters" in arguments:
        raise ValueError("legal action filters are not supported for this game")
    actions = list(context.get("legal_actions", []))
    if context.get("schema_version") == CONTEXT_V1:
        return actions
    arguments = arguments or {}
    requested_group = arguments.get("group")
    if requested_group is None and len(actions) > DEFAULT_ACTION_PAGE_SIZE:
        return {
            "state_version": context.get("version"),
            "mode": "groups",
            "total": len(actions),
            "groups": deepcopy(context.get("legal_action_groups", [])),
            "instruction": (
                "Call legal_actions again with a group to list concrete action IDs."
            ),
        }
    selected = [
        item for item in actions
        if requested_group is None or item.get("_group") == requested_group
    ]
    cursor = arguments.get("cursor", 0)
    limit = arguments.get("limit", DEFAULT_ACTION_PAGE_SIZE)
    cursor = cursor if isinstance(cursor, int) and cursor >= 0 else 0
    limit = limit if isinstance(limit, int) else DEFAULT_ACTION_PAGE_SIZE
    limit = max(1, min(MAX_ACTION_PAGE_SIZE, limit))
    page = selected[cursor:cursor + limit]
    visible = [
        {key: deepcopy(value) for key, value in item.items() if key != "_group"}
        for item in page
    ]
    next_cursor = cursor + len(page)
    return {
        "state_version": context.get("version"),
        "mode": "actions",
        "group": requested_group,
        "total": len(selected),
        "cursor": cursor,
        "next_cursor": next_cursor if next_cursor < len(selected) else None,
        "actions": visible,
    }


def _player_snapshot(player: Mapping[str, Any]) -> dict[str, Any]:
    workers = player.get("association_workers", {})
    game_map = player.get("map", {})
    return {
        "money": player.get("money"),
        "x_tokens": player.get("x_tokens"),
        "tracks": deepcopy(player.get("tracks", {})),
        "hand_count": player.get("hand_count", len(player.get("hand", []))),
        "icons": deepcopy(player.get("icons", {})),
        "workers": {
            "active": workers.get("active"), "reserve": workers.get("reserve"),
            "committed": len(workers.get("committed", [])),
        },
        "partner_zoos": deepcopy(player.get("partner_zoos", [])),
        "universities": deepcopy(player.get("universities", [])),
        "action_cards": [
            (
                card.get("action"), card.get("position"), bool(card.get("upgraded")),
                tuple(
                    (
                        _action_token_type(token),
                        token.get("source_id") if isinstance(token, Mapping) else None,
                    )
                    for token in card.get("tokens", [])
                ),
            )
            for card in player.get("action_cards", []) if isinstance(card, Mapping)
        ],
        "played": {
            str(card.get("id")): card.get("display_title")
            for card in player.get("played_cards", []) if isinstance(card, Mapping)
        },
        "buildings": {
            str(item.get("id")): {
                "type": item.get("type"), "size": item.get("size"),
                "occupied": item.get("occupied"),
            }
            for item in game_map.get("buildings", []) if isinstance(item, Mapping)
        },
    }


def observation_delta(
    previous: Mapping[str, Any] | None, current: Mapping[str, Any],
) -> dict[str, Any]:
    current_version = current.get("state_version", current.get("decision_count"))
    if not previous or previous.get("game") != current.get("game"):
        return {
            "baseline": True, "from_version": None, "to_version": current_version,
            "events": [],
        }
    events: list[dict[str, Any]] = []
    if previous.get("phase") != current.get("phase"):
        events.append({
            "kind": "phase", "from": previous.get("phase"), "to": current.get("phase"),
        })
    previous_break = previous.get("break_track", {})
    current_break = current.get("break_track", {})
    if previous_break != current_break:
        events.append({
            "kind": "break_track", "from": previous_break.get("position"),
            "to": current_break.get("position"),
            "triggered": current_break.get("triggered", False),
        })
    old_players = {
        int(player.get("seat", index)): _player_snapshot(player)
        for index, player in enumerate(previous.get("players", []))
        if isinstance(player, Mapping)
    }
    for index, player in enumerate(current.get("players", [])):
        if not isinstance(player, Mapping):
            continue
        seat = int(player.get("seat", index))
        before = old_players.get(seat)
        after = _player_snapshot(player)
        if before is None:
            continue
        changes: dict[str, Any] = {}
        for key in ("money", "x_tokens", "tracks", "hand_count", "icons", "workers"):
            if before.get(key) != after.get(key):
                changes[key] = {"before": before.get(key), "after": after.get(key)}
        for key in ("partner_zoos", "universities", "action_cards"):
            if before.get(key) != after.get(key):
                changes[key] = {"before": before.get(key), "after": after.get(key)}
        new_cards = [
            {"id": card_id, "title": title}
            for card_id, title in after["played"].items()
            if card_id not in before["played"]
        ]
        if new_cards:
            changes["cards_played"] = new_cards
        new_buildings = [
            {"id": building_id, **details}
            for building_id, details in after["buildings"].items()
            if building_id not in before["buildings"]
        ]
        if new_buildings:
            changes["buildings_placed"] = new_buildings
        if changes:
            events.append({"kind": "player_changes", "seat": seat, "changes": changes})
    old_display = [item.get("id") for item in previous.get("card_display", [])]
    new_display = [item.get("id") for item in current.get("card_display", [])]
    if old_display != new_display:
        events.append({"kind": "card_display", "before": old_display, "after": new_display})
    return {
        "baseline": False,
        "from_version": previous.get("state_version", previous.get("decision_count")),
        "to_version": current_version,
        "events": events,
    }


def _decision_focus(
    observation: Mapping[str, Any], groups: list[dict[str, Any]],
) -> dict[str, Any]:
    pending = observation.get("pending_choice")
    focus = {
        "phase": observation.get("phase"),
        "active_seat": observation.get("active_seat"),
        "action_card": observation.get("turn", {}).get("action_card"),
        "legal_action_count": sum(int(row["count"]) for row in groups),
        "legal_action_groups": groups,
    }
    endgame = observation.get("endgame")
    if isinstance(endgame, Mapping) and endgame.get("triggered"):
        focus["endgame"] = {
            "triggered": True,
            "triggered_by": endgame.get("triggered_by"),
            "remaining_final_turn_seats": deepcopy(
                endgame.get("remaining_final_turn_seats", [])
            ),
            "is_my_final_action": bool(endgame.get("is_my_final_action")),
            "scoring_after_this_action": bool(
                endgame.get("scoring_after_this_action")
            ),
            "instruction": (
                endgame.get("instruction_en") or endgame.get("instruction_cn")
            ),
        }
    if isinstance(pending, Mapping):
        focus["pending_choice"] = deepcopy(dict(pending))
    return focus


def compact_ark_nova_observation(
    observation: Mapping[str, Any], delta: Mapping[str, Any],
    groups: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
) -> dict[str, Any]:
    viewer_seat = int(observation.get("viewer_seat", -1))
    players = [
        _compact_player(player, viewer_seat)
        for player in observation.get("players", []) if isinstance(player, Mapping)
    ]
    own = next((player for player in players if player["seat"] == viewer_seat), None)
    opponents = [player for player in players if player["seat"] != viewer_seat]
    # Avoid repeating complete public played-card faces in the default view.
    if own is not None:
        own["played_cards"]["cards"] = [
            {
                "id": card.get("id"), "title": card.get("title"),
                "type": card.get("type"), "detail_ref": card.get("detail_ref"),
            }
            for card in own["played_cards"]["cards"]
        ]
    break_rules = observation.get("break_rules_summary", {})
    compact_break_rules = {
        "steps": [
            {
                "order": item.get("order"), "key": item.get("key"),
                "description": item.get("description_en") or item.get("description_cn"),
            }
            for item in break_rules.get("steps", []) if isinstance(item, Mapping)
        ],
        "recurring_rule": (
            break_rules.get("recurring_rule_en")
            or break_rules.get("recurring_rule_cn")
        ),
    } if isinstance(break_rules, Mapping) else {}
    bonus_tiles = [
        {
            "id": tile.get("id"), "milestone": tile.get("milestone"),
            "label": tile.get("label_en") or tile.get("label_cn") or tile.get("label"),
            "available": tile.get("available"),
        }
        for tile in observation.get("game_board_bonus_tiles", [])
        if isinstance(tile, Mapping)
    ]
    break_track = observation.get("break_track", {})
    completed_breaks = int(break_track.get("count", 0) or 0)
    turn_count = int(observation.get("turn_count", 0) or 0)
    pacing_players = []
    for player in players:
        tracks = player.get("tracks", {})
        appeal = int(tracks.get("appeal", 0) or 0)
        conservation = int(tracks.get("conservation", 0) or 0)
        target = conservation_target_appeal(conservation)
        pacing_players.append({
            "seat": player.get("seat"),
            "appeal": appeal,
            "conservation": conservation,
            "appeal_needed_to_cross": max(0, target - appeal),
            "endgame_target_appeal": target,
        })
    game_pacing = {
        "completed_breaks": completed_breaks,
        "turns_completed": turn_count,
        "turns_per_completed_break": (
            round(turn_count / completed_breaks, 2) if completed_breaks else None
        ),
        "players": pacing_players,
        "objective_rules": [
            "The endgame is triggered when a player's Appeal reaches or crosses the opposing Conservation score position.",
            "Money has no direct endgame value; it matters only through actions and card effects that convert it into scoring progress.",
            "Break income, worker recall, and recurring rewards are benefits, but advancing the Break track also shortens the shared game clock.",
        ],
    }
    base_projects = [
        _compact_project(project)
        for project in observation.get("base_conservation_projects", [])
        if isinstance(project, Mapping)
    ]
    zoo_projects = [
        _compact_project(project)
        for project in observation.get("zoo_conservation_projects", [])
        if isinstance(project, Mapping)
    ]
    decision_focus = _decision_focus(observation, groups)
    if opportunities:
        decision_focus["eligible_conservation_projects"] = deepcopy(opportunities)
    result = {
        "schema_version": "agentbga.agent-observation.v2",
        "game": observation.get("game"),
        "rules_version": observation.get("rules_version"),
        "content_pack_id": observation.get("content_pack_id"),
        "content_hash": observation.get("content_hash"),
        "state_version": observation.get("state_version"),
        "viewer_seat": viewer_seat,
        "status": observation.get("status"),
        "endgame": deepcopy(observation.get("endgame", {})),
        "decision_focus": decision_focus,
        "changes_since_last_observation": deepcopy(dict(delta)),
        # Private state deliberately precedes the larger public board projection.
        # Some OpenAI-compatible providers cap individual tool results; keeping
        # the hand and initial draw first makes the seat's own cards reliably
        # visible even if a provider truncates the tail of the response.
        "self": own,
        "opponents": opponents,
        "rules": rules_catalog(),
        "global": {
            "turn_count": observation.get("turn_count"),
            "decision_count": observation.get("decision_count"),
            "break_track": deepcopy(observation.get("break_track", {})),
            "break_rules_summary": compact_break_rules,
            "solo_board": deepcopy(observation.get("solo_board")),
            "deck_count": observation.get("deck_count"),
            "discard_count": observation.get("discard_count"),
            "card_display": [
                compact_card(card) for card in observation.get("card_display", [])
                if isinstance(card, Mapping)
            ],
            "base_conservation_projects": base_projects,
            "zoo_conservation_projects": zoo_projects,
            "eligible_conservation_projects": deepcopy(opportunities),
            "association_display": deepcopy(observation.get("association_display", {})),
            "game_board_bonus_tiles": bonus_tiles,
            "game_pacing": game_pacing,
        },
        "pending_choice": deepcopy(observation.get("pending_choice")),
        "resource_tools": {
            "card": "inspect_card",
            "rules": "inspect_rules",
            "map": "inspect_map",
            "played_cards": "inspect_played_cards",
            "history": "inspect_history",
        },
    }
    if own is not None:
        private_first: dict[str, Any] = {}
        if own.get("initial_draw"):
            private_first["initial_draw"] = own["initial_draw"]
        if own.get("hand"):
            private_first["hand"] = own["hand"]
        if own.get("final_scoring_cards"):
            private_first["final_scoring_cards"] = own["final_scoring_cards"]
        result["self"] = {
            **private_first,
            **{
                key: value for key, value in own.items()
                if key not in {"initial_draw", "hand", "final_scoring_cards"}
            },
        }
    if observation.get("phase") == "initial_hand_selection" and own is not None:
        # Setup has a 70-combination legal space, but only one real decision:
        # compare the eight private cards and keep four.  Keep every card face
        # at the front while deferring unrelated public-board detail to its
        # normal inspection tools.
        keep_count = int(observation.get("initial_keep_required", 4) or 4)
        setup_instruction = (
            f"Choose exactly {keep_count} of the {len(own.get('initial_draw', []))} "
            "visible initial cards. All cards in self.initial_draw are visible. "
            "Before choosing, call inspect_card with either detail_ref or the bare card id "
            "for every card whose requirements or mechanics are not fully clear."
        )
        result["self"] = {
            key: deepcopy(result["self"][key]) for key in (
                "initial_draw", "final_scoring_cards", "seat", "money", "x_tokens",
                "tracks", "track_constraints", "score", "action_cards", "map",
            ) if key in result["self"]
        }
        result["opponents"] = [
            {
                key: deepcopy(player[key]) for key in (
                    "seat", "tracks", "score",
                ) if key in player
            }
            for player in opponents
        ]
        result["global"] = {
            key: deepcopy(result["global"][key]) for key in (
                "turn_count", "decision_count", "break_track",
                "base_conservation_projects",
            ) if key in result["global"]
        }
        result = {"setup_instruction": setup_instruction, **result}
    return {key: value for key, value in result.items() if value is not None}


def _build_resources(observation: Mapping[str, Any]) -> dict[str, Any]:
    cards: dict[str, dict[str, Any]] = {}
    _collect_cards(observation, cards)
    maps: dict[str, Any] = {}
    zones: dict[str, Any] = {}
    for player in observation.get("players", []):
        if not isinstance(player, Mapping):
            continue
        seat = player.get("seat")
        maps[f"map:seat-{seat}"] = {
            "seat": seat,
            "map": deepcopy(player.get("map", {})),
            "map_display": deepcopy(player.get("map_display", {})),
        }
        zones[f"zone:seat-{seat}:played"] = {
            "seat": seat,
            "cards": [
                deepcopy(dict(card)) for card in player.get("played_cards", [])
                if isinstance(card, Mapping)
            ],
        }
    return {
        "cards": cards, "maps": maps, "zones": zones,
        "rules": rules_resource(),
    }


def _load_cache(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def prepare_seat_context(
    context_path: Path, *, match_id: str, seat: int, version: Any,
    observation: dict[str, Any], legal: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create and persist the versioned context consumed by every harness."""
    flattened = _flatten_legal(legal)
    if observation.get("game") != "ark_nova":
        context = {
            "schema_version": CONTEXT_V1, "match_id": match_id, "seat": seat,
            "version": version, "observation": observation,
            "legal_actions": flattened,
        }
        if observation.get("game") in GAME_FILTERS:
            context["legal_action_query"] = query_metadata(observation["game"], flattened)
        context_path.write_text(
            json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        return context

    cache_path = context_path.with_name("agent-context-cache.json")
    cache = _load_cache(cache_path)
    previous = cache.get("observation") if cache.get("match_id") == match_id else None
    if isinstance(previous, Mapping) and (
        previous.get("state_version") == observation.get("state_version")
    ):
        delta = cache.get("last_delta") or observation_delta(None, observation)
        history = list(cache.get("history", []))
    else:
        delta = observation_delta(previous if isinstance(previous, Mapping) else None, observation)
        history = list(cache.get("history", [])) if cache.get("match_id") == match_id else []
        if not delta.get("baseline") and delta.get("events"):
            history.append(deepcopy(delta))
        history = history[-MAX_HISTORY_ITEMS:]
    compact_projects = [
        _compact_project(project)
        for key in ("base_conservation_projects", "zoo_conservation_projects")
        for project in observation.get(key, [])
        if isinstance(project, Mapping)
    ]
    opportunities = _association_project_opportunities(
        observation, compact_projects, legal,
    )
    annotated_legal = _annotate_association_starts(legal, opportunities)
    flattened = _flatten_legal(annotated_legal)
    groups = legal_action_groups(annotated_legal)
    compact = compact_ark_nova_observation(
        observation, delta, groups, opportunities,
    )
    resources = _build_resources(observation)
    v2_actions = [
        {**item, "_group": action_group(source)}
        for item, source in zip(flattened, annotated_legal, strict=True)
    ]
    context = {
        "schema_version": CONTEXT_V2,
        "match_id": match_id, "seat": seat, "version": version,
        "observation": compact,
        "legal_actions": v2_actions,
        "legal_action_groups": groups,
        "resources": resources,
        "history": history,
        "full_observation_digest": hashlib.sha256(_json_bytes(observation)).hexdigest(),
    }
    context_path.write_text(
        json.dumps(context, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    cache_path.write_text(json.dumps({
        "schema_version": "agentbga.agent-context-cache.v1",
        "match_id": match_id, "seat": seat,
        "observation": observation, "last_delta": delta, "history": history,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return context


def inspect_card(context: Mapping[str, Any], arguments: Mapping[str, Any]) -> Any:
    reference = arguments.get("card_ref")
    cards = context.get("resources", {}).get("cards", {})
    if isinstance(reference, str) and not reference.startswith("card:"):
        reference = f"card:{reference}"
    if not isinstance(reference, str) or reference not in cards:
        raise ValueError("card_ref is unavailable in this seat-scoped observation")
    result = deepcopy(cards[reference])
    housing_options = _animal_housing_options(result)
    if housing_options:
        result["housing_options"] = housing_options
    return result


def inspect_rules(context: Mapping[str, Any], arguments: Mapping[str, Any]) -> Any:
    """Return a bounded Ark Nova rules topic, or the topic catalog."""
    rules = context.get("resources", {}).get("rules")
    if not isinstance(rules, Mapping):
        raise ValueError("rules reference is unavailable for this game")
    topic = arguments.get("topic")
    if topic is None:
        return {
            key: deepcopy(value) for key, value in rules.items()
            if key != "details"
        }
    if not isinstance(topic, str) or not topic:
        raise ValueError("topic must be a non-empty string")
    return rule_topic(topic)


def inspect_map(context: Mapping[str, Any], arguments: Mapping[str, Any]) -> Any:
    seat = arguments.get("seat", context.get("seat"))
    if not isinstance(seat, int) or isinstance(seat, bool):
        raise ValueError("seat must be an integer")
    reference = f"map:seat-{seat}"
    maps = context.get("resources", {}).get("maps", {})
    if reference not in maps:
        raise ValueError("map is unavailable in this seat-scoped observation")
    resource = maps[reference]
    sections = arguments.get("sections")
    if not sections:
        return deepcopy(resource)
    if not isinstance(sections, list) or not all(isinstance(item, str) for item in sections):
        raise ValueError("sections must be a list of strings")
    game_map = resource.get("map", {})
    display = resource.get("map_display", {})
    buildings = game_map.get("buildings", [])
    result: dict[str, Any] = {
        "seat": seat,
        "map_id": game_map.get("id"),
        "placement_rules": {
            "current_connectivity_rule": (
                "Every new building must be adjacent to at least one existing building."
                if buildings else
                "This is the first building: it must cover at least one map-border hex."
            ),
            "shape_and_occupancy": (
                "The full fixed polyhex must be in bounds on legal unoccupied cells; "
                "Build-II cells require the Build card to be upgraded."
            ),
            "rules_topic": "build",
        },
    }
    if "terrain" in sections:
        result["terrain"] = {
            "coordinate_system": game_map.get("coordinate_system"),
            "cells": deepcopy(game_map.get("cells", [])),
        }
    if "buildings" in sections:
        result["buildings"] = deepcopy(buildings)
    if "rewards" in sections:
        result["placement_rewards"] = [
            {
                **deepcopy(dict(reward)),
                "effect_explanation": _map_reward_explanation(reward.get("effect", {})),
            }
            for reward in display.get("placement_rewards", [])
            if isinstance(reward, Mapping)
        ]
        result["conservation_rewards"] = deepcopy(display.get("conservation_rewards", []))
        result["coverage"] = deepcopy(display.get("coverage", {}))
    if "player_board" in sections:
        result["player_board"] = deepcopy(display.get("player_board", {}))
    return result


def _map_reward_explanation(effect: Any) -> str | None:
    if not isinstance(effect, Mapping):
        return None
    reward_type = effect.get("type")
    amount = effect.get("amount")
    if reward_type == "gain_money":
        return f"Immediately gain {amount} money when covered."
    if reward_type == "gain_x_token":
        return f"Immediately gain {amount} X-token(s) when covered."
    if reward_type == "gain_reputation":
        return f"Immediately gain {amount} Reputation when covered."
    if reward_type == "take_card":
        return "Immediately take one card from the deck or from within Reputation range."
    if reward_type == "clever":
        return (
            "Clever: after the current action finishes, move any chosen Action card to "
            "slot 1. It does not execute that card."
        )
    return None


def inspect_played_cards(
    context: Mapping[str, Any], arguments: Mapping[str, Any],
) -> dict[str, Any]:
    seat = arguments.get("seat", context.get("seat"))
    if not isinstance(seat, int) or isinstance(seat, bool):
        raise ValueError("seat must be an integer")
    zone = context.get("resources", {}).get("zones", {}).get(
        f"zone:seat-{seat}:played"
    )
    if not isinstance(zone, Mapping):
        raise ValueError("played-card zone is unavailable")
    kind = arguments.get("kind")
    cards = [
        card for card in zone.get("cards", [])
        if isinstance(card, Mapping) and (kind is None or _card_type(card) == kind)
    ]
    cursor = arguments.get("cursor", 0)
    limit = arguments.get("limit", DEFAULT_ACTION_PAGE_SIZE)
    cursor = cursor if isinstance(cursor, int) and cursor >= 0 else 0
    limit = max(1, min(MAX_ACTION_PAGE_SIZE, limit if isinstance(limit, int) else 20))
    page = cards[cursor:cursor + limit]
    next_cursor = cursor + len(page)
    return {
        "seat": seat, "kind": kind, "total": len(cards), "cursor": cursor,
        "next_cursor": next_cursor if next_cursor < len(cards) else None,
        "cards": [compact_card(card) for card in page],
    }


def inspect_history(
    context: Mapping[str, Any], arguments: Mapping[str, Any],
) -> dict[str, Any]:
    rows = list(context.get("history", []))
    since = arguments.get("since_version")
    if isinstance(since, int) and not isinstance(since, bool):
        rows = [row for row in rows if int(row.get("to_version", -1)) > since]
    cursor = arguments.get("cursor", 0)
    limit = arguments.get("limit", DEFAULT_ACTION_PAGE_SIZE)
    cursor = cursor if isinstance(cursor, int) and cursor >= 0 else 0
    limit = max(1, min(MAX_ACTION_PAGE_SIZE, limit if isinstance(limit, int) else 20))
    page = rows[cursor:cursor + limit]
    next_cursor = cursor + len(page)
    return {
        "history_scope": "observed_state_changes",
        "complete_from_version": rows[0].get("from_version") if rows else None,
        "total": len(rows), "cursor": cursor,
        "next_cursor": next_cursor if next_cursor < len(rows) else None,
        "items": deepcopy(page),
    }
