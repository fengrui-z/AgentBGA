"""Base English edition mechanical catalog; see CATALOG_LICENSE.txt and notices."""
import json
from pathlib import Path

BIRDS = {b['id']: b for b in json.loads(Path(__file__).with_name('birds.json').read_text())}
FOODS = ('invertebrate', 'seed', 'fish', 'fruit', 'rodent')
HABITATS = ('forest', 'grassland', 'wetland')
DIE_FACES = (*FOODS, 'invertebrate/seed')
# Each tuple is one physical double-sided goal tile.
GOAL_TILES = tuple((f'birds_{h}', f'eggs_{h}') for h in HABITATS) + tuple(
    (f'nested_{n}', f'eggs_{n}') for n in ('bowl', 'cavity', 'ground', 'platform')
) + (('egg_sets', 'birds_total'),)
# threshold/points pairs. Per-item bonuses have a multiplier instead.
BONUSES = {}

def _bonus(name, metric, thresholds=(), multiplier=0):
    key = name.lower().replace(' ', '_')
    BONUSES[key] = {'id': key, 'name': name, 'metric': metric,
                    'thresholds': list(thresholds), 'multiplier': multiplier}

_bonus('Anatomist', 'name:Anatomist', [(2, 3), (4, 7)])
_bonus('Backyard Birder', 'low_points', [(5, 3), (7, 6)])
_bonus('Bird Counter', 'flocking', multiplier=2)
_bonus('Bird Feeder', 'food:seed', [(5, 3), (8, 7)])
_bonus('Breeding Manager', 'four_eggs', multiplier=1)
_bonus('Cartographer', 'name:Cartographer', [(2, 3), (4, 7)])
_bonus('Ecologist', 'fewest_habitat', multiplier=2)
_bonus('Enclosure Builder', 'nest:ground', [(4, 4), (6, 7)])
_bonus('Falconer', 'predator', multiplier=2)
_bonus('Fishery Manager', 'food:fish', [(2, 3), (4, 8)])
_bonus('Food Web Expert', 'only_invertebrate', multiplier=2)
_bonus('Forester', 'only:forest', [(3, 4), (5, 8)])
_bonus('Historian', 'name:Historian', multiplier=2)
_bonus('Large Bird Specialist', 'large', [(4, 3), (6, 6)])
_bonus('Nest Box Builder', 'nest:cavity', [(4, 4), (6, 7)])
_bonus('Omnivore Expert', 'food:wild', multiplier=2)
_bonus('Oologist', 'has_egg', [(7, 3), (9, 6)])
_bonus('Passerine Specialist', 'small', [(4, 3), (6, 6)])
_bonus('Photographer', 'name:Photographer', [(4, 3), (6, 7)])
_bonus('Platform Builder', 'nest:platform', [(4, 4), (6, 7)])
_bonus('Prairie Manager', 'only:grassland', [(2, 3), (4, 8)])
_bonus('Rodentologist', 'food:rodent', multiplier=2)
_bonus('Visionary Leader', 'hand', [(5, 4), (8, 7)])
_bonus('Viticulturalist', 'food:fruit', [(2, 3), (4, 7)])
_bonus('Wetland Scientist', 'only:wetland', [(3, 3), (5, 7)])
_bonus('Wildlife Gardener', 'nest:bowl', [(4, 4), (6, 7)])


def all_birds(player):
    return [b for h in HABITATS for b in player['habitats'][h]]


def nest_matches(bird, nest):
    return BIRDS[bird['id']]['nest'] in (nest, 'star')


def goal_value(player, goal):
    if goal == 'birds_total':
        return len(all_birds(player))
    if goal == 'egg_sets':
        return min(sum(b['eggs'] for b in player['habitats'][h]) for h in HABITATS)
    kind, target = goal.split('_', 1)
    birds = player['habitats'][target] if target in HABITATS else [
        b for b in all_birds(player) if nest_matches(b, target)]
    return sum(b['eggs'] for b in birds) if kind == 'eggs' else sum(
        1 for b in birds if kind == 'birds' or b['eggs'] > 0)


def bonus_value(player, key):
    bonus = BONUSES[key]
    metric = bonus['metric']
    birds = all_birds(player)
    if metric == 'hand':
        count = len(player['hand'])
    elif metric == 'fewest_habitat':
        count = min(len(player['habitats'][h]) for h in HABITATS)
    else:
        def matches(b):
            c = BIRDS[b['id']]
            if metric.startswith('name:'): return metric[5:] in c['name_bonuses']
            if metric.startswith('nest:'): return nest_matches(b, metric[5:])
            if metric.startswith('food:'): return metric[5:] in c['cost']
            if metric.startswith('only:'): return c['habitats'] == [metric[5:]]
            return {'low_points': c['points'] < 4, 'flocking': c['flocking'],
                    'predator': c['predator'], 'four_eggs': b['eggs'] >= 4,
                    'has_egg': b['eggs'] > 0, 'large': c['wingspan'] > 65,
                    'small': c['wingspan'] <= 30,
                    'only_invertebrate': set(c['cost']) == {'invertebrate'}}[metric]
        count = sum(matches(b) for b in birds)
    points = count * bonus['multiplier'] if bonus['multiplier'] else max(
        (points for threshold, points in bonus['thresholds'] if count >= threshold), default=0)
    return {'count': count, 'points': points}


def score_breakdown(player):
    birds = all_birds(player)
    return {'birds': sum(BIRDS[b['id']]['points'] for b in birds),
            'eggs': sum(b['eggs'] for b in birds),
            'cached_food': sum(sum(b['cache'].values()) for b in birds),
            'tucked_cards': sum(len(b['tucked']) for b in birds),
            'round_goals': sum(player['round_points']),
            'bonus_cards': sum(bonus_value(player, k)['points'] for k in player['bonuses'])}
