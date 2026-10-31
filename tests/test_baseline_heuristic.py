import unittest
from agentbga.registry import get_game
from agentbga.baselines.heuristic import Agent
from agentbga.baselines.config import normalize_params
from agentbga.baselines.evaluation import value


class HeuristicTests(unittest.TestCase):
    def test_position_weight_changes_the_evaluation(self):
        game=get_game('splendor');state=game.setup(2,42)
        self.assertNotEqual(value(game,state,0,0),value(game,state,0,1))
        agent=Agent(game,0,normalize_params('heuristic',{'max_candidates':0}))
        agent.bind(state,0);legal=game.legal_actions(state,0)
        action,meta=agent.choose(game.observe(state,0),legal)
        self.assertIn(action,{a['id'] for a in legal})
        self.assertEqual(len(legal),meta['evaluated_candidates'])
        self.assertEqual(action,agent.choose(game.observe(state,0),legal)[0])
