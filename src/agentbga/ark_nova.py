"""Deterministic Ark Nova controlled-core rules plugin.

The turn, action-card, Break, hidden-information, and decision-step machinery is
playable end to end. Zoo cards are generated research fixtures with no copied
publisher text or artwork; their special abilities are intentionally deferred to
the data-driven card-effect milestone.
"""

from __future__ import annotations

from copy import deepcopy
from itertools import combinations
import hashlib
import json
import random
from typing import Any

from .game import GameRuleError


RULES_VERSION = "base-1.2-controlled-core.1"
ACTION_TYPES = ("animals", "cards", "build", "association", "sponsors")
CONTINENTS = ("africa", "asia", "australia", "europe", "americas")
ANIMAL_TAGS = ("bird", "primate", "predator", "reptile", "herbivore", "bear", "petting_zoo")
HEX_DIRECTIONS = ((1, 0), (0, 1), (-1, 1))
BREAK_LIMITS = {2: 10, 3: 12, 4: 14}


class RuleError(GameRuleError):
    pass


def describe() -> dict[str, Any]:
    return {
        "id": "ark_nova",
        "name": "Ark Nova",
        "rules_version": RULES_VERSION,
        "players": {"minimum": 2, "maximum": 4},
        "hidden_information": True,
        "implementation_status": "controlled_core",
        "runnable": True,
        "decision_model": "player_turn_with_multiple_decision_steps",
        "action_types": list(ACTION_TYPES),
        "map": "symmetric_beginner_map_a_schematic",
        "content_scope": (
            "complete controlled-core match using generated research cards; "
            "publisher card text, special abilities, and verified map footprints are deferred"
        ),
        "rules_sources": [
            "Ark Nova Rulebook, English, version 1.2",
            "Ark Nova FAQ/Errata, English, version 2",
        ],
        "win_condition": (
            "Controlled-core threshold or turn limit, followed by deterministic ranking. "
            "Published final-scoring cards are deferred."
        ),
    }


def _research_zoo_cards() -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for index in range(1, 129):
        cards.append({
            "id": f"research-animal-{index:03d}", "card_type": "animal",
            "tags": [ANIMAL_TAGS[(index - 1) % len(ANIMAL_TAGS)]],
            "continent": CONTINENTS[(index - 1) % len(CONTINENTS)],
            "cost": 4 + (index % 10), "enclosure_size": 1 + (index % 5),
            "appeal": 2 + (index % 5), "conservation": 1 if index % 17 == 0 else 0,
            "reputation": 1 if index % 13 == 0 else 0,
            "implementation": "controlled_no_special_ability",
        })
    for index in range(1, 65):
        cards.append({
            "id": f"research-sponsor-{index:03d}", "card_type": "sponsor", "tags": [],
            "level": 1 + (index % 5), "appeal": 1 if index % 3 == 0 else 0,
            "income": 1 + (index % 3), "implementation": "controlled_income_effect",
        })
    for index in range(1, 21):
        cards.append({
            "id": f"research-project-{index:03d}", "card_type": "conservation_project",
            "tags": [(*ANIMAL_TAGS, *CONTINENTS)[(index - 1) % (len(ANIMAL_TAGS) + len(CONTINENTS))]],
            "implementation": "controlled_project_reference",
        })
    return cards


def _final_cards() -> list[dict[str, Any]]:
    return [{"id": f"research-final-{index:02d}", "implementation": "scoring_deferred"}
            for index in range(1, 12)]


def _base_projects() -> list[dict[str, Any]]:
    tags = (*ANIMAL_TAGS, *CONTINENTS)
    return [{
        "id": f"research-base-{index:02d}", "tag": tags[index - 1],
        "levels": [2, 4, 5], "claims": [], "implementation": "controlled_tag_project",
    } for index in range(1, 13)]


def _bonus_tiles() -> list[dict[str, Any]]:
    return [{"id": f"research-bonus-{index:02d}", "implementation": "effect_deferred"}
            for index in range(1, 10)]


