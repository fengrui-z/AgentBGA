"""Trusted information-set sampling for the ten default rule sets.

The policy never receives the authoritative state. Hidden zones are pooled,
canonically sorted and redealt, and future RNG is replaced. This is a memoryless
uniform belief: it deliberately does not infer opponents' policies from history.
"""
from __future__ import annotations
from copy import deepcopy
import json
import random

SUPPORTED_RULES = {
    'splendor': 'classic-1.0', 'azul': 'next-move-2018-base-colored-wall-1.0',
    'ark_nova': 'base-1.2-faq-v2-map0.1',
    'brass_birmingham': 'roxley-2018.11-playable-beta.2',
    'castles_of_burgundy': 'ravensburger-2019-base-1.0',
    'century_spice_road': 'plan-b-2017-base-1.0',
    'seven_wonders': 'second-edition-base-1.0', 'harmonies': 'libellud-2024-base-1.0',
    'wingspan': 'stonemaier-base-en-1.0', 'carcassonne': 'hig-base-farmers-1.0',
}


def redeal(zones, rng):
    """Keep zone sizes, erase both hidden ordering and hidden ownership."""
    cards = sorted((c for zone in zones for c in zone), key=lambda c: json.dumps(c, sort_keys=True))
    rng.shuffle(cards)
    offset = 0
    for zone in zones:
        size = len(zone)
        zone[:] = cards[offset:offset + size]
        offset += size


def sample_state(game, state, seat, rng):
    s = deepcopy(state)
    s['seed'] = rng.randrange(2**63)
    players = s['players']
    others = [p for p in players if p['seat'] != seat]
    kind = game.game_id
    if kind == 'splendor':
        from ..splendor import CARDS
        hidden = [c for d in s['decks'].values() for c in d] + [c for p in others for c in p['reserved']]
        reserves = []
        for tier, deck in s['decks'].items():
            pool = sorted(c for c in hidden if CARDS[c]['tier'] == int(tier))
            rng.shuffle(pool)
            size = len(deck)
            deck[:] = pool[:size]
            reserves.extend(pool[size:])
        reserves.sort()
        rng.shuffle(reserves)
        for p in others:
            n = len(p['reserved'])
            p['reserved'][:] = reserves[:n]
            del reserves[:n]
    elif kind == 'azul':
        redeal([s['bag'], s['lid']], rng)
    elif kind == 'century_spice_road':
        redeal([s['merchant_deck']], rng)
        redeal([s['point_deck']], rng)
    elif kind == 'carcassonne':
        redeal([s['deck']], rng)
    elif kind == 'harmonies':
        redeal([s['bag'], s['discarded_tokens']], rng)
        redeal([s['deck'], s['discarded_cards']], rng)
        redeal([s['spirit_deck'], *[p['spirit_choices'] for p in others]], rng)
    elif kind == 'castles_of_burgundy':
        from ..castles_of_burgundy import TILES
        for color, supply in s['tile_supply'].items():
            discarded = [c for c in s['discarded_tiles'] if TILES[c]['source'] != 'black' and TILES[c]['color'] == color]
            original = set(discarded)
            redeal([supply, discarded], rng)
            s['discarded_tiles'] = [c for c in s['discarded_tiles'] if c not in original] + discarded
        discarded = [c for c in s['discarded_tiles'] if TILES[c]['source'] == 'black']
        original = set(discarded)
        redeal([s['black_supply'], discarded], rng)
        s['discarded_tiles'] = sorted([c for c in s['discarded_tiles'] if c not in original] + discarded)
        redeal([*s['phase_goods'], s['discarded_goods']], rng)
    elif kind == 'wingspan':
        # Tucked cards and discards are represented by counts in observations.
        zones = [s['deck'], s['discard'], *[p['hand'] for p in others]]
        zones += [b['tucked'] for p in players for habitat in p['habitats'].values() for b in habitat]
        task = s['queue'][0] if s['queue'] else {}
        if not (task.get('op') == 'draft_choose' and task.get('seat') == seat):
            zones.append(s['draft'])
        redeal(zones, rng)
        redeal([s['bonus_deck'], s['bonus_discard'], *[p[k] for p in others for k in ('bonuses', 'bonus_choices')]], rng)
        s['rng'] = json.loads(json.dumps(random.Random(rng.getrandbits(64)).getstate()))
    elif kind == 'brass_birmingham':
        zones = [s['draw_deck'], *[p['hand'] for p in others]]
        hidden_discards = []
        for p in players:
            for index, card in enumerate(p['discard']):
                if card.get('face_up') is False:
                    hidden_discards.append((p['discard'], index))
        discard_zone = [{k:v for k,v in cards[i].items() if k != 'face_up'} for cards,i in hidden_discards]
        zones.append(discard_zone)
        redeal(zones, rng)
        for (cards, index), card in zip(hidden_discards, discard_zone):
            cards[index] = {**card, 'face_up': False}
    elif kind == 'ark_nova':
        # Active semantic choice belongs to the deciding player. Its bound
        # cards must remain unchanged. In setup all seats decide concurrently.
        zones = [s['zoo_deck'], s['zoo_discard']]
        zones.extend(p[k] for p in others for k in ('hand', 'initial_draw') if k in p)
        zones.extend(card['tucked_cards'] for p in players for card in p['played_cards'] if 'tucked_cards' in card)
        redeal(zones, rng)
        redeal([s['final_scoring_deck'], s['final_scoring_discard'], *[p['final_scoring_cards'] for p in others]], rng)
    elif kind == 'seven_wonders':
        _seven_wonders(s, seat, rng)
    else:
        raise ValueError(f'no information-set sampler for {kind}')
    return s


