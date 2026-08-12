import random
import unittest

from agentbga import splendor


class SplendorTests(unittest.TestCase):
    def test_catalog_and_setup(self):
        self.assertEqual(90, len(splendor.CARDS))
        self.assertEqual({1: 40, 2: 30, 3: 20}, {
            tier: sum(card["tier"] == tier for card in splendor.CARDS.values())
            for tier in (1, 2, 3)
        })
        # Known source row: the first black tier-1 card costs one of every
        # colored gem except black.
        self.assertEqual("black", splendor.CARDS["t1-black-1"]["bonus"])
        self.assertEqual(
            {"white": 1, "blue": 1, "green": 1, "red": 1, "black": 0},
            splendor.CARDS["t1-black-1"]["cost"],
        )
        state = splendor.new_game(2, 42)
        splendor.validate_state(state)
        self.assertEqual(4, state["bank"]["white"])
        self.assertEqual(3, len(state["available_nobles"]))

    def test_setup_is_deterministic(self):
        self.assertEqual(splendor.new_game(4, 123), splendor.new_game(4, 123))
        self.assertNotEqual(splendor.new_game(4, 123)["market"], splendor.new_game(4, 124)["market"])

    def test_other_player_cannot_see_deck_reservation(self):
        state = splendor.new_game(2, 7)
        action = next(
            row["action"] for row in splendor.legal_actions(state, 0)
            if row["action"]["type"] == "reserve_deck"
        )
        state, _ = splendor.apply_action(state, 0, action)
        self.assertIn("id", splendor.observe(state, 0)["players"][0]["reserved"][0])
        self.assertEqual({"hidden": True}, splendor.observe(state, 1)["players"][0]["reserved"][0])

    def test_random_games_preserve_invariants(self):
        for seed in range(5):
            state = splendor.new_game(2 + seed % 3, seed)
            rng = random.Random(seed)
            for _ in range(250):
                if state["status"] == "finished":
                    break
                legal = splendor.legal_actions(state, state["active_seat"])
                self.assertTrue(legal)
                state, _ = splendor.apply_action(state, state["active_seat"], rng.choice(legal)["action"])
                splendor.validate_state(state)
            self.assertEqual("finished", state["status"])


if __name__ == "__main__":
    unittest.main()
