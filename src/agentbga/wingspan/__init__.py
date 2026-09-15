"""Deterministic Wingspan base multiplayer rules with explicit effect decisions."""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
from itertools import combinations, combinations_with_replacement
import random

from ..game import GameRuleError
from ..mechanics import ActionSpace, action_accepted, assign_competition_ranks, domain_event, state_digest
from .catalog import (BIRDS, BONUSES, DIE_FACES, FOODS, GOAL_TILES, HABITATS,
                      all_birds, bonus_value, goal_value, nest_matches, score_breakdown)

from .presentation import power_summary, power_summary_cn

RULES_VERSION = 'stonemaier-base-en-1.0'
SCHEMA_VERSION = 'agentbga.wingspan.state.v1'
RULES = {
    'setup': 'Keep any of five birds; discard one of your five food tokens for each bird kept. Keep one of two bonus cards.',
    'turn': 'Four rounds, with 8/7/6/5 actions per player. Play a bird, gain food, lay eggs, or draw cards. Resolve brown powers from right to left; powers are optional.',
    'play': 'Use a permitted habitat, filling from left to right. Pay printed food and 0/1/1/2/2 eggs for columns 1–5. Any two food can replace one required food, only when playing a bird. White powers activate only on play.',
    'forest': 'At 0–5 birds gain 1/1/2/2/3/3 food from the feeder. At 1/3/5 birds you may discard one card for one extra food, before brown powers.',
    'grassland': 'At 0–5 birds lay 2/2/3/3/4/4 eggs. At 1/3/5 birds you may discard one food for one extra egg. Respect each bird’s egg capacity.',
    'wetland': 'At 0–5 birds draw 1/1/2/2/3/3 cards. At 1/3/5 birds you may discard one egg for one extra card. Choose face-up cards or the deck. Refill tray only at turn end.',
    'dice': 'One food per die; the invertebrate/seed face gives a choice. Empty feeder rerolls all five dice immediately. When gaining food and all remaining faces are identical, you may reroll all five before selecting a die.',
    'powers': 'Brown powers resolve in reverse habitat order. Pink powers may be used once between your own turns, including across rounds. Copied powers act on the original bird. A repeat cannot form a recursive loop.',
    'rounds': 'Score the round goal, discard and refill the tray, pass first player clockwise. Green goals award 4/1/0, 5/2/1, 6/3/2, 7/4/3; split occupied places on ties, round down, and score zero for no qualifying items. Blue scores min(quantity, 5).',
    'scoring': 'Bird points + bonus cards + round goals + one point per egg, cached food, and tucked card. Ties use unused food, then shared victory. Hidden bonus scores are revealed at game end.',
}

class RuleError(GameRuleError):
    """Invalid Wingspan decision."""


def describe():
    return {'id': 'wingspan', 'name': 'Wingspan · 展翅翱翔', 'rules_version': RULES_VERSION,
            'players': {'minimum': 2, 'maximum': 5}, 'runnable': True,
            'hidden_information': True, 'implementation_status': 'playable_beta',
            'decision_model': 'sequential_effect_choices', 'default_max_turns': 5000,
            'setup_options': {'goal_board': ['green', 'blue']},
            'action_types': ['keep_birds', 'discard_food', 'choose_bonus', 'play_bird',
                             'gain_food', 'lay_eggs', 'draw_cards', 'pay_food', 'pay_egg',
                             'take_food', 'reroll', 'lay_egg', 'draw_card', 'activate_power',
                             'skip', 'tuck_card', 'discard_card', 'trade_food', 'move_bird',
                             'repeat_power', 'choose_start', 'draft_card'],
            'content_scope': '170 base birds, 26 bonus cards, 8 double-sided goals; 2–5 players. No Swift-Start, expansions, Automa, or publisher artwork.',
            'rules_sources': ['https://stonemaiergames.com/games/wingspan/rules/', 'https://wingspan.rulepop.com/'],
            'win_condition': 'Highest score, then most unused food; remaining ties share victory.'}


def _rng(state):
    rng = random.Random()
    value = state['rng']
    rng.setstate((value[0], tuple(value[1]), value[2]))
    return rng


def _shuffle(state, items):
    rng = _rng(state)
    rng.shuffle(items)
    state['rng'] = list(rng.getstate())
    state['rng'][1] = list(state['rng'][1])


def _roll(state, count):
    rng = _rng(state)
    faces = [rng.choice(DIE_FACES) for _ in range(count)]
    state['rng'] = list(rng.getstate())
    state['rng'][1] = list(state['rng'][1])
    return faces


