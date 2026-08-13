import copy
import unittest

from agentbga import ark_nova


class ArkNovaSetupTests(unittest.TestCase):
    def test_setup_is_deterministic_and_matches_beginner_setup_shape(self):
        first = ark_nova.new_game(2, 42)
        second = ark_nova.new_game(2, 42)
        self.assertEqual(first, second)
        self.assertEqual("setup", first["status"])
        self.assertEqual(6, len(first["card_display"]))
        self.assertEqual(3, len(first["base_conservation_projects"]))
        self.assertEqual(4, len(first["game_board_bonus_tiles"]))
        self.assertEqual(12, len(first["base_conservation_projects"]) + len(first["base_conservation_deck"]))
        self.assertEqual(
            212,
            len(first["card_display"]) + len(first["zoo_deck"])
            + sum(len(player["initial_draw"]) for player in first["players"]),
        )
        for seat, player in enumerate(first["players"]):
            self.assertEqual(25, player["money"])
            self.assertEqual(seat, player["appeal"])
            self.assertEqual(8, len(player["initial_draw"]))
            self.assertEqual(2, len(player["final_scoring_cards"]))
            self.assertEqual("animals", player["action_cards"][0]["action"])
            self.assertEqual("map-a", player["map"]["id"])
            self.assertEqual(3, player["map"]["buildings"][0]["size"])

    def test_observation_hides_other_seats_private_cards(self):
        state = ark_nova.new_game(3, 7)
        view = ark_nova.observe(state, 0)
        self.assertEqual({"hidden": True}, view["card_display"][0])
        self.assertIn("id", view["players"][0]["initial_draw"][0])
        self.assertEqual({"hidden": True}, view["players"][1]["initial_draw"][0])
        self.assertIn("id", view["players"][0]["final_scoring_cards"][0])
        self.assertEqual({"hidden": True}, view["players"][2]["final_scoring_cards"][0])
        self.assertNotIn("zoo_deck", view)
        self.assertEqual(len(state["zoo_deck"]), view["deck_count"])

    def test_card_uniqueness_invariant_detects_duplicate(self):
        state = ark_nova.new_game(4, 9)
        ark_nova.validate_state(state)
        broken = copy.deepcopy(state)
        broken["card_display"][0] = broken["players"][0]["initial_draw"][0]
        with self.assertRaisesRegex(AssertionError, "more than one location"):
            ark_nova.validate_state(broken)

    def test_setup_skeleton_rejects_actions_explicitly(self):
        state = ark_nova.new_game(2, 1)
        self.assertEqual([], ark_nova.legal_actions(state, 0))
        with self.assertRaisesRegex(ark_nova.RuleError, "not implemented"):
            ark_nova.apply_action(state, 0, {"type": "animals"})


if __name__ == "__main__":
    unittest.main()
