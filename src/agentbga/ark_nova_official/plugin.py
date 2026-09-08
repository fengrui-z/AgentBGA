"""Runnable official-base Ark Nova game plugin."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from ..ark_nova_presentation import map_display, player_public_summary, public_tracks
from ..ark_nova_tracks import appeal_income, conservation_score_offset, conservation_target_appeal
from ..game import GameRuleError
from ..mechanics import action_accepted, hidden_items, state_digest
from .action_domains import apply_official_action, content_entry_indexes, legal_official_actions
from .cards import printed_icon_counts, terrain_requirement_icon_counts
from .content import ContentPack
from .final_scoring_effects import score_final_card
from .milestones import (
    OFFICIAL_REPUTATION_MILESTONE_IDS,
    official_reputation_milestones,
    queue_endgame_final_scoring_discard,
)
from .presentation import explain_predicate, resolve_mechanics
from .projects import legal_project_support_options
from .rounds import advance_solo_round_after_turn, queue_break, queue_solo_break
from .scoring import check_endgame_trigger, score_game
from .semantics import SemanticEngine, SemanticRuleError, official_kiosk_income
from .setup import (
    card_instance,
    choose_initial_hand,
    legal_initial_hand_actions,
    load_official_base_pack,
    setup_official_game,
)
from .state import SEMANTIC_RULES_VERSION, reputation_track_limit, validate_semantic_state


class ArkNovaOfficialPlugin:
    game_id = "ark_nova"
    rules_version = SEMANTIC_RULES_VERSION

    def __init__(self, pack: ContentPack | None = None) -> None:
        self.pack = pack or load_official_base_pack()
        self.indexes = content_entry_indexes(self.pack)
        self.engine = SemanticEngine(base_project_cards={
            entry.id: card_instance(entry)
            for entry in self.pack.collections["base_conservation_projects"]
        })

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.game_id,
            "name": "Ark Nova",
            "rules_version": self.rules_version,
            "players": {"minimum": 1, "maximum": 4},
            "hidden_information": True,
            "implementation_status": "released",
            "runnable": True,
            # Ark Nova regularly needs well over 250 player turns in longer
            # multiplayer and baseline-agent games. Keep a finite runaway
            # guard, but use a game-appropriate ceiling.
            "default_max_turns": 1000,
            "decision_model": "simultaneous_setup_then_player_turns",
            "action_types": ["animals", "cards", "build", "association", "sponsors"],
            "map": "map-0",
            "available_maps": ["map-0", "map-a"],
            "map_status": {"map-0": "released", "map-a": "preview"},
            "content_pack": self.pack.manifest.pack_id,
            "content_version": self.pack.manifest.content_version,
            "content_sha256": self.pack.content_sha256,
            "content_scope": (
                "255 physical base cards: 128 Animals, 64 Sponsors, 32 Conservation "
                "Projects, 11 Final Scoring cards, and five Action cards; released Map 0 "
                "plus an opt-in Map A board preview"
            ),
        }

    def setup(
        self, players: int, seed: int, config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return setup_official_game(players, seed, pack=self.pack, config=config)
        except SemanticRuleError as error:
            raise GameRuleError(str(error)) from error

    def decision_seats(self, state: dict[str, Any]) -> list[int]:
        if state.get("status") == "finished":
            return []
        if state.get("phase") == "initial_hand_selection":
            return list(state.get("setup_pending_seats", []))
        pending = state.get("resolution", {}).get("pending_choice")
        if isinstance(pending, Mapping):
            return [int(pending["seat"])]
        if state.get("phase") in {"active", "action"} or state["turn"].get("bonus_sponsor_play"):
            return [int(state["active_seat"])]
        return []

    def legal_actions(self, state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
        state, _ = _normalize_legacy_state(state)
        if seat not in self.decision_seats(state):
            return []
        if state.get("phase") == "initial_hand_selection":
            return legal_initial_hand_actions(state, seat)
        # Labels and benefit metadata are part of the agent/UI contract.  The
        # executable ``action`` remains authoritative, while these fields make
        # the legal choice understandable without reverse-engineering IDs.
        return deepcopy(legal_official_actions(
            self.engine, state, seat, self.indexes,
        ))

    def apply_action(
        self, state: dict[str, Any], seat: int, action: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        try:
            state, normalization_events = _normalize_legacy_state(state)
            if state.get("phase") == "initial_hand_selection":
                if action.get("type") != "choose_initial_hand":
                    raise SemanticRuleError("initial hand selection is required")
                next_state, events = choose_initial_hand(
                    state, seat, list(action.get("card_ids", [])),
                )
            else:
                next_state, events = apply_official_action(
                    self.engine, state, seat, self.indexes, action,
                )
            next_state["decision_count"] = int(next_state.get("decision_count", 0)) + 1
            next_state, lifecycle_events = self._advance_lifecycle(next_state, events)
            next_state["turn_count"] = int(next_state["turn"]["number"])
            self.validate_state(next_state)
            return next_state, [
                action_accepted(seat, deepcopy(action), rules_version=self.rules_version),
                *normalization_events,
                *events,
                *lifecycle_events,
            ]
        except SemanticRuleError as error:
            raise GameRuleError(str(error)) from error

    def _advance_lifecycle(
        self, state: dict[str, Any], incoming: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        events: list[dict[str, Any]] = []
        work = list(incoming)
        # One accepted decision can finish an effect queue, a turn, and a Break.
        # Iterate over those engine-emitted boundaries until another player
        # choice is required or the game is scored.
        while True:
            if state["status"] == "finished":
                return state, events
            if state["phase"] == "break_pending":
                seat = int(state["active_seat"])
                if state["endgame"].get("triggered"):
                    state["endgame"]["pending_final_turn_seat"] = seat
                state, produced = (
                    queue_solo_break(self.engine, state)
                    if state["break"]["mode"] == "solo_round"
                    else queue_break(self.engine, state)
                )
                events.extend(produced)
                work.extend(produced)
                if state["resolution"]["pending_choice"] is not None:
                    return state, events
                continue

            turn_events = [event for event in work if event.get("type") == "turn_finished"]
            break_events = [event for event in work if event.get("type") == "break_finished"]
            discard_finished = any(
                event.get("type") == "final_scoring_discard_window_finished"
                for event in work
            )
            work = []

            for event in turn_events:
                if state["break"]["mode"] == "solo_round":
                    state, advanced = advance_solo_round_after_turn(
                        state, int(event["seat"]),
                    )
                    events.extend(advanced)
                    continue
                if event.get("break_pending"):
                    continue
                state, triggered = self._trigger_or_consume_final_turn(
                    state, int(event["seat"]), "end_of_turn",
                )
                events.extend(triggered)
            for event in break_events:
                if state["break"]["mode"] == "solo_round":
                    continue
                if not state["endgame"].get("triggered"):
                    state, triggered = self._check_all_for_trigger(state, "break")
                    events.extend(triggered)
                else:
                    pending = state["endgame"].pop("pending_final_turn_seat", None)
                    if isinstance(pending, int):
                        state, consumed = self._consume_final_turn(state, pending)
                        events.extend(consumed)

            if discard_finished:
                state, scored = self._score_now(state)
                events.extend(scored)
                return state, events
            if state["phase"] == "break_pending":
                continue
            if state["endgame"].get("triggered") and not state["endgame"].get("final_turn_seats"):
                state, produced = self._begin_final_scoring(state)
                events.extend(produced)
                if state["status"] == "finished" or state["resolution"]["pending_choice"] is not None:
                    return state, events
                work.extend(produced)
                continue
            return state, events

    def _trigger_or_consume_final_turn(
        self, state: dict[str, Any], seat: int, boundary: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if state["endgame"].get("triggered"):
            return self._consume_final_turn(state, seat)
        checked, events = check_endgame_trigger(
            state, seat, boundary=boundary,
            target_by_conservation=_TARGET_APPEAL,
        )
        if events:
            if boundary == "break":
                start = int(checked["active_seat"])
                checked["endgame"]["final_turn_seats"] = [
                    (start + offset) % checked["player_count"]
                    for offset in range(checked["player_count"])
                ]
            else:
                checked["endgame"]["final_turn_seats"] = [
                    (seat + offset) % checked["player_count"]
                    for offset in range(1, checked["player_count"])
                ]
        return checked, events

    def _check_all_for_trigger(
        self, state: dict[str, Any], boundary: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        start = int(state["active_seat"])
        for offset in range(state["player_count"]):
            seat = (start + offset) % state["player_count"]
            checked, events = self._trigger_or_consume_final_turn(state, seat, boundary)
            if events:
                return checked, events
        return state, []

    @staticmethod
    def _consume_final_turn(
        state: dict[str, Any], seat: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        remaining = state["endgame"].setdefault("final_turn_seats", [])
        if not remaining or remaining[0] != seat:
            return state, []
        remaining.pop(0)
        return state, [{
            "type": "endgame_final_turn_completed", "seat": seat,
            "remaining_seats": list(remaining),
        }]

    def _begin_final_scoring(
        self, state: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if state["endgame"].get("scoring_started"):
            return state, []
        state["endgame"]["scoring_started"] = True
        if state["endgame"].get("final_scoring_discard_completed"):
            return self._score_now(state)
        prepared, events = queue_endgame_final_scoring_discard(
            self.engine, state, starting_seat=int(state["active_seat"]),
        )
        return prepared, events

    def _score_now(
        self, state: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return score_game(self.engine, state, _TARGET_APPEAL)

    def observe(self, state: dict[str, Any], seat: int) -> dict[str, Any]:
        if not 0 <= seat < state["player_count"]:
            raise GameRuleError("seat is out of range")
        state, _ = _normalize_legacy_state(state)
        return self._observe(state, seat, reveal_all_private=False)

    def observe_spectator(self, state: dict[str, Any]) -> dict[str, Any]:
        state, _ = _normalize_legacy_state(state)
        view = self._observe(state, 0, reveal_all_private=True)
        view["viewer_mode"] = "spectator"
        return view

    def _observe(
        self, state: dict[str, Any], seat: int, *, reveal_all_private: bool,
    ) -> dict[str, Any]:
        rows = [
            _present_player(
                player, reveal_all_private or player["seat"] == seat, state,
                self.indexes,
            )
            for player in state["players"]
        ]
        projection = {
            "players": rows,
            "break_track": {
                "position": state["break"]["position"],
                "limit": state["break"].get("limit") or 0,
            },
        }
        association = _present_association(state)
        remaining_final_turns = list(state["endgame"].get("final_turn_seats", []))
        is_my_final_action = bool(
            not reveal_all_private
            and state["endgame"].get("triggered")
            and state.get("status") != "finished"
            and remaining_final_turns
            and remaining_final_turns[0] == seat
            and state.get("active_seat") == seat
        )
        scoring_after_this_action = bool(
            is_my_final_action and remaining_final_turns == [seat]
        )
        if scoring_after_this_action:
            instruction_cn = "这是你的最后一个行动；本行动结束后立即进行终局计分。"
            instruction_en = "This is your final action; final scoring begins immediately after it ends."
        elif is_my_final_action:
            later = [value + 1 for value in remaining_final_turns[1:]]
            instruction_cn = f"这是你的最后一个行动；之后座位 {later} 仍各有最后一个行动。"
            instruction_en = f"This is your final action; seats {later} still have one final action each."
        elif state["endgame"].get("triggered") and remaining_final_turns:
            seats = [value + 1 for value in remaining_final_turns]
            instruction_cn = f"终局已触发；座位 {seats} 尚有最后行动。"
            instruction_en = f"Endgame is triggered; seats {seats} still have final actions."
        elif state["endgame"].get("triggered") and state.get("status") != "finished":
            instruction_cn = "所有最后行动已经完成，正在进行终局计分。"
            instruction_en = "All final actions are complete; final scoring is in progress."
        else:
            instruction_cn = "终局尚未触发。"
            instruction_en = "Endgame has not been triggered."
        return {
            "game": self.game_id,
            "rules_version": state["rules_version"],
            "content_pack_id": state.get("content_pack_id"),
            "content_hash": state.get("content_hash"),
            "implementation_status": state["implementation_status"],
            "map_id": state.get("map_id", "map-0"),
            "viewer_seat": seat,
            "status": state["status"], "phase": state["phase"],
            "turn_count": state["turn"]["number"],
            "decision_count": state.get("decision_count", 0),
            "active_seat": state["active_seat"],
            "endgame": {
                "triggered": bool(state["endgame"].get("triggered")),
                "triggered_by": state["endgame"].get("triggered_by"),
                "remaining_final_turn_seats": remaining_final_turns,
                "is_my_final_action": is_my_final_action,
                "scoring_after_this_action": scoring_after_this_action,
                "instruction_cn": instruction_cn,
                "instruction_en": instruction_en,
            },
            "turn": {
                "active_seat": state["active_seat"],
                "decision": state["phase"],
                "action_card": (
                    None if state["turn"].get("action_session") is None
                    else state["turn"]["action_session"].get("action")
                ),
                "remaining_plays": 0,
                "execution": (
                    0 if state["turn"].get("action_session") is None
                    else int(state["turn"]["action_session"].get("current_execution", 0)) + 1
                ),
                "executions_total": (
                    0 if state["turn"].get("action_session") is None
                    else len(state["turn"]["action_session"].get("strengths", []))
                ),
            },
            "break_track": {
                "position": state["break"]["position"],
                "limit": state["break"].get("limit") or 0,
                "count": int(state["break"].get("count", 0)),
                "start_marker": f"players-{state['player_count']}",
                "triggered": bool(state["break"]["pending"]),
            },
            "break_rules_summary": _break_rules_summary(state),
            "solo_board": _present_solo_board(state),
            "card_display": [_present_card(card, self.indexes) for card in state["card_display"]],
            "game_board_bonus_tiles": [
                {**deepcopy(tile), "milestone": int(at)}
                for at in ("5", "8")
                for tile in state["conservation_bonus_slots"][at]
            ],
            "deck_count": len(state["zoo_deck"]),
            "discard_count": len(state["zoo_discard"]),
            "base_conservation_projects": _present_projects(
                self.engine, state, self.indexes, base=True, viewer_seat=seat,
            ),
            "zoo_conservation_projects": _present_projects(
                self.engine, state, self.indexes, base=False, viewer_seat=seat,
            ),
            "association_board": association,
            "association_display": _association_display(state),
            "public_tracks": public_tracks(projection),
            "players": rows,
            "rankings": deepcopy(state["endgame"].get("results")),
            "end_reason": "track_crossing" if state["status"] == "finished" else None,
            "pending_choice": _present_pending_choice(
                state["resolution"].get("pending_choice"), seat,
                reveal_all_private=reveal_all_private,
            ),
        }

    def rankings(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        if state["endgame"].get("results") is not None:
            return deepcopy(state["endgame"]["results"])
        rows = [{
            "seat": player["seat"],
            "appeal": player["tracks"]["appeal"],
            "conservation": player["tracks"]["conservation"],
            "victory_points": (
                player["tracks"]["appeal"]
                + conservation_score_offset(player["tracks"]["conservation"])
            ),
            "supported_projects": len(player["supported_projects"]),
        } for player in state["players"]]
        ordered = sorted(rows, key=lambda row: (-row["victory_points"], -row["supported_projects"], row["seat"]))
        for index, row in enumerate(ordered, 1):
            row["rank"] = index
        return ordered

    def validate_state(self, state: dict[str, Any]) -> None:
        validate_semantic_state(state)
        ids = _physical_zoo_card_ids(state)
        if len(ids) != len(set(ids)):
            raise AssertionError("Zoo-card physical IDs must be unique across zones")
        if state.get("content_pack_id") and len(ids) != 212:
            raise AssertionError("official Zoo-card zones must retain all 212 physical cards")

    def state_hash(self, state: dict[str, Any]) -> str:
        return state_digest(state)


_TARGET_APPEAL = tuple(conservation_target_appeal(value) for value in range(42))


def _normalize_reputation_caps(
    state: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Repair legacy states created before the Cards-I ceiling was enforced."""

    corrections = []
    for player in state["players"]:
        old = int(player["tracks"]["reputation"])
        limit = reputation_track_limit(player)
        if old > limit:
            corrections.append({
                "type": "reputation_cap_corrected", "seat": int(player["seat"]),
                "old_value": old, "value": limit, "cards_upgraded": limit == 15,
            })
    if not corrections:
        return state, []
    normalized = deepcopy(state)
    for event in corrections:
        normalized["players"][event["seat"]]["tracks"]["reputation"] = event["value"]
    return normalized, corrections


