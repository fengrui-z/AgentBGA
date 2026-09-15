"""Offline Grok protocol fixture: invokes the actual generated seat MCP server."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib


def emit(value):
    print(json.dumps(value), flush=True)


args = sys.argv[1:]
assert args[args.index("--output-format") + 1] == "streaming-json"
assert args[args.index("--tools") + 1] == ""
assert "XAI_API_KEY" not in os.environ
session_id = "72c21f33-f4a2-499b-bd93-4ae82eb94dd7"
if "--resume" in args:
    assert args[args.index("--resume") + 1] == session_id
mode = os.environ.get("AGENTBGA_GROK_FIXTURE_MODE", "success")
if mode == "error":
    emit({"type": "error", "message": "Subscription limit reached"})
    sys.exit(1)
emit({"type": "thought", "data": "Considering the board."})
if mode != "no_submit":
    settings = tomllib.loads((Path(os.environ["GROK_HOME"]) / "config.toml").read_text())
    mcp = settings["mcp_servers"]["agentbga"]
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "observe"}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "legal_actions"}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "submit_action", "arguments": {"action_id": "a-test"}}},
    ]
    result = subprocess.run([mcp["command"], *mcp["args"]],
                            input="".join(json.dumps(r) + "\n" for r in requests),
                            capture_output=True, text=True, check=True, timeout=10,
                            cwd=mcp["cwd"], env={**os.environ, **mcp["env"]})
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert not responses[-1]["result"].get("isError"), responses[-1]
    emit({"type": "tool_call", "toolName": "agentbga__submit_action",
          "toolCallId": "c1", "rawInput": {"action_id": "a-test"}})
    emit({"type": "tool_call_update", "toolCallId": "c1", "status": "completed"})
emit({"type": "text", "data": "Decision completed."})
usage = {"input_tokens": 100, "cache_read_input_tokens": 40,
         "cache_creation_input_tokens": 5, "output_tokens": 20, "reasoning_tokens": 8}
emit({"type": "usage", "usage": usage})
emit({"type": "end", "sessionId": session_id, "usage": usage, "num_turns": 1})
