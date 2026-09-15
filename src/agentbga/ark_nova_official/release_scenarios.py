"""Per-face release scenarios for the Ark Nova base-game Map 0 pack.

The release ledger records one stable scenario ID for every card, bonus tile,
and the supported map.  This module is the executable registry behind those
IDs: it validates the face's closed semantic vocabulary and exercises the
runtime path appropriate to that component family.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from ..ark_nova_map import unique_sponsor_building_spec
from .cards import entry_is_eligible, play_entry_semantics
from .content import ContentEntry, ContentPack
from .final_scoring_effects import score_final_card
from .projects import add_project_to_state, legal_project_support_options
from .semantics import SemanticEngine
from .state import new_semantic_state, validate_semantic_state


RELEASE_SCENARIO_PREFIX = "ark-nova-map0-release"


def release_scenario_id(entry: ContentEntry) -> str:
    component = entry.official_component_id or entry.id.removeprefix("ark-nova:")
    return f"{RELEASE_SCENARIO_PREFIX}:{entry.kind}:{component}"


def run_release_scenario(
    pack: ContentPack, entry: ContentEntry,
) -> dict[str, Any]:
    """Execute one deterministic, family-specific release smoke scenario."""
    engine = SemanticEngine()
    for requirement in entry.requirements:
        engine.validate_predicate_vocabulary(requirement)
    for effect in entry.effects:
        engine.validate_effect_vocabulary(effect)

    if entry.kind in {"animal", "sponsor"}:
        result = _run_zoo_card(engine, entry)
    elif entry.kind in {"base_conservation_project", "zoo_conservation_project"}:
        result = _run_project(engine, entry)
    elif entry.kind == "final_scoring":
        result = _run_final_scoring(entry)
    elif entry.kind == "bonus_tile":
        result = _run_bonus_tile(engine, entry)
    elif entry.kind == "map":
        result = _run_map_zero(entry)
    else:
        raise AssertionError(f"no release scenario family for {entry.kind}: {entry.id}")
    return {"scenario_id": release_scenario_id(entry), "entry_id": entry.id, **result}


def run_pack_release_scenarios(pack: ContentPack) -> list[dict[str, Any]]:
    results = [
        run_release_scenario(pack, entry)
        for entries in pack.collections.values()
        for entry in entries
    ]
    ids = [result["scenario_id"] for result in results]
    if len(ids) != len(set(ids)):
        raise AssertionError("release scenario IDs must be unique")
    return results


def _maximal_state() -> dict[str, Any]:
    state = new_semantic_state(2, seed=20260828)
    state["phase"] = "active"
    state["status"] = "active"
    state["zoo_deck"] = [
        {"id": f"release-deck-{index}", "kind": "sponsor", "facts": {}}
        for index in range(40)
    ]
    state["zoo_discard"] = [
        {"id": f"release-discard-{index}", "kind": "sponsor", "facts": {}}
        for index in range(10)
    ]
    state["card_display"] = [
        {"id": f"release-display-{index}", "kind": "sponsor", "facts": {}}
        for index in range(6)
    ]
    all_icons = (
        "africa", "americas", "asia", "australia", "europe", "bear", "bird",
        "herbivore", "pet", "predator", "primate", "reptile", "science",
        "research", "rock", "water",
    )
    for player in state["players"]:
        player["money"] = 200
        player["x_tokens"] = 5
        # Several Sponsors use a maximum-25 Appeal prerequisite while other
        # prerequisites ask for a high Reputation value.
        player["tracks"].update({"appeal": 20, "conservation": 0, "reputation": 15})
        player["icons"].update({icon: 10 for icon in all_icons})
        player["tags"].update({icon: 10 for icon in all_icons})
        player["partner_zoos"] = [
            "africa", "americas", "asia", "australia", "europe",
        ]
        player["universities"] = [
            "research-2", "research-reputation", "research-hand-limit",
        ]
        player["association_workers"].update({"active": 4, "reserve": 0})
        for card in player["action_cards"]:
            card["upgraded"] = True
    return state


def _settle_choices(
    engine: SemanticEngine, state: dict[str, Any], *, maximum_steps: int = 200,
) -> tuple[dict[str, Any], int]:
    steps = 0
    while state["resolution"]["pending_choice"] is not None:
        if steps >= maximum_steps:
            raise AssertionError("release scenario did not close its semantic choices")
        choice = state["resolution"]["pending_choice"]
        legal = engine.legal_choice_actions(state, int(choice["seat"]))
        if not legal:
            raise AssertionError("release scenario exposed a choice without legal actions")
        # The first engine-generated action is deterministic and already obeys
        # the choice's min/max cardinality. Optional effects therefore select
        # their explicit stop/empty branch when available.
        action = legal[0]["action"]
        state, _ = engine.submit_choice(
            state, int(choice["seat"]), str(action["choice_id"]),
            list(action["option_ids"]),
        )
        steps += 1
    if state["resolution"]["queue"]:
        raise AssertionError("release scenario left unresolved semantic frames")
    validate_semantic_state(state)
    return state, steps


def _run_zoo_card(engine: SemanticEngine, entry: ContentEntry) -> dict[str, Any]:
    state = _maximal_state()
    if not entry_is_eligible(engine, state, 0, entry):
        raise AssertionError(f"maximal release fixture does not satisfy {entry.id}")
    state, events = play_entry_semantics(
        engine, state, 0, entry,
        instance_id=f"release-instance:{entry.official_component_id}",
    )
    state, choices = _settle_choices(engine, state)
    played = state["players"][0]["played_cards"]
    if not any(card.get("entry_id") == entry.id for card in played):
        raise AssertionError(f"release scenario did not retain played card {entry.id}")
    unique = entry.facts.get("unique_building")
    if unique is not None:
        if not isinstance(unique, Mapping):
            raise AssertionError(f"unique building metadata is malformed: {entry.id}")
        component = int(str(entry.official_component_id))
        spec = unique_sponsor_building_spec(component)
        if spec is None or int(spec["size"]) != int(unique["size"]):
            raise AssertionError(f"unique building registry mismatch: {entry.id}")
    return {
        "family": entry.kind,
        "events": len(events),
        "choices_resolved": choices,
        "unique_building_checked": unique is not None,
    }


def _project_fixture(entry: ContentEntry) -> dict[str, Any]:
    state = _maximal_state()
    state = add_project_to_state(
        state, entry, base=entry.kind == "base_conservation_project",
    )
    player = state["players"][0]
    # Cover icon/continent Breeding Programs and the small/large animal
    # conservation faces with actual played Animal records, not only counters.
    for index in range(8):
        icon = ("bird", "predator", "reptile", "herbivore", "primate")[index % 5]
        player["played_cards"].append({
            "id": f"project-small-{index}", "kind": "animal",
            "facts": {
                "enclosure_size": 2,
                "continents": ["europe"],
                "animal_categories": [icon],
                "icons": {icon: 1},
            },
        })
    for index in range(4):
        player["played_cards"].append({
            "id": f"project-large-{index}", "kind": "animal",
            "facts": {
                "enclosure_size": 4,
                "continents": ["europe"],
                "animal_categories": ["herbivore"],
                "icons": {"herbivore": 1},
            },
        })
    if entry.facts.get("project_type") == "release":
        icon = str(entry.facts["release_icon"])
        for size in range(1, 6):
            animal_id = f"release-animal-{size}"
            enclosure_id = f"release-enclosure-{size}"
            player["played_cards"].append({
                "id": animal_id,
                "entry_id": animal_id,
                "kind": "animal",
                "facts": {
                    "enclosure_size": size,
                    "continents": [icon] if icon in {
                        "africa", "americas", "asia", "australia", "europe",
                    } else [],
                    "animal_categories": [icon] if icon not in {
                        "africa", "americas", "asia", "australia", "europe",
                    } else [],
                    "appeal": size,
                    "icons": {icon: 1},
                },
                "enclosure_id": enclosure_id,
            })
            player["map"]["buildings"].append({
                "id": enclosure_id,
                "type": "standard_enclosure",
                "size": size,
                "occupied": True,
                "used_capacity": size,
                "animal_ids": [animal_id],
                "cells": [],
            })
    return state


def _run_project(engine: SemanticEngine, entry: ContentEntry) -> dict[str, Any]:
    levels = entry.facts.get("levels")
    if not isinstance(levels, list) or not levels:
        raise AssertionError(f"release project has no compiled levels: {entry.id}")
    for level in levels:
        for requirement in level.get("requirements", []):
            engine.validate_predicate_vocabulary(requirement)
    state = _project_fixture(entry)
    options = legal_project_support_options(engine, state, 0, entry)
    if not options:
        raise AssertionError(f"release project has no executable support option: {entry.id}")
    return {
        "family": entry.kind,
        "compiled_levels": len(levels),
        "legal_support_options": len(options),
    }


def _run_final_scoring(entry: ContentEntry) -> dict[str, Any]:
    state = _maximal_state()
    player = state["players"][0]
    player["played_cards"].extend({
        "id": f"score-animal-{index}", "kind": "animal",
        "facts": {
            "enclosure_size": 4 if index < 4 else 1,
            "animal_categories": ["bird"], "continents": ["europe"],
            "icons": {"rock": 1, "water": 1},
        },
    } for index in range(8))
    card = {"id": entry.id, "entry_id": entry.id, "facts": deepcopy(dict(entry.facts))}
    scored = score_final_card(state, 0, card)
    if not isinstance(scored, Mapping) or int(scored.get("conservation", -1)) < 0:
        raise AssertionError(f"Final Scoring face is not executable: {entry.id}")
    return {
        "family": entry.kind,
        "conservation": int(scored["conservation"]),
        "mode": entry.facts["scoring"]["mode"],
    }


def _run_bonus_tile(engine: SemanticEngine, entry: ContentEntry) -> dict[str, Any]:
    state = _maximal_state()
    state, events = engine.start_effects(
        state, 0, list(entry.effects), source_id=entry.id,
    )
    state, choices = _settle_choices(engine, state)
    return {
        "family": entry.kind,
        "events": len(events),
        "choices_resolved": choices,
    }


def _run_map_zero(entry: ContentEntry) -> dict[str, Any]:
    if entry.official_component_id != "0" or entry.facts.get("map_id") != "0":
        raise AssertionError("released Map 0 pack may contain only the Map 0 face")
    state = new_semantic_state(2, seed=0)
    validate_semantic_state(state)
    map_state = state["players"][0]["map"]
    return {
        "family": entry.kind,
        "cells": len(map_state["cells"]),
        "starter_buildings": len(map_state["buildings"]),
    }
