"""Conservation Project eligibility, claiming, and reward resolution."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from ..mechanics import axial_hex_neighbors
from .cards import printed_icon_counts
from .content import ContentEntry
from .semantics import EvaluationContext, SemanticEngine, SemanticRuleError
from .state import clone_state


def add_project_to_state(
    state: dict[str, Any], entry: ContentEntry, *, base: bool,
    instance_id: str | None = None,
) -> dict[str, Any]:
    if entry.kind not in {"base_conservation_project", "zoo_conservation_project"}:
        raise SemanticRuleError("only conservation projects may enter the project display")
    next_state = clone_state(state)
    if any(project["id"] == entry.id for project in next_state["conservation_projects"]):
        raise SemanticRuleError(f"conservation project is already displayed: {entry.id}")
    if not base:
        maximum = {1: 2, 2: 2, 3: 3, 4: 4}[next_state["player_count"]]
        zoo_projects = [project for project in next_state["conservation_projects"] if not project["base"]]
        if len(zoo_projects) >= maximum:
            oldest = zoo_projects[-1]
            next_state["conservation_projects"] = [
                project for project in next_state["conservation_projects"]
                if project["id"] != oldest["id"]
            ]
            for claim in oldest["claims"]:
                next_state["players"][claim["seat"]]["project_tokens_supply"] += 1
            next_state["zoo_discard"].append({
                "id": oldest.get("instance_id", oldest["id"]),
                "entry_id": oldest["id"],
                "kind": "conservation_project",
            })
    next_state["conservation_projects"].insert(0, {
        "id": entry.id,
        "instance_id": instance_id or entry.id,
        "base": base,
        "claims": [],
        "blocked_levels": [],
    })
    return next_state


def install_base_projects(
    state: dict[str, Any], entries: list[ContentEntry] | tuple[ContentEntry, ...],
) -> dict[str, Any]:
    """Install the official face-up base-project row and two-player blocks."""
    expected = 4 if state["player_count"] == 4 else 3
    if len(entries) != expected or any(
        entry.kind != "base_conservation_project" for entry in entries
    ):
        raise SemanticRuleError(f"base-project setup requires exactly {expected} entries")
    if state["conservation_projects"]:
        raise SemanticRuleError("base projects can only be installed into an empty display")
    next_state = clone_state(state)
    next_state["conservation_projects"] = [
        {"id": entry.id, "base": True, "claims": [], "blocked_levels": []}
        for entry in entries
    ]
    if state["player_count"] == 2:
        for project, level_id in zip(
            next_state["conservation_projects"], ("high", "middle", "low"),
        ):
            project["blocked_levels"].append(level_id)
    return next_state


def legal_project_levels(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    entry: ContentEntry,
) -> list[dict[str, Any]]:
    # Pending imported project faces are deliberately fail-closed until P5
    # supplies executable levels.  Direct support still rejects malformed
    # compiled content through ``_project_levels``.
    if not isinstance(entry.facts.get("levels"), list):
        return []
    options = legal_project_support_options(engine, state, seat, entry)
    by_level: dict[str, dict[str, Any]] = {}
    for option in options:
        by_level.setdefault(option["id"], {
            key: deepcopy(value) for key, value in option.items()
            if key not in {"release_animal_id", "release_enclosure_id"}
        })
    return list(by_level.values())


def legal_project_support_options(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    entry: ContentEntry,
) -> list[dict[str, Any]]:
    """Return exact support choices, including Release animal/enclosure pairs."""
    if not isinstance(entry.facts.get("levels"), list):
        return []
    project = next(
        (project for project in state["conservation_projects"] if project["id"] == entry.id),
        None,
    )
    if project is None or state["players"][seat]["project_tokens_available"] <= 0:
        return []
    repeat_release = (
        entry.facts.get("project_type") == "release"
        and any(
            modifier.get("kind") == "repeat_release_projects"
            for modifier in state["players"][seat].get("modifiers", [])
        )
    )
    if not repeat_release and any(claim["seat"] == seat for claim in project["claims"]):
        return []
    levels = _project_levels(entry)
    claimed_levels = {
        *project.get("blocked_levels", []),
        *(claim["level_id"] for claim in project["claims"]),
    }
    card = {"id": entry.id, "kind": entry.kind, "facts": dict(entry.facts)}
    context = EvaluationContext(state=state, actor_seat=seat, card=card)
    result = []
    for level in levels:
        if level["id"] in claimed_levels:
            continue
        release_rule = entry.facts.get("release_levels", {}).get(level["id"])
        if isinstance(release_rule, Mapping):
            for option in _release_options(state["players"][seat], level, release_rule):
                result.append(option)
            continue
        if isinstance(entry.facts.get("breeding_icon"), str):
            normal = _has_breeding_match(
                state["players"][seat], str(entry.facts["breeding_icon"]),
            )
        else:
            normal = all(
                engine.evaluate(requirement, context) for requirement in level["requirements"]
            )
        wildcard_instance_id = None if normal or not project["base"] else _wildcard_instance_for(
            engine, state, seat, level["requirements"], context,
        )
        if normal or wildcard_instance_id is not None:
            result.append({
                "id": level["id"],
                "conservation": level["conservation"],
                "reputation": level["reputation"],
                "wildcard_instance_id": wildcard_instance_id,
            })
    return result


def legal_project_token_choices(player: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return uncovered player-board tokens and both legal timing choices."""
    if int(player.get("project_tokens_available", 0)) < 1:
        return []
    return [
        {
            "slot_id": slot["id"],
            "recurring": bool(slot["recurring"]),
            "timing": timing,
        }
        for slot in player.get("project_token_slots", [])
        if not slot.get("claimed")
        for timing in ("before", "after")
    ]


