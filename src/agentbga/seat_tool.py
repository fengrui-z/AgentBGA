"""Seat-scoped command tools exposed to external agent harnesses."""

from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import stat
import time
from typing import Any


def _atomic_open_flags() -> int:
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise RuntimeError("atomic seat file access is unsupported on this platform")
    return os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)


def _open_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise ValueError("trusted seat file root must be a directory")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_existing_regular(
    directory: int, name: str, flags: int, label: str,
) -> int:
    # The directory descriptor is the containment boundary. O_NOFOLLOW makes
    # selecting the fixed entry and opening it one operation; later entry
    # replacement cannot redirect the returned descriptor.
    try:
        descriptor = os.open(name, flags | _atomic_open_flags(), dir_fd=directory)
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.EMLINK, errno.EISDIR, errno.ENXIO}:
            raise ValueError(f"{label} must be a single-link regular file") from error
        raise
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError(f"{label} must be a single-link regular file")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_or_create_regular(
    directory: int, name: str, flags: int, label: str,
) -> int:
    for _ in range(4):
        try:
            return _open_existing_regular(directory, name, flags, label)
        except FileNotFoundError:
            pass
        try:
            descriptor = os.open(
                name, flags | os.O_CREAT | os.O_EXCL | _atomic_open_flags(),
                0o600, dir_fd=directory,
            )
        except FileExistsError:
            continue
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError(f"{label} must be a single-link regular file")
            return descriptor
        except Exception:
            os.close(descriptor)
            raise
    raise ValueError(f"{label} changed while it was being opened")


def _read_text_at(root: Path, name: str, label: str, *, missing: str | None = None) -> str:
    directory = _open_directory(root)
    descriptor = -1
    try:
        try:
            descriptor = _open_existing_regular(directory, name, os.O_RDONLY, label)
        except FileNotFoundError:
            if missing is not None:
                return missing
            raise
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)


def _replace_text_at(root: Path, name: str, label: str, content: str) -> None:
    directory = _open_directory(root)
    descriptor = -1
    try:
        descriptor = _open_or_create_regular(directory, name, os.O_WRONLY, label)
        os.ftruncate(descriptor, 0)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(content)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)


def _append_text_at(root: Path, name: str, label: str, content: str) -> None:
    directory = _open_directory(root)
    descriptor = -1
    try:
        descriptor = _open_or_create_regular(
            directory, name, os.O_WRONLY | os.O_APPEND, label,
        )
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(content)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)


def _create_text_at(root: Path, name: str, label: str, content: str) -> None:
    directory = _open_directory(root)
    descriptor = -1
    try:
        try:
            descriptor = os.open(
                name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _atomic_open_flags(),
                0o600, dir_fd=directory,
            )
        except FileExistsError as error:
            raise ValueError("an action has already been submitted for this turn") from error
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError(f"{label} must be a single-link regular file")
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(content)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(_read_text_at(path.parent, path.name, "seat context"))
    if not isinstance(value, dict) or value.get("schema_version") != "agentbga.seat-context.v1":
        raise ValueError("invalid seat context")
    return value


def _audit(context_path: Path, tool: str, arguments: dict[str, Any], result: Any) -> None:
    row = {"tool": tool, "arguments": arguments, "result": result, "created_at": time.time()}
    _append_text_at(
        context_path.parent, "tool-events.jsonl", "tool audit",
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n",
    )


def call_tool(
    context_path: Path, tool: str, arguments: dict[str, Any] | None = None, *,
    notes_root: Path | None = None,
) -> Any:
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
        _create_text_at(
            context_path.parent, "submission.json", "action submission",
            json.dumps(result, separators=(",", ":")),
        )
    elif tool == "read_notes":
        if notes_root is None:
            raise ValueError("persistent notes require a trusted notes root")
        result = _read_text_at(
            notes_root, "strategy-notes.md", "strategy notes", missing="",
        )
    elif tool == "write_notes":
        if notes_root is None:
            raise ValueError("persistent notes require a trusted notes root")
        content = str(arguments.get("content", ""))
        _replace_text_at(notes_root, "strategy-notes.md", "strategy notes", content)
        result = {"saved": True, "bytes": len(content.encode("utf-8"))}
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
