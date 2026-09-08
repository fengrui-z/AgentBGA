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
            def decision_seats(self, state): ...
            def legal_actions(self, state, seat): ...
            def apply_action(self, state, seat, action): ...
            def rankings(self, state): ...
            def validate_state(self, state): ...
            def state_hash(self, state): ...

        with self.assertRaisesRegex(ValueError, "description id"):
            registry.register(WrongDescription())

    def test_registry_keeps_multiple_rules_versions_and_selects_exactly(self):
        original = get_game("splendor")

        class VersionAlias:
            game_id = original.game_id
            rules_version = "test-rules-v2"

            def describe(self):
                return {**original.describe(), "rules_version": self.rules_version}

            def setup(self, players, seed, config=None):
                return original.setup(players, seed, config)

            def observe(self, state, seat):
                return original.observe(state, seat)

            def decision_seats(self, state):
                return original.decision_seats(state)

            def legal_actions(self, state, seat):
                return original.legal_actions(state, seat)

            def apply_action(self, state, seat, action):
                return original.apply_action(state, seat, action)

            def rankings(self, state):
                return original.rankings(state)

            def validate_state(self, state):
                return original.validate_state(state)

            def state_hash(self, state):
                return original.state_hash(state)

        alias = VersionAlias()
        registry = GameRegistry((original, alias))
        self.assertEqual((original.rules_version, alias.rules_version), registry.rules_versions("splendor"))
        self.assertIs(alias, registry.get("splendor"))
        self.assertIs(original, registry.get("splendor", original.rules_version))
        self.assertEqual(
            [original.rules_version, alias.rules_version],
            registry.list_games()[0]["available_rules_versions"],
        )
        with self.assertRaisesRegex(ValueError, "unknown rules version"):
            registry.get("splendor", "missing")

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
