"""Shared deterministic ranking policies."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


def assign_competition_ranks(
    rows: Iterable[dict[str, Any]], *, sort_key: Callable[[dict[str, Any]], tuple[Any, ...]],
    tie_key: Callable[[dict[str, Any]], tuple[Any, ...]],
) -> list[dict[str, Any]]:
    """Sort rows and assign 1, 2, 2, 4 style ranks without mutating callers."""
    ranked = [dict(row) for row in rows]
    ranked.sort(key=sort_key)
    previous: tuple[Any, ...] | None = None
    rank = 0
    for index, row in enumerate(ranked):
        current = tie_key(row)
        if current != previous:
            rank = index + 1
            previous = current
        row["rank"] = rank
    return ranked
