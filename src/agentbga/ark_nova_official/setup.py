"""Deterministic official-base setup from the validated semantic content pack."""

from __future__ import annotations

from copy import deepcopy
from itertools import combinations
from pathlib import Path
import random
from typing import Any, Mapping, Sequence

from .content import ContentEntry, ContentPack, load_content_pack
from .milestones import install_official_conservation_milestones
from .projects import install_base_projects
from .semantics import SemanticRuleError
from .state import ACTION_TYPES, new_semantic_state, validate_semantic_state


DEFAULT_CONTENT_ROOT = (
    Path(__file__).resolve().parents[3] / "content-packs" / "ark-nova" / "base-en-draft"
)


def load_official_base_pack() -> ContentPack:
    return load_content_pack(DEFAULT_CONTENT_ROOT)


def card_instance(entry: ContentEntry) -> dict[str, Any]:
    """Project one physical base-game card without publisher prose or artwork."""
    component = entry.official_component_id or entry.id.rsplit("-", 1)[-1]
    prefix = "final" if entry.kind == "final_scoring" else "zoo"
    facts = deepcopy(dict(entry.facts))
    card_type = {
        "animal": "animal",
        "sponsor": "sponsor",
        "zoo_conservation_project": "conservation_project",
        "final_scoring": "final_scoring",
    }.get(entry.kind, entry.kind)
    card = {
        "id": f"{prefix}-{component}",
        "entry_id": entry.id,
        "kind": entry.kind,
        "card_type": card_type,
        "display_title": entry.display_title,
        "display_summary": entry.display_summary,
        "facts": facts,
        "effects": deepcopy(list(entry.effects)),
    }
    for key in (
        "cost", "enclosure_size", "appeal", "conservation", "reputation",
        "level", "tags", "icons", "rock_requirement", "water_requirement",
        "special_enclosure", "scoring", "levels",
    ):
        if key in facts:
            card[key] = deepcopy(facts[key])
    continents = facts.get("continents")
    if isinstance(continents, list) and continents:
        card["continent"] = continents[0]
    return card