def _draw(state, bonus=False):
    deck, discard = ('bonus_deck', 'bonus_discard') if bonus else ('deck', 'discard')
    if not state[deck] and state[discard]:
        state[deck] = state[discard][:]
        state[discard].clear()
        _shuffle(state, state[deck])
    return state[deck].pop() if state[deck] else None


def _refill(state):
    for i in range(3):
        if state['tray'][i] is None:
            state['tray'][i] = _draw(state)


def new_game(players, seed, config=None):
    config = {} if config is None else config
    if type(players) is not int or not 2 <= players <= 5:
        raise RuleError('Wingspan base multiplayer requires 2 to 5 players')
    if type(seed) is not int or not isinstance(config, dict) or set(config) - {'goal_board'}:
        raise RuleError('integer seed and goal_board setup option required')
    if config.get('goal_board', 'green') not in ('green', 'blue'):
        raise RuleError('goal_board must be green or blue')
    rng = random.Random(seed)
    deck, bonus = list(BIRDS), list(BONUSES)
    rng.shuffle(deck)
    rng.shuffle(bonus)
    tiles = list(GOAL_TILES)
    rng.shuffle(tiles)
    goals = [rng.choice(tile) for tile in tiles[:4]]
    first = rng.randrange(players)
    state = {'schema_version': SCHEMA_VERSION, 'rules_version': RULES_VERSION, 'seed': seed,
             'rng': list(rng.getstate()), 'player_count': players, 'status': 'active',
             'phase': 'setup', 'round': 1, 'turn_count': 0, 'completed_turns': 0,
             'active_seat': first, 'turn_owner': first, 'first_player': first,
             'goal_board': config.get('goal_board', 'green'), 'goals': goals, 'goal_history': [],
             'deck': deck, 'discard': [], 'bonus_deck': bonus, 'bonus_discard': [],
             'tray': [None]*3, 'feeder': [], 'queue': [], 'draft': [], 'players': []}
    state['rng'][1] = list(state['rng'][1])
    for seat in range(players):
        state['players'].append({'seat': seat, 'hand': [deck.pop() for _ in range(5)],
                                'food': dict.fromkeys(FOODS, 1), 'habitats': {h: [] for h in HABITATS},
                                'bonuses': [], 'bonus_choices': [bonus.pop() for _ in range(2)],
                                'round_points': [], 'actions_left': 8, 'turns': 0,
                                'pink_used': [], 'end_discards': 0, 'score': 0})
    _refill(state)
    state['feeder'] = _roll(state, 5)
    for i in range(players):
        seat = (first+i) % players
        state['queue'].extend([{'op': 'setup_keep', 'seat': seat},
                               {'op': 'bonus_choose', 'seat': seat}])
    _advance(state)
    _update_scores(state)
    validate_state(state)
    return state


def _bird(player, key):
    return next(b for b in all_birds(player) if b['id'] == key)


def _habitat(player, key):
    return next(h for h in HABITATS if any(b['id'] == key for b in player['habitats'][h]))


def _tasks(state, *items):
    state['queue'][0:0] = list(items)


def _effect(op, seat, **kwargs):
    return {'op': op, 'seat': seat, **kwargs}


def _costs(card):
    if card['cost_choice']:
        return (tuple([f]) for f in card['cost'])
    return (tuple(f for f, n in card['cost'].items() for _ in range(n)),)


@lru_cache(maxsize=8192)
def _can_pay(food, needs):
    if not needs:
        return True
    for payment in _payments(food, needs[0]):
        remaining = tuple(n-payment.count(f) for f, n in zip(FOODS, food))
        if _can_pay(remaining, needs[1:]):
            return True
    return False


def _payments(food, need):
    single = [(f,) for f, n in zip(FOODS, food) if n and need in (f, 'wild')]
    pairs = [pair for pair in combinations_with_replacement(FOODS, 2)
             if all(food[FOODS.index(f)] >= pair.count(f) for f in set(pair))]
    return single+pairs


def _play_choices(state, seat, habitat=None):
    p = state['players'][seat]
    food = tuple(p['food'][f] for f in FOODS)
    eggs = sum(b['eggs'] for b in all_birds(p))
    actions = []
    for key in p['hand']:
        c = BIRDS[key]
        if not any(_can_pay(food, needs) for needs in _costs(c)):
            continue
        for h in c['habitats']:
            size = len(p['habitats'][h])
            if size < 5 and eggs >= (0, 1, 1, 2, 2)[size] and habitat in (None, h):
                actions.append({'type': 'play_bird', 'card_id': key, 'habitat': h})
    return actions


