import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest
from unittest import mock

from agentbga.agents import AgentError, PlayerConfig
from agentbga.harness import HarnessAgent
from agentbga.seat_mcp import TOOLS
from agentbga.seat_tool import call_tool
from agentbga.store import Store
from agentbga.usage import TokenUsageAccumulator, TokenUsageSample


LEGAL = [{"id": "a-test", "action": {"type": "take_tokens", "take": {"blue": 2}, "return": {}}}]


class HarnessTests(unittest.TestCase):
    def test_qwen_resumed_usage_keeps_latest_cumulative_snapshot(self):
        agent = HarnessAgent.__new__(HarnessAgent)
        agent.config = mock.Mock(backend="qwen")
        agent._match_usage = TokenUsageAccumulator()
        agent._turn_usage = TokenUsageAccumulator()
        agent._qwen_usage_snapshot = None
        first = TokenUsageSample(100, 60, 0, 30, 20, "qwen.result")
        second = TokenUsageSample(160, 100, 0, 50, 30, "qwen.result")

        agent._record_stream_usage(first, {"num_turns": 2})
        agent._turn_usage = TokenUsageAccumulator()
        agent._record_stream_usage(second, {"num_turns": 4})

        self.assertEqual(160, agent.usage_summary()["input_tokens"])
        self.assertEqual(100, agent.usage_summary()["cached_input_tokens"])
        self.assertEqual(50, agent.usage_summary()["output_tokens"])
        self.assertEqual(4, agent.usage_summary()["usage_records"])
        self.assertEqual(60, agent._turn_usage.summary()["input_tokens"])
        self.assertEqual(40, agent._turn_usage.summary()["cached_input_tokens"])
        self.assertEqual(20, agent._turn_usage.summary()["output_tokens"])

    def test_qwen_backend_is_persisted_as_a_harness(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "matches.sqlite3")
            match_id, _, _ = store.create(2, 7)
            store.set_players(match_id, [
                PlayerConfig.from_dict({
                    "name": "Qwen Code", "backend": "qwen", "model": "qwen3-coder-plus",
                }, 0).public_dict(),
                PlayerConfig.from_dict({"name": "Random", "backend": "random"}, 1).public_dict(),
            ])
            players = store.players(match_id)
            store.close()
        self.assertEqual("qwen", players[0]["harness"])
        self.assertNotIn("harness", players[1])

    def test_player_config_accepts_harness_backends(self):
        codex = PlayerConfig.from_dict({
            "name": "Codex + GPT", "backend": "codex", "model": "gpt-test",
        }, 0)
        opencode = PlayerConfig.from_dict({
            "name": "OpenCode + DeepSeek", "backend": "opencode",
            "model": "deepseek/deepseek-chat",
            "base_url": "https://api.deepseek.com/v1/chat/completions/",
        }, 1)
        self.assertEqual("OPENAI_API_KEY", codex.api_key_env)
        self.assertEqual("api_key", codex.auth_mode)
        self.assertEqual("responses", codex.wire_api)
        self.assertEqual("DEEPSEEK_API_KEY", opencode.api_key_env)
        self.assertEqual("https://api.deepseek.com/v1", opencode.base_url)
        claude = PlayerConfig.from_dict({
            "name": "Claude Code", "backend": "claude", "model": "claude-test",
        }, 2)
        pi = PlayerConfig.from_dict({
            "name": "Pi", "backend": "pi", "model": "model-test",
        }, 3)
        qwen = PlayerConfig.from_dict({
            "name": "Qwen Code", "backend": "qwen", "model": "qwen3-coder-plus",
        }, 4)
        self.assertEqual("ANTHROPIC_API_KEY", claude.api_key_env)
        self.assertEqual("AGENTBGA_API_KEY", pi.api_key_env)
        self.assertEqual("BAILIAN_CODING_PLAN_API_KEY", qwen.api_key_env)
        self.assertEqual("https://coding.dashscope.aliyuncs.com/v1", qwen.base_url)
        cursor = PlayerConfig.from_dict({
            "name": "Cursor CLI", "backend": "cursor", "model": "gpt-test",
        }, 4)
        grok = PlayerConfig.from_dict({
            "name": "Grok Build", "backend": "grok", "model": "grok-4.6",
        }, 4)
        self.assertEqual("CURSOR_API_KEY", cursor.api_key_env)
        self.assertIsNone(cursor.base_url)
        self.assertEqual("XAI_API_KEY", grok.api_key_env)
        self.assertEqual("https://api.x.ai/v1", grok.base_url)
        self.assertEqual("max", codex.reasoning_effort)
        self.assertEqual("max", opencode.reasoning_effort)
        dsh = PlayerConfig.from_dict({
            "name": "DeepSeek Harness", "backend": "dsh", "model": "deepseek-v4-flash",
        }, 4)
        self.assertEqual("DEEPSEEK_API_KEY", dsh.api_key_env)
        self.assertEqual("https://api.deepseek.com", dsh.base_url)
        self.assertEqual("max", dsh.reasoning_effort)
        series = PlayerConfig.from_dict({
            "name": "DSh series", "backend": "dsh", "model": "deepseek-v4-flash",
            "series_id": "anneal-20",
        }, 5)
        self.assertEqual("anneal-20", series.series_id)
        opencode_series = PlayerConfig.from_dict({
            "name": "OpenCode series", "backend": "opencode", "model": "test",
            "series_id": "anneal-20", "participant_id": "opencode-player",
        }, 5)
        self.assertEqual("opencode-player", opencode_series.participant_id)
        hermes = PlayerConfig.from_dict({
            "name": "Hermes Agent", "backend": "hermes", "model": "gpt-test",
        }, 5)
        self.assertEqual("OPENAI_API_KEY", hermes.api_key_env)
        self.assertEqual("https://api.openai.com/v1", hermes.base_url)
        self.assertEqual("max", hermes.reasoning_effort)

        configured = PlayerConfig.from_dict({
            "name": "Configured", "backend": "opencode", "model": "deepseek-v4-flash",
            "reasoning_effort": "medium",
        }, 5)
        self.assertEqual("medium", configured.reasoning_effort)
        with self.assertRaisesRegex(ValueError, "reasoning_effort must be one of"):
            PlayerConfig.from_dict({
                "name": "Invalid", "backend": "codex", "model": "gpt-test",
                "reasoning_effort": "extreme",
            }, 6)
        with self.assertRaisesRegex(ValueError, "codex wire_api must be responses"):
            PlayerConfig.from_dict({
                "name": "Legacy Codex", "backend": "codex", "model": "gpt-test",
                "wire_api": "chat",
            }, 6)
        with self.assertRaisesRegex(ValueError, "cannot be none"):
            PlayerConfig.from_dict({
                "name": "No Reasoning Codex", "backend": "codex", "model": "gpt-test",
                "reasoning_effort": "none",
            }, 6)
        with self.assertRaisesRegex(ValueError, "qwen reasoning_effort cannot be none"):
            PlayerConfig.from_dict({
                "name": "No Reasoning Qwen", "backend": "qwen", "model": "qwen3-coder-plus",
                "reasoning_effort": "none",
            }, 6)
        subscription = PlayerConfig.from_dict({
            "name": "Codex Subscription", "backend": "codex", "model": "gpt-test",
            "auth_mode": "subscription",
        }, 6)
        self.assertEqual("subscription", subscription.auth_mode)
        self.assertIsNone(subscription.base_url)
        self.assertIsNone(subscription.api_key_env)
        with self.assertRaisesRegex(ValueError, "subscription auth cannot use base_url"):
            PlayerConfig.from_dict({
                "name": "Invalid Subscription", "backend": "codex", "model": "gpt-test",
                "auth_mode": "subscription", "base_url": "https://api.openai.com/v1",
            }, 6)
        with self.assertRaisesRegex(ValueError, "only supported by the codex backend"):
            PlayerConfig.from_dict({
                "name": "Invalid Auth", "backend": "opencode", "model": "gpt-test",
                "auth_mode": "subscription",
            }, 6)
        with self.assertRaisesRegex(ValueError, "only supported for harness backends"):
            PlayerConfig.from_dict({
                "name": "Direct API", "backend": "openai", "model": "gpt-test",
                "reasoning_effort": "high",
            }, 6)

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
        self.assertEqual({
            "observe", "legal_actions", "inspect", "inspect_card", "inspect_rules", "inspect_map",
            "inspect_played_cards", "inspect_history", "submit_action",
            "read_notes", "write_notes",
        }, {tool["name"] for tool in TOOLS})

    def test_notes_ignore_mutable_context_path_and_reject_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            workspace = root / "workspace"
            runtime.mkdir()
            workspace.mkdir()
            outside = root / "outside.txt"
            outside.write_text("host secret", encoding="utf-8")
            context = runtime / "turn-context.json"
            context.write_text(json.dumps({
                "schema_version": "agentbga.seat-context.v1", "match_id": "m", "seat": 0,
                "version": 1, "observation": {}, "legal_actions": [],
                "notes_path": str(outside),
            }))

            self.assertEqual("", call_tool(context, "read_notes", notes_root=workspace))
            call_tool(context, "write_notes", {"content": "safe"}, notes_root=workspace)
            self.assertEqual("safe", (workspace / "strategy-notes.md").read_text())
            self.assertEqual("host secret", outside.read_text())

            (workspace / "strategy-notes.md").unlink()
            (workspace / "strategy-notes.md").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "single-link regular file"):
                call_tool(context, "read_notes", notes_root=workspace)
            with self.assertRaisesRegex(ValueError, "single-link regular file"):
                call_tool(context, "write_notes", {"content": "escape"}, notes_root=workspace)
            self.assertEqual("host secret", outside.read_text())

    def test_notes_descriptor_cannot_be_redirected_after_atomic_open(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            workspace = root / "workspace"
            runtime.mkdir()
            workspace.mkdir()
            outside = root / "outside.txt"
            outside.write_text("host secret", encoding="utf-8")
            context = runtime / "turn-context.json"
            context.write_text(json.dumps({
                "schema_version": "agentbga.seat-context.v1", "match_id": "m", "seat": 0,
                "version": 1, "observation": {}, "legal_actions": [],
            }))
            notes = workspace / "strategy-notes.md"
            notes.write_text("safe notes", encoding="utf-8")
            original = notes.stat()
            real_fstat = os.fstat
            swapped = False

            def swap_after_open(descriptor):
                nonlocal swapped
                metadata = real_fstat(descriptor)
                if not swapped and (metadata.st_dev, metadata.st_ino) == (
                    original.st_dev, original.st_ino,
                ):
                    notes.unlink()
                    notes.symlink_to(outside)
                    swapped = True
                return metadata

            with mock.patch("agentbga.seat_tool.os.fstat", side_effect=swap_after_open):
                self.assertEqual(
                    "safe notes", call_tool(context, "read_notes", notes_root=workspace),
                )
            self.assertTrue(swapped)
            self.assertTrue(notes.is_symlink())
            self.assertEqual("host secret", outside.read_text(encoding="utf-8"))

            notes.unlink()
            notes.write_text("old notes", encoding="utf-8")
            original = notes.stat()
            swapped = False
            with mock.patch("agentbga.seat_tool.os.fstat", side_effect=swap_after_open):
                result = call_tool(
                    context, "write_notes", {"content": "replacement"}, notes_root=workspace,
                )
            self.assertTrue(result["saved"])
            self.assertTrue(swapped)
            self.assertTrue(notes.is_symlink())
            self.assertEqual("host secret", outside.read_text(encoding="utf-8"))

    def test_notes_resist_concurrent_symlink_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            workspace = root / "workspace"
            runtime.mkdir()
            workspace.mkdir()
            outside = root / "outside.txt"
            outside.write_text("host secret", encoding="utf-8")
            context = runtime / "turn-context.json"
            context.write_text(json.dumps({
                "schema_version": "agentbga.seat-context.v1", "match_id": "m", "seat": 0,
                "version": 1, "observation": {}, "legal_actions": [],
            }))
            notes = workspace / "strategy-notes.md"
            notes.write_text("safe", encoding="utf-8")
            stop = threading.Event()
            started = threading.Event()
            swaps = 0

            def replace_entry():
                nonlocal swaps
                link = workspace / "notes-link.tmp"
                regular = workspace / "notes-regular.tmp"
                while not stop.is_set():
                    link.unlink(missing_ok=True)
                    link.symlink_to(outside)
                    os.replace(link, notes)
                    regular.write_text("safe", encoding="utf-8")
                    os.replace(regular, notes)
                    swaps += 1
                    started.set()

            attacker = threading.Thread(target=replace_entry)
            attacker.start()
            try:
                self.assertTrue(started.wait(timeout=2))
                for index in range(200):
                    try:
                        call_tool(
                            context, "write_notes", {"content": f"safe-{index}"},
                            notes_root=workspace,
                        )
                    except (OSError, ValueError):
                        # Hostile replacement may deny an operation, but must
                        # never redirect its descriptor outside the workspace.
                        pass
            finally:
                stop.set()
                attacker.join(timeout=2)
            self.assertFalse(attacker.is_alive())
            self.assertGreater(swaps, 0)
            self.assertEqual("host secret", outside.read_text(encoding="utf-8"))

    @unittest.skipUnless(hasattr(os, "link"), "hard links are required")
    def test_notes_reject_hard_links_and_non_regular_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            workspace = root / "workspace"
            runtime.mkdir()
            workspace.mkdir()
            outside = root / "outside.txt"
            outside.write_text("host secret", encoding="utf-8")
            context = runtime / "turn-context.json"
            context.write_text(json.dumps({
                "schema_version": "agentbga.seat-context.v1", "match_id": "m", "seat": 0,
                "version": 1, "observation": {}, "legal_actions": [],
            }))
            notes = workspace / "strategy-notes.md"
            os.link(outside, notes)
            with self.assertRaisesRegex(ValueError, "single-link regular file"):
                call_tool(context, "read_notes", notes_root=workspace)
            with self.assertRaisesRegex(ValueError, "single-link regular file"):
                call_tool(context, "write_notes", {"content": "escape"}, notes_root=workspace)
            self.assertEqual("host secret", outside.read_text(encoding="utf-8"))

            notes.unlink()
            notes.mkdir()
            with self.assertRaisesRegex(ValueError, "single-link regular file"):
                call_tool(context, "read_notes", notes_root=workspace)
            with self.assertRaisesRegex(ValueError, "single-link regular file"):
                call_tool(context, "write_notes", {"content": "escape"}, notes_root=workspace)

            if hasattr(os, "mkfifo"):
                notes.rmdir()
                os.mkfifo(notes)
                with self.assertRaisesRegex(ValueError, "single-link regular file"):
                    call_tool(context, "read_notes", notes_root=workspace)
                with self.assertRaisesRegex(ValueError, "single-link regular file"):
                    call_tool(context, "write_notes", {"content": "escape"}, notes_root=workspace)

    def test_runtime_outputs_reject_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            outside = root / "outside.txt"
            outside.write_text("host secret", encoding="utf-8")
            context = runtime / "turn-context.json"
            context.write_text(json.dumps({
                "schema_version": "agentbga.seat-context.v1", "match_id": "m", "seat": 0,
                "version": 1, "observation": {"viewer_seat": 0},
                "legal_actions": [{"id": "a-good", "type": "pass"}],
            }))

            audit = runtime / "tool-events.jsonl"
            audit.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "single-link regular file"):
                call_tool(context, "observe")
            self.assertEqual("host secret", outside.read_text(encoding="utf-8"))

            audit.unlink()
            submission = runtime / "submission.json"
            submission.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "already been submitted"):
                call_tool(context, "submit_action", {"action_id": "a-good"})
            self.assertEqual("host secret", outside.read_text(encoding="utf-8"))

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
                [sys.executable, "-m", "agentbga.seat_mcp", "--context", str(context),
                 "--notes-root", directory],
                input=requests, text=True, capture_output=True, check=True,
            )
            responses = [json.loads(line) for line in completed.stdout.splitlines()]
            self.assertEqual("agentbga-seat", responses[0]["result"]["serverInfo"]["name"])
            self.assertEqual(11, len(responses[1]["result"]["tools"]))

    def test_harness_commands_resume_sessions(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", side_effect=lambda name: f"/bin/{name}"):
            codex_config = PlayerConfig.from_dict({
                "name": "Codex", "backend": "codex", "model": "gpt-test",
            }, 0)
            codex = HarnessAgent(codex_config, "match", 0, runs_root=directory)
            first_command = codex._command("turn")
            self.assertIn("workspace-write", first_command)
            self.assertNotIn("--ask-for-approval", first_command)
            runtime_dir = os.path.relpath(codex.session.runtime, codex.session.workspace)
            self.assertEqual(runtime_dir, first_command[first_command.index("--add-dir") + 1])
            self.assertNotIn(str(codex.session.runtime), first_command)
            codex.session.session_id = "thread-1"
            resume_command = codex._command("turn")
            self.assertEqual(runtime_dir, resume_command[resume_command.index("--add-dir") + 1])
            self.assertLess(resume_command.index("--add-dir"), resume_command.index("resume"))
            self.assertNotIn(str(codex.session.runtime), resume_command)

            opencode_config = PlayerConfig.from_dict({
                "name": "OpenCode", "backend": "opencode", "model": "deepseek/test",
                "base_url": "https://deepseek-proxy.example/v1", "reasoning_effort": "medium",
            }, 1)
            opencode = HarnessAgent(opencode_config, "match", 1, runs_root=directory)
            opencode.session.session_id = "session-1"
            command = opencode._command("turn")
            self.assertIn("--pure", command)
            self.assertEqual("medium", command[command.index("--variant") + 1])
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
            self.assertIn("mcp__agentbga__inspect_card", command)
            self.assertIn("mcp__agentbga__inspect_rules", command)
            self.assertIn("mcp__agentbga__inspect_map", command)
            self.assertIn("mcp__agentbga__inspect_played_cards", command)
            self.assertIn("mcp__agentbga__inspect_history", command)
            self.assertIn("mcp__agentbga__inspect", command)
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

            qwen_config = PlayerConfig.from_dict({
                "name": "Qwen Code", "backend": "qwen", "model": "qwen3-coder-plus",
                "reasoning_effort": "minimal",
            }, 4)
            qwen = HarnessAgent(qwen_config, "match", 4, runs_root=directory)
            qwen._prepare_turn({"state_version": 1}, LEGAL)
            qwen.session.session_id = "qwen-session"
            command = qwen._command("turn")
            self.assertEqual("stream-json", command[command.index("--output-format") + 1])
            self.assertIn("--chat-recording", command)
            self.assertEqual("yolo", command[command.index("--approval-mode") + 1])
            self.assertEqual("", command[command.index("--core-tools") + 1])
            inline_mcp = json.loads(command[command.index("--mcp-config") + 1])
            self.assertIn("agentbga", inline_mcp["mcpServers"])
            self.assertEqual("qwen-session", command[command.index("--resume") + 1])
            self.assertEqual("turn", command[command.index("--prompt") + 1])
            self.assertEqual("low", qwen._native_reasoning_effort())

            cursor_config = PlayerConfig.from_dict({
                "name": "Cursor CLI", "backend": "cursor", "model": "gpt-test",
            }, 4)
            cursor = HarnessAgent(cursor_config, "match", 4, runs_root=directory)
            self.assertEqual("/bin/cursor-agent", cursor.binary)
            cursor.session.session_id = "cursor-session"
            command = cursor._command("turn")
            self.assertEqual("stream-json", command[command.index("--output-format") + 1])
            self.assertIn("--approve-mcps", command)
            self.assertIn("--trust", command)
            self.assertEqual("cursor-session", command[command.index("--resume") + 1])

            grok_config = PlayerConfig.from_dict({
                "name": "Grok Build", "backend": "grok", "model": "grok-4.6",
                "reasoning_effort": "xhigh",
            }, 4)
            grok = HarnessAgent(grok_config, "match", 4, runs_root=directory)
            grok.session.session_id = "grok-session"
            command = grok._command("turn")
            self.assertEqual("streaming-json", command[command.index("--output-format") + 1])
            self.assertEqual("agentbga", command[command.index("--sandbox") + 1])
            self.assertEqual("MCPTool(agentbga__*)", command[command.index("--allow") + 1])
            self.assertEqual("xhigh", command[command.index("--effort") + 1])
            self.assertEqual("grok-session", command[command.index("--resume") + 1])
            self.assertEqual("turn", command[command.index("-p") + 1])

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
            self.assertTrue(dsh.session.session_id.startswith("session-agentbga-match-"))

            hermes_config = PlayerConfig.from_dict({
                "name": "Hermes Agent", "backend": "hermes", "model": "gpt-test",
            }, 5)
            hermes = HarnessAgent(hermes_config, "match", 5, runs_root=directory)
            command = hermes._command("turn")
            self.assertEqual("chat", command[1])
            self.assertIn("--quiet", command)
            self.assertIn("--ignore-rules", command)
            self.assertEqual("tool", command[command.index("--source") + 1])
            self.assertEqual(["--query", "turn"], command[-2:])
            self.assertNotIn("--resume", command)
            hermes.session.session_id = "hermes-session"
            command = hermes._command("next turn")
            self.assertEqual("hermes-session", command[command.index("--resume") + 1])

    def test_harnesses_generate_seat_tool_configuration(self):
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
                    self.assertEqual("xhigh", models["providers"]["agentbga"]["models"][0]["thinkingLevelMap"]["xhigh"])
                    extension = (agent.session.workspace / "agentbga-tools.ts").read_text()
                    self.assertIn('name: "submit_action"', extension)

            qwen = HarnessAgent(PlayerConfig.from_dict({
                "name": "Qwen Code", "backend": "qwen", "model": "qwen3-coder-plus",
                "base_url": "https://coding.dashscope.aliyuncs.com/v1",
                "api_key_env": "QWEN_TEST_KEY", "reasoning_effort": "high",
            }, 0), "match-qwen", 0, runs_root=directory)
            qwen._prepare_turn({"state_version": 1}, LEGAL)
            qwen_settings = json.loads(
                (qwen.session.workspace / ".qwen-home" / "settings.json").read_text()
            )
            provider = qwen_settings["modelProviders"]["openai"][0]
            self.assertEqual("qwen3-coder-plus", provider["id"])
            self.assertEqual(
                "https://coding.dashscope.aliyuncs.com/v1", provider["baseUrl"],
            )
            self.assertEqual("QWEN_TEST_KEY", provider["envKey"])
            self.assertEqual("high", qwen_settings["model"]["reasoningEffort"])
            self.assertEqual([], qwen_settings["tools"]["core"])
            self.assertIn("agent", qwen_settings["tools"]["disabled"])
            self.assertIn("skill", qwen_settings["tools"]["disabled"])
            self.assertFalse(qwen_settings["tools"]["computerUse"]["enabled"])
            self.assertFalse(qwen_settings["memory"]["enableManagedAutoMemory"])
            self.assertEqual(["agentbga"], qwen_settings["mcp"]["allowed"])
            qwen_mcp = json.loads(
                (qwen.session.workspace / "qwen-mcp.json").read_text()
            )
            self.assertEqual(
                ["observe", "legal_actions", "submit_action", "read_notes", "write_notes"],
                qwen_mcp["mcpServers"]["agentbga"]["includeTools"],
            )
            with mock.patch.dict(os.environ, {
                "QWEN_TEST_KEY": "qwen-secret", "OTHER_TOKEN": "hidden", "PATH": "/bin",
            }, clear=True):
                qwen_environment = qwen._environment()
            self.assertEqual("qwen-secret", qwen_environment["QWEN_TEST_KEY"])
            self.assertNotIn("OTHER_TOKEN", qwen_environment)
            self.assertEqual("0", qwen_environment["QWEN_USAGE_STATISTICS_ENABLED"])
            self.assertEqual("0", qwen_environment["QWEN_TELEMETRY_ENABLED"])
            self.assertIn("seat-0-qwen/.qwen-home", qwen_environment["QWEN_HOME"])

            cursor = HarnessAgent(PlayerConfig.from_dict({
                "name": "Cursor CLI", "backend": "cursor", "model": "gpt-test",
                "api_key_env": "CURSOR_TEST_KEY",
            }, 0), "match-cursor", 0, runs_root=directory)
            cursor._prepare_turn({"state_version": 1}, LEGAL)
            cursor_mcp = json.loads(
                (cursor.session.workspace / ".cursor" / "mcp.json").read_text()
            )
            self.assertIn("agentbga", cursor_mcp["mcpServers"])
            cursor_policy = json.loads(
                (cursor.session.workspace / ".cursor" / "cli.json").read_text()
            )
            self.assertEqual(1, cursor_policy["version"])
            self.assertIn("Shell(*)", cursor_policy["permissions"]["deny"])
            cursor_global = json.loads(
                (cursor.session.workspace / ".cursor-data" / "cli-config.json").read_text()
            )
            self.assertFalse(cursor_global["editor"]["vimMode"])
            self.assertFalse(cursor_global["attribution"]["attributeCommitsToAgent"])
            with mock.patch.dict(os.environ, {
                "CURSOR_TEST_KEY": "cursor-secret", "OTHER_TOKEN": "hidden", "PATH": "/bin",
            }, clear=True):
                cursor_environment = cursor._environment()
            self.assertEqual("cursor-secret", cursor_environment["CURSOR_API_KEY"])
            self.assertNotIn("OTHER_TOKEN", cursor_environment)
            self.assertIn("seat-0-cursor/.cursor-data", cursor_environment["CURSOR_DATA_DIR"])
            self.assertEqual(
                cursor_environment["CURSOR_DATA_DIR"], cursor_environment["CURSOR_CONFIG_DIR"],
            )

            grok = HarnessAgent(PlayerConfig.from_dict({
                "name": "Grok Build", "backend": "grok", "model": "grok-4.6",
                "api_key_env": "GROK_TEST_KEY",
            }, 0), "match-grok", 0, runs_root=directory)
            grok._prepare_turn({"state_version": 1}, LEGAL)
            grok_home = grok.session.workspace / ".grok-home"
            grok_toml = (grok_home / "config.toml").read_text()
            self.assertIn("[mcp_servers.agentbga]", grok_toml)
            self.assertIn("mcps = false", grok_toml)
            grok_settings = tomllib.loads(grok_toml)
            self.assertFalse(grok_settings["features"]["telemetry"])
            self.assertTrue(grok_settings["mcp_servers"]["agentbga"]["enabled"])
            grok_sandbox = (grok_home / "sandbox.toml").read_text()
            self.assertIn("[profiles.agentbga]", grok_sandbox)
            self.assertIn("extends = \"strict\"", grok_sandbox)
            self.assertIn(str(grok.session.runtime), grok_sandbox)
            sandbox_settings = tomllib.loads(grok_sandbox)["profiles"]["agentbga"]
            self.assertEqual("strict", sandbox_settings["extends"])
            self.assertIn(str(grok.session.runtime), sandbox_settings["read_write"])
            with mock.patch.dict(os.environ, {
                "GROK_TEST_KEY": "grok-secret", "OTHER_TOKEN": "hidden", "PATH": "/bin",
            }, clear=True):
                grok_environment = grok._environment()
            self.assertEqual("grok-secret", grok_environment["XAI_API_KEY"])
            self.assertNotIn("OTHER_TOKEN", grok_environment)
            self.assertEqual("0", grok_environment["GROK_TELEMETRY_ENABLED"])
            self.assertIn("seat-0-grok/.grok-home", grok_environment["GROK_HOME"])

            opencode = HarnessAgent(PlayerConfig.from_dict({
                "name": "OpenCode", "backend": "opencode", "model": "custom-model",
                "base_url": "https://proxy.example/v1", "api_key_env": "CUSTOM_KEY",
            }, 0), "match-two", 0, runs_root=directory)
            opencode._prepare_turn({"state_version": 1}, LEGAL)
            configured = json.loads((opencode.session.workspace / "opencode.json").read_text())
            self.assertEqual("@ai-sdk/openai-compatible", configured["provider"]["agentbga"]["npm"])
            self.assertEqual("{env:CUSTOM_KEY}", configured["provider"]["agentbga"]["options"]["apiKey"])
            # Reasoning is controlled explicitly, not inferred from the endpoint URL.
            variant = configured["provider"]["agentbga"]["models"]["custom-model"]["variants"]["max"]
            self.assertEqual("max", variant["reasoningEffort"])
            opencode_command = opencode._command("turn")
            self.assertIn("agentbga/custom-model", opencode_command)
            self.assertIn("--print-logs", opencode_command)
            self.assertIn("--title=AgentBGA-seat-1", opencode_command)
            self.assertNotIn("read", configured["permission"])
            self.assertNotIn("edit", configured["permission"])
            opencode_environment = opencode._environment()
            self.assertEqual(
                str(opencode.session.workspace / "opencode.json"),
                opencode_environment["OPENCODE_CONFIG"],
            )
            self.assertEqual("1", opencode_environment["OPENCODE_DISABLE_PROJECT_CONFIG"])
            self.assertEqual(
                str(opencode.session.runtime / "turn-context.json"),
                configured["mcp"]["agentbga"]["command"][4],
            )
            self.assertEqual(
                str(opencode.session.workspace),
                configured["mcp"]["agentbga"]["command"][6],
            )

            proxied_deepseek = HarnessAgent(PlayerConfig.from_dict({
                "name": "OpenCode", "backend": "opencode", "model": "deepseek-v4-flash",
                "base_url": "https://deepseek-proxy.example/compatible-mode/v1",
                "reasoning_effort": "high",
            }, 1), "match-three", 1, runs_root=directory)
            proxied_deepseek._prepare_turn({"state_version": 1}, LEGAL)
            proxied_config = json.loads((proxied_deepseek.session.workspace / "opencode.json").read_text())
            proxied_variant = proxied_config["provider"]["agentbga"]["models"]["deepseek-v4-flash"]["variants"]["high"]
            self.assertEqual("high", proxied_variant["reasoningEffort"])
            self.assertEqual({"type": "enabled"}, proxied_variant["thinking"])
            self.assertIn("--thinking", proxied_deepseek._command("turn"))

            non_deepseek_url = HarnessAgent(PlayerConfig.from_dict({
                "name": "OpenCode", "backend": "opencode", "model": "deepseek-v4-flash",
                "base_url": "https://dashscope.example/compatible-mode/v1",
                "reasoning_effort": "high",
            }, 1), "match-five", 1, runs_root=directory)
            non_deepseek_url._prepare_turn({"state_version": 1}, LEGAL)
            non_deepseek_config = json.loads((non_deepseek_url.session.workspace / "opencode.json").read_text())
            non_deepseek_variant = non_deepseek_config["provider"]["agentbga"]["models"]["deepseek-v4-flash"]["variants"]["high"]
            self.assertEqual("high", non_deepseek_variant["reasoningEffort"])
            self.assertNotIn("thinking", non_deepseek_variant)
            self.assertIn("--thinking", non_deepseek_url._command("turn"))

            glm = HarnessAgent(PlayerConfig.from_dict({
                "name": "GLM", "backend": "opencode", "model": "glm-5.2",
                "base_url": "https://dashscope.example/compatible-mode/v1",
                "reasoning_effort": "high",
            }, 1), "match-glm", 1, runs_root=directory)
            glm._prepare_turn({"state_version": 1}, LEGAL)
            glm_config = json.loads((glm.session.workspace / "opencode.json").read_text())
            glm_variant = glm_config["provider"]["agentbga"]["models"]["glm-5.2"]["variants"]["high"]
            self.assertEqual("high", glm_variant["reasoningEffort"])
            self.assertTrue(glm_variant["tool_stream"])

            kimi = HarnessAgent(PlayerConfig.from_dict({
                "name": "Kimi", "backend": "opencode", "model": "kimi-k2.7-code",
                "base_url": "https://dashscope.example/compatible-mode/v1",
                "reasoning_effort": "none",
            }, 1), "match-kimi", 1, runs_root=directory)
            kimi._prepare_turn({"state_version": 1}, LEGAL)
            kimi_config = json.loads((kimi.session.workspace / "opencode.json").read_text())
            kimi_variant = kimi_config["provider"]["agentbga"]["models"]["kimi-k2.7-code"]["variants"]["none"]
            self.assertEqual({"enable_thinking": True}, kimi_variant)
            self.assertNotIn("--thinking", kimi._command("turn"))

            no_reasoning = HarnessAgent(PlayerConfig.from_dict({
                "name": "OpenCode", "backend": "opencode", "model": "deepseek-v4-flash",
                "base_url": "https://deepseek-proxy.example/compatible-mode/v1",
                "reasoning_effort": "none",
            }, 1), "match-four", 1, runs_root=directory)
            no_reasoning._prepare_turn({"state_version": 1}, LEGAL)
            self.assertNotIn("--thinking", no_reasoning._command("turn"))
            no_reasoning_config = json.loads((no_reasoning.session.workspace / "opencode.json").read_text())
            no_reasoning_variant = no_reasoning_config["provider"]["agentbga"]["models"]["deepseek-v4-flash"]["variants"]["none"]
            self.assertEqual({"type": "disabled"}, no_reasoning_variant["thinking"])

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
            self.assertIn("- id: headless-runner\n  disabled: true", patch)
            self.assertIn("agentbga-resumable-runner", patch)
            self.assertIn("dsh_resumable_runner.mjs", patch)
            self.assertIn("sessionId:", patch)
            self.assertIn("ownerKey:", patch)
            self.assertIn("serverName: agentbga", patch)
            env = dsh._environment()
            self.assertEqual("https://api.deepseek.com", env["DEEPSEEK_BASE_URL"])
            self.assertEqual("workspace-write", env["DSH_PERMISSION_MODE"])
            self.assertEqual("DISABLED", env["DSH_TELEMETRY_MODE"])
            self.assertIn("seat-0-dsh", env["DSH_HOME"])

            hermes = HarnessAgent(PlayerConfig.from_dict({
                "name": "Hermes Agent", "backend": "hermes", "model": "custom-model",
                "base_url": "https://proxy.example/v1", "api_key_env": "CUSTOM_KEY",
                "wire_api": "responses", "reasoning_effort": "medium",
            }, 1), "match-hermes", 1, runs_root=directory)
            hermes._prepare_turn({"state_version": 1}, LEGAL)
            hermes_yaml = (hermes.session.workspace / ".hermes-home" / "config.yaml").read_text()
            self.assertIn('default: "custom-model"', hermes_yaml)
            self.assertIn('base_url: "https://proxy.example/v1"', hermes_yaml)
            self.assertIn('api_mode: "codex_responses"', hermes_yaml)
            self.assertIn('reasoning_effort: "medium"', hermes_yaml)
            self.assertIn("platform_toolsets:\n  cli:\n    - agentbga", hermes_yaml)
            self.assertIn("mcp_servers:\n  agentbga:", hermes_yaml)
            self.assertIn("agentbga.seat_mcp", hermes_yaml)
            hermes_with_key = PlayerConfig(**{**hermes.config.__dict__, "api_key": "seat-secret"})
            hermes.config = hermes_with_key
            with mock.patch.dict(os.environ, {"CUSTOM_KEY": "old", "OTHER_TOKEN": "hidden", "PATH": "/bin"}, clear=True):
                environment = hermes._environment()
            self.assertEqual("seat-secret", environment["CUSTOM_KEY"])
            self.assertEqual("seat-secret", environment["OPENAI_API_KEY"])
            self.assertEqual("https://proxy.example/v1", environment["OPENAI_BASE_URL"])
            self.assertIn("seat-1-hermes/.hermes-home", environment["HERMES_HOME"])
            self.assertNotIn("OTHER_TOKEN", environment)

    def test_dsh_session_keys_isolate_seats_and_reset_between_matches(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "shutil.which", return_value="/bin/dsh"
        ):
            config = PlayerConfig.from_dict({
                "name": "DSh", "backend": "dsh", "model": "deepseek-v4-flash",
            }, 0)
            match_a_seat_0 = HarnessAgent(config, "match-a", 0, runs_root=directory)
            match_a_seat_1 = HarnessAgent(config, "match-a", 1, runs_root=directory)
            match_b_seat_0 = HarnessAgent(config, "match-b", 0, runs_root=directory)

            self.assertNotEqual(
                match_a_seat_0.session.session_id, match_a_seat_1.session.session_id
            )
            self.assertNotEqual(match_a_seat_0._dsh_home, match_a_seat_1._dsh_home)
            self.assertNotEqual(
                match_a_seat_0.session.session_id, match_b_seat_0.session.session_id
            )
            self.assertNotEqual(match_a_seat_0._dsh_home, match_b_seat_0._dsh_home)
            self.assertEqual("match", match_a_seat_0.session.scope)

    def test_dsh_series_key_follows_participant_across_seats(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "shutil.which", return_value="/bin/dsh"
        ):
            config = PlayerConfig.from_dict({
                "name": "DSh", "backend": "dsh", "model": "deepseek-v4-flash",
                "series_id": "anneal-20", "participant_id": "learner",
            }, 0)
            other_config = PlayerConfig.from_dict({
                "name": "Other DSh", "backend": "dsh", "model": "deepseek-v4-flash",
                "series_id": "anneal-20", "participant_id": "opponent",
            }, 1)
            first = HarnessAgent(config, "match-01", 0, runs_root=directory)
            second = HarnessAgent(config, "match-02", 1, runs_root=directory)
            other_seat = HarnessAgent(other_config, "match-02", 0, runs_root=directory)

            self.assertEqual(first.session.session_id, second.session.session_id)
            self.assertEqual(first.session.workspace, second.session.workspace)
            self.assertEqual(first._dsh_home, second._dsh_home)
            self.assertNotEqual(first.session.session_id, other_seat.session.session_id)
            self.assertEqual("series", first.session.scope)
            self.assertEqual("anneal-20", first.session.scope_id)

    def test_non_dsh_series_restores_native_session_id(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "shutil.which", return_value="/bin/opencode"
        ):
            config = PlayerConfig.from_dict({
                "name": "OpenCode", "backend": "opencode", "model": "test",
                "series_id": "series-one", "participant_id": "learner",
            }, 0)
            first = HarnessAgent(config, "match-01", 0, runs_root=directory)
            first.session.session_id = "native-session"
            first._save_harness_session_state()
            self.assertEqual(0, first.session.resume_count)
            resumed = HarnessAgent(config, "match-02", 1, runs_root=directory)
            self.assertEqual("native-session", resumed.session.session_id)
            self.assertEqual(first.session.workspace, resumed.session.workspace)
            self.assertEqual("learner", resumed.participant_id)
            self.assertEqual(0, resumed.session.resume_count)

            resumed._save_harness_session_state(resumed=True)
            self.assertEqual(1, resumed.session.resume_count)
            reloaded = HarnessAgent(config, "match-03", 0, runs_root=directory)
            self.assertEqual(1, reloaded.session.resume_count)
            reloaded._save_harness_session_state()
            self.assertEqual(1, reloaded.session.resume_count)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the DSh runner unit test")
    def test_dsh_resumable_runner_create_resume_and_compaction(self):
        completed = subprocess.run(
            [shutil.which("node"), "--test", str(Path(__file__).with_name(
                "dsh_resumable_runner.test.mjs"
            ))],
            text=True, capture_output=True,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)

    def test_hermes_recovers_quiet_session_id_from_isolated_state(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", return_value="/bin/hermes"):
            config = PlayerConfig.from_dict({
                "name": "Hermes Agent", "backend": "hermes", "model": "gpt-test",
            }, 0)
            agent = HarnessAgent(config, "match", 0, runs_root=directory)
            home = agent.session.workspace / ".hermes-home"
            home.mkdir(exist_ok=True)
            with sqlite3.connect(home / "state.db") as connection:
                connection.execute("CREATE TABLE sessions (id TEXT, source TEXT, started_at REAL)")
                connection.executemany(
                    "INSERT INTO sessions VALUES (?, ?, ?)",
                    [("interactive", "cli", 3), ("older-tool", "tool", 1), ("new-tool", "tool", 2)],
                )
            agent._recover_hermes_session_id()
            self.assertEqual("new-tool", agent.session.session_id)

    def test_hermes_reads_exact_usage_delta_from_session_database(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", return_value="/bin/hermes"):
            config = PlayerConfig.from_dict({
                "name": "Hermes Agent", "backend": "hermes", "model": "gpt-test",
            }, 0)
            agent = HarnessAgent(config, "match", 0, runs_root=directory)
            agent.session.session_id = "session-1"
            home = agent.session.workspace / ".hermes-home"
            home.mkdir(exist_ok=True)
            with sqlite3.connect(home / "state.db") as connection:
                connection.execute(
                    "CREATE TABLE sessions ("
                    "id TEXT, input_tokens INTEGER, cache_read_tokens INTEGER, "
                    "cache_write_tokens INTEGER, output_tokens INTEGER, "
                    "reasoning_tokens INTEGER, api_call_count INTEGER)"
                )
                connection.execute(
                    "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("session-1", 100, 70, 5, 30, 20, 2),
                )
            before = {
                "inputTokens": 40, "cacheReadTokens": 30, "cacheWriteTokens": 0,
                "outputTokens": 10, "reasoningTokens": 5, "modelResponses": 1,
            }

            agent._record_hermes_usage(before)

            usage = agent.usage_summary()
            self.assertEqual(105, usage["input_tokens"])
            self.assertEqual(40, usage["cached_input_tokens"])
            self.assertEqual(20, usage["output_tokens"])
            self.assertEqual(15, usage["reasoning_output_tokens"])
            self.assertEqual(1, usage["usage_records"])

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
        qwen_message = {
            "type": "assistant",
            "session_id": "qwen-session",
            "message": {"content": [{"type": "text", "text": "qwen text"}]},
        }
        self.assertEqual("qwen text", HarnessAgent._event_text(qwen_message))
        self.assertEqual("qwen-session", HarnessAgent._event_session_id(qwen_message))
        self.assertEqual("cursor text", HarnessAgent._event_text({
            "type": "assistant", "session_id": "cursor-session",
            "message": {"content": [{"type": "text", "text": "cursor text"}]},
        }))
        self.assertEqual("grok text", HarnessAgent._event_text({
            "type": "text", "data": "grok text",
        }))
        self.assertEqual("grok-session", HarnessAgent._event_session_id({
            "type": "end", "sessionId": "grok-session",
        }))
        self.assertEqual("", HarnessAgent._event_text({
            "type": "end", "text": "do not duplicate final text",
        }))
        self.assertEqual(("submit_action", {"action_id": "a-test"}), HarnessAgent._tool_details({
            "type": "tool_call", "toolName": "submit_action",
            "rawInput": {"action_id": "a-test"},
        }))
        self.assertEqual(("submit_action", {"action_id": "a-test"}), HarnessAgent._tool_details({
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "name": "submit_action",
                "input": {"action_id": "a-test"},
            }]},
        }))

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
            self.assertEqual("xhigh", metadata["native_reasoning_effort"])
            self.assertIsNotNone(metadata["action_latency_ms"])
            self.assertGreaterEqual(metadata["process_latency_ms"], 0)
            self.assertEqual(metadata["process_latency_ms"], metadata["latency_ms"])
            self.assertEqual(3, len([event for event in events if event["type"] == "harness_tool_call"]))
            self.assertTrue((agent.session.workspace / ".codex" / "config.toml").is_file())
            self.assertIn('model_reasoning_effort = "xhigh"', (agent.session.workspace / ".codex" / "config.toml").read_text())
            self.assertIn('model_reasoning_effort="xhigh"', agent._codex_config_args)
            opencode_config = json.loads((agent.session.workspace / "opencode.json").read_text())
            self.assertEqual("deny", opencode_config["permission"]["*"])
            self.assertEqual("allow", opencode_config["permission"]["agentbga_*"])
            self.assertNotEqual(agent.session.workspace.parent, agent.session.runtime.parent)
            codex_command = agent._command("next turn")
            self.assertIn("turn-context.json", " ".join(codex_command))
            self.assertNotIn(directory, " ".join(codex_command))
            displayed = agent._display_command([str(Path.home() / "bin" / "codex"), *codex_command])
            self.assertNotIn(str(Path.home()), " ".join(displayed))

            (agent.session.runtime / "submission.json").unlink(missing_ok=True)
            with mock.patch.object(agent, "_run", return_value=("{}", "", 0)):
                with self.assertRaisesRegex(AgentError, "without calling submit_action"):
                    agent.choose({"turn_count": 1, "state_version": 1}, LEGAL)
            self.assertEqual(1, agent.session.resume_count)
            resumed_trace = json.loads(
                (agent.trace_dir / "turn-0001.json").read_text(encoding="utf-8")
            )
            self.assertTrue(resumed_trace["session_resumed"])
            self.assertEqual(1, resumed_trace["session_resume_count"])

    def test_harness_environment_does_not_inherit_unrelated_secrets(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", return_value="/bin/codex"):
            config = PlayerConfig.from_dict({
                "name": "Codex", "backend": "codex", "model": "gpt-test",
                "api_key_env": "SEAT_KEY",
            }, 0)
            config = PlayerConfig(**{**config.__dict__, "api_key": "seat-secret"})
            with mock.patch.dict(os.environ, {"SEAT_KEY": "old", "OTHER_TOKEN": "hidden", "PATH": "/bin"}, clear=True):
                environment = HarnessAgent(config, "match", 0, runs_root=directory)._environment()
            self.assertEqual("seat-secret", environment["SEAT_KEY"])
            self.assertNotIn("OTHER_TOKEN", environment)
            self.assertIn("seat-0-codex/.codex-home", environment["CODEX_HOME"])

    def test_codex_subscription_reuses_login_store_and_forces_chatgpt_auth(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", return_value="/bin/codex"):
            root = Path(directory)
            source_home = root / "authenticated-codex"
            source_home.mkdir()
            source_auth = source_home / "auth.json"
            source_auth.write_text("{}", encoding="utf-8")
            (source_home / "plugins").mkdir()
            config = PlayerConfig.from_dict({
                "name": "Codex Subscription", "backend": "codex", "model": "gpt-test",
                "auth_mode": "subscription",
            }, 0)
            with mock.patch.dict(os.environ, {
                "HOME": str(root), "PATH": "/bin",
                "CODEX_HOME": str(source_home),
                "OPENAI_API_KEY": "metered-secret",
                "OPENAI_BASE_URL": "https://proxy.example/v1",
            }, clear=True):
                agent = HarnessAgent(config, "match", 0, runs_root=root / "runs")
                environment = agent._environment()
                agent._prepare_turn({"turn_count": 0, "state_version": 0}, LEGAL)
            isolated_home = agent.session.workspace / ".codex-home"
            self.assertEqual(str(isolated_home), environment["CODEX_HOME"])
            self.assertNotIn("OPENAI_API_KEY", environment)
            self.assertNotIn("OPENAI_BASE_URL", environment)
            self.assertTrue((isolated_home / "auth.json").is_symlink())
            self.assertEqual(source_auth.resolve(), (isolated_home / "auth.json").resolve())
            self.assertFalse((isolated_home / "plugins").exists())
            codex_config = (agent.session.workspace / ".codex" / "config.toml").read_text(
                encoding="utf-8"
            )
            self.assertIn('forced_login_method = "chatgpt"', codex_config)
            self.assertIn('history.persistence = "none"', codex_config)
            self.assertIn('model_provider = "agentbga_chatgpt_https"', codex_config)
            self.assertIn('[model_providers.agentbga_chatgpt_https]', codex_config)
            self.assertIn('base_url = "https://chatgpt.com/backend-api/codex"', codex_config)
            self.assertIn("requires_openai_auth = true", codex_config)
            self.assertIn("supports_websockets = false", codex_config)
            self.assertIn("plugins = false", codex_config)
            self.assertIn("remote_plugin = false", codex_config)
            self.assertIn("shell_tool = false", codex_config)
            self.assertIn(f'env = {{ PYTHONPATH = {json.dumps(agent._pythonpath)} }}', codex_config)
            self.assertIn("required = true", codex_config)
            self.assertIn('default_tools_approval_mode = "approve"', codex_config)
            self.assertIn('forced_login_method="chatgpt"', agent._codex_config_args)
            self.assertIn('model_provider="agentbga_chatgpt_https"', agent._codex_config_args)
            self.assertIn(
                "model_providers.agentbga_chatgpt_https.supports_websockets=false",
                agent._codex_config_args,
            )
            self.assertIn("features.plugins=false", agent._codex_config_args)
            self.assertIn("features.remote_plugin=false", agent._codex_config_args)
            self.assertIn("features.shell_tool=false", agent._codex_config_args)
            self.assertIn("mcp_servers.agentbga.required=true", agent._codex_config_args)
            self.assertIn(
                'mcp_servers.agentbga.default_tools_approval_mode="approve"',
                agent._codex_config_args,
            )

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
            self.assertEqual("xhigh", trace["native_reasoning_effort"])
            self.assertIsNone(trace["error"])
            self.assertIn("seat 0", trace["prompt"]["user"])
            self.assertEqual("a-test", trace["prompt"]["legal_actions"][0]["id"])
            self.assertEqual("a-test", trace["submission"]["action_id"])
            self.assertIsNotNone(trace["action_latency_ms"])
            self.assertGreaterEqual(trace["process_latency_ms"], trace["action_latency_ms"])
            self.assertEqual(trace["process_latency_ms"], trace["latency_ms"])
            self.assertFalse(Path(trace["trace_file"]).is_absolute())
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
            agent.session.session_id = "existing-session"
            with mock.patch.object(agent, "_run", return_value=("", "boom", 1)):
                with self.assertRaisesRegex(AgentError, "exited 1"):
                    agent.choose({"turn_count": 0, "state_version": 0}, LEGAL)
            trace_path = Path(directory) / "_traces" / "err-match" / "seat-0" / "turn-0000.json"
            self.assertTrue(trace_path.is_file())
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            self.assertEqual("error", trace["status"])
            self.assertEqual("boom", trace["error"])
            self.assertIsNone(trace["submission"])
            self.assertTrue(trace["session_resumed"])
            self.assertEqual(0, trace["session_resume_count"])

    def test_harness_writes_trace_on_timeout(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", return_value="/bin/fake"):
            config = PlayerConfig.from_dict({
                "name": "Codex", "backend": "codex", "model": "gpt-test",
            }, 0)
            agent = HarnessAgent(config, "timeout-match", 0, runs_root=directory)
            with mock.patch.object(agent, "_run", side_effect=AgentError("codex harness timed out after 1s")):
                with self.assertRaisesRegex(AgentError, "timed out"):
                    agent.choose({"turn_count": 2, "state_version": 2}, LEGAL)
            trace_path = Path(directory) / "_traces" / "timeout-match" / "seat-0" / "turn-0002.json"
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            self.assertEqual("error", trace["status"])
            self.assertIn("timed out", trace["error"])
            self.assertGreaterEqual(trace["process_latency_ms"], 0)
            self.assertFalse(Path(trace["trace_file"]).is_absolute())


if __name__ == "__main__":
    unittest.main()
