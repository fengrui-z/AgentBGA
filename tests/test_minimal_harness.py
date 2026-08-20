import unittest

from agentbga.minimal_harness import DirectGameAgent


class MinimalHarnessTests(unittest.TestCase):
    def test_splendor_observation_uses_unambiguous_color_names(self):
        agent = object.__new__(DirectGameAgent)
        agent.seat = 0
        observation = {
            "game": "splendor",
            "turn_count": 7,
            "players": [
                {
                    "score": 3,
                    "tokens": {"black": 1, "blue": 3, "gold": 0},
                    "bonuses": {"black": 4, "blue": 2},
                    "purchased_count": 6,
                    "reserved": [],
                },
                {
                    "score": 2,
                    "bonuses": {"black": 1, "blue": 2},
                    "purchased_count": 3,
                },
            ],
            "bank": {},
            "market": {},
            "available_nobles": [],
        }

        formatted = agent._format_observation(observation)

        self.assertIn("Tokens: black:1 blue:3", formatted)
        self.assertIn("Bonuses: black=4 blue=2 (6 cards)", formatted)
        self.assertIn("Opponent: 3 cards (bonuses: black=1 blue=2)", formatted)
        self.assertNotIn("Tokens: B:", formatted)
        self.assertNotIn("Bonuses: B=", formatted)


if __name__ == "__main__":
    unittest.main()
