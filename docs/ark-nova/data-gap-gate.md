# Ark Nova reference-data gap gate

The reference importer writes `data_gaps.reference.json` beside the generated
content pack. The report deliberately separates two kinds of unfinished work:

- `missing_printed_parameters` means the structured source does not yet encode
  enough card-face information to compile the rule without guessing;
- `animal_compiler_backlog` means the source parameters are sufficient, but a
  shared engine subsystem or semantic dispatcher is still pending.

Collection-level counts track Sponsor effect records, Conservation Project
tiers, Final Scoring tiers, and Action-card faces independently. These counts
are authoring backlog metrics, not released-card coverage.

Normal draft imports always produce the report. A release-oriented import can
enable the blocking gate:

```sh
python -m agentbga.ark_nova_official.reference_import \
  reference-input/ark-nova-base/ark_nova_base_cards.json \
  content-packs/ark-nova/base-en-draft \
  --require-no-blocking-gaps
```

The strict command must fail until every printed parameter required by a
compiler is present. Compiler backlog may remain during development, but no
entry can advance to `released` while its effects or scenario tests are
incomplete.

Historical P0 baseline:

- 38 animal ability records lack one or more printed parameters;
- 15 animal ability records have sufficient data but await engine work;
- 77 Sponsor effect records await compilation;
- 96 Conservation Project tiers await criterion/reward compilation;
- 40 Final Scoring tiers await scoring compilation.

Current P2 progress has closed every animal parameter and compiler record.
Forty-four ability keyword families used by the base Animal deck compile, and
all 128 of 128 Animal faces now have complete ability coverage.
Pack and Petting Zoo Animal are compiled from their
official universal keyword rules rather than being misclassified as per-card
table gaps. Pilfering 1/2 now also resolves the official leading-player choice,
victim response, deterministic random hand-card transfer, and forced money/card
fallbacks. Hypnosis 3 now copies the leading opponent's eligible low-slot card,
uses that card's side, strength, Venom, and Constriction state, forbids its
Multiplier, and moves the acting player's matching Action card. Boost offers
the official slot 1/5 choice for the named Action card, while
Action abilities grant a normal extra use of the named card at its live
strength. Iconic Animal counts matching continent icons across all zoos and
caps the reward at 8; Inventive Bear counts all zoos and caps X-tokens at 3;
Inventive Primate uses the 1/3/5 icon to 1/2/3 X-token table. The strict
`--require-no-blocking-gaps` import now succeeds for Animal content. Sponsor,
Conservation Project, and Final Scoring compilation were tracked as explicit
collection backlogs for P3, P5, and P6.

P3 is complete: all 77 Sponsor effect records and all Sponsor prerequisites are
compiled. This includes fixed unique-building footprints, stored-token and
cross-action windows, terrain/map listeners, project hooks, WAZA programs, and
conditional end-game clauses. Both generated Sponsor backlog counters are zero.

P5 is complete: all 96 tiers across the 12 Base Conservation Projects and 20
Zoo Conservation Projects compile. The project backlog counter is zero; release
selectors, breeding matches, normal icon/size criteria, player-board token
rewards, two-player blocked tiers, and project-display eviction are executable.

P6 is complete: all 11 Final Scoring faces and all 40 threshold/condition
records compile and execute. The generated Final Scoring backlog counter is
zero. Therefore every compiler backlog tracked by this report is now zero.

The report is regenerated from the authoritative reference JSON. Do not edit
the generated report by hand; add the missing structured fields to the source
dataset and re-run the importer.
