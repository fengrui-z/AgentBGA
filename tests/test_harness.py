import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from agentbga.agents import AgentError, PlayerConfig
from agentbga.harness import HarnessAgent
from agentbga.seat_mcp import TOOLS
from agentbga.seat_tool import call_tool


LEGAL = [{"id": "a-test", "action": {"type": "take_tokens", "take": {"blue": 2}, "return": {}}}]


class HarnessTests(unittest.TestCase):
    def test_player_config_accepts_harness_backends(self):
        codex = PlayerConfig.from_dict({
            "name": "Codex + GPT", "backend": "codex", "model": "gpt-test",
        }, 0)
        opencode = PlayerConfig.from_dict({
            "name": "OpenCode + DeepSeek", "backend": "opencode",
            "model": "deepseek/deepseek-chat", "base_url": "https://api.deepseek.com",
        }, 1)
        self.assertEqual("OPENAI_API_KEY", codex.api_key_env)
        self.assertEqual("DEEPSEEK_API_KEY", opencode.api_key_env)
        claude = PlayerConfig.from_dict({
            "name": "Claude Code", "backend": "claude", "model": "claude-test",
        }, 2)
        pi = PlayerConfig.from_dict({
            "name": "Pi", "backend": "pi", "model": "model-test",
        }, 3)
        self.assertEqual("ANTHROPIC_API_KEY", claude.api_key_env)
        self.assertEqual("AGENTBGA_API_KEY", pi.api_key_env)
        self.assertEqual("max", codex.reasoning_effort)
        self.assertEqual("max", opencode.reasoning_effort)
        dsh = PlayerConfig.from_dict({
            "name": "DeepSeek Harness", "backend": "dsh", "model": "deepseek-v4-flash",
        }, 4)
        self.assertEqual("DEEPSEEK_API_KEY", dsh.api_key_env)
        self.assertEqual("https://api.deepseek.com", dsh.base_url)
        self.assertEqual("max", dsh.reasoning_effort)

    def test_seat_tool_is_scoped_and_submit_is_single_use(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "turn-context.json"
            path.write_text(json.dumps({
                "schema_version": "agentbga.seat-context.v1", "match_id": "m", "seat": 0,
                "version": 7, "observation": {"viewer_seat": 0},
                "legal_actions": [{"id": "a-good", "type": "pass"}],
            }))
            self.assertEqual(0, call_tool(path, "observe")["viewer_seat"])
            with self.assertRaisesRegex(ValueError, "unknown or stale"):
                call_tool(path, "submit_action", {"action_id": "a-bad"})
            accepted = call_tool(path, "submit_action", {"action_id": "a-good"})
            self.assertTrue(accepted["accepted"])
            with self.assertRaisesRegex(ValueError, "already been submitted"):
                call_tool(path, "submit_action", {"action_id": "a-good"})

    def test_mcp_exposes_only_seat_tools(self):
        self.assertEqual({"observe", "legal_actions", "submit_action"}, {tool["name"] for tool in TOOLS})

    def test_mcp_stdio_initialize_and_tool_list(self):
        with tempfile.TemporaryDirectory() as directory:
            context = Path(directory) / "turn-context.json"
            context.write_text(json.dumps({
                "schema_version": "agentbga.seat-context.v1", "match_id": "m", "seat": 0,
                "version": 1, "observation": {}, "legal_actions": [],
            }))
            requests = "\n".join([
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            ]) + "\n"
            completed = subprocess.run(
                [sys.executable, "-m", "agentbga.seat_mcp", "--context", str(context)],
                input=requests, text=True, capture_output=True, check=True,
            )
            responses = [json.loads(line) for line in completed.stdout.splitlines()]
            self.assertEqual("agentbga-seat", responses[0]["result"]["serverInfo"]["name"])
            self.assertEqual(3, len(responses[1]["result"]["tools"]))

    def test_harness_commands_resume_sessions(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", side_effect=lambda name: f"/bin/{name}"):
            codex_config = PlayerConfig.from_dict({
                "name": "Codex", "backend": "codex", "model": "gpt-test",
            }, 0)
            codex = HarnessAgent(codex_config, "match", 0, runs_root=directory)
            first_command = codex._command("turn")
            self.assertIn("workspace-write", first_command)
            self.assertNotIn("--ask-for-approval", first_command)
            codex.session.session_id = "thread-1"
            self.assertEqual("resume", codex._command("turn")[2])

            opencode_config = PlayerConfig.from_dict({
                "name": "OpenCode", "backend": "opencode", "model": "deepseek/test",
                "base_url": "https://api.deepseek.com",
            }, 1)
            opencode = HarnessAgent(opencode_config, "match", 1, runs_root=directory)
            opencode.session.session_id = "session-1"
            command = opencode._command("turn")
            self.assertIn("--pure", command)
            self.assertEqual("max", command[command.index("--variant") + 1])
            self.assertIn("--thinking", command)
            self.assertEqual("session-1", command[command.index("--session") + 1])

            claude_config = PlayerConfig.from_dict({
                "name": "Claude", "backend": "claude", "model": "claude-test",
            }, 2)
            claude = HarnessAgent(claude_config, "match", 2, runs_root=directory)
            claude.session.session_id = "claude-session"
            command = claude._command("turn")
            self.assertIn("--strict-mcp-config", command)
            self.assertEqual(claude.session.session_id, command[command.index("--resume") + 1])
            self.assertIn("mcp__agentbga__observe", command)
            self.assertIn("mcp__agentbga__legal_actions", command)
            self.assertIn("mcp__agentbga__submit_action", command)
            self.assertEqual("max", command[command.index("--effort") + 1])
            self.assertEqual(["--", "turn"], command[-2:])

            pi_config = PlayerConfig.from_dict({
                "name": "Pi", "backend": "pi", "model": "test-model",
            }, 3)
            pi = HarnessAgent(pi_config, "match", 3, runs_root=directory)
            pi.session.session_id = "session-3"
            command = pi._command("turn")
            self.assertIn("--no-builtin-tools", command)
            self.assertEqual("xhigh", command[command.index("--thinking") + 1])
            self.assertEqual("session-3", command[command.index("--session") + 1])

            dsh_config = PlayerConfig.from_dict({
                "name": "DeepSeek Harness", "backend": "dsh", "model": "deepseek-v4-flash",
            }, 4)
            dsh = HarnessAgent(dsh_config, "match", 4, runs_root=directory)
            dsh._prepare_turn({"state_version": 1}, LEGAL)
            command = dsh._command("turn")
            self.assertIn("--profile", command)
            self.assertEqual("headless", command[command.index("--profile") + 1])
            self.assertIn("--patch", command)
            self.assertTrue((dsh.session.workspace / "dsh-patch.yml").is_file())
            self.assertEqual("turn", command[-1])

    def test_claude_and_pi_generate_seat_tool_configuration(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", side_effect=lambda name: f"/bin/{name}"):
            for seat, backend, model in ((0, "claude", "claude-test"), (1, "pi", "model-test")):
                config = PlayerConfig.from_dict({
                    "name": backend, "backend": backend, "model": model,
                    "base_url": "https://proxy.example/v1",
                }, seat)
                agent = HarnessAgent(config, "match", seat, runs_root=directory)
                agent._prepare_turn({"state_version": 1}, LEGAL)
                if backend == "claude":
                    mcp = json.loads((agent.session.workspace / "claude-mcp.json").read_text())
                    self.assertIn("agentbga", mcp["mcpServers"])
                    self.assertEqual("https://proxy.example/v1", agent._environment()["ANTHROPIC_BASE_URL"])
                else:
                    models = json.loads((agent.session.workspace / ".pi-home" / "models.json").read_text())
                    self.assertEqual("https://proxy.example/v1", models["providers"]["agentbga"]["baseUrl"])
                    self.assertEqual("$OPENAI_API_KEY", models["providers"]["agentbga"]["apiKey"])
                    self.assertTrue(models["providers"]["agentbga"]["models"][0]["reasoning"])
                    self.assertEqual("max", models["providers"]["agentbga"]["models"][0]["thinkingLevelMap"]["xhigh"])
                    extension = (agent.session.workspace / "agentbga-tools.ts").read_text()
                    self.assertIn('name: "submit_action"', extension)

            opencode = HarnessAgent(PlayerConfig.from_dict({
                "name": "OpenCode", "backend": "opencode", "model": "custom-model",
                "base_url": "https://proxy.example/v1", "api_key_env": "CUSTOM_KEY",
            }, 0), "match-two", 0, runs_root=directory)
            opencode._prepare_turn({"state_version": 1}, LEGAL)
            configured = json.loads((opencode.session.workspace / "opencode.json").read_text())
            self.assertEqual("@ai-sdk/openai-compatible", configured["provider"]["agentbga"]["npm"])
            self.assertEqual("{env:CUSTOM_KEY}", configured["provider"]["agentbga"]["options"]["apiKey"])
            # Non-DeepSeek endpoints get an empty variant (no reasoning_effort/thinking).
            self.assertEqual({}, configured["provider"]["agentbga"]["models"]["custom-model"]["variants"]["max"])
            self.assertIn("agentbga/custom-model", opencode._command("turn"))

            dsh = HarnessAgent(PlayerConfig.from_dict({
                "name": "DeepSeek Harness", "backend": "dsh", "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY",
            }, 0), "match-dsh", 0, runs_root=directory)
            dsh._prepare_turn({"state_version": 1}, LEGAL)
            patch = (dsh.session.workspace / "dsh-patch.yml").read_text()
            self.assertIn("deepseek-official", patch)
            self.assertIn("deepseek-v4-flash", patch)
            self.assertIn("reasoningEffort: max", patch)
            self.assertIn("defaultPreset: workspace-write", patch)
            self.assertIn("approval: never", patch)
            self.assertIn("@deepseek-ai/dsh-mcp-client", patch)
            self.assertIn("serverName: agentbga", patch)
            env = dsh._environment()
            self.assertEqual("https://api.deepseek.com", env["DEEPSEEK_BASE_URL"])
            self.assertEqual("workspace-write", env["DSH_PERMISSION_MODE"])
            self.assertEqual("DISABLED", env["DSH_TELEMETRY_MODE"])
            self.assertIn("seat-0-dsh", env["DSH_HOME"])

    def test_pi_json_events_stream_text_reasoning_and_session(self):
        self.assertEqual("hello", HarnessAgent._event_text({
            "type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "hello"},
        }))
        self.assertEqual("thinking", HarnessAgent._event_text({
            "type": "message_update", "assistantMessageEvent": {"type": "thinking_delta", "delta": "thinking"},
        }))
        self.assertEqual("claude", HarnessAgent._event_text({
            "type": "stream_event", "event": {"delta": {"text": "claude"}},
        }))
        self.assertEqual("pi-session", HarnessAgent._event_session_id({"type": "session", "id": "pi-session"}))

    def test_harness_requires_submit_tool_and_records_tool_events(self):
        events = []
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", return_value="/bin/fake"):
            config = PlayerConfig.from_dict({
                "name": "Codex", "backend": "codex", "model": "gpt-test",
            }, 0)
            agent = HarnessAgent(config, "match", 0, runs_root=directory, event_sink=events.append)

            def fake_run(_command):
                context = agent.session.runtime / "turn-context.json"
                call_tool(context, "observe")
                call_tool(context, "legal_actions")
                call_tool(context, "submit_action", {"action_id": "a-test"})
                agent.session.session_id = "persistent-session"
                return "", "", 0

            with mock.patch.object(agent, "_run", side_effect=fake_run):
                action_id, metadata = agent.choose({"turn_count": 0, "state_version": 0}, LEGAL)
            self.assertEqual("a-test", action_id)
            self.assertEqual("persistent-session", metadata["session_id"])
            self.assertEqual("max", metadata["reasoning_effort"])
            self.assertEqual(3, len([event for event in events if event["type"] == "harness_tool_call"]))
            self.assertTrue((agent.session.workspace / ".codex" / "config.toml").is_file())
            self.assertIn('model_reasoning_effort = "max"', (agent.session.workspace / ".codex" / "config.toml").read_text())
            self.assertIn('model_reasoning_effort="max"', agent._codex_config_args)
            opencode_config = json.loads((agent.session.workspace / "opencode.json").read_text())
            self.assertEqual("deny", opencode_config["permission"]["*"])
            self.assertEqual("allow", opencode_config["permission"]["agentbga_*"])
            self.assertNotEqual(agent.session.workspace.parent, agent.session.runtime.parent)
            codex_command = agent._command("next turn")
            self.assertIn(str(agent.session.runtime / "turn-context.json"), " ".join(codex_command))

            (agent.session.runtime / "submission.json").unlink(missing_ok=True)
            with mock.patch.object(agent, "_run", return_value=("{}", "", 0)):
                with self.assertRaisesRegex(AgentError, "without calling submit_action"):
                    agent.choose({"turn_count": 1, "state_version": 1}, LEGAL)

    def test_harness_environment_does_not_inherit_unrelated_secrets(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", return_value="/bin/codex"):
            config = PlayerConfig.from_dict({
                "name": "Codex", "backend": "codex", "model": "gpt-test",
                "api_key_env": "SEAT_KEY",
            }, 0)
            config = PlayerConfig(**{**config.__dict__, "api_key": "seat-secret"})
            with mock.patch.dict(os.environ, {"SEAT_KEY": "old", "OTHER_TOKEN": "hidden", "PATH": "/bin"}, clear=True):
                environment = HarnessAgent(config, "match", 0, runs_root=directory)._environment()
            self.assertEqual("seat-secret", environment["OPENAI_API_KEY"])
            self.assertEqual("seat-secret", environment["SEAT_KEY"])
            self.assertNotIn("OTHER_TOKEN", environment)
            self.assertIn("seat-0-codex/.codex-home", environment["CODEX_HOME"])

    def test_harness_writes_per_turn_trace_file(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", return_value="/bin/fake"):
            config = PlayerConfig.from_dict({
                "name": "Codex", "backend": "codex", "model": "gpt-test",
            }, 0)
            agent = HarnessAgent(config, "trace-match", 0, runs_root=directory)

            def fake_run(_command):
                context = agent.session.runtime / "turn-context.json"
                call_tool(context, "observe")
                call_tool(context, "legal_actions")
                # Simulate streamed assistant prose and a tool-call sighting,
                # in the order the harness would emit them.
                agent._trace_steps.append({"role": "assistant", "channel": "reasoning", "text": "planning"})
                agent._trace_steps.append({"role": "tool_call", "tool": "submit_action", "arguments": {"action_id": "a-test"}, "result": None})
                call_tool(context, "submit_action", {"action_id": "a-test"})
                agent.session.session_id = "trace-session"
                return "", "", 0

            with mock.patch.object(agent, "_run", side_effect=fake_run):
                action_id, _ = agent.choose({"turn_count": 5, "state_version": 5, "game": "splendor"}, LEGAL)
            self.assertEqual("a-test", action_id)
            trace_path = Path(directory) / "_traces" / "trace-match" / "seat-0" / "turn-0005.json"
            self.assertTrue(trace_path.is_file())
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            self.assertEqual("agentbga.turn-trace.v1", trace["schema_version"])
            self.assertEqual(0, trace["seat"])
            self.assertEqual("trace-session", trace["session_id"])
            self.assertEqual("ok", trace["status"])
            self.assertIsNone(trace["error"])
            self.assertIn("seat 0", trace["prompt"]["user"])
            self.assertEqual("a-test", trace["prompt"]["legal_actions"][0]["id"])
            self.assertEqual("a-test", trace["submission"]["action_id"])
            # The observe and legal_actions tool calls were not sighted in the
            # stream, so they are appended from the audit log with results.
            tools_seen = [step for step in trace["steps"] if step.get("role") == "tool_call"]
            tool_names = [step["tool"] for step in tools_seen]
            self.assertIn("observe", tool_names)
            self.assertIn("legal_actions", tool_names)
            self.assertIn("submit_action", tool_names)
            # submit_action was sighted in the stream; its result is filled in.
            submit_step = next(step for step in tools_seen if step["tool"] == "submit_action")
            self.assertEqual({"action_id": "a-test"}, submit_step["arguments"])
            self.assertEqual("a-test", submit_step["result"]["action_id"])
            # The reasoning chunk is preserved in order.
            reasoning = [step for step in trace["steps"] if step.get("role") == "assistant" and step.get("channel") == "reasoning"]
            self.assertEqual("planning", reasoning[0]["text"])

    def test_harness_writes_trace_on_error(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", return_value="/bin/fake"):
            config = PlayerConfig.from_dict({
                "name": "Codex", "backend": "codex", "model": "gpt-test",
            }, 0)
            agent = HarnessAgent(config, "err-match", 0, runs_root=directory)
            with mock.patch.object(agent, "_run", return_value=("", "boom", 1)):
                with self.assertRaisesRegex(AgentError, "exited 1"):
                    agent.choose({"turn_count": 0, "state_version": 0}, LEGAL)
            trace_path = Path(directory) / "_traces" / "err-match" / "seat-0" / "turn-0000.json"
            self.assertTrue(trace_path.is_file())
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            self.assertEqual("error", trace["status"])
            self.assertEqual("boom", trace["error"])
            self.assertIsNone(trace["submission"])


if __name__ == "__main__":
    unittest.main()
