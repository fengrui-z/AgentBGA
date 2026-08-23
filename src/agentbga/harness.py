"""External agent-harness controllers for supported agent CLIs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import selectors
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any, Callable

from .agents import AgentError, PlayerConfig, StreamSink
from .memory import memory_identity, stable_session_id


HarnessEventSink = Callable[[dict[str, Any]], None]


def _version_key(version: Any) -> int:
    try:
        return int(version)
    except (TypeError, ValueError):
        return 0


TURN_PROMPT = """You are seat {seat} in an AgentBGA {game} benchmark, at state version {version}.
Play by using the agentbga MCP tools. Do not inspect the parent project, database, or another seat.
Hidden opponent information is unavailable by design.

Call observe, then legal_actions, then commit exactly one choice with submit_action.
You must call submit_action exactly once for this decision step before finishing. A player turn may
contain later decision steps with the same active seat. You may keep strategic notes inside this seat
workspace for later decisions and turns. After submitting, briefly report completion.
"""


PI_EXTENSION = r'''import { Type } from "@sinclair/typebox";
import { readFile, writeFile, appendFile } from "node:fs/promises";

const contextPath = process.env.AGENTBGA_SEAT_CONTEXT!;
const submissionPath = process.env.AGENTBGA_SEAT_SUBMISSION!;
const auditPath = process.env.AGENTBGA_SEAT_AUDIT!;

async function context() { return JSON.parse(await readFile(contextPath, "utf8")); }
async function audit(tool: string, args: object, result: unknown) {
  await appendFile(auditPath, JSON.stringify({ tool, arguments: args, result, created_at: Date.now() / 1000 }) + "\n");
}
function result(value: unknown) { return { content: [{ type: "text", text: JSON.stringify(value) }], details: value }; }

export default function (pi: any) {
  pi.registerTool({ name: "observe", label: "Observe", description: "Read your seat-scoped board-game observation.",
    promptSnippet: "Read the current seat-scoped board state", parameters: Type.Object({}, { additionalProperties: false }),
    async execute() { const value = (await context()).observation; await audit("observe", {}, value); return result(value); } });
  pi.registerTool({ name: "legal_actions", label: "Legal actions", description: "List legal action IDs for this seat and state.",
    promptSnippet: "List the current legal board-game actions", parameters: Type.Object({}, { additionalProperties: false }),
    async execute() { const value = (await context()).legal_actions; await audit("legal_actions", {}, value); return result(value); } });
  pi.registerTool({ name: "submit_action", label: "Submit action", description: "Commit exactly one current legal action ID.",
    promptSnippet: "Commit exactly one legal action ID", promptGuidelines: ["Call submit_action exactly once before finishing the turn."],
    parameters: Type.Object({ action_id: Type.String() }, { additionalProperties: false }),
    async execute(_id: string, args: { action_id: string }) {
      const value = await context();
      if (!value.legal_actions.some((item: any) => item.id === args.action_id)) throw new Error("unknown or stale action ID");
      try { await readFile(submissionPath, "utf8"); throw new Error("an action has already been submitted for this turn"); } catch (error: any) {
        if (error?.code !== "ENOENT") throw error;
      }
      const accepted = { accepted: true, action_id: args.action_id, match_id: value.match_id, seat: value.seat, version: value.version };
      await writeFile(submissionPath, JSON.stringify(accepted)); await audit("submit_action", args, accepted); return result(accepted);
    } });
}
'''


@dataclass
class HarnessSession:
    match_id: str
    seat: int
    workspace: Path
    runtime: Path
    session_id: str | None = None
    scope: str | None = None
    scope_id: str | None = None
    resume_count: int | None = None


class HarnessAgent:
    """Run one persistent external CLI session for a tournament seat."""

    def __init__(self, config: PlayerConfig, match_id: str, seat: int, *,
                 event_sink: HarnessEventSink | None = None, timeout: float = 600,
                 runs_root: str | Path | None = None):
        self.config = config
        self.timeout = timeout
        self.event_sink = event_sink
        root = Path(runs_root) if runs_root else Path.cwd() / ".agentbga" / "runs"
        self.runs_root = root
        identity = memory_identity(root, config, match_id, seat)
        workspace = identity.workspace
        runtime = root / "_runtime" / match_id / f"seat-{seat}"
        trace_dir = root / "_traces" / match_id / f"seat-{seat}"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime.mkdir(parents=True, exist_ok=True)
        trace_dir.mkdir(parents=True, exist_ok=True)
        session_id = stable_session_id(identity) if config.backend == "dsh" else None
        self.session = HarnessSession(
            match_id, seat, workspace, runtime, session_id,
            identity.scope, identity.scope_id, 0,
        )
        self.participant_id = identity.participant_id
        self._session_owner_key = identity.owner_key
        self._dsh_home = workspace / ".dsh-home"
        self._dsh_state_path = self._dsh_home / "agentbga-session.json"
        self._dsh_metadata_path = runtime / "dsh-turn-metadata.json"
        self._dsh_turn_metadata: dict[str, Any] = {}
        self._session_state_path = workspace / "agentbga-harness-session.json"
        self.trace_dir = trace_dir
        self._trace_steps: list[dict[str, Any]] = []
        self.binary = shutil.which(config.backend)
        if not self.binary:
            raise AgentError(f"harness executable not found: {config.backend}")
        self._load_harness_session_state()

    def _emit(self, event_type: str, **payload: Any) -> None:
        if self.event_sink:
            self.event_sink({
                "type": event_type, "harness": self.config.backend,
                "seat": self.session.seat, "player": self.config.name, **payload,
            })

    def _native_reasoning_effort(self) -> str:
        """Translate the benchmark effort label to a harness-native value."""
        requested = self.config.reasoning_effort or "max"
        if self.config.backend in {"codex", "pi"} and requested == "max":
            return "xhigh"
        if self.config.backend == "claude" and requested == "xhigh":
            return "max"
        return requested

    def _display_command(self, command: list[str]) -> list[str]:
        """Redact secrets and user-specific absolute paths from persisted events."""
        replacements = (
            (str(self.session.runtime), "[RUNTIME]"),
            (str(self.session.workspace), "."),
            (str(Path.home()), "$HOME"),
        )
        safe: list[str] = []
        for part in command:
            value = self._redact_text(part)
            for prefix, replacement in replacements:
                value = value.replace(prefix, replacement)
            safe.append(value)
        return safe

    def _command(self, prompt: str) -> list[str]:
        model = self.config.model or ""
        requested_effort = self.config.reasoning_effort or "max"
        reasoning_effort = self._native_reasoning_effort()
        reasoning_enabled = requested_effort != "none"
        if self.config.backend == "claude":
            allowed_tools = [
                "mcp__agentbga__observe",
                "mcp__agentbga__legal_actions",
                "mcp__agentbga__submit_action",
            ]
            command = [self.binary, "--print", "--output-format", "stream-json", "--verbose",
                       "--include-partial-messages", "--bare", "--strict-mcp-config",
                       "--mcp-config", "claude-mcp.json",
                       "--model", model]
            if reasoning_enabled:
                command.extend(["--effort", reasoning_effort])
            command.extend([
                "--permission-mode", "dontAsk", "--allowedTools", *allowed_tools,
                "--tools", "",
            ])
            if self.session.session_id:
                command.extend(["--resume", self.session.session_id])
            # --tools accepts a variable number of values. Without the explicit
            # option terminator Commander consumes the turn prompt as another tool.
            return [*command, "--", prompt]
        if self.config.backend == "pi":
            command = [self.binary, "--mode", "json", "--provider", "agentbga",
                       "--model", model, "--thinking",
                       "off" if not reasoning_enabled else "xhigh" if reasoning_effort == "max" else reasoning_effort,
                       "--no-builtin-tools", "--no-context-files",
                       "--no-skills", "--no-prompt-templates", "--no-extensions",
                       "--extension", "agentbga-tools.ts",
                       "--session-dir", ".pi-sessions"]
            if self.session.session_id:
                command.extend(["--session", self.session.session_id])
            return [*command, prompt]
        if self.config.backend == "codex":
            overrides = getattr(self, "_codex_config_args", [])
            runtime_dir = os.path.relpath(self.session.runtime, self.session.workspace)
            common = ["--model", model, "--json", "--sandbox", "workspace-write",
                      "--add-dir", runtime_dir, "--skip-git-repo-check",
                      "--ignore-user-config", "--ignore-rules", *overrides]
            if self.session.session_id:
                return [self.binary, "exec", "--add-dir", runtime_dir,
                        "resume", "--model", model, "--json",
                        "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
                        *overrides, self.session.session_id, prompt]
            return [self.binary, "exec", *common, "--cd", ".", prompt]
        if self.config.backend == "opencode":
            selected_model = model if "/" in model else f"agentbga/{model}"
            command = [self.binary, "run", "--pure", "--format", "json", "--model", selected_model,
                       "--variant", reasoning_effort, "--dir", "."]
            # OpenCode's CLI flag controls whether reasoning blocks are shown;
            # provider-specific request options are configured separately below.
            if reasoning_enabled:
                command.append("--thinking")
            if self.session.session_id:
                command.extend(["--session", self.session.session_id])
            return [*command, prompt]
        if self.config.backend == "dsh":
            # The process is still one-shot, but the overlay replaces DSh's
            # random-session runner with AgentBGA's create-or-resume driver.
            command = [self.binary, "--profile", "headless", "--patch", "dsh-patch.yml"]
            return [*command, prompt]
        if self.config.backend == "hermes":
            command = [
                self.binary, "chat", "--quiet", "--model", model,
                "--ignore-rules", "--source", "tool",
            ]
            if self.session.session_id:
                command.extend(["--resume", self.session.session_id])
            return [*command, "--query", prompt]
        raise AgentError(f"unsupported harness: {self.config.backend}")

    def _redact_text(self, value: str) -> str:
        key = self.config.api_key or os.environ.get(self.config.api_key_env or "", "")
        return value.replace(key, "[REDACTED]") if key else value

    def _provider_api_key_env(self) -> str:
        """Return the credential variable understood by the selected harness/provider."""
        configured = self.config.api_key_env or ""
        if configured not in {"AGENTBGA_API_KEY", ""}:
            return configured
        endpoint = (self.config.base_url or "").lower()
        if self.config.backend == "pi":
            if "anthropic" in endpoint:
                return "ANTHROPIC_API_KEY"
            if "googleapis.com" in endpoint:
                return "GEMINI_API_KEY"
            if "deepseek" in endpoint:
                return "DEEPSEEK_API_KEY"
            return "OPENAI_API_KEY"
        return configured

    def _environment(self) -> dict[str, str]:
        source_env = dict(os.environ)
        secret_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
        env = {
            name: value for name, value in source_env.items()
            if not any(marker in name.upper() for marker in secret_markers)
        }
        key_name = self.config.api_key_env or ""
        key = self.config.api_key or source_env.get(key_name)
        if key_name and key:
            env[key_name] = key
        if self.config.backend == "codex":
            codex_home = self.session.workspace / ".codex-home"
            codex_home.mkdir(mode=0o700, exist_ok=True)
            env["CODEX_HOME"] = str(codex_home)
            if self.config.auth_mode == "subscription":
                # Keep caches, plugins, skills, and runtime state seat-local. Only
                # bridge the file-backed ChatGPT login; keyring-backed credentials
                # remain discoverable by the CLI without a file link.
                source_home = Path(source_env.get("CODEX_HOME") or Path.home() / ".codex")
                source_auth = source_home / "auth.json"
                auth_link = codex_home / "auth.json"
                if auth_link.is_symlink() and auth_link.resolve() != source_auth.resolve():
                    auth_link.unlink()
                elif auth_link.exists() and not auth_link.is_symlink():
                    raise AgentError(
                        f"refusing to replace non-symlink Codex credential file: {auth_link}"
                    )
                if source_auth.is_file() and not auth_link.exists():
                    auth_link.symlink_to(source_auth)
                env.pop("OPENAI_API_KEY", None)
                env.pop("OPENAI_BASE_URL", None)
            else:
                if key:
                    env[self.config.api_key_env or "OPENAI_API_KEY"] = key
                if self.config.base_url:
                    env["OPENAI_BASE_URL"] = self.config.base_url
        elif self.config.backend == "opencode":
            for variable, dirname in (
                ("XDG_DATA_HOME", ".opencode-data"),
                ("XDG_CONFIG_HOME", ".opencode-config"),
                ("XDG_CACHE_HOME", ".opencode-cache"),
                ("XDG_STATE_HOME", ".opencode-state"),
            ):
                target = self.session.workspace / dirname
                target.mkdir(exist_ok=True)
                env[variable] = str(target)
            if key:
                env[self.config.api_key_env or "DEEPSEEK_API_KEY"] = key
        elif self.config.backend == "claude":
            claude_config = self.session.workspace / ".claude-config"
            claude_config.mkdir(exist_ok=True)
            env["CLAUDE_CONFIG_DIR"] = str(claude_config)
            if key:
                if self.config.base_url and "api.anthropic.com" not in self.config.base_url:
                    if key_name:
                        env.pop(key_name, None)
                    env.pop("ANTHROPIC_API_KEY", None)
                    env["ANTHROPIC_AUTH_TOKEN"] = key
                else:
                    if key_name and key_name != "ANTHROPIC_API_KEY":
                        env.pop(key_name, None)
                    env["ANTHROPIC_API_KEY"] = key
            if self.config.base_url:
                env["ANTHROPIC_BASE_URL"] = self.config.base_url
        elif self.config.backend == "pi":
            pi_home = self.session.workspace / ".pi-home"
            pi_home.mkdir(exist_ok=True)
            env["PI_CODING_AGENT_DIR"] = str(pi_home)
            env["PI_SKIP_VERSION_CHECK"] = "1"
            env["PI_TELEMETRY"] = "0"
            pi_key_env = self._provider_api_key_env()
            env["AGENTBGA_API_KEY"] = key or ""
            if pi_key_env and key:
                env[pi_key_env] = key
            env["AGENTBGA_SEAT_CONTEXT"] = str(self.session.runtime / "turn-context.json")
            env["AGENTBGA_SEAT_SUBMISSION"] = str(self.session.runtime / "submission.json")
            env["AGENTBGA_SEAT_AUDIT"] = str(self.session.runtime / "tool-events.jsonl")
        elif self.config.backend == "dsh":
            self._dsh_home.mkdir(parents=True, exist_ok=True)
            env["DSH_HOME"] = str(self._dsh_home)
            # workspace-write confines file writes to the seat cwd; the patch
            # forces approval policy to "never" so headless runs never block.
            env["DSH_PERMISSION_MODE"] = "workspace-write"
            env["DSH_TELEMETRY_MODE"] = "DISABLED"
            if key:
                env["DEEPSEEK_API_KEY"] = key
            if self.config.base_url:
                env["DEEPSEEK_BASE_URL"] = self.config.base_url
        elif self.config.backend == "hermes":
            hermes_home = self.session.workspace / ".hermes-home"
            hermes_home.mkdir(exist_ok=True)
            env["HERMES_HOME"] = str(hermes_home)
            env["HERMES_IGNORE_RULES"] = "1"
            if key:
                # Hermes' custom OpenAI-compatible provider reads this canonical
                # variable even when AgentBGA received the key under another name.
                env["OPENAI_API_KEY"] = key
            if self.config.base_url:
                env["OPENAI_BASE_URL"] = self.config.base_url
        if hasattr(self, "_pythonpath"):
            env["PYTHONPATH"] = self._pythonpath
        return env

    def _prepare_turn(
        self, observation: dict[str, Any], legal: list[dict[str, Any]],
    ) -> Path:
        context_path = self.session.runtime / "turn-context.json"
        submission_path = self.session.runtime / "submission.json"
        audit_path = self.session.runtime / "tool-events.jsonl"
        submission_path.unlink(missing_ok=True)
        audit_path.unlink(missing_ok=True)
        self._dsh_metadata_path.unlink(missing_ok=True)
        self._dsh_turn_metadata = {}
        context = {
            "schema_version": "agentbga.seat-context.v1",
            "match_id": self.session.match_id,
            "seat": self.session.seat,
            "version": observation.get("state_version", observation.get("turn_count")),
            "observation": observation,
            "legal_actions": [{"id": item["id"], **item["action"]} for item in legal],
        }
        context_path.write_text(
            json.dumps(context, ensure_ascii=False, separators=(",", ":")), encoding="utf-8",
        )
        package_root = Path(__file__).resolve().parents[1]
        inherited = os.environ.get("PYTHONPATH")
        self._pythonpath = str(package_root) + (os.pathsep + inherited if inherited else "")
        relative_context = os.path.relpath(context_path, self.session.workspace)
        mcp_command = [
            sys.executable, "-m", "agentbga.seat_mcp", "--context", relative_context,
            "--notes-root", ".",
        ]
        requested_effort = self.config.reasoning_effort or "max"
        reasoning_effort = self._native_reasoning_effort()
        reasoning_enabled = requested_effort != "none"
        claude_mcp = {"mcpServers": {"agentbga": {
            "type": "stdio", "command": mcp_command[0], "args": mcp_command[1:],
        }}}
        (self.session.workspace / "claude-mcp.json").write_text(
            json.dumps(claude_mcp, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        (self.session.workspace / "agentbga-tools.ts").write_text(PI_EXTENSION, encoding="utf-8")
        pi_dir = self.session.workspace / ".pi-home"
        pi_dir.mkdir(exist_ok=True)
        pi_api_key_env = self._provider_api_key_env()
        pi_api = self.config.wire_api or "openai-completions"
        pi_model: dict[str, Any] = {
            "id": self.config.model,
            "reasoning": reasoning_enabled,
            "thinkingLevelMap": {
                "minimal": None, "low": None, "medium": None,
                "high": "high", "xhigh": "xhigh",
            },
        }
        if pi_api == "openai-completions" and self.config.base_url != "https://api.openai.com/v1":
            pi_model["compat"] = {
                "supportsStore": False,
                "supportsDeveloperRole": False,
                "supportsReasoningEffort": False,
                "supportsStrictMode": False,
                "maxTokensField": "max_tokens",
            }
        pi_models = {"providers": {"agentbga": {
            "baseUrl": self.config.base_url, "api": pi_api,
            "apiKey": f"${pi_api_key_env}", "models": [pi_model],
        }}}
        (pi_dir / "models.json").write_text(
            json.dumps(pi_models, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        codex_dir = self.session.workspace / ".codex"
        codex_dir.mkdir(exist_ok=True)
        escaped_args = ", ".join(json.dumps(part) for part in mcp_command[1:])
        provider = ""
        provider_args: list[str] = []
        if self.config.auth_mode == "subscription":
            # The built-in ChatGPT provider prefers WebSockets and only falls
            # back to HTTPS after exhausting its stream retries. Some networks
            # allow the HTTPS endpoint but silently drop the WebSocket stream,
            # adding more than a minute to every move. A named provider can
            # reuse Codex's ChatGPT login while selecting HTTPS explicitly.
            provider = (
                "model_provider = \"agentbga_chatgpt_https\"\n"
                "[model_providers.agentbga_chatgpt_https]\n"
                "name = \"AgentBGA ChatGPT HTTPS\"\n"
                "base_url = \"https://chatgpt.com/backend-api/codex\"\n"
                "wire_api = \"responses\"\n"
                "requires_openai_auth = true\n"
                "supports_websockets = false\n"
            )
            provider_args = [
                "--config", "model_provider=\"agentbga_chatgpt_https\"",
                "--config", "model_providers.agentbga_chatgpt_https.name=\"AgentBGA ChatGPT HTTPS\"",
                "--config", "model_providers.agentbga_chatgpt_https.base_url=\"https://chatgpt.com/backend-api/codex\"",
                "--config", "model_providers.agentbga_chatgpt_https.wire_api=\"responses\"",
                "--config", "model_providers.agentbga_chatgpt_https.requires_openai_auth=true",
                "--config", "model_providers.agentbga_chatgpt_https.supports_websockets=false",
            ]
        elif self.config.base_url and self.config.base_url.rstrip("/") != "https://api.openai.com/v1":
            provider = (
                "model_provider = \"agentbga\"\n"
                "[model_providers.agentbga]\n"
                "name = \"AgentBGA seat provider\"\n"
                f"base_url = {json.dumps(self.config.base_url.rstrip('/'))}\n"
                f"env_key = {json.dumps(self.config.api_key_env or 'OPENAI_API_KEY')}\n"
                "wire_api = \"responses\"\n"
                "requires_openai_auth = false\n"
            )
            provider_args = [
                "--config", "model_provider=\"agentbga\"",
                "--config", "model_providers.agentbga.name=\"AgentBGA seat provider\"",
                "--config", f"model_providers.agentbga.base_url={json.dumps(self.config.base_url.rstrip('/'))}",
                "--config", f"model_providers.agentbga.env_key={json.dumps(self.config.api_key_env or 'OPENAI_API_KEY')}",
                "--config", "model_providers.agentbga.wire_api=\"responses\"",
                "--config", "model_providers.agentbga.requires_openai_auth=false",
            ]
        codex_reasoning = (
            f"model_reasoning_effort = {json.dumps(reasoning_effort)}\n"
            if reasoning_enabled else ""
        )
        codex_config = (
            "approval_policy = \"never\"\n"
            "sandbox_mode = \"workspace-write\"\n"
            "web_search = \"disabled\"\n"
            + ("forced_login_method = \"chatgpt\"\n" if self.config.auth_mode == "subscription" else "")
            + ("history.persistence = \"none\"\n" if self.config.auth_mode == "subscription" else "")
            + ("memories.use_memories = false\n" if self.config.auth_mode == "subscription" else "")
            + codex_reasoning
            + provider
            + (
                "[features]\n"
                "plugins = false\n"
                "remote_plugin = false\n"
                "shell_tool = false\n"
                "skill_mcp_dependency_install = false\n"
                if self.config.auth_mode == "subscription" else ""
            )
            + "[mcp_servers.agentbga]\n"
            f"command = {json.dumps(mcp_command[0])}\n"
            f"args = [{escaped_args}]\n"
            f"env = {{ PYTHONPATH = {json.dumps(self._pythonpath)} }}\n"
            "required = true\n"
            "startup_timeout_sec = 30\n"
            "default_tools_approval_mode = \"approve\"\n"
        )
        (codex_dir / "config.toml").write_text(codex_config, encoding="utf-8")
        provider_id, separator, model_id = (self.config.model or "").partition("/")
        if not separator:
            provider_id, model_id = "agentbga", provider_id
        opencode_config: dict[str, Any] = {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {"agentbga": {"type": "local", "command": mcp_command, "enabled": True}},
            "permission": {
                "*": "deny", "read": "allow", "edit": "allow",
                "agentbga_*": "allow",
            },
        }
        if provider_id and model_id:
            variant: dict[str, Any] = {}
            if reasoning_enabled:
                variant = {"reasoningEffort": requested_effort}
                if "deepseek" in (self.config.base_url or "").lower():
                    variant["thinking"] = {"type": "enabled"}
            elif "deepseek" in (self.config.base_url or "").lower():
                variant["thinking"] = {"type": "disabled"}
            opencode_config["provider"] = {
                provider_id: {
                    "npm": "@ai-sdk/openai" if self.config.wire_api == "responses" else "@ai-sdk/openai-compatible",
                    "name": "AgentBGA seat provider",
                    "options": {
                        "baseURL": self.config.base_url,
                        "apiKey": f"{{env:{self.config.api_key_env or 'DEEPSEEK_API_KEY'}}}",
                    },
                    "models": {model_id: {
                        "name": model_id,
                        "variants": {requested_effort: variant},
                    }},
                },
            }
        (self.session.workspace / "opencode.json").write_text(
            json.dumps(opencode_config, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        dsh_mcp_args = ", ".join(json.dumps(part) for part in mcp_command[1:])
        dsh_runner = Path(__file__).with_name("dsh_resumable_runner.mjs").resolve().as_uri()
        dsh_owner_key = self._session_owner_key
        dsh_api_key_env = self.config.api_key_env or "OPENAI_API_KEY"
        dsh_base_url = (self.config.base_url or "https://api.deepseek.com").rstrip("/")
        is_deepseek_native = "deepseek.com" in dsh_base_url.lower()
        if is_deepseek_native:
            llm_plugin_block = (
                "- id: llm-deepseek\n"
                "  config:\n"
                f"    reasoningEffort: {requested_effort}\n"
                f"    thinking: {'enabled' if reasoning_enabled else 'disabled'}\n"
            )
        else:
            # Non-DeepSeek endpoint: use OpenAI-compatible adapter via dsh-llm-pi-ai.
            llm_plugin_block = (
                "- id: llm-pi-ai\n"
                "  config:\n"
                f"    baseURL: {json.dumps(dsh_base_url)}\n"
                f"    apiKeyEnv: {json.dumps(dsh_api_key_env)}\n"
            )
        dsh_patch = (
            "- id: agent-default-model\n"
            "  config:\n"
            f"    provider: {'deepseek-official' if is_deepseek_native else 'pi-ai'}\n"
            f"    model: {json.dumps(self.config.model or '')}\n"
            + llm_plugin_block
            + "- id: headless-runner\n"
            "  disabled: true\n"
            + "- id: permission\n"
            "  config:\n"
            "    defaultPreset: workspace-write\n"
            "    presets:\n"
            "      read-only:\n"
            "        sandbox: read-only\n"
            "        approval: ask\n"
            "      workspace-write:\n"
            "        sandbox: workspace-write\n"
            "        approval: never\n"
            "      danger-full-access:\n"
            "        sandbox: danger-full-access\n"
            "        approval: never\n"
            "- insert:\n"
            "    - id: agentbga-resumable-runner\n"
            f"      name: {json.dumps(dsh_runner)}\n"
            "      inject: [headlessStartup]\n"
            "      config:\n"
            "        task: !!js ctx.headlessStartup.task\n"
            f"        sessionId: {json.dumps(self.session.session_id)}\n"
            f"        ownerKey: {json.dumps(dsh_owner_key, ensure_ascii=False)}\n"
            f"        statePath: {json.dumps(str(self._dsh_state_path))}\n"
            f"        metadataPath: {json.dumps(str(self._dsh_metadata_path))}\n"
            "    - id: mcp-agentbga\n"
            "      name: '@deepseek-ai/dsh-mcp-client'\n"
            "      config:\n"
            "        serverName: agentbga\n"
            "        transport: stdio\n"
            f"        command: {json.dumps(mcp_command[0])}\n"
            f"        args: [{dsh_mcp_args}]\n"
            "        env:\n"
            f"          PYTHONPATH: {json.dumps(self._pythonpath)}\n"
        )
        (self.session.workspace / "dsh-patch.yml").write_text(dsh_patch, encoding="utf-8")
        hermes_home = self.session.workspace / ".hermes-home"
        hermes_home.mkdir(exist_ok=True)
        hermes_api_mode = ""
        if self.config.wire_api:
            api_mode = "codex_responses" if self.config.wire_api == "responses" else "chat_completions"
            hermes_api_mode = f"  api_mode: {json.dumps(api_mode)}\n"
        hermes_config = (
            "model:\n"
            f"  default: {json.dumps(self.config.model or '')}\n"
            "  provider: custom\n"
            f"  base_url: {json.dumps((self.config.base_url or '').rstrip('/'))}\n"
            + hermes_api_mode
            + "agent:\n"
            f"  reasoning_effort: {json.dumps(requested_effort)}\n"
            "  max_turns: 20\n"
            "display:\n"
            "  streaming: false\n"
            "  turn_summary: false\n"
            "platform_toolsets:\n"
            "  cli:\n"
            "    - agentbga\n"
            "mcp_servers:\n"
            "  agentbga:\n"
            "    enabled: true\n"
            f"    command: {json.dumps(mcp_command[0])}\n"
            f"    args: [{escaped_args}]\n"
            "    env:\n"
            f"      PYTHONPATH: {json.dumps(self._pythonpath)}\n"
            f"    timeout: {max(1, int(self.timeout))}\n"
            "    connect_timeout: 60\n"
        )
        (hermes_home / "config.yaml").write_text(hermes_config, encoding="utf-8")
        self._codex_config_args = [
            "--config", "approval_policy=\"never\"",
            "--config", "sandbox_mode=\"workspace-write\"",
            "--config", "web_search=\"disabled\"",
            "--config", f"mcp_servers.agentbga.command={json.dumps(mcp_command[0])}",
            "--config", f"mcp_servers.agentbga.args=[{escaped_args}]",
            "--config", f"mcp_servers.agentbga.env={{PYTHONPATH={json.dumps(self._pythonpath)}}}",
            "--config", "mcp_servers.agentbga.required=true",
            "--config", "mcp_servers.agentbga.startup_timeout_sec=30",
            "--config", 'mcp_servers.agentbga.default_tools_approval_mode="approve"',
        ]
        if self.config.auth_mode == "subscription":
            self._codex_config_args.extend([
                "--config", "forced_login_method=\"chatgpt\"",
                "--config", "history.persistence=\"none\"",
                "--config", "memories.use_memories=false",
                "--config", "features.plugins=false",
                "--config", "features.remote_plugin=false",
                "--config", "features.shell_tool=false",
                "--config", "features.skill_mcp_dependency_install=false",
            ])
        if reasoning_enabled:
            self._codex_config_args.extend([
                "--config", f"model_reasoning_effort={json.dumps(reasoning_effort)}",
            ])
        self._codex_config_args.extend(provider_args)
        return submission_path

    def _recover_hermes_session_id(self) -> None:
        """Read the ID created by quiet Hermes CLI mode from its isolated state DB."""
        if self.config.backend != "hermes" or self.session.session_id:
            return
        database = self.session.workspace / ".hermes-home" / "state.db"
        if not database.is_file():
            return
        try:
            with sqlite3.connect(database) as connection:
                row = connection.execute(
                    "SELECT id FROM sessions WHERE source = ? "
                    "ORDER BY started_at DESC, id DESC LIMIT 1",
                    ("tool",),
                ).fetchone()
        except sqlite3.Error:
            return
        if row and isinstance(row[0], str) and row[0]:
            self.session.session_id = row[0]

    def _load_harness_session_state(self) -> None:
        if self.config.backend == "dsh" or not self._session_state_path.is_file():
            return
        try:
            state = json.loads(self._session_state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if state.get("owner_key") != self._session_owner_key:
            raise AgentError("harness session state belongs to a different participant")
        session_id = state.get("session_id")
        if isinstance(session_id, str) and session_id:
            self.session.session_id = session_id
        resume_count = state.get("resume_count")
        if isinstance(resume_count, int) and resume_count >= 0:
            self.session.resume_count = resume_count

    def _save_harness_session_state(self, *, resumed: bool = False) -> None:
        if self.config.backend == "dsh" or not self.session.session_id:
            return
        previous = self.session.resume_count or 0
        # Count a resume only when this turn was actually launched with a
        # native session ID and the harness process completed successfully.
        # File existence is not evidence of a resume: a stale or newly written
        # state file may exist even when no restore path ran.
        self.session.resume_count = previous + int(resumed)
        temporary = self._session_state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "schema_version": "agentbga.harness-session.v1",
            "owner_key": self._session_owner_key,
            "session_id": self.session.session_id,
            "resume_count": self.session.resume_count,
        }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(self._session_state_path)

    def _recover_dsh_turn_metadata(self) -> None:
        """Load the resumable runner's authoritative per-invocation metadata."""
        if self.config.backend != "dsh" or not self._dsh_metadata_path.is_file():
            return
        try:
            metadata = json.loads(self._dsh_metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(metadata, dict):
            return
        session_id = metadata.get("sessionId")
        if session_id and session_id != self.session.session_id:
            raise AgentError("DSh runner returned metadata for a different session")
        self._dsh_turn_metadata = metadata
        resume_count = metadata.get("resumeCount")
        if isinstance(resume_count, int) and resume_count >= 0:
            self.session.resume_count = resume_count

    def _emit_tool_audit(self) -> None:
        path = self.session.runtime / "tool-events.jsonl"
        if not path.is_file():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._emit("harness_tool_call", tool=row.get("tool"), arguments=row.get("arguments") or {})
            self._emit("harness_tool_result", tool=row.get("tool"), result=row.get("result"))

    @staticmethod
    def _event_text(payload: dict[str, Any]) -> str:
        assistant_event = payload.get("assistantMessageEvent")
        if isinstance(assistant_event, dict) and assistant_event.get("type") in {
            "text_delta", "thinking_delta",
        }:
            return str(assistant_event.get("delta") or "")
        stream_event = payload.get("event")
        if isinstance(stream_event, dict):
            delta = stream_event.get("delta")
            if isinstance(delta, dict):
                for key in ("text", "thinking"):
                    if isinstance(delta.get(key), str):
                        return delta[key]
        item = payload.get("item") or payload.get("part") or payload
        if not isinstance(item, dict):
            return ""
        for key in ("text", "content", "output", "message"):
            value = item.get(key)
            if isinstance(value, str):
                return value
        return ""

    @staticmethod
    def _event_session_id(payload: dict[str, Any]) -> str | None:
        if payload.get("type") == "session" and isinstance(payload.get("id"), str):
            return payload["id"]
        for key in ("thread_id", "session_id", "sessionID"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        session = payload.get("session")
        if isinstance(session, dict):
            value = session.get("id")
            if isinstance(value, str):
                return value
        return None

    @staticmethod
    def _tool_details(payload: dict[str, Any]) -> tuple[str, Any] | None:
        if payload.get("type") == "tool_execution_start":
            return str(payload.get("toolName") or "tool"), payload.get("args") or {}
        item = payload.get("item") or payload.get("part") or payload
        if not isinstance(item, dict):
            return None
        item_type = str(item.get("type") or payload.get("type") or "")
        if "tool" not in item_type.lower() and not item.get("tool") and not item.get("name"):
            return None
        name = item.get("tool") or item.get("name") or item.get("tool_name") or item_type
        arguments = item.get("arguments") or item.get("input") or item.get("args") or {}
        return str(name), arguments

    def _run(self, command: list[str]) -> tuple[str, str, int]:
        safe_command = self._display_command(command)
        self._emit("harness_started", command=safe_command, session_id=self.session.session_id)
        started = time.monotonic()
        process = subprocess.Popen(
            command, cwd=self.session.workspace, env=self._environment(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
        )
        selector = selectors.DefaultSelector()
        assert process.stdout is not None and process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        output: list[str] = []
        errors: list[str] = []
        try:
            while selector.get_map():
                remaining = self.timeout - (time.monotonic() - started)
                if remaining <= 0:
                    process.kill()
                    raise AgentError(f"{self.config.backend} harness timed out after {self.timeout:g}s")
                for key, _ in selector.select(min(0.25, remaining)):
                    line = key.fileobj.readline()
                    if line == "":
                        selector.unregister(key.fileobj)
                        continue
                    line = line.rstrip("\r\n")
                    if key.data == "stderr":
                        line = self._redact_text(line)
                        errors.append(line)
                        self._emit("harness_output", channel="stderr", delta=line + "\n")
                        self._trace_steps.append({"role": "stderr", "text": line})
                        continue
                    line = self._redact_text(line)
                    output.append(line)
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        self._emit("harness_output", channel="content", delta=line + "\n")
                        self._trace_steps.append({"role": "assistant", "channel": "content", "text": line})
                        continue
                    session_id = self._event_session_id(payload)
                    if session_id:
                        self.session.session_id = session_id
                    tool = self._tool_details(payload)
                    if tool:
                        self._emit("harness_tool_call", tool=tool[0], arguments=tool[1], raw_type=payload.get("type"))
                        self._trace_steps.append({
                            "role": "tool_call", "tool": tool[0],
                            "arguments": tool[1], "result": None,
                        })
                    text = self._event_text(payload)
                    if text:
                        assistant_event = payload.get("assistantMessageEvent") or {}
                        stream_delta = ((payload.get("event") or {}).get("delta") or {})
                        channel = "reasoning" if (
                            assistant_event.get("type") == "thinking_delta" or "thinking" in stream_delta
                        ) else "content"
                        self._emit("harness_output", channel=channel, delta=text)
                        self._trace_steps.append({"role": "assistant", "channel": channel, "text": text})
            returncode = process.wait(timeout=2)
        finally:
            selector.close()
            if process.poll() is None:
                process.kill()
                process.wait()
        return "\n".join(output), "\n".join(errors), returncode

    def _write_trace(
        self, *, prompt: str, observation: dict[str, Any],
        legal: list[dict[str, Any]], version: Any,
        status: str, error: str | None,
        action_latency_ms: float | None, process_latency_ms: float,
        trace_kind: str = "turn", session_resumed: bool | None = None,
    ) -> None:
        """Persist one ordered per-turn trace: prompt → assistant/tool steps → submission."""
        context_path = self.session.runtime / "turn-context.json"
        audit_path = self.session.runtime / "tool-events.jsonl"
        submission_path = self.session.runtime / "submission.json"
        observation_snapshot = observation
        legal_snapshot = [{"id": item["id"], **item["action"]} for item in legal]
        executed: list[dict[str, Any]] = []
        if audit_path.is_file():
            for line in audit_path.read_text(encoding="utf-8").splitlines():
                try:
                    executed.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        steps = list(self._trace_steps)
        # Attach authoritative tool results from the audit log by matching tool
        # name in encounter order; stream-parsed tool calls carry no result.
        pending_by_tool: dict[str, list[dict[str, Any]]] = {}
        for step in steps:
            if step.get("role") == "tool_call":
                pending_by_tool.setdefault(step["tool"], []).append(step)
        for row in executed:
            tool_name = row.get("tool")
            queue = pending_by_tool.get(tool_name)
            if queue:
                queue.pop(0)["result"] = row.get("result")
            else:
                # A tool ran without a stream sighting (e.g. pi native tools);
                # append it preserving execution order at the end.
                steps.append({
                    "role": "tool_call", "tool": tool_name,
                    "arguments": row.get("arguments") or {}, "result": row.get("result"),
                    "created_at": row.get("created_at"),
                })
        submission = None
        if submission_path.is_file():
            try:
                submission = json.loads(submission_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                submission = None
        trace = {
            "schema_version": "agentbga.turn-trace.v1",
            "match_id": self.session.match_id,
            "seat": self.session.seat,
            "player": self.config.name,
            "backend": self.config.backend,
            "model": self.config.model,
            "reasoning_effort": self.config.reasoning_effort,
            "native_reasoning_effort": self._native_reasoning_effort(),
            "version": version,
            "session_id": self.session.session_id,
            "session_scope": self.session.scope,
            "session_scope_id": self.session.scope_id,
            "participant_id": self.participant_id,
            "session_resumed": self._dsh_turn_metadata.get("resumed", session_resumed),
            "session_resume_count": self.session.resume_count,
            "compaction_events": self._dsh_turn_metadata.get("compactionEvents", []),
            "compaction_event_count_total": self._dsh_turn_metadata.get(
                "compactionEventCountTotal"
            ),
            # Keep latency_ms as a compatibility alias for the total process
            # latency while exposing time-to-action separately.
            "latency_ms": process_latency_ms,
            "action_latency_ms": action_latency_ms,
            "process_latency_ms": process_latency_ms,
            "status": status,
            "error": error,
            "prompt": {
                "system": None,
                "user": prompt,
                "observation": observation_snapshot,
                "legal_actions": legal_snapshot,
            },
            "steps": steps,
            "submission": submission,
            "trace_file": str(
                (self.trace_dir / f"{trace_kind}-{_version_key(version):04d}.json")
                .relative_to(self.trace_dir.parents[2])
            ),
        }
        target = self.trace_dir / f"{trace_kind}-{_version_key(version):04d}.json"
        target.write_text(
            json.dumps(trace, ensure_ascii=False, separators=(",", ":")), encoding="utf-8",
        )

    @staticmethod
    def _action_latency_ms(submission_path: Path, started_wall: float) -> float | None:
        """Measure time to accepted submit_action independently of CLI shutdown."""
        if not submission_path.is_file():
            return None
        audit_path = submission_path.with_name("tool-events.jsonl")
        if audit_path.is_file():
            for line in audit_path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("tool") == "submit_action" and isinstance(row.get("created_at"), (int, float)):
                    return round(max(0.0, row["created_at"] - started_wall) * 1000, 3)
        return round(max(0.0, submission_path.stat().st_mtime - started_wall) * 1000, 3)

    def choose(
        self, observation: dict[str, Any], legal: list[dict[str, Any]],
        on_stream: StreamSink | None = None,
    ) -> tuple[str, dict[str, Any]]:
        submission_path = self._prepare_turn(observation, legal)
        prompt = TURN_PROMPT.format(
            seat=self.session.seat,
            version=observation.get("state_version", observation.get("turn_count")),
            game=observation.get("game", "board-game"),
        )
        version = observation.get("state_version", observation.get("turn_count"))
        started = time.monotonic()
        started_wall = time.time()
        turn_resumed = bool(self.session.session_id)
        self._trace_steps = []
        try:
            raw, stderr, returncode = self._run(self._command(prompt))
        except AgentError as error:
            self._recover_hermes_session_id()
            self._recover_dsh_turn_metadata()
            self._save_harness_session_state()
            process_latency_ms = round((time.monotonic() - started) * 1000, 3)
            action_latency_ms = self._action_latency_ms(submission_path, started_wall)
            self._emit_tool_audit()
            detail = self._redact_text(str(error))
            self._emit("harness_error", error=detail)
            self._write_trace(
                prompt=prompt, observation=observation, legal=legal, version=version,
                status="error", error=detail,
                action_latency_ms=action_latency_ms, process_latency_ms=process_latency_ms,
                session_resumed=turn_resumed,
            )
            raise
        self._recover_hermes_session_id()
        self._recover_dsh_turn_metadata()
        process_latency_ms = round((time.monotonic() - started) * 1000, 3)
        action_latency_ms = self._action_latency_ms(submission_path, started_wall)
        self._emit_tool_audit()
        if returncode != 0:
            self._save_harness_session_state()
            detail = stderr[-1000:] or raw[-1000:]
            detail = self._redact_text(detail)
            self._emit("harness_error", error=detail, exit_code=returncode)
            self._write_trace(
                prompt=prompt, observation=observation, legal=legal, version=version,
                status="error", error=detail,
                action_latency_ms=action_latency_ms, process_latency_ms=process_latency_ms,
                session_resumed=turn_resumed,
            )
            raise AgentError(f"{self.config.backend} harness exited {returncode}: {detail}")
        self._save_harness_session_state(resumed=turn_resumed)
        submission = None
        if submission_path.is_file():
            submission = json.loads(submission_path.read_text(encoding="utf-8"))
        action_id = submission.get("action_id") if submission else None
        if action_id is None:
            self._write_trace(
                prompt=prompt, observation=observation, legal=legal, version=version,
                status="no_submit", error=None,
                action_latency_ms=action_latency_ms, process_latency_ms=process_latency_ms,
                session_resumed=turn_resumed,
            )
            raise AgentError(f"{self.config.backend} harness finished without calling submit_action")
        if action_id not in {item["id"] for item in legal}:
            self._write_trace(
                prompt=prompt, observation=observation, legal=legal, version=version,
                status="bad_action", error=None,
                action_latency_ms=action_latency_ms, process_latency_ms=process_latency_ms,
                session_resumed=turn_resumed,
            )
            raise AgentError("harness submitted an unknown or stale action ID")
        metadata = {
            "backend": self.config.backend, "harness": self.config.backend,
            "model": self.config.model, "session_id": self.session.session_id,
            "reasoning_effort": self.config.reasoning_effort,
            "native_reasoning_effort": self._native_reasoning_effort(),
            "session_scope": self.session.scope,
            "session_scope_id": self.session.scope_id,
            "participant_id": self.participant_id,
            "session_resumed": self._dsh_turn_metadata.get("resumed", turn_resumed),
            "session_resume_count": self.session.resume_count,
            "compaction_events": self._dsh_turn_metadata.get("compactionEvents", []),
            "compaction_event_count_total": self._dsh_turn_metadata.get(
                "compactionEventCountTotal"
            ),
            "latency_ms": process_latency_ms,
            "action_latency_ms": action_latency_ms,
            "process_latency_ms": process_latency_ms,
        }
        self._emit("harness_finished", action_id=action_id,
                   latency_ms=process_latency_ms,
                   action_latency_ms=action_latency_ms,
                   process_latency_ms=process_latency_ms,
                   session_id=self.session.session_id,
                   reasoning_effort=self.config.reasoning_effort,
                   native_reasoning_effort=self._native_reasoning_effort())
        self._write_trace(
            prompt=prompt, observation=observation, legal=legal, version=version,
            status="ok", error=None,
            action_latency_ms=action_latency_ms, process_latency_ms=process_latency_ms,
            session_resumed=turn_resumed,
        )
        return action_id, metadata



def build_harness_agent(config: PlayerConfig, match_id: str, seat: int,
                        event_sink: HarnessEventSink | None = None) -> HarnessAgent:
    return HarnessAgent(config, match_id, seat, event_sink=event_sink)