def _egg_targets(player, task, paying=False):
    return [b for b in all_birds(player)
            if (b['eggs'] > 0 if paying else b['eggs'] < BIRDS[b['id']]['egg_limit'])
            and (not task.get('nest') or nest_matches(b, task['nest']))
            and (not task.get('self') or b['id'] == task.get('bird'))
            and (not task.get('other') or b['id'] != task.get('bird'))
            and b['id'] not in task.get('used', [])]


def _choices(state, task):
    p, op = state['players'][task['seat']], task['op']
    actions = []
    if op == 'setup_keep':
        actions = [{'type': 'keep_birds', 'card_ids': list(c)} for n in range(6)
                   for c in combinations(p['hand'], n)]
    elif op == 'discard_food':
        actions = [{'type': 'discard_food', 'food': f} for f in FOODS if p['food'][f]]
    elif op == 'bonus_choose':
        actions = [{'type': 'choose_bonus', 'card_id': k} for k in p['bonus_choices']]
    elif op == 'play':
        actions = _play_choices(state, task['seat'], task.get('habitat'))
    elif op == 'pay_food':
        food = tuple(p['food'][f] for f in FOODS)
        seen = set()
        for needs in task['costs']:
            if not needs:
                continue
            for payment in _payments(food, needs[0]):
                remaining = tuple(n-payment.count(f) for f, n in zip(FOODS, food))
                if _can_pay(remaining, tuple(needs[1:])):
                    choice = (tuple(payment), tuple(needs[1:]))
                    if choice not in seen:
                        seen.add(choice)
                        actions.append({'type': 'pay_food', 'food': list(payment), 'remaining': list(needs[1:])})
    elif op in ('eggs', 'pay_eggs'):
        actions = [{'type': 'pay_egg' if op == 'pay_eggs' else 'lay_egg', 'bird_id': b['id']}
                   for b in _egg_targets(p, task, paying=op == 'pay_eggs')]
    elif op in ('food', 'feeder'):
        allowed = task.get('foods', FOODS)
        if op == 'food':
            actions = [{'type': 'take_food', 'food': f} for f in allowed]
        else:
            for face in dict.fromkeys(state['feeder']):
                for f in face.split('/'):
                    if f in allowed:
                        actions.append({'type': 'take_food', 'food': f, 'face': face, 'cache': False})
                        if task.get('cache'):
                            actions.append({'type': 'take_food', 'food': f, 'face': face, 'cache': True})
            if len(set(state['feeder'])) == 1:
                actions.append({'type': 'reroll'})
    elif op == 'draw':
        if state['deck'] or state['discard']:
            actions.append({'type': 'draw_card', 'source': 'deck'})
        if not task.get('deck_only'):
            actions.extend({'type': 'draw_card', 'source': 'tray', 'slot': i}
                           for i, k in enumerate(state['tray']) if k)
    elif op == 'discard_card':
        actions = [{'type': 'discard_card', 'card_id': k} for k in p['hand']]
    elif op == 'power':
        actions = [{'type': 'activate_power', 'bird_id': task['bird']}]
    elif op == 'tuck':
        actions = [{'type': 'tuck_card', 'card_id': k} for k in p['hand']]
    elif op == 'trade':
        actions = [{'type': 'trade_food', 'give': f, 'receive': g} for f in FOODS
                   if p['food'][f] for g in FOODS if g != f]
    elif op == 'food_tuck':
        if p['food'][task['food']]:
            actions = [{'type': 'discard_food', 'food': task['food']}]
    elif op == 'move':
        h = _habitat(p, task['bird'])
        if p['habitats'][h][-1]['id'] == task['bird']:
            actions = [{'type': 'move_bird', 'habitat': g} for g in HABITATS
                       if g != h and len(p['habitats'][g]) < 5]
    elif op == 'repeat':
        h = _habitat(p, task['bird'])
        actions = [{'type': 'repeat_power', 'bird_id': b['id']} for b in p['habitats'][h]
                   if b['id'] not in task.get('chain', []) + [task['bird']]
                   and BIRDS[b['id']]['color'] == 'brown'
                   and (not task.get('predator') or BIRDS[b['id']]['predator'])]
    elif op == 'choose_start':
        actions = [{'type': 'choose_start', 'seat': i} for i in range(state['player_count'])]
    elif op == 'draft_choose':
        actions = [{'type': 'draft_card', 'card_id': k} for k in state['draft']]
    elif op == 'feeder_all':
        if any(any(f in task['foods'] for f in face.split('/')) for face in state['feeder']):
            actions.append({'type': 'take_all_food'})
        if len(set(state['feeder'])) == 1:
            actions.append({'type': 'reroll'})
    if task.get('optional'):
        actions.append({'type': 'skip'})
    return actions


