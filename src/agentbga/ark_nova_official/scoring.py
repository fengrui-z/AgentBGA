"""End-game trigger and official track-crossing score pipeline."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from .semantics import SemanticEngine, SemanticRuleError
from .state import validate_semantic_state
from .final_scoring_effects import score_final_card
from ..ark_nova_tracks import conservation_score_offset


def _target_number(target_by_conservation: Sequence[int] | Mapping[int, int], conservation: int) -> int:
    try:
        value = target_by_conservation[conservation]
    except (IndexError, KeyError, TypeError) as error:
        raise SemanticRuleError(
            f"missing appeal target for conservation space {conservation}",
        ) from error
    if not isinstance(value, int) or isinstance(value, bool):
        raise SemanticRuleError("appeal target table must contain integers")
    return value


def counters_crossed(
    state: Mapping[str, Any], seat: int,
    target_by_conservation: Sequence[int] | Mapping[int, int],
) -> bool:
    player = state["players"][seat]
    tracks = player["tracks"]
    return tracks["appeal"] >= _target_number(target_by_conservation, tracks["conservation"])


def check_endgame_trigger(
    state: dict[str, Any], seat: int, *, boundary: str,
    target_by_conservation: Sequence[int] | Mapping[int, int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Check endgame only at a legal boundary: end of turn or during a Break."""
    if boundary not in {"end_of_turn", "break"}:
        raise SemanticRuleError("endgame may only be checked at end_of_turn or break")
    next_state = deepcopy(state)
    if next_state["endgame"]["triggered"] or not counters_crossed(
        next_state, seat, target_by_conservation,
    ):
        return next_state, []
    next_state["endgame"].update({
        "triggered": True,
        "triggered_by": seat,
        "trigger_boundary": boundary,
    })
    return next_state, [{"type": "endgame_triggered", "seat": seat, "boundary": boundary}]


