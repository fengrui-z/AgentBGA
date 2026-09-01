# Ark Nova semantic operations v1

Status: executable contract used by the released base-game Map 0 rules version.
The historical M3 staging gate was closed by P8, and every in-scope component
has passed the source-crosswalk and runtime-scenario review in the release ledger.

## Design constraints

- Content is data only. JSON is never evaluated as Python or JavaScript.
- Predicates and effects use a closed operation vocabulary. Exceptional cards
  refer to a stable `custom_id` whose implementation must be registered in code.
- Every resolution is deterministic and serializable. A choice pauses the effect
  queue and exposes ordinary legal actions with a stable `choice_id`.
- Hidden objects are not available through general paths. Semantic references
  expose counts and public facts, not another player's card identities.
- UI descriptions are generated from facts and operations and do not reproduce
  publisher card prose.

## Value expressions

Values are JSON literals, safe references, or integer calculations.

```json
{"ref": "actor.tags.bear"}
```

```json
{"calc": "multiply", "values": [{"ref": "card.facts.continent_icons"}, 3]}
```

Allowed reference roots are `actor`, `target`, `card.facts`, `state`, and
choice `binding`. Player references expose money, X tokens, tracks, tag/icon
counts, flags, income, hand count, played-card count, project count, and worker
counts. They do not expose hidden card arrays.

## Predicates

The initial closed vocabulary is:

`all`, `any`, `not`, `compare`, `has_tag`, `has_icon`, `flag_set`,
`player_count`, `in`, and registered `custom` predicates.

Example:

```json
{
  "op": "all",
  "args": {
    "conditions": [
      {"op": "has_tag", "args": {"tag": "bear", "count": 2}},
      {
        "op": "compare",
        "args": {
          "left": {"ref": "actor.money"},
          "operator": ">=",
          "right": 6
        }
      }
    ]
  }
}
```

## Effects and timing

Effects declare one of the schema timings and a closed operation. The initial
vocabulary covers resources and tracks, Break advancement, card draw, flags,
ongoing modifiers, choices, opponent targeting, repeated effects, the ordered
Break procedure, and auditable score entries.

```json
{
  "op": "choose_one",
  "timing": "immediate",
  "args": {
    "prompt": "Choose a research benefit",
    "options": [
      {
        "id": "funding",
        "label": "Funding",
        "effects": [
          {"op": "gain_money", "timing": "immediate", "args": {"amount": 5}}
        ]
      },
      {
        "id": "reputation",
        "label": "Reputation",
        "effects": [
          {
            "op": "move_track",
            "timing": "immediate",
            "args": {"track": "reputation", "amount": 1}
          }
        ]
      }
    ]
  }
}
```

Ongoing effects are stored as modifiers with a trigger and semantic effect list.
Implemented triggers cover income, icon entry, animal play, building placement,
project support, release, and the associated cross-card modifier families.

## Action-session boundary

The five Action cards have explicit positions `1..5`. A regular action session
locks all information that cannot change during that execution:

- selected Action card and its current position;
- side I/II at action start;
- Constriction penalty;
- one X-token allocation and resulting strength per Multiplier execution;
- number of Multiplier tokens being used.

Each execution must record `performed: true`; the turn envelope refuses an
empty action. The selected card remains in its old slot until every Multiplier
execution is complete. It then moves to slot 1, relevant Action-card tokens are
removed, Venom is settled, and only then are deferred `after_finishing` effects
placed on the semantic queue.

`legal_action_starts` exposes concrete X/Multiplier allocations. The current
execution exposes a JSON-safe specification for Cards, Build, Animals,
Association, or Sponsors. Concrete card, worker, and Map 0 choices are supplied
by the action-domain resolvers and intersect their options with this
turn-envelope legality rather than duplicate strength or timing rules.

The alternative X-token action is a distinct transition: it ignores slot
strength and upgraded side, moves the selected card to slot 1, and then gains
exactly one X token. It is unavailable at the five-token cap.

## Break and scoring boundaries

The shared Break is a system-authored semantic queue in official order: hand
limit, Action-card tokens, association workers and supply, card display, income,
then Break-track reset. Hand discards use the same choice contract as cards.

End-game effects resolve before Victory Points. The track's mapping from each
Conservation space to its target Appeal value is reviewed board data supplied by
the content pack; the engine computes `appeal - target` and uses supported
Conservation Projects as the first tie-break.

The official Conservation milestones use system-only effects that content
entries cannot invoke: the Action upgrade/worker choice at 2, shared money/Bonus
tile choices at 5 and 8, and the one-time all-player Final Scoring card discard
at 10. A separate pre-scoring queue implements the rulebook fallback when no
player reaches 10 Conservation before the end of the game.
