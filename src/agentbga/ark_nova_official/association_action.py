"""Concrete resolver for Association I/II tasks and donation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .actions import (
    complete_action_execution,
    current_action_execution,
    defer_after_finishing,
)
from .cards_action import reputation_display_limit
from .content import ContentEntry
from .projects import (
    add_project_to_state,
    legal_new_project_levels,
    legal_new_project_support_options,
    legal_project_levels,
    legal_project_support_options,
    legal_project_token_choices,
    support_project,
)
from .semantics import SemanticEngine, SemanticRuleError
from .state import clone_state, validate_semantic_state


_DISPLAY_REFILL_EFFECT = {
    "op": "refill_card_display",
    "timing": "after_finishing",
    "args": {"target_size": 6},
}


def legal_association_execution_actions(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    project_entries: Mapping[str, ContentEntry],
) -> list[dict[str, Any]]:
    """Enumerate legal Association tasks, rewards, donation, and finish."""
    try:
        execution, resolution = _association_context(state, seat)
    except SemanticRuleError:
        return []
    if state["resolution"]["queue"] or state["resolution"]["pending_choice"] is not None:
        return []
    if resolution is not None and resolution["pending_reward"] is not None:
        return _upgrade_reward_actions(state, seat)
    remaining = execution["spec"]["maximum_total_strength"] if resolution is None else resolution["remaining_strength"]
    used = set() if resolution is None else set(resolution["task_ids"])
    maximum_tasks = execution["spec"]["maximum_tasks"]
    at_limit = resolution is not None and maximum_tasks is not None and len(resolution["tasks"]) >= maximum_tasks
    result = [] if at_limit else _task_actions(
        engine, state, seat, project_entries, remaining,
        used if execution["spec"]["tasks_must_be_different"] else set(),
        bool(execution["upgraded"]),
    )
    if resolution is not None and resolution["tasks"]:
        if (
            execution["spec"]["donation_allowed"]
            and not resolution["donation_made"]
        ):
            cost = state["donation_costs"][min(
                len(state["donations_made"]), len(state["donation_costs"]) - 1,
            )]
            if state["players"][seat]["money"] >= cost:
                result.append({
                    "id": f"association:donate:{cost}",
                    "label": f"Donate {cost} money for 1 conservation",
                    "action": {"type": "make_association_donation", "cost": cost},
                })
        result.append({
            "id": "association:finish", "label": "Finish Association action",
            "action": {"type": "finish_association_action"},
        })
    return result


def apply_association_execution_action(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    project_entries: Mapping[str, ContentEntry],
    action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(action, Mapping) or not isinstance(action.get("type"), str):
        raise SemanticRuleError("Association execution action must contain a type")
    requested = dict(action)
    legal = [
        item["action"] for item in legal_association_execution_actions(
            engine, state, seat, project_entries,
        )
    ]
    if requested not in legal:
        raise SemanticRuleError("Association execution choice is not currently legal")
    if requested["type"] == "perform_association_task":
        return _perform_task(engine, state, seat, project_entries, requested)
    if requested["type"] == "upgrade_association_reward_card":
        return _take_upgrade_reward(state, seat, requested["action_card_id"])
    if requested["type"] == "make_association_donation":
        return _make_donation(engine, state, seat, requested["cost"])
    if requested["type"] == "finish_association_action":
        return _finish_association(engine, state, seat)
    raise SemanticRuleError(f"unknown Association action: {requested['type']}")


def _association_context(
    state: Mapping[str, Any], seat: int,
) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    execution = current_action_execution(state, seat)
    if execution["action"] != "association":
        raise SemanticRuleError("the active execution is not an Association action")
    resolution = state["turn"]["action_session"].get("association_resolution")
    if resolution is not None and not isinstance(resolution, Mapping):
        raise SemanticRuleError("invalid Association action resolution state")
    return execution, resolution


def _task_actions(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    seat: int,
    project_entries: Mapping[str, ContentEntry],
    remaining: int,
    excluded: set[str],
    upgraded: bool,
) -> list[dict[str, Any]]:
    player = state["players"][seat]
    result: list[dict[str, Any]] = []
    if remaining >= 2 and "gain-reputation" not in excluded:
        _append_if_workers(result, player, "gain-reputation", 2, {
            "task_id": "gain-reputation",
        })
    can_take_later_zoo = len(player["partner_zoos"]) < 2 or upgraded
    if remaining >= 3 and "partner-zoo" not in excluded and can_take_later_zoo:
        owned = {_asset_id(value, "continent") for value in player["partner_zoos"]}
        for continent, supply in state["association_board"]["partner_zoos"].items():
            if continent not in owned and _supply_available(supply):
                _append_if_workers(result, player, "partner-zoo", 3, {
                    "task_id": "partner-zoo", "continent": continent,
                })
    if remaining >= 4 and "university" not in excluded:
        owned = {_asset_id(value, "id") for value in player["universities"]}
        for university_id, supply in state["association_board"]["universities"].items():
            if university_id not in owned and _supply_available(supply):
                _append_if_workers(result, player, "university", 4, {
                    "task_id": "university", "university_id": university_id,
                })
    project_strength = _project_task_strength(player)
    if remaining >= project_strength and "conservation-project" not in excluded:
        for project in state["conservation_projects"]:
            entry = project_entries.get(project["id"])
            if entry is None:
                continue
            for level in legal_project_support_options(engine, state, seat, entry):
                fields = {
                    "task_id": "conservation-project",
                    "project_id": entry.id, "level_id": level["id"],
                }
                _copy_release_fields(fields, level)
                _append_project_token_variants(
                    result, player, project_strength, fields,
                    _project_choice_label("Support", entry, level),
                )
        displayed_ids = {project["id"] for project in state["conservation_projects"]}
        new_projects: list[tuple[Mapping[str, Any], str, int | None]] = [
            (card, "hand", None) for card in player["hand"]
        ]
        if upgraded:
            limit = reputation_display_limit(player["tracks"]["reputation"])
            new_projects.extend(
                (card, "display", position)
                for position, card in enumerate(state["card_display"])
                if position < limit
            )
        for card, source, display_position in new_projects:
            entry_id = card.get("entry_id", card.get("id"))
            entry = project_entries.get(entry_id) if isinstance(entry_id, str) else None
            if (
                entry is None or entry.kind not in {
                    "zoo_conservation_project", "base_conservation_project",
                }
                or entry.id in displayed_ids
            ):
                continue
            folder_cost = 0 if display_position is None else int(display_position) + 1
            if folder_cost > player["money"]:
                continue
            for level in legal_new_project_support_options(engine, state, seat, entry):
                fields = {
                    "task_id": "conservation-project",
                    "project_id": entry.id,
                    "level_id": level["id"],
                    "source": source,
                    "instance_id": _instance_id(card),
                    "folder_cost": folder_cost,
                }
                _copy_release_fields(fields, level)
                _append_project_token_variants(
                    result, player, project_strength, fields,
                    (
                    _project_choice_label("Introduce and support", entry, level)
                    + f" from {source}"
                    + (f" · pay folder {folder_cost}" if folder_cost else "")
                    ),
                )
    return result


def _append_if_workers(
    result: list[dict[str, Any]],
    player: Mapping[str, Any],
    task_id: str,
    strength: int,
    fields: Mapping[str, Any],
    *,
    label: str | None = None,
) -> None:
    workers = _worker_cost(player, task_id)
    if workers not in {1, 2} or player["association_workers"]["active"] < workers:
        return
    suffix = ":".join(str(value) for key, value in fields.items() if key != "task_id")
    result.append({
        "id": f"association:task:{task_id}{':' + suffix if suffix else ''}",
        "label": (
            f"{label} · strength {strength} · {workers} worker(s)"
            if label is not None
            else f"{task_id} · strength {strength} · {workers} worker(s)"
        ),
        "action": {
            "type": "perform_association_task", "strength": strength,
            "workers": workers, **dict(fields),
        },
    })


def _perform_task(
    engine: SemanticEngine,
    state: dict[str, Any],
    seat: int,
    project_entries: Mapping[str, ContentEntry],
    action: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    execution, old_resolution = _association_context(state, seat)
    next_state = clone_state(state)
    if old_resolution is None:
        next_state["turn"]["action_session"]["association_resolution"] = {
            "remaining_strength": execution["spec"]["maximum_total_strength"],
            "tasks": [], "task_ids": [], "pending_reward": None,
            "donation_made": False,
        }
    resolution = next_state["turn"]["action_session"]["association_resolution"]
    player = next_state["players"][seat]
    task_id = action["task_id"]
    player["association_workers"]["active"] -= action["workers"]
    player["association_workers"]["committed"].extend(
        {"task": task_id} for _ in range(action["workers"])
    )
    resolution["remaining_strength"] -= action["strength"]
    resolution["task_ids"].append(task_id)
    record = {
        key: deepcopy(value) for key, value in action.items()
        if key not in {"type"}
    }
    resolution["tasks"].append(record)
    events = [{
        "type": "association_task_performed", "seat": seat,
        "task_id": task_id, "strength": action["strength"], "workers": action["workers"],
    }]
    semantic_effects: list[dict[str, Any]] = []
    if task_id == "gain-reputation":
        semantic_effects.append(_track_effect("reputation", 2))
    elif task_id == "partner-zoo":
        _take_partner_zoo(next_state, seat, action["continent"], resolution, semantic_effects)
    elif task_id == "university":
        _take_university(next_state, seat, action["university_id"], resolution, semantic_effects)
    else:
        entry = project_entries[action["project_id"]]
        introduced = False
        if action.get("source") in {"hand", "display"}:
            source = str(action["source"])
            instance_id = str(action["instance_id"])
            card = _remove_zone_card(next_state, seat, source, instance_id)
            if card.get("entry_id", card.get("id")) != entry.id:
                raise SemanticRuleError("selected project card does not match its content entry")
            folder_cost = int(action.get("folder_cost", 0))
            player = next_state["players"][seat]
            player["money"] -= folder_cost
            if source == "display":
                next_state = _defer_display_refill(next_state, seat)
            next_state = add_project_to_state(
                next_state, entry, base=False, instance_id=instance_id,
            )
            introduced = True
            events.append({
                "type": "conservation_project_introduced",
                "seat": seat,
                "project_id": entry.id,
                "instance_id": instance_id,
                "source": source,
                "folder_cost": folder_cost,
            })
        next_state, project_events = support_project(
            engine, next_state, seat, entry, action["level_id"],
            release_animal_id=action.get("release_animal_id"),
            release_enclosure_id=action.get("release_enclosure_id"),
            introduction_effects=(
                entry.facts.get("introduction_effects", []) if introduced else []
            ),
            token_bonus_timing=str(action["token_bonus_timing"]),
            token_slot_id=str(action["token_slot_id"]),
        )
        return next_state, [*events, *project_events]
    if semantic_effects:
        next_state, semantic_events = engine.start_effects(
            next_state, seat, semantic_effects, source_id=f"association:{task_id}",
        )
        events.extend(semantic_events)
    validate_semantic_state(next_state)
    return next_state, events


def _take_partner_zoo(
    state: dict[str, Any], seat: int, continent: str,
    resolution: dict[str, Any], effects: list[dict[str, Any]],
) -> None:
    supply = state["association_board"]["partner_zoos"][continent]
    supply["available"] = 0
    if seat not in supply["owners"]:
        supply["owners"].append(seat)
    player = state["players"][seat]
    player["partner_zoos"].append(continent)
    count = len(player["partner_zoos"])
    if count == 2:
        resolution["pending_reward"] = "action_upgrade"
    elif count == 3 and player["association_workers"]["reserve"]:
        player["association_workers"]["reserve"] -= 1
        player["association_workers"]["active"] += 1
    elif count == 4:
        effects.append(_track_effect("conservation", 2))


def _take_university(
    state: dict[str, Any], seat: int, university_id: str,
    resolution: dict[str, Any], effects: list[dict[str, Any]],
) -> None:
    supply = state["association_board"]["universities"][university_id]
    supply["available"] = 0
    if seat not in supply["owners"]:
        supply["owners"].append(seat)
    player = state["players"][seat]
    player["universities"].append(university_id)
    icon_count = 2 if university_id == "research-2" else 1
    # ``research`` is retained as the presentation-facing counter while
    # ``science`` is the canonical card-semantics icon used by the imported
    # English dataset.  They represent the same printed icons.
    player["icons"]["research"] = player["icons"].get("research", 0) + icon_count
    player["icons"]["science"] = player["icons"].get("science", 0) + icon_count
    effects.append({
        "op": "trigger_icon_entered", "timing": "immediate",
        "args": {"icon": "science", "count": icon_count},
    })
    if university_id == "research-reputation":
        effects.append(_track_effect("reputation", 2))
    elif university_id == "research-hand-limit":
        player["hand_limit"] += 2
    count = len(player["universities"])
    if count == 2:
        resolution["pending_reward"] = "action_upgrade"
    elif count == 3:
        effects.append(_track_effect("conservation", 2))


def _upgrade_reward_actions(state: Mapping[str, Any], seat: int) -> list[dict[str, Any]]:
    return [{
        "id": f"association:reward:upgrade:{card['id']}",
        "label": f"Upgrade {card['action']}",
        "action": {
            "type": "upgrade_association_reward_card", "action_card_id": card["id"],
        },
    } for card in state["players"][seat]["action_cards"] if not card["upgraded"]]


def _take_upgrade_reward(
    state: dict[str, Any], seat: int, action_card_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    next_state = clone_state(state)
    card = next(
        card for card in next_state["players"][seat]["action_cards"]
        if card["id"] == action_card_id
    )
    card["upgraded"] = True
    next_state["turn"]["action_session"]["association_resolution"]["pending_reward"] = None
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "association_asset_action_card_upgraded", "seat": seat,
        "action_card_id": action_card_id,
    }]


def _make_donation(
    engine: SemanticEngine, state: dict[str, Any], seat: int, cost: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    next_state = clone_state(state)
    next_state["players"][seat]["money"] -= cost
    next_state["donations_made"].append({"seat": seat, "cost": cost})
    next_state["turn"]["action_session"]["association_resolution"]["donation_made"] = True
    next_state, events = engine.start_effects(next_state, seat, [
        _track_effect("conservation", 1),
    ], source_id="association:donation")
    return next_state, [{
        "type": "association_donation_made", "seat": seat, "cost": cost,
    }, *events]


def _finish_association(
    engine: SemanticEngine, state: dict[str, Any], seat: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolution = deepcopy(state["turn"]["action_session"]["association_resolution"])
    next_state = clone_state(state)
    del next_state["turn"]["action_session"]["association_resolution"]
    return complete_action_execution(engine, next_state, seat, {
        "performed": True, "tasks": resolution["tasks"],
        "donation_made": resolution["donation_made"],
    })


def _worker_cost(player: Mapping[str, Any], task_id: str) -> int:
    prior = sum(
        worker.get("task") == task_id
        for worker in player["association_workers"]["committed"]
    )
    return prior + 1


def _project_task_strength(player: Mapping[str, Any]) -> int:
    strengths = [5]
    strengths.extend(
        int(modifier["amount"])
        for modifier in player.get("modifiers", [])
        if modifier.get("kind") == "association_project_strength"
    )
    return min(strengths)


def _supply_available(supply: Any) -> bool:
    if isinstance(supply, Mapping):
        return bool(supply.get("available", 0))
    return bool(supply)


def _asset_id(value: Any, key: str) -> Any:
    return value if isinstance(value, str) else value.get(key) if isinstance(value, Mapping) else None


def _instance_id(card: Mapping[str, Any]) -> str:
    value = card.get("id")
    if not isinstance(value, str) or not value:
        raise SemanticRuleError("project card instances require stable IDs")
    return value


def _copy_release_fields(target: dict[str, Any], option: Mapping[str, Any]) -> None:
    for key in ("release_animal_id", "release_enclosure_id"):
        if key in option:
            target[key] = option[key]


def _append_project_token_variants(
    result: list[dict[str, Any]],
    player: Mapping[str, Any],
    strength: int,
    fields: Mapping[str, Any],
    label: str,
) -> None:
    for token in legal_project_token_choices(player):
        _append_if_workers(
            result, player, "conservation-project", strength,
            {
                **dict(fields),
                "token_slot_id": token["slot_id"],
                "token_bonus_timing": token["timing"],
            },
            label=(
                f"{label} · token {token['slot_id']} "
                f"{token['timing']} reward"
            ),
        )


def _project_choice_label(
    verb: str, entry: ContentEntry, option: Mapping[str, Any],
) -> str:
    label = f"{verb} {entry.display_title} at {option['id']}"
    if "release_animal_id" in option:
        label += (
            f" · release {option['release_animal_id']} using "
            f"{option['release_enclosure_id']}"
        )
    return label


def _remove_zone_card(
    state: dict[str, Any], seat: int, source: str, instance_id: str,
) -> dict[str, Any]:
    cards = state["players"][seat]["hand"] if source == "hand" else state["card_display"]
    matches = [card for card in cards if card.get("id") == instance_id]
    if len(matches) != 1:
        raise SemanticRuleError("selected project card is no longer in its source zone")
    cards.remove(matches[0])
    return matches[0]


def _defer_display_refill(state: dict[str, Any], seat: int) -> dict[str, Any]:
    session = state["turn"]["action_session"]
    if any(
        effect.get("op") == "refill_card_display"
        for effect in session["after_finishing_effects"]
    ):
        return state
    return defer_after_finishing(state, seat, [_DISPLAY_REFILL_EFFECT])


def _track_effect(track: str, amount: int) -> dict[str, Any]:
    return {"op": "move_track", "timing": "immediate", "args": {
        "track": track, "amount": amount,
    }}
