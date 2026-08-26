"""Unified legal-action routing for the staged official rules engine."""

from __future__ import annotations

from typing import Any, Mapping

from .actions import (
    decline_unavailable_hypnosis_action,
    legal_action_starts,
    start_action,
    take_x_token_action,
)
from .animals_action import apply_animals_execution_action, legal_animals_execution_actions
from .association_action import (
    apply_association_execution_action,
    legal_association_execution_actions,
)
from .build_action import apply_build_execution_action, legal_build_execution_actions
from .cards_action import apply_cards_execution_action, legal_cards_execution_actions
from .content import ContentEntry, ContentPack
from .semantics import SemanticEngine, SemanticRuleError
from .sponsors_action import (
    apply_bonus_sponsor_action,
    apply_sponsors_execution_action,
    legal_bonus_sponsor_actions,
    legal_sponsors_execution_actions,
)


def content_entry_indexes(pack: ContentPack) -> dict[str, dict[str, ContentEntry]]:
    """Build stable per-domain indexes once at a server boundary."""
    return {
        collection: {entry.id: entry for entry in entries}
        for collection, entries in pack.collections.items()
    }


def legal_official_actions(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    content: ContentPack | Mapping[str, Mapping[str, ContentEntry]],
) -> list[dict[str, Any]]:
    """Return authoritative semantic, execution, or turn-start actions."""
    indexes = content_entry_indexes(content) if isinstance(content, ContentPack) else content
    resolution = state["resolution"]
    if resolution["queue"] or resolution["pending_choice"] is not None:
        return engine.legal_choice_actions(state, seat)
    if state["turn"].get("bonus_sponsor_play") is not None:
        return legal_bonus_sponsor_actions(
            engine, state, seat, indexes.get("sponsors", {}),
        )
    session = state["turn"].get("action_session")
    if session is not None:
        return _legal_domain_actions(engine, state, seat, indexes)
    result = []
    for candidate in legal_action_starts(state, seat):
        action = candidate["action"]
        if action["type"] == "take_x_token_action":
            result.append(candidate)
            continue
        simulated, _ = start_action(
            dict(state), seat, action["action_card_id"],
            x_by_execution=action["x_by_execution"],
            multiplier_tokens=action["multiplier_tokens"],
        )
        if _legal_domain_actions(engine, simulated, seat, indexes):
            result.append(candidate)
    if not result and state["turn"].get("hypnosis_action") is not None:
        result.append({
            "id": "hypnosis:unavailable",
            "label": "Copied action has no legal execution",
            "action": {"type": "decline_unavailable_hypnosis_action"},
        })
    return result


def apply_official_action(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    content: ContentPack | Mapping[str, Mapping[str, ContentEntry]],
    action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate against the unified legal list, then dispatch one action."""
    if not isinstance(action, Mapping):
        raise SemanticRuleError("official action must be an object")
    requested = dict(action)
    legal = [item["action"] for item in legal_official_actions(engine, state, seat, content)]
    if requested not in legal:
        raise SemanticRuleError("official action is not currently legal")
    indexes = content_entry_indexes(content) if isinstance(content, ContentPack) else content
    action_type = requested.get("type")
    if action_type == "start_action":
        return start_action(
            state, seat, requested["action_card_id"],
            x_by_execution=requested["x_by_execution"],
            multiplier_tokens=requested["multiplier_tokens"],
        )
    if action_type == "take_x_token_action":
        return take_x_token_action(state, seat, requested["action_card_id"])
    if action_type == "decline_unavailable_hypnosis_action":
        return decline_unavailable_hypnosis_action(state, seat)
    if action_type == "resolve_semantic_choice":
        return engine.submit_choice(
            state, seat, requested["choice_id"], requested["option_ids"],
        )
    if state["turn"].get("bonus_sponsor_play") is not None:
        return apply_bonus_sponsor_action(
            engine, state, seat, indexes.get("sponsors", {}), requested,
        )
    session = state["turn"].get("action_session")
    if session is None:
        raise SemanticRuleError("domain action requires an active action session")
    if session["action"] == "cards":
        return apply_cards_execution_action(engine, state, seat, requested)
    if session["action"] == "build":
        return apply_build_execution_action(engine, state, seat, requested)
    if session["action"] == "animals":
        return apply_animals_execution_action(
            engine, state, seat, indexes.get("animals", {}), requested,
        )
    if session["action"] == "association":
        projects = {
            **indexes.get("base_conservation_projects", {}),
            **indexes.get("zoo_conservation_projects", {}),
        }
        return apply_association_execution_action(engine, state, seat, projects, requested)
    return apply_sponsors_execution_action(
        engine, state, seat, indexes.get("sponsors", {}), requested,
    )


def _legal_domain_actions(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    indexes: Mapping[str, Mapping[str, ContentEntry]],
) -> list[dict[str, Any]]:
    session = state["turn"].get("action_session")
    if session is None:
        return []
    action = session["action"]
    if action == "cards":
        return legal_cards_execution_actions(state, seat)
    if action == "build":
        return legal_build_execution_actions(state, seat)
    if action == "animals":
        return legal_animals_execution_actions(
            engine, state, seat, indexes.get("animals", {}),
        )
    if action == "association":
        projects = {
            **indexes.get("base_conservation_projects", {}),
            **indexes.get("zoo_conservation_projects", {}),
        }
        return legal_association_execution_actions(engine, state, seat, projects)
    if action == "sponsors":
        return legal_sponsors_execution_actions(
            engine, state, seat, indexes.get("sponsors", {}),
        )
    raise SemanticRuleError(f"unknown official action domain: {action}")
