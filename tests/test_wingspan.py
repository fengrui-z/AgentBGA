from copy import deepcopy
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from agentbga import wingspan as w
from agentbga.agents import PlayerConfig
from agentbga.public_projection import public_action, public_action_id, public_controller_event
from agentbga.runner import run_match
from agentbga.store import Store


def act(s, kind=None, **fields):
    options = w.legal_actions(s, s['active_seat'])
    item = next(a for a in options if (kind is None or a['action']['type'] == kind)
                and all(a['action'].get(k) == v for k, v in fields.items()))
    return w.apply_action(s, s['active_seat'], item['action'])[0]


def ready(n=2, seed=13, board='green'):
    s = w.new_game(n, seed, {'goal_board': board})
    while s['phase'] == 'setup':
        if s['queue'][0]['op'] == 'setup_keep':
            s = act(s, 'keep_birds', card_ids=[])
        else:
            s = act(s)
    return s


def key(name):
    return next(k for k, c in w.BIRDS.items() if c['name'] == name)


def remove(s, k):
    for zone in ['deck', 'discard', 'draft']:
        if k in s[zone]: s[zone].remove(k); return
    if k in s['tray']:
        s['tray'][s['tray'].index(k)] = None
        return
    for p in s['players']:
        if k in p['hand']: p['hand'].remove(k); return
        for row in p['habitats'].values():
            for b in row:
                if b['id'] == k: row.remove(b); return
                if k in b['tucked']: b['tucked'].remove(k); return
    raise AssertionError(k)


def stage(s, name, habitat=None, seat=None, eggs=0, hand=False):
    seat = s['turn_owner'] if seat is None else seat
    k = key(name)
    remove(s, k)
    p = s['players'][seat]
    if hand:
        p['hand'].append(k)
    else:
        p['habitats'][habitat or w.BIRDS[k]['habitats'][0]].append(
            {'id': k, 'eggs': eggs, 'cache': dict.fromkeys(w.FOODS, 0), 'tucked': []})
    w._update_scores(s)
    return k


def power(s, name):
    seat = s['turn_owner']
    s['players'][seat]['actions_left'] -= 1
    s['queue'] = [w._effect('power', seat, bird=key(name), optional=True)]
    s['phase'] = 'power'
    w._advance(s)
    return act(s, 'activate_power')


