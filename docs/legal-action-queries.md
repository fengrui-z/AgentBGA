# Legal action queries

Splendor, 7 Wonders and Brass: Birmingham support seat-local `legal_actions` filters through MCP, Minimal, Pi,
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

## 7 Wonders

```json
{"filters":{"type":"build_card","card_color":"green","max_left_payment":0}}
```

| Filter | Meaning |
|---|---|
| `type` | Exact action type, including `build_card`, `build_wonder`, `sell_card`, `build_discard`, and phase-specific skip actions |
| `card_id` | Exact card used by the action, including a card sacrificed to build a wonder |
| `card_color` | Card color: brown, gray, blue, yellow, red, green, or purple |
| `card_age` | Card age 1–3 |
| `stage` | One-based wonder stage, for wonder-building actions |
| `free_source` | Exact free-build reason provided by the action, e.g. `chain` |
| `max_payment` | Maximum total coins paid to the bank and both neighbors |
| `max_left_payment`, `max_right_payment` | Maximum coins paid to the specified neighbor |

Payment alternatives remain separate actions. For example, paying the left
neighbor and paying the right neighbor are not merged. Only the acting seat's
legal options are queried, including discard-building and seventh-card phases;
opponents' sealed choices and hands are not added to the result.

## Brass: Birmingham

```json
{"filters":{"type":"build_industry","industry":"brewery","location_id":"burton_on_trent","max_cost":10}}
```

```json
{"filters":{"type":"take_resource","resource":"beer","source":"industry","owner":0}}
```

| Filter | Meaning |
|---|---|
| `type` | Exact current decision type, e.g. `select_action`, `build_industry`, `take_resource` |
| `action` | Main action: pass, build, network, develop, sell, loan, or scout; matches `select_action` |
| `card_id` | Exact discarded card, or membership in a scout action's two-card discard |
| `wild_type` | Discarded wild card kind: location or industry |
| `industry` | Industry type for a build/merchant development, or membership in a development combination |
| `location_id`, `slot_id`, `tile_id` | Exact location, board slot, or tile when present on the action |
| `industry_id` | Exact industry being sold or liquidated |
| `merchant_location_id`, `merchant_slot_id` | Exact merchant destination of a sale |
| `connection_id` | Exact link connection |
| `resource` | coal, iron, or beer |
| `source`, `source_id` | Resource source kind (industry, market, merchant) and exact source ID |
| `owner` | Zero-based resource-source owner; ownerless market/merchant actions do not match |
| `max_cost` | Upper bound on the action's existing `cost` field |
| `max_estimated_market_cost` | Upper bound on a development choice's existing market estimate |

A build's `cost` is its tile's money cost; subsequent resource purchases can cost
more. A resource action's `cost` is for that source choice. Neither filter invents
a full-turn total. Actions without the corresponding cost field do not match.
Location and industry filters use fields already on each legal action; they do
not infer a source's location or a sold industry's type from unrelated state.

Multi-industry development and scout discard combinations remain whole actions,
including double development of the same industry. Queries never create remote
resource sources, illegal links, or new actions in another decision phase.

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
