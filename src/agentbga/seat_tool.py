"""Seat-scoped command tools exposed to external agent harnesses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "agentbga.seat-context.v1":
        raise ValueError("invalid seat context")
    return value


def _audit(context_path: Path, tool: str, arguments: dict[str, Any], result: Any) -> None:
    row = {"tool": tool, "arguments": arguments, "result": result, "created_at": time.time()}
    with (context_path.parent / "tool-events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def call_tool(context_path: Path, tool: str, arguments: dict[str, Any] | None = None) -> Any:
    arguments = arguments or {}
    context = _load(context_path)
    if tool == "observe":
        result = context["observation"]
    elif tool == "legal_actions":
        result = context["legal_actions"]
    elif tool == "submit_action":
        action_id = arguments.get("action_id")
        legal_ids = {item["id"] for item in context["legal_actions"]}
        if action_id not in legal_ids:
            raise ValueError("unknown or stale action ID")
        result = {
            "accepted": True, "action_id": action_id,
            "match_id": context["match_id"], "seat": context["seat"],
            "version": context["version"],
        }
        submission = context_path.parent / "submission.json"
        if submission.exists():
            raise ValueError("an action has already been submitted for this turn")
        submission.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    elif tool == "read_notes":
        notes_path = Path(context.get("notes_path") or context_path.parent / "strategy-notes.md")
        result = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""
    elif tool == "write_notes":
        notes_path = Path(context.get("notes_path") or context_path.parent / "strategy-notes.md")
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        notes_path.write_text(str(arguments.get("content", "")), encoding="utf-8")
        result = {"saved": True, "bytes": len(arguments.get("content", ""))}
    else:
        raise ValueError(f"unknown tool: {tool}")
    _audit(context_path, tool, arguments, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentbga-seat", description="Tools bound to one match seat")
    parser.add_argument("--context", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("observe")
    commands.add_parser("legal-actions")
    submit = commands.add_parser("submit-action")
    submit.add_argument("--action-id", required=True)
    args = parser.parse_args(argv)
    context_path = Path(args.context).resolve()
    if args.command == "observe":
        tool, arguments = "observe", {}
    elif args.command == "legal-actions":
        tool, arguments = "legal_actions", {}
    else:
        tool, arguments = "submit_action", {"action_id": args.action_id}
    result = call_tool(context_path, tool, arguments)
    print(json.dumps({"schema_version": "agentbga.seat-tool.v1", "data": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
