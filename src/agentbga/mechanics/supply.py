"""Descriptions and deterministic filtering for candidate resource sources."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SupplySource:
    source_id: str
    resource: str
    amount: int
    source_type: str
    owner: int | None = None
    distance: int | None = None
    unit_price: int = 0
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not self.source_id or not self.resource or not self.source_type:
            raise ValueError("supply source identifiers must not be empty")
        if not isinstance(self.amount, int) or isinstance(self.amount, bool) or self.amount < 0:
            raise ValueError("supply source amount must be a non-negative integer")
        if self.distance is not None and self.distance < 0:
            raise ValueError("supply source distance must be non-negative")
        if self.unit_price < 0:
            raise ValueError("supply source price must be non-negative")


def eligible_sources(
    sources: Iterable[SupplySource], *, resource: str,
    predicate: Callable[[SupplySource], bool] | None = None,
) -> list[SupplySource]:
    """Return stable candidate sources; the game plugin supplies legality policy."""
    return [source for source in sources
            if source.resource == resource and source.amount > 0
            and (predicate is None or predicate(source))]


def nearest_sources(sources: Iterable[SupplySource]) -> list[SupplySource]:
    candidates = list(sources)
    if not candidates:
        return []
    if any(source.distance is None for source in candidates):
        raise ValueError("nearest-source selection requires a distance for every source")
    distance = min(source.distance for source in candidates)
    return [source for source in candidates if source.distance == distance]
