# P7 — Cross-card interactions and timing

P7 audits persistent card effects, simultaneous trigger order, and Action-card
markers across the compiled standard base-game content.

## Trigger audit

- 51 compiled persistent modifiers were discovered recursively in card effects.
- 40 dynamic modifiers map to concrete engine event producers: icon entry,
  distinct icon entry, Animal play/size, building placement, project support,
  release support, and Break income.
- 11 static modifiers map to concrete legality/cost/placement consumers.
- The generated interaction audit has zero unresolved triggers or static kinds.

## Ordering and markers

- When multiple persistent effects trigger at one time, the acting player gets
  a serializable semantic choice for which effect resolves next.
- Each chosen effect retains its physical source card, modifier owner, target,
  and event bindings; later choices re-evaluate values against current state.
- Venom money is reserved before an unmarked Action card starts, remains
  reserved through after-finishing/Hypnosis/extra actions, and is refunded if a
  Venom token is removed before the complete turn ends.
- Unaffordable non-Venom Action cards are omitted from legal actions, preventing
  a human player from entering a turn that cannot be completed.
- String and structured marker representations both honor the no-duplicate
  Venom/Constriction placement rule.
- Multiplier, Constriction, Break cleanup, and interaction immunity remain
  covered by the earlier action/ability/Sponsor suites.

## Verification

Six P7 scenarios cover order-dependent results, cross-owner target preservation,
the full modifier inventory, unaffordable Venom filtering, deferred Venom
settlement through an extra action, and duplicate marker handling. The complete
official staged suite contains 132 passing tests after P7.