def legal_actions(state, seat):
    _check_seat(state, seat)
    if state['status'] != 'active' or seat != state['active_seat']:
        return []
    if state['queue']:
        actions = _choices(state, state['queue'][0])
    else:
        actions = _play_choices(state, seat) + [{'type': t} for t in ('gain_food', 'lay_eggs', 'draw_cards')]
    # Include a recognizable private prefix so harness audit projections cannot
    # expose a brute-forceable digest of hidden card selections.
    prefix = 'wingspan-private' if state['queue'] and state['queue'][0]['op'] in (
        'setup_keep', 'bonus_choose', 'discard_card', 'tuck', 'draft_choose') else 'wingspan'
    if prefix == 'wingspan-private':
        actions = [{**a, 'private': 'wingspan'} for a in actions]
    return ActionSpace.from_actions(state['phase'], state['turn_count'], actions, prefix=prefix).wrapped()


def _check_seat(state, seat):
    if type(seat) is not int or not 0 <= seat < state['player_count']:
        raise RuleError('seat out of range')


def _trigger(state, actor, trigger):
    tasks = []
    for i in range(1, state['player_count']):
        seat = (actor+i) % state['player_count']
        p = state['players'][seat]
        for b in all_birds(p):
            if BIRDS[b['id']]['power'].get('trigger') == trigger and b['id'] not in p['pink_used']:
                tasks.append(_effect('power', seat, bird=b['id'], optional=True, pink=True))
    _tasks(state, *tasks)


def _activate(state, task):
    seat, key = task['seat'], task['bird']
    p = state['players'][seat]
    power = BIRDS[key]['power']
    kind = power['kind']
    params = {k: v for k, v in power.items() if k not in ('kind', 'trigger')}
    def job(op, **kw):
        return _effect(op, seat, bird=key, **kw)
    if kind in ('food', 'feeder', 'eggs', 'draw', 'move', 'trade', 'tuck', 'food_tuck', 'repeat', 'feeder_all'):
        if kind == 'repeat':
            params['chain'] = task.get('chain', [])+[key]
        _tasks(state, job(kind, optional=True, **params))
    elif kind == 'none':
        pass
    elif kind == 'cache':
        _bird(p, key)['cache'][power['food']] += 1
    elif kind == 'bonus':
        p['bonus_choices'] = [k for _ in range(2) if (k := _draw(state, bonus=True))]
        _tasks(state, job('bonus_choose'))
    elif kind == 'egg_trade':
        _tasks(state, job('pay_eggs', count=1, other=power.get('other', False), optional=True,
                         then=job('food' if power['reward'] == 'food' else 'draw', count=power['count'], optional=True)))
    elif kind == 'draw_discard':
        _tasks(state, job('draw', count=power['count'], optional=True, deferred_discard=True))
    elif kind == 'hunt_card':
        card = _draw(state)
        if card:
            if BIRDS[card]['wingspan'] < power['limit']:
                _bird(p, key)['tucked'].append(card)
                _trigger(state, seat, 'predator')
            else:
                state['discard'].append(card)
    elif kind == 'hunt_dice':
        faces = _roll(state, 5-len(state['feeder']))
        if power['food'] in faces:
            _bird(p, key)['cache'][power['food']] += 1
            _trigger(state, seat, 'predator')
    elif kind == 'all_feeder':
        _tasks(state, job('choose_start'))
    elif kind == 'all_food':
        for other in state['players']:
            other['food'][power['food']] += 1
    elif kind == 'all_draw':
        for i in range(state['player_count']):
            other = state['players'][(seat+i) % state['player_count']]
            if (card := _draw(state)):
                other['hand'].append(card)
    elif kind == 'fewest':
        fewest = min(len(other['habitats'][power['habitat']]) for other in state['players'])
        _tasks(state, *[_effect(power['reward'], (seat+i) % state['player_count'], optional=True)
                       for i in range(state['player_count'])
                       if len(state['players'][(seat+i) % state['player_count']]['habitats'][power['habitat']]) == fewest])
    elif kind == 'nest_eggs':
        for b in all_birds(p):
            if nest_matches(b, power['nest']):
                b['eggs'] = min(b['eggs']+1, BIRDS[b['id']]['egg_limit'])
    elif kind == 'all_eggs':
        _tasks(state, *[_effect('eggs', (seat+i) % state['player_count'], nest=power['nest'],
                               count=2 if i == 0 else 1, distinct=True, optional=True)
                       for i in range(state['player_count'])])
    elif kind == 'extra_bird':
        h = _habitat(p, key) if power['habitat'] == 'same' else power['habitat']
        _tasks(state, job('play', habitat=h, optional=True))
    elif kind == 'draft':
        state['draft'] = [k for _ in range(state['player_count']+1) if (k := _draw(state))]
        # Card printing: each player selects one; owner retains the last card.
        _tasks(state, *[_effect('draft_choose', (seat+i) % state['player_count']) for i in range(state['player_count'])],
               job('draft_finish'))
    else:
        raise AssertionError(f'unimplemented Wingspan power: {kind}')