def _normalize_legacy_state(
    state: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Project legacy saves onto current reputation and terrain-icon rules."""

    normalized, events = _normalize_reputation_caps(state)
    if normalized.get("player_count") == 1 and normalized.get("solo_starting_appeal") not in {0, 10, 20}:
        if normalized is state:
            normalized = deepcopy(state)
        normalized["solo_starting_appeal"] = 20
        events.append({
            "type": "solo_starting_appeal_migrated", "value": 20,
        })
    missing_reputation_milestones = (
        OFFICIAL_REPUTATION_MILESTONE_IDS
        - {item.get("id") for item in normalized.get("milestones", [])}
    )
    legacy_asset_seats = [
        int(player["seat"]) for player in normalized["players"]
        if not player.get("association_asset_icons_accounted")
    ]
    if missing_reputation_milestones or legacy_asset_seats:
        if normalized is state:
            normalized = deepcopy(state)
        if missing_reputation_milestones:
            normalized["milestones"].extend(
                item for item in official_reputation_milestones()
                if item["id"] in missing_reputation_milestones
            )
            events.append({
                "type": "reputation_milestones_migrated",
                "milestones": sorted(missing_reputation_milestones),
            })
        for seat in legacy_asset_seats:
            player = normalized["players"][seat]
            added: dict[str, int] = {}
            for continent in player.get("partner_zoos", []):
                asset = continent if isinstance(continent, str) else continent.get("continent")
                if isinstance(asset, str):
                    player["icons"][asset] = int(player["icons"].get(asset, 0)) + 1
                    added[asset] = added.get(asset, 0) + 1
            player["association_asset_icons_accounted"] = True
            events.append({
                "type": "association_asset_icons_migrated", "seat": seat,
                "icons_added": added,
            })
        if (
            missing_reputation_milestones
            and not normalized["resolution"]["queue"]
            and normalized["resolution"]["pending_choice"] is None
        ):
            retroactive_effects = []
            for player in normalized["players"]:
                for milestone in official_reputation_milestones():
                    if (
                        milestone["id"] in missing_reputation_milestones
                        and int(player["tracks"]["reputation"]) >= int(milestone["at"])
                        and milestone["id"] not in player["claimed_milestones"]
                    ):
                        player["claimed_milestones"].append(milestone["id"])
                        retroactive_effects.extend({
                            **deepcopy(effect), "_semantic_target_seat": int(player["seat"]),
                        } for effect in milestone["effects"])
            if retroactive_effects:
                normalized, reward_events = SemanticEngine().start_effects(
                    normalized, int(normalized["active_seat"]), retroactive_effects,
                    source_id="migration:reputation-milestones",
                )
                events.extend(reward_events)
    legacy_explorer_seats = [
        int(player["seat"])
        for player in normalized["players"]
        if any(
            modifier.get("id") == "sponsor-262"
            and [effect.get("op") for effect in modifier.get("effects", [])]
            == ["move_track", "gain_money"]
            for modifier in player.get("modifiers", [])
        )
    ]
    if legacy_explorer_seats:
        if normalized is state:
            normalized = deepcopy(state)
        for seat in legacy_explorer_seats:
            for modifier in normalized["players"][seat].get("modifiers", []):
                if modifier.get("id") != "sponsor-262":
                    continue
                if [effect.get("op") for effect in modifier.get("effects", [])] != [
                    "move_track", "gain_money",
                ]:
                    continue
                modifier["effects"] = [{
                    "op": "gain_resources", "timing": "on_trigger",
                    "args": {"appeal": 1, "money": 2},
                }]
            events.append({"type": "explorer_modifier_migrated", "seat": seat})

    additions: list[tuple[int, dict[str, int], list[str]]] = []
    for player in normalized["players"]:
        counts: dict[str, int] = {}
        card_ids: list[str] = []
        for card in player.get("played_cards", []):
            if card.get("terrain_icons_accounted") is True:
                continue
            facts = card.get("facts", {})
            if not isinstance(facts, Mapping):
                continue
            card_counts = terrain_requirement_icon_counts(facts)
            for icon, count in card_counts.items():
                counts[icon] = counts.get(icon, 0) + count
            card_id = card.get("id")
            if isinstance(card_id, str):
                card_ids.append(card_id)
        if card_ids:
            additions.append((int(player["seat"]), counts, card_ids))
    if not additions:
        return normalized, events
    if normalized is state:
        normalized = deepcopy(state)
    for seat, counts, card_ids in additions:
        player = normalized["players"][seat]
        for icon, count in counts.items():
            player["icons"][icon] = int(player["icons"].get(icon, 0)) + count
        migrated = set(card_ids)
        for card in player.get("played_cards", []):
            if card.get("id") in migrated:
                card["terrain_icons_accounted"] = True
        events.append({
            "type": "terrain_icons_migrated", "seat": seat,
            "icons_added": counts, "card_ids": card_ids,
        })
    return normalized, events


def _physical_zoo_card_ids(state: Mapping[str, Any]) -> list[str]:
    """Collect physical Zoo-card IDs from every persistent or in-flight zone.

    Pending semantic choices may temporarily own cards already removed from a
    deck or discard pile. Only continuations that actually transfer physical
    Zoo cards are included; effect-frame card snapshots are deliberately not.
    """

    ids = [
        card["id"]
        for card in [*state["zoo_deck"], *state["zoo_discard"], *state["card_display"]]
        if isinstance(card.get("id"), str) and card["id"].startswith("zoo-")
    ]
    for player in state["players"]:
        ids.extend(
            card["id"] for card in player["hand"]
            if isinstance(card.get("id"), str) and card["id"].startswith("zoo-")
        )
        ids.extend(
            card["id"] for card in player.get("initial_draw", [])
            if isinstance(card.get("id"), str) and card["id"].startswith("zoo-")
        )
        for card in player.get("played_cards", []):
            card_id = card.get("id")
            if isinstance(card_id, str) and card_id.startswith("zoo-"):
                ids.append(card_id)
            ids.extend(
                tucked["id"] for tucked in card.get("tucked_cards", [])
                if isinstance(tucked, Mapping)
                and isinstance(tucked.get("id"), str)
                and tucked["id"].startswith("zoo-")
            )
    ids.extend(
        project["instance_id"] for project in state.get("conservation_projects", [])
        if isinstance(project.get("instance_id"), str)
        and project["instance_id"].startswith("zoo-")
    )
    pending = state.get("resolution", {}).get("pending_choice")
    continuation = pending.get("continuation") if isinstance(pending, Mapping) else None
    if (
        isinstance(continuation, Mapping)
        and continuation.get("type") in {"draw_keep_cards", "scavenge_discard"}
    ):
        drawn = continuation.get("drawn", [])
        if isinstance(drawn, list):
            ids.extend(
                card["id"] for card in drawn
                if isinstance(card, Mapping)
                and isinstance(card.get("id"), str)
                and card["id"].startswith("zoo-")
            )
    return ids


def _present_card(
    card: Mapping[str, Any], indexes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    result = deepcopy(dict(card))
    facts = result.get("facts")
    if isinstance(facts, Mapping):
        for key, value in facts.items():
            result.setdefault(key, deepcopy(value))
        if result.get("kind") in {"animal", "sponsor"}:
            # The Web card face must show the same complete printed-icon set
            # that the executable engine records when this card enters play.
            result["icons"] = printed_icon_counts(facts)
        # ``effects`` on a runtime card contains executable operations.  The
        # imported Sponsor facts also carry short, original-language-neutral
        # mechanic summaries intended for the UI, so expose those under a
        # distinct key instead of overwriting the executable program.
        fact_effects = facts.get("effects")
        if isinstance(fact_effects, list):
            result["mechanism_notes"] = [
                deepcopy(dict(item)) for item in fact_effects
                if isinstance(item, Mapping)
            ]
    kind_to_card_type = {
        "animal": "animal",
        "sponsor": "sponsor",
        "zoo_conservation_project": "conservation_project",
        "final_scoring": "final_scoring",
    }
    kind = result.get("kind")
    if kind in kind_to_card_type:
        result.setdefault("card_type", kind_to_card_type[kind])
    entry_id = result.get("entry_id")
    entry = next((
        collection.get(entry_id)
        for collection in indexes.values()
        if isinstance(entry_id, str) and collection.get(entry_id) is not None
    ), None)
    if entry is not None:
        result["resolved_requirements"] = [{
            "description_cn": explain_predicate(requirement, locale="zh-CN"),
            "description_en": explain_predicate(requirement, locale="en"),
        } for requirement in entry.requirements]
    if result.get("card_type") == "sponsor" or result.get("kind") == "sponsor":
        result["resolved_mechanics"] = resolve_mechanics(
            result.get("effects", []), facts if isinstance(facts, Mapping) else {},
        )
    return result


def _present_pending_choice(
    choice: Any, viewer_seat: int, *, reveal_all_private: bool,
) -> dict[str, Any] | None:
    """Expose a decision only to its owner (or a trusted spectator view).

    Choice options can contain hand cards, Final Scoring cards, and other
    private bindings.  Opponents only need to know whose response is pending;
    copying the complete engine frame here would leak those identities.
    """
    if choice is None:
        return None
    if not isinstance(choice, Mapping):
        raise AssertionError("pending semantic choice must be an object")
    owner = choice.get("seat")
    if reveal_all_private or owner == viewer_seat:
        return deepcopy(dict(choice))
    return {"seat": owner, "hidden": True}


def _present_player(
    player: Mapping[str, Any], private: bool, state: Mapping[str, Any],
    indexes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    tracks = player["tracks"]
    supported_project_details = []
    for project_id in player["supported_projects"]:
        entry = (
            indexes.get("zoo_conservation_projects", {}).get(project_id)
            or indexes.get("base_conservation_projects", {}).get(project_id)
        )
        board_project = next((
            project for project in state["conservation_projects"]
            if project.get("id") == project_id
        ), None)
        claim = None if board_project is None else next((
            item for item in board_project.get("claims", [])
            if int(item.get("seat", -1)) == int(player["seat"])
        ), None)
        supported_project_details.append({
            "id": project_id,
            "display_title": entry.display_title if entry is not None else project_id,
            "level_id": None if claim is None else claim.get("level_id"),
            "on_board": board_project is not None,
        })
    played = [_present_card(card, indexes) for card in player["played_cards"]]
    final_scoring_cards = []
    if private:
        for card in player["final_scoring_cards"]:
            presented = _present_card(card, indexes)
            live_scoring = score_final_card(state, int(player["seat"]), card)
            if live_scoring is not None:
                presented["live_scoring"] = live_scoring
            final_scoring_cards.append(presented)
    else:
        final_scoring_cards = hidden_items(player["final_scoring_cards"])
    row = deepcopy(dict(player))
    row.update({
        "appeal": tracks["appeal"], "conservation": tracks["conservation"],
        "reputation": tracks["reputation"],
        "action_cards": [
            {**deepcopy(card), "strength": card["position"]}
            for card in player["action_cards"]
        ],
        "hand_count": len(player["hand"]),
        "initial_draw_count": len(player.get("initial_draw", [])),
        "hand": [_present_card(card, indexes) for card in player["hand"]] if private else hidden_items(player["hand"]),
        "initial_draw": (
            [_present_card(card, indexes) for card in player.get("initial_draw", [])]
            if private else hidden_items(player.get("initial_draw", []))
        ),
        "final_scoring_cards": final_scoring_cards,
        "played_cards": played,
        "supported_project_details": supported_project_details,
        "conservation_tokens_on_map": player["project_tokens_available"],
        "upgrade_rewards_claimed": [
            2 for value in player["claimed_milestones"] if value == "conservation-2"
        ],
        "conservation_rewards_claimed": [
            at for at in (5, 8) if f"conservation-{at}" in player["claimed_milestones"]
        ],
        "final_card_choice_resolved": len(player["final_scoring_cards"]) == 1,
        "next_break_projection": _next_break_projection(player),
    })
    row["public_summary"] = player_public_summary(row)
    row["map_display"] = map_display(row)
    return row


_PROJECT_TOKEN_REWARD_NAMES = {
    "card": ("精选：从牌库抽一张或从展示区任选一张", "Snap one card from the deck or any display folder"),
    "enclosure-2": ("免费建造一个2格普通围栏", "Build one size-2 standard enclosure for free"),
    "money-5": ("获得5金币", "Gain 5 money"),
    "conservation-1": ("获得1保护点数", "Gain 1 conservation"),
}


def _fixed_income_money(effects: Any) -> int:
    """Return unconditional integer money from an income modifier."""
    if not isinstance(effects, (list, tuple)):
        return 0
    total = 0
    for effect in effects:
        if not isinstance(effect, Mapping):
            continue
        if effect.get("op") == "gain_money":
            amount = effect.get("args", {}).get("amount")
            if isinstance(amount, int) and not isinstance(amount, bool):
                total += amount
        elif effect.get("op") == "choose_effect_order":
            total += _fixed_income_money(effect.get("args", {}).get("effects"))
    return total


def _next_break_projection(player: Mapping[str, Any]) -> dict[str, Any]:
    appeal_money = appeal_income(int(player["tracks"]["appeal"]))
    kiosk_money = official_kiosk_income(player)
    other_money = int(player.get("income", {}).get("other", 0))
    recurring_rewards = []
    guaranteed_extra_money = 0
    for modifier in player.get("modifiers", []):
        if not isinstance(modifier, Mapping) or modifier.get("trigger") != "income":
            continue
        effects = modifier.get("effects", [])
        mechanics = resolve_mechanics(effects, {})
        source_id = str(modifier.get("source_id", modifier.get("id", "income-effect")))
        slot_id = source_id.removeprefix("project-token:")
        reward_name = _PROJECT_TOKEN_REWARD_NAMES.get(slot_id)
        conditional = modifier.get("condition") is not None
        fixed_money = 0 if conditional else _fixed_income_money(effects)
        guaranteed_extra_money += fixed_money
        recurring_rewards.append({
            "source_id": source_id,
            "kind": str(modifier.get("kind", "income_modifier")),
            "title_cn": reward_name[0] if reward_name else source_id,
            "title_en": reward_name[1] if reward_name else source_id,
            "timing_cn": "每次休息的收入步骤",
            "timing_en": "During the income step of every Break",
            "conditional": conditional,
            "guaranteed_money": fixed_money,
            "resolved_mechanics": mechanics,
        })
    committed = player.get("association_workers", {}).get("committed", [])
    workers_to_recall = sum(
        int(item.get("workers", 1)) for item in committed
        if isinstance(item, Mapping)
    )
    hand_count = len(player.get("hand", []))
    hand_limit = int(player.get("hand_limit", 3))
    base_money = appeal_money + kiosk_money + other_money
    return {
        "money_income": {
            "appeal": appeal_money,
            "kiosks": kiosk_money,
            "other": other_money,
            "base_total": base_money,
            "guaranteed_recurring": guaranteed_extra_money,
            "estimated_total": base_money + guaranteed_extra_money,
            "note_cn": "条件式或需选择的收入奖励另列，不计入预计总额。",
            "note_en": "Conditional or choice-based income is listed separately and excluded from the estimate.",
        },
        "workers_to_recall": workers_to_recall,
        "hand_discard_required": max(0, hand_count - hand_limit),
        "action_tokens_to_clear": sum(
            len(card.get("tokens", [])) for card in player.get("action_cards", [])
            if isinstance(card, Mapping)
        ),
        "recurring_rewards": recurring_rewards,
        "association_replenishes": True,
        "display_refreshes": True,
    }


def _break_rules_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    solo = state.get("break", {}).get("mode") == "solo_round"
    steps = [
        ("discard_to_hand_limit", "所有玩家将手牌弃至各自上限", "Every player discards down to their hand limit"),
        ("clear_action_tokens", "移除行动牌上的毒液、缠绕和倍率标记", "Clear Venom, Constriction, and Multiplier tokens from Action cards"),
        ("recall_workers", "收回所有已派出的事务员", "Recall all committed Association workers"),
        ("replenish_association", "补充本轮可用的合作动物园和大学", "Replenish Partner zoos and universities for the new round"),
        ("refresh_display", "弃掉展示区最左侧两张牌并补满六张", "Discard the two leftmost display cards and refill to six"),
        ("take_income", "依次领取魅力、商亭及卡牌收入；持续保护项目奖励再次触发", "Collect Appeal, kiosk, and card income in order; recurring conservation rewards trigger again"),
    ]
    if not solo:
        steps.append(("reset_break", "将休息标记重置到起点", "Reset the Break marker to the start"))
    return {
        "mode": "solo_round" if solo else "shared_track",
        "title_cn": "休息阶段固定流程",
        "title_en": "Fixed Break procedure",
        "steps": [
            {"order": index, "key": key, "description_cn": cn, "description_en": en}
            for index, (key, cn, en) in enumerate(steps, 1)
        ],
        "recurring_rule_cn": "标注“立即 + 每次休息”的玩家板奖励在领取时执行一次，此后每次休息的收入步骤再执行一次。",
        "recurring_rule_en": "A player-board reward marked 'immediate + every Break' resolves once when claimed and again during every later Break income step.",
    }


def _present_association(state: Mapping[str, Any]) -> dict[str, Any]:
    def available(value: Any) -> int:
        return int(value.get("available", 0)) if isinstance(value, Mapping) else int(value)
    return {
        "partner_zoos": {
            key: available(value)
            for key, value in state["association_board"]["partner_zoos"].items()
        },
        "universities": {
            key: available(value)
            for key, value in state["association_board"]["universities"].items()
        },
        "blocked_two_player": (
            ["project-high", "project-middle", "project-low"]
            if state["player_count"] == 2 else []
        ),
        "donations": deepcopy(state["donations_made"]),
    }


def _association_display(state: Mapping[str, Any]) -> dict[str, Any]:
    board = _present_association(state)
    return {
        "partner_zoos": [
            {"id": key, "remaining": value, "owners": [
                player["seat"] for player in state["players"]
                if any((asset.get("continent") if isinstance(asset, Mapping) else asset) == key for asset in player["partner_zoos"])
            ]}
            for key, value in board["partner_zoos"].items()
        ],
        "universities": [
            {"id": key, "remaining": value, "owners": [
                player["seat"] for player in state["players"]
                if any((asset.get("id") if isinstance(asset, Mapping) else asset) == key for asset in player["universities"])
            ]}
            for key, value in board["universities"].items()
        ],
        "workers": [
            {"seat": player["seat"], **deepcopy(worker)}
            for player in state["players"]
            for worker in player["association_workers"]["committed"]
        ],
        "donations": deepcopy(state["donations_made"]),
        "donation_slots": _present_donation_spaces(state),
        "blocked_spaces": board["blocked_two_player"],
    }


def _present_donation_spaces(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    donations = [
        item for item in state.get("donations_made", [])
        if isinstance(item, Mapping)
    ]
    spaces: list[dict[str, Any]] = []
    for position, cost in enumerate(state["donation_costs"][:-1], 1):
        record = next((item for item in donations if item.get("cost") == cost), None)
        source = None if record is None else record.get("source", "player")
        spaces.append({
            "position": position,
            "cost": cost,
            "status": (
                "available" if record is None
                else "blocked" if source == "solo_tile"
                else "claimed"
            ),
            "seat": None if record is None else record.get("seat"),
            "source": source,
            "donation_count": 0 if record is None else 1,
        })
    repeatable_cost = int(state["donation_costs"][-1])
    repeatable = [item for item in donations if item.get("cost") == repeatable_cost]
    spaces.append({
        "position": len(state["donation_costs"]),
        "cost": repeatable_cost,
        "status": "repeatable",
        "seat": repeatable[-1].get("seat") if repeatable else None,
        "source": "repeatable",
        "donation_count": len(repeatable),
        "seats": [item.get("seat") for item in repeatable],
    })
    return spaces


def _present_solo_board(state: Mapping[str, Any]) -> dict[str, Any] | None:
    track = state.get("break", {})
    if state.get("player_count") != 1 or track.get("mode") != "solo_round":
        return None
    round_size = int(track["solo_total_tokens"])
    tokens_left = int(track["solo_tokens_left"])
    donation_blocks = deepcopy(track.get("solo_donation_blocks", []))
    return {
        "round": int(track["solo_round"]),
        "rounds": 6,
        "round_size": round_size,
        "tokens_left": tokens_left,
        "tokens_moved": round_size - tokens_left,
        "completed_breaks": int(track["count"]),
        "schedule": [7, 6, 5, 4, 3, 2],
        "next_boundary": "final_scoring" if round_size == 2 else "break",
        "starting_appeal": int(state.get("solo_starting_appeal", 20)),
        "donation_blocks": donation_blocks,
        "donation_spaces": _present_donation_spaces(state),
        "tokens_next_to_12": sum(
            1 for item in donation_blocks
            if item.get("source") == "solo_tile_next_to_12"
        ),
    }


def _present_projects(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    indexes: Mapping[str, Mapping[str, Any]],
    *,
    base: bool,
    viewer_seat: int,
) -> list[dict[str, Any]]:
    result = []
    for project in state["conservation_projects"]:
        if bool(project.get("base")) != base:
            continue
        row = deepcopy(project)
        entry_id = project["id"]
        collection = (
            "base_conservation_projects" if base else "zoo_conservation_projects"
        )
        entry = indexes.get(collection, {}).get(entry_id)
        levels = [] if entry is None else list(entry.facts.get("levels", []))
        reward_by_id = {
            level.get("id"): int(level.get("conservation", 0))
            for level in levels if isinstance(level, Mapping)
        }
        row["tag"] = entry.display_title if entry is not None else entry_id
        row["display_title"] = entry.display_title if entry is not None else entry_id
        row["display_summary"] = entry.display_summary if entry is not None else ""
        row["criterion_cn"] = (
            entry.facts.get("criterion_cn", "") if entry is not None else ""
        )
        row["criterion_en"] = (
            entry.facts.get("criterion_en", "") if entry is not None else ""
        )
        imported_tiers = entry.facts.get("tiers", []) if entry is not None else []
        row["tiers"] = (
            [deepcopy(dict(tier)) for tier in imported_tiers if isinstance(tier, Mapping)]
            if isinstance(imported_tiers, list) and imported_tiers
            else [
                {
                    "id": level.get("id"),
                    "requirement": next((
                        item.get("args", {}).get("right")
                        for item in level.get("requirements", [])
                        if isinstance(item, Mapping)
                        and isinstance(item.get("args"), Mapping)
                        and item.get("op") == "compare"
                    ), None),
                    "conservation": int(level.get("conservation", 0)),
                    "reputation": int(level.get("reputation", 0)),
                }
                for level in levels if isinstance(level, Mapping)
            ]
        )
        # Imported tiers carry the human-readable requirements, while the engine
        # levels carry the canonical high/middle/low slot identity.  Project the
        # two together so clients never have to infer which physical slot is
        # covered in a two-player game.
        blocked_levels = set(project.get("blocked_levels", []))
        for index, tier in enumerate(row["tiers"]):
            semantic_level = levels[index] if index < len(levels) else {}
            if isinstance(semantic_level, Mapping):
                tier["id"] = semantic_level.get("id")
            tier["blocked"] = tier.get("id") in blocked_levels
        row["levels"] = list(reward_by_id.values())
        row["claims"] = [
            {
                **deepcopy(claim),
                "level": reward_by_id.get(claim.get("level_id"), 0),
            }
            for claim in project.get("claims", [])
        ]
        row["card_type"] = "conservation_project"
        if entry is not None:
            legal_levels = legal_project_support_options(
                engine, state, viewer_seat, entry,
            )
            eligible_by_id = {
                str(level["id"]): {
                    "id": str(level["id"]),
                    "conservation": int(level.get("conservation", 0)),
                    "reputation": int(level.get("reputation", 0)),
                }
                for level in legal_levels
                if isinstance(level, Mapping) and isinstance(level.get("id"), str)
            }
            row["eligible_levels"] = list(eligible_by_id.values())
            row["best_eligible_level"] = max(
                eligible_by_id.values(),
                key=lambda level: (
                    int(level.get("conservation", 0)),
                    int(level.get("reputation", 0)),
                ),
                default=None,
            )
            metric = _project_metric_for_viewer(
                engine, state, viewer_seat, entry,
            )
            if metric is not None:
                row.update(metric)
        player = state["players"][viewer_seat]
        row["effective_action_strength_required"] = min([
            5,
            *(
                int(modifier["amount"])
                for modifier in player.get("modifiers", [])
                if modifier.get("kind") == "association_project_strength"
            ),
        ])
        row["workers_required"] = 1 + sum(
            worker.get("task") == "conservation-project"
            for worker in player["association_workers"]["committed"]
        )
        row["project_token_available"] = (
            int(player.get("project_tokens_available", 0)) > 0
        )
        result.append(row)
    return result


def _project_metric_for_viewer(
    engine: SemanticEngine,
    state: Mapping[str, Any],
    viewer_seat: int,
    entry: Any,
) -> dict[str, Any] | None:
    """Expose the authoritative current value for simple tiered projects."""
    levels = entry.facts.get("levels", [])
    first = levels[0] if isinstance(levels, list) and levels else None
    requirements = first.get("requirements", []) if isinstance(first, Mapping) else []
    requirement = requirements[0] if len(requirements) == 1 else None
    if not isinstance(requirement, Mapping):
        return None
    operation = requirement.get("op")
    args = requirement.get("args", {})
    if operation == "has_icon" and isinstance(args.get("icon"), str):
        icon = str(args["icon"])
        return {
            "current_metric": f"actor.icons.{icon}",
            "current_value": int(state["players"][viewer_seat]["icons"].get(icon, 0)),
        }
    if operation == "compare" and isinstance(args.get("left"), Mapping):
        reference = args["left"].get("ref")
        if isinstance(reference, str) and reference.startswith("actor."):
            from .semantics import EvaluationContext

            value = engine.value(
                args["left"],
                EvaluationContext(
                    state=state, actor_seat=viewer_seat,
                    card={"id": entry.id, "kind": entry.kind, "facts": dict(entry.facts)},
                ),
            )
            if isinstance(value, int) and not isinstance(value, bool):
                return {"current_metric": reference, "current_value": value}
    return None
