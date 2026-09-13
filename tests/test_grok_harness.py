from contextlib import redirect_stdout
from io import StringIO
import json
import fnmatch
import os
from pathlib import Path
import sys
import tempfile
import threading
import tomllib
import unittest
from unittest import mock

from agentbga.agents import AgentError, PlayerConfig
from agentbga.cli import main
from agentbga.grok_harness import discovered_plugins, subscription_status
from agentbga.harness import HarnessAgent
from agentbga.store import Store
from agentbga.usage import harness_usage_samples
from agentbga.web import MatchHub


LEGAL = [{"id": "a-test", "action": {"type": "pass"}}]
FIXTURE = Path(__file__).parent / "fixtures" / "grok_cli.py"
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "grok-subscription-vs-random.json"


class GrokHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "login"
        self.home.mkdir()
        (self.home / "auth.json").write_text('{"fixture": true}')
        self.environment = mock.patch.dict(os.environ, {"GROK_HOME": str(self.home)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        platform = mock.patch("agentbga.grok_harness.sys.platform", "darwin")
        platform.start()
        self.addCleanup(platform.stop)
        discovery = mock.patch("agentbga.grok_harness.discovered_plugins", return_value=["personal-plugin"])
        discovery.start()
        self.addCleanup(discovery.stop)

    def agent(self, seat=0, **overrides):
        config = PlayerConfig.from_dict({"name": "Grok", "backend": "grok",
                                        "auth_mode": "subscription", **overrides}, seat)
        with mock.patch("agentbga.harness.shutil.which", return_value=sys.executable):
            return HarnessAgent(config, "match", seat, runs_root=self.root / "runs")

    def test_config_defaults_and_rejected_credentials(self):
        config = self.agent().config
        self.assertEqual("subscription", config.auth_mode)
        self.assertEqual("grok-4.6", config.model)
        self.assertIsNone(config.reasoning_effort)
        self.assertIsNone(config.api_key_env)
        for field, value in (("base_url", "https://api.x.ai/v1"),
                             ("api_key_env", "XAI_API_KEY"), ("wire_api", "responses")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.agent(**{field: value})

    def test_legacy_api_configuration_remains_compatible(self):
        legacy = PlayerConfig.from_dict({"name": "Grok", "backend": "grok", "model": "grok-4.6"}, 0)
        explicit = PlayerConfig.from_dict({"name": "Grok", "backend": "grok", "model": "grok-4.6",
                                          "auth_mode": "api_key"}, 0)
        for config in (legacy, explicit):
            self.assertEqual("XAI_API_KEY", config.api_key_env)
            self.assertEqual("https://api.x.ai/v1", config.base_url)
            self.assertEqual("max", config.reasoning_effort)

    def test_explicit_session_resume_and_effort(self):
        agent = self.agent(reasoning_effort="high")
        first = agent._command("turn")
        self.assertNotIn("--resume", first)
        self.assertNotIn("--continue", first)
        self.assertEqual("high", first[first.index("--effort") + 1])
        self.assertNotIn("--effort", self.agent()._command("turn"))
        agent.session.session_id = "session-a"
        command = agent._command("next turn")
        self.assertEqual("session-a", command[command.index("--resume") + 1])
        self.assertEqual("MCPTool(agentbga__*)", command[command.index("--allow") + 1])

    def test_seat_config_and_login_isolation(self):
        agent = self.agent()
        agent._prepare_turn({"state_version": 1}, LEGAL)
        with mock.patch.dict(os.environ, {
            "XAI_API_KEY": "do-not-use", "GROK_MODELS_BASE_URL": "https://unwanted.invalid",
            "GROK_AGENT": "/unwanted/agent", "GROK_EXTERNAL_AUTH_COMMAND": "unwanted",
        }):
            env = agent._environment()
        local = Path(env["GROK_HOME"])
        self.assertNotEqual(self.home, local)
        self.assertEqual(str((self.home / "auth.json").resolve()), env["GROK_AUTH_PATH"])
        self.assertFalse((local / "auth.json").exists())
        self.assertEqual("1", env["GROK_DISABLE_API_KEY_AUTH"])
        self.assertNotIn("XAI_API_KEY", env)
        self.assertNotIn("GROK_MODELS_BASE_URL", env)
        self.assertNotIn("GROK_EXTERNAL_AUTH_COMMAND", env)
        self.assertEqual("0", env["GROK_CLAUDE_MCPS_ENABLED"])
        config = tomllib.loads((local / "config.toml").read_text())
        self.assertEqual(["agentbga"], list(config["mcp_servers"]))
        self.assertFalse(config["memory"]["enabled"])
        self.assertFalse(config["compat"]["cursor"]["hooks"])
        self.assertEqual(["personal-plugin"], config["plugins"]["disabled"])
        sandbox = tomllib.loads((local / "sandbox.toml").read_text())["profiles"]["agentbga"]
        self.assertEqual("strict", sandbox["extends"])
        self.assertIn(str(agent.session.runtime.resolve()), sandbox["read_write"])
        self.assertIn(str(self.home.resolve()), sandbox["read_only"])
        for name in ("config.toml", "sessions", "hooks", "auth.json.lock", "auth", "new-secret", "auth.json.extra"):
            self.assertTrue(any(fnmatch.fnmatchcase(str((self.home / name).resolve()), rule) for rule in sandbox["deny"]))
        self.assertFalse(any(fnmatch.fnmatchcase(env["GROK_AUTH_PATH"], rule) for rule in sandbox["deny"]))
        self.assertNotIn(str(self.home.resolve()), sandbox["read_write"])
        self.assertNotIn(env["GROK_AUTH_PATH"], sandbox["read_write"])
        self.assertEqual([agent.session.workspace.anchor], config["skills"]["ignore"])
        self.assertTrue((agent.session.workspace / ".git").is_dir())
        self.assertNotEqual(env["GROK_HOME"], self.agent(seat=1)._environment()["GROK_HOME"])

    def test_missing_login_fails_and_local_credentials_are_not_overwritten(self):
        agent = self.agent()
        (self.home / "auth.json").unlink()
        self.assertFalse(subscription_status(dict(os.environ))[0])
        with self.assertRaisesRegex(AgentError, "grok login"):
            agent._environment()
        (self.home / "auth.json").write_text("{}")
        local = agent.session.workspace / ".grok-home"
        local.mkdir(exist_ok=True)
        (local / "auth.json").write_text("do not overwrite")
        env = agent._environment()
        self.assertEqual(str((self.home / "auth.json").resolve()), env["GROK_AUTH_PATH"])
        self.assertEqual("do not overwrite", (local / "auth.json").read_text())

    def test_plugin_discovery_requires_valid_machine_readable_output(self):
        with mock.patch("agentbga.grok_harness.subprocess.run") as run:
            run.return_value.stdout = '{"plugins": [{"name": "personal-plugin"}]}'
            self.assertEqual(["personal-plugin"], discovered_plugins("grok", self.root, {}))
            self.assertEqual(["grok", "inspect", "--json"], run.call_args.args[0])
            run.return_value.stdout = "not json"
            with self.assertRaisesRegex(AgentError, "inspect Grok plugins safely"):
                discovered_plugins("grok", self.root, {})

    def test_usage_counts_only_aggregate_and_includes_cache(self):
        usage = {"input_tokens": 100, "cache_read_input_tokens": 40,
                 "cache_creation_input_tokens": 5, "output_tokens": 20, "reasoning_tokens": 8}
        self.assertEqual([], harness_usage_samples("grok", {"type": "usage", "usage": usage}))
        sample, = harness_usage_samples("grok", {"type": "end", "usage": usage})
        self.assertEqual((145, 40, 5, 20, 8), (sample.input_tokens, sample.cached_input_tokens,
                         sample.cache_write_input_tokens, sample.output_tokens, sample.reasoning_output_tokens))
        self.assertEqual([], harness_usage_samples("grok", {"type": "end"}))

    def test_series_resume_follows_participant_not_seat(self):
        first = self.agent(series_id="series", participant_id="alice")
        first.session.session_id = "alice-session"
        first._save_harness_session_state()
        moved = self.agent(seat=1, series_id="series", participant_id="alice")
        self.assertEqual("alice-session", moved.session.session_id)
        opponent = self.agent(series_id="series", participant_id="bob")
        self.assertIsNone(opponent.session.session_id)
        self.assertNotEqual(first.session.workspace, opponent.session.workspace)

    def test_web_rejects_api_key_in_subscription_mode(self):
        with self.assertRaisesRegex(ValueError, "cannot use api_key"):
            MatchHub(self.root / "rejected.sqlite3").create({"players": [
                {"name": "Grok", "backend": "grok", "auth_mode": "subscription", "api_key": "unused-test-key"},
                {"name": "Random", "backend": "random"},
            ]})

    def run_fixture(self, agent):
        command = agent._command
        with mock.patch.object(agent, "_command", side_effect=lambda p: [
            sys.executable, str(FIXTURE), *command(p)[1:],
        ]):
            return agent.choose({"game": "azul", "state_version": 1}, LEGAL)

    def test_offline_cli_mcp_submission_stream_and_persisted_resume(self):
        agent = self.agent()
        events = []
        agent.event_sink = events.append
        action, metadata = self.run_fixture(agent)
        self.assertEqual("a-test", action)
        self.assertFalse(metadata["session_resumed"])
        self.assertEqual(145, metadata["usage"]["input_tokens"])
        self.assertTrue(any(e.get("channel") == "reasoning" for e in events))
        self.assertTrue(any(e.get("delta") == "Decision completed." for e in events))
        self.assertTrue(any(e.get("tool") == "agentbga__submit_action" for e in events))
        restored = self.agent()
        self.assertEqual(agent.session.session_id, restored.session.session_id)
        _, metadata = self.run_fixture(restored)
        self.assertTrue(metadata["session_resumed"])
        self.assertEqual(1, metadata["session_resume_count"])
        self.assertIsNone(self.agent(seat=1).session.session_id)

    def test_errors_and_no_submission_are_not_success(self):
        for mode, message in (("error", "Subscription limit reached"),
                              ("no_submit", "without calling submit_action")):
            with self.subTest(mode=mode), mock.patch.dict(os.environ, {"AGENTBGA_GROK_FIXTURE_MODE": mode}):
                with self.assertRaisesRegex(AgentError, message):
                    self.run_fixture(self.agent())

    def test_web_accepts_subscription_without_key(self):
        captured = threading.Event()
        seen = []

        def fake_run(_store, _match, players, sink, turn_gate):
            seen.extend(players)
            captured.set()
            sink({"type": "match_failed", "error": "fixture stop"})

        with mock.patch("agentbga.web.run_match", side_effect=fake_run):
            hub = MatchHub(self.root / "web.sqlite3")
            created = hub.create({"players": [
                {"name": "Grok", "backend": "grok", "auth_mode": "subscription"},
                {"name": "Random", "backend": "random"},
            ]})
            self.assertTrue(captured.wait(2))
            for thread in threading.enumerate():
                if thread.name == f"agentbga-{created['match_id']}":
                    thread.join(timeout=5)
        self.assertEqual("subscription", seen[0].auth_mode)
        self.assertIsNone(seen[0].api_key)

    def test_persisted_subscription_resumes_without_ephemeral_api_key(self):
        db = self.root / "resume.sqlite3"
        configs = [self.agent().config,
                   PlayerConfig.from_dict({"name": "Random", "backend": "random"}, 1)]
        store = Store(db)
        try:
            match_id, _, _ = store.create(2, 7)
            store.set_players(match_id, [config.public_dict() for config in configs])
        finally:
            store.close()
        hub = MatchHub(db)
        for payload in (None, [config.public_dict() for config in configs]):
            restored = hub._resume_player_configs(match_id, payload)
            self.assertEqual("subscription", restored[0].auth_mode)
            self.assertIsNone(restored[0].api_key)

    def test_doctor_reports_local_login_without_claiming_entitlement(self):
        output = StringIO()
        with mock.patch("agentbga.cli.shutil.which", return_value=sys.executable), redirect_stdout(output):
            self.assertEqual(0, main(["doctor", "--players-config", str(EXAMPLE)]))
        row = json.loads(output.getvalue())["data"]["players"][0]
        self.assertIsNone(row["api_key_configured"])
        self.assertIn("checked by Grok at runtime", row["authentication_status"])
