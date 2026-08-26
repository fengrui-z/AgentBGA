# M2 semantic rules engine status

Historical milestone snapshot. M3 action-session and Conservation milestone
work is documented in `m3-status.md` and supersedes the corresponding gaps
below.

Implemented on `codex/ark-nova-official-base`:

- safe literals, references, integer calculations, and closed predicates;
- an auditable effect vocabulary with code-registered exceptional handlers;
- serializable effect queues, nested choices, opponent targeting, and stable
  legal choice actions;
- play-time entry requirements, derived tag/icon counts, immediate effects,
  ongoing modifiers, generic named triggers, and interaction effects;
- data-driven track milestones that interrupt and resume the original effect;
- Conservation Project level eligibility, exclusive claims, map-token bonus
  ordering, rewards, and player-count display eviction;
- the ordered six-step multiplayer Break, including hand-limit choices,
  Action-card token cleanup, workers, display refresh, sequential income, and
  recurring income triggers;
- boundary-aware endgame triggering, end-game card effects, scoring-area target
  lookup, Victory Point distance, and supported-project tie-break;
- Chinese/English mechanics summaries generated from semantic data;
- a content-pack audit that rejects unknown, unregistered, malformed, or
  system-only operations.

The following was the historical backlog before P1–P8 (now closed for Map 0):

- concrete Cards/Build/Animals/Association/Sponsors multi-step domain resolvers
  beneath the completed M3 turn envelope;
- reviewed maps, footprints, enclosure placement, animal accommodation, special
  enclosures, and Release into the Wild enclosure selection;
- reviewed Bonus tile entries for the completed 5/8 Conservation choice flow;
- exact reviewed track/scoring-area data and the solo six-round procedure;
- all reviewed base content entries and exceptional card handlers;
- seat-safe observations for semantic choice windows and the dedicated Web UI;
- golden replays, randomized invariants, and one-to-four-player completion tests.

P8 registered `base-1.2-faq-v2-semantic.1` as the default candidate. The legacy
`base-1.2-controlled-core.6` remains registered only for exact replay.
