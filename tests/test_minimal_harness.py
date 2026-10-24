import tempfile
import ssl
from dataclasses import replace
import unittest
from unittest import mock

from agentbga.harness_features import HarnessFeatures
from agentbga.agents import PlayerConfig
from agentbga.minimal_harness import DirectGameAgent


class MinimalHarnessTests(unittest.TestCase):
    def test_api_requests_verify_certificates_and_hostnames(self):
        agent = object.__new__(DirectGameAgent)
        agent.config = replace(PlayerConfig.from_dict({
            "name": "Minimal", "backend": "minimal", "model": "test",
            "base_url": "https://example.test/v1",
        }, 0), api_key="test-key")
        agent._messages = []
        agent.timeout = 10
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b""
        with mock.patch("urllib.request.urlopen", return_value=response) as request:
            agent._call_llm()
        context = request.call_args.kwargs["context"]
        self.assertEqual(ssl.CERT_REQUIRED, context.verify_mode)
        self.assertTrue(context.check_hostname)

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

    def test_ark_nova_journal_summary_uses_ark_nova_progress(self):
        agent = object.__new__(DirectGameAgent)
        agent.game_id = "ark_nova"
        agent.seat = 0
        before = {
            "state_version": 20,
            "turn_count": 4,
            "phase": "action",
            "break_track": {"count": 0, "position": 2},
            "players": [{
                "seat": 0, "money": 20, "x_tokens": 1,
                "tracks": {"appeal": 3, "conservation": 0, "reputation": 1},
                "score": 3, "hand": [{"id": "zoo-1"}],
                "played_cards": [], "supported_projects": [],
                "map": {"buildings": []},
            }, {
                "seat": 1, "money": 18, "x_tokens": 0,
                "tracks": {"appeal": 4, "conservation": 0, "reputation": 1},
                "score": 4, "hand_count": 2,
                "played_cards": [], "supported_projects": [],
                "map": {"buildings": []},
            }],
        }
        after = {
            **before,
            "state_version": 24,
            "turn_count": 5,
            "break_track": {"count": 0, "position": 2},
            "players": [{
                **before["players"][0],
                "money": 14,
                "tracks": {"appeal": 8, "conservation": 0, "reputation": 1},
                "hand": [],
                "played_cards": [{"id": "zoo-1"}],
                "map": {"buildings": [{"id": "building-1"}]},
            }, before["players"][1]],
        }
        agent.profile = None
        agent._journal = [
            agent._journal_entry(20, {
                "type": "start_action", "action_card_id": "animals",
                "x_by_execution": [0], "multiplier_tokens": 0,
            }, before, before),
            agent._journal_entry(24, {
                "type": "play_selected_animal", "building_id": "building-1",
            }, after, after),
        ]

        summary = agent._journal_summary(last_n=50)

        self.assertIn("Ark Nova decision steps digest", summary)
        self.assertIn("Appeal 3→8", summary)
        self.assertIn("played 1", summary)
        self.assertIn("animals 1", summary)
        self.assertIn("animals housed 1", summary)
        self.assertNotIn("0 builds, 0 takes, 0 blocks", summary)

    def test_legacy_splendor_digest_is_replaced_for_ark_nova(self):
        agent = object.__new__(DirectGameAgent)
        agent.game_id = "ark_nova"
        agent.seat = 0
        agent._journal = []
        agent._messages = [{
            "role": "system",
            "content": (
                "=== Last 50 turns digest ===\n"
                "Actions: 0 builds, 0 takes, 0 blocks\n"
                "Engine: 0 cards, bonuses={}"
            ),
        }]
        observation = {
            "state_version": 42,
            "turn_count": 8,
            "phase": "action",
            "break_track": {"count": 1, "position": 7},
            "players": [{
                "seat": 0, "money": 12, "x_tokens": 2,
                "tracks": {"appeal": 14, "conservation": 3, "reputation": 5},
                "hand": [{"id": "zoo-1"}, {"id": "zoo-2"}],
                "played_cards": [{"id": "zoo-3"}, {"id": "zoo-4"}],
                "supported_projects": ["project-1"],
                "map": {"buildings": [{"id": "building-1"}]},
            }],
        }

        agent._prepare_ark_nova_session(observation, 42)

        digest = agent._messages[0]["content"]
        self.assertIn("Legacy non-Ark counters were removed", digest)
        self.assertIn("hand 2, played 2, projects 1, buildings 1", digest)
        self.assertNotIn("0 builds", digest)
        self.assertNotIn("0 cards", digest)
        self.assertEqual(1, len(agent._journal))

    def test_session_persists_structured_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            config = PlayerConfig.from_dict({
                "name": "Minimal", "backend": "minimal", "model": "test",
                "base_url": "https://example.test/v1",
            }, 0)
            first = DirectGameAgent(config, "match", 0, runs_root=directory)
            first._journal = [{"turn": 3, "action_type": "start_action"}]
            first._save_session()

            resumed = DirectGameAgent(config, "match", 0, runs_root=directory)

            self.assertEqual(first._journal, resumed._journal)


if __name__ == "__main__":
    unittest.main()
