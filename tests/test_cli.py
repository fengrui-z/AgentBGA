from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from agentbga.cli import main


class CLITests(unittest.TestCase):
    def test_games_describe_and_create_ark_nova_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "match.sqlite3"
            output = StringIO()
            with redirect_stdout(output):
                code = main(["games", "describe", "ark_nova"])
            self.assertEqual(0, code)
            description = json.loads(output.getvalue())["data"]
            self.assertEqual("controlled_core", description["implementation_status"])
            self.assertTrue(description["runnable"])

            output = StringIO()
            with redirect_stdout(output):
                code = main([
                    "match", "create", "--game", "ark_nova", "--players", "2",
                    "--seed", "42", "--db", str(database),
                ])
            self.assertEqual(0, code)
            created = json.loads(output.getvalue())["data"]
            self.assertEqual("ark_nova", created["game"])

            output = StringIO()
            with redirect_stdout(output):
                code = main([
                    "match", "observe", created["match_id"], "--seat", "0",
                    "--db", str(database),
                ])
            self.assertEqual(0, code)
            observed = json.loads(output.getvalue())["data"]
            self.assertEqual("ark_nova", observed["game"])
            self.assertEqual(70, len(observed["legal_actions"]))

    def test_ark_nova_cli_accepts_game_config(self):
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            with redirect_stdout(output):
                code = main([
                    "match", "create", "--game", "ark_nova", "--players", "2",
                    "--seed", "5", "--game-config", '{"turn_limit":12}',
                    "--db", str(Path(directory) / "match.sqlite3"),
                ])
            self.assertEqual(0, code)
            self.assertEqual("ark_nova", json.loads(output.getvalue())["data"]["game"])
    def test_doctor_accepts_common_harnesses(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "players.json"
            config.write_text(json.dumps({
                "schema_version": "agentbga.players.v1",
                "players": [
                    {"name": "Claude", "backend": "claude", "model": "claude-test"},
                    {"name": "Codex", "backend": "codex", "model": "gpt-test"},
                    {"name": "OpenCode", "backend": "opencode", "model": "deepseek/test"},
                    {"name": "DeepSeek Harness", "backend": "dsh", "model": "deepseek-v4-flash"},
                ],
            }))
            output = StringIO()
            with mock.patch.dict(os.environ, {
                "ANTHROPIC_API_KEY": "present", "AGENTBGA_API_KEY": "present",
                "OPENAI_API_KEY": "present", "DEEPSEEK_API_KEY": "present",
            }, clear=True), mock.patch("agentbga.cli.shutil.which", return_value="/bin/harness"), redirect_stdout(output):
                code = main(["doctor", "--players-config", str(config)])
            self.assertEqual(0, code)
            result = json.loads(output.getvalue())
            self.assertEqual(
                ["claude", "codex", "opencode", "dsh"],
                [row["backend"] for row in result["data"]["players"]],
            )

    def test_doctor_checks_each_named_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "players.json"
            config.write_text(json.dumps({
                "schema_version": "agentbga.players.v1",
                "players": [
                    {"name": "A", "backend": "openai", "model": "a", "api_key_env": "A_KEY"},
                    {"name": "B", "backend": "anthropic", "model": "b", "api_key_env": "B_KEY"},
                ],
            }))
            output = StringIO()
            with mock.patch.dict(os.environ, {"A_KEY": "present"}, clear=True), redirect_stdout(output):
                code = main(["doctor", "--players-config", str(config)])
            self.assertEqual(1, code)
            result = json.loads(output.getvalue())
            self.assertFalse(result["ready_for_model"])
            self.assertEqual([True, False], [row["api_key_configured"] for row in result["data"]["players"]])

    def test_named_random_players_config_runs_and_status_preserves_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "players.json"
            database = root / "match.sqlite3"
            config.write_text(json.dumps({
                "schema_version": "agentbga.players.v1",
                "players": [
                    {"name": "Baseline One", "backend": "random"},
                    {"name": "Baseline Two", "backend": "random"},
                ],
            }))
            output = StringIO()
            with redirect_stdout(output):
                code = main([
                    "run", "--players-config", str(config), "--seed", "77", "--db", str(database),
                ])
            self.assertEqual(0, code)
            result = json.loads(output.getvalue())
            self.assertEqual(
                {"Baseline One", "Baseline Two"},
                {row["player"] for row in result["data"]["rankings"]},
            )
            output = StringIO()
            with redirect_stdout(output):
                code = main(["match", "status", result["data"]["match_id"], "--db", str(database)])
            self.assertEqual(0, code)
            status = json.loads(output.getvalue())
            self.assertEqual(
                ["Baseline One", "Baseline Two"],
                [row["name"] for row in status["data"]["players"]],
            )


if __name__ == "__main__":
    unittest.main()
