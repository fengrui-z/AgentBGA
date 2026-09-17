# Carcassonne / 卡卡颂

Implemented as `carcassonne`, rules version `hig-base-farmers-1.0` (playable beta).
Supports 2–5 players, all 72 base tiles, seven followers per player, and modern
farmer scoring. River, Abbot, decorative gardens, expansions, and solo variants
are outside this rules version. All board graphics are original SVG geometry.

## Play

```console
./agentbga run --game carcassonne --players 2 --controllers random,random --seed 42
cd web && npm run build && cd ..
./agentbga web
```

Choose **卡卡颂 / Carcassonne** in Web setup. Human seats need no API key.
Rotate the drawn tile, click a highlighted empty space, then choose a feature
on the enlarged tile or skip the follower. Cities, roads, fields, and monasteries
have stable local IDs (`c0`, `r0`, `f0`, `m0`, etc.). Click any board tile to
inspect its connected features, followers, and current scoring value. The board
scrolls and has zoom controls. Existing match links reopen the same game.

## Rules and data references

- [Publisher's English Big Box rulebook](https://cdn.svc.asmodee.net/production-zman/uploads/2024/10/Carcassonne-Big-Box-Rulebook.pdf):
  base rules pp. 3–7, farmers p. 8, A–X base tile inventory p. 22.
- [Publisher's English supplement](https://www.hans-im-glueck.de/wp-content/uploads/2024/11/Carcassonne-v3_Supplement_EN_web.pdf):
  modern field scoring and majority ties, p. 1.

The 24 mechanical tile definitions were transcribed from the official tile list,
including separate city caps, shield locations, junction road endings, divided
fields, and field-to-city adjacency. No publisher artwork or rulebook prose is
bundled. One of the four D tiles is the starting tile and is removed before the
remaining 71 physical tiles are shuffled.

## Engine and agent protocol

The state and observations use integer coordinates: x increases east, y increases
south. `rotation` is a clockwise quarter-turn count from 0 to 3 relative to the
publisher's tile chart. Each ordinary turn has two decisions:

```json
{"type":"place_tile","x":0,"y":-1,"rotation":2}
{"type":"place_meeple","feature":"c0"}
```

The second decision may instead be `{"type":"skip_meeple"}`. Only the current
tile may receive a follower, before completion is scored. All four rotations are
enumerated, including equivalent orientations, keeping feature IDs unambiguous.
An unplaceable draw is automatically discarded and replaced for the same player.
There are at most 142 decisions in a match.

Cities and roads connect by edge; fields connect by two oriented ports per edge.
Roads and city walls split fields; a monastery road endpoint does not. Components
track distinct tile positions, shields, followers, and distinct adjacent completed
cities. This handles loops and features that reconnect through multiple segments
of one tile without counting that tile or city twice. Tied majorities receive full
points. Farmers remain deployed until final scoring; all other completed features
return their followers only after the optional follower decision. Final scores
include incomplete features, and tied totals share the winning rank.

Observations expose the entire public board and connected-feature summaries,
current face-up draw, discarded tiles, supplies, scores, and concise rules.
They exclude the seed and future deck order. Legal-action queries support `type`,
`x`, `y`, `rotation`, and `feature` filters, pagination, and stable action IDs.
The shared registry, CLI, harness, SQLite store, and replay protocol work normally.

## Validation

```console
PYTHONPATH=src python3 -m pytest tests/test_carcassonne.py tests/test_game_contract.py -q
cd web && node --test tests/carcassonne-rendered.test.mjs
```

Tests cover all 96 tile orientations and physical inventory, independent city caps
and junctions, matching every neighbor, follower restrictions, shield scoring,
majorities and ties, road loops, reconnecting segments counted once, field-side
connections, distinct-city farmer scoring, monastery diagonals, draw exhaustion,
last-tile follower scoring, hidden information, action rejection, deterministic
full matches at every supported player count, persisted replay, and a complete
human Web match with reopen. Render tests consume observations from the Python
engine and exercise both placement phases, spectator views, all tile orientations,
and finished games.
