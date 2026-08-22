import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples" / "three_game_tournament.py"
CONFIG = ROOT / "examples" / "three-game-test-local-providers.json"
SPEC = importlib.util.spec_from_file_location("agentbga_three_game_tournament", SCRIPT)
assert SPEC and SPEC.loader
TOURNAMENT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TOURNAMENT
SPEC.loader.exec_module(TOURNAMENT)


class ThreeGameTournamentTests(unittest.TestCase):
    def test_local_provider_pilot_is_balanced_and_uses_expected_endpoints(self):
        config = TOURNAMENT.load_config(CONFIG)
        schedule = TOURNAMENT.build_schedule(config)

        self.assertEqual(12, len(config["participants"]))
        self.assertEqual(66, len(schedule))
        appearances = {row["id"]: 0 for row in config["participants"]}
        for match in schedule:
            for participant_id in match["participants"]:
                appearances[participant_id] += 1
        self.assertEqual({16}, set(appearances.values()))

        players = [row["player"] for row in config["participants"]]
        endpoints = {row["base_url"] for row in players}
        self.assertEqual({
            "https://dashscope.aliyuncs.com/compatible-mode/apps/anthropic",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "https://token-plan-cn.xiaomimimo.com/anthropic",
            "https://token-plan-cn.xiaomimimo.com/v1",
        }, endpoints)
        self.assertIn("glm-5.2", {row["model"] for row in players})
        self.assertNotIn("glm-5.3", {row["model"] for row in players})
        self.assertNotIn("codex", {row["backend"] for row in players})
        for player in players:
            endpoint = player["base_url"]
            if player["backend"] == "claude":
                self.assertTrue(endpoint.endswith(("/anthropic", "/apps/anthropic")))
            else:
                self.assertTrue(endpoint.endswith("/v1"))

    def test_runtime_report_records_presence_but_never_secret_values(self):
        config = TOURNAMENT.load_config(CONFIG)
        completed = mock.Mock(stdout="test-version\n", stderr="")
        secrets = {
            "DASHSCOPE_API_KEY": "dashscope-secret-value",
            "MIMO_API_KEY": "mimo-secret-value",
        }
        with mock.patch.dict(os.environ, secrets, clear=False), \
             mock.patch.object(TOURNAMENT.shutil, "which", return_value="/bin/test"), \
             mock.patch.object(TOURNAMENT.subprocess, "run", return_value=completed):
            report = TOURNAMENT.runtime_report(config)
            TOURNAMENT.validate_runtime(report)

        serialized = json.dumps(report)
        self.assertNotIn(secrets["DASHSCOPE_API_KEY"], serialized)
        self.assertNotIn(secrets["MIMO_API_KEY"], serialized)
        self.assertTrue(report["credentials"]["DASHSCOPE_API_KEY"]["configured"])
        self.assertTrue(report["credentials"]["MIMO_API_KEY"]["configured"])


if __name__ == "__main__":
    unittest.main()
