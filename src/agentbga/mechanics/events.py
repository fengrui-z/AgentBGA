"""Stable constructors for cross-game semantic events."""

from __future__ import annotations

from typing import Any


def domain_event(event_type: str, *, seat: int | None = None, **payload: Any) -> dict[str, Any]:
    if not event_type:
        raise ValueError("event type must not be empty")
    result: dict[str, Any] = {"type": event_type}
    if seat is not None:
        result["seat"] = seat
    result.update(payload)
    return result


def action_accepted(seat: int, action: dict[str, Any], **context: Any) -> dict[str, Any]:
    """The common first event emitted by every successful transition."""
    return domain_event("action_accepted", seat=seat, action=action, **context)
