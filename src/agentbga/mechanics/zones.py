"""Helpers for moving and projecting pieces across named game zones."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Iterable, TypeVar


T = TypeVar("T")


def _default_id(item: Any) -> str:
    return item if isinstance(item, str) else item["id"]


def remove_item(
    source: list[T], item_id: str, *, identify: Callable[[T], str] = _default_id,
) -> T:
    for index, item in enumerate(source):
        if identify(item) == item_id:
            return source.pop(index)
    raise KeyError(f"item is not present in source zone: {item_id}")


def move_item(
    source: list[T], destination: list[T], item_id: str, *,
    identify: Callable[[T], str] = _default_id,
) -> T:
    item = remove_item(source, item_id, identify=identify)
    destination.append(item)
    return item


def hidden_items(items_or_count: Iterable[Any] | int) -> list[dict[str, bool]]:
    count = items_or_count if isinstance(items_or_count, int) else sum(1 for _ in items_or_count)
    return [{"hidden": True} for _ in range(count)]


def validate_unique_items(
    zones: Iterable[Iterable[T]], *, expected_count: int | None = None,
    identify: Callable[[T], str] = _default_id, label: str = "items",
) -> None:
    identifiers = [identify(item) for zone in zones for item in zone]
    if expected_count is not None and len(identifiers) != expected_count:
        raise AssertionError(f"{label} expected {expected_count} items, found {len(identifiers)}")
    if len(identifiers) != len(set(identifiers)):
        raise AssertionError(f"{label} must be unique across zones")


def private_items(items: list[T], visible: bool) -> list[T] | list[dict[str, bool]]:
    """Deep-copy a zone for its owner, otherwise preserve only its size."""
    return deepcopy(items) if visible else hidden_items(items)
