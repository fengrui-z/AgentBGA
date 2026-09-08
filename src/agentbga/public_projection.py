"""Shared spectator-safe projections for actions and domain events."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any, Mapping


_PRIVATE_ACTION_TYPES = frozenset({"choose_initial_hand", "resolve_semantic_choice"})


def _private_action_type(action_id: str) -> str | None:
    if action_id.startswith("setup:keep:"):
        return "choose_initial_hand"
    if action_id.startswith("semantic-choice-"):
        return "resolve_semantic_choice"
    return None


def _opaque_action_id(*, match_id: str, version: int, seat: int, action_type: str) -> str:
    public_scope = f"{match_id}:{version}:{seat}:{action_type}"
    digest = hashlib.sha256(public_scope.encode("utf-8")).hexdigest()[:16]
    return f"private-action-{digest}"


def public_action(action: Mapping[str, Any]) -> dict[str, Any]:
    """Return an action payload that cannot expose private option identities."""

    action_type = action.get("type")
    if action_type == "choose_initial_hand":
        card_ids = action.get("card_ids")
        return {
            "type": action_type,
            "kept_count": len(card_ids) if isinstance(card_ids, list) else 0,
        }
    if action_type == "resolve_semantic_choice":
        option_ids = action.get("option_ids")
        return {
            "type": action_type,
            "choice_id": action.get("choice_id"),
            "selected_count": len(option_ids) if isinstance(option_ids, list) else 0,
        }
    return deepcopy(dict(action))


def public_action_id(
    action_id: str, action: Mapping[str, Any], *, match_id: str, version: int, seat: int,
) -> str:
    """Replace private choice IDs with an opaque decision-scoped identifier.

    The digest deliberately excludes ``action_id``.  Hashing a small hidden
    option set directly would still permit brute-force recovery of the selected
    cards.
    """

    if action.get("type") not in _PRIVATE_ACTION_TYPES:
        return action_id
    return _opaque_action_id(
        match_id=match_id, version=version, seat=seat,
        action_type=str(action.get("type")),
    )


def public_controller_event(
    event: Mapping[str, Any], *, match_id: str, version: int, seat: int,
) -> dict[str, Any]:
    """Redact private action references from harness audit events."""

    def project(value: Any) -> Any:
        if isinstance(value, Mapping):
            result = {}
            for key, item in value.items():
                if key == "action_id" and isinstance(item, str):
                    action_type = _private_action_type(item)
                    if action_type is not None:
                        item = _opaque_action_id(
                            match_id=match_id, version=version, seat=seat,
                            action_type=action_type,
                        )
                result[key] = project(item)
            return result
        if isinstance(value, list):
            return [project(item) for item in value]
        return deepcopy(value)

    return project(event)


def public_game_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Project an authoritative event into a spectator-safe audit event."""

    result = deepcopy(dict(event))
    event_type = result.get("type")
    if event_type == "action_accepted" and isinstance(result.get("action"), Mapping):
        result["action"] = public_action(result["action"])
    elif event_type == "semantic_choice_resolved":
        option_ids = result.pop("option_ids", None)
        result["selected_count"] = len(option_ids) if isinstance(option_ids, list) else 0
    elif event_type == "final_scoring_card_discarded":
        result.pop("card_id", None)
        result["discarded_count"] = 1
    elif event_type == "map_card_reward_taken" and result.get("source") == "deck":
        # Both Build rewards and semantic card effects emit this event. The
        # authoritative event keeps the identity for replay/auditing, while
        # only cards taken from the public display may reveal it here.
        result.pop("card_id", None)
    return result