def score_game(
    engine: SemanticEngine,
    state: dict[str, Any],
    target_by_conservation: Sequence[int] | Mapping[int, int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve all semantic end-game effects, then calculate official VP distance.

    The scoring-area table is board data, not logic, and therefore must come
    from the reviewed map/track content pack.
    """
    next_state = deepcopy(state)
    if next_state["resolution"]["queue"] or next_state["resolution"]["pending_choice"] is not None:
        raise SemanticRuleError("cannot score while a semantic resolution is pending")
    if (
        not next_state["endgame"].get("final_scoring_discard_completed")
        and any(len(player["final_scoring_cards"]) > 1 for player in next_state["players"])
    ):
        raise SemanticRuleError(
            "Final Scoring card discard must finish before end-game scoring",
        )
    pre_endgame_tracks = [
        {
            "appeal": int(player["tracks"]["appeal"]),
            "conservation": int(player["tracks"]["conservation"]),
        }
        for player in next_state["players"]
    ]
    events: list[dict[str, Any]] = []
    for seat, player in enumerate(next_state["players"]):
        scoring_sources = [*player["played_cards"], *player["final_scoring_cards"]]
        for source in scoring_sources:
            award = score_final_card(next_state, seat, source)
            if award is not None:
                before = next_state["players"][seat]["tracks"]["conservation"]
                limit = int(next_state["track_limits"]["conservation"])
                after = min(limit, before + int(award["conservation"]))
                next_state["players"][seat]["tracks"]["conservation"] = after
                score_entry = {
                    "kind": "final_scoring_card",
                    **deepcopy(award),
                    "awarded_conservation": after - before,
                }
                next_state["players"][seat]["score_entries"].append(score_entry)
                events.append({
                    "type": "final_scoring_card_scored", "seat": seat,
                    **deepcopy(score_entry),
                })
            effects = source.get("effects", [])
            if not isinstance(effects, list):
                raise SemanticRuleError("scoring source effects must be an array")
            before_effects = deepcopy(next_state["players"][seat]["tracks"])
            next_state, resolved = engine.start_effects(
                next_state,
                seat,
                effects,
                source_id=str(source.get("id", "unknown-scoring-source")),
                card=source,
                timing="end_of_game",
            )
            if next_state["resolution"]["pending_choice"] is not None:
                raise SemanticRuleError("end-game card semantics may not open a choice window")
            events.extend(resolved)
            after_effects = next_state["players"][seat]["tracks"]
            track_deltas = {
                track: int(after_effects.get(track, 0)) - int(before_effects.get(track, 0))
                for track in ("appeal", "conservation", "reputation")
                if int(after_effects.get(track, 0)) != int(before_effects.get(track, 0))
            }
            if track_deltas:
                score_entry = {
                    "kind": "endgame_card_effect",
                    "card_id": str(source.get("entry_id", source.get("id", "unknown"))),
                    "card_instance_id": str(source.get("id", "unknown")),
                    "card_kind": str(source.get("kind", "unknown")),
                    "track_deltas": track_deltas,
                }
                next_state["players"][seat]["score_entries"].append(score_entry)
                events.append({
                    "type": "endgame_card_effect_scored", "seat": seat,
                    **deepcopy(score_entry),
                })

    rows = []
    for seat, player in enumerate(next_state["players"]):
        appeal = player["tracks"]["appeal"]
        conservation = player["tracks"]["conservation"]
        target = _target_number(target_by_conservation, conservation)
        map_reward = player.get("map", {}).get("completion_reward", {})
        map_completion_points = (
            int(map_reward.get("amount", 0))
            if player.get("map", {}).get("completion_reward_claimed")
            and map_reward.get("type") == "gain_appeal"
            else 0
        )
        if map_completion_points:
            player["score_entries"].append({
                "kind": "map_completion", "victory_points": map_completion_points,
            })
            events.append({
                "type": "map_completion_scored", "seat": player["seat"],
                "victory_points": map_completion_points,
            })
        victory_points = appeal + map_completion_points - target
        pre_tracks = pre_endgame_tracks[seat]
        final_track_score = (
            appeal + map_completion_points + conservation_score_offset(conservation)
        )
        pre_endgame_track_score = (
            pre_tracks["appeal"]
            + conservation_score_offset(pre_tracks["conservation"])
        )
        endgame_scoring_points = final_track_score - pre_endgame_track_score
        supported_projects = len(player["supported_projects"])
        rows.append({
            "seat": player["seat"],
            "appeal": appeal,
            "conservation": conservation,
            "target_appeal": target,
            "victory_points": victory_points,
            "map_completion_points": map_completion_points,
            "pre_endgame_appeal": pre_tracks["appeal"],
            "pre_endgame_conservation": pre_tracks["conservation"],
            "pre_endgame_track_score": pre_endgame_track_score,
            "final_track_score": final_track_score,
            "endgame_scoring_points": endgame_scoring_points,
            "supported_projects": supported_projects,
            "score_entries": deepcopy(player["score_entries"]),
            "rank": None,
            **({"solo_won": victory_points >= 0} if next_state["player_count"] == 1 else {}),
        })
    ordered = sorted(rows, key=lambda row: (-row["victory_points"], -row["supported_projects"], row["seat"]))
    previous_key = None
    previous_rank = 0
    for index, row in enumerate(ordered, 1):
        tie_key = (row["victory_points"], row["supported_projects"])
        if tie_key != previous_key:
            previous_rank = index
            previous_key = tie_key
        row["rank"] = previous_rank
    next_state["status"] = "finished"
    next_state["phase"] = "finished"
    next_state["endgame"]["results"] = ordered
    if next_state["player_count"] == 1:
        next_state["endgame"]["solo_won"] = bool(ordered[0]["solo_won"])
    events.append({"type": "final_scoring_completed", "rankings": deepcopy(ordered)})
    validate_semantic_state(next_state)
    return next_state, events