def _seven_wonders(s, seat, rng):
    from ..seven_wonders import CARDS, _deck_for_age
    # Fresh future decks: in particular, do not reveal the sampled guild set.
    for age in range(s['age'] + 1, 4):
        s['age_decks'][str(age)] = _deck_for_age(age, s['player_count'], rng)
    zones = [s['discard'], *[p['wonder_stages'] for p in s['players']]]
    zones += [h for i,h in enumerate(s['hands']) if i != seat]
    # At build-from-discard, the legal-action list legitimately reveals discard.
    if s['phase'] == 'build_from_discard':
        zones.remove(s['discard'])
    fixed = set(s['hands'][seat]) | {c for p in s['players'] for c in p['city']}
    if s['phase'] == 'build_from_discard':
        fixed.update(s['discard'])
    # Runner binds one simultaneous snapshot before any sealed submission.
    if s['pending_choices']:
        raise ValueError('sample simultaneous decisions before sealed choices are committed')
    # Keep the public per-age number of built stages; card identity is hidden.
    # Unknown guild identities are resampled even when the real game omitted them.
    for age in range(1, s['age'] + 1):
        slots = [(zone, i) for zone in zones for i,c in enumerate(zone) if CARDS[c]['age'] == age]
        normal = [c for c,v in CARDS.items() if v['age'] == age and v['color'] != 'purple'
                  and v['minimum_players'] <= s['player_count'] and c not in fixed]
        guilds = [c for c,v in CARDS.items() if v['color'] == 'purple' and c not in fixed]
        rng.shuffle(guilds)
        pool = normal
        if age == 3:
            known_guilds = sum(CARDS[c]['color'] == 'purple' for c in fixed)
            pool += guilds[:s['player_count'] + 2 - known_guilds]
        pool.sort()
        rng.shuffle(pool)
        if len(pool) != len(slots):
            raise AssertionError('inconsistent seven-wonders information set')
        for (zone,i),card in zip(slots,pool):
            zone[i] = card
    s['card_pool'] = sorted([c for d in s['age_decks'].values() for c in d]
        + [c for h in s['hands'] for c in h] + s['discard']
        + [c for p in s['players'] for k in ('city','wonder_stages') for c in p[k]])
