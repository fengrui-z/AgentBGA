import random
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from agentbga.agents import PlayerConfig
from agentbga.baselines.config import normalize_params
from agentbga.baselines.sampling import sample_state, SUPPORTED_RULES
from agentbga.registry import get_game, list_games
from agentbga.store import Store


class BaselineCommonTests(unittest.TestCase):
    def test_configuration_and_persistence(self):
        for backend in ('greedy','heuristic','ismcts'):
            config=PlayerConfig.from_dict({'name':backend,'backend':backend,'algorithm_params':{'seed':17,'max_candidates':8}},0)
            with tempfile.TemporaryDirectory() as directory:
                store=Store(Path(directory)/'test.sqlite3')
                match,_,_=store.create(2,42)
                store.set_players(match,[config.public_dict()])
                self.assertEqual(config.algorithm_params,store.players(match)[0]['algorithm_params'])
                store.close()
        for bad in ({'unknown':1},{'max_steps':0},{'iterations':True},{'time_limit_ms':-1},{'max_steps':1.5},{'exploration':float('nan')}):
            with self.assertRaises(ValueError):normalize_params('ismcts',bad)
        with self.assertRaises(ValueError):normalize_params('greedy',{'iterations':1})

    def test_every_default_game_has_a_sampler(self):
        self.assertEqual(set(SUPPORTED_RULES),{d['id'] for d in list_games()})
        for description in list_games():
            game=get_game(description['id'])
            state=game.setup(max(2,description['players']['minimum']),42)
            for _ in range(30):
                if state['status']!='active':break
                seats=game.decision_seats(state)
                choices={}
                for seat in seats:
                    with self.subTest(game=game.game_id,phase=state['phase'],seat=seat):
                        before=deepcopy(state)
                        sample=sample_state(game,state,seat,random.Random(123))
                        game.validate_state(sample)
                        self.assertEqual(before,state)
                        self.assertEqual(game.observe(state,seat),game.observe(sample,seat))
                        self.assertEqual(game.legal_actions(state,seat),game.legal_actions(sample,seat))
                        choices[seat]=random.Random(43+state.get('decision_count',state['turn_count'])).choice(game.legal_actions(state,seat))['action']
                for seat in seats:state,_=game.apply_action(state,seat,choices[seat])

    def test_hidden_order_and_real_seed_do_not_change_samples(self):
        for name in SUPPORTED_RULES:
            game=get_game(name);description=game.describe()
            state=game.setup(max(2,description['players']['minimum']),42)
            seat=game.decision_seats(state)[0]
            changed=deepcopy(state);changed['seed']=99999
            for key in ('deck','bag','zoo_deck','draw_deck','merchant_deck','point_deck'):
                if key in changed:changed[key].reverse()
            if 'decks' in changed:
                for deck in changed['decks'].values():deck.reverse()
            with self.subTest(game=name):
                self.assertEqual(sample_state(game,state,seat,random.Random(9)),sample_state(game,changed,seat,random.Random(9)))
