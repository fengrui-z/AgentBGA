from copy import deepcopy
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

from agentbga import harmonies as h
from agentbga.agents import PlayerConfig
from agentbga.runner import run_match
from agentbga.store import Store


def player_with(placements):
    p = h.new_game(1, 1)['players'][0]
    for cell, stack in placements.items():
        p['board'][cell] = stack
    return p


def stage(state, seat=0, placements=None, cards=()):
    """Construct a scenario while retaining the real catalog/token inventory."""
    p = state['players'][seat]
    for cell, stack in (placements or {}).items():
        state['bag'].extend(p['board'][cell])
        p['board'][cell] = list(stack)
        for color in stack:
            if color not in state['bag']:
                # Move an unused market token into the bag, replacing from it.
                group = next(g for g in state['token_groups'] if color in g)
                group.remove(color)
                group.append(state['bag'].pop())
                state['bag'].append(color)
            state['bag'].remove(color)
    for key in cards:
        for zone in ('deck', 'market', 'spirit_deck', 'discarded_cards'):
            if key in state[zone]:
                state[zone].remove(key)
                break
        p['cards'].append({'id': key, 'placed': 0})
    h._update_scores(state)
    h.validate_state(state)
    return state


class HarmoniesTests(unittest.TestCase):
    def test_setup_catalog_and_hidden_information(self):
        self.assertEqual(23, len(h.CELLS))
        self.assertEqual(32, sum(not c['spirit'] for c in h.CARDS.values()))
        self.assertEqual(10, sum(c['spirit'] for c in h.CARDS.values()))
        for n in range(1, 5):
            s = h.new_game(n, 42, {'nature_spirits': True})
            self.assertEqual(s, h.new_game(n, 42, {'nature_spirits': True}))
            self.assertEqual(3 if n == 1 else 5, len(s['market']))
            v = h.observe(s, 0)
            for key in ('bag', 'deck', 'spirit_deck', 'discarded_cards', 'seed'):
                self.assertNotIn(key, v)
            for p in v['players']:
                self.assertEqual(2 if p['seat'] == 0 else 0, len(p['spirit_choices']))
            v['players'][0]['cells'][0]['stack'].append('red')
            self.assertEqual([], s['players'][0]['board'][0])
        for args in [(0, 1, None), (5, 1, None), (True, 1, None), (2, 1, {'board_side': 'C'}),
                     (2, 1, {'nature_spirits': 'yes'}), (2, 1, {'expansion': True})]:
            with self.assertRaises(h.RuleError):
                h.new_game(*args)

    def test_exact_stacking_and_animal_lock(self):
        allowed = {
            (): set(h.COLORS), ('gray',): {'gray', 'red'}, ('gray', 'gray'): {'gray'},
            ('gray', 'gray', 'gray'): set(), ('brown',): {'brown', 'green', 'red'},
            ('brown', 'brown'): {'green'}, ('red',): {'red'}, ('brown', 'red'): set(),
            ('red', 'red'): set(), ('gray', 'red'): set(), ('green',): set(),
            ('yellow',): set(), ('blue',): set(), ('brown', 'green'): set(),
            ('brown', 'brown', 'green'): set(),
        }
        for stack, expected in allowed.items():
            self.assertEqual(expected, {c for c in h.COLORS if h.can_stack(list(stack), c)}, stack)
            self.assertFalse(any(h.can_stack(list(stack), c, 'h01') for c in h.COLORS))

    def test_building_habitat_requires_two_tokens_and_accepts_all_bases(self):
        for base in ('red', 'brown', 'gray'):
            self.assertTrue(h._matches([base, 'red'], ['base', 'red']))
        self.assertFalse(h._matches(['red'], ['base', 'red']))
        self.assertFalse(h._matches(['gray', 'gray', 'red'], ['base', 'red']))

    def test_all_42_cards_match_every_in_bounds_rotation_and_exact_height(self):
        for key, card in h.CARDS.items():
            candidates = h.pattern_placements(key)
            self.assertTrue(candidates, key)
            # Independent coordinate transforms, not the engine's rotation helper.
            for rotation in range(6):
                transformed = []
                for step in card['pattern']:
                    q, r = step['q'], step['r']
                    transformed.append(((q, r), (-r, q+r), (-q-r, q), (-q, -r), (r, -q-r), (q+r, -q))[rotation])
                for oq, or_ in h.CELLS:
                    coords = [(oq+q, or_+r) for q, r in transformed]
                    if all(c in h.CELL_INDEX for c in coords):
                        break
                else:
                    self.fail(f'{key} rotation {rotation} has no placement')
                cells = [h.CELL_INDEX[c] for c in coords]
                stacks = {i: ['gray' if x == 'base' else x for x in s['stack']] for i, s in zip(cells, card['pattern'])}
                p = player_with(stacks)
                target = cells[next(i for i, s in enumerate(card['pattern']) if s['animal'])]
                self.assertIn(target, h.animal_targets(p, key), (key, rotation))
                p['cubes'][target] = key
                self.assertNotIn(target, h.animal_targets(p, key))
                p['cubes'][target] = None
                p['board'][target] = []
                self.assertNotIn(target, h.animal_targets(p, key))

    def test_chiral_pattern_is_not_reflected(self):
        # Base cards are reflection-symmetric; a synthetic chiral probe verifies
        # that the matcher itself does not silently introduce a mirror transform.
        card = {'pattern': [
            {'q':0,'r':0,'stack':['yellow'],'animal':False},
            {'q':1,'r':0,'stack':['blue'],'animal':True},
            {'q':1,'r':1,'stack':['gray'],'animal':False},
        ]}
        cells = [h.CELL_INDEX[c] for c in [(1,0),(1,1),(2,1)]]
        p = player_with({i:s['stack'][:] for i,s in zip(cells,card['pattern'])})
        with mock.patch.dict(h.CARDS, {'probe':card}):
            self.assertNotIn(cells[1], h.animal_targets(p,'probe'))
        h.pattern_placements.cache_clear()

    def test_interleaved_settlement_shared_support_and_later_height_change(self):
        # Fennec: field / mountain / marked mountain, in a straight chain.
        s = h.new_game(2, 8)
        target, cells = h.pattern_placements('h23')[0]
        s = stage(s, placements={cells[0]: ['yellow'], cells[1]: ['gray'], target: ['gray']}, cards=['h23', 'h26'])
        # One market group is made gray/green/blue while conserving inventory.
        s['bag'].extend(s['token_groups'][0]); s['token_groups'][0] = ['gray', 'green', 'blue']
        for c in s['token_groups'][0]: s['bag'].remove(c)
        s, _ = h.apply_action(s, 0, {'type': 'take_tokens', 'group': 0})
        before = deepcopy(s)
        s, _ = h.apply_action(s, 0, {'type': 'place_animal', 'card_id': 'h23', 'cell': target})
        self.assertEqual(3, len(s['pending_tokens']))
        self.assertEqual(4, s['players'][0]['score'] - before['players'][0]['score'])
        # Other habitats may share the field while its neighboring mountain holds a cube.
        self.assertIn(cells[1], h.animal_targets(s['players'][0], 'h26'))
        # Modify an unlocked support: previously settled Fennec persists.
        s, _ = h.apply_action(s, 0, {'type': 'place_token', 'color': 'gray', 'cell': cells[1]})
        self.assertEqual('h23', s['players'][0]['cubes'][target])
        self.assertEqual(4, h.score_breakdown(s['players'][0], 'A')['animals'])
        h.validate_state(s)

    def test_actions_reject_wrong_seat_payload_and_early_end_without_mutation(self):
        s = h.new_game(2, 22)
        original = deepcopy(s)
        for seat, action in [(1, {'type':'take_tokens','group':0}), (0, {'type':'end_turn'}),
                             (0, {'type':'take_tokens','group':True}), (0, {'type':'take_tokens','group':0,'extra':1})]:
            with self.assertRaises(h.RuleError): h.apply_action(s, seat, action)
            self.assertEqual(original, s)
        actions = h.legal_actions(s, 0)
        s, _ = h.apply_action(s, 0, {'type':'take_tokens','group':0})
        self.assertFalse(any(a['action']['type'] in ('take_tokens','end_turn') for a in h.legal_actions(s,0)))
        self.assertTrue(set(a['id'] for a in actions).isdisjoint(a['id'] for a in h.legal_actions(s,0)))

    def test_once_per_turn_card_draft_and_completed_card_frees_slot(self):
        s = stage(h.new_game(2, 3), cards=['h01','h02','h03','h04'])
        self.assertFalse(any(a['action']['type']=='take_animal' for a in h.legal_actions(s,0)))
        p=s['players'][0]
        # Legal-action capacity depends on completion, not total owned cards.
        p['cards'][0]['placed']=3
        self.assertTrue(any(a['action']['type']=='take_animal' for a in h.legal_actions(s,0)))
        s=h.new_game(2,3)
        key=s['market'][0]
        s,_=h.apply_action(s,0,{'type':'take_animal','card_id':key})
        self.assertEqual(4,len(s['market']))
        self.assertFalse(any(a['action']['type']=='take_animal' for a in h.legal_actions(s,0)))

    def test_landscape_scores(self):
        # Independent isolated tree heights, including bare trunks.
        p=player_with({0:['green'], 5:['brown','green'], 10:['brown','brown','green'], 20:['brown','brown']})
        self.assertEqual(11,h.score_breakdown(p,'A')['trees'])
        p=player_with({0:['gray'], 1:['gray','gray'], 22:['gray','gray','gray']})
        self.assertEqual(4,h.score_breakdown(p,'A')['mountains'])
        p=player_with({0:['yellow'],1:['yellow'],2:['yellow'],3:['yellow'],21:['yellow'],22:['yellow'],10:['yellow']})
        self.assertEqual(10,h.score_breakdown(p,'A')['fields'])
        center=h.CELL_INDEX[(2,1)]; neighbors=h.NEIGHBORS[center]
        p=player_with({center:['gray','red'],neighbors[0]:['blue'],neighbors[1]:['green'],neighbors[2]:['yellow']})
        self.assertEqual(5,h.score_breakdown(p,'A')['buildings'])
        p['board'][neighbors[2]]=['blue']
        self.assertEqual(0,h.score_breakdown(p,'A')['buildings'])
        p['board'][neighbors[2]]=['red']
        self.assertEqual(5,h.score_breakdown(p,'A')['buildings'])
        p['board'][center]=['red']
        self.assertEqual(0,h.score_breakdown(p,'A')['buildings'])

    def test_river_uses_shortest_paths_not_longest_simple_path(self):
        # Six-token ring: farthest shortest route is 4 tokens, not all 6.
        center=h.CELL_INDEX[(2,1)]
        p=player_with({i:['blue'] for i in h.NEIGHBORS[center]})
        self.assertEqual(8,h.score_breakdown(p,'A')['water'])
        # Ring cuts an empty island out of the mainland.
        self.assertEqual(10,h.score_breakdown(p,'B')['water'])
        self.assertEqual(5,h.score_breakdown(player_with({}),'B')['water'])
        self.assertEqual(0,h.score_breakdown(player_with({0:['blue']}),'A')['water'])
        # Winding 7-token route without shortcuts, verified by coordinates.
        route=[(0,0),(0,1),(0,2),(0,3),(1,3),(2,2),(2,1)]
        p=player_with({h.CELL_INDEX[c]:['blue'] for c in route})
        self.assertEqual(19,h.score_breakdown(p,'A')['water'])

    def test_animals_use_cumulative_uncovered_value(self):
        p=player_with({});p['cards']=[{'id':'h23','placed':2},{'id':'h01','placed':0}]
        self.assertEqual(9,h.score_breakdown(p,'A')['animals'])
        p['cards'][0]['placed']=3
        self.assertEqual(16,h.score_breakdown(p,'A')['animals'])

    def test_spirits_score_only_after_placement(self):
        fixtures={
            'h33':({0:['yellow'],1:['yellow'],2:['yellow'],22:['yellow']},12),
            'h34':({0:['yellow'],1:['yellow'],22:['yellow']},10),
            'h35':({0:['green'],1:['brown','green'],2:['brown','brown','green']},8),
            'h36':({0:['green'],1:['brown','green'],2:['brown','brown','green']},7),
            'h37':({0:['red','red'],1:['brown','red'],22:['gray','red'],10:['red']},8),
            'h38':({0:['red','red'],1:['brown','red'],22:['gray','red']},6),
            'h39':({0:['gray'],1:['gray','gray'],22:['gray','gray','gray']},8),
            'h40':({0:['gray'],1:['gray','gray'],22:['gray','gray','gray']},7),
            'h41':({0:['blue'],1:['blue'],22:['blue']},7),
            'h42':({0:['blue'],1:['blue'],22:['blue']},6),
        }
        for key,(stacks,score) in fixtures.items():
            p=player_with(stacks);p['cards']=[{'id':key,'placed':0}]
            self.assertEqual(0,h.score_breakdown(p,'A')['spirits'])
            p['cards'][0]['placed']=1
            self.assertEqual(score,h.score_breakdown(p,'A')['spirits'],key)

    def test_solo_refills_all_groups_and_can_replace_card_only_without_draft(self):
        s=h.new_game(1,8);old_market=s['market'][:]
        s,_=h.apply_action(s,0,{'type':'take_tokens','group':1})
        for i,c in enumerate(s['pending_tokens'][:]):
            s,_=h.apply_action(s,0,{'type':'place_token','color':c,'cell':i})
        self.assertEqual(4,sum(a['action']['type']=='end_turn' for a in h.legal_actions(s,0)))
        s,_=h.apply_action(s,0,{'type':'end_turn','discard_card':old_market[0]})
        self.assertEqual(6,len(s['discarded_tokens']))
        self.assertEqual(102,len(s['bag']))
        self.assertEqual([3,3,3],list(map(len,s['token_groups'])))
        self.assertNotIn(old_market[0],s['market'])
        self.assertEqual(3,len(s['market']))

    def test_board_end_trigger_waits_for_end_turn_and_equal_round(self):
        s=h.new_game(2,19)
        # 20 occupied cells, leaving exactly three places for the mandatory draft.
        colors=['brown']*10+['gray']*10
        s=stage(s,placements={i:[c] for i,c in enumerate(colors)})
        s,_=h.apply_action(s,0,{'type':'take_tokens','group':0})
        for i,c in enumerate(s['pending_tokens'][:]):
            s,_=h.apply_action(s,0,{'type':'place_token','color':c,'cell':20+i})
        self.assertIsNone(s['final_round'])
        s,_=h.apply_action(s,0,{'type':'end_turn'})
        self.assertEqual('active',s['status']);self.assertEqual(1,s['final_round'])
        s,_=h.apply_action(s,1,{'type':'take_tokens','group':0})
        for i,c in enumerate(s['pending_tokens'][:]):
            s,_=h.apply_action(s,1,{'type':'place_token','color':c,'cell':i})
        s,_=h.apply_action(s,1,{'type':'end_turn'})
        self.assertEqual('finished',s['status']);self.assertEqual([1,1],[p['turns'] for p in s['players']])
        self.assertEqual([],h.legal_actions(s,0))

    def test_bag_exhaustion_still_gives_remaining_players_a_turn(self):
        s=h.new_game(4,9)
        s['discarded_tokens'].extend(s['bag']);s['bag']=[]
        for seat in range(4):
            s,_=h.apply_action(s,seat,{'type':'take_tokens','group':seat})
            for i,c in enumerate(s['pending_tokens'][:]):
                s,_=h.apply_action(s,seat,{'type':'place_token','color':c,'cell':i})
            s,_=h.apply_action(s,seat,{'type':'end_turn'})
            self.assertEqual('finished' if seat==3 else 'active',s['status'])
        self.assertEqual('bag_empty',s['end_reason'])

    def test_solo_suns_include_board_and_spirit_adjustment(self):
        s=h.new_game(1,1)
        s['players'][0]['score']=130
        self.assertEqual(8,h.solo_suns(s))
        s['nature_spirits']=True
        s['players'][0]['cards']=[{'id':'h33','placed':1}]
        self.assertEqual(7,h.solo_suns(s))
        s['players'][0]['cards']=[{'id':'h39','placed':1}]
        s['board_side']='B'
        self.assertEqual(5,h.solo_suns(s))
        self.assertIsNone(h.solo_suns(h.new_game(2,1)))

    def test_ties_exclude_spirit_cubes(self):
        s=h.new_game(3,2)
        s['players'][0]['cubes'][0]='h33'
        s['players'][1]['cubes'][0]='h01'
        s['players'][2]['cubes'][0]='h02'
        ranks=h.rankings(s)
        self.assertEqual([1,2,0],[r['seat'] for r in ranks])
        self.assertEqual([1,1,3],[r['rank'] for r in ranks])

    def test_validator_detects_corruption(self):
        for mutate in [lambda s:s['bag'].pop(),lambda s:s['deck'].append(s['deck'][0]),
                       lambda s:s['players'][0].update(score=999),lambda s:s['players'][0]['board'][0].extend(['green','red'])]:
            s=h.new_game(2,8);mutate(s)
            with self.assertRaises(AssertionError):h.validate_state(s)

    def test_random_games_finish_and_json_replay_exactly(self):
        for n in range(1,5):
            for side in ('A','B'):
                for spirits in (False,True):
                    s=h.new_game(n,21,{'board_side':side,'nature_spirits':spirits})
                    rng=random.Random(7)
                    while s['status']=='active':
                        self.assertLess(s['turn_count'],1000)
                        legal=h.legal_actions(s,s['active_seat']);self.assertTrue(legal)
                        self.assertEqual(len(legal),len({a['id'] for a in legal}))
                        a=rng.choice(legal)['action']
                        again,e2=h.apply_action(json.loads(json.dumps(s)),s['active_seat'],a)
                        s,e1=h.apply_action(s,s['active_seat'],a)
                        self.assertEqual(h.state_hash(s),h.state_hash(again));self.assertEqual(e1,e2)
                    self.assertEqual(1,len({p['turns'] for p in s['players']}))

    def test_store_runner_reopen_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'harmonies.sqlite3'
            store=Store(db)
            match_id,_,_=store.create(2,17,'harmonies',{'board_side':'B','nature_spirits':True})
            configs=[PlayerConfig.from_dict({'name':f'Random {i}','backend':'random'},i) for i in range(2)]
            result=run_match(store,match_id,configs,max_turns=1000)
            self.assertEqual('finished',store.load(match_id)[1]['status'])
            self.assertEqual('harmonies',result['game'])
            replay=store.replay(match_id)
            self.assertGreater(len(replay),30)
            final_hash=replay[-1]['state_hash'];store.close()
            store=Store(db)
            self.assertEqual(final_hash,store.replay(match_id)[-1]['state_hash'])
            store.close()


if __name__=='__main__':unittest.main()
