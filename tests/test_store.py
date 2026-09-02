import tempfile
import unittest
from pathlib import Path
import sqlite3

from agentbga import splendor
from agentbga.agents import PlayerConfig
from agentbga.public_projection import (
    public_action_id,
    public_controller_event,
    public_game_event,
)
from agentbga.runner import run_match
from agentbga.store import ConflictError, Store


class StoreTests(unittest.TestCase):
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
            self.assertEqual(state["rules_version"], store.rules_version(match_id))
            self.assertEqual(("ark_nova", state["rules_version"]), store.match_identity(match_id))
            self.assertEqual(
                (state["content_pack_id"], state["content_hash"]),
                store.content_identity(match_id),
            )
            self.assertEqual("initial_hand_selection", state["phase"])
            replay = store.replay(match_id)
            self.assertEqual(0, replay[-1]["version"])
            store.close()

    def test_old_match_table_is_migrated_for_content_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite3"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE matches ("
                "id TEXT PRIMARY KEY, game_id TEXT NOT NULL, rules_version TEXT NOT NULL, "
                "version INTEGER NOT NULL, seed INTEGER NOT NULL, state_json TEXT NOT NULL, "
                "state_hash TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)"
            )
            connection.commit()
            connection.close()

            store = Store(database)
            columns = {
                row["name"] for row in store.connection.execute("PRAGMA table_info(matches)")
            }
            self.assertIn("content_pack_id", columns)
            self.assertIn("content_hash", columns)
            store.close()

    def test_create_rejects_unknown_exact_rules_version(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            with self.assertRaisesRegex(ValueError, "unknown rules version"):
                store.create(2, 1, "ark_nova", rules_version="does-not-exist")
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
            match_id, _, _ = store.create(
                2, 12, "ark_nova", {"turn_limit": 12},
                rules_version="base-1.2-controlled-core.6",
            )
            players = [
                PlayerConfig.from_dict({"name": "A", "backend": "random"}, 0),
                PlayerConfig.from_dict({"name": "B", "backend": "random"}, 1),
            ]
            result = run_match(store, match_id, players, max_turns=20)
            self.assertEqual("ark_nova", result["game"])
            self.assertEqual(
                "agentbga.ark-nova.match-report.v6",
                result["match_report"]["schema_version"],
            )
            report_metrics = result["match_report"]["players"][0]["metrics"]
            self.assertIn("final_track_score", report_metrics)
            self.assertIn("score", report_metrics)
            self.assertEqual(result["match_report"], store.match_report(match_id))
            self.assertEqual([], result["harness_metrics"]["players"])
            self.assertTrue(result["harness_metrics"]["totals"]["complete"])
            self.assertGreater(result["decisions"], result["turns"])
            self.assertEqual("finished", store.load(match_id)[1]["status"])
            self.assertEqual(result["version"], store.replay(match_id)[-1]["version"])
            store.close()

    def test_ark_nova_public_runner_stream_redacts_initial_hand_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            match_id, _, _ = store.create(
                2, 3, "ark_nova", {"turn_limit": 4},
                rules_version="base-1.2-controlled-core.6",
            )
            players = [
                PlayerConfig.from_dict({"name": "A", "backend": "random"}, 0),
                PlayerConfig.from_dict({"name": "B", "backend": "random"}, 1),
            ]
            streamed = []
            run_match(store, match_id, players, max_turns=10, sink=streamed.append)
            first = next(event for event in streamed if event["type"] == "decision")
            kept_ids = store.replay(match_id)[1]["action"]["card_ids"]
            self.assertEqual({"type": "choose_initial_hand", "kept_count": 4}, first["action"])
            self.assertNotIn("card_ids", str(first))
            self.assertTrue(all(card_id not in first["action_id"] for card_id in kept_ids))
            self.assertTrue(first["action_id"].startswith("private-action-"))
            store.close()

    def test_public_projection_redacts_semantic_and_final_scoring_choices(self):
        final_card_id = "final-007"
        action = {
            "type": "resolve_semantic_choice",
            "choice_id": "semantic-choice-9",
            "option_ids": [final_card_id],
        }
        projected_id = public_action_id(
            f"semantic-choice-9:{final_card_id}", action,
            match_id="match-1", version=8, seat=1,
        )
        accepted = public_game_event({
            "type": "action_accepted", "seat": 1, "action": action,
        })
        resolved = public_game_event({
            "type": "semantic_choice_resolved", "seat": 1,
            "choice_id": "semantic-choice-9", "option_ids": [final_card_id],
        })
        discarded = public_game_event({
            "type": "final_scoring_card_discarded", "seat": 1,
            "card_id": final_card_id,
        })

        self.assertTrue(projected_id.startswith("private-action-"))
        self.assertNotIn(final_card_id, str((projected_id, accepted, resolved, discarded)))
        self.assertEqual(1, accepted["action"]["selected_count"])
        self.assertEqual(1, resolved["selected_count"])
        self.assertEqual(1, discarded["discarded_count"])

    def test_public_controller_events_redact_private_action_references(self):
        private_id = "semantic-choice-4:final-007"
        projected = public_controller_event({
            "type": "harness_tool_result", "tool": "submit_action",
            "result": {"accepted": True, "action_id": private_id},
        }, match_id="match-1", version=3, seat=0)
        self.assertNotIn(private_id, str(projected))
        self.assertTrue(projected["result"]["action_id"].startswith("private-action-"))

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
