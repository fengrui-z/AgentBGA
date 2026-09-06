import tempfile
import random
import unittest
from pathlib import Path

from agentbga import splendor
from agentbga.agents import PlayerConfig
from agentbga.runner import run_match
from agentbga.store import ConflictError, Store


class StoreTests(unittest.TestCase):
    def test_catan_actions_survive_reopen_and_exact_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "catan.sqlite3"
            store = Store(database)
            match_id, version, state = store.create(4, 42, "catan")
            game = store.game(match_id)
            rng = random.Random(71)
            rolls = 0
            for _ in range(100):
                seat = state["active_seat"]
                legal = game.legal_actions(state, seat)
                choice = rng.choice(legal)["action"]
                # Keep this persistence test focused on setup and dice-bearing turns.
                if state["phase"] == "main":
                    choice = next(item["action"] for item in legal if item["action"]["type"] == "end_turn")
                rolls += choice["type"] == "roll_dice"
                version, state, _ = store.act(match_id, seat, version, choice)
            self.assertGreater(rolls, 10)
            digest = game.state_hash(state)
            store.close()
            reopened = Store(database)
            try:
                self.assertEqual(state, reopened.load(match_id)[1])
                frames = reopened.replay(match_id)
                self.assertEqual(version, frames[-1]["version"])
                self.assertEqual(digest, frames[-1]["state_hash"])
            finally:
                reopened.close()

    def test_create_act_and_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            match_id, version, state = store.create(2, 1)
            action = splendor.legal_actions(state, 0)[0]["action"]
            version, _, events = store.act(match_id, 0, version, action)
            self.assertEqual(1, version)
            self.assertTrue(events)
            with self.assertRaises(ConflictError):
                store.act(match_id, 1, 0, action)
            replay = store.replay(match_id)
            self.assertEqual(1, replay[-1]["version"])
            tables = store.list_matches()
            self.assertEqual(1, len(tables))
            self.assertEqual(match_id, tables[0]["match_id"])
            self.assertEqual("splendor", tables[0]["game"])
            self.assertEqual(1, tables[0]["turn_count"])
            store.close()

    def test_create_and_load_ark_nova_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            match_id, version, state = store.create(3, 42, "ark_nova")
            self.assertEqual(0, version)
            self.assertEqual("ark_nova", store.game_id(match_id))
            self.assertEqual("initial_hand_selection", state["phase"])
            replay = store.replay(match_id)
            self.assertEqual(0, replay[-1]["version"])
            store.close()

    def test_create_act_and_replay_azul(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            match_id, version, state = store.create(2, 42, "azul")
            self.assertEqual("azul", store.game_id(match_id))
            action = store.game(match_id).legal_actions(state, 0)[0]["action"]
            version, state, events = store.act(match_id, 0, version, action)
            self.assertEqual(1, version)
            self.assertEqual("action_accepted", events[0]["type"])
            self.assertEqual(store.game(match_id).state_hash(state),
                             store.replay(match_id)[-1]["state_hash"])
            store.close()

    def test_ark_nova_random_controllers_finish_and_replay_controlled_core(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            match_id, _, _ = store.create(2, 12, "ark_nova", {"turn_limit": 12})
            players = [
                PlayerConfig.from_dict({"name": "A", "backend": "random"}, 0),
                PlayerConfig.from_dict({"name": "B", "backend": "random"}, 1),
            ]
            result = run_match(store, match_id, players, max_turns=20)
            self.assertEqual("ark_nova", result["game"])
            self.assertEqual([], result["harness_metrics"]["players"])
            self.assertTrue(result["harness_metrics"]["totals"]["complete"])
            self.assertGreater(result["decisions"], result["turns"])
            self.assertEqual("finished", store.load(match_id)[1]["status"])
            self.assertEqual(result["version"], store.replay(match_id)[-1]["version"])
            store.close()

    def test_ark_nova_public_runner_stream_redacts_initial_hand_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            match_id, _, _ = store.create(2, 3, "ark_nova", {"turn_limit": 4})
            players = [
                PlayerConfig.from_dict({"name": "A", "backend": "random"}, 0),
                PlayerConfig.from_dict({"name": "B", "backend": "random"}, 1),
            ]
            streamed = []
            run_match(store, match_id, players, max_turns=10, sink=streamed.append)
            first = next(event for event in streamed if event["type"] == "decision")
            self.assertEqual({"type": "choose_initial_hand", "kept_count": 4}, first["action"])
            self.assertNotIn("card_ids", str(first))
            store.close()

    def test_brass_birmingham_random_controllers_finish_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            match_id, _, _ = store.create(2, 21, "brass_birmingham")
            players = [
                PlayerConfig.from_dict({"name": "A", "backend": "random"}, 0),
                PlayerConfig.from_dict({"name": "B", "backend": "random"}, 1),
            ]
            result = run_match(store, match_id, players, max_turns=100)
            self.assertEqual("brass_birmingham", result["game"])
            self.assertGreater(result["decisions"], result["turns"])
            self.assertEqual("finished", store.load(match_id)[1]["status"])
            self.assertEqual(result["version"], store.replay(match_id)[-1]["version"])
            store.close()

    def test_public_events_redact_private_initial_hand_but_replay_remains_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            match_id, version, state = store.create(2, 9, "ark_nova", {"turn_limit": 4})
            choice = store.game(match_id).legal_actions(state, 0)[0]["action"]
            store.act(match_id, 0, version, choice)
            public = str(store.events(match_id))
            self.assertNotIn("card_ids", public)
            self.assertNotIn(choice["card_ids"][0], public)
            self.assertEqual(1, store.replay(match_id)[-1]["version"])
            store.close()


if __name__ == "__main__":
    unittest.main()
