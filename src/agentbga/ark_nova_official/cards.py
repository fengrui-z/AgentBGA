"""Vertical bridge from reviewed content entries to semantic execution."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .content import ContentEntry
from .semantics import (
    EvaluationContext, SemanticEngine, SemanticRuleError, simultaneous_effects,
)
from .state import clone_state


PLAY_TIMINGS = frozenset({"on_play", "immediate", "ongoing", "interaction"})
DEFERRED_PLAY_TIMINGS = frozenset({"after_finishing"})


def entry_is_eligible(
    engine: SemanticEngine, state: dict[str, Any], seat: int, entry: ContentEntry,
) -> bool:
    card = {"id": entry.id, "kind": entry.kind, "facts": dict(entry.facts)}
    context = EvaluationContext(state=state, actor_seat=seat, card=card)
    return all(engine.evaluate(requirement, context) for requirement in entry.requirements)


def play_entry_semantics(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    entry: ContentEntry,
    *,
    instance_id: str | None = None,
    additional_effects: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] = (),
    requirements_already_authorized: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Record a played semantic entry and execute its play-time operations.

    Payment, enclosure placement, action strength, and card-zone movement remain
    responsibilities of the action/domain layer. This bridge handles entry
    requirements, derived tag/icon counts, and card-specific semantic effects.
    """
    if entry.kind not in {"animal", "sponsor", "zoo_conservation_project"}:
        raise SemanticRuleError(f"content kind cannot be played through the zoo-card bridge: {entry.kind}")
    if state["resolution"]["queue"] or state["resolution"]["pending_choice"] is not None:
        raise SemanticRuleError("cannot play a semantic entry during another resolution")
    if not requirements_already_authorized and not entry_is_eligible(engine, state, seat, entry):
        raise SemanticRuleError(f"semantic requirements are not met: {entry.id}")
    next_state = clone_state(state)
    player = next_state["players"][seat]
    played_id = entry.id if instance_id is None else instance_id
    if not isinstance(played_id, str) or not played_id:
        raise SemanticRuleError("played card instance requires a stable ID")
    if any(card.get("id") == played_id for card in player["played_cards"]):
        raise SemanticRuleError(f"semantic card instance is already in play: {played_id}")
    played = {
        "id": played_id,
        "entry_id": entry.id,
        "kind": entry.kind,
        "display_title": entry.display_title,
        "facts": deepcopy(dict(entry.facts)),
        "effects": deepcopy(list(entry.effects)),
        "semantic_context": {"pre_play_tracks": deepcopy(player["tracks"])},
        # Since rules version 2026.08, printed rock/water adjacency symbols are
        # also persistent player icons.  This marker lets old saved games be
        # migrated exactly once.
        "terrain_icons_accounted": True,
    }
    player["played_cards"].append(played)
    _add_counts(player["tags"], entry.facts.get("tags", []), "tags")
    printed_icons = printed_icon_counts(entry.facts)
    _add_counts(player["icons"], printed_icons, "icons")
    entry_effects = _entry_effects_for_player_count(entry, next_state["player_count"])
    play_effects = [deepcopy(dict(effect)) for effect in additional_effects]
    play_effects.extend(
        deepcopy(dict(effect))
        for effect in entry_effects if effect.get("timing") in PLAY_TIMINGS
    )
    effects = _ordered_play_effects(play_effects, entry.display_title)
    deferred = [
        effect for effect in entry_effects if effect.get("timing") in DEFERRED_PLAY_TIMINGS
    ]
    session = next_state["turn"].get("action_session")
    if deferred and session is not None and session.get("seat") == seat:
        grouped = simultaneous_effects(
            deferred,
            label=f"Order {entry.display_title} after-finishing effects",
            timing="after_finishing",
        )
        session["after_finishing_effects"].extend({
            **effect,
            "_semantic_source_id": entry.id,
            "_semantic_card": deepcopy(played),
        } for effect in grouped)
    elif deferred:
        effects.extend(simultaneous_effects(
            deferred,
            label=f"Order {entry.display_title} after-finishing effects",
            timing="after_finishing",
        ))
    # Printed icons enter only after the card is in the zoo and its ongoing
    # modifiers have been installed.  One trigger operation per icon type keeps
    # doubled icons deterministic while letting matching Sponsors fire once for
    # each physical icon.
    effects.extend(_icon_entered_effects(printed_icons))
    if entry.kind == "animal":
        effects.append({
            "op": "trigger_animal_played",
            "args": {
                "size_class": _animal_size_class(entry),
                "entry_id": entry.id,
                "instance_id": played_id,
            },
            "timing": "on_play",
        })
    if not effects:
        return next_state, [{
            "type": "semantic_entry_played",
            "seat": seat,
            "entry_id": entry.id,
            "kind": entry.kind,
        }]
    next_state, events = engine.start_effects(
        next_state,
        seat,
        effects,
        source_id=entry.id,
        card=played,
    )
    return next_state, [{
        "type": "semantic_entry_played",
        "seat": seat,
        "entry_id": entry.id,
        "kind": entry.kind,
    }, *events]


def _add_counts(target: dict[str, int], raw: Any, label: str) -> None:
    if isinstance(raw, list):
        for key in raw:
            if not isinstance(key, str) or not key:
                raise SemanticRuleError(f"card fact {label} must contain stable string IDs")
            target[key] = target.get(key, 0) + 1
        return
    if isinstance(raw, dict):
        for key, count in raw.items():
            if (
                not isinstance(key, str) or not key
                or not isinstance(count, int) or isinstance(count, bool) or count < 0
            ):
                raise SemanticRuleError(f"card fact {label} counts are invalid")
            target[key] = target.get(key, 0) + count
        return
    raise SemanticRuleError(f"card fact {label} must be an array or count object")


