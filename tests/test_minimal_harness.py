import tempfile
import unittest
from unittest import mock

from agentbga.harness_features import HarnessFeatures
from agentbga.agents import PlayerConfig
from agentbga.minimal_harness import DirectGameAgent


class MinimalHarnessTests(unittest.TestCase):
    def test_choose_accumulates_every_provider_response(self):
        with tempfile.TemporaryDirectory() as directory:
            config = PlayerConfig.from_dict({
                "name": "Minimal", "backend": "minimal", "model": "test",
                "base_url": "https://example.test/v1",
            }, 0)
            agent = DirectGameAgent(config, "match", 0, runs_root=directory)
            agent._call_llm = mock.Mock(return_value={
                "content": "done", "reasoning_content": "",
                "tool_calls": [{
                    "id": "call-1", "function": {
                        "name": "submit_action",
                        "arguments": '{"action_id":"action-1"}',
                    },
                }],
                "usage": {
                    "prompt_tokens": 100, "completion_tokens": 20,
                    "prompt_tokens_details": {"cached_tokens": 75},
                    "completion_tokens_details": {"reasoning_tokens": 10},
                },
                "model": "test", "finish_reason": "tool_calls",
            })
            observation = {"game": "test", "turn_count": 0, "state_version": 0}
            legal = [{"id": "action-1", "action": {"type": "pass"}}]

            action_id, metadata = agent.choose(observation, legal)

            self.assertEqual("action-1", action_id)
            self.assertEqual(120, metadata["usage"]["total_tokens"])
            self.assertEqual(75, metadata["usage"]["cached_input_tokens"])
            self.assertEqual(metadata["usage"], agent.usage_summary())

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

    def test_baseline_session_compacts_at_transport_safety_limit(self):
        agent = object.__new__(DirectGameAgent)
        agent.features = HarnessFeatures.baseline()
        agent.game_id = "ark_nova"
        agent.keep_recent = 2
        agent._journal = []
        messages = []
        for turn in range(18):
            messages.extend([
                {"role": "user", "content": f"You are seat 0 in turn {turn}." + "x" * 20000},
                {"role": "assistant", "content": "", "tool_calls": [{
                    "id": f"tool-{turn}", "type": "function",
                    "function": {"name": "observe", "arguments": "{}"},
                }]},
                {"role": "tool", "tool_call_id": f"tool-{turn}", "content": "{}"},
            ])
        agent._messages = messages

        agent._maybe_compact()

        self.assertEqual("system", agent._messages[0]["role"])
        self.assertEqual("user", agent._messages[1]["role"])
        self.assertTrue(agent._messages[1]["content"].startswith("You are seat "))
        self.assertLess(len(agent._messages), len(messages))


if __name__ == "__main__":
    unittest.main()