def _begin_play(state, seat, action):
    p = state['players'][seat]
    key, h = action['card_id'], action['habitat']
    eggs = (0, 1, 1, 2, 2)[len(p['habitats'][h])]
    costs = [list(c) for c in _costs(BIRDS[key])]
    _tasks(state, _effect('pay_eggs', seat, count=eggs),
           _effect('pay_food', seat, costs=costs),
           _effect('install', seat, bird=key, habitat=h))


def _begin_turn_action(state, seat, action):
    p = state['players'][seat]
    p['actions_left'] -= 1
    kind = action['type']
    if kind == 'play_bird':
        _begin_play(state, seat, action)
        return
    h, op = {'gain_food': ('forest', 'feeder'), 'lay_eggs': ('grassland', 'eggs'),
             'draw_cards': ('wetland', 'draw')}[kind]
    size = len(p['habitats'][h])
    count = (2 if h == 'grassland' else 1) + size//2
    row = [_effect(op, seat, count=count, optional=True, base_action=kind)]
    if size % 2:
        pay = {'forest': 'discard_card', 'grassland': 'discard_food', 'wetland': 'pay_eggs'}[h]
        row.append(_effect(pay, seat, optional=True, count=1,
                           then=_effect(op, seat, count=1, optional=True, base_action=kind)))
    row.extend(_effect('power', seat, bird=b['id'], optional=True)
               for b in reversed(p['habitats'][h]) if BIRDS[b['id']]['color'] == 'brown')
    _tasks(state, *row)
    if kind == 'lay_eggs':
        _trigger(state, seat, 'lay_eggs')


def _consume(state, task, *, then=True):
    task['count'] = task.get('count', 1)-1
    if task['count'] > 0:
        _tasks(state, task)
    elif then and task.get('then'):
        _tasks(state, task['then'])


