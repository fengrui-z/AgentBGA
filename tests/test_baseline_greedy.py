import unittest
from agentbga.registry import get_game
from agentbga.baselines.greedy import Agent
from agentbga.baselines.config import normalize_params


class GreedyTests(unittest.TestCase):
    def test_deterministic_legal_choice_and_candidate_limit(self):
        game = get_game("splendor")
        state = game.setup(2, 42)
        params = normalize_params("greedy", {"max_candidates": 8})
        agent = Agent(game, 0, params)
        agent.bind(state, 0)
        legal = game.legal_actions(state, 0)
        obs = game.observe(state, 0)
        first, metadata = agent.choose(obs, legal)
        self.assertIn(first, {x["id"] for x in legal})
        self.assertEqual(first, agent.choose(obs, legal)[0])
        self.assertEqual(8, metadata["evaluated_candidates"])
        self.assertEqual(8, metadata["simulation_steps"])

    def test_scores_purchase_above_reserving_with_full_bank(self):
        game = get_game("splendor")
        state = game.setup(2, 42)
        # Four black tokens can buy a one-point blue card in this fixture.
        card = next(
            c
            for c in __import__("agentbga.splendor", fromlist=["CARDS"]).CARDS.values()
            if c["tier"] == 1 and c["points"] == 1 and c["cost"]["black"] == 4
        )
        old = state["market"]["1"][0]
        state["decks"]["1"].remove(card["id"])
        state["decks"]["1"].append(old)
        state["market"]["1"][0] = card["id"]
        state["players"][0]["tokens"]["black"] = 4
        state["bank"]["black"] = 0
        game.validate_state(state)
        agent = Agent(game, 0, normalize_params("greedy", {"max_candidates": 0}))
        agent.bind(state, 0)
        legal = game.legal_actions(state, 0)
        action_id, _ = agent.choose(game.observe(state, 0), legal)
        selected = next(x["action"] for x in legal if x["id"] == action_id)
        self.assertEqual("buy_visible", selected["type"])
