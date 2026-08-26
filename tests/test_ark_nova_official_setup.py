from pathlib import Path
import unittest

from agentbga.ark_nova_official import load_content_pack, setup_official_game


class ArkNovaOfficialSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.pack = load_content_pack(
            root / "content-packs" / "ark-nova" / "base-en-draft"
        )

    def test_multiplayer_setup_uses_printed_break_lengths_and_starting_appeal(self):
        expected = {2: 9, 3: 12, 4: 15}
        for player_count, break_limit in expected.items():
            with self.subTest(player_count=player_count):
                state = setup_official_game(player_count, 41, pack=self.pack)
                self.assertEqual(break_limit, state["break"]["limit"])
                self.assertEqual(
                    list(range(player_count)),
                    [player["tracks"]["appeal"] for player in state["players"]],
                )
                self.assertTrue(all(
                    player["tracks"]["conservation"] == 0
                    for player in state["players"]
                ))

    def test_two_player_base_projects_block_left_high_middle_and_right_low(self):
        state = setup_official_game(2, 42, pack=self.pack)
        base_projects = [
            project for project in state["conservation_projects"]
            if project["base"]
        ]
        self.assertEqual(
            [["high"], ["middle"], ["low"]],
            [project["blocked_levels"] for project in base_projects],
        )


if __name__ == "__main__":
    unittest.main()
