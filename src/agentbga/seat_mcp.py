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
        "description": (
            "List legal actions for this state version. Large action spaces return groups; "
            "call again with group/cursor to retrieve concrete action IDs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "group": {"type": "string"},
                "cursor": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "inspect_card",
        "description": "Read complete details for one visible card. Accepts a detail_ref such as card:zoo-421 or a bare visible card id such as zoo-421.",
        "inputSchema": {
            "type": "object", "properties": {"card_ref": {"type": "string"}},
            "required": ["card_ref"], "additionalProperties": False,
        },
    },
    {
        "name": "inspect_rules",
        "description": "Read one bounded, engine-aligned Ark Nova rules topic. Call without a topic to list available topics; use this instead of guessing rules from legal actions.",
        "inputSchema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "inspect_map",
        "description": "Read a public player map on demand, optionally selecting terrain, buildings, rewards, or player_board.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "seat": {"type": "integer", "minimum": 0},
                "sections": {
                    "type": "array",
                    "items": {"enum": ["terrain", "buildings", "rewards", "player_board"]},
                    "uniqueItems": True,
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "inspect_played_cards",
        "description": "List public played cards for one seat without repeating every card program in observe.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "seat": {"type": "integer", "minimum": 0},
                "kind": {"type": "string"},
                "cursor": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "inspect_history",
        "description": "Read seat-safe state changes accumulated across prior observations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "since_version": {"type": "integer", "minimum": 0},
                "cursor": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "additionalProperties": False,
        },
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


def serve(context_path: Path, notes_root: Path) -> None:
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
                result = call_tool(
                    context_path, params.get("name", ""), params.get("arguments") or {},
                    notes_root=notes_root,
                )
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
    parser.add_argument("--notes-root", required=True)
    args = parser.parse_args(argv)
    serve(Path(args.context).resolve(), Path(args.notes_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