def _resolve(state, seat, action):
    task = state['queue'].pop(0)
    p, kind, op = state['players'][seat], action['type'], task['op']
    if kind == 'skip':
        return
    if kind == 'keep_birds':
        kept = action['card_ids']
        state['discard'].extend(k for k in p['hand'] if k not in kept)
        p['hand'] = kept[:]
        if kept:
            _tasks(state, _effect('discard_food', seat, count=len(kept)))
    elif kind == 'choose_bonus':
        p['bonuses'].append(action['card_id'])
        state['bonus_discard'].extend(k for k in p['bonus_choices'] if k != action['card_id'])
        p['bonus_choices'].clear()
    elif kind == 'discard_food':
        p['food'][action['food']] -= 1
        if op == 'food_tuck':
            for _ in range(2):
                if (card := _draw(state)):
                    _bird(p, task['bird'])['tucked'].append(card)
        else:
            _consume(state, task)
    elif kind == 'play_bird':
        _begin_play(state, seat, action)
    elif kind == 'pay_food':
        for f in action['food']:
            p['food'][f] -= 1
        if action['remaining']:
            task['costs'] = [action['remaining']]
            _tasks(state, task)
    elif kind in ('pay_egg', 'lay_egg'):
        b = _bird(p, action['bird_id'])
        b['eggs'] += -1 if kind == 'pay_egg' else 1
        if task.get('distinct'):
            task.setdefault('used', []).append(b['id'])
        _consume(state, task)
    elif kind == 'reroll':
        state['feeder'] = _roll(state, 5)
        _tasks(state, task)
    elif kind == 'take_food':
        food = action['food']
        if op == 'feeder':
            state['feeder'].remove(action['face'])
            if not state['feeder']:
                state['feeder'] = _roll(state, 5)
        if action.get('cache'):
            _bird(p, task['bird'])['cache'][food] += 1
        else:
            p['food'][food] += 1
        _consume(state, task)
        if task.get('base_action') == 'gain_food' and food == 'rodent':
            _trigger(state, seat, 'gain_rodent')
    elif kind == 'take_all_food':
        faces = [f for f in state['feeder'] if any(x in task['foods'] for x in f.split('/'))]
        for face in faces:
            state['feeder'].remove(face)
            food = next(x for x in face.split('/') if x in task['foods'])
            p['food'][food] += 1
        if not state['feeder']:
            state['feeder'] = _roll(state, 5)
    elif kind == 'draw_card':
        if action['source'] == 'deck':
            card = _draw(state)
        else:
            card = state['tray'][action['slot']]
            state['tray'][action['slot']] = None
        p['hand'].append(card)
        if task.pop('deferred_discard', False):
            p['end_discards'] += 1
        _consume(state, task)
    elif kind == 'discard_card':
        p['hand'].remove(action['card_id'])
        state['discard'].append(action['card_id'])
        _consume(state, task)
    elif kind == 'activate_power':
        if task.get('pink'):
            if task['bird'] in p['pink_used']:
                return
            p['pink_used'].append(task['bird'])
        _activate(state, task)
    elif kind == 'tuck_card':
        p['hand'].remove(action['card_id'])
        _bird(p, task['bird'])['tucked'].append(action['card_id'])
        reward = task.get('reward')
        if reward:
            extra = {'self': True} if reward == 'egg' else {'foods': task['foods']} if reward == 'food' else {}
            _tasks(state, _effect('eggs' if reward == 'egg' else reward, seat,
                                 bird=task['bird'], optional=True, **extra))
    elif kind == 'trade_food':
        p['food'][action['give']] -= 1
        p['food'][action['receive']] += 1
    elif kind == 'move_bird':
        source = p['habitats'][_habitat(p, task['bird'])]
        b = source.pop()
        p['habitats'][action['habitat']].append(b)
    elif kind == 'repeat_power':
        _tasks(state, _effect('power', seat, bird=action['bird_id'], chain=task['chain']))
    elif kind == 'choose_start':
        _tasks(state, *[_effect('feeder', (action['seat']+i) % state['player_count'], optional=True)
                       for i in range(state['player_count'])])
    elif kind == 'draft_card':
        state['draft'].remove(action['card_id'])
        p['hand'].append(action['card_id'])
    else:
        raise AssertionError(f'unhandled action {kind}')


def _advance(state):
    """Resolve forced bookkeeping, stopping at the next actual player choice."""
    while state['status'] == 'active':
        if state['queue']:
            task = state['queue'][0]
            op, seat = task['op'], task['seat']
            p = state['players'][seat]
            if op == 'install':
                state['queue'].pop(0)
                key, h = task['bird'], task['habitat']
                p['hand'].remove(key)
                p['habitats'][h].append({'id': key, 'eggs': 0, 'cache': dict.fromkeys(FOODS, 0), 'tucked': []})
                if BIRDS[key]['color'] == 'white':
                    _tasks(state, _effect('power', seat, bird=key, optional=True))
                _trigger(state, seat, 'play_'+h)
                continue
            if op == 'draft_finish':
                state['queue'].pop(0)
                p['hand'].extend(state['draft'])
                state['draft'].clear()
                continue
            if (task.get('count') == 0 or (op == 'pay_food' and any(not c for c in task['costs']))
                    or (op == 'power' and task.get('pink') and task['bird'] in p['pink_used'])):
                state['queue'].pop(0)
                continue
            choices = _choices(state, task)
            if not choices or all(a['type'] == 'skip' for a in choices):
                state['queue'].pop(0)
                continue
            state['active_seat'] = seat
            state['phase'] = 'setup' if state['phase'] == 'setup' else op
            return
        if state['phase'] == 'setup':
            state['turn_owner'] = state['first_player']
            state['active_seat'] = state['turn_owner']
            state['phase'] = 'turn'
            return
        if state['phase'] == 'turn':
            return
        p = state['players'][state['turn_owner']]
        if p['end_discards']:
            count = min(p['end_discards'], len(p['hand']))
            p['end_discards'] = 0
            if count:
                _tasks(state, _effect('discard_card', p['seat'], count=count))
                continue
        _end_turn(state)
        return


