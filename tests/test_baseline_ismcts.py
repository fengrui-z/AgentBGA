import unittest
from unittest.mock import patch
from agentbga.registry import get_game
from agentbga.baselines.ismcts import Agent
from agentbga.baselines.config import normalize_params


class ISMCTSTests(unittest.TestCase):
    def test_iterations_depth_tree_and_determinism(self):
        game = get_game("splendor")
        state = game.setup(2, 42)
        params = normalize_params(
            "ismcts",
            {"time_limit_ms": 0, "iterations": 20, "max_steps": 6, "max_candidates": 2},
        )
        agent = Agent(game, 0, params)
        agent.bind(state, 0)
        legal = game.legal_actions(state, 0)
        action, meta = agent.choose(game.observe(state, 0), legal)
        self.assertIn(action, {x["id"] for x in legal})
        self.assertEqual(20, meta["iterations"])
        self.assertEqual(20, meta["root_visits"])
        self.assertLessEqual(meta["simulation_steps"], 120)
        self.assertGreater(meta["nodes"], 1)
        self.assertEqual(action, agent.choose(game.observe(state, 0), legal)[0])

    def test_expired_budget_returns_legal_action_without_simulating(self):
        game = get_game("splendor")
        state = game.setup(2, 42)
        agent = Agent(game, 0, normalize_params("ismcts"))
        agent.bind(state, 0)
        legal = game.legal_actions(state, 0)
        with patch("agentbga.baselines.runtime.Budget.expired", return_value=True):
            action, meta = agent.choose(game.observe(state, 0), legal)
        self.assertIn(action, {x["id"] for x in legal})
        self.assertEqual(0, meta["iterations"])
        self.assertEqual(0, meta["simulation_steps"])

    def test_simultaneous_search_respects_complete_groups(self):
        game = get_game("seven_wonders")
        state = game.setup(3, 42)
        params = normalize_params(
            "ismcts",
            {"time_limit_ms": 0, "iterations": 5, "max_steps": 7, "max_candidates": 2},
        )
        agent = Agent(game, 0, params)
        agent.bind(state, 0)
        action, meta = agent.choose(
            game.observe(state, 0), game.legal_actions(state, 0)
        )
        self.assertEqual(5, meta["root_visits"])
        self.assertEqual(30, meta["simulation_steps"])
        self.assertEqual({}, state["pending_choices"])
