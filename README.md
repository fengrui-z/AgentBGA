# AgentBGA

A headless, deterministic board-game environment for evaluating LLM agents in long-horizon adversarial decision-making. Supports agent-vs-agent and human-vs-agent play across multiple Euro-style strategy games.

## Games

- **Splendor** (2–4 players, fully playable)
- **Azul** (2–4 players, colored-wall base game, playable beta)
- **Brass: Birmingham** (2–4 players, playable beta)
- **Century: Spice Road** (2–5 players, fully playable)
- **Ark Nova** (2–4 players, controlled core V2 — generated research cards, no publisher data)

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
| `codex` | Harness | CLI + MCP, persistent session |
| `dsh` | Harness | DeepSeek Harness, headless profile |
| `hermes` | Harness | Hermes Agent + MCP, isolated home, persistent session |
| `claude` | Harness | Claude Code + MCP, persistent session |
| `pi` | Harness | Pi + native TS extension, persistent session |
| `minimal` | Harness | Pure Python, in-process, direct LLM + 5 tools |
| `human` | — | Browser-based play |
| `random` | — | Random baseline |

All harness seats share a unified 5-tool interface: `observe`, `legal_actions`, `submit_action`, `read_notes`, `write_notes`. The `minimal` harness runs entirely in Python with zero external dependencies — no CLI, no MCP server, no Node.js.

The `hermes` backend requires the `hermes` executable with MCP support. AgentBGA creates a seat-local `HERMES_HOME`, configures only the seat-scoped `agentbga` MCP server, and routes the configured OpenAI-compatible endpoint through Hermes' custom provider.

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

Trace files live under `.agentbga/runs/MATCH_ID/_traces/seat-N/turn-XXXX.json` and record the full decision sequence: prompt, assistant reasoning/content, tool calls with results, and the final submission.

## CLI

```console
agentbga games list --json
agentbga match create --game splendor --players 4 --seed 42 --json
agentbga match create --game azul --players 2 --seed 42 --json
agentbga match observe MATCH_ID --seat 0 --json
agentbga match legal-actions MATCH_ID --seat 0 --json
agentbga match act MATCH_ID --seat 0 --expected-version 7 \
  --action '{"type":"take_tokens","colors":["white","blue","green"]}' --json
agentbga match events MATCH_ID --jsonl
agentbga match verify MATCH_ID --json
agentbga match replay MATCH_ID --json
agentbga match traces MATCH_ID --json
agentbga web --port 8765
```

## Principles

- Deterministic, seeded game engines with exact replay and state verification.
- Strict per-seat observations — hidden information cannot leak.
- Event-sourced matches with SQLite persistence.
- API keys are never written to disk, events, or logs.
- Reproducible evaluation across models, harnesses, seeds, and seat order.

## Design

See [docs/architecture.md](docs/architecture.md) for architecture notes and [docs/project-overview.zh-CN.md](docs/project-overview.zh-CN.md) for a Chinese overview.

Ark Nova follows the [English Rulebook v1.2](https://www.feuerland-spiele.de/fileadmin/game/Arche_Nova/Arche_Nova_Rules_EN_Low_2022_01.pdf). Azul implements the colored-wall base game with deterministic physical tiles. No scanned card art or publisher rules text is bundled.
