# Ark Nova M4/M5 implementation status

Historical M4/M5 snapshot, superseded by the Map 0 release on 2026-08-28.

## Delivered in this stage

- A validated `ark-nova-base-en-draft-roster` content pack reserves the exact
  base-game inventory used by the project: 128 animals, 64 sponsors, 20 zoo
  conservation projects, 12 base conservation projects, 11 final-scoring
  cards, 9 bonus tiles, and 10 maps.
- 235 animal, sponsor, project, and final-scoring entries now contain imported
  structured facts from the local 255-card reference. Five Action-card faces,
  47 ability keywords, and all 255 physical copies are retained as auxiliary
  authoring indexes; none is executable until its DSL compilation is reviewed.
- The content schema now permits a null component identifier and deferred
  project levels only for `unentered` authoring slots. Any later review state
  requires a concrete identifier; project semantics also require executable
  levels.
- The semantic audit reports collection counts, review-state counts, roster
  coverage, executable-entry coverage, and scenario coverage.
- A deterministic UI catalog export is generated from the validated pack. The
  Web client does not maintain a second hand-authored interpretation.
- The Web setup and match views now expose an Ark Nova rules workbench with
  collection filtering, roster search, structured traits, five semantic stages,
  review maturity, content hash, and the M3 action-session grammar.
- The match view now projects a complete mechanics-first table: public tracks,
  six-card display, bonus bank, association stock and workers, base projects,
  donation spaces, one 58-cell Map 0 surface per player, and compact public
  summaries. It uses text, symbols, and original CSS rather than publisher art.
- The Map 0 surface uses the supplied flat-top axial transcription: 39 buildable
  cells, 10 water cells, 9 rock cells, 12 placement bonuses, two Build II cells,
  and no starter buildings. Fixed polyhex rotations and Build II legality are
  enforced by the engine, including the first-building border rule and later
  building adjacency; card-taking and Clever bonuses are explicit decisions.
- Every controlled-core human decision is placed on its corresponding table
  component. This includes initial-hand selection, action-card strength and X
  spending, drawing and snapping, hand discard, sponsor play, map building and
  animal placement, association tasks and donation, conservation rewards, final
  card choice, and optional action completion. Controls submit engine-issued
  action IDs and do not duplicate legality in the browser.
- A selected action can be cancelled before any concrete effect resolves. The
  engine restores spent X tokens (and the Cards action's provisional Break
  movement), so an unavailable card or task never traps a human turn.
- Each player's two final-scoring cards have a dedicated private area and the
  10-conservation keep-one decision is rendered on those cards. Played animal
  and sponsor cards are separated into two public rows beneath the zoo map.
- The reputation university now grants one research icon and two reputation;
  all three universities contribute their printed research icon to the public
  counter. Building rotations preserve an anchor that belongs to the physical
  polyhex, eliminating dropped border placements.
- The Ark Nova surfaces adapt to narrow screens with scrollable tracks, card
  rows, and action slots instead of imposing a fixed desktop-width board.
- Cards and Sponsors decisions now resolve directly between the player's action
  rack and fixed-width hand. Animals are selected on their card before a legal
  enclosure is highlighted, and Break discards state both the surplus and the
  resulting hand limit.
- Appeal and Conservation share one opposing score axis. Every Appeal space
  exposes its printed Break income, while Conservation 0 starts at the opposite
  endpoint and advances by two, then three, score-axis spaces per point.
- Break resolution recalls the actual number of committed association workers
  and replenishes each partner zoo and university for players who do not yet
  own it. The Web stock distinguishes permanent owners from current-round
  availability.

## M5 acceptance status

M5 Web refactoring is complete for the runnable controlled-core rules version.
The semantic workbench and live table consume validated server projections,
preserve hidden information, expose keyboard focus for interactive components,
and keep generic fallback action controls out of the Ark Nova table flow.

Historical M4/M5 snapshot: P1–P8 subsequently completed the dispatcher,
project, final-scoring, interaction, setup, and complete-match gates described
as remaining below. This status did not itself promote the draft roster.
High-fidelity official-base card semantics remain gated by the review process
described below.

## Superseding release

The former draft boundary is closed for the intentionally limited Map 0 mode.
`base-1.2-faq-v2-map0.1` loads the released 245-entry content package: 235 card
faces, nine reward tiles, and Map 0. Every entry records a source-crosswalk
review process and a separate executable scenario review process. See
`p8-release-gate.md` and `release-baseline-results.json` for the current gate and
one-to-four-player completion evidence. Map A and Maps 1–8 remain outside this
version instead of appearing as unentered release slots.
