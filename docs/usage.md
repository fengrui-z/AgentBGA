# AgentBGA usage guide

**English** · [简体中文](usage.zh-CN.md) · [Back to the README](../README.md)

Start with the [local quick start](../README.md#play-locally). This guide covers
optional configuration and inspection workflows. Run commands from the repository
root; replace model names, endpoint URLs, and environment-variable placeholders
with settings supported by your provider.

[Agents](#agents) · [Game options](#games) · [Traces](#traces) ·
[Experiments](#experiments) · [CLI](#cli) · [Troubleshooting](#troubleshooting)

<a id="agents"></a>

## Agents and authentication

Use `--players-config` for independently configured seats:

```bash
./agentbga doctor --players-config examples/multi-llm-match.json
./agentbga run --players-config examples/multi-llm-match.json --seed 42 --jsonl
```

Edit the example before running it: it contains four providers with placeholder
models and credentials. Use `api_key_env` to name an environment variable rather
than putting a secret into the JSON. Player count must fit the selected game.
`doctor` performs configuration checks; a successful check does not guarantee a
complete model-driven game. API-backed runs consume the configured provider's quota.

### Choose a backend

Each seat can use one of:

| Backend | Type | Notes |
|---|---|---|
| `openai` | Direct API | OpenAI-compatible chat completions |
| `anthropic` | Direct API | Anthropic Messages API |
| `gemini` | Direct API | Google Gemini generateContent |
| `opencode` | Harness | CLI + MCP, persistent session |
| `codex` | Harness | CLI + MCP, persistent session; API key or ChatGPT subscription auth |
| `dsh` | Harness | DeepSeek Harness, cold-start resumable headless profile |
| `hermes` | Harness | Hermes Agent + MCP, isolated home, persistent session |
| `claude` | Harness | Claude Code + MCP, persistent session |
| `pi` | Harness | Pi + native TS extension, persistent session |
| `qwen` | Harness | Qwen Code + MCP, isolated provider config, persistent session |
| `cursor` | Harness | Cursor Agent CLI + MCP, isolated data directory, persistent session |
| `grok` | Harness | xAI Grok Build CLI + MCP, isolated home and sandbox, persistent session; API key or SuperGrok subscription |
| `minimal` | Harness | Pure Python, in-process, direct LLM + 10 seat-scoped tools |
| `human` | — | Browser-based play |
| `random` | — | Random baseline |

All harness seats share a unified seat-scoped interface: `observe`, paged `legal_actions`,
`inspect_card`, `inspect_rules`, `inspect_map`, `inspect_played_cards`, `inspect_history`, `submit_action`,
`read_notes`, and `write_notes`. Ark Nova uses a compact default observation plus
state deltas; complete visible card, map, played-card, and observed-history details are
loaded only when requested. The `minimal` harness runs entirely in Python with zero
external dependencies — no CLI, no MCP server, no Node.js.

For game-specific legal-action filters and bounded responses, see
[Legal action queries](legal-action-queries.md).

### Hermes, Qwen Code, Cursor, and Grok API setup

The `hermes` backend requires the `hermes` executable with MCP support. AgentBGA creates a seat-local `HERMES_HOME`, configures only the seat-scoped `agentbga` MCP server, and routes the configured OpenAI-compatible endpoint through Hermes' custom provider.

The `qwen` backend requires the `qwen` executable. AgentBGA creates seat-local
`QWEN_HOME` and `QWEN_RUNTIME_DIR` directories, configures an OpenAI-compatible
model provider, disables ambient tools and memory, and exposes only the seat-scoped
`agentbga` MCP tools. For Alibaba Cloud Coding Plan:

```console
export BAILIAN_CODING_PLAN_API_KEY='...'
./agentbga doctor --players-config examples/qwen-code-vs-random.json
./agentbga run --players-config examples/qwen-code-vs-random.json --seed 42 --jsonl
```

The `cursor` backend requires the `cursor-agent` executable and a `CURSOR_API_KEY`.
The `grok` backend requires the xAI `grok` executable and, by default, an `XAI_API_KEY`. Both
run headlessly with persistent native sessions, disable built-in coding and web
tools, and expose only AgentBGA's seat-scoped MCP tools. Their user configuration,
credentials, and sessions remain isolated per participant workspace.

```console
export CURSOR_API_KEY='...'
export XAI_API_KEY='...'
./agentbga doctor --players-config examples/cursor-cli-vs-grok-build.json
./agentbga run --players-config examples/cursor-cli-vs-grok-build.json --seed 42 --jsonl
```

### Codex with a ChatGPT subscription

Codex can reuse the ChatGPT subscription already authenticated by the local CLI. Log in
once, select `auth_mode: "subscription"`, and omit `base_url` and `api_key_env`:

```console
codex login
./agentbga doctor --players-config examples/codex-subscription-vs-random.json
./agentbga run --players-config examples/codex-subscription-vs-random.json --seed 42 --jsonl
```

Subscription mode bridges only the active Codex credential into a seat-isolated
`CODEX_HOME`, forces ChatGPT login, and disables personal plugins, skills, shell access,
history, and memories. It does not inject `OPENAI_API_KEY` or endpoint overrides. The
default `api_key` mode keeps the existing seat-isolated usage-based API configuration.
Custom Codex API endpoints must support the Responses API (`wire_api: "responses"`).
Choose a model available to your account; the example's model is a configurable
starting point, not an entitlement check.

### Grok Build with a SuperGrok subscription

For subscription auth, install the [official CLI](https://docs.x.ai/build/overview), then:

```console
grok login
grok models
./agentbga doctor --players-config examples/grok-subscription-vs-random.json
./agentbga run --game azul --players-config examples/grok-subscription-vs-random.json --seed 42 --jsonl
```

Select **Grok Build → SuperGrok subscription** in the Web UI. This mode does not
send an API key or endpoint. JSON configurations must explicitly set
`auth_mode: "subscription"`; omitting it preserves the existing API-key behavior.
The subscription model defaults to `grok-4.6`, with the model's native reasoning
default. A JSON config can request a supported `reasoning_effort` explicitly.

Subscription mode keeps a seat-local `GROK_HOME` and the existing strict tool
sandbox. It uses the official `GROK_AUTH_PATH` override for the original login,
so Grok manages token refresh and locking without copying credentials.
`GROK_DISABLE_API_KEY_AUTH=1` prevents fallback to metered API authentication.
Personal plugins are disabled by name after read-only discovery; skill injection
and ambient compatibility integrations are disabled. Git bounds upward project
discovery to the generated seat workspace. All current seat MCP tools remain
available, including the inspection tools used by Ark Nova.

Configuration/MCP discovery was checked with Grok Build 1.0.30. `doctor` checks
the executable and local credential file, not live entitlement; subscription
limits and model availability still depend on the account. Offline tests do not
consume model quota. Missing usage/cost must not be treated as zero.

### Sessions and memory

Every harness backend assigns match memory to `(match_id, seat)`. In a learning series,
memory is instead assigned to `(series_id, participant_id)`, so a competitor keeps its
own session while seats rotate and can never inherit an opponent's private context. DSh
uses a cold-start resumable runner; session-capable external harnesses restore their
native session from the same participant workspace. Experiment runs add an internal `run_id` namespace, so
rerunning the same manifest starts with clean memory. Series execution does not add a
post-match review turn.

```json
{"backend":"dsh","model":"deepseek-v4-flash","series_id":"anneal-20","participant_id":"learner"}
```

Example harness match:

```console
export DEEPSEEK_API_KEY=...
./agentbga run --players-config examples/dsh-vs-opencode.json --seed 42 --jsonl
```

<a id="games"></a>

## Game options and play notes

Use `./agentbga games list --json` to discover registered games and
`./agentbga games describe GAME_ID --json` for their current scope, player range,
and rule versions. The [README game table](../README.md#supported-games) is the
short overview. The following notes cover games with additional setup choices.
On the browser table, review the selected move and confirm it; selecting a card,
tile, payment, or target can be an intermediate choice rather than a submitted move.

### Ark Nova

Ark Nova defaults to the released Map 0. Use `--map map-a` with `match create` or
`run` for the separately labelled Map A preview. Map 1–8 are not implemented.
The browser supports the solo human preset without an API key. Card data describes
mechanics; publisher artwork and verbatim card text are not bundled.

### Harmonies / 自然和弦

```console
./agentbga run --game harmonies --players 2 --controllers random,random --seed 42
./agentbga run --game harmonies --players 1 --controllers random --seed 42 \
  --game-config '{"board_side":"B","nature_spirits":true}'
```

In the Web setup choose **自然和弦 / Harmonies**, select A (river) or B (islands),
and optionally enable Nature's Spirits. The **Solo** preset needs no API key.
Take a token group, select a token and click a highlighted hex. Animal cards show
exact stack heights and mark the cube target; click **Settle animal** and a
highlighted target when available. Optional card/animal actions can interrupt
placements. Click **End turn** after all three tokens are placed.

Includes deterministic replay, cumulative animal scores, the equal-turn final
round, solo market refresh and sun ratings. Cards use stable numbers and original
SVG diagrams; the mechanical catalog is community-transcribed and the game is
labelled playable beta. No publisher art or expansion cards are bundled. See the
[implementation and validation plan](harmonies-implementation-plan.md).

### Wingspan / 展翅翱翔

```console
./agentbga run --game wingspan --players 2 --controllers random,random --seed 42
./agentbga run --game wingspan --players 5 --controllers random,random,random,random,random \
  --seed 42 --game-config '{"goal_board":"blue"}'
```

In Web setup choose **展翅翱翔 / Wingspan**, 2–5 human/random/model seats,
and green (competitive) or blue (individual) round goals. Select starting birds,
discard one food per kept bird, and keep one bonus card. Click habitat actions or
play a bird from your hand, then select payments and effect choices as prompted.
Bird powers and bonus conditions have Chinese and English descriptions. Name-based
bonuses use the English bird names printed in this catalog.

Includes all 170 original base birds, 26 bonus cards, eight double-sided goal tiles,
white/brown/pink powers, exact seeded replay and hidden-information observations.
No Swift-Start birds, expansions, Automa solo mode, or publisher artwork. The
community-transcribed mechanical catalog is labelled playable beta; see
[implementation and validation](wingspan-implementation-plan.md) and
[third-party notices](../THIRD_PARTY_NOTICES.md).

### Carcassonne / 卡卡颂

```console
./agentbga run --game carcassonne --players 2 --controllers random,random --seed 42
./agentbga run --game carcassonne --players-config examples/carcassonne-random-match.json --seed 42
```

In Web setup choose **卡卡颂 / Carcassonne** and 2–5 human/random/model seats.
Rotate the drawn tile, click a highlighted space, then place one follower or skip.
Click any tile to inspect its connected features; scroll or zoom the shared board.
Includes all 72 base tiles, roads, cities, shields, monasteries, farmers, majority
ties, final scoring, and deterministic persisted replay. Future draw order stays
hidden. Uses original SVG graphics; excludes River, Abbot, and other expansions.
See [rules, protocol, and validation](carcassonne.md).

<a id="traces"></a>

## Trace and audit

Harness model calls are saved as structured JSON traces. Automatic moves that
bypass the model are recorded in the game events. Human and random controllers
also use game events rather than model traces:

```console
./agentbga match traces MATCH_ID --json          # list all traces
./agentbga match traces MATCH_ID --seat 0 --turn 7  # export one turn
./agentbga match harness-events MATCH_ID --json      # tool call audit trail
```

Trace files live under `.agentbga/runs/_traces/MATCH_ID/seat-N/turn-XXXX.json` and
record prompts, the reasoning/content actually exposed by the backend, tool calls
with results, and the final submission. Private internal model reasoning may not
be available. Traces also record the participant, stable session scope, resume
count, and any DSh compaction events. Use the turn value returned by the trace list
when exporting a specific trace. Usage metrics are described in the next section.

<a id="experiments"></a>

## Experiments and result artifacts

The example manifests are templates: set accessible models, real endpoints, and
credential environment variables before a paid run. In particular, replace
`https://api.example.com/v1` wherever present. Validation checks the manifest and
schedule; it does not call the providers to verify credentials or model access.

An experiment manifest schedules one of three reproducible evaluation modes:

- `duel`: two competitors, paired seeds, and both seat orders; no cross-match memory.
- `tournament`: every configured 2-, 3-, or 4-player combination, with every cyclic
  seat rotation; no cross-match memory.
- `series`: a two-player sequence with alternating seats. One or both competitors may
  retain memory across the series; independent replicates never share memory. Replicate
  starting seats alternate for odd-length series, and generated replicate seeds occupy
  disjoint ranges while each result retains its original `base_seed`.

```console
./agentbga experiment validate --config examples/experiment-duel.json
./agentbga experiment run --config examples/experiment-duel.json \
  --out .agentbga/experiments/duel-001
```

Example manifests are provided in
[`examples/experiment-duel.json`](../examples/experiment-duel.json),
[`examples/experiment-tournament.json`](../examples/experiment-tournament.json), and
[`examples/experiment-series-one-sided.json`](../examples/experiment-series-one-sided.json).

The server-resumable 12-participant, 396-match balanced frontier tournament is
configured in [`examples/frontier12-tournament.json`](../examples/frontier12-tournament.json).
See [`docs/frontier12-server-run.zh-CN.md`](frontier12-server-run.zh-CN.md) for
credential checks, the four-match all-participant probe, 16-worker execution, and recovery.

Every run writes cumulative `agentbga.results.v1` documents atomically. `latest.json`
is refreshed after every configured batch, `results-000020.json` is an immutable
checkpoint, and `final.json` is the complete artifact. Set `results.emit_every` to `1`
for every match or to `N` for every N matches. The format is defined by
[`schemas/results-v1.schema.json`](../schemas/results-v1.schema.json).

Each completed match result also includes `harness_metrics`. For every harness seat it
records provider-reported input and output tokens, cache reads and writes, uncached input,
reasoning tokens, cache-hit rate, controller calls, failures and random fallbacks, session
resumes, compactions, and process/action latency statistics. Match-level totals use
`cached_input_tokens / input_tokens` for the cache-hit rate; reasoning tokens are a subset
of output tokens and are not counted twice. If a harness or provider does not expose exact
usage, its `token_usage.available` is `false` and `totals.complete` is `false` rather than
substituting an estimate.

Trusted upload credentials may be embedded at generation time without putting the token
in the experiment manifest:

```json
{"results":{"emit_every":20,"submission_token_env":"AGENTBGA_RESULTS_TOKEN"}}
```

The resulting file contains `submission.token`; its integrity digest deliberately covers
only the benchmark data, not the transport credential. A receiving service must validate
and discard the token before storing the artifact. This is an upload credential, not
player authentication. Never publish a result file containing `submission.token`.

<a id="cli"></a>

## CLI reference

Run these commands from the checkout with `./agentbga`. Replace `MATCH_ID` with
an existing match ID. Seats are zero-based. Read the current observation and legal
actions before submitting a move; `expected_version` must match the current state.
In the action command below, replace `VERSION` with that integer and `ACTION_ID`
with an ID returned by `legal-actions` for the same seat and state.

```console
./agentbga games list --json
./agentbga match create --game splendor --players 4 --seed 42 --json
./agentbga match create --game azul --players 2 --seed 42 --json
./agentbga match create --game castles_of_burgundy --players 2 --seed 42 --json
./agentbga match create --game seven_wonders --players 3 --seed 42 --json
./agentbga match observe MATCH_ID --seat 0 --json
./agentbga match legal-actions MATCH_ID --seat 0 --json
./agentbga match act MATCH_ID --seat 0 --expected-version VERSION \
  --action-id ACTION_ID --json
./agentbga match events MATCH_ID --jsonl
./agentbga match verify MATCH_ID --json
./agentbga match replay MATCH_ID --json
./agentbga match traces MATCH_ID --json
./agentbga experiment validate --config EXPERIMENT.json
./agentbga experiment run --config EXPERIMENT.json --out RESULTS_DIR
./agentbga web --port 8765
```

<a id="troubleshooting"></a>

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `frontend build not found` | Run `npm ci` and `npm run build` in `web/`, then start `./agentbga web` from the repository root. |
| An external harness executable is missing | Install that harness and ensure its command is on the server process's `PATH`; check the backend table above. |
| Subscription login is not found | Log in with the CLI as the same OS user that runs AgentBGA, then rerun `doctor` with your players config. |
| A model rejects requests | Check model entitlement, endpoint, API key variable, reasoning settings, and provider quota. Local login checks do not verify all of these. |
| The selected game rejects the player count | Use the range in `games describe`; 7 Wonders requires at least three seats. |
| A submitted move is stale | Refresh the observation and legal actions; submit the current version and an action from that state. |
| A model fails and a random move appears | The runner defaults to `--fallback random`; use `--fallback fail` to stop instead, and inspect failure/fallback metrics. |
| A CLI-run table cannot be paused from the browser | Watching does not take ownership of the runner. Pause controls apply to web-run matches. |

For evaluation, explicitly choose `--retries`, `--fallback`, and `--max-turns`
where needed, and report them with results. A run that reaches its turn cap may
remain unfinished. Missing usage is not zero usage.

The web server is local-only and has no participant login or seat authorization.
Keep API keys, CLI credentials, raw traces, and runtime workspaces private.
Review artifacts before publishing them. The static Pages site currently
withholds benchmark results; keep local exports outside `web/public`. See
[Web development](../web/README.md).
