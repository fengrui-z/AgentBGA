"""Compiler and dispatcher boundary for imported Ark Nova animal abilities."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


ABILITY_TIMING = "on_play"


# Mechanics transcription of the base-card blue solo stripes. These operations
# replace only the interactive keyword operation; printed tracks/icons remain.
SOLO_ANIMAL_REPLACEMENTS: dict[str, dict[str, Any]] = {
    "449": {"replaces_ops": ["apply_interaction_tokens"], "effects": [
        {"op": "gain_x_token", "args": {"amount": 1}, "timing": "on_play"},
    ]},
    "456": {"replaces_ops": ["pilfer"], "effects": [
        {"op": "draw_cards", "args": {"amount": 1}, "timing": "on_play"},
    ]},
    "458": {"replaces_ops": ["pilfer"], "effects": [
        {"op": "draw_cards", "args": {"amount": 2}, "timing": "on_play"},
    ]},
    "463": {"replaces_ops": ["pilfer"], "effects": [
        {"op": "draw_cards", "args": {"amount": 1}, "timing": "on_play"},
    ]},
    "470": {"replaces_ops": ["apply_interaction_tokens"], "effects": [
        {"op": "gain_x_token", "args": {"amount": 1}, "timing": "on_play"},
    ]},
    "474": {"replaces_ops": ["apply_interaction_tokens"], "effects": [
        {"op": "reposition_action_card", "args": {"target_slot": 1, "optional": True},
         "timing": "after_finishing"},
    ]},
    "475": {"replaces_ops": ["grant_hypnosis_action"], "effects": [
        {"op": "grant_extra_action", "args": {"excluded_action": "animals"},
         "timing": "after_finishing"},
    ]},
    "482": {"replaces_ops": ["apply_interaction_tokens"], "effects": [
        {"op": "reposition_action_card", "args": {"target_slot": 1, "optional": True},
         "timing": "after_finishing"},
    ]},
    "483": {"replaces_ops": ["apply_interaction_tokens"], "effects": [
        {"op": "reposition_action_card", "args": {"target_slot": 1, "optional": True},
         "timing": "after_finishing"},
    ]},
    "485": {"replaces_ops": ["grant_hypnosis_action"], "effects": [
        {"op": "grant_extra_action", "args": {"excluded_action": "animals"},
         "timing": "after_finishing"},
    ]},
    "492": {"replaces_ops": ["apply_interaction_tokens"], "effects": [
        {"op": "gain_x_token", "args": {"amount": 1}, "timing": "on_play"},
    ]},
}


def solo_animal_replacement(component_id: Any) -> dict[str, Any] | None:
    value = SOLO_ANIMAL_REPLACEMENTS.get(str(component_id))
    return deepcopy(value) if value is not None else None


def _positive_integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def compile_animal_ability(ability: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    """Return closed semantic operations, or ``None`` when a dispatcher is pending.

    Only abilities whose structured parameters completely determine their rules
    are compiled here. Choice-heavy and interaction abilities remain explicit
    pending records instead of silently degrading to a no-op.
    """
    key = ability.get("key")
    value = _positive_integer(ability.get("value"))
    raw_value = ability.get("value")
    if key == "sprint" and value is not None:
        return [{"op": "draw_cards", "args": {"amount": value}, "timing": ABILITY_TIMING}]
    if key == "jumping" and value is not None:
        return [
            {"op": "advance_break", "args": {"amount": value}, "timing": ABILITY_TIMING},
            {"op": "gain_money", "args": {"amount": value}, "timing": ABILITY_TIMING},
        ]
    if key == "inventive":
        return [{"op": "gain_x_token", "args": {"amount": 1}, "timing": ABILITY_TIMING}]
    if key == "pack":
        # Pack is a keyword rule, not a card-specific printed table: after the
        # animal's own icon has entered the zoo, gain one appeal for every
        # predator icon currently present.
        return [{
            "op": "move_track",
            "args": {"track": "appeal", "amount": {"ref": "actor.icons.predator"}},
            "timing": ABILITY_TIMING,
        }]
    if key == "petting_zoo_animal":
        # The official keyword table is 3 / 6 / 9 appeal for the first,
        # second, and third Petting Zoo animal.  Since only three may be
        # accommodated, this is exactly three times the post-play icon count.
        return [{
            "op": "move_track",
            "args": {
                "track": "appeal",
                "amount": {
                    "calc": "multiply",
                    "values": [{"ref": "actor.icons.pet"}, 3],
                },
            },
            "timing": ABILITY_TIMING,
        }]
    if key == "pilfering_1":
        return [{
            "op": "pilfer",
            "args": {"leader_track": "appeal"},
            "timing": "interaction",
        }]
    if key == "pilfering_2":
        return [
            {
                "op": "pilfer",
                "args": {"leader_track": track},
                "timing": "interaction",
            }
            for track in ("appeal", "conservation")
        ]
    if key == "hypnosis" and value is not None:
        return [{
            "op": "grant_hypnosis_action",
            "args": {"maximum_target_slot": value},
            "timing": "after_finishing",
        }]
    if key == "iconic_animal" and isinstance(raw_value, str) and raw_value:
        return [{
            "op": "gain_icon_reward",
            "args": {
                "icon": raw_value.lower(), "scope": "all_players",
                "reward": "appeal", "per_icon": 1, "maximum": 8,
            },
            "timing": ABILITY_TIMING,
        }]
    if key == "inventive_bear":
        return [{
            "op": "gain_icon_reward",
            "args": {
                "icon": "bear", "scope": "all_players",
                "reward": "x_token", "per_icon": 1, "maximum": 3,
            },
            "timing": ABILITY_TIMING,
        }]
    if key == "inventive_primary":
        return [{
            "op": "gain_tiered_icon_reward",
            "args": {
                "icon": "primate", "scope": "actor", "reward": "x_token",
                "thresholds": [1, 3, 5], "rewards": [1, 2, 3],
            },
            "timing": ABILITY_TIMING,
        }]
    boost_actions = {
        "boost_animal": "animals",
        "boost_card": "cards",
        "boost_building": "build",
        "boost_association": "association",
        "boost_sponsors": "sponsors",
    }
    if key in boost_actions:
        return [{
            "op": "reposition_action_card",
            "args": {
                "action": boost_actions[key],
                "target_slots": [1, 5],
                "optional": True,
            },
            "timing": "after_finishing",
        }]
    extra_actions = {
        "action_association": "association",
        "action_sponsors": "sponsors",
        "action_cards": "cards",
        "action_building": "build",
    }
    if key in extra_actions:
        return [{
            "op": "grant_extra_action",
            "args": {"action": extra_actions[key]},
            "timing": "after_finishing",
        }]
    if key == "sun_bathing" and value is not None:
        return [{
            "op": "sell_hand_cards", "args": {"maximum": value},
            "timing": ABILITY_TIMING,
        }]
    if key == "pouch" and value is not None:
        return [{
            "op": "tuck_hand_cards", "args": {"maximum": value},
            "timing": ABILITY_TIMING,
        }]
    if key == "hunter" and value is not None:
        return [{
            "op": "reveal_keep_animal", "args": {"draw": value, "keep": 1},
            "timing": ABILITY_TIMING,
        }]
    if key == "perception_4":
        return [{
            "op": "draw_keep_cards", "args": {"draw": 4, "keep": 2},
            "timing": ABILITY_TIMING,
        }]
    if key in {"snapping_1", "snapping_2"}:
        return [
            {"op": "take_display_card", "args": {}, "timing": ABILITY_TIMING}
            for _ in range(1 if key == "snapping_1" else 2)
        ]
    if key == "scavenging" and value is not None:
        return [{
            "op": "scavenge_discard", "args": {"draw": value, "keep": 1},
            "timing": ABILITY_TIMING,
        }]
    if key == "digging" and value is not None:
        return [{
            "op": "dig_cards", "args": {"maximum": value},
            "timing": ABILITY_TIMING,
        }]
    if key == "venom" and value is not None:
        return [{
            "op": "apply_interaction_tokens",
            "args": {"token": "venom", "amount": value, "track_mode": "appeal"},
            "timing": "interaction",
        }]
    if key == "constriction":
        return [{
            "op": "apply_interaction_tokens",
            "args": {"token": "constriction", "track_mode": "appeal_and_conservation"},
            "timing": "interaction",
        }]
    if key == "clever":
        return [{
            "op": "reposition_action_card",
            "args": {"target_slot": 1, "optional": True},
            "timing": "after_finishing",
        }]
    if key == "determination":
        return [{
            "op": "grant_extra_action",
            "args": {"excluded_action": "animals"},
            "timing": "after_finishing",
        }]
    if key == "resistance":
        return [{
            "op": "draw_keep_final_scoring",
            "args": {"draw": 2, "keep": 1},
            "timing": ABILITY_TIMING,
        }]
    if key == "sponsor_magnet":
        return [
            {
                "op": "take_display_sponsors", "args": {},
                "timing": ABILITY_TIMING,
            },
            {
                "op": "refill_card_display", "args": {"target_size": 6},
                "timing": "after_finishing",
            },
        ]
    if key == "full_throated":
        return [{
            "op": "gain_association_worker", "args": {"amount": 1},
            "timing": ABILITY_TIMING,
        }]
    if key == "flock_animal" and value is not None:
        # Enclosure sharing changes legal accommodation rather than resolving
        # as a queued effect. animals_action consumes the printed minimum size.
        return []
    if key == "assertion":
        return [{
            "op": "take_base_project", "args": {}, "timing": ABILITY_TIMING,
        }]
    if key == "dominance":
        return [{
            "op": "introduce_base_project",
            "args": {"project_id": "ark-nova:base-project-108"},
            "timing": ABILITY_TIMING,
        }]
    if key == "posturing" and value is not None:
        return [{
            "op": "place_free_building",
            "args": {"building_types": ["kiosk", "pavilion"], "maximum": value},
            "timing": ABILITY_TIMING,
        }]
    if key == "peacocking":
        return [{
            "op": "place_free_building",
            "args": {"building_types": ["large_bird_aviary"], "maximum": 1},
            "timing": ABILITY_TIMING,
        }]
    multiplier_actions = {
        "multiplier_animal": "animals",
        "multiplier_card": "cards",
        "multiplier_building": "build",
        "multiplier_association": "association",
        "multiplier_sponsors": "sponsors",
    }
    if key in multiplier_actions:
        return [{
            "op": "add_action_token",
            "args": {"action": multiplier_actions[key], "token": "multiplier"},
            "timing": ABILITY_TIMING,
        }]
    return None


def compile_animal_effects(row: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Compile printed track rewards and the currently supported abilities."""
    effects: list[dict[str, Any]] = []
    for field, track in (
        ("appeal", "appeal"),
        ("reputation", "reputation"),
        ("conservation", "conservation"),
    ):
        amount = row.get(field, 0)
        if isinstance(amount, int) and not isinstance(amount, bool) and amount > 0:
            effects.append({
                "op": "move_track",
                "args": {"track": track, "amount": amount},
                "timing": ABILITY_TIMING,
            })
    unresolved = []
    for ability in row.get("abilities", []):
        compiled = compile_animal_ability(ability)
        if compiled is None:
            unresolved.append(str(ability.get("key", "unknown")))
        else:
            effects.extend(deepcopy(compiled))
    return effects, unresolved