def _map_a() -> dict[str, Any]:
    cells = []
    water = {(-2, 0), (2, 0)}
    rock = {(0, -2), (0, 2)}
    starter = {(-1, 0), (0, 0), (1, 0)}
    for q in range(-3, 4):
        for r in range(-3, 4):
            if abs(q + r) <= 3:
                terrain = "water" if (q, r) in water else "rock" if (q, r) in rock else "buildable"
                cells.append({"q": q, "r": r, "terrain": terrain})
    return {
        "id": "map-a", "name": "Beginner Map A",
        "geometry_status": "schematic_controlled_footprints",
        "cells": cells,
        "buildings": [{
            "id": "starting-enclosure-3", "type": "standard_enclosure", "size": 3,
            "occupied": False, "cells": [{"q": q, "r": r} for q, r in sorted(starter)],
        }],
        "next_building_id": 1,
    }


def new_game(players: int, seed: int, config: dict[str, Any] | None = None) -> dict[str, Any]:
    if players not in (2, 3, 4):
        raise RuleError("Ark Nova requires 2, 3, or 4 players")
    config = config or {}
    if set(config) - {"map", "turn_limit"} or config.get("map", "a") != "a":
        raise RuleError("the controlled core supports only beginner map A and turn_limit")
    turn_limit = config.get("turn_limit", players * 30)
    if not isinstance(turn_limit, int) or turn_limit < players:
        raise RuleError("turn_limit must be an integer at least equal to player count")
    rng = random.Random(seed)
    zoo_cards = _research_zoo_cards()
    rng.shuffle(zoo_cards)
    display = [zoo_cards.pop() for _ in range(6)]
    finals = _final_cards()
    rng.shuffle(finals)
    projects = _base_projects()
    rng.shuffle(projects)
    bonus_tiles = _bonus_tiles()
    rng.shuffle(bonus_tiles)
    rows = []
    for seat in range(players):
        initial_draw = [zoo_cards.pop() for _ in range(8)]
        other_actions = list(ACTION_TYPES[1:])
        rng.shuffle(other_actions)
        rows.append({
            "seat": seat, "money": 25, "x_tokens": 0, "appeal": seat,
            "conservation": 0, "reputation": 0,
            "action_cards": [{"action": action, "strength": position, "upgraded": False, "tokens": []}
                             for position, action in enumerate(["animals", *other_actions], 1)],
            "association_workers": {"active": 1, "reserve": 3, "committed": []},
            "partner_zoos": [], "universities": [], "map": _map_a(), "hand": [],
            "initial_draw": initial_draw, "initial_keep_required": 4, "played_cards": [],
            "final_scoring_cards": [finals.pop() for _ in range(2)],
            "conservation_tokens_on_map": 7, "supported_projects": [],
        })
    project_count = 4 if players == 4 else 3
    state = {
        "schema_version": "agentbga.ark_nova.state.v2", "game_id": "ark_nova",
        "rules_version": RULES_VERSION, "implementation_status": "controlled_core",
        "seed": seed, "player_count": players, "turn_limit": turn_limit,
        "status": "active", "phase": "initial_hand_selection", "turn_count": 0,
        "decision_count": 0, "active_seat": 0, "pending_action": None,
        "end_after_turn": None, "end_reason": None,
        "turn": {"active_seat": 0, "decision": "choose_initial_hand", "action_card": None,
                 "remaining_plays": 0},
        "break_track": {"position": 0, "limit": BREAK_LIMITS[players],
                        "start_marker": f"players-{players}", "triggered": False,
                        "next_seat": None},
        "recycle_count": 0, "game_board_bonus_tiles": bonus_tiles[:4],
        "unused_bonus_tiles": bonus_tiles[4:], "card_display": display,
        "zoo_deck": zoo_cards, "zoo_discard": [], "final_scoring_deck": finals,
        "base_conservation_projects": projects[:project_count],
        "base_conservation_deck": projects[project_count:],
        "association_board": {
            "partner_zoos": {continent: 1 for continent in CONTINENTS},
            "universities": {"research-2": 1, "research-reputation": 1, "hand-limit-5": 1},
            "blocked_two_player": (["project-left", "project-middle", "project-right",
                                    "donation-left-1", "donation-left-2", "donation-left-3"]
                                   if players == 2 else []),
        },
        "players": rows,
    }
    validate_state(state)
    return state


def state_hash(state: dict[str, Any]) -> str:
    raw = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _hidden_cards(count: int) -> list[dict[str, bool]]:
    return [{"hidden": True} for _ in range(count)]


