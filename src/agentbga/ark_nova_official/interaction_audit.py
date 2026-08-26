"""Static audit linking compiled persistent effects to their engine producers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .content import ContentPack
from .semantics import STATIC_MODIFIER_KINDS


_EXACT_DYNAMIC_TRIGGERS = frozenset({
    "income", "building_placed", "project_supported",
    "release_project_supported", "animal_played", "small_animal_played",
    "medium_animal_played", "large_animal_played", "distinct_icon_entered",
})


@dataclass(frozen=True)
class InteractionAuditReport:
    modifier_count: int
    dynamic_modifier_count: int
    static_modifier_count: int
    triggers: tuple[str, ...]
    static_kinds: tuple[str, ...]
    unresolved: tuple[str, ...]


def audit_interactions(pack: ContentPack) -> InteractionAuditReport:
    """Verify every compiled modifier has a concrete event producer or rule consumer."""
    modifiers: list[tuple[str, Mapping[str, Any]]] = []
    for entries in pack.collections.values():
        for entry in entries:
            for effect in entry.effects:
                _collect_modifiers(effect, entry.id, modifiers)
    triggers = set()
    static_kinds = set()
    unresolved = []
    dynamic_count = 0
    static_count = 0
    for entry_id, args in modifiers:
        trigger = args.get("trigger")
        kind = args.get("kind")
        if trigger == "static":
            static_count += 1
            if isinstance(kind, str):
                static_kinds.add(kind)
            if kind not in STATIC_MODIFIER_KINDS:
                unresolved.append(f"{entry_id}:static:{kind}")
            continue
        dynamic_count += 1
        if isinstance(trigger, str):
            triggers.add(trigger)
        if not _dynamic_trigger_supported(trigger):
            unresolved.append(f"{entry_id}:trigger:{trigger}")
    return InteractionAuditReport(
        modifier_count=len(modifiers),
        dynamic_modifier_count=dynamic_count,
        static_modifier_count=static_count,
        triggers=tuple(sorted(triggers)),
        static_kinds=tuple(sorted(static_kinds)),
        unresolved=tuple(sorted(unresolved)),
    )


def _dynamic_trigger_supported(trigger: Any) -> bool:
    return (
        isinstance(trigger, str)
        and (
            trigger in _EXACT_DYNAMIC_TRIGGERS
            or trigger.startswith("icon_entered:self:")
            or trigger.startswith("icon_entered:any:")
        )
    )


def _collect_modifiers(
    effect: Mapping[str, Any], entry_id: str,
    target: list[tuple[str, Mapping[str, Any]]],
) -> None:
    if effect.get("op") == "add_modifier" and isinstance(effect.get("args"), Mapping):
        target.append((entry_id, effect["args"]))
    args = effect.get("args")
    if not isinstance(args, Mapping):
        return
    children = args.get("effects")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, Mapping):
                _collect_modifiers(child, entry_id, target)
    options = args.get("options")
    if isinstance(options, list):
        for option in options:
            if not isinstance(option, Mapping):
                continue
            for child in option.get("effects", []):
                if isinstance(child, Mapping):
                    _collect_modifiers(child, entry_id, target)
