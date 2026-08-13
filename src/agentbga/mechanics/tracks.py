"""Bounded-track operations for break, reputation, income, and similar tracks."""

from __future__ import annotations

from typing import Any, MutableMapping


def crossed_milestones(before: int, after: int, milestones: list[int] | tuple[int, ...]) -> list[int]:
    """Return milestones crossed in movement order, including reverse tracks."""
    if after >= before:
        return sorted(point for point in milestones if before < point <= after)
    return sorted((point for point in milestones if after <= point < before), reverse=True)


def advance_track(
    track: MutableMapping[str, Any], steps: int, *, position_key: str = "position",
    limit_key: str = "limit", triggered_key: str | None = "triggered",
) -> int:
    if not isinstance(steps, int) or isinstance(steps, bool) or steps < 0:
        raise ValueError("track advance must be a non-negative integer")
    before = track[position_key]
    after = min(track[limit_key], before + steps)
    track[position_key] = after
    if triggered_key is not None:
        track[triggered_key] = after >= track[limit_key]
    return after - before


def reset_track(
    track: MutableMapping[str, Any], *, position: int = 0, position_key: str = "position",
    triggered_key: str | None = "triggered",
) -> None:
    track[position_key] = position
    if triggered_key is not None:
        track[triggered_key] = False