def _bonus_tiles(entries: Sequence[ContentEntry] | None = None) -> list[dict[str, Any]]:
    """Return the nine mechanics-only base-game reward tiles."""

    if entries is not None:
        if len(entries) != 9:
            raise SemanticRuleError("official bonus-tile content must contain nine faces")
        return [{
            "id": f"bonus-{entry.official_component_id or entry.id.rsplit('-', 1)[-1]}",
            "label": entry.display_title,
            "label_en": entry.display_title,
            "label_cn": str(entry.facts.get("label_cn", entry.display_title)),
            "effects": deepcopy(list(entry.effects)),
        } for entry in entries]

    def effect(op: str, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return {"op": op, "timing": "immediate", "args": dict(args or {})}

    multiplier_options = [
        {
            "id": action,
            "label": f"Place the multiplier token on {action}",
            "effects": [effect("add_action_token", {
                "action": action, "token": "multiplier",
            })],
        }
        for action in ACTION_TYPES
    ]
    definitions = (
        ("reputation-2", "Gain 2 reputation", "声望提升 2 点", [
            effect("move_track", {"track": "reputation", "amount": 2}),
        ]),
        ("x-3", "Gain 3 X-tokens", "获得 3 枚 X 标记", [
            effect("gain_x_token", {"amount": 3}),
        ]),
        ("enclosure-3", "Build a free size-3 standard enclosure", "立刻免费建造一个 3 格标准饲养区", [
            effect("place_free_building", {
                "building_types": ["standard_enclosure_3"], "maximum": 1,
            }),
        ]),
        ("cards-3", "Take or draw a card three times", "执行 3 次：从声望范围拿牌或从牌库抽牌", [
            effect("take_map_reward_card"),
            effect("take_map_reward_card"),
            effect("take_map_reward_card"),
        ]),
        ("money-5", "Gain 5 money", "获得 5 金币", [
            effect("gain_money", {"amount": 5}),
        ]),
        ("money-10", "Gain 10 money", "获得 10 金币", [
            effect("gain_money", {"amount": 10}),
        ]),
        ("multiplier", "Place a multiplier token on an Action card", "在一张行动卡牌上放置双重标记", [
            effect("choose_one", {
                "prompt": "Choose an Action card for the multiplier token",
                "options": multiplier_options,
            }),
        ]),
        ("university", "Take an available university", "从协会板图选择一个可用大学", [
            effect("choose_bonus_association_asset", {"asset": "university"}),
        ]),
        ("partner-zoo", "Take an available partner zoo", "从协会板图选择一个可用合作动物园", [
            effect("choose_bonus_association_asset", {"asset": "partner_zoo"}),
        ]),
    )
    return [{
        "id": f"bonus-{tile_id}",
        "label": label_en,
        "label_en": label_en,
        "label_cn": label_cn,
        "effects": effects,
    } for tile_id, label_en, label_cn, effects in definitions]


def setup_official_game(
    players: int, seed: int, *, pack: ContentPack | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if players not in (1, 2, 3, 4):
        raise SemanticRuleError("Ark Nova supports one to four players")
    config = dict(config or {})
    if set(config) - {"map", "turn_limit", "solo_starting_appeal"} or config.get("map", "map-0") not in {"0", "map-0"}:
        raise SemanticRuleError("the official-base plugin currently supports Map 0")
    solo_starting_appeal = config.get("solo_starting_appeal", 20)
    if players == 1 and solo_starting_appeal not in {0, 10, 20}:
        raise SemanticRuleError("solo_starting_appeal must be 0, 10, or 20")
    content = pack or load_official_base_pack()
    rng = random.Random(seed)
    state = new_semantic_state(players, seed=seed)
    state.update({
        "implementation_status": "official_base_candidate",
        "content_pack_id": content.manifest.pack_id,
        "content_version": content.manifest.content_version,
        "content_sha256": content.content_sha256,
        "content_hash": content.content_sha256,
        "official_track_income": True,
        "status": "active",
        "phase": "initial_hand_selection",
        "setup_pending_seats": list(range(players)),
        "decision_count": 0,
        "turn_count": 0,
    })

    zoo_cards = [
        card_instance(entry)
        for collection in ("animals", "sponsors", "zoo_conservation_projects")
        for entry in content.collections[collection]
    ]
    if len(zoo_cards) != 212:
        raise SemanticRuleError("official Zoo deck must contain exactly 212 physical cards")
    rng.shuffle(zoo_cards)
    state["card_display"] = [zoo_cards.pop() for _ in range(6)]

    finals = [card_instance(entry) for entry in content.collections["final_scoring"]]
    rng.shuffle(finals)
    for action_order, player in enumerate(state["players"]):
        if players == 1:
            player["tracks"]["appeal"] = int(solo_starting_appeal)
        else:
            # Seats are assigned in the initial action order.  The printed
            # setup gives each later player one additional Appeal.
            player["tracks"]["appeal"] = action_order
        player["tracks"]["reputation"] = 1
        player["initial_draw"] = [zoo_cards.pop() for _ in range(8)]
        player["initial_keep_required"] = 4
        player["final_scoring_cards"] = _draw_two_final_cards(finals, players, rng)
        other_actions = list(ACTION_TYPES[1:])
        rng.shuffle(other_actions)
        for position, action in enumerate(("animals", *other_actions), 1):
            card = next(item for item in player["action_cards"] if item["action"] == action)
            card["position"] = position
    state["zoo_deck"] = zoo_cards
    state["final_scoring_deck"] = finals

    projects = list(content.collections["base_conservation_projects"])
    rng.shuffle(projects)
    project_count = 4 if players == 4 else 3
    state = install_base_projects(state, projects[:project_count])
    state["base_project_supply"] = [entry.id for entry in projects[project_count:]]

    bonuses = _bonus_tiles(content.collections["bonus_tiles"])
    rng.shuffle(bonuses)
    state = install_official_conservation_milestones(
        state, bonuses_at_5=bonuses[:2], bonuses_at_8=bonuses[2:4],
    )
    state["unused_conservation_bonus_tiles"] = bonuses[4:]
    validate_semantic_state(state)
    return state


def legal_initial_hand_actions(state: Mapping[str, Any], seat: int) -> list[dict[str, Any]]:
    if state.get("phase") != "initial_hand_selection" or seat not in state.get("setup_pending_seats", []):
        return []
    cards = state["players"][seat].get("initial_draw", [])
    required = int(state["players"][seat].get("initial_keep_required", 4))
    return [
        {
            "id": "setup:keep:" + ":".join(card_ids),
            "action": {"type": "choose_initial_hand", "card_ids": list(card_ids)},
        }
        for card_ids in combinations((card["id"] for card in cards), required)
    ]


def choose_initial_hand(
    state: dict[str, Any], seat: int, card_ids: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    legal = [item["action"] for item in legal_initial_hand_actions(state, seat)]
    requested = {"type": "choose_initial_hand", "card_ids": list(card_ids)}
    if requested not in legal:
        raise SemanticRuleError("initial hand selection is not currently legal")
    next_state = deepcopy(state)
    player = next_state["players"][seat]
    selected = set(card_ids)
    player["hand"] = [card for card in player["initial_draw"] if card["id"] in selected]
    discarded = [card for card in player["initial_draw"] if card["id"] not in selected]
    next_state["zoo_discard"].extend(discarded)
    player["initial_draw"] = []
    next_state["setup_pending_seats"].remove(seat)
    if not next_state["setup_pending_seats"]:
        # Map 0 has no free starter enclosure or kiosk.  Those printed starter
        # buildings belong to Map A and must not leak into the Map 0 setup.
        next_state["phase"] = "active"
        next_state["active_seat"] = 0
    validate_semantic_state(next_state)
    return next_state, [{
        "type": "initial_hand_selected", "seat": seat,
        "kept": len(player["hand"]), "discarded": len(discarded),
    }]

def _draw_two_final_cards(
    deck: list[dict[str, Any]], players: int, rng: random.Random,
) -> list[dict[str, Any]]:
    result = []
    while len(result) < 2:
        if not deck:
            raise SemanticRuleError("Final Scoring deck is exhausted during setup")
        card = deck.pop()
        if players == 1 and card.get("entry_id") == "ark-nova:final-009":
            deck.insert(0, card)
            rng.shuffle(deck)
            continue
        result.append(card)
    return result
