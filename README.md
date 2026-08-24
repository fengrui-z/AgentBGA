# AgentBGA

A headless, deterministic board-game environment for evaluating LLM agents in long-horizon adversarial decision-making. Supports agent-vs-agent and human-vs-agent play across multiple Euro-style strategy games.

## Games

- **Splendor** (2–4 players, fully playable)
- **Azul** (2–4 players, colored-wall base game, playable beta)
- **Brass: Birmingham** (2–4 players, playable beta)
- **Century: Spice Road** (2–5 players, fully playable)
- **Ark Nova** (2–4 players, controlled core V2 — generated research cards, no publisher data)
- **7 Wonders** (3–7 players, complete Second Edition base rules, Day/Night Wonders)

## Quick start

Python 3.11+, no install required:

```console
./agentbga run --players 2 --controllers random,random --seed 42
```

LLM vs random:

```console
export OPENAI_API_KEY='...'
./agentbga run --players 2 --controllers openai,random \
  --base-url https://api.openai.com/v1 --model YOUR_MODEL --seed 42 --jsonl
```

Multi-model matches via JSON config:

```console
./agentbga run --players-config examples/multi-llm-match.json --seed 42 --jsonl
```

Local live web table:

```console
cd web && npm install && npm run build && cd ..
./agentbga web   # http://127.0.0.1:8765
```

## Harness backends

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
| `minimal` | Harness | Pure Python, in-process, direct LLM + 5 tools |
| `human` | — | Browser-based play |
| `random` | — | Random baseline |

All harness seats share a unified 5-tool interface: `observe`, `legal_actions`, `submit_action`, `read_notes`, `write_notes`. The `minimal` harness runs entirely in Python with zero external dependencies — no CLI, no MCP server, no Node.js.

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

Every harness backend assigns match memory to `(match_id, seat)`. In a learning series,
memory is instead assigned to `(series_id, participant_id)`, so a competitor keeps its
own session while seats rotate and can never inherit an opponent's private context. DSh
uses a cold-start resumable runner; the other harnesses restore their native session from
the same participant workspace. Experiment runs add an internal `run_id` namespace, so
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

## Trace & audit

Every harness turn is saved as a structured JSON trace:

```console
./agentbga match traces MATCH_ID --json          # list all traces
./agentbga match traces MATCH_ID --seat 0 --turn 7  # export one turn
./agentbga match harness-events MATCH_ID --json      # tool call audit trail
```

Trace files live under `.agentbga/runs/_traces/MATCH_ID/seat-N/turn-XXXX.json` and record the full decision sequence: prompt, assistant reasoning/content, tool calls with results, and the final submission. Traces also record the participant, stable session scope, resume count, and any DSh compaction events.

## Experiments and result artifacts

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

Runnable examples are provided in
[`examples/experiment-duel.json`](examples/experiment-duel.json),
[`examples/experiment-tournament.json`](examples/experiment-tournament.json), and
[`examples/experiment-series-one-sided.json`](examples/experiment-series-one-sided.json).

The server-resumable 12-participant, 396-match balanced frontier tournament is
configured in [`examples/frontier12-tournament.json`](examples/frontier12-tournament.json).
See [`docs/frontier12-server-run.zh-CN.md`](docs/frontier12-server-run.zh-CN.md) for
credential checks, the four-match all-participant probe, 16-worker execution, and recovery.

Every run writes cumulative `agentbga.results.v1` documents atomically. `latest.json`
is refreshed after every configured batch, `results-000020.json` is an immutable
checkpoint, and `final.json` is the complete artifact. Set `results.emit_every` to `1`
for every match or to `N` for every N matches. The format is defined by
[`schemas/results-v1.schema.json`](schemas/results-v1.schema.json).

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
and discard the token before storing the artifact.

## CLI

```console
agentbga games list --json
agentbga match create --game splendor --players 4 --seed 42 --json
agentbga match create --game azul --players 2 --seed 42 --json
agentbga match create --game seven_wonders --players 3 --seed 42 --json
agentbga match observe MATCH_ID --seat 0 --json
agentbga match legal-actions MATCH_ID --seat 0 --json
agentbga match act MATCH_ID --seat 0 --expected-version 7 \
  --action '{"type":"take_tokens","colors":["white","blue","green"]}' --json
agentbga match events MATCH_ID --jsonl
agentbga match verify MATCH_ID --json
agentbga match replay MATCH_ID --json
agentbga match traces MATCH_ID --json
agentbga experiment validate --config EXPERIMENT.json
agentbga experiment run --config EXPERIMENT.json --out RESULTS_DIR
agentbga web --port 8765
```

## Principles

- Deterministic, seeded game engines with exact replay and state verification.
- Strict per-seat observations — hidden information cannot leak.
- Simultaneous-choice games use frozen observations, parallel agent calls, and a reveal barrier.
- Event-sourced matches with SQLite persistence.
- API keys are never written to disk, events, or logs.
- Reproducible evaluation across models, harnesses, seeds, and seat order.

## Design

See [docs/architecture.md](docs/architecture.md) for architecture notes and [docs/project-overview.zh-CN.md](docs/project-overview.zh-CN.md) for a Chinese overview.

Ark Nova follows the [English Rulebook v1.2](https://www.feuerland-spiele.de/fileadmin/game/Arche_Nova/Arche_Nova_Rules_EN_Low_2022_01.pdf). Azul implements the colored-wall base game with deterministic physical tiles. No scanned card art or publisher rules text is bundled.
