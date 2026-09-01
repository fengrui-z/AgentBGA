# Ark Nova base-game Map 0 rules conformance

This is the release traceability record for rules version
`base-1.2-faq-v2-map0.1`. The scope is the base game for one to four players on
Map 0. It does not claim Map A, Maps 1–8, Marine Worlds, promotional cards, or
publisher presentation assets.

## Authorities

The review used the publisher-hosted 20-page rulebook, eight-page glossary, and
three-page FAQ v2. Their URLs, retrieval date, page counts, and SHA-256 hashes
are fixed in `rules-conformance.json`. The repository does not redistribute
these copyrighted PDFs.

## Result

All 27 rule domains in the machine-readable matrix are `pass`, with at least
one implementation path and one executable test for every domain. They cover:

- components, physical card zones, setup, hidden information, two-player
  blocking, and the exact Map 0 footprint;
- the action-card cycle, X tokens, Cards, Build, Animals, Association, Sponsors,
  projects, unique buildings, and polyhex placement;
- glossary semantics such as self-counting and double icons, terrain icons,
  release/breeding, special enclosures, interaction tokens, multiplier timing,
  and simultaneous-effect order;
- the Break procedure, track milestones, FAQ v2 restrictions, end trigger,
  final turns, final scoring, and solo play;
- complete content coverage and Web/private-state projections.

This matrix is enforced by the P8 release test. It verifies that every listed
source digest is well formed, every rule is marked `pass`, every implementation
file exists, every named test exists, the expected official sources are present,
and the matrix is bound to the runtime rules version.

## Content evidence

Rules conformance complements, rather than replaces, the content review:

- 235 distinct base-game card faces passed the independent source crosswalk;
- those 235 faces, nine reward tiles, and Map 0 each have a unique executable
  runtime scenario (245 total);
- the four-player physical inventory contains the documented 255 cards after
  counting repeated physical Zoo cards and five Action cards per seat;
- deterministic random baselines finish for one, two, three, and four players
  while validating state after every accepted action.

The content ledger is
`content-packs/ark-nova/base-en-draft/release-review-ledger.json`; random-game
evidence is `docs/ark-nova/release-baseline-results.json`.
