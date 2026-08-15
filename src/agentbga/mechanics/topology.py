"""Topology primitives shared by map, route, and adjacency-heavy games."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Hashable, Iterable, Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar


Node = TypeVar("Node", bound=Hashable)
Hex = tuple[int, int]


@dataclass(frozen=True)
class NetworkEdge(Generic[Node]):
    edge_id: str
    first: Node
    second: Node
    kind: str
    owner: int | None = None
    active: bool = True


def edge_adjacency(
    edges: Iterable[NetworkEdge[Node]], *,
    predicate: Callable[[NetworkEdge[Node]], bool] | None = None,
) -> dict[Node, set[Node]]:
    """Project typed, owned edges into an undirected adjacency mapping."""
    adjacency: dict[Node, set[Node]] = {}
    for edge in edges:
        if not edge.active or (predicate is not None and not predicate(edge)):
            continue
        adjacency.setdefault(edge.first, set()).add(edge.second)
        adjacency.setdefault(edge.second, set()).add(edge.first)
    return adjacency


def shortest_distances(
    starts: Iterable[Node], adjacency: Mapping[Node, Iterable[Node]],
) -> dict[Node, int]:
    """Return unweighted shortest-path distances from one or more starting nodes."""
    distances = {node: 0 for node in starts}
    frontier = deque(distances)
    while frontier:
        node = frontier.popleft()
        for neighbor in adjacency.get(node, ()):
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                frontier.append(neighbor)
    return distances


def reachable_nodes(
    starts: Iterable[Node], adjacency: Mapping[Node, Iterable[Node]],
) -> set[Node]:
    return set(shortest_distances(starts, adjacency))


def player_network_nodes(
    owned_nodes: Iterable[Node], edges: Iterable[NetworkEdge[Node]], seat: int,
) -> set[Node]:
    """Nodes containing a player's pieces or touching one of their active edges."""
    result = set(owned_nodes)
    for edge in edges:
        if edge.active and edge.owner == seat:
            result.update((edge.first, edge.second))
    return result


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
