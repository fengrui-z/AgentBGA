"""Upgrade checks against action/hash evidence captured from the PR base."""

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from agentbga.agents import PlayerConfig
from agentbga.registry import get_game
from agentbga.runner import run_match
from agentbga.store import Store
from agentbga.web import MatchHub


class ArkNovaLegacyV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).parent / "fixtures/ark_nova/controlled-core-v2-replay.json"
        cls.evidence = json.loads(fixture.read_text(encoding="utf-8"))

    def create_old_database(self, database: Path) -> str:
        evidence = self.evidence
        game = get_game("ark_nova", evidence["rules_version"])
        state = game.setup(evidence["players"], evidence["seed"], evidence["config"])
        self.assertEqual(evidence["initial_state_hash"], game.state_hash(state))
        match_id = "legacy-v2-upgrade"
        # This is the pre-PR schema and creation event, without content identity.
        connection = sqlite3.connect(database)
        self.addCleanup(connection.close)
        connection.executescript("""
            CREATE TABLE matches (
                id TEXT PRIMARY KEY, game_id TEXT NOT NULL, rules_version TEXT NOT NULL,
                version INTEGER NOT NULL, seed INTEGER NOT NULL, state_json TEXT NOT NULL,
                state_hash TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE events (
                match_id TEXT NOT NULL, seq INTEGER NOT NULL, version INTEGER NOT NULL,
                seat INTEGER, event_json TEXT NOT NULL, state_hash TEXT NOT NULL,
                created_at REAL NOT NULL, PRIMARY KEY(match_id, seq)
            );
        """)
        created = {
            "type": "match_created", "game": "ark_nova", "players": evidence["players"],
            "seed": evidence["seed"], "config": evidence["config"],
        }
        connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (match_id, 0, 0, None, json.dumps(created), evidence["initial_state_hash"], 0),
        )
        seq = 1
        for version, decision in enumerate(evidence["decisions"][:-1], start=1):
            state, events = game.apply_action(state, decision["seat"], decision["action"])
            self.assertEqual(decision["state_hash"], game.state_hash(state))
            for event in events:
                connection.execute(
                    "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (match_id, seq, version, decision["seat"], json.dumps(event),
                     decision["state_hash"], 0),
                )
                seq += 1
        connection.execute(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (match_id, "ark_nova", evidence["rules_version"], version, evidence["seed"],
             json.dumps(state), game.state_hash(state), 0, 0),
        )
        connection.commit()
        connection.close()
        return match_id

    def test_upgrade_preserves_historical_hashes_views_and_next_action(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "old.sqlite3"
            match_id = self.create_old_database(database)
            store = Store(database)
            self.addCleanup(store.close)
            self.assertEqual((None, None), store.content_identity(match_id))
            self.assertEqual(self.evidence["rules_version"], store.game(match_id).rules_version)
            self.assertEqual(
                [self.evidence["initial_state_hash"]]
                + [row["state_hash"] for row in self.evidence["decisions"][:-1]],
                [row["state_hash"] for row in store.replay(match_id)],
            )
            snapshot = MatchHub(database)._snapshot(match_id)
            self.assertEqual(self.evidence["rules_version"], snapshot["rules_version"])
            self.assertEqual("map-a", snapshot["views"][0]["players"][0]["map"]["id"])
            version, _, _ = store.load(match_id)
            next_decision = self.evidence["decisions"][-1]
            _, state, _ = store.act(
                match_id, next_decision["seat"], version, next_decision["action"],
            )
            self.assertEqual(next_decision["state_hash"], store.game(match_id).state_hash(state))
            self.assertEqual(next_decision["state_hash"], store.replay(match_id)[-1]["state_hash"])
            store.close()

    def test_old_match_can_finish_without_changing_the_new_match_default(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "old.sqlite3"
            match_id = self.create_old_database(database)
            store = Store(database)
            self.addCleanup(store.close)
            players = [
                PlayerConfig.from_dict({"name": f"Seat {seat}", "backend": "random"}, seat)
                for seat in range(2)
            ]
            result = run_match(store, match_id, players, max_turns=20)
            self.assertEqual(self.evidence["rules_version"], result["rules_version"])
            self.assertEqual("finished", store.load(match_id)[1]["status"])
            self.assertEqual(result["version"], store.replay(match_id)[-1]["version"])
            self.assertEqual("base-1.2-faq-v2-map0.1", get_game("ark_nova").rules_version)
            self.assertEqual(
                "base-1.2-controlled-core.6",
                get_game("ark_nova", "base-1.2-controlled-core.6").rules_version,
            )
            store.close()