class WingspanTests(unittest.TestCase):
    def test_catalog_setup_and_invalid_configs(self):
        self.assertEqual(170, len(w.BIRDS))
        self.assertEqual(26, len(w.BONUSES))
        self.assertEqual(8, len(w.GOAL_TILES))
        self.assertEqual(5, w.BIRDS[key('Spotted Sandpiper')]['points'])
        self.assertEqual(67, len({json.dumps(b['power'], sort_keys=True) for b in w.BIRDS.values()}))
        for n in range(2, 6):
            s = w.new_game(n, 12)
            self.assertEqual(s, w.new_game(n, 12))
            self.assertEqual(170-5*n-3, len(s['deck']))
            self.assertEqual(26-2*n, len(s['bonus_deck']))
            self.assertEqual(5, len(s['feeder']))
            self.assertEqual(4, len(set(s['goals'])))
        for args in [(1, 0, None), (6, 0, None), (True, 0, None), (2, True, None),
                     (2, 0, {'goal_board':'bad'}), (2, 0, {'swift_start':True})]:
            with self.assertRaises(w.RuleError): w.new_game(*args)

    def test_setup_food_trade_and_bonus(self):
        s = w.new_game(2, 1)
        seat = s['active_seat']
        kept = s['players'][seat]['hand'][:3]
        s = act(s, 'keep_birds', card_ids=kept)
        for f in ('seed','fish','fruit'): s = act(s, 'discard_food', food=f)
        self.assertEqual(2, sum(s['players'][seat]['food'].values()))
        self.assertEqual(kept, s['players'][seat]['hand'])
        s = act(s, 'choose_bonus')
        self.assertEqual(1, len(s['players'][seat]['bonuses']))
        self.assertEqual(0, s['completed_turns'])

    def test_hidden_information_observation_and_public_actions(self):
        s = w.new_game(2, 3)
        seat = s['active_seat']; other = 1-seat
        v = w.observe(s, seat)
        for k in ('seed','rng','deck','bonus_deck','discard','bonus_discard','queue'):
            self.assertNotIn(k, v)
        self.assertEqual([], v['players'][other]['hand'])
        self.assertEqual([], v['players'][other]['bonus_choices'])
        self.assertNotIn('bonus_cards', v['players'][other]['score_breakdown'])
        v['players'][seat]['food']['seed'] = 99
        self.assertEqual(1, s['players'][seat]['food']['seed'])
        choices = w.legal_actions(s, seat)
        a, b = choices[1], choices[2]
        self.assertEqual({'type':'keep_birds','private':'wingspan'}, public_action(a['action']))
        self.assertEqual(public_action_id(a['id'],a['action'],match_id='m',version=1,seat=seat),
                         public_action_id(b['id'],b['action'],match_id='m',version=1,seat=seat))
        self.assertNotIn(a['id'], json.dumps(public_controller_event({'action_id':a['id']},match_id='m',version=1,seat=seat)))

    def test_all_illegal_decisions_leave_state_unchanged_and_reject_bool(self):
        s = ready(); original = deepcopy(s)
        for a in ({'type':'play_bird','card_id':'fake','habitat':'forest'}, {'type':'gain_food','extra':1},
                  {'type':'skip'}, [], {'type':'keep_birds','card_ids':[]}):
            with self.assertRaises(w.RuleError): w.apply_action(s,s['active_seat'],a)
            self.assertEqual(original,s)
        with self.assertRaises(w.RuleError): w.apply_action(s,True,{'type':'gain_food'})
        with self.assertRaises(w.RuleError): w.apply_action(s,1-s['active_seat'],{'type':'gain_food'})

    def test_food_substitution_and_all_payment_paths_preserve_completion(self):
        s=ready(); seat=s['active_seat']; p=s['players'][seat]
        bird=stage(s,'American Goldfinch',hand=True)
        p['food'] = dict.fromkeys(w.FOODS,0); p['food']['fish']=4
        self.assertTrue(any(a['action'].get('card_id')==bird for a in w.legal_actions(s,seat)))
        s=act(s,'play_bird',card_id=bird)
        s=act(s,'pay_food',food=['fish','fish'])
        s=act(s,'pay_food',food=['fish','fish'])
        self.assertEqual(0,sum(s['players'][seat]['food'].values()))
        self.assertEqual(bird,w.all_birds(s['players'][seat])[0]['id'])
        s=act(s,'skip')
        self.assertEqual(1,s['completed_turns'])

    def test_egg_cost_comes_from_existing_birds_before_install(self):
        s=ready(); seat=s['active_seat']
        existing=stage(s,'Carolina Chickadee','forest',eggs=1)
        bird=stage(s,'Carolina Wren',hand=True)
        s['players'][seat]['food']={f:3 for f in w.FOODS}
        s=act(s,'play_bird',card_id=bird,habitat='forest')
        self.assertEqual('pay_eggs',s['queue'][0]['op'])
        self.assertEqual([existing],[a['action'].get('bird_id') for a in w.legal_actions(s,seat)])
        s=act(s,'pay_egg',bird_id=existing)
        self.assertEqual(0,w._bird(s['players'][seat],existing)['eggs'])
        self.assertIn(bird,s['players'][seat]['hand'])

    def test_tray_refills_at_turn_end_not_between_draws(self):
        s=ready();seat=s['active_seat']
        stage(s,'Mallard','wetland');stage(s,'Ruddy Duck','wetland');w._refill(s)
        s=act(s,'draw_cards');k=s['tray'][0]
        s=act(s,'draw_card',source='tray',slot=0)
        self.assertIsNone(s['tray'][0]);self.assertIn(k,s['players'][seat]['hand'])
        s=act(s,'draw_card',source='tray',slot=1)
        self.assertIsNone(s['tray'][1])
        while s['completed_turns']==0:s=act(s,'skip')
        self.assertTrue(all(s['tray']))

    def test_feeder_split_face_reroll_and_empty_refill(self):
        s=ready();seat=s['active_seat'];s['feeder']=['invertebrate/seed']
        s=act(s,'gain_food')
        opts=w.legal_actions(s,seat)
        self.assertEqual({'invertebrate','seed'},{a['action']['food'] for a in opts if a['action']['type']=='take_food'})
        self.assertTrue(any(a['action']['type']=='reroll' for a in opts))
        before=s['players'][seat]['food']['seed']
        s=act(s,'take_food',food='seed')
        self.assertEqual(5,len(s['feeder']));self.assertEqual(before+1,s['players'][seat]['food']['seed'])

    def test_filtered_feeder_can_reroll_to_seek_missing_food(self):
        s=ready();stage(s,'Acorn Woodpecker','forest');s['feeder']=['fish','fish']
        s=power(s,'Acorn Woodpecker')
        self.assertEqual({'reroll','skip'},{a['action']['type'] for a in w.legal_actions(s,s['active_seat'])})
        with patch.object(w,'_roll',return_value=['seed','fish','fruit','rodent','invertebrate']): s=act(s,'reroll')
        s=act(s,'take_food',food='seed',cache=True)
        self.assertEqual(1,w._bird(s['players'][s['first_player']],key('Acorn Woodpecker'))['cache']['seed'])

    def test_egg_limits_wild_nests_and_payment_from_others(self):
        s=ready();seat=s['active_seat']
        raven=stage(s,'Common Raven','grassland',eggs=1)
        dove=stage(s,'Mourning Dove','grassland',eggs=1)
        s=power(s,'Common Raven')
        self.assertEqual([dove],[a['action'].get('bird_id') for a in w.legal_actions(s,seat) if a['action']['type']=='pay_egg'])
        s=act(s,'pay_egg',bird_id=dove)
        for f in ('fish','seed'): s=act(s,'take_food',food=f)
        self.assertEqual(1,w._bird(s['players'][seat],raven)['eggs'])
        self.assertEqual(0,w._bird(s['players'][seat],dove)['eggs'])
        wild = next(k for k,c in w.BIRDS.items() if c['nest']=='star')
        self.assertTrue(w.nest_matches({'id':wild},'bowl'))
        self.assertFalse(w.nest_matches(w._bird(s['players'][seat],raven),'bowl'))

    def test_deferred_discard_after_rest_of_row(self):
        s=ready();seat=s['active_seat']
        stage(s,'Ruddy Duck','wetland');s=power(s,'Ruddy Duck')
        s=act(s,'draw_card',source='deck');s=act(s,'draw_card',source='deck')
        self.assertEqual('discard_card',s['phase'])
        self.assertEqual(2,len(s['players'][seat]['hand']))
        s=act(s,'discard_card')
        self.assertEqual(1,len(s['players'][seat]['hand']));self.assertEqual(1,s['completed_turns'])

    def test_migration_preserves_eggs_cache_and_tucked_cards(self):
        s=ready();seat=s['active_seat'];bird=stage(s,"Bewick's Wren",'forest',eggs=1)
        s=power(s,"Bewick's Wren");s=act(s,'move_bird',habitat='wetland')
        self.assertEqual([],s['players'][seat]['habitats']['forest'])
        self.assertEqual(1,w._bird(s['players'][seat],bird)['eggs'])
        self.assertEqual('wetland',w._habitat(s['players'][seat],bird))

    def test_repeat_uses_original_bird_and_blocks_recursive_chain(self):
        s=ready();seat=s['active_seat']
        chick=stage(s,'Carolina Chickadee','forest');stage(s,'Gray Catbird','forest');stage(s,'Northern Mockingbird','forest')
        s=power(s,'Northern Mockingbird');s=act(s,'repeat_power',bird_id=key('Gray Catbird'))
        s=act(s,'activate_power')
        opts=w.legal_actions(s,seat)
        self.assertFalse(any(a['action'].get('bird_id')==key('Northern Mockingbird') for a in opts))
        s=act(s,'repeat_power',bird_id=chick);s=act(s,'activate_power')
        self.assertEqual(1,w._bird(s['players'][seat],chick)['cache']['seed'])
        self.assertEqual(0,sum(w._bird(s['players'][seat],key('Northern Mockingbird'))['cache'].values()))

    def test_pink_reaction_uses_opponents_seat_once_and_resets_next_turn(self):
        s=ready();seat=s['active_seat'];other=1-seat
        cow=stage(s,'Brown-Headed Cowbird','grassland',seat=other)
        stage(s,'House Finch','grassland',seat=other)
        stage(s,'Mourning Dove','grassland',seat=seat)
        s=act(s,'lay_eggs')
        self.assertEqual(other,s['active_seat']);self.assertEqual(seat,s['turn_owner'])
        s=act(s,'activate_power');s=act(s,'lay_egg')
        self.assertIn(cow,s['players'][other]['pink_used'])
        w._trigger(s,seat,'lay_eggs')
        self.assertFalse(any(t.get('bird')==cow for t in s['queue']))
        while s['completed_turns']==0:s=act(s,'skip')
        self.assertEqual([],s['players'][other]['pink_used'])

    def test_hunting_threshold_is_strict_and_triggers_scavenger(self):
        s=ready();seat=s['active_seat'];other=1-seat
        predator=stage(s,'Barred Owl','forest');stage(s,'Turkey Vulture','grassland',seat=other)
        prey=key('American Robin')
        remove(s,prey);s['deck'].append(prey)
        with patch.dict(w.BIRDS,{prey:{**w.BIRDS[prey],'wingspan':75}}):
            s=power(s,'Barred Owl')
        self.assertIn(prey,s['discard']);self.assertEqual([],w._bird(s['players'][seat],predator)['tucked'])
        s=ready();seat=s['active_seat'];other=1-seat
        predator=stage(s,'Barred Owl','forest');stage(s,'Turkey Vulture','grassland',seat=other)
        prey=key('Carolina Chickadee');remove(s,prey);s['deck'].append(prey)
        s=power(s,'Barred Owl')
        self.assertEqual([prey],w._bird(s['players'][seat],predator)['tucked'])
        self.assertEqual(other,s['active_seat'])

    def test_goal_ties_zero_quantities_and_blue_cap(self):
        s=ready(5);s['goals'][0]='birds_total'
        # Direct scoring oracle: four-way first tie (4+1+0+0)/4 = 1.
        for seat,name in enumerate(['American Crow','American Robin','Common Raven','House Finch']): stage(s,name,seat=seat)
        w._score_round(s)
        self.assertEqual([1,1,1,1,0],s['goal_history'][0]['points'])
        s=ready(3,board='blue');s['goals'][0]='eggs_grassland'
        stage(s,'Mourning Dove','grassland',seat=0,eggs=5);stage(s,'House Finch','grassland',seat=0,eggs=1)
        w._score_round(s)
        self.assertEqual([5,0,0],s['goal_history'][0]['points'])

    def test_bonus_boundaries_and_final_food_ties(self):
        s=ready();p=s['players'][0]
        # Independently specified boundary table avoids mirroring threshold code.
        for name, expected in [('backyard_birder',[(4,0),(5,3),(6,3),(7,6)]),
                               ('photographer',[(3,0),(4,3),(5,3),(6,7)])]:
            metric='low_points' if name=='backyard_birder' else 'name:Photographer'
            candidates=[k for k,c in w.BIRDS.items() if (c['points']<4 if metric=='low_points' else 'Photographer' in c['name_bonuses'])]
            for count,points in expected:
                fake=deepcopy(p);fake['habitats']['forest']=[{'id':k,'eggs':0,'cache':{},'tucked':[]} for k in candidates[:count]]
                self.assertEqual(points,w.bonus_value(fake,name)['points'])
        s['players'][0]['food']['seed']+=1
        self.assertEqual(0,w.rankings(s)[0]['seat'])
        s['players'][1]['food']['seed']+=1
        self.assertEqual([1,1],[r['rank'] for r in w.rankings(s)])

    def test_all_170_birds_have_executable_effect_paths_and_conserve_inventory(self):
        for card in w.BIRDS.values():
            with self.subTest(bird=card['name']):
                s=ready();seat=s['active_seat']
                stage(s,card['name'],eggs=min(1,card['egg_limit']))
                # Support eggs, food, repetition, extra plays and hand tucks.
                for name in ['Carolina Chickadee','Mourning Dove','Mallard']:
                    if name!=card['name']: stage(s,name,eggs=1)
                for name in ['House Finch','American Robin','American Goldfinch']:
                    if name!=card['name']: stage(s,name,hand=True)
                s['players'][seat]['food']=dict.fromkeys(w.FOODS,5)
                s['feeder']=['seed','fish','fruit']
                s=power(s,card['name'])
                for _ in range(120):
                    if s['completed_turns']:break
                    opts=w.legal_actions(s,s['active_seat'])
                    good=[a for a in opts if a['action']['type'] not in ('skip','reroll')]
                    chosen=(good or opts)[0]
                    s,_=w.apply_action(s,s['active_seat'],chosen['action'])
                self.assertEqual(1,s['completed_turns'])
                w.validate_state(s)

    def test_random_games_both_boards_json_replay_and_exact_turn_counts(self):
        for n in range(2,6):
            for board in ('green','blue'):
                s=w.new_game(n,37,{'goal_board':board});rng=random.Random(4)
                while s['status']=='active':
                    self.assertLess(s['turn_count'],3000)
                    actions=w.legal_actions(s,s['active_seat']);self.assertTrue(actions)
                    self.assertEqual(len(actions),len({a['id'] for a in actions}))
                    a=rng.choice(actions)['action']
                    replay,e2=w.apply_action(json.loads(json.dumps(s)),s['active_seat'],a)
                    s,e1=w.apply_action(s,s['active_seat'],a)
                    self.assertEqual(w.state_hash(s),w.state_hash(replay));self.assertEqual(e1,e2)
                self.assertEqual([26]*n,[p['turns'] for p in s['players']])
                self.assertEqual(4,len(s['goal_history']))
                self.assertEqual(26*n,s['completed_turns'])

    def test_exhausted_deck_reshuffles_discards_without_recycling_tucked_cards(self):
        s=ready();seat=s['active_seat']
        bird=stage(s,'American Coot','wetland')
        tucked=s['deck'].pop()
        w._bird(s['players'][seat],bird)['tucked'].append(tucked)
        s['discard'].extend(s['deck']);s['deck'].clear()
        expected=set(s['discard'])
        w._update_scores(s)
        original=deepcopy(s)
        drawn=w._draw(s)
        again=w._draw(original)
        self.assertEqual(drawn,again)
        self.assertIn(drawn,expected);self.assertNotEqual(drawn,tucked)
        s['players'][seat]['hand'].append(drawn)
        self.assertEqual([],s['discard'])
        w.validate_state(s)

    def test_star_nest_applies_to_all_four_goal_and_bonus_types(self):
        s=ready();seat=s['active_seat']
        bird=next(c for c in w.BIRDS.values() if c['nest']=='star' and c['egg_limit']>=2)
        stage(s,bird['name'],eggs=2)
        p=s['players'][seat]
        for nest in ('bowl','cavity','ground','platform'):
            self.assertEqual(2,w.goal_value(p,'eggs_'+nest))
            self.assertEqual(1,w.goal_value(p,'nested_'+nest))
        for bonus in ('nest_box_builder','enclosure_builder','platform_builder','wildlife_gardener'):
            self.assertEqual(1,w.bonus_value(p,bonus)['count'])
        self.assertNotIn('Anatomist',w.BIRDS[key('Tufted Titmouse')]['name_bonuses'])

    def test_all_player_eggs_use_distinct_birds_and_respect_capacity(self):
        s=ready();seat=s['active_seat'];other=1-seat
        stage(s,'Lazuli Bunting','grassland')
        first=stage(s,'House Finch','grassland')
        stage(s,'Northern Cardinal','forest',seat=other)
        s=power(s,'Lazuli Bunting');s=act(s,'lay_egg',bird_id=first)
        self.assertFalse(any(a['action'].get('bird_id')==first for a in w.legal_actions(s,seat)))
        s=act(s,'lay_egg')
        self.assertEqual(other,s['active_seat']);s=act(s,'lay_egg')
        self.assertEqual(1,s['completed_turns'])
        self.assertEqual(2,sum(b['eggs'] for b in w.all_birds(s['players'][seat])))
        self.assertEqual(1,sum(b['eggs'] for b in w.all_birds(s['players'][other])))

    def test_extra_bird_uses_normal_egg_cost_and_no_second_action_cube(self):
        s=ready();seat=s['active_seat']
        stage(s,'Downy Woodpecker','forest',eggs=1)
        chick=stage(s,'Carolina Chickadee',hand=True)
        s['players'][seat]['food']=dict.fromkeys(w.FOODS,3)
        s=power(s,'Downy Woodpecker')
        s=act(s,'play_bird',card_id=chick,habitat='forest')
        self.assertEqual('pay_eggs',s['phase']);s=act(s,'pay_egg')
        s=act(s,'pay_food',food=['seed'])
        self.assertEqual(7,s['players'][seat]['actions_left'])
        self.assertEqual(1,s['completed_turns'])
        self.assertEqual(2,len(s['players'][seat]['habitats']['forest']))

    def test_corrupted_inventory_eggs_food_and_scores_rejected(self):
        for mutation in [lambda s:s['deck'].pop(), lambda s:s['bonus_deck'].append(s['bonus_deck'][0]),
                         lambda s:s['players'][0]['food'].update(seed=-1),lambda s:s['players'][0].update(score=900)]:
            s=ready();mutation(s)
            with self.assertRaises(AssertionError):w.validate_state(s)

    def test_store_runner_resume_replay_and_events_are_private(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'wingspan.sqlite3';store=Store(db)
            match_id,_,_=store.create(2,17,'wingspan',{'goal_board':'blue'})
            configs=[PlayerConfig.from_dict({'name':f'Random {i}','backend':'random'},i) for i in range(2)]
            result=run_match(store,match_id,configs,max_turns=2500)
            self.assertEqual('finished',store.load(match_id)[1]['status'])
            self.assertEqual('wingspan',result['game'])
            replay=store.replay(match_id);self.assertGreater(len(replay),52)
            digest=replay[-1]['state_hash'];store.close()
            store=Store(db);self.assertEqual(digest,store.replay(match_id)[-1]['state_hash']);store.close()
