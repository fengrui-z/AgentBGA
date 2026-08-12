# AgentBGA

AgentBGA is a runnable headless board-game environment for studying how LLM agents plan and
act over long horizons. It is designed for both agent-vs-human and agent-vs-agent
play. Every capability is exposed through a stable, machine-readable CLI and can
also be wrapped as MCP tools.

The first supported game will be **Splendor (base game, 2–4 players)**. The engine
is intended to grow into a game-neutral framework suitable for heavier multiplayer
strategy games such as *Ark Nova* and *The Castles of Burgundy*.

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

Supported `backend` values are `openai`, `anthropic`, `gemini`, `random`, and
`human`. Player names appear in streamed turns, persisted match metadata, and final
rankings. Only the environment-variable name is persisted; its secret value is not.

Keys are read only from the environment variable named by `--api-key-env`
(default `OPENAI_API_KEY`). They are never written to SQLite, events, or output.
Model call metadata and token usage are stored without raw prompts or responses.

## Current CLI surface

```console
agentbga games list --json
agentbga games describe splendor --json

agentbga match create --game splendor --players 4 --seed 42 --json
agentbga match observe MATCH_ID --seat 0 --json
agentbga match legal-actions MATCH_ID --seat 0 --json
agentbga match act MATCH_ID --seat 0 --expected-version 7 \
  --action '{"type":"take_tokens","colors":["white","blue","green"]}' --json
agentbga match events MATCH_ID --after 0 --jsonl
agentbga match verify MATCH_ID --json
agentbga match replay MATCH_ID --json

agentbga run --players 2 --controllers openai,random \
  --model YOUR_MODEL --base-url ENDPOINT --jsonl
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

## Current status

- Splendor 2–4 player deterministic engine with exact 90-card/10-noble research data.
- Token taking/return, reservation and hidden cards, flexible gold payment, nobles,
  final round, scoring, official tie-break, and auditable pass-only-if-stuck handling.
- SQLite matches, observations, legal actions, action submission, events, replay,
  state verification, random matches, interactive human seats, and API model seats.
- Independent named seats using OpenAI-compatible, Anthropic, Gemini, random, or
  human backends, with retries and auditable fallback.

Planned next: MCP adapter, tournament scheduling/reports, stronger scripted
baselines, model-specific prompt/memory policies, and a richer human TUI.
