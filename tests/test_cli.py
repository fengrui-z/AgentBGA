from contextlib import chdir, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from agentbga.cli import main


class CLITests(unittest.TestCase):
    def test_seven_wonders_cli_accepts_seven_players(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "match.sqlite3"
            output = StringIO()
            with redirect_stdout(output):
                code = main([
                    "match", "create", "--game", "seven_wonders", "--players", "7",
                    "--seed", "17", "--db", str(database),
                ])
            self.assertEqual(0, code)
            created = json.loads(output.getvalue())["data"]
            self.assertEqual("seven_wonders", created["game"])
            self.assertEqual(7, created["players"])

    def test_match_traces_reads_runtime_trace_layout(self):
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            database = Path(directory) / "match.sqlite3"
            created_output = StringIO()
            with redirect_stdout(created_output):
                self.assertEqual(0, main([
                    "match", "create", "--players", "2", "--seed", "9",
                    "--db", str(database),
                ]))
            match_id = json.loads(created_output.getvalue())["data"]["match_id"]
            trace_dir = Path(directory) / ".agentbga" / "runs" / "_traces" / match_id / "seat-0"
            trace_dir.mkdir(parents=True)
            (trace_dir / "turn-0000.json").write_text(json.dumps({
                "version": 0, "status": "ok", "backend": "codex",
                "action_latency_ms": 10, "process_latency_ms": 20,
                "submission": {"action_id": "a-test"},
            }))

            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main([
                    "match", "traces", match_id, "--db", str(database),
                ]))
            rows = json.loads(output.getvalue())["data"]
            self.assertEqual(1, len(rows))
            self.assertEqual("a-test", rows[0]["action_id"])
            self.assertFalse(Path(rows[0]["file"]).is_absolute())

    def test_games_describe_and_create_ark_nova_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "match.sqlite3"
            output = StringIO()
            with redirect_stdout(output):
                code = main(["games", "describe", "ark_nova"])
            self.assertEqual(0, code)
            description = json.loads(output.getvalue())["data"]
            self.assertEqual("released", description["implementation_status"])
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

    def test_cli_can_select_an_exact_rules_version(self):
        with tempfile.TemporaryDirectory() as directory:
            describe_output = StringIO()
            with redirect_stdout(describe_output):
                self.assertEqual(0, main([
                    "games", "describe", "ark_nova", "--rules-version",
                    "base-1.2-controlled-core.6",
                ]))
            description = json.loads(describe_output.getvalue())["data"]
            self.assertEqual("base-1.2-controlled-core.6", description["rules_version"])

            create_output = StringIO()
            with redirect_stdout(create_output):
                self.assertEqual(0, main([
                    "match", "create", "--game", "ark_nova", "--players", "2",
                    "--seed", "42", "--rules-version", "base-1.2-controlled-core.6",
                    "--db", str(Path(directory) / "match.sqlite3"),
                ]))
            created = json.loads(create_output.getvalue())["data"]
            self.assertEqual("base-1.2-controlled-core.6", created["rules_version"])

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

    def test_ark_nova_cli_can_select_map_a(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "match.sqlite3"
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main([
                    "match", "create", "--game", "ark_nova", "--players", "2",
                    "--seed", "7", "--map", "map-a", "--db", str(database),
                ]))
            match_id = json.loads(output.getvalue())["data"]["match_id"]
            observed_output = StringIO()
            with redirect_stdout(observed_output):
                self.assertEqual(0, main([
                    "match", "observe", match_id, "--seat", "0",
                    "--db", str(database),
                ]))
            observed = json.loads(observed_output.getvalue())["data"]
            self.assertEqual("map-a", observed["players"][0]["map"]["id"])
            self.assertEqual(2, len(observed["players"][0]["map"]["buildings"]))

    def test_games_describe_and_create_azul(self):
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            with redirect_stdout(output):
                code = main(["games", "describe", "azul"])
            self.assertEqual(0, code)
            description = json.loads(output.getvalue())["data"]
            self.assertEqual("playable_beta", description["implementation_status"])
            self.assertEqual({"minimum": 2, "maximum": 4}, description["players"])

            database = Path(directory) / "match.sqlite3"
            output = StringIO()
            with redirect_stdout(output):
                code = main([
                    "match", "create", "--game", "azul", "--players", "2",
                    "--seed", "42", "--db", str(database),
                ])
            self.assertEqual(0, code)
            self.assertEqual("azul", json.loads(output.getvalue())["data"]["game"])

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

    def test_doctor_accepts_logged_in_codex_subscription_without_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "players.json"
            config.write_text(json.dumps({
                "schema_version": "agentbga.players.v1",
                "players": [
                    {"name": "Codex", "backend": "codex", "model": "gpt-test",
                     "auth_mode": "subscription"},
                    {"name": "Baseline", "backend": "random"},
                ],
            }))
            output = StringIO()
            login_status = mock.Mock(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch("agentbga.cli.shutil.which", return_value="/bin/codex"), \
                    mock.patch("agentbga.cli.subprocess.run", return_value=login_status) as run, \
                    redirect_stdout(output):
                code = main(["doctor", "--players-config", str(config)])
            self.assertEqual(0, code)
            result = json.loads(output.getvalue())
            codex = result["data"]["players"][0]
            self.assertTrue(codex["authentication_configured"])
            self.assertIsNone(codex["api_key_configured"])
            self.assertEqual("Logged in using ChatGPT", codex["authentication_status"])
            run.assert_called_once()
            command, = run.call_args.args
            self.assertEqual(["/bin/codex", "login", "status"], command)
            call_options = run.call_args.kwargs
            self.assertTrue(call_options["capture_output"])
            self.assertTrue(call_options["text"])
            self.assertEqual(10, call_options["timeout"])
            self.assertFalse(call_options["check"])
            self.assertNotIn("OPENAI_API_KEY", call_options["env"])
            self.assertNotEqual(os.environ.get("CODEX_HOME"), call_options["env"]["CODEX_HOME"])

    def test_doctor_rejects_api_key_login_for_codex_subscription(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "players.json"
            config.write_text(json.dumps({
                "schema_version": "agentbga.players.v1",
                "players": [
                    {"name": "Codex", "backend": "codex", "model": "gpt-test",
                     "auth_mode": "subscription"},
                    {"name": "Baseline", "backend": "random"},
                ],
            }))
            output = StringIO()
            api_login = mock.Mock(returncode=0, stdout="Logged in using an API key\n", stderr="")
            with mock.patch("agentbga.cli.shutil.which", return_value="/bin/codex"), \
                    mock.patch("agentbga.cli.subprocess.run", return_value=api_login), \
                    redirect_stdout(output):
                code = main(["doctor", "--players-config", str(config)])
            self.assertEqual(1, code)
            result = json.loads(output.getvalue())
            self.assertFalse(result["ready_for_model"])
            self.assertFalse(result["data"]["players"][0]["authentication_configured"])

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
