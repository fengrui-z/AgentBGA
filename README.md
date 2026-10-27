# AgentBGA

**English** · [简体中文](README.zh-CN.md)

[Preprint](https://arxiv.org/pdf/2610.35773)

Play strategy board games against AI agents, watch agents compete, and replay their
decisions. AgentBGA combines ten deterministic game engines, a local browser table,
and a CLI for comparing models, agent harnesses, and memory strategies.

**Start here:** [Play locally](#play-locally) · [Connect an agent](#connect-an-agent) ·
[Supported games](#supported-games) · [Inspect a match](#inspect-a-match) ·
[Run experiments](#run-experiments)

## Play locally

Requires **Python 3.11+** and **Node.js 22.13+** with npm. Run these commands in a
terminal; the Python CLI works directly from the checkout without installation.

```bash
git clone https://github.com/fengrui-z/AgentBGA.git
cd AgentBGA
cd web
npm ci
npm run build
cd ..
./agentbga web
```

Open **[http://127.0.0.1:8765](http://127.0.0.1:8765)**. For your first match:

1. Choose **Splendor** with two players.
2. Set one player to **Human** and the other to **Random**. No API key is needed.
3. Start the match, select a move on the board, review it, and confirm.

The interface supports Chinese and English. The current decision and your player
summary stay close to the board; desktop layouts use the available width. Expand
player details when needed. The Agent output and Action log can be collapsed
independently. Larger maps still support their own zoom or scrolling controls.

The live table is **localhost-only** and has no multi-user authentication. Use it
on a trusted machine. Node.js is needed to build the frontend; the built table is
served by Python. Public GitHub Pages content is a static project introduction,
not a hosted game server. Benchmark results are currently withheld.

<details>
<summary><strong>Prefer the terminal? Run a match with Python only.</strong></summary>

From the repository root, run a seeded Splendor match between two random players:

```bash
./agentbga run --game splendor --players 2 --controllers random,random --seed 42
```

This needs no Node.js, API key, external agent CLI, or Python package installation.
The result includes the match ID. Add `--jsonl` to stream decisions as they happen.

</details>

## Connect an agent

Each seat has its own controller. Start with one agent against a human or random
player; then use a [players configuration](docs/usage.md#agents) to compare several
models or harnesses in the same match. Only install the external CLI you choose.

<details>
<summary><strong>Codex with a local ChatGPT subscription login</strong></summary>

With the Codex CLI installed, authenticate on the same machine that runs AgentBGA:

```bash
codex login
```

In the browser, choose **Codex → ChatGPT subscription** for the agent seat, enter
a model available to your account, and set the other seat to **Human**. Subscription
mode does not need an API key or a custom endpoint.

For a CLI match, edit the model in the example to match your account, then run:

```bash
./agentbga doctor --players-config examples/codex-subscription-vs-random.json
./agentbga run --players-config examples/codex-subscription-vs-random.json --seed 42 --jsonl
```

`doctor` checks the local executable and login; it does not prove live model access
or remaining subscription quota. See [authentication details](docs/usage.md#agents).

</details>

<details>
<summary><strong>A model API, an OpenAI-compatible endpoint, or another harness</strong></summary>

For an OpenAI-compatible Chat Completions endpoint, replace `YOUR_MODEL` with a
model your endpoint supports:

```bash
export OPENAI_API_KEY='YOUR_API_KEY'
./agentbga run --players 2 --controllers openai,random \
  --base-url https://api.openai.com/v1 --model YOUR_MODEL --seed 42 --jsonl
```

For a local model or gateway, change `--base-url` and the model ID. In the browser,
select the provider/runtime and supply its model and credentials.

Other options include Anthropic and Gemini APIs, plus OpenCode, Codex, DSh,
Hermes, Claude Code, Pi, Qwen Code, Cursor, Grok Build, and the built-in Minimal
harness. See the [backend table and configuration guide](docs/usage.md#agents).

</details>

## Supported games

All ten games have a browser table and a seeded CLI engine. “Playable beta” marks
implementations still undergoing validation; the scope below matters when comparing
results. Use the game ID with `--game`.

| Game | Game ID | Players | Implemented scope / status |
| --- | --- | --- | --- |
| Splendor | `splendor` | 2–4 | Base game; playable |
| Wingspan | `wingspan` | 2–5 | 170 base birds, 26 bonus cards, both goal boards; playable beta |
| Harmonies | `harmonies` | 1–4 | A/B boards, 32 animal cards, optional Nature's Spirits; playable beta |
| Azul | `azul` | 2–4 | Colored-wall base game; playable beta |
| Brass: Birmingham | `brass_birmingham` | 2–4 | Canal and Rail eras; playable beta |
| The Castles of Burgundy | `castles_of_burgundy` | 2–4 | 2019 base game, common no. 1 duchy; playable beta |
| Century: Spice Road | `century_spice_road` | 2–5 | Base game; playable |
| Ark Nova | `ark_nova` | 1–4 | Released base-game Map 0; Map A is an opt-in preview |
| 7 Wonders | `seven_wonders` | 3–7 | Second Edition base game, Day/Night Wonders; playable |
| Carcassonne | `carcassonne` | 2–5 | 72 base tiles with farmers; playable beta |

For solo play without a model, choose **Ark Nova** or **Harmonies** and the **Solo**
preset. 7 Wonders needs at least three players; add another human, random, or agent
seat. See [game options and play notes](docs/usage.md#games) for variants and exclusions.

## Inspect a match

Matches are saved in `.agentbga/agentbga.sqlite3` by default. Open a recent match
from the setup page, or visit `http://127.0.0.1:8765/?match=MATCH_ID`. Watching a
CLI-run match does not take over its runner; web pause controls apply to web-run
matches.

Replace `MATCH_ID` with the ID returned by a run:

```bash
./agentbga match events MATCH_ID --jsonl
./agentbga match verify MATCH_ID --json
./agentbga match replay MATCH_ID --json
./agentbga match traces MATCH_ID --json
```

Game events record accepted actions. Harness traces add prompts, tool calls,
results, and the outputs the backend actually exposes; they do not guarantee
access to a model's private reasoning. Trace files live under
`.agentbga/runs/_traces/MATCH_ID/seat-N/`. Human and random play can be inspected
through game events without model traces.

See [trace export and usage metrics](docs/usage.md#traces) for per-turn inspection.
Keep raw traces and local runtime data private when sharing results.

## Run experiments

Use **duel** for paired seeds and both seat orders, **tournament** for multi-player
comparisons, or **series** to study memory across repeated matches. Configure
models, endpoints, and credentials in an example before running it:

```bash
./agentbga experiment validate --config examples/experiment-duel.json
./agentbga experiment run --config examples/experiment-duel.json \
  --out .agentbga/experiments/duel-001
```

Validation checks the manifest; it does not test provider access. The run writes
incremental results and a final artifact, including available harness usage and
failure metrics. [Experiment modes, memory, and result files →](docs/usage.md#experiments)

## Go deeper

| If you want to… | Read |
| --- | --- |
| Configure harnesses, game variants, traces, or CLI actions | [Usage guide](docs/usage.md) |
| Query large legal-action sets efficiently | [Legal action queries](docs/legal-action-queries.md) |
| Understand the engine and evaluation design | [Architecture notes](docs/architecture.md) |
| Develop the browser table or maintain the project page | [Web development](web/README.md) |
| Run the Frontier12 batch on a server | [Server runbook (Chinese)](docs/frontier12-server-run.zh-CN.md) |
| Review human-play changes and their test coverage | [Usability audit (Chinese)](docs/human-usability-audit-2026-10-16.md) |

<details>
<summary><strong>Runtime architecture and development checks</strong></summary>

![AgentBGA runtime architecture](docs/images/agentbga-runtime-share-card.png)

The rules engine owns game state and validates actions. Agents receive seat-scoped
observations; simultaneous-choice games use frozen observations and a reveal
barrier. SQLite stores accepted actions for deterministic replay. The local web
table also exposes debugging views and is not a multi-user access-control boundary.

From the repository root:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
cd web
npm ci
npm run lint
npm test
```

The Python core has no third-party runtime dependencies. External harnesses have
their own installation requirements. See the [PR checks](.github/workflows/pr-checks.yml)
for the CI commands.

</details>

AgentBGA code is MIT-licensed. Game content is represented as mechanical data and
original graphics; publisher artwork and verbatim rules text are not bundled.
See [third-party notices](THIRD_PARTY_NOTICES.md) for content provenance and licenses.
