"""Topology primitives shared by map, route, and adjacency-heavy games."""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping
from typing import TypeVar


Node = TypeVar("Node", bound=Hashable)
Hex = tuple[int, int]


def axial_hex_neighbors(cell: Hex) -> set[Hex]:
    q, r = cell
    return {(q + 1, r), (q - 1, r), (q, r + 1), (q, r - 1), (q + 1, r - 1), (q - 1, r + 1)}


def axial_hex_distance(first: Hex, second: Hex) -> int:
    dq, dr = first[0] - second[0], first[1] - second[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def is_connected(nodes: Iterable[Node], adjacency: Mapping[Node, Iterable[Node]]) -> bool:
    """Test connectivity for an arbitrary board graph."""
    remaining = set(nodes)
    if not remaining:
        return True
    frontier = [remaining.pop()]
    while frontier:
        node = frontier.pop()
        reachable = remaining.intersection(adjacency.get(node, ()))
        remaining.difference_update(reachable)
        frontier.extend(reachable)
    return not remaining


def adjacent_to_any(
    nodes: Iterable[Node], occupied: Iterable[Node], adjacency: Mapping[Node, Iterable[Node]],
) -> bool:
    occupied_set = set(occupied)
    return any(occupied_set.intersection(adjacency.get(node, ())) for node in nodes)