def _action_id(state: dict[str, Any], action: dict[str, Any]) -> str:
    material = json.dumps(action, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f'{state["decision_count"]}:{state["phase"]}:{material}'.encode()).hexdigest()[:12]
    return f"a-{digest}"


def _wrap_actions(state: dict[str, Any], actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": _action_id(state, action), "action": action} for action in actions]


def _action_card(player: dict[str, Any], name: str) -> dict[str, Any]:
    return next(card for card in player["action_cards"] if card["action"] == name)


def _occupied_cells(player: dict[str, Any]) -> set[tuple[int, int]]:
    return {(cell["q"], cell["r"]) for building in player["map"]["buildings"] for cell in building["cells"]}


def _neighbors(cell: tuple[int, int]) -> set[tuple[int, int]]:
    q, r = cell
    return {(q + 1, r), (q - 1, r), (q, r + 1), (q, r - 1), (q + 1, r - 1), (q - 1, r + 1)}


def _hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    dq, dr = a[0] - b[0], a[1] - b[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def _build_actions(player: dict[str, Any], strength: int) -> list[dict[str, Any]]:
    buildable = {(cell["q"], cell["r"]) for cell in player["map"]["cells"]
                 if cell["terrain"] == "buildable"}
    occupied = _occupied_cells(player)
    existing_kiosks = [tuple((building["cells"][0][key] for key in ("q", "r")))
                        for building in player["map"]["buildings"] if building["type"] == "kiosk"]
    choices: dict[str, dict[str, Any]] = {}
    types = [("pavilion", 1), ("kiosk", 1)] + [("standard_enclosure", size)
                                                for size in range(1, min(5, strength) + 1)]
    for building_type, size in types:
        if size > strength or player["money"] < size * 2:
            continue
        for start in sorted(buildable):
            for dq, dr in HEX_DIRECTIONS:
                cells = [(start[0] + dq * step, start[1] + dr * step) for step in range(size)]
                cell_set = set(cells)
                if len(cell_set) != size or not cell_set <= buildable or cell_set & occupied:
                    continue
                if not any(_neighbors(cell) & occupied for cell in cell_set):
                    continue
                if building_type == "kiosk" and any(_hex_distance(cells[0], other) < 3 for other in existing_kiosks):
                    continue
                action = {"type": "place_building", "building_type": building_type, "size": size,
                          "cost": size * 2, "cells": [{"q": q, "r": r} for q, r in sorted(cells)]}
                choices[json.dumps(action, sort_keys=True)] = action
    return list(choices.values())


def _playable_animals(player: dict[str, Any]) -> list[dict[str, Any]]:
    empty = [building for building in player["map"]["buildings"]
             if building["type"] == "standard_enclosure" and not building["occupied"]]
    actions = []
    for card in player["hand"]:
        if card["card_type"] != "animal" or card["cost"] > player["money"]:
            continue
        for enclosure in empty:
            if enclosure["size"] >= card["enclosure_size"]:
                actions.append({"type": "play_animal", "card_id": card["id"],
                                "enclosure_id": enclosure["id"], "cost": card["cost"]})
    return actions


def _tag_count(player: dict[str, Any], tag: str) -> int:
    count = sum(tag in card.get("tags", []) for card in player["played_cards"])
    count += sum(zoo == tag for zoo in player["partner_zoos"])
    return count


def _association_actions(state: dict[str, Any], player: dict[str, Any], strength: int) -> list[dict[str, Any]]:
    if player["association_workers"]["active"] < 1:
        return []
    actions = []
    if strength >= 2:
        actions.append({"type": "association_task", "task": "reputation", "value": 2,
                        "workers": 1})
    if strength >= 3:
        for continent, available in state["association_board"]["partner_zoos"].items():
            if available and continent not in player["partner_zoos"]:
                actions.append({"type": "association_task", "task": "partner_zoo", "value": 3,
                                "workers": 1, "continent": continent})
    if strength >= 4:
        for university, available in state["association_board"]["universities"].items():
            if available and university not in player["universities"]:
                actions.append({"type": "association_task", "task": "university", "value": 4,
                                "workers": 1, "university": university})
    if strength >= 5 and player["conservation_tokens_on_map"]:
        for project in state["base_conservation_projects"]:
            claimed = {claim["level"] for claim in project["claims"]}
            for level in project["levels"]:
                if level <= _tag_count(player, project["tag"]) and level not in claimed:
                    actions.append({"type": "association_task", "task": "conservation_project",
                                    "value": 5, "workers": 1, "project_id": project["id"],
                                    "level": level})
    return actions


def _can_start_action(state: dict[str, Any], player: dict[str, Any], name: str, strength: int) -> bool:
    if name == "cards":
        return bool(state["zoo_deck"] or state["zoo_discard"] or state["card_display"])
    if name == "build":
        return bool(_build_actions(player, strength))
    if name == "animals":
        return bool(_playable_animals(player))
    if name == "association":
        return bool(_association_actions(state, player, strength))
    return True  # Sponsors can always advance Break and gain money.


def legal_actions(state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    if state["status"] != "active" or seat != state["active_seat"]:
        return []
    player = state["players"][seat]
    phase = state["phase"]
    if phase == "initial_hand_selection":
        actions = [{"type": "choose_initial_hand", "card_ids": sorted(card["id"] for card in chosen)}
                   for chosen in combinations(player["initial_draw"], player["initial_keep_required"])]
        return _wrap_actions(state, actions)
    if phase == "choose_action":
        actions = []
        for card in sorted(player["action_cards"], key=lambda item: item["strength"]):
            for x_tokens in range(player["x_tokens"] + 1):
                strength = card["strength"] + x_tokens
                if _can_start_action(state, player, card["action"], strength):
                    actions.append({"type": "select_action", "action_card": card["action"],
                                    "base_strength": card["strength"], "x_tokens": x_tokens,
                                    "strength": strength})
            if player["x_tokens"] < 5:
                actions.append({"type": "take_x_token", "action_card": card["action"]})
        return _wrap_actions(state, actions)
    pending = state["pending_action"] or {}
    strength = pending.get("strength", 0)
    if phase == "cards_choose":
        actions = [{"type": "draw_cards", "draw_count": (strength + 1) // 2,
                    "discard_count": 1 if strength % 2 else 0}]
        snap_at = 3 if pending.get("upgraded") else 5
        if strength >= snap_at:
            actions.extend({"type": "snap_card", "card_id": card["id"]}
                           for card in state["card_display"])
        return _wrap_actions(state, actions)
    if phase == "cards_discard":
        return _wrap_actions(state, [{"type": "discard_card", "card_id": card["id"]}
                                     for card in player["hand"]])
    if phase == "build_place":
        return _wrap_actions(state, _build_actions(player, strength))
    if phase == "animals_play":
        actions = _playable_animals(player)
        if pending.get("plays_done", 0) > 0:
            actions.append({"type": "finish_action"})
        return _wrap_actions(state, actions)
    if phase == "association_task":
        return _wrap_actions(state, _association_actions(state, player, strength))
    if phase == "sponsors_choose":
        actions = [{"type": "advance_break", "steps": strength, "money": strength}]
        actions.extend({"type": "play_sponsor", "card_id": card["id"]}
                       for card in player["hand"]
                       if card["card_type"] == "sponsor" and card["level"] <= strength)
        return _wrap_actions(state, actions)
    if phase == "break_discard":
        limit = 5 if "hand-limit-5" in player["universities"] else 3
        surplus = len(player["hand"]) - limit
        actions = [{"type": "break_discard", "card_ids": sorted(card["id"] for card in chosen)}
                   for chosen in combinations(player["hand"], surplus)] if surplus > 0 else []
        return _wrap_actions(state, actions)
    return []


def _set_phase(state: dict[str, Any], phase: str, decision: str, *, action_card: str | None = None,
               remaining_plays: int = 0) -> None:
    state["phase"] = phase
    state["turn"] = {"active_seat": state["active_seat"], "decision": decision,
                     "action_card": action_card, "remaining_plays": remaining_plays}


def _move_action_card(player: dict[str, Any], name: str) -> None:
    chosen = _action_card(player, name)
    old_strength = chosen["strength"]
    for card in player["action_cards"]:
        if card["strength"] < old_strength:
            card["strength"] += 1
    chosen["strength"] = 1


def _draw_zoo_card(state: dict[str, Any]) -> dict[str, Any] | None:
    if not state["zoo_deck"] and state["zoo_discard"]:
        state["recycle_count"] += 1
        deck = state["zoo_discard"]
        state["zoo_discard"] = []
        random.Random(state["seed"] + 10_000 * state["recycle_count"]).shuffle(deck)
        state["zoo_deck"] = deck
    return state["zoo_deck"].pop() if state["zoo_deck"] else None


def _refill_display(state: dict[str, Any]) -> None:
    while len(state["card_display"]) < 6:
        card = _draw_zoo_card(state)
        if card is None:
            return
        state["card_display"].append(card)


def _move_break(state: dict[str, Any], steps: int) -> None:
    track = state["break_track"]
    track["position"] = min(track["limit"], track["position"] + steps)
    track["triggered"] = track["position"] >= track["limit"]


def _controlled_income(player: dict[str, Any]) -> int:
    appeal_income = 5 + (player["appeal"] // 2) + (2 if player["appeal"] >= 7 else 0)
    sponsor_income = sum(card.get("income", 0) for card in player["played_cards"]
                         if card["card_type"] == "sponsor")
    return appeal_income + sponsor_income


def _resolve_break(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    for player in state["players"]:
        for card in player["action_cards"]:
            card["tokens"] = []
        workers = player["association_workers"]
        workers["active"] += len(workers["committed"])
        workers["committed"] = []
    for continent in CONTINENTS:
        state["association_board"]["partner_zoos"][continent] = int(
            not all(continent in player["partner_zoos"] for player in state["players"])
        )
    for university in state["association_board"]["universities"]:
        state["association_board"]["universities"][university] = int(
            not all(university in player["universities"] for player in state["players"])
        )
    removed = state["card_display"][:2]
    state["card_display"] = state["card_display"][2:]
    state["zoo_discard"].extend(removed)
    _refill_display(state)
    incomes = []
    for player in state["players"]:
        amount = _controlled_income(player)
        player["money"] += amount
        incomes.append({"seat": player["seat"], "money": amount})
    state["break_track"].update({"position": 0, "triggered": False, "next_seat": None})
    events.append({"type": "break_resolved", "income": incomes})
    _set_phase(state, "choose_action", "choose_action_card")


def _begin_or_resolve_break(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    for player in state["players"]:
        limit = 5 if "hand-limit-5" in player["universities"] else 3
        if len(player["hand"]) > limit:
            state["active_seat"] = player["seat"]
            _set_phase(state, "break_discard", "discard_to_hand_limit")
            return
    state["active_seat"] = state["break_track"]["next_seat"]
    _resolve_break(state, events)


def _controlled_end_triggered(player: dict[str, Any]) -> bool:
    return player["appeal"] + player["conservation"] * 5 >= 45


def _finish_player_turn(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    player = state["players"][state["active_seat"]]
    pending = state["pending_action"]
    if pending:
        _move_action_card(player, pending["action_card"])
    _refill_display(state)
    state["pending_action"] = None
    state["turn_count"] += 1
    if state["end_after_turn"] is None and _controlled_end_triggered(player):
        state["end_after_turn"] = ((state["turn_count"] - 1) // state["player_count"] + 1) * state["player_count"]
        state["end_reason"] = "controlled_score_threshold"
    if state["turn_count"] >= state["turn_limit"] and state["end_after_turn"] is None:
        state["end_after_turn"] = state["turn_count"]
        state["end_reason"] = "controlled_turn_limit"
    if state["end_after_turn"] is not None and state["turn_count"] >= state["end_after_turn"]:
        state["status"] = "finished"
        _set_phase(state, "finished", "finished")
        events.append({"type": "match_end_triggered", "reason": state["end_reason"]})
        return
    next_seat = state["turn_count"] % state["player_count"]
    if state["break_track"]["triggered"]:
        state["break_track"]["next_seat"] = next_seat
        events.append({"type": "break_triggered", "seat": player["seat"]})
        _begin_or_resolve_break(state, events)
    else:
        state["active_seat"] = next_seat
        _set_phase(state, "choose_action", "choose_action_card")


def _finish_selected_action(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    _finish_player_turn(state, events)


def _canonical_action(state: dict[str, Any], seat: int, action: dict[str, Any]) -> dict[str, Any]:
    legal = legal_actions(state, seat)
    canonical = json.dumps(action, sort_keys=True, separators=(",", ":"))
    by_json = {json.dumps(item["action"], sort_keys=True, separators=(",", ":")): item["action"]
               for item in legal}
    if canonical not in by_json:
        raise RuleError("action is not legal in the current decision step")
    return by_json[canonical]


def apply_action(state: dict[str, Any], seat: int, action: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    action = _canonical_action(state, seat, action)
    next_state = deepcopy(state)
    player = next_state["players"][seat]
    phase = next_state["phase"]
    kind = action["type"]
    events: list[dict[str, Any]] = [{"type": "action_accepted", "seat": seat, "action": action,
                                    "decision": next_state["turn"]["decision"]}]
    next_state["decision_count"] += 1

    if phase == "initial_hand_selection":
        selected = set(action["card_ids"])
        player["hand"] = [card for card in player["initial_draw"] if card["id"] in selected]
        discarded = [card for card in player["initial_draw"] if card["id"] not in selected]
        next_state["zoo_discard"].extend(discarded)
        player["initial_draw"] = []
        events.append({"type": "initial_hand_chosen", "seat": seat, "kept": len(selected),
                       "discarded": len(discarded)})
        unfinished = [row["seat"] for row in next_state["players"] if row["initial_draw"]]
        if unfinished:
            next_state["active_seat"] = unfinished[0]
            _set_phase(next_state, "initial_hand_selection", "choose_initial_hand")
        else:
            next_state["active_seat"] = 0
            _set_phase(next_state, "choose_action", "choose_action_card")
            events.append({"type": "setup_completed"})
    elif phase == "choose_action":
        if kind == "take_x_token":
            _move_action_card(player, action["action_card"])
            player["x_tokens"] += 1
            next_state["pending_action"] = None
            _finish_player_turn(next_state, events)
        else:
            card = _action_card(player, action["action_card"])
            player["x_tokens"] -= action["x_tokens"]
            next_state["pending_action"] = {
                "action_card": action["action_card"], "strength": action["strength"],
                "base_strength": action["base_strength"], "x_tokens": action["x_tokens"],
                "upgraded": card["upgraded"], "plays_done": 0,
            }
            phase_for = {"cards": ("cards_choose", "choose_cards_mode"),
                         "build": ("build_place", "place_building"),
                         "animals": ("animals_play", "choose_animal"),
                         "association": ("association_task", "choose_association_task"),
                         "sponsors": ("sponsors_choose", "choose_sponsor_or_break")}
            new_phase, decision = phase_for[action["action_card"]]
            if action["action_card"] == "cards":
                _move_break(next_state, 2)
            remaining = 2 if action["action_card"] == "animals" and action["strength"] >= 5 else 1
            _set_phase(next_state, new_phase, decision, action_card=action["action_card"],
                       remaining_plays=remaining)
    elif phase == "cards_choose":
        if kind == "snap_card":
            card = next(card for card in next_state["card_display"] if card["id"] == action["card_id"])
            next_state["card_display"].remove(card)
            player["hand"].append(card)
            events.append({"type": "card_snapped", "seat": seat, "card_id": card["id"]})
            _finish_selected_action(next_state, events)
        else:
            drawn = []
            for _ in range(action["draw_count"]):
                card = _draw_zoo_card(next_state)
                if card:
                    player["hand"].append(card)
                    drawn.append(card["id"])
            events.append({"type": "cards_drawn", "seat": seat, "count": len(drawn)})
            if action["discard_count"] and player["hand"]:
                _set_phase(next_state, "cards_discard", "discard_after_cards", action_card="cards")
            else:
                _finish_selected_action(next_state, events)
    elif phase == "cards_discard":
        card = next(card for card in player["hand"] if card["id"] == action["card_id"])
        player["hand"].remove(card)
        next_state["zoo_discard"].append(card)
        events.append({"type": "card_discarded", "seat": seat, "card_id": card["id"]})
        _finish_selected_action(next_state, events)
    elif phase == "build_place":
        building = {"id": f"building-{player['map']['next_building_id']}",
                    "type": action["building_type"], "size": action["size"],
                    "occupied": False, "cells": action["cells"]}
        player["map"]["next_building_id"] += 1
        player["map"]["buildings"].append(building)
        player["money"] -= action["cost"]
        if action["building_type"] == "pavilion":
            player["appeal"] += 1
        events.append({"type": "building_placed", "seat": seat, "building": building,
                       "cost": action["cost"]})
        _finish_selected_action(next_state, events)
    elif phase == "animals_play":
        if kind == "finish_action":
            _finish_selected_action(next_state, events)
        else:
            card = next(card for card in player["hand"] if card["id"] == action["card_id"])
            enclosure = next(building for building in player["map"]["buildings"]
                             if building["id"] == action["enclosure_id"])
            player["hand"].remove(card)
            played = {**card, "enclosure_id": enclosure["id"]}
            player["played_cards"].append(played)
            enclosure["occupied"] = True
            player["money"] -= card["cost"]
            player["appeal"] += card["appeal"]
            player["conservation"] += card["conservation"]
            player["reputation"] += card["reputation"]
            next_state["pending_action"]["plays_done"] += 1
            remaining = (2 if next_state["pending_action"]["strength"] >= 5 else 1) - next_state["pending_action"]["plays_done"]
            events.append({"type": "animal_played", "seat": seat, "card_id": card["id"],
                           "enclosure_id": enclosure["id"]})
            if remaining > 0 and _playable_animals(player):
                _set_phase(next_state, "animals_play", "choose_animal", action_card="animals",
                           remaining_plays=remaining)
            else:
                _finish_selected_action(next_state, events)
    elif phase == "association_task":
        task = action["task"]
        workers = player["association_workers"]
        workers["active"] -= action["workers"]
        workers["committed"].append({"task": task, "workers": action["workers"]})
        if task == "reputation":
            player["reputation"] += 2
        elif task == "partner_zoo":
            player["partner_zoos"].append(action["continent"])
            next_state["association_board"]["partner_zoos"][action["continent"]] = 0
        elif task == "university":
            player["universities"].append(action["university"])
            next_state["association_board"]["universities"][action["university"]] = 0
        else:
            project = next(project for project in next_state["base_conservation_projects"]
                           if project["id"] == action["project_id"])
            reward = {2: 2, 4: 3, 5: 4}[action["level"]]
            project["claims"].append({"seat": seat, "level": action["level"]})
            player["supported_projects"].append(project["id"])
            player["conservation_tokens_on_map"] -= 1
            player["conservation"] += reward
        events.append({"type": "association_task_completed", "seat": seat, "task": task})
        _finish_selected_action(next_state, events)
    elif phase == "sponsors_choose":
        if kind == "advance_break":
            _move_break(next_state, action["steps"])
            player["money"] += action["money"]
            events.append({"type": "sponsors_break_advanced", "seat": seat,
                           "steps": action["steps"], "money": action["money"]})
        else:
            card = next(card for card in player["hand"] if card["id"] == action["card_id"])
            player["hand"].remove(card)
            player["played_cards"].append(card)
            player["appeal"] += card["appeal"]
            events.append({"type": "sponsor_played", "seat": seat, "card_id": card["id"]})
        _finish_selected_action(next_state, events)
    elif phase == "break_discard":
        selected = set(action["card_ids"])
        discarded = [card for card in player["hand"] if card["id"] in selected]
        player["hand"] = [card for card in player["hand"] if card["id"] not in selected]
        next_state["zoo_discard"].extend(discarded)
        events.append({"type": "break_cards_discarded", "seat": seat, "count": len(discarded)})
        _begin_or_resolve_break(next_state, events)
    else:  # pragma: no cover
        raise RuleError(f"unsupported decision phase: {phase}")
    validate_state(next_state)
    return next_state, events


def _controlled_score(player: dict[str, Any]) -> int:
    return player["appeal"] + 5 * player["conservation"] + player["reputation"] + len(player["played_cards"])


def rankings(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [{"seat": player["seat"], "appeal": player["appeal"],
             "conservation": player["conservation"], "reputation": player["reputation"],
             "controlled_score": _controlled_score(player), "rank": None}
            for player in state["players"]]
    rows.sort(key=lambda row: (-row["controlled_score"], -row["conservation"], row["seat"]))
    previous = None
    rank = 0
    for index, row in enumerate(rows):
        key = (row["controlled_score"], row["conservation"])
        if key != previous:
            rank = index + 1
            previous = key
        row["rank"] = rank
    return rows


def observe(state: dict[str, Any], seat: int) -> dict[str, Any]:
    if seat < 0 or seat >= state["player_count"]:
        raise RuleError("seat is out of range")
    rows = []
    for player in state["players"]:
        own = player["seat"] == seat
        row = deepcopy(player)
        row["hand_count"] = len(player["hand"])
        row["initial_draw_count"] = len(player["initial_draw"])
        row["hand"] = deepcopy(player["hand"]) if own else _hidden_cards(len(player["hand"]))
        row["initial_draw"] = deepcopy(player["initial_draw"]) if own else _hidden_cards(len(player["initial_draw"]))
        row["final_scoring_cards"] = (deepcopy(player["final_scoring_cards"]) if own
                                        else _hidden_cards(len(player["final_scoring_cards"])))
        rows.append(row)
    return {
        "game": "ark_nova", "rules_version": state["rules_version"],
        "implementation_status": state["implementation_status"], "viewer_seat": seat,
        "status": state["status"], "phase": state["phase"], "turn_count": state["turn_count"],
        "decision_count": state["decision_count"], "active_seat": state["active_seat"],
        "turn": deepcopy(state["turn"]), "break_track": deepcopy(state["break_track"]),
        "card_display": (_hidden_cards(len(state["card_display"]))
                         if state["phase"] == "initial_hand_selection" else deepcopy(state["card_display"])),
        "game_board_bonus_tiles": deepcopy(state["game_board_bonus_tiles"]),
        "deck_count": len(state["zoo_deck"]), "discard_count": len(state["zoo_discard"]),
        "base_conservation_projects": deepcopy(state["base_conservation_projects"]),
        "association_board": deepcopy(state["association_board"]), "players": rows,
        "rankings": rankings(state) if state["status"] == "finished" else None,
        "end_reason": state["end_reason"],
    }


def validate_state(state: dict[str, Any]) -> None:
    if state.get("schema_version") != "agentbga.ark_nova.state.v2":
        raise AssertionError("invalid Ark Nova state schema")
    if state["player_count"] not in (2, 3, 4) or len(state["players"]) != state["player_count"]:
        raise AssertionError("invalid Ark Nova player count")
    if not 0 <= state["active_seat"] < state["player_count"]:
        raise AssertionError("invalid active seat")
    seen: list[str] = [card["id"] for card in state["card_display"] + state["zoo_deck"] + state["zoo_discard"]]
    for player in state["players"]:
        if player["money"] < 0 or not 0 <= player["x_tokens"] <= 5:
            raise AssertionError("invalid player resources")
        if sorted(card["strength"] for card in player["action_cards"]) != [1, 2, 3, 4, 5]:
            raise AssertionError("action cards must occupy strengths 1 through 5")
        if {card["action"] for card in player["action_cards"]} != set(ACTION_TYPES):
            raise AssertionError("player must have all five action cards")
        seen.extend(card["id"] for card in player["hand"] + player["initial_draw"] + player["played_cards"])
        buildings = player["map"]["buildings"]
        building_cells = [(cell["q"], cell["r"]) for building in buildings for cell in building["cells"]]
        if len(building_cells) != len(set(building_cells)):
            raise AssertionError("map buildings overlap")
        terrain = {(cell["q"], cell["r"]): cell["terrain"] for cell in player["map"]["cells"]}
        if any(cell not in terrain or terrain[cell] != "buildable" for cell in building_cells):
            raise AssertionError("building occupies illegal terrain")
        workers = player["association_workers"]
        if workers["active"] < 0 or workers["active"] + workers["reserve"] + sum(
            item["workers"] for item in workers["committed"]
        ) != 4:
            raise AssertionError("association worker conservation failed")
    if len(seen) != 212 or len(seen) != len(set(seen)):
        raise AssertionError("Ark Nova must conserve all 212 unique zoo cards")
    bonus_seen = [tile["id"] for tile in state["game_board_bonus_tiles"] + state["unused_bonus_tiles"]]
    if len(bonus_seen) != 9 or len(bonus_seen) != len(set(bonus_seen)):
        raise AssertionError("invalid game-board bonus tiles")
    final_seen = [card["id"] for card in state["final_scoring_deck"]]
    for player in state["players"]:
        final_seen.extend(card["id"] for card in player["final_scoring_cards"])
    if len(final_seen) != 11 or len(final_seen) != len(set(final_seen)):
        raise AssertionError("invalid final scoring deck")
    projects = state["base_conservation_projects"] + state["base_conservation_deck"]
    if len(projects) != 12 or len({project["id"] for project in projects}) != 12:
        raise AssertionError("invalid base conservation project deck")
