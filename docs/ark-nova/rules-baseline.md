# Ark Nova official-base implementation baseline

Status: frozen for the first high-fidelity implementation milestone.

## Scope

The target ruleset is the Ark Nova base game, English rulebook version 1.2,
combined with the official English FAQ/Errata version 2.  The implementation
must cover the base-game components and rules for one to four players.

Included:

- the five base Action cards and their upgraded sides;
- the 212 base Zoo cards (128 Animal, 64 Sponsor, 20 Conservation Project);
- 12 Base Conservation Projects, 11 Final Scoring cards, and 9 Bonus tiles;
- beginner Maps A and 0 and advanced Maps 1 through 8;
- the solo rules in the base rulebook;
- all generally applicable rulings and card clarifications in FAQ/Errata v2.

Excluded from the first rules version:

- Marine Worlds;
- Map Packs and alternative BGA maps;
- promotional cards and promotional buildings;
- later expansions or unofficial variants.

## Authoritative sources

- Feuerland/Capstone English Rulebook v1.2:
  <https://www.feuerland-spiele.de/fileadmin/game/Arche_Nova/Arche_Nova_Rules_EN_Low_2022_01.pdf>
- Feuerland English FAQ/Errata v2:
  <https://www.feuerland-spiele.de/fileadmin/game/Arche_Nova/Arche_Nova_FAQ_V2_EN_A4_low.pdf>

Before the first content release, re-check the publisher's current download page
and record whether a newer English rules or FAQ revision exists.  A newer source
must create a new named rules version; it must not silently change this baseline.

## Version identifiers

- Legacy controlled core: `base-1.2-controlled-core.6`
- Official semantic candidate: `base-1.2-faq-v2-semantic.1`
- Planned state schema: `agentbga.ark_nova.state.v3`
- Planned content schema: `agentbga.ark_nova.content.v1`

Rules, state schema, and content-pack versions are independent.  A semantic
change that alters legal actions, state transitions, or scoring requires a new
rules version and new golden replay fixtures.

## Fidelity policy

The rules engine is authoritative.  Web clients, agents, and content summaries
must not reconstruct legality or scoring independently.  Publisher prose and art
are not required for fidelity: cards are represented by stable references,
facts, typed predicates, typed effects, and project-authored short summaries.
