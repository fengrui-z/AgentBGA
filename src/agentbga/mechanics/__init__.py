"""Reusable, game-agnostic mechanisms for deterministic board-game plugins.

The package deliberately models small mechanisms rather than game rules.  A
game plugin remains responsible for deciding *when* a transfer, zone move, or
track advance is legal and what it means in that game's rules.
"""

from .actions import ActionSpace, canonical_json, state_digest
from .decisions import DecisionStep
from .events import action_accepted, domain_event
from .markets import MarketQuote, MarketTrack
from .rankings import assign_competition_ranks
from .resources import (
    adjust_resources,
    discounted_cost,
    payment_options,
    transfer_resources,
    validate_resource_pool,
)
from .supply import SupplySource, eligible_sources, nearest_sources
from .topology import (
    NetworkEdge,
    adjacent_to_any,
    axial_hex_distance,
    axial_hex_neighbors,
    edge_adjacency,
    is_connected,
    player_network_nodes,
    reachable_nodes,
    shortest_distances,
)
from .tracks import advance_track, crossed_milestones, reset_track
from .turns import ActionBudget, stable_metric_order
from .zones import hidden_items, move_item, private_items, remove_item, validate_unique_items

__all__ = [
    "ActionSpace",
    "ActionBudget",
    "DecisionStep",
    "MarketQuote",
    "MarketTrack",
    "NetworkEdge",
    "SupplySource",
    "action_accepted",
    "adjacent_to_any",
    "adjust_resources",
    "advance_track",
    "assign_competition_ranks",
    "axial_hex_distance",
    "axial_hex_neighbors",
    "canonical_json",
    "crossed_milestones",
    "discounted_cost",
    "domain_event",
    "edge_adjacency",
    "eligible_sources",
    "hidden_items",
    "move_item",
    "nearest_sources",
    "payment_options",
    "private_items",
    "player_network_nodes",
    "reachable_nodes",
    "remove_item",
    "reset_track",
    "state_digest",
    "stable_metric_order",
    "shortest_distances",
    "is_connected",
    "transfer_resources",
    "validate_resource_pool",
    "validate_unique_items",
]