def terrain_requirement_icon_counts(facts: Mapping[str, Any]) -> dict[str, int]:
    """Return terrain symbols not already represented in ``facts.icons``.

    Some imported Sponsor records already carry their terrain symbol in the
    ordinary icon field as well as the placement requirement.  Treating the
    printed requirement as a lower bound avoids losing the symbol without
    counting the same printed symbol twice.
    """

    explicit: dict[str, int] = {}
    _add_counts(explicit, facts.get("icons", []), "icons")
    counts: dict[str, int] = {}
    for terrain in ("rock", "water"):
        raw = facts.get(f"{terrain}_requirement", 0)
        if raw is None:
            raw = 0
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            raise SemanticRuleError(f"card fact {terrain}_requirement is invalid")
        missing = raw - int(explicit.get(terrain, 0))
        if missing > 0:
            counts[terrain] = missing
    return counts


def printed_icon_counts(facts: Mapping[str, Any]) -> dict[str, int]:
    """Merge ordinary icons and terrain-requirement icons on a played card."""

    counts: dict[str, int] = {}
    _add_counts(counts, facts.get("icons", []), "icons")
    _add_counts(counts, terrain_requirement_icon_counts(facts), "terrain requirement icons")
    return counts


_CARD_CHOICE_OPS = frozenset({
    "choose_one", "choose_opponent", "pilfer", "take_display_card",
    "take_map_reward_card", "draw_keep_cards", "reveal_keep_animal",
    "draw_keep_final_scoring", "take_base_project", "dig_cards",
    "scavenge_discard", "sell_hand_cards", "tuck_hand_cards",
    "place_free_building", "take_display_sponsors",
})


def _entry_effects_for_player_count(
    entry: ContentEntry, player_count: int,
) -> list[dict[str, Any]]:
    effects = [deepcopy(dict(effect)) for effect in entry.effects]
    if player_count != 1 or entry.kind != "animal":
        return effects
    replacements = entry.facts.get("solo_replaces_ops")
    solo_effects = entry.facts.get("solo_effects")
    if replacements is None and solo_effects is None:
        return effects
    if (
        not isinstance(replacements, list) or not replacements
        or any(not isinstance(op, str) or not op for op in replacements)
        or not isinstance(solo_effects, list) or not solo_effects
        or any(not isinstance(effect, Mapping) for effect in solo_effects)
    ):
        raise SemanticRuleError(f"malformed solo replacement effects: {entry.id}")
    replaced = set(replacements)
    if not any(effect.get("op") in replaced for effect in effects):
        raise SemanticRuleError(f"solo replacement does not match an interactive effect: {entry.id}")
    return [
        effect for effect in effects if effect.get("op") not in replaced
    ] + [deepcopy(dict(effect)) for effect in solo_effects]


def _ordered_play_effects(
    effects: list[Mapping[str, Any]], title: str,
) -> list[dict[str, Any]]:
    """Open an order window exactly when same-card order can change choices.

    Pure additive effects are mathematically commutative and can be resolved in
    printed/data order without burdening the player. Choice effects, multiple
    mutable card-pool effects, Conservation milestones, and Reputation-dependent
    card taking retain the official explicit ordering decision.
    """
    copied = [deepcopy(dict(effect)) for effect in effects]
    if len(copied) <= 1:
        return copied
    ops = [effect.get("op") for effect in copied]
    choice_count = sum(op in _CARD_CHOICE_OPS for op in ops)
    moved_tracks = {
        effect.get("args", {}).get("track")
        for effect in copied if effect.get("op") == "move_track"
    }
    order_matters = (
        choice_count > 1
        or "pilfer" in ops
        or "conservation" in moved_tracks
        or (
            "reputation" in moved_tracks
            and any(op in {"take_display_card", "take_map_reward_card", "take_display_sponsors"} for op in ops)
        )
    )
    if not order_matters:
        return copied
    return simultaneous_effects(
        copied, label=f"Order {title} play effects", timing="immediate",
    )
def _animal_size_class(entry: ContentEntry) -> str:
    size = entry.facts.get("enclosure_size")
    if not isinstance(size, int) or isinstance(size, bool):
        # Hand-authored semantic scenarios may omit physical enclosure facts;
        # they are neutral to the small/large Sponsor rules.
        return "medium"
    if size <= 2:
        return "small"
    if size >= 4:
        return "large"
    return "medium"


def _icon_entered_effects(raw: Any) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    if isinstance(raw, list):
        for icon in raw:
            if not isinstance(icon, str) or not icon:
                raise SemanticRuleError("card fact icons must contain stable string IDs")
            counts[icon] = counts.get(icon, 0) + 1
    elif isinstance(raw, dict):
        for icon, count in raw.items():
            if (
                not isinstance(icon, str) or not icon
                or not isinstance(count, int) or isinstance(count, bool) or count < 0
            ):
                raise SemanticRuleError("card fact icon counts are invalid")
            if count:
                counts[icon] = count
    else:
        raise SemanticRuleError("card fact icons must be an array or count object")
    return [{
        "op": "trigger_icon_entered",
        "args": {"icon": icon, "count": count},
        "timing": "on_play",
    } for icon, count in counts.items()]
