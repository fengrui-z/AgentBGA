# P6 — Final Scoring cards

P6 compiles and executes every Final Scoring card in the standard base game.

## Coverage

- 11/11 unique Final Scoring faces compile to closed, JSON-safe scoring rules.
- 40/40 supplied tier/condition records have no compiler backlog.
- Nine threshold cards use named metrics and exact printed thresholds.
- Architectural Zoo evaluates its four Map 0 conditions independently.
- Diverse Species Zoo compares all seven animal categories with the modeled
  right-hand neighbor, caps the award at four conservation, and is discarded
  and replaced when drawn in a solo game.
- Final-card conservation is awarded before the final appeal/conservation
  distance is calculated and is recorded in both events and score entries.

## Verification

- Exhaustive threshold tests reach every tier of all nine threshold cards.
- Dedicated tests cover all four Architectural Zoo conditions, category ties,
  the four-point diversity cap, solo replacement, and score-pipeline ordering.
- The official staged suite contains 126 passing tests after P6.
- The imported reference audit reports zero uncompiled animal abilities,
  Sponsor effects/requirements, project tiers, and Final Scoring tiers.

The content remains mechanics-first: names identify components, while the UI
uses project-authored summaries and structured facts rather than publisher art
or copied card prose.
