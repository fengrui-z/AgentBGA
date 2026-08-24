from __future__ import annotations

import unittest

from agentbga.ratings import score_matches


def match(*ranked: tuple[str, int]) -> dict:
    return {
        "status": "ok",
        "participants": [
            {"participant_id": identifier, "seat": seat}
            for seat, (identifier, _) in enumerate(ranked)
        ],
        "result": {
            "rankings": [
                {"seat": seat, "rank": rank, "score": len(ranked) - rank}
                for seat, (_, rank) in enumerate(ranked)
            ],
        },
    }


class RatingTests(unittest.TestCase):
    def test_multiplayer_rankings_produce_ordered_elo_and_pws(self):
        leaderboard = score_matches([
            match(("alpha", 1), ("beta", 2), ("gamma", 3)),
            match(("alpha", 1), ("gamma", 2), ("beta", 3)),
        ])
        by_id = {row["participant_id"]: row for row in leaderboard}
        self.assertGreater(by_id["alpha"]["elo"], by_id["beta"]["elo"])
        self.assertGreater(by_id["alpha"]["elo"], by_id["gamma"]["elo"])
        self.assertEqual(1.0, by_id["alpha"]["pws"])
        self.assertAlmostEqual(1500.0, sum(row["elo"] for row in leaderboard) / 3, places=1)

    def test_ties_split_pairwise_points_and_first_place_credit(self):
        leaderboard = score_matches([match(("alpha", 1), ("beta", 1), ("gamma", 3))])
        by_id = {row["participant_id"]: row for row in leaderboard}
        self.assertAlmostEqual(0.75, by_id["alpha"]["pws"])
        self.assertAlmostEqual(0.75, by_id["beta"]["pws"])
        self.assertEqual(0.5, by_id["alpha"]["first_place_equivalent"])
        self.assertEqual(0.5, by_id["beta"]["first_place_equivalent"])

    def test_rating_is_invariant_to_match_order(self):
        rows = [
            match(("alpha", 1), ("beta", 2)),
            match(("beta", 1), ("gamma", 2)),
            match(("alpha", 1), ("gamma", 2)),
        ]
        forward = {row["participant_id"]: row["elo"] for row in score_matches(rows)}
        reverse = {row["participant_id"]: row["elo"] for row in score_matches(reversed(rows))}
        self.assertEqual(forward, reverse)

    def test_failed_matches_are_visible_but_not_scored(self):
        failed = {
            "status": "error",
            "participants": [
                {"participant_id": "alpha", "seat": 0},
                {"participant_id": "beta", "seat": 1},
            ],
        }
        leaderboard = score_matches([failed])
        self.assertEqual({1500.0}, {row["elo"] for row in leaderboard})
        self.assertEqual({1}, {row["failed_exposures"] for row in leaderboard})
        self.assertEqual({0}, {row["completed"] for row in leaderboard})


if __name__ == "__main__":
    unittest.main()
