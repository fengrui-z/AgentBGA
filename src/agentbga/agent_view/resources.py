"""Bounded, lossless inspection of an already seat-safe JSON document.

Pages are prepared once per decision so every harness serves identical content.
No engine state, filesystem paths or database queries are accepted by this API.
"""
from copy import deepcopy
import hashlib
import json

from ..legal_action_query import MAX_REPLY_BYTES, reply_bytes

INSPECT_DESCRIPTION = (
    "Read Brass observation details using an inspect_ref from observe or this tool. "
    "No arguments opens the full observation index. mode=value contains the complete value; "
    "mode=object/array contains entries with a value or another inspect_ref. "
    "Follow next_cursor with the SAME ref to get remaining entries. Cursors expire when "
    "the decision changes. All details are seat-visible; use this tool rather than files."
)
INSPECT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "ref": {"type": "string", "minLength": 1},
        "cursor": {"type": "string", "minLength": 1},
        "state_version": {"type": "integer", "minimum": 0},
    },
}


def build_resources(source, version, scope, *, root_ref="observation", aliases=None):
    documents = {}
    revision = hashlib.sha256(json.dumps([scope, version, source], sort_keys=True,
                                        ensure_ascii=False).encode()).hexdigest()

    def build(value, ref):
        base = {"state_version": version, "ref": ref, "cursor": None, "next_cursor": None}
        full = {**base, "mode": "value", "value": deepcopy(value)}
        if reply_bytes(full) <= MAX_REPLY_BYTES:
            documents[ref] = [full]
            return
        if not isinstance(value, (dict, list)):
            raise ValueError(f"oversized scalar at {ref}; adapter must split it into sections")
        entries = []
        for key, child in (value.items() if isinstance(value, dict) else enumerate(value)):
            entry = {"key" if isinstance(value, dict) else "index": key}
            # Small entries can be returned together. Large children get named resources.
            if reply_bytes(child) <= 4000:
                entry["value"] = deepcopy(child)
            else:
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                child_ref = f"{ref}/{escaped}"
                build(child, child_ref)
                entry["inspect_ref"] = child_ref
            entries.append(entry)
        pages, offset = [], 0
        while offset < len(entries):
            index = len(pages)
            token = lambda i: hashlib.sha256(f"{revision}:{ref}:{i}".encode()).hexdigest()[:24]
            page = {**base, "mode": "object" if isinstance(value, dict) else "array",
                    "total": len(entries), "cursor": token(index) if index else None,
                    "next_cursor": token(index + 1), "entries": []}
            for entry in entries[offset:offset + 20]:
                page["entries"].append(entry)
                if reply_bytes(page) > MAX_REPLY_BYTES:
                    page["entries"].pop()
                    break
            if not page["entries"]:
                raise ValueError(f"oversized resource entry at {ref}")
            offset += len(page["entries"])
            if offset == len(entries):
                page["next_cursor"] = None
            pages.append(page)
        documents[ref] = pages

    build(source, root_ref)
    for ref, value in (aliases or {}).items():
        build(value, ref)
    return {"documents": documents}


def inspect(context, arguments):
    if not isinstance(arguments, dict) or set(arguments) - set(INSPECT_SCHEMA["properties"]):
        raise ValueError("invalid inspect arguments")
    for key in ("ref", "cursor"):
        if key in arguments and (not isinstance(arguments[key], str) or not arguments[key]):
            raise ValueError(f"{key} must be a non-empty string")
    if "state_version" in arguments:
        version = arguments["state_version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise ValueError("state_version must be a nonnegative integer")
        if version != context["version"]:
            raise ValueError("stale state_version; call observe again")
    ref = arguments.get("ref", "observation")
    pages = context.get("view_resources", {}).get("documents", {}).get(ref)
    if pages is None:
        raise ValueError("inspect ref unavailable in this seat's observation")
    cursor = arguments.get("cursor")
    page = next((page for page in pages if page["cursor"] == cursor), None)
    if page is None:
        raise ValueError("stale cursor or wrong ref; restart inspection")
    return deepcopy(page)
