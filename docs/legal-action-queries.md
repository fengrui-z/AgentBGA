# Legal action queries

Splendor supports seat-local `legal_actions` filters through MCP, Minimal, Pi,
and the seat CLI. The engine still enumerates the complete legal action set;
queries select from that set without changing IDs, payment alternatives, game
rules, or submission validation. Other games retain their existing behavior.

## Splendor

Filters combine with AND:

```json
{"filters":{"type":"buy_visible","bonus":"red","max_payment":2}}
```

| Filter | Meaning |
|---|---|
| `type` | Exact action type, e.g. `take_tokens`, `buy_visible`, `buy_reserved`, `choose_noble` |
| `card_id` | Exact development card ID; never reveals a card without a matching legal action |
| `tier` | Card tier 1–3, including reserved purchases |
| `bonus` | Card bonus: white, blue, green, red, or black |
| `noble_id` | Exact noble ID in a noble-choice decision |
| `max_payment` | Maximum total tokens paid, including gold; only actions with a payment match |

`group` selects an action type and is compatible with the existing grouped-action
interface. For these filtered games, unknown groups, unsupported filter names,
invalid values, and conflicting `group`/`filters.type` fail explicitly. A valid
filter with no legal matches returns an empty page, not another seat's actions.

## When paging is necessary

A deterministic random-play sample (seeds 43–47, at most 250 decisions per game;
2 players for Splendor/Brass and 3 for 7 Wonders) reached the following raw flat
JSON sizes, before MCP's text and structured-content wrappers:

| Game | Decisions sampled | Largest list | Raw bytes |
|---|---:|---:|---:|
| Splendor | 440 | 531 actions | 68,031 |
| 7 Wonders | 271 | 48 actions | 12,636 |
| Brass: Birmingham | 1,067 | 58 actions | 12,193 |

These are sampled sizes, not theoretical maxima. Splendor take/return combinations
can exceed the CLI's observed 20,000-byte text limit even after filtering by type.
Filtering is the primary interface; paging is a lossless fallback for large groups.
No strategic pruning or preferential ordering is applied.

An unfiltered reply that fits the 16,000-byte budget remains the original complete
array. Larger defaults return `mode: "groups"`, action-type counts and
`available_filters`; use a group or filters to fetch concrete IDs. Query replies
contain `state_version`, `total` (filtered count), `actions`, and `next_cursor`.
The byte budget counts both MCP output representations and JSON escaping.
Queries return up to 50 rows (or the supplied `limit`, 1–50), shortened further
when needed to meet the byte budget. Whole action objects are preserved.

```json
{"group":"take_tokens","limit":20}
```

If `next_cursor` is non-null, call again with that cursor and the **same** filters
and group. Cursors are offsets within this decision's filtered snapshot; restart
the query after the state changes. All pages together recover every matching ID.
Use `submit_action` with one returned ID; submission still checks the complete
current legal set and rejects stale IDs and duplicate submissions.

Do not read the CLI's output files or use terminal commands to retrieve actions.
The tool is the supported route to all pages. This change does not require new
match IDs or alter replay hashes. Experiment runs that change this interface
mid-match should record that intervention instead of treating them as unchanged
baseline runs.

Seat CLI example:

```console
python -m agentbga.seat_tool --context /path/to/turn-context.json legal-actions \
  --filters '{"type":"buy_visible","bonus":"red"}' --limit 20
```
