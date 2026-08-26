# M3 action sessions and Conservation milestones

Historical milestone snapshot. P1–P8 subsequently completed the resolver,
content, setup, privacy, Web, solo, and release-gate work described below.

Implemented on `codex/ark-nova-official-base`:

- explicit Action-card slots 1 through 5 and validated turn/action-session
  state;
- concrete legal action-start candidates with independent X-token allocation
  for each Multiplier execution;
- strength and upgraded-side locking at action start;
- Constriction strength reduction, Venom removal/payment, Multiplier use, and
  Break cleanup compatibility;
- the rule that all Multiplier executions finish before the selected Action
  card moves to slot 1 and before `after_finishing` effects resolve;
- the alternative action that selects and moves an Action card and gains one
  X token, including the five-token cap;
- the printed Cards I/II draw/discard tables, snap thresholds, Animals card
  counts, Build limits, Association task costs, and Sponsors level/Break
  envelopes as JSON-safe execution specifications;
- official Conservation choices at 2, 5, 8, and 10, including shared Bonus
  tile consumption and serializable Final Scoring card choices;
- the mandatory pre-scoring Final Scoring discard when nobody reached 10
  Conservation;
- action-session and milestone scenario tests covering movement timing,
  strength locking, token removal, deferred effects, shared bonuses, and
  player-order discard windows.

Authoritative rule references used for M3:

- current Capstone English rulebook download:
  <https://capstone-games.com/cdn/shop/files/Ark-Nova-Rulebook.pdf>;
- current Capstone/Feuerland glossary download:
  <https://cdn.shopify.com/s/files/1/0947/3907/1278/files/Ark-Nova-Glossary.pdf>;
- official Feuerland symbol overview used to verify printed side-I tables:
  <https://www.feuerland-spiele.de/fileadmin/game/Arche_Nova/Symbol-UEbersicht.pdf>.

The next implementation stage at the time was to add concrete multi-step
resolvers beneath the M3 envelope (completed in P1–P5):

- Cards draw/snap selection, discard, display gaps, and end-of-turn refill;
- exact zoo-map geometry, adjacency, building placement, placement bonuses,
  kiosks, pavilions, and special enclosures;
- Animals selection, prerequisites, costs/discounts, enclosure occupation,
  immediate abilities, and display acquisition;
- Association worker assignment, partner zoos, universities, projects,
  donations, and upgraded multi-task ordering;
- Sponsors play/break branches, multiple-card budgeting, display cost, unique
  building placement, and per-card immediate/ongoing effects.

P8 replaced staged setup, added private/spectator observations, and supplied
full-match replay and invariant tests. The official candidate is now the default;
the legacy `base-1.2-controlled-core.6` remains selectable for replay.
