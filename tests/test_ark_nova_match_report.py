import unittest

from agentbga.ark_nova_match_report import _played_card_count


class ArkNovaMatchReportTests(unittest.TestCase):
    def test_sponsor_count_accepts_official_and_controlled_card_shapes(self):
        player = {
            "played_cards": [
                {"id": "zoo-220", "kind": "sponsor"},
                {"id": "zoo-248", "kind": "sponsor", "unique_building": True},
                {"id": "controlled-sponsor", "card_type": "sponsor"},
                {"id": "zoo-486", "kind": "animal"},
            ],
        }

        self.assertEqual(3, _played_card_count(player, "sponsor"))
        self.assertEqual(1, _played_card_count(player, "animal"))

    def test_sponsor_count_handles_missing_or_invalid_played_zone(self):
        self.assertEqual(0, _played_card_count({}, "sponsor"))
        self.assertEqual(0, _played_card_count({"played_cards": None}, "sponsor"))


if __name__ == "__main__":
    unittest.main()
