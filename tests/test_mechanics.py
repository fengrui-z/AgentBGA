import copy
import unittest

from agentbga.mechanics import (
    ActionSpace,
    DecisionStep,
    adjacent_to_any,
    adjust_resources,
    advance_track,
    assign_competition_ranks,
    axial_hex_distance,
    axial_hex_neighbors,
    crossed_milestones,
    discounted_cost,
    hidden_items,
    is_connected,
    payment_options,
    reset_track,
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


if __name__ == "__main__":
    unittest.main()
