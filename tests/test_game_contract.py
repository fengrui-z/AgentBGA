import unittest

from agentbga.registry import GameRegistry, game_ids, get_game


class RegisteredGameContractTests(unittest.TestCase):
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
                first = plugin.setup(2, 4242)
                second = plugin.setup(2, 4242)
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

    def test_wrong_seat_never_receives_legal_actions(self):
        for game_id in game_ids():
            with self.subTest(game=game_id):
                plugin = get_game(game_id)
                state = plugin.setup(2, 1)
                self.assertEqual([], plugin.legal_actions(state, 1))


if __name__ == "__main__":
    unittest.main()
