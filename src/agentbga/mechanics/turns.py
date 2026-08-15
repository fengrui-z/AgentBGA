"""Turn budgets and stable metric-based player ordering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ActionBudget:
    """Immutable counter for decisions or actions inside a player turn."""

    total: int
    remaining: int

    def __post_init__(self) -> None:
        if not isinstance(self.total, int) or isinstance(self.total, bool) or self.total < 0:
            raise ValueError("action budget total must be a non-negative integer")
        if (not isinstance(self.remaining, int) or isinstance(self.remaining, bool)
                or not 0 <= self.remaining <= self.total):
            raise ValueError("action budget remaining must be between zero and total")

    @classmethod
    def start(cls, total: int) -> ActionBudget:
        return cls(total=total, remaining=total)

    @property
    def used(self) -> int:
        return self.total - self.remaining

    @property
    def complete(self) -> bool:
        return self.remaining == 0

    def spend(self, amount: int = 1) -> ActionBudget:
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("action spend must be a positive integer")
        if amount > self.remaining:
            raise ValueError("action spend exceeds remaining budget")
        return ActionBudget(self.total, self.remaining - amount)

    def to_dict(self) -> dict[str, int]:
        return {"total": self.total, "remaining": self.remaining, "used": self.used}


def stable_metric_order(
    current_order: Sequence[int], metrics: Mapping[int, int | float], *, reverse: bool = False,
) -> list[int]:
    """Sort seats by a metric while preserving the previous order for ties."""
    seats = list(current_order)
    if len(seats) != len(set(seats)):
        raise ValueError("current order contains duplicate seats")
    missing = set(seats) - set(metrics)
    if missing:
        raise KeyError(f"metrics are missing seats: {', '.join(map(str, sorted(missing)))}")
    previous_position = {seat: index for index, seat in enumerate(seats)}
    direction = -1 if reverse else 1
    return sorted(seats, key=lambda seat: (direction * metrics[seat], previous_position[seat]))
