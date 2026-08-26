"""Runnable official-base Ark Nova game plugin."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from ..ark_nova_presentation import map_display, player_public_summary, public_tracks
from ..ark_nova_tracks import conservation_score_offset, conservation_target_appeal
from ..game import GameRuleError
from ..mechanics import action_accepted, hidden_items, state_digest
from .action_domains import apply_official_action, content_entry_indexes, legal_official_actions
from .cards import printed_icon_counts, terrain_requirement_icon_counts
from .content import ContentPack
from .final_scoring_effects import score_final_card
from .milestones import queue_endgame_final_scoring_discard
from .presentation import resolve_mechanics
from .rounds import advance_solo_round_after_turn, queue_break, queue_solo_break
from .scoring import check_endgame_trigger, score_game
from .semantics import SemanticEngine, SemanticRuleError
from .setup import (
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
        self.engine = SemanticEngine()

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.game_id,
            "name": "Ark Nova",
            "rules_version": self.rules_version,
            "players": {"minimum": 1, "maximum": 4},
            "hidden_information": True,
            "implementation_status": "official_base_candidate",
            "runnable": True,
            "decision_model": "simultaneous_setup_then_player_turns",
            "action_types": ["animals", "cards", "build", "association", "sponsors"],
            "map": "map_zero_flat_top_polyhex_v3",
            "content_pack": self.pack.manifest.pack_id,
            "content_version": self.pack.manifest.content_version,
            "content_sha256": self.pack.content_sha256,
            "content_scope": (
                "255 physical base cards: 128 Animals, 64 Sponsors, 32 Conservation "
                "Projects, 11 Final Scoring cards, and five Action cards; Map 0"
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
        return [
            {"id": item["id"], "action": deepcopy(item["action"])}
            for item in legal_official_actions(
                self.engine, state, seat, self.indexes,
            )
        ]

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
        return {
            "game": self.game_id,
            "rules_version": state["rules_version"],
            "implementation_status": state["implementation_status"],
            "viewer_seat": seat,
            "status": state["status"], "phase": state["phase"],
            "turn_count": state["turn"]["number"],
            "decision_count": state.get("decision_count", 0),
            "active_seat": state["active_seat"],
            "turn": {
                "active_seat": state["active_seat"],
                "decision": state["phase"],
                "action_card": (
                    None if state["turn"].get("action_session") is None
                    else state["turn"]["action_session"].get("action")
                ),
                "remaining_plays": 0,
            },
            "break_track": {
                "position": state["break"]["position"],
                "limit": state["break"].get("limit") or 0,
                "start_marker": f"players-{state['player_count']}",
                "triggered": bool(state["break"]["pending"]),
            },
            "card_display": [_present_card(card) for card in state["card_display"]],
            "game_board_bonus_tiles": [
                {**deepcopy(tile), "milestone": int(at)}
                for at in ("5", "8")
                for tile in state["conservation_bonus_slots"][at]
            ],
            "deck_count": len(state["zoo_deck"]),
            "discard_count": len(state["zoo_discard"]),
            "base_conservation_projects": _present_projects(state, self.indexes),
            "association_board": association,
            "association_display": _association_display(state),
            "public_tracks": public_tracks(projection),
            "players": rows,
            "rankings": deepcopy(state["endgame"].get("results")),
            "end_reason": "track_crossing" if state["status"] == "finished" else None,
            "pending_choice": deepcopy(state["resolution"].get("pending_choice")),
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
    ]
    for player in state["players"]:
        ids.extend(card["id"] for card in player["hand"])
        ids.extend(card["id"] for card in player.get("initial_draw", []))
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


def _present_card(card: Mapping[str, Any]) -> dict[str, Any]:
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
    if result.get("card_type") == "sponsor" or result.get("kind") == "sponsor":
        result["resolved_mechanics"] = resolve_mechanics(
            result.get("effects", []), facts if isinstance(facts, Mapping) else {},
        )
    return result


def _present_player(
    player: Mapping[str, Any], private: bool, state: Mapping[str, Any],
) -> dict[str, Any]:
    tracks = player["tracks"]
    played = [_present_card(card) for card in player["played_cards"]]
    final_scoring_cards = []
    if private:
        for card in player["final_scoring_cards"]:
            presented = _present_card(card)
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
        "hand": [_present_card(card) for card in player["hand"]] if private else hidden_items(player["hand"]),
        "initial_draw": (
            [_present_card(card) for card in player.get("initial_draw", [])]
            if private else hidden_items(player.get("initial_draw", []))
        ),
        "final_scoring_cards": final_scoring_cards,
        "played_cards": played,
        "conservation_tokens_on_map": player["project_tokens_available"],
        "upgrade_rewards_claimed": [
            2 for value in player["claimed_milestones"] if value == "conservation-2"
        ],
        "conservation_rewards_claimed": [
            at for at in (5, 8) if f"conservation-{at}" in player["claimed_milestones"]
        ],
        "final_card_choice_resolved": len(player["final_scoring_cards"]) == 1,
    })
    row["public_summary"] = player_public_summary(row)
    row["map_display"] = map_display(row)
    return row


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
        "donation_slots": [
            {
                "position": index + 1, "cost": cost,
                "status": "claimed" if index < len(state["donations_made"]) else "available",
                "seat": state["donations_made"][index]["seat"] if index < len(state["donations_made"]) else None,
            }
            for index, cost in enumerate(state["donation_costs"])
        ],
        "blocked_spaces": board["blocked_two_player"],
    }


def _present_projects(
    state: Mapping[str, Any], indexes: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for project in state["conservation_projects"]:
        if not project.get("base"):
            continue
        row = deepcopy(project)
        entry_id = project["id"]
        entry = indexes.get("base_conservation_projects", {}).get(entry_id)
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
        result.append(row)
    return result
