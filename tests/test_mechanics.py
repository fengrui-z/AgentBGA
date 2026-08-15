import copy
import unittest

from agentbga.mechanics import (
    ActionSpace,
    ActionBudget,
    DecisionStep,
    MarketTrack,
    NetworkEdge,
    SupplySource,
    adjacent_to_any,
    adjust_resources,
    advance_track,
    assign_competition_ranks,
    axial_hex_distance,
    axial_hex_neighbors,
    crossed_milestones,
    discounted_cost,
    edge_adjacency,
    eligible_sources,
    hidden_items,
    is_connected,
    nearest_sources,
    payment_options,
    reset_track,
    player_network_nodes,
    reachable_nodes,
    shortest_distances,
    stable_metric_order,
    state_digest,
    transfer_resources,
    validate_resource_pool,
    validate_unique_items,
)
from agentbga.mechanics.zones import move_item, private_items


class MechanicsTests(unittest.TestCase):
    def test_action_space_ids_are_order_independent_and_require_canonical_action(self):
        action = {"type": "pay", "resources": {"coal": 1, "iron": 2}}
        reordered = {"resources": {"iron": 2, "coal": 1}, "type": "pay"}
        space = ActionSpace.from_actions("build", 7, [action])
        self.assertEqual(space.action_id(action), space.action_id(reordered))
        self.assertIs(action, space.require(reordered))
        with self.assertRaisesRegex(ValueError, "not legal"):
            space.require({"type": "pass"})

    def test_state_digest_is_stable_for_equivalent_json(self):
        self.assertEqual(state_digest({"a": 1, "b": [2]}), state_digest({"b": [2], "a": 1}))

    def test_resource_changes_and_transfers_are_atomic(self):
        bank = {"coal": 3, "iron": 1}
        player = {"coal": 0, "iron": 0}
        transfer_resources(bank, player, {"coal": 2})
        self.assertEqual(({"coal": 1, "iron": 1}, {"coal": 2, "iron": 0}), (bank, player))
        before = copy.deepcopy((bank, player))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            transfer_resources(bank, player, {"iron": 2})
        self.assertEqual(before, (bank, player))
        adjust_resources(player, {"coal": -1, "iron": 4})
        self.assertEqual({"coal": 1, "iron": 4}, player)
        validate_resource_pool(player, expected_keys={"coal", "iron"})

    def test_cost_resolver_supports_discounts_and_wildcards(self):
        self.assertEqual({"blue": 2, "red": 0}, discounted_cost(
            {"blue": 3, "red": 1}, {"blue": 1, "red": 5},
        ))
        options = payment_options(
            {"blue": 3, "red": 1}, {"blue": 2, "red": 1, "gold": 2},
            discounts={"blue": 1}, wildcard="gold",
        )
        self.assertEqual({"blue": 2, "red": 1}, options[0])
        self.assertIn({"blue": 1, "red": 1, "gold": 1}, options)

    def test_zones_preserve_identity_and_hide_only_contents(self):
        deck = [{"id": "card-1"}, {"id": "card-2"}]
        hand = []
        moved = move_item(deck, hand, "card-2")
        self.assertIs(moved, hand[0])
        self.assertEqual([{"hidden": True}], private_items(hand, False))
        self.assertEqual([{"hidden": True}, {"hidden": True}], hidden_items(2))
        validate_unique_items([deck, hand], expected_count=2)
        with self.assertRaisesRegex(AssertionError, "unique"):
            validate_unique_items([deck, deck])

    def test_bounded_track_and_competition_rank_policy(self):
        track = {"position": 8, "limit": 10, "triggered": False}
        self.assertEqual(2, advance_track(track, 5))
        self.assertEqual({"position": 10, "limit": 10, "triggered": True}, track)
        reset_track(track)
        self.assertEqual(0, track["position"])
        self.assertFalse(track["triggered"])
        self.assertEqual([3, 5], crossed_milestones(2, 6, [1, 3, 5, 7]))
        self.assertEqual([5, 3], crossed_milestones(6, 2, [1, 3, 5, 7]))
        ranked = assign_competition_ranks(
            [{"seat": 0, "score": 3}, {"seat": 1, "score": 5}, {"seat": 2, "score": 3}],
            sort_key=lambda row: (-row["score"], row["seat"]),
            tie_key=lambda row: (row["score"],),
        )
        self.assertEqual([(1, 1), (0, 2), (2, 2)], [(r["seat"], r["rank"]) for r in ranked])

    def test_topology_supports_hex_maps_and_generic_networks(self):
        self.assertEqual(6, len(axial_hex_neighbors((0, 0))))
        self.assertEqual(3, axial_hex_distance((0, 0), (2, -3)))
        graph = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}, "x": set()}
        self.assertTrue(is_connected({"a", "b", "c"}, graph))
        self.assertFalse(is_connected({"a", "x"}, graph))
        self.assertTrue(adjacent_to_any({"c"}, {"b"}, graph))

    def test_decision_step_keeps_turn_protocol_shape(self):
        self.assertEqual(
            {"active_seat": 2, "decision": "choose_route", "action_card": None,
             "remaining_plays": 1},
            DecisionStep(2, "choose_route", "route", remaining_plays=1).to_dict(),
        )

    def test_action_budget_and_stable_metric_turn_order(self):
        budget = ActionBudget.start(2)
        self.assertEqual({"total": 2, "remaining": 2, "used": 0}, budget.to_dict())
        budget = budget.spend()
        self.assertEqual(1, budget.used)
        self.assertFalse(budget.complete)
        self.assertTrue(budget.spend().complete)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            budget.spend(2)

        self.assertEqual(
            [2, 0, 1, 3],
            stable_metric_order([2, 0, 1, 3], {0: 4, 1: 9, 2: 4, 3: 9}),
        )
        self.assertEqual(
            [1, 3, 2, 0],
            stable_metric_order([2, 0, 1, 3], {0: 4, 1: 9, 2: 4, 3: 9}, reverse=True),
        )

    def test_typed_network_supports_filters_distances_and_player_networks(self):
        edges = [
            NetworkEdge("canal-ab", "a", "b", "canal", owner=0),
            NetworkEdge("rail-bc", "b", "c", "rail", owner=1),
            NetworkEdge("closed-cd", "c", "d", "rail", owner=0, active=False),
        ]
        all_open = edge_adjacency(edges)
        canals = edge_adjacency(edges, predicate=lambda edge: edge.kind == "canal")
        self.assertEqual({"a", "b", "c"}, reachable_nodes(["a"], all_open))
        self.assertEqual({"a", "b"}, reachable_nodes(["a"], canals))
        self.assertEqual(2, shortest_distances(["a"], all_open)["c"])
        self.assertEqual({"mine", "a", "b"}, player_network_nodes(["mine"], edges, 0))

    def test_supply_candidates_leave_source_policy_to_the_game(self):
        sources = [
            SupplySource("coal-near", "coal", 2, "industry", owner=1, distance=1),
            SupplySource("coal-far", "coal", 1, "industry", owner=0, distance=3),
            SupplySource("empty", "coal", 0, "industry", distance=0),
            SupplySource("iron", "iron", 2, "industry", distance=1),
        ]
        coal = eligible_sources(sources, resource="coal")
        self.assertEqual(["coal-near", "coal-far"], [source.source_id for source in coal])
        self.assertEqual(["coal-near"], [source.source_id for source in nearest_sources(coal)])
        own = eligible_sources(sources, resource="coal", predicate=lambda source: source.owner == 0)
        self.assertEqual(["coal-far"], [source.source_id for source in own])

    def test_market_track_quotes_consumes_and_refills_without_game_policy(self):
        market = MarketTrack(
            prices=(1, 2, 3), occupied=[True, False, True],
            purchase_order=(0, 1, 2), refill_order=(2, 1, 0), external_price=5,
        )
        self.assertEqual((1, 3, 5), market.quote(3).unit_prices)
        paid = market.consume(2)
        self.assertEqual(4, paid.total_price)
        self.assertEqual([False, False, False], market.occupied)
        earned = market.refill(2)
        self.assertEqual((3, 2), earned.unit_prices)
        self.assertEqual([False, True, True], market.occupied)


if __name__ == "__main__":
    unittest.main()
