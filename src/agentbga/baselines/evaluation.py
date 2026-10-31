"""Explicit per-game immediate material and longer-horizon position features.

No learned weights or private opponent information. Values are expressed in
approximate game points; they are intentionally simple, versioned baselines.
"""
from __future__ import annotations
import math

SCALES = {'splendor':15, 'azul':30, 'ark_nova':50, 'brass_birmingham':50,
          'castles_of_burgundy':50, 'century_spice_road':30, 'seven_wonders':30,
          'harmonies':40, 'wingspan':40, 'carcassonne':40}


def features(game, state, seat):
    """Return (immediate material value, strategic position value)."""
    p = state['players'][seat]
    kind = game.game_id
    if kind == 'splendor':
        from ..splendor import score, bonuses, CARDS, NOBLES, COLORS
        bonus = bonuses(state, seat)
        material = score(state, seat) * 10 + 3 * len(p['purchased']) + sum(p['tokens'].values()) + p['tokens']['gold']
        targets = [CARDS[c] for cards in state['market'].values() for c in cards] + [CARDS[c] for c in p['reserved']]
        def distance(c):
            return max(0, sum(max(0,c['cost'][k]-bonus[k]-p['tokens'][k]) for k in COLORS)-p['tokens']['gold'])
        potential = max(((c['points'] * 10 + 6)/(1+distance(c)) for c in targets), default=0)
        nobles = max((15/(1+sum(max(0,v-bonus[k]) for k,v in NOBLES[n]['required'].items())) for n in state['available_nobles']), default=0)
        return material/10, (potential+nobles - 2*len(p['reserved']))/10
    if kind == 'azul':
        from ..azul import observe
        v = observe(state, seat)['players'][seat]
        complete = sum(1 for line in v['pattern_lines'] if line['complete'])
        progress = sum(line['count']/line['capacity'] for line in v['pattern_lines'])
        floor = sum((1 if i<2 else 2 if i<5 else 3) for i in range(len(v['floor'])))
        rows = [sum(cell['occupied'] for cell in row) for row in v['wall']]
        columns = [sum(row[i]['occupied'] for row in v['wall']) for i in range(5)]
        return p['score']+2*complete+0.3*progress-floor, sum(x*x for x in rows+columns)*0.12
    if kind == 'ark_nova':
        tracks=p['tracks']; buildings=p['map'].get('buildings',[])
        material=tracks['appeal']+3*tracks['conservation']+min(p['money'],40)*0.12+len(p['played_cards'])*0.6
        position=tracks['reputation']*0.4+len(p['partner_zoos'])*1.5+len(p['universities'])*1.5
        position+=sum(c['upgraded'] for c in p['action_cards'])*2+len(buildings)*0.7+min(len(p['hand']),5)*0.25
        return material,position
    if kind == 'brass_birmingham':
        industries=[i for i in state['board']['industries'] if i.get('owner',i.get('seat'))==seat]
        material=p['vp']+min(p['money'],40)*0.08+p['income_position']*0.15+len(industries)*0.7
        links=sum(l.get('owner',l.get('seat'))==seat for l in state['board']['links'])
        position=links*1.5+sum(2 if not i.get('flipped') else 0 for i in industries)
        return material,position
    if kind == 'castles_of_burgundy':
        occupied=sum(c.get('tile_id') is not None for c in p['duchy'])
        material=p['score']+min(p['workers'],8)*0.25+min(p['silver'],8)*0.4+len(p['storage'])*0.4
        regions={}
        for c in p['duchy']:
            used,total=regions.get(c['region'],(0,0));regions[c['region']]=(used+(c.get('tile_id') is not None),total+1)
        position=occupied*0.8+sum(used*used/total for used,total in regions.values())+p['bridge']*0.2
        return material,position
    if kind == 'century_spice_road':
        from ..century_spice_road import score, POINT_CARDS
        spices=list(p['spices']); weighted=sum((i+1)*p['spices'][k] for i,k in enumerate(spices))
        material=score(state,seat)+weighted*0.15+min(len(p['hand'])+len(p['played']),8)*0.2
        potential=[]
        for key in state['point_market']:
            card=POINT_CARDS[key]
            missing=sum((i+1)*max(0,card['cost'].get(k,0)-p['spices'][k]) for i,k in enumerate(spices))
            potential.append(card['points']/(1+missing))
        return material, max(potential,default=0)+len(p['hand'])*0.15
    if kind == 'seven_wonders':
        from ..seven_wonders import score, CARDS, _military_strength
        material=score(state,seat)+min(p['coins'],12)*0.1+len(p['city'])*0.05
        production=sum(len(CARDS[c].get('production',[])) for c in p['city'])
        military=_military_strength(state,seat)
        neighbors=[(seat-1)%state['player_count'],(seat+1)%state['player_count']]
        edge=sum(math.tanh(military-_military_strength(state,n)) for n in neighbors)
        return material,production*(4-state['age'])*0.8+edge*state['age']
    if kind == 'harmonies':
        from ..harmonies import score_breakdown
        score=score_breakdown(p,state['board_side'])['total']
        occupied=sum(bool(stack) for stack in p['board'])
        # Bare trunks and mountain bases enable high-value later placements.
        bases=sum(stack in (['brown'],['brown','brown'],['gray']) for stack in p['board'])
        remaining=sum(max(0,4-c['placed']) for c in p['cards'])
        return score+occupied*0.05,bases*0.4+min(remaining,8)*0.1
    if kind == 'wingspan':
        from ..wingspan import score_breakdown
        breakdown=score_breakdown(p)
        # Bonus identities of opponents are hidden; caller evaluates root's own
        # private score only, and uses the public component for other seats.
        score=sum(v for k,v in breakdown.items() if k!='bonus_cards')
        birds=[b for habitat in p['habitats'].values() for b in habitat]
        material=score+min(sum(p['food'].values()),8)*0.3+min(len(p['hand']),5)*0.15
        position=len(birds)*(5-state['round'])*0.8
        return material,position
    if kind == 'carcassonne':
        from ..carcassonne import observe
        obs=observe(state,seat)
        potential=sum(f['points']/(1+f['open_edges']) for f in obs['features'] if seat in f['owners'])
        return p['score']+p['meeples_available']*0.15,potential
    raise ValueError(f'no evaluation for {kind}')


def value(game,state,seat,position_weight=0.0,opponent_weight=0.0):
    immediate,position=features(game,state,seat)
    result=immediate+position_weight*position
    if opponent_weight:
        others=[features(game,state,i) for i in range(state['player_count']) if i!=seat]
        result-=opponent_weight*max((a+position_weight*b for a,b in others),default=0)
    return result


def action_prior(game,state,seat,action):
    """Break material ties in staged actions without changing the rules."""
    kind=action.get('type','')
    if game.game_id=='brass_birmingham' and kind=='select_action':
        return {'sell':0.5,'build':0.4,'network':0.2,'develop':0.1,'loan':0.05,'pass':-0.5}.get(action.get('action'),0)
    # Prefer completing optional resolutions over cycling resources indefinitely.
    if kind in {'pass','skip','rest','end_turn'}:
        return -0.001
    return 0.0
