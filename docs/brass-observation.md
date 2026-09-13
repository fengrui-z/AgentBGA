# Brass agent observation

Brass uses a compact seat observation plus bounded `inspect` resources in MCP,
Minimal, Pi and the seat CLI. The engine's full observation, Web projections,
legal actions and submission rules are unchanged. This interface changes what an
agent sees by default; record the interface version when comparing experiments.

## Default observation

`observe({})` returns `schema_version: agentbga.brass-observation.v1` and the
current decision's `state_version`. It retains the phase, era, round, action
budget, turn order, markets, merchants, each player's economy, wildcard counts,
and the viewer's complete hand.

Repeated industry definitions are replaced by per-player tables containing every
industry type, remaining count and next level. Full tile costs, development
restrictions and later levels are inspectable. Discards and removed tiles have
counts and inspection references. Opponent hands remain hidden.

The public board overview contains all built industries and links. Tables use
explicit `columns` with matching `rows` to avoid repeating field names on every
piece. Industries include identity, type, level, owner, location, slot, resources,
flipped status, VP, link icons and beer required to sell. Full tile properties,
city slots and connection definitions have detail references. The overview does
not select only the acting player's neighborhood.

Both default observations and inspection pages must fit 16,000 UTF-8 bytes,
measured across MCP's text and structured-content representations. If a dense
board makes the overview exceed the budget, `board.deferred` is explicitly true
and `board.inspect_ref` points to the complete global overview. Read that overview
before choosing an action. No rows are silently truncated. An unsupported
oversized scalar or an oversized mandatory summary fails explicitly.

## Detail queries

References identify data in a prepared, seat-visible snapshot, not filesystem
paths. Follow references returned by the tools instead of inventing deeper paths.
For example:

```json
{"ref":"observation/players/0/industry_stacks","state_version":123}
```

```json
{"ref":"observation/board/connection_spaces","state_version":123}
```

`inspect({})` opens the complete source observation, using an index when large.
All fields of that source observation can be recovered through its entries and
references. The response has one of these shapes:

- `mode: value`: `value` is the complete requested value, including small arrays
  and objects.
- `mode: object`: each entry has a `key` and either a complete `value` or an
  `inspect_ref` for that child.
- `mode: array`: each entry has an `index` and either a complete `value` or an
  `inspect_ref` for that child. Indices preserve the original ordering.

For object/array pages, a non-null `next_cursor` means more entries remain:

```json
{"ref":"observation/board/industries","cursor":"<returned next_cursor>"}
```

Keep the same `ref`. Cursors are opaque and bind the reference, match, seat,
version and source snapshot. Reusing one after a decision change or for another
reference raises an error. Optional `state_version` detects a stale inspection
before reading. Each page contains up to 20 entries, reduced as needed by the
byte budget. A large child becomes an explicit reference, never a partial value.

Seat CLI:

```console
python -m agentbga.seat_tool --context /path/to/turn-context.json inspect \
  --ref observation/players/0/industry_stacks --state-version 123
```

## Implementation and extension

`agent_view/brass.py` owns the semantic overview and useful resource aliases.
`agent_view/resources.py` owns byte-bounded document decomposition, lossless
pages, references and cursor validation. The adapter registry in
`agent_view/__init__.py` selects the projection by game ID. Both inputs come from
the existing seat-safe observation boundary; the layer never receives raw state
or reads a match database.

Pages are prepared once per decision and stored in the seat context. Python and
Pi serve identical prepared pages instead of implementing independent projection
logic. Other games retain their existing observation paths; Ark Nova is not
migrated in this change. The generic inspection tool reports an unavailable
reference when a game has no registered view resources.

## Validation

At seed 43, measuring opening observations with both MCP representations gives
approximately 95 KB to 9 KB for two players and 163 KB to 12.5 KB for four players.
These are opening examples, not theoretical maxima. Tests cover 2–4 players,
complete reconstruction of the original visible observation, hidden card
isolation, real decisions, a deliberately oversized board, stale/cross-reference
cursors, unchanged action IDs, accepted submission, and MCP/Minimal/Pi/CLI parity.