def legal_new_project_levels(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    entry: ContentEntry,
) -> list[dict[str, Any]]:
    """Return support levels after introducing a project from a card zone.

    Introducing a zoo project happens before it is supported.  Staging the
    project through the same public transition used by the real action keeps
    project-display capacity and returned conservation tokens authoritative.
    """
    if (
        entry.kind not in {"zoo_conservation_project", "base_conservation_project"}
        or not isinstance(entry.facts.get("levels"), list)
    ):
        return []
    if any(project["id"] == entry.id for project in state["conservation_projects"]):
        return []
    staged = add_project_to_state(dict(state), entry, base=False)
    return legal_project_levels(engine, staged, seat, entry)


def legal_new_project_support_options(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    entry: ContentEntry,
) -> list[dict[str, Any]]:
    """Return exact choices after staging a newly introduced zoo project."""
    if (
        entry.kind not in {"zoo_conservation_project", "base_conservation_project"}
        or not isinstance(entry.facts.get("levels"), list)
        or any(project["id"] == entry.id for project in state["conservation_projects"])
    ):
        return []
    staged = add_project_to_state(dict(state), entry, base=False)
    return legal_project_support_options(engine, staged, seat, entry)


def support_project(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    entry: ContentEntry,
    level_id: str,
    *,
    token_bonus_effects: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] = (),
    token_bonus_timing: str = "before",
    release_animal_id: str | None = None,
    release_enclosure_id: str | None = None,
    introduction_effects: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] = (),
    token_slot_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Claim one available level and resolve map-token bonus before or after reward."""
    if token_bonus_timing not in {"before", "after"}:
        raise SemanticRuleError("project token bonus timing must be before or after")
    options = legal_project_support_options(engine, state, seat, entry)
    selected = next((
        option for option in options
        if option["id"] == level_id
        and option.get("release_animal_id") == release_animal_id
        and option.get("release_enclosure_id") == release_enclosure_id
    ), None)
    if selected is None:
        raise SemanticRuleError("conservation project level is not legal for this player")
    next_state = clone_state(state)
    project = next(project for project in next_state["conservation_projects"] if project["id"] == entry.id)
    player = next_state["players"][seat]
    wildcard_instance_id = selected.get("wildcard_instance_id")
    if wildcard_instance_id is not None:
        wildcard_card = next(
            (card for card in player["played_cards"] if card.get("id") == wildcard_instance_id),
            None,
        )
        if wildcard_card is None or int(wildcard_card.get("stored_tokens", 0)) < 1:
            raise SemanticRuleError("base-project wildcard token is no longer available")
        wildcard_card["stored_tokens"] -= 1
    automatic_bonus: list[Mapping[str, Any]] = []
    token_slot = None
    if token_slot_id is not None:
        token_slot = next((
            slot for slot in player.get("project_token_slots", [])
            if slot.get("id") == token_slot_id and not slot.get("claimed")
        ), None)
        if token_slot is None:
            raise SemanticRuleError("conservation-project player token is unavailable")
        token_slot["claimed"] = True
        automatic_bonus = _project_token_effects(token_slot_id, token_bonus_timing)
        if token_slot["recurring"]:
            player["modifiers"].append({
                "id": f"project-token:{token_slot_id}",
                "source_id": f"project-token:{token_slot_id}",
                "trigger": "income",
                "condition": None,
                "effects": _project_token_effects(token_slot_id, "income"),
                "kind": "project_token_income",
            })
    player["project_tokens_available"] -= 1
    player["supported_projects"].append(entry.id)
    project["claims"].append({
        "seat": seat, "level_id": level_id,
        **({"token_slot_id": token_slot_id} if token_slot_id else {}),
        **({"wildcard_instance_id": wildcard_instance_id} if wildcard_instance_id else {}),
    })
    release_events: list[dict[str, Any]] = []
    if release_animal_id is not None:
        release_events.append(_release_animal(
            next_state, seat, release_animal_id, str(release_enclosure_id), entry.id,
        ))
    level = selected
    reward_effects = [
        {"op": "move_track", "timing": "on_support", "args": {
            "track": "conservation", "amount": level["conservation"],
        }},
    ]
    if level["reputation"]:
        reward_effects.append({"op": "move_track", "timing": "on_support", "args": {
            "track": "reputation", "amount": level["reputation"],
        }})
    entry_effects = [effect for effect in entry.effects if effect.get("timing") == "on_support"]
    trigger = {
        "op": "trigger_project_supported", "timing": "on_support",
        "args": {"release": entry.facts.get("project_type") == "release"},
    }
    bonus = [*automatic_bonus, *list(token_bonus_effects)]
    intro = [deepcopy(dict(effect)) for effect in introduction_effects]
    effects = [*intro, *bonus, *reward_effects, *entry_effects, trigger] if token_bonus_timing == "before" else [
        *intro, *reward_effects, *entry_effects, *bonus, trigger,
    ]
    card = {"id": entry.id, "kind": entry.kind, "facts": deepcopy(dict(entry.facts))}
    next_state, resolved = engine.start_effects(
        next_state, seat, effects, source_id=entry.id, card=card,
    )
    return next_state, [*release_events, {
        "type": "conservation_project_supported",
        "seat": seat,
        "project_id": entry.id,
        "level_id": level_id,
        "token_bonus_timing": token_bonus_timing,
        "wildcard_instance_id": wildcard_instance_id,
        "release_animal_id": release_animal_id,
        "release_enclosure_id": release_enclosure_id,
        "token_slot_id": token_slot_id,
    }, *resolved]


def _project_token_effects(slot_id: str, timing: str) -> list[dict[str, Any]]:
    definitions: dict[str, tuple[str, dict[str, Any]]] = {
        "card": ("take_map_reward_card", {}),
        "enclosure-2": ("place_free_building", {
            "building_types": ["standard_enclosure_2"], "maximum": 1,
        }),
        "money-5": ("gain_money", {"amount": 5}),
        "conservation-1": ("move_track", {"track": "conservation", "amount": 1}),
        "worker-1": ("gain_association_worker", {"amount": 1}),
        "money-12": ("gain_money", {"amount": 12}),
        "x-3": ("gain_x_token", {"amount": 3}),
    }
    if slot_id not in definitions:
        raise SemanticRuleError(f"unknown conservation-project token slot: {slot_id}")
    op, args = definitions[slot_id]
    effect_timing = "income" if timing == "income" else "on_support"
    return [{"op": op, "args": deepcopy(args), "timing": effect_timing}]


def _has_breeding_match(player: Mapping[str, Any], icon: str) -> bool:
    partner_zoos = {
        value if isinstance(value, str) else value.get("continent")
        for value in player["partner_zoos"]
    }
    return any(
        card.get("kind") == "animal"
        and int(card.get("facts", {}).get("icons", {}).get(icon, 0)) > 0
        and bool(set(card.get("facts", {}).get("continents", [])) & partner_zoos)
        for card in player["played_cards"]
        if isinstance(card.get("facts"), Mapping)
    )


def _release_options(
    player: Mapping[str, Any], level: Mapping[str, Any], rule: Mapping[str, Any],
) -> list[dict[str, Any]]:
    icon = rule.get("icon")
    minimum = rule.get("minimum_size")
    maximum = rule.get("maximum_size")
    if (
        not isinstance(icon, str)
        or not isinstance(minimum, int) or isinstance(minimum, bool)
        or not isinstance(maximum, int) or isinstance(maximum, bool)
    ):
        raise SemanticRuleError("release-project selector metadata is malformed")
    result: list[dict[str, Any]] = []
    for card in player["played_cards"]:
        facts = card.get("facts")
        if card.get("kind") != "animal" or not isinstance(facts, Mapping):
            continue
        size = facts.get("enclosure_size")
        if (
            not isinstance(size, int) or isinstance(size, bool)
            or not minimum <= size <= maximum
            or int(facts.get("icons", {}).get(icon, 0)) < 1
        ):
            continue
        for building_id in _release_enclosure_ids(player, card):
            result.append({
                "id": level["id"],
                "conservation": level["conservation"],
                "reputation": level["reputation"],
                "wildcard_instance_id": None,
                "release_animal_id": card["id"],
                "release_enclosure_id": building_id,
            })
    return result


def _release_enclosure_ids(
    player: Mapping[str, Any], card: Mapping[str, Any],
) -> list[str]:
    facts = card["facts"]
    special = facts.get("special_enclosure")
    if isinstance(special, str) and special:
        name, _, raw_space = special.rpartition(" ")
        building_type = {
            "Reptile House": "reptile_house",
            "Large Bird Aviary": "large_bird_aviary",
            "Petting Zoo": "petting_zoo",
        }.get(name)
        if building_type is not None:
            try:
                space = int(raw_space)
            except ValueError as error:
                raise SemanticRuleError("special-enclosure release fact is malformed") from error
            special_ids = [
                building["id"] for building in player["map"]["buildings"]
                if building.get("type") == building_type
                and int(building.get("used_capacity", 0)) >= space
            ]
            if special_ids:
                return special_ids
    standards = [
        building for building in player["map"]["buildings"]
        if building.get("type") == "standard_enclosure"
        and building.get("occupied")
        and int(building.get("size", 0)) >= int(facts.get("enclosure_size", 0))
    ]
    fully_valid = [
        building for building in standards
        if _release_terrain_met(player, building, facts)
    ]
    candidates = fully_valid or standards
    if not candidates and "flock_animal" in facts.get("compiled_ability_keys", []):
        candidates = [
            building for building in player["map"]["buildings"]
            if building.get("type") == "standard_enclosure" and building.get("occupied")
        ]
    if not candidates:
        return []
    smallest = min(int(building["size"]) for building in candidates)
    return [building["id"] for building in candidates if int(building["size"]) == smallest]


def _release_terrain_met(
    player: Mapping[str, Any], building: Mapping[str, Any], facts: Mapping[str, Any],
) -> bool:
    footprint = {(cell["q"], cell["r"]) for cell in building["cells"]}
    adjacent = set().union(*(axial_hex_neighbors(cell) for cell in footprint))
    for terrain in ("rock", "water"):
        needed = int(facts.get(f"{terrain}_requirement", 0) or 0)
        cells = {
            (cell["q"], cell["r"]) for cell in player["map"]["cells"]
            if cell["terrain"] == terrain and (cell["q"], cell["r"]) not in footprint
        }
        if len(adjacent & cells) < needed:
            return False
    return True


def _release_animal(
    state: dict[str, Any], seat: int, animal_id: str, enclosure_id: str,
    project_id: str,
) -> dict[str, Any]:
    player = state["players"][seat]
    card = next(card for card in player["played_cards"] if card.get("id") == animal_id)
    building = next(
        building for building in player["map"]["buildings"]
        if building.get("id") == enclosure_id
    )
    facts = card["facts"]
    if building["type"] == "standard_enclosure":
        displaced = list(building.get("animal_ids", []))
        building["occupied"] = False
        building["used_capacity"] = 0
        building["animal_ids"] = []
        for other in player["played_cards"]:
            if other.get("id") in displaced and other.get("id") != animal_id:
                other["enclosure_id"] = None
    else:
        special = str(facts.get("special_enclosure", ""))
        try:
            space = int(special.rpartition(" ")[2])
        except ValueError as error:
            raise SemanticRuleError("special-enclosure release fact is malformed") from error
        building["used_capacity"] = max(0, int(building.get("used_capacity", 0)) - space)
        building["occupied"] = building["used_capacity"] >= int(building["size"])
        building["animal_ids"] = [
            value for value in building.get("animal_ids", []) if value != animal_id
        ]
    printed_appeal = int(facts.get("appeal", 0) or 0)
    old_appeal = player["tracks"]["appeal"]
    player["tracks"]["appeal"] = max(0, old_appeal - printed_appeal)
    _remove_counts(player["tags"], facts.get("tags", []))
    _remove_counts(player["icons"], printed_icon_counts(facts))
    tucked = list(card.get("tucked_cards", []))
    state["zoo_discard"].extend(tucked)
    player["played_cards"].remove(card)
    remaining_same_face = any(
        other.get("entry_id") == card.get("entry_id") for other in player["played_cards"]
    )
    player["modifiers"] = [
        modifier for modifier in player.get("modifiers", [])
        if modifier.get("source_instance_id") != animal_id
        and not (
            not remaining_same_face and modifier.get("source_id") == card.get("entry_id")
        )
    ]
    state["zoo_discard"].append({
        "id": animal_id,
        "entry_id": card.get("entry_id", animal_id),
        "kind": "animal",
    })
    return {
        "type": "animal_released",
        "seat": seat,
        "project_id": project_id,
        "animal_id": animal_id,
        "enclosure_id": enclosure_id,
        "appeal_lost": old_appeal - player["tracks"]["appeal"],
        "tucked_cards_discarded": len(tucked),
    }


def _remove_counts(target: dict[str, int], raw: Any) -> None:
    values = raw.items() if isinstance(raw, Mapping) else ((key, 1) for key in raw)
    for key, count in values:
        remaining = int(target.get(key, 0)) - int(count)
        if remaining > 0:
            target[key] = remaining
        else:
            target.pop(key, None)


def _wildcard_instance_for(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    requirements: list[Mapping[str, Any]],
    context: EvaluationContext,
) -> str | None:
    failures = []
    for requirement in requirements:
        if engine.evaluate(requirement, context):
            continue
        args = requirement.get("args", {})
        icon = args.get("icon")
        count = args.get("count", 1)
        if (
            requirement.get("op") != "has_icon"
            or not isinstance(icon, str)
            or not isinstance(count, int) or isinstance(count, bool)
            or int(state["players"][seat]["icons"].get(icon, 0)) + 1 < count
        ):
            return None
        failures.append(requirement)
    if len(failures) != 1:
        return None
    player = state["players"][seat]
    for modifier in player.get("modifiers", []):
        if modifier.get("kind") != "base_project_wildcard":
            continue
        instance_id = modifier.get("source_instance_id")
        card = next(
            (card for card in player["played_cards"] if card.get("id") == instance_id),
            None,
        )
        if card is not None and int(card.get("stored_tokens", 0)) > 0:
            return instance_id
    return None


def _project_levels(entry: ContentEntry) -> list[dict[str, Any]]:
    levels = entry.facts.get("levels")
    if not isinstance(levels, list) or not levels:
        raise SemanticRuleError(f"conservation project requires semantic levels: {entry.id}")
    result = []
    seen = set()
    for raw in levels:
        if not isinstance(raw, Mapping):
            raise SemanticRuleError("project level must be an object")
        level_id = raw.get("id")
        requirements = raw.get("requirements")
        conservation = raw.get("conservation")
        reputation = raw.get("reputation", 0)
        if not isinstance(level_id, str) or not level_id or level_id in seen:
            raise SemanticRuleError("project level IDs must be non-empty and unique")
        if not isinstance(requirements, list):
            raise SemanticRuleError("project level requirements must be an array")
        if (
            not isinstance(conservation, int) or isinstance(conservation, bool) or conservation < 0
            or not isinstance(reputation, int) or isinstance(reputation, bool) or reputation < 0
        ):
            raise SemanticRuleError("project level rewards must be non-negative integers")
        seen.add(level_id)
        result.append({
            "id": level_id,
            "requirements": requirements,
            "conservation": conservation,
            "reputation": reputation,
        })
    return result