def _end_turn(state):
    p = state['players'][state['turn_owner']]
    p['turns'] += 1
    state['completed_turns'] += 1
    if all(other['actions_left'] == 0 for other in state['players']):
        _score_round(state)
        if state['round'] == 4:
            state['status'] = 'finished'
            state['phase'] = 'finished'
            state['active_seat'] = state['turn_owner']
            return
        state['round'] += 1
        state['first_player'] = (state['first_player']+1) % state['player_count']
        for other in state['players']:
            other['actions_left'] = 9-state['round']
        state['discard'].extend(k for k in state['tray'] if k)
        state['tray'] = [None]*3
        following = state['first_player']
    else:
        following = (state['turn_owner']+1) % state['player_count']
        while not state['players'][following]['actions_left']:
            following = (following+1) % state['player_count']
    _refill(state)
    state['turn_owner'] = following
    state['active_seat'] = following
    state['players'][following]['pink_used'].clear()
    state['phase'] = 'turn'


def _score_round(state):
    goal = state['goals'][state['round']-1]
    quantities = [goal_value(p, goal) for p in state['players']]
    awards = [0]*state['player_count']
    if state['goal_board'] == 'blue':
        awards = [min(5, n) for n in quantities]
    else:
        r = state['round']
        scores = [3+r, r, max(0, r-1), 0, 0]
        for i, n in enumerate(quantities):
            if n:
                better = sum(x > n for x in quantities)
                tied = quantities.count(n)
                awards[i] = sum(scores[better:better+tied])//tied
    for p, points in zip(state['players'], awards):
        p['round_points'].append(points)
    state['goal_history'].append({'round': state['round'], 'goal': goal, 'quantities': quantities, 'points': awards})


def _update_scores(state):
    for p in state['players']:
        p['score'] = sum(score_breakdown(p).values())


def apply_action(state, seat, action):
    _check_seat(state, seat)
    if not isinstance(action, dict):
        raise RuleError('action must be an object')
    space = ActionSpace.from_actions(state['phase'], state['turn_count'],
                                     [item['action'] for item in legal_actions(state, seat)])
    canonical = space.require(action, error_factory=RuleError)
    updated = deepcopy(state)
    if updated['queue']:
        _resolve(updated, seat, canonical)
    else:
        updated['phase'] = 'action'
        _begin_turn_action(updated, seat, canonical)
    updated['turn_count'] += 1
    _advance(updated)
    _update_scores(updated)
    validate_state(updated)
    # The authoritative acceptance event enables exact replay. Public projection
    # removes hidden selections; other events contain no private card identity.
    events = [action_accepted(seat, canonical), domain_event('wingspan_decision', seat=seat, action_type=canonical['type'],
                           round=updated['round'], completed_turns=updated['completed_turns'])]
    if len(updated['goal_history']) > len(state['goal_history']):
        events.append(domain_event('wingspan_round_scored', **updated['goal_history'][-1]))
    if updated['status'] == 'finished':
        events.append(domain_event('game_finished', rankings=rankings(updated)))
    return updated, events


def state_hash(state):
    return state_digest(state)


def rankings(state):
    return assign_competition_ranks([{'seat': p['seat'], 'score': p['score'],
                                      'food': sum(p['food'].values()),
                                      'score_breakdown': score_breakdown(p)} for p in state['players']],
                                     sort_key=lambda p: (-p['score'], -p['food'], p['seat']),
                                     tie_key=lambda p: (p['score'], p['food']))


def card_view(key, placed=None):
    card = deepcopy(BIRDS[key])
    card['power_summary'] = power_summary(card['power'])
    card['power_summary_cn'] = power_summary_cn(card['power'])
    if placed is not None:
        card.update({'eggs': placed['eggs'], 'cache': deepcopy(placed['cache']),
                     'tucked_count': len(placed['tucked'])})
    return card


