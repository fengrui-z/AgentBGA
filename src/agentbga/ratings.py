"""Order-independent tournament scores from complete multiplayer rankings."""

from __future__ import annotations

import math
from typing import Any, Iterable


def _participants(row: dict[str, Any]) -> dict[int, str]:
    result: dict[int, str] = {}
    for participant in row.get("participants", []):
        if not isinstance(participant, dict):
            continue
        seat = participant.get("seat")
        identifier = participant.get("participant_id")
        if isinstance(seat, int) and isinstance(identifier, str) and identifier:
            result[seat] = identifier
    return result


def _ranking_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    result = row.get("result")
    if not isinstance(result, dict):
        return []
    rankings = result.get("rankings")
    return [item for item in rankings if isinstance(item, dict)] if isinstance(rankings, list) else []


def _fit_bradley_terry(
    identifiers: list[str], comparisons: list[tuple[str, str, float, float]], *,
    iterations: int = 4000, learning_rate: float = 0.08, l2: float = 0.02,
) -> dict[str, float]:
    """Fit batch Bradley-Terry skills with Adam and a weak zero-centred prior."""
    if not identifiers:
        return {}
    if not comparisons:
        return {identifier: 0.0 for identifier in identifiers}

    index = {identifier: position for position, identifier in enumerate(identifiers)}
    skill = [0.0] * len(identifiers)
    first_moment = [0.0] * len(identifiers)
    second_moment = [0.0] * len(identifiers)
    beta1, beta2, epsilon = 0.9, 0.999, 1e-8
    comparison_weight = sum(weight for _, _, _, weight in comparisons)

    for step in range(1, iterations + 1):
        gradient = [-l2 * value for value in skill]
        for left, right, outcome, weight in comparisons:
            left_index = index[left]
            right_index = index[right]
            difference = max(-30.0, min(30.0, skill[left_index] - skill[right_index]))
            expected = 1.0 / (1.0 + math.exp(-difference))
            residual = weight * (outcome - expected)
            gradient[left_index] += residual
            gradient[right_index] -= residual

        largest_update = 0.0
        for position in range(len(skill)):
            value = gradient[position] / comparison_weight
            first_moment[position] = beta1 * first_moment[position] + (1.0 - beta1) * value
            second_moment[position] = beta2 * second_moment[position] + (1.0 - beta2) * value * value
            corrected_first = first_moment[position] / (1.0 - beta1**step)
            corrected_second = second_moment[position] / (1.0 - beta2**step)
            update = learning_rate * corrected_first / (math.sqrt(corrected_second) + epsilon)
            skill[position] += update
            largest_update = max(largest_update, abs(update))

        mean = sum(skill) / len(skill)
        skill = [value - mean for value in skill]
        if step > 200 and largest_update < 1e-8:
            break

    return dict(zip(identifiers, skill, strict=True))


def score_matches(matches: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return Elo-scaled Bradley-Terry ratings and descriptive match scores."""
    rows = list(matches)
    identifiers = sorted({identifier for row in rows for identifier in _participants(row).values()})
    counts_by_game: dict[str, set[int]] = {}
    for row in rows:
        game = row.get("game")
        player_count = row.get("player_count")
        if isinstance(game, str) and isinstance(player_count, int):
            counts_by_game.setdefault(game, set()).add(player_count)
    stats = {
        identifier: {
            "participant_id": identifier,
            "scheduled": 0,
            "completed": 0,
            "failed_exposures": 0,
            "first_place_equivalent": 0.0,
            "rank_sum": 0.0,
            "pairwise_points": 0.0,
            "pairwise_weight": 0.0,
            "pairwise_comparisons": 0,
        }
        for identifier in identifiers
    }
    comparisons: list[tuple[str, str, float, float]] = []

    for row in rows:
        by_seat = _participants(row)
        for identifier in by_seat.values():
            stats[identifier]["scheduled"] += 1
        if row.get("status") != "ok":
            for identifier in by_seat.values():
                stats[identifier]["failed_exposures"] += 1
            continue

        rankings = _ranking_rows(row)
        ranked: list[tuple[str, float]] = []
        for fallback_rank, ranking in enumerate(rankings, start=1):
            seat = ranking.get("seat")
            identifier = by_seat.get(seat) if isinstance(seat, int) else None
            if identifier is None:
                continue
            raw_rank = ranking.get("rank", fallback_rank)
            rank = float(raw_rank) if isinstance(raw_rank, (int, float)) else float(fallback_rank)
            ranked.append((identifier, rank))
            stats[identifier]["completed"] += 1
            stats[identifier]["rank_sum"] += rank

        if len(ranked) < 2:
            continue
        game = row.get("game")
        game_count = len(counts_by_game.get(game, {len(ranked)})) if isinstance(game, str) else 1
        match_weight = 1.0 / game_count
        pair_weight = match_weight / (len(ranked) - 1)
        best_rank = min(rank for _, rank in ranked)
        first = [identifier for identifier, rank in ranked if rank == best_rank]
        for identifier in first:
            stats[identifier]["first_place_equivalent"] += 1.0 / len(first)

        for left_index, (left, left_rank) in enumerate(ranked):
            for right, right_rank in ranked[left_index + 1:]:
                outcome = 1.0 if left_rank < right_rank else 0.0 if left_rank > right_rank else 0.5
                comparisons.append((left, right, outcome, pair_weight))
                stats[left]["pairwise_points"] += pair_weight * outcome
                stats[right]["pairwise_points"] += pair_weight * (1.0 - outcome)
                stats[left]["pairwise_weight"] += pair_weight
                stats[right]["pairwise_weight"] += pair_weight
                stats[left]["pairwise_comparisons"] += 1
                stats[right]["pairwise_comparisons"] += 1

    skill = _fit_bradley_terry(identifiers, comparisons)
    elo_scale = 400.0 / math.log(10.0)
    leaderboard: list[dict[str, Any]] = []
    for identifier in identifiers:
        item = stats[identifier]
        completed = item["completed"]
        pairwise_weight = item["pairwise_weight"]
        leaderboard.append({
            "participant_id": identifier,
            "elo": round(1500.0 + elo_scale * skill.get(identifier, 0.0), 1),
            "pws": round(item["pairwise_points"] / pairwise_weight, 4)
            if pairwise_weight else None,
            "average_rank": round(item["rank_sum"] / completed, 4) if completed else None,
            "first_place_equivalent": round(item["first_place_equivalent"], 4),
            "scheduled": item["scheduled"],
            "completed": completed,
            "failed_exposures": item["failed_exposures"],
            "pairwise_comparisons": item["pairwise_comparisons"],
        })
    leaderboard.sort(key=lambda item: (-item["elo"], item["participant_id"]))
    for rank, item in enumerate(leaderboard, start=1):
        item["rating_rank"] = rank
    return leaderboard
