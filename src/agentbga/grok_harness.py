"""Seat-local configuration for the official Grok Build subscription CLI.

Protocol: https://docs.x.ai/build/cli/headless-scripting
Authentication stays with Grok; AgentBGA never reads OAuth tokens.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
import subprocess
import sys

from .agents import AgentError


def auth_path(source_env: dict[str, str]) -> Path:
    return Path(source_env.get("GROK_AUTH_PATH") or
                Path(source_env.get("GROK_HOME") or Path.home() / ".grok") / "auth.json").resolve()


def subscription_status(source_env: dict[str, str]) -> tuple[bool, str]:
    auth = auth_path(source_env)
    if not auth.is_file():
        return False, "Grok login not found; run grok login with your SuperGrok account"
    return True, "Local Grok credential file found; subscription entitlement is checked by Grok at runtime"


def environment(workspace: Path, source_env: dict[str, str], env: dict[str, str]) -> dict[str, str]:
    ready, detail = subscription_status(source_env)
    if not ready:
        raise AgentError(detail)
    source_auth = auth_path(source_env)
    grok_home = workspace.resolve() / ".grok-home"
    grok_home.mkdir(mode=0o700, exist_ok=True)
    # Do not inherit endpoints, external auth commands, agent profiles or keys.
    env = {name: value for name, value in env.items()
           if not name.startswith(("GROK_", "XAI_"))}
    # Official auth-path override preserves Grok's atomic refresh and shared lock.
    # A symlink is insufficient: an atomic auth.json replacement breaks the link.
    env.update({"GROK_HOME": str(grok_home), "GROK_AUTH_PATH": str(source_auth),
                "GROK_DISABLE_API_KEY_AUTH": "1", "GROK_DISABLE_AUTOUPDATER": "1",
                "GROK_MEMORY": "0", "GROK_SUBAGENTS": "0", "GROK_TOOL_SEARCH": "0"})
    for flag in ("GROK_TELEMETRY_ENABLED", "GROK_TELEMETRY_TRACE_UPLOAD",
                 "GROK_TELEMETRY_MIXPANEL_ENABLED", "GROK_FEEDBACK_ENABLED"):
        env[flag] = "0"
    env["CLAUDE_CONFIG_DIR"] = str(grok_home / "empty-claude")
    for vendor in ("CLAUDE", "CURSOR", "CODEX"):
        for feature in ("SKILLS", "RULES", "AGENTS", "MCPS", "HOOKS", "SESSIONS"):
            env[f"GROK_{vendor}_{feature}_ENABLED"] = "0"
    return env


def discovered_plugins(binary: str, workspace: Path, env: dict[str, str]) -> list[str]:
    """Read-only discovery; plugin compatibility flags alone do not block imports."""
    try:
        result = subprocess.run([binary, "inspect", "--json"], cwd=workspace, env=env,
                                capture_output=True, text=True, check=True, timeout=20)
        report = json.loads(result.stdout)
        return [plugin["name"] for plugin in report.get("plugins", [])]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise AgentError("Unable to inspect Grok plugins safely; update Grok Build and retry") from error


def credential_read_scope(path: Path) -> tuple[str, list[str]]:
    """Grok grants directories only; deny every sibling except the auth file.

    Absolute deny globs are enforced at runtime by macOS Seatbelt, including
    siblings created after launch. The parent remains read-only. Linux uses
    launch-time glob expansion, so refuse this compatibility grant there.
    """
    if sys.platform != "darwin":
        raise AgentError("Shared subscription credentials under strict sandbox require macOS")
    parent, name = str(path.parent), path.name
    if any(c in parent for c in "*?[") or not re.fullmatch(r"[A-Za-z0-9_.]+", name):
        raise AgentError("Grok auth path cannot be represented by exact sandbox deny rules")
    denied = []
    for index, char in enumerate(name):
        prefix = name[:index]
        if prefix:
            denied.append(f"{parent}/{prefix}")
        denied.append(f"{parent}/{prefix}[!{char}]*")
    denied.append(f"{path}?*")
    return parent, denied


def prepare(workspace: Path, mcp_command: list[str], pythonpath: str,
            binary: str, env: dict[str, str]) -> None:
    workspace = workspace.resolve()
    # Stop Grok's upward project discovery at this seat, not the benchmark repo.
    if not (workspace / ".git").exists():
        try:
            subprocess.run(["git", "init", "--quiet", "--template=", str(workspace)], check=True,
                           capture_output=True, timeout=10,
                           env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")})
        except (OSError, subprocess.SubprocessError) as error:
            raise AgentError("Grok seat isolation requires git init to succeed") from error
    grok_home = workspace / ".grok-home"
    grok_home.mkdir(mode=0o700, exist_ok=True)
    # Retain PR #39's strict tool sandbox and the seat MCP runtime access.
    context_path = (workspace / mcp_command[mcp_command.index("--context") + 1]).resolve()
    auth_parent, credential_denies = credential_read_scope(Path(env["GROK_AUTH_PATH"]).resolve())
    readable_roots = list(dict.fromkeys((
        str(Path(__file__).resolve().parents[1]),
        str(Path(sys.executable).resolve().parents[1]),
        auth_parent,
    )))
    (grok_home / "sandbox.toml").write_text(
        '[profiles.agentbga]\nextends = "strict"\n'
        f"read_only = {json.dumps(readable_roots)}\n"
        f"deny = {json.dumps(credential_denies)}\n"
        f"read_write = {json.dumps([str(context_path.parent)])}\n",
        encoding="utf-8",
    )
    settings = (
        "[cli]\nauto_update = false\n"
        "[session]\nload_envrc = false\n"
        "[memory]\nenabled = false\n"
        "[subagents]\nenabled = false\n"
        "[features]\nweb_fetch = false\nlsp_tools = false\n"
        # Grok skills.ignore uses resolved path prefixes, not name globs.
        f"[skills]\nignore = {json.dumps([workspace.anchor])}\n"
        "[mcp_servers.agentbga]\n"
        f"command = {json.dumps(mcp_command[0])}\n"
        f"args = {json.dumps(mcp_command[1:])}\n"
        f"cwd = {json.dumps(str(workspace))}\n"
        f"env = {{ PYTHONPATH = {json.dumps(pythonpath)} }}\n"
        "startup_timeout_sec = 30\n"
    )
    for vendor in ("claude", "cursor"):
        settings += (f"[compat.{vendor}]\n"
                     "skills = false\nrules = false\nagents = false\nmcps = false\nhooks = false\n")
    config_path = grok_home / "config.toml"
    config_path.write_text(settings, encoding="utf-8")
    # Disable by exact names: '*' is not a supported plugin wildcard.
    plugins = discovered_plugins(binary, workspace, env)
    config_path.write_text(settings + f"[plugins]\ndisabled = {json.dumps(plugins)}\n",
                           encoding="utf-8")
