"""Lossless, seat-local filtering of already-enumerated legal actions."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from typing import Any, Mapping


MAX_REPLY_BYTES = 16_000
PAGE_SIZE = 50
MAX_PAGE_SIZE = 50
STRING = {"type": "string", "minLength": 1}
NONNEGATIVE = {"type": "integer", "minimum": 0}
GAME_FILTERS = {
    "splendor": {
        "type": STRING,
        "card_id": STRING,
        "tier": {"type": "integer", "minimum": 1, "maximum": 3},
        "bonus": {"type": "string", "enum": ["white", "blue", "green", "red", "black"]},
        "noble_id": STRING,
        "max_payment": NONNEGATIVE,
    },
}


def query_schema() -> dict[str, Any]:
    properties = {key: value for fields in GAME_FILTERS.values() for key, value in fields.items()}
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "group": STRING, "cursor": NONNEGATIVE,
            "limit": {"type": "integer", "minimum": 1, "maximum": MAX_PAGE_SIZE},
            "filters": {"type": "object", "properties": properties, "additionalProperties": False},
        },
    }


QUERY_DESCRIPTION = (
    "List current legal action IDs. Small unfiltered lists are returned in full; large lists "
    "return groups. Select a group (action type), or combine exact-match filters with AND. "
    "max_payment is an upper bound on the total payment. Check available_filters in a groups "
    "response for this game's fields. Follow next_cursor with the SAME group/filters to read "
    "all pages; cursors apply only to this decision. Never read output files to find actions."
)


def filter_values(game: str, item: Mapping[str, Any]) -> dict[str, Any]:
    values = dict(item)
    if game == "splendor":
        from .splendor import CARDS
        card = CARDS.get(item.get("card_id"), {})
        values.update({key: card[key] for key in ("tier", "bonus") if key in card})
    if isinstance(item.get("payment"), dict):
        values["max_payment"] = sum(item["payment"].values())
    return {key: values[key] for key in GAME_FILTERS[game] if key in values}


def query_metadata(game: str, actions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "fields": GAME_FILTERS[game],
        "values": {item["id"]: filter_values(game, item) for item in actions},
    }


def reply_bytes(value: Any) -> int:
    """Count both MCP representations, including the JSON-escaped text wrapper."""
    payload = {
        "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
        "structuredContent": {"data": value}, "isError": False,
    }
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _validate(name: str, value: Any, schema: Mapping[str, Any]) -> None:
    if schema["type"] == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        if value < schema.get("minimum", 0) or value > schema.get("maximum", value):
            raise ValueError(f"{name} is out of range")
    elif not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{name} must be one of {schema['enum']}")


def query_actions(context: Mapping[str, Any], arguments: Mapping[str, Any]) -> Any:
    game = context["observation"]["game"]
    actions = context["legal_actions"]
    if not isinstance(arguments, dict):
        raise ValueError("legal_actions arguments must be an object")
    unknown = set(arguments) - set(query_schema()["properties"])
    if unknown:
        raise ValueError(f"unknown legal_actions arguments: {sorted(unknown)}")
    filters = arguments.get("filters", {})
    if not isinstance(filters, dict):
        raise ValueError("filters must be an object")
    unknown = set(filters) - set(GAME_FILTERS[game])
    if unknown:
        raise ValueError(f"unsupported {game} filters: {sorted(unknown)}")
    for key, value in filters.items():
        _validate(key, value, GAME_FILTERS[game][key])
    for key in ("group", "cursor", "limit"):
        if key in arguments:
            _validate(key, arguments[key], query_schema()["properties"][key])
    group = arguments.get("group")
    types = Counter(item["type"] for item in actions)
    if group is not None and group not in types:
        raise ValueError(f"unknown group; available groups: {sorted(types)}")
    if group is not None and "type" in filters and filters["type"] != group:
        raise ValueError("group and filters.type must match")
    if not arguments:
        if reply_bytes(actions) <= MAX_REPLY_BYTES:
            return deepcopy(actions)
        return {
            "state_version": context["version"], "mode": "groups", "total": len(actions),
            "groups": [{"group": kind, "count": count} for kind, count in sorted(types.items())],
            "available_filters": list(GAME_FILTERS[game]),
            "instruction": "Call legal_actions with group or filters; follow next_cursor with the same query.",
        }
    metadata = context.get("legal_action_query") or query_metadata(game, actions)
    selected = []
    for item in actions:
        if group is not None and item["type"] != group:
            continue
        values = metadata["values"][item["id"]]
        if all(key in values and (
            values[key] <= value if key.startswith("max_") else values[key] == value
        ) for key, value in filters.items()):
            selected.append(item)
    cursor, limit = arguments.get("cursor", 0), arguments.get("limit", PAGE_SIZE)
    if cursor > len(selected):
        raise ValueError("cursor exceeds the filtered action count")
    page = deepcopy(selected[cursor:cursor + limit])
    result = {
        "state_version": context["version"], "mode": "actions", "group": group,
        "filters": filters, "total": len(selected), "cursor": cursor,
        "next_cursor": None, "actions": page,
    }
    while True:
        next_cursor = cursor + len(page)
        result["next_cursor"] = next_cursor if next_cursor < len(selected) else None
        if reply_bytes(result) <= MAX_REPLY_BYTES:
            return result
        if len(page) <= 1:
            raise ValueError("a single legal action exceeds the response byte budget")
        page.pop()