def observe(state, seat):
    _check_seat(state, seat)
    players = []
    for p in state['players']:
        visible = p['seat'] == seat or state['status'] == 'finished'
        breakdown = score_breakdown(p)
        if not visible:
            breakdown.pop('bonus_cards')
        players.append({'seat': p['seat'], 'food': deepcopy(p['food']),
                        'hand': [card_view(k) for k in p['hand']] if visible else [],
                        'hand_count': len(p['hand']), 'bonus_count': len(p['bonuses']),
                        'bonuses': [{**deepcopy(BONUSES[k]), **bonus_value(p, k)} for k in p['bonuses']] if visible else [],
                        'bonus_choices': [deepcopy(BONUSES[k]) for k in p['bonus_choices']] if p['seat'] == seat else [],
                        'habitats': {h: [card_view(b['id'], b) for b in p['habitats'][h]] for h in HABITATS},
                        'score': sum(breakdown.values()), 'score_breakdown': breakdown,
                        'round_points': p['round_points'][:], 'actions_left': p['actions_left'],
                        'turns': p['turns'], 'pink_used': p['pink_used'][:]})
    task = state['queue'][0] if state['queue'] else None
    pending = {k: deepcopy(v) for k, v in task.items() if k in (
        'op', 'seat', 'bird', 'count', 'foods', 'nest', 'other', 'self', 'habitat', 'optional')} if task else None
    if task and task['seat'] == seat:
        pending = deepcopy(task)
    return {'game': 'wingspan', 'rules_version': RULES_VERSION, 'viewer_seat': seat,
            **{k: state[k] for k in ('status', 'phase', 'round', 'turn_count', 'completed_turns',
                                    'active_seat', 'turn_owner', 'first_player', 'goal_board')},
            'feeder': state['feeder'][:], 'tray': [card_view(k) if k else None for k in state['tray']],
            'deck_count': len(state['deck']), 'discard_count': len(state['discard']),
            'bonus_deck_count': len(state['bonus_deck']), 'goals': state['goals'][:],
            'goal_history': deepcopy(state['goal_history']), 'players': players,
            'pending': pending, 'draft': [card_view(k) for k in state['draft']]
            if task and task['op'] == 'draft_choose' and task['seat'] == seat else [],
            'rules': dict(RULES), 'rankings': rankings(state) if state['status'] == 'finished' else None}


def validate_state(state):
    if state.get('schema_version') != SCHEMA_VERSION or state.get('rules_version') != RULES_VERSION:
        raise AssertionError('invalid Wingspan version')
    n = state['player_count']
    assert type(n) is int and 2 <= n <= 5 and len(state['players']) == n
    assert state['status'] in ('active', 'finished') and 1 <= state['round'] <= 4
    assert state['goal_board'] in ('green', 'blue')
    assert len(state['goals']) == 4 and all(g in sum(GOAL_TILES, ()) for g in state['goals'])
    assert len({next(i for i, t in enumerate(GOAL_TILES) if g in t) for g in state['goals']}) == 4
    assert all(type(state[k]) is int and 0 <= state[k] < n for k in ('active_seat', 'turn_owner', 'first_player'))
    assert all(type(state[k]) is int and state[k] >= 0 for k in ('turn_count', 'completed_turns'))
    assert 1 <= len(state['feeder']) <= 5 and all(f in DIE_FACES for f in state['feeder'])
    assert len(state['tray']) == 3
    cards = state['deck'] + state['discard'] + [k for k in state['tray'] if k] + state['draft']
    bonuses = state['bonus_deck'] + state['bonus_discard']
    for i, p in enumerate(state['players']):
        assert p['seat'] == i and set(p['habitats']) == set(HABITATS)
        assert set(p['food']) == set(FOODS) and all(type(v) is int and v >= 0 for v in p['food'].values())
        assert type(p['actions_left']) is int and 0 <= p['actions_left'] <= 9-state['round']
        assert type(p['end_discards']) is int and p['end_discards'] >= 0
        assert type(p['turns']) is int and 0 <= p['turns'] <= 26
        cards += p['hand']
        bonuses += p['bonuses'] + p['bonus_choices']
        for h, row in p['habitats'].items():
            assert len(row) <= 5
            for b in row:
                assert b['id'] in BIRDS and h in BIRDS[b['id']]['habitats']
                assert type(b['eggs']) is int and 0 <= b['eggs'] <= BIRDS[b['id']]['egg_limit']
                assert set(b['cache']) == set(FOODS) and all(type(v) is int and v >= 0 for v in b['cache'].values())
                cards += [b['id']] + b['tucked']
        assert len(set(p['pink_used'])) == len(p['pink_used'])
        assert all(k in [b['id'] for b in all_birds(p)] and BIRDS[k]['color'] == 'pink' for k in p['pink_used'])
        assert len(p['round_points']) == len(state['goal_history'])
        assert p['score'] == sum(score_breakdown(p).values())
    assert Counter(cards) == Counter(BIRDS.keys()), 'bird inventory changed'
    assert Counter(bonuses) == Counter(BONUSES.keys()), 'bonus inventory changed'
    assert state['completed_turns'] == sum(p['turns'] for p in state['players'])
    if state['status'] == 'finished':
        assert state['phase'] == 'finished' and state['round'] == 4 and not state['queue']
        assert all(p['turns'] == 26 and p['actions_left'] == 0 for p in state['players'])
    if state['queue']:
        assert state['queue'][0]['seat'] == state['active_seat']
        assert all(type(t['seat']) is int and 0 <= t['seat'] < n for t in state['queue'])
