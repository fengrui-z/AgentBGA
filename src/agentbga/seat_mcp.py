"""Minimal stdio MCP server bound to one generated seat context."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .seat_tool import call_tool


TOOLS = [
    {
        "name": "observe",
        "description": "Read your seat-scoped current board-game observation.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "legal_actions",
        "description": "List the only actions legal for your seat in this decision and state version.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "submit_action",
        "description": "Commit exactly one legal action ID for this decision step.",
        "inputSchema": {
            "type": "object", "properties": {"action_id": {"type": "string"}},
            "required": ["action_id"], "additionalProperties": False,
        },
    },
    {
        "name": "read_notes",
        "description": "Read your persistent strategy notes (survives across turns).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "write_notes",
        "description": "Replace your strategy notes with new content (survives across turns).",
        "inputSchema": {
            "type": "object", "properties": {"content": {"type": "string"}},
            "required": ["content"], "additionalProperties": False,
        },
    },
]


def _read_message() -> dict[str, Any] | None:
    first = sys.stdin.buffer.readline()
    if not first:
        return None
    if first.lower().startswith(b"content-length:"):
        length = int(first.split(b":", 1)[1].strip())
        while True:
            header = sys.stdin.buffer.readline()
            if header in {b"\n", b"\r\n", b""}:
                break
        return json.loads(sys.stdin.buffer.read(length))
    return json.loads(first)


def _reply(request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    payload["error" if error else "result"] = error if error else result
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


def serve(context_path: Path) -> None:
    while True:
        request: dict[str, Any] = {}
        try:
            loaded = _read_message()
            if loaded is None:
                return
            request = loaded
            method = request.get("method")
            request_id = request.get("id")
            if request_id is None:
                continue
            if method == "initialize":
                protocol = (request.get("params") or {}).get("protocolVersion", "2025-06-18")
                _reply(request_id, {
                    "protocolVersion": protocol,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "agentbga-seat", "version": "0.1.0"},
                })
            elif method == "ping":
                _reply(request_id, {})
            elif method == "tools/list":
                _reply(request_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = request.get("params") or {}
                result = call_tool(context_path, params.get("name", ""), params.get("arguments") or {})
                _reply(request_id, {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                    "structuredContent": {"data": result},
                    "isError": False,
                })
            else:
                _reply(request_id, error={"code": -32601, "message": "method not found"})
        except Exception as error:
            request_id = request.get("id") if isinstance(request, dict) else None
            if request_id is not None:
                _reply(request_id, error={"code": -32000, "message": str(error)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", required=True)
    args = parser.parse_args(argv)
    serve(Path(args.context).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
