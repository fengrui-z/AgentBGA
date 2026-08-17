# AgentBGA

AgentBGA is a runnable headless board-game environment for studying how LLM agents plan and
act over long horizons. It is designed for both agent-vs-human and agent-vs-agent
play. Every capability is exposed through a stable, machine-readable CLI and can
also be wrapped as MCP tools.

The playable game is **Splendor (base game, 2–4 players)**. A game-plugin registry
now also exposes an **Ark Nova controlled core V2**: deterministic setup, multi-step
turns, the five action cards, upgrades, Break resolution, partner-zoo discounts,
donations, release projects, controlled effects and final objectives, seat-scoped
hidden information, persistence/replay, CLI discovery, and a dedicated web renderer.
It uses generated research cards; publisher card abilities and verified map geometry
remain deferred.

The two plugins share a small reusable mechanics kernel for structured decision
steps, stable action IDs, resource payments and transfers, hidden zones, bounded
tracks, map/network topology, rankings, and semantic events. The kernel does not
attempt to encode every board-game rule: each game still owns legality, timing,
special effects, end conditions, and scoring. See [the architecture notes](docs/architecture.md#31-reusable-mechanics-kernel).

## Project principles

- Deterministic, headless game engines with seeded randomness.
- A pure rules core: `state + action -> events + new state`.
- Strict per-seat observations so hidden information cannot leak.
- Structured actions validated against versioned JSON Schemas.
- Event-sourced matches with snapshots, verification, and exact replay.
- The CLI is the public contract; interactive UX, model adapters, and MCP are thin
  clients of the same application service.
- Reproducible evaluation across models, prompts, seeds, and seat order.

## Quick start

No install is required for a repository checkout; Python 3.11+ and the standard
library are sufficient.

```console
./agentbga run --players 2 --controllers random,random --seed 42
```

To run an LLM against a random baseline, provide an API key, endpoint, and model.
The endpoint must implement the OpenAI-compatible `POST /v1/chat/completions`
shape. If `--base-url` already ends in `/chat/completions`, it is used unchanged.

```console
export OPENAI_API_KEY='...'

./agentbga doctor \
  --base-url https://api.openai.com/v1 \
  --model YOUR_MODEL

./agentbga run \
  --players 2 \
  --controllers openai,random \
  --base-url https://api.openai.com/v1 \
  --model YOUR_MODEL \
  --seed 42 \
  --jsonl
```

For a compatible gateway or a local server:

```console
export OPENAI_API_KEY='gateway-or-local-key'
export OPENAI_BASE_URL='http://127.0.0.1:8000/v1'
export OPENAI_MODEL='your-model-name'
./examples/openai-vs-random.sh
```

### Named multi-model matches

Each seat can use an independent backend, endpoint, model, API-key environment
variable, and player name. Native adapters are included for OpenAI-compatible Chat
Completions, Anthropic Messages, and Google Gemini `generateContent`.

Copy and edit [examples/multi-llm-match.json](examples/multi-llm-match.json), then:

```console
export OPENAI_API_KEY='...'
export ANTHROPIC_API_KEY='...'
export GEMINI_API_KEY='...'
export LOCAL_LLM_API_KEY='...'

./agentbga run \
  --players-config examples/multi-llm-match.json \
  --seed 42 \
  --jsonl
```

Example configuration:

```json
{
  "schema_version": "agentbga.players.v1",
  "players": [
    {
      "name": "Model A",
      "backend": "openai",
      "model": "model-a",
      "base_url": "https://gateway-a.example/v1",
      "api_key_env": "MODEL_A_API_KEY"
    },
    {
      "name": "Model B",
      "backend": "anthropic",
      "model": "model-b",
      "base_url": "https://api.anthropic.com",
      "api_key_env": "MODEL_B_API_KEY"
    }
  ]
}
```

Supported `backend` values are `openai`, `anthropic`, `gemini`, `claude`, `pi`,
`codex`, `opencode`, `dsh`, `random`, and `human`. Player names appear in streamed turns, persisted match metadata, and final
rankings. Only the environment-variable name is persisted; its secret value is not.

Keys are read only from the environment variable named by `--api-key-env`
(default `OPENAI_API_KEY`). They are never written to SQLite, events, or output.
Model call metadata and token usage are stored without raw prompts or responses.
Model API calls use a 600-second timeout by default so slower reasoning models can
finish their turns; the live event stream sends keepalives while a model is thinking.

### Local live table

The web table lets you configure 2–4 seats with a separate backend, endpoint,
model name, API key, and display name for every seat. It streams every move live
and shows the market, bank, nobles, each agent's gems, purchased cards, reserved
cards, engine discounts, and prestige. The right-side model Chat streams each
backend's exposed reasoning/content chunks while it is deciding, with the parsed
game action kept in the action log below it. Provider-hidden chain-of-thought
cannot be displayed when an API does not return it.

Choose the **Human vs Agent** preset, or change any seat's run mode to **Human
player**, to play from the browser. At a human turn, the server publishes only
that seat's current legal actions and waits until the UI submits an action ID
for the matching seat and state version. The setup screen can move each player
up or down, randomize seats, and applies the displayed order as the turn order.

Choose **Ark Nova** on the same setup screen to run the controlled-core benchmark.
It renders the display, tracks, Association board, action-card strengths, player
resources, private-card counts, and schematic beginner maps. Human and model seats
use the same decision-step action IDs. The UI and API label it `controlled_core` so
results are not confused with the future complete commercial card-pool benchmark.

The table header includes a safe pause/resume control. A pause requested while
a model is generating lets that response finish and commits its action, then
stops before the next seat starts. The status changes from `waiting to pause`
to `paused` when that turn boundary is reached, while the live stream remains
connected. Pause state belongs to the running local server process.

The setup form includes editable presets for DeepSeek, Alibaba Cloud Model
Studio (pay-as-you-go), Zhipu AI, and MiniMax. Selecting a provider fills its
OpenAI-compatible endpoint and offers common model IDs; choosing Custom keeps
all fields editable for gateways, regional endpoints, and newly released models.

Build the static frontend once, then start the localhost-only server:

```console
cd web
npm install
npm run build
cd ..

./agentbga web
```

Open `http://127.0.0.1:8765`. API keys entered in the form stay in browser/process
memory for that match and are sent only to this local server. They are never put
in local storage, URLs, logs, SQLite rows, match events, or snapshots. The server
intentionally refuses non-localhost binds because it accepts credentials.

### Harness-vs-harness matches

Claude Code, Pi, Codex, OpenCode, and DeepSeek Harness can participate as
persistent agent harnesses instead of as single API calls. In the web setup,
choose one of these Harness presets, then enter only its Endpoint, API key, and
model name. Each seat receives its own workspace and three seat-bound tools:
`observe`, `legal_actions`, and `submit_action`. Claude Code, Codex, OpenCode,
and DeepSeek Harness consume them over MCP; Pi receives equivalent native tools
through a generated extension. A harness must submit exactly one current legal
action before its turn can advance. Its session ID is reused across turns, so
its own notes and conversation can support long-horizon plans without exposing
another seat's hidden observation. DeepSeek Harness (`dsh`) runs its one-shot
`headless` profile, so each turn is a fresh `dsh` session while the seat
workspace keeps the agent's notes across turns.

Configure API credentials in the shell, then run the included example:

```console
export DEEPSEEK_API_KEY=...
./agentbga doctor --players-config examples/codex-vs-opencode.json
./agentbga run --players-config examples/codex-vs-opencode.json --seed 42 --jsonl
```

The default web table and this example compare the same model through two
harnesses: seat 1 is OpenCode + `deepseek-v4-flash`, and seat 2 is Codex +
`deepseek-v4-flash`. Both use `https://api.deepseek.com`; only the API-key
fields need to be filled in on the web screen. A `dsh`-vs-OpenCode matchup is
available via [examples/dsh-vs-opencode.json](examples/dsh-vs-opencode.json).
AgentBGA fixes every harness at its highest reasoning setting for comparable
quality-first runs: Claude Code uses `max`, Pi maps its `xhigh` level to
provider effort `max`, Codex uses `model_reasoning_effort=max`, OpenCode runs
the generated `max` variant, and DeepSeek Harness is configured with
`reasoningEffort: max`. The requested normalized value (`reasoning_effort: max`)
is stored with each harness seat and controller-call metadata for
reproducibility.

All five Harness presets are available in the web setup screen. The corresponding
`claude`, `pi`, `codex`, `opencode`, or `dsh` executable is required. AgentBGA
starts it with its JSON event modes, records redacted harness/tool events, and
keeps API keys out of the database and emitted commands. Inspect an audit trail
with:

```console
./agentbga match harness-events MATCH_ID --json
```

Harness memory workspaces live under `.agentbga/runs/MATCH_ID/seat-N-HARNESS/`.
Authoritative turn contexts live in a separate runtime directory outside that
seat's sandbox. The MCP server is authoritative for submission; prose, direct
file writes, or a final JSON message cannot change the board by itself.

`harness-events` is an administrator/research export: tool results can contain
that seat's private observation. Harness prose/token streams remain live-only and
are not persisted; API keys are redacted before any harness output is emitted.

Every harness turn is also written as an ordered trace JSON file under
`.agentbga/runs/MATCH_ID/_traces/seat-N/turn-XXXX.json`. Each file records the
full decision sequence for that seat and state version: the `prompt` block
(`user` message, `observation`, `legal_actions`), an ordered `steps` array
(`assistant` content/reasoning chunks and `tool_call` entries with their
`result`), the final `submission`, `latency_ms`, `session_id`, and `status`
(`ok` / `error` / `no_submit`). Assistant prose is captured from the harness's
streamed JSON output and redacted; tool results come from the authoritative
seat-tool audit log. List trace files or export one turn with:

```console
./agentbga match traces MATCH_ID --json
./agentbga match traces MATCH_ID --seat 0 --turn 7
```

For frontend development, run `./agentbga web` in one terminal and `npm run dev`
inside `web/` in another, then open `http://127.0.0.1:3000`.

## Current CLI surface

```console
agentbga games list --json
agentbga games describe splendor --json
agentbga games describe ark_nova --json

agentbga match create --game splendor --players 4 --seed 42 --json
agentbga match create --game ark_nova --players 2 --seed 42 --json
agentbga match create --game ark_nova --players 2 --seed 42 \
  --game-config '{"turn_limit":60}' --json
agentbga match observe MATCH_ID --seat 0 --json
agentbga match legal-actions MATCH_ID --seat 0 --json
agentbga match act MATCH_ID --seat 0 --expected-version 7 \
  --action '{"type":"take_tokens","colors":["white","blue","green"]}' --json
agentbga match events MATCH_ID --after 0 --jsonl
agentbga match verify MATCH_ID --json
agentbga match replay MATCH_ID --json
agentbga match harness-events MATCH_ID --json
agentbga match traces MATCH_ID --json
agentbga match traces MATCH_ID --seat 0 --turn 7

agentbga run --players 2 --controllers openai,random \
  --model YOUR_MODEL --base-url ENDPOINT --jsonl

agentbga web --port 8765
```

The repository-local form is `./agentbga ...`. All non-interactive commands emit
versioned JSON by default; `--json` is accepted for explicitness and `--jsonl`
streams one event per line during a run.

Human players can use the same `observe`, `legal-actions`, `act`, and `watch`
commands directly. A later TUI may improve ergonomics, but it must not introduce
capabilities that are absent from the non-interactive CLI.

## Design

See [docs/architecture.md](docs/architecture.md) for the proposed architecture,
protocols, Splendor MVP scope, evaluation plan, and implementation milestones.
The Ark Nova setup implementation follows the official
[English Rulebook v1.2](https://www.feuerland-spiele.de/fileadmin/game/Arche_Nova/Arche_Nova_Rules_EN_Low_2022_01.pdf)
and tracks the official
[FAQ/Errata v2](https://www.feuerland-spiele.de/fileadmin/game/Arche_Nova/Arche_Nova_FAQ_V2_EN_A4_low.pdf)
for future interaction tests. No scanned card art or publisher rules text is bundled.

## Current status

- Splendor 2–4 player deterministic engine with exact 90-card/10-noble research data.
- Token taking/return, reservation and hidden cards, flexible gold payment, nobles,
  final round, scoring, official tie-break, and auditable pass-only-if-stuck handling.
- SQLite matches, observations, legal actions, action submission, events, replay,
  state verification, random matches, interactive human seats, and API model seats.
- Independent named seats using OpenAI-compatible, Anthropic, Gemini, random, or
  human backends, with retries and auditable fallback.
- Local live table for per-seat model configuration and real-time visual matches.
- GamePlugin/GameRegistry boundary used by Store, Runner, CLI, harness prompts, web API,
  and per-game React renderers.
- Ark Nova 2–4 player controlled core V2 with initial-hand selection, all five action
  state machines, action-card strength movement and upgrades, X tokens, Break resolution,
  partner-zoo discounts, donations, animal release, controlled effect primitives,
  generated final objectives, Map A schematic, hidden information, replay, and UI.

Planned next for Ark Nova: legally distributable verified card data, verified map
footprints, the published appeal/conservation scoring geometry, full enclosure
conditions and special-enclosure occupancy, interactive/after-finishing card timing,
and per-card FAQ interaction coverage.
Framework work continues with tournament scheduling/reports and stronger baselines.
