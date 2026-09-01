# Ark Nova official-base implementation baseline

Status: released for the high-fidelity base-game Map 0 mode.

## Scope

The target ruleset is the Ark Nova base game, English rulebook version 1.2,
combined with the official English FAQ/Errata version 2.  The implementation
must cover the base-game components and rules for one to four players when all
players use Map 0.

Included:

- the five base Action cards and their upgraded sides;
- the 212 base Zoo cards (128 Animal, 64 Sponsor, 20 Conservation Project);
- 12 Base Conservation Projects, 11 Final Scoring cards, and 9 Bonus tiles;
- beginner Map 0, including its exact footprint, terrain, placement bonuses,
  Build-II spaces, empty setup, and end-game map-cover bonus;
- the solo rules in the base rulebook;
- all generally applicable rulings and card clarifications in FAQ/Errata v2.

Excluded from the first rules version:

- Marine Worlds;
- Map Packs and alternative BGA maps;
- promotional cards and promotional buildings;
- later expansions or unofficial variants.
- beginner Map A and Maps 1 through 8 (these require separately versioned map
  geometry and player-board abilities and are not claimed by this release).

## Authoritative sources

- Capstone English Rulebook v1.2:
  <https://capstone-games.com/cdn/shop/files/Ark-Nova-Rulebook.pdf>
- Capstone English Glossary:
  <https://cdn.shopify.com/s/files/1/0947/3907/1278/files/Ark-Nova-Glossary.pdf>
- Capstone English FAQ/Errata v2:
  <https://cdn.shopify.com/s/files/1/0947/3907/1278/files/Ark-Nova-FAQ-v2.pdf>

These downloads were re-checked on 2026-08-28. A newer source must create a new
named rules version; it must not silently change this baseline.

## Version identifiers

- Legacy controlled core: `base-1.2-controlled-core.6`
- Released Map 0 rules: `base-1.2-faq-v2-map0.1`
- Planned state schema: `agentbga.ark_nova.state.v3`
- Content entry schema: `agentbga.ark_nova.card.v1`

Rules, state schema, and content-pack versions are independent.  A semantic
change that alters legal actions, state transitions, or scoring requires a new
rules version and new golden replay fixtures.

## Fidelity policy

The rules engine is authoritative.  Web clients, agents, and content summaries
must not reconstruct legality or scoring independently.  Publisher prose and art
are not required for fidelity: cards are represented by stable references,
facts, typed predicates, typed effects, and project-authored short summaries.
