# AgentBGA live table

Static React frontend for the local AgentBGA server, with dedicated tables for all
ten [supported games](../README.md#supported-games).

For installation and human play, start with the [English README](../README.md) or
[中文 README](../README.zh-CN.md). This page covers frontend development and static
project-page publishing. It requires Python 3.11+ and Node.js 22.13+ with npm.

From the repository's `web/` directory:

```console
npm ci
npm run build
cd ..
./agentbga web
```

Open `http://127.0.0.1:8765`. The setup page lists recent local matches so a
CLI table can be watched without restarting it; `?match=MATCH_ID` opens a
table directly. During development, keep `./agentbga web` running and use
`npm run dev`; `/api` is proxied to port 8765.

The production build uses `output: "export"` so the Python standard-library
server can serve `dist/client` without a Node process. This UI deliberately has
no hosted API: it accepts model credentials and therefore stays localhost-only.

## GitHub Pages project introduction

The `/arena` route introduces the project with actual game screenshots, four core
modules, the ten-game library, and links to the bilingual quick start. GitHub
Pages serves this introduction at `/AgentBGA/`; it does not run matches or ask for
credentials. The local server continues to open the live-table setup at `/`.

`.github/workflows/pages.yml` builds with `NEXT_PUBLIC_BASE_PATH=/AgentBGA` and
`NEXT_PUBLIC_PAGES_RESULTS=true` (the existing Pages-mode flag), then publishes
`dist/client` when changes reach `main`. To reproduce that build from `web/`:

```console
NEXT_PUBLIC_BASE_PATH=/AgentBGA NEXT_PUBLIC_PAGES_RESULTS=true npm run build
```

See [project-page maintenance](../docs/project-page.md) for screenshot provenance
and the benchmark-data criteria. The historical sanitized snapshot in
`public/results/frontier12-2026-v2.json` and its publishing script remain available
for reproducibility, but the introduction does not load or chart that dataset.

## Harmonies / 自然和弦

The game selector includes a dedicated Harmonies table. Choose 1–4 seats, board
A/B and optional Nature's Spirits. The Solo preset selects a human controller.
The table renders all 23 hexes, stacked tokens, cube locks, card habitat diagrams,
progress and score breakdowns. Select a pending color and a highlighted cell to
place it; select a settleable animal card and a highlighted cell to place its
cube. Card drafts and settlements can interleave with token placement. End turn
explicitly; solo replacement is available in the end-turn menu.

The renderer is `app/harmonies-table.tsx` with `app/harmonies-table.css`.
It consumes the standard match observation and authoritative legal action IDs.
Animal cards use stable numbers; no publisher artwork is required.

### Wingspan

Choose **Wingspan / 展翅翱翔** for 2–5 players and green/blue goal scoring.
The board supports initial bird selection, food/egg payments, three habitat actions,
optional powers and inter-player effect choices. Cards and bonus conditions include
Chinese and English mechanical descriptions. The renderer is
`app/wingspan-table.tsx`, styled by `app/wingspan-table.css`.
