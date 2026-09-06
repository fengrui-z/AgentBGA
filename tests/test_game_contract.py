import unittest

from agentbga.registry import GameRegistry, game_ids, get_game
from agentbga.game_profile import get_profile


class RegisteredGameContractTests(unittest.TestCase):
    def test_catan_profile_covers_supported_actions(self):
        game = get_game("catan")
        profile = get_profile("catan")
        self.assertEqual("Catan", profile.game_name)
        self.assertEqual("multi_step", profile.turn_structure)
        self.assertTrue(profile.has_spatial)
        self.assertFalse(set(game.describe()["action_types"]) - set(profile.action_meta_types))

    def test_registry_rejects_duplicates_and_metadata_mismatches(self):
        registry = GameRegistry()
        plugin = get_game("splendor")
        registry.register(plugin)
        self.assertEqual(("splendor",), registry.game_ids())
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(plugin)

        class WrongDescription:
            game_id = "wrong"
            rules_version = "v1"

            def describe(self):
                return {"id": "another", "rules_version": "v1"}

            def setup(self, players, seed, config=None): ...
            def observe(self, state, seat): ...
            def decision_seats(self, state): ...
            def legal_actions(self, state, seat): ...
            def apply_action(self, state, seat, action): ...
            def rankings(self, state): ...
            def validate_state(self, state): ...
            def state_hash(self, state): ...

        with self.assertRaisesRegex(ValueError, "description id"):
            registry.register(WrongDescription())

    def test_every_registered_game_is_deterministic_and_exposes_one_action_protocol(self):
        for game_id in game_ids():
            with self.subTest(game=game_id):
                plugin = get_game(game_id)
                players = plugin.describe()["players"]["minimum"]
                first = plugin.setup(players, 4242)
                second = plugin.setup(players, 4242)
                self.assertEqual(first, second)
                self.assertEqual(plugin.state_hash(first), plugin.state_hash(second))
                plugin.validate_state(first)

                seat = first["active_seat"]
                observation = plugin.observe(first, seat)
                legal = plugin.legal_actions(first, seat)
                self.assertEqual(game_id, observation["game"])
                self.assertTrue(legal)
                self.assertTrue(all(set(item) == {"id", "action"} for item in legal))
                self.assertEqual(len(legal), len({item["id"] for item in legal}))

                next_state, events = plugin.apply_action(first, seat, legal[0]["action"])
                self.assertNotEqual(plugin.state_hash(first), plugin.state_hash(next_state))
                self.assertEqual("action_accepted", events[0]["type"])
                plugin.validate_state(next_state)

    def test_only_current_decision_seats_receive_legal_actions(self):
        for game_id in game_ids():
            with self.subTest(game=game_id):
                plugin = get_game(game_id)
                state = plugin.setup(plugin.describe()["players"]["minimum"], 1)
                decision_seats = plugin.decision_seats(state)
                self.assertTrue(decision_seats)
                for seat in range(state["player_count"]):
                    if seat in decision_seats:
                        self.assertTrue(plugin.legal_actions(state, seat))
                    else:
                        self.assertEqual([], plugin.legal_actions(state, seat))


if __name__ == "__main__":
    unittest.main()
