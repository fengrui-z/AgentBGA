# AgentBGA live table

Static React frontend for the local AgentBGA server, with dedicated tables for all
ten [supported games](../README.md#supported-games).

For installation and human play, start with the [English README](../README.md) or
[中文 README](../README.zh-CN.md). This page covers frontend development and static
results publishing. It requires Python 3.11+ and Node.js 22.13+ with npm.

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

## GitHub Pages results

The public `/arena` route reads a sanitized Frontier12 snapshot from
`public/results/frontier12-2026-v2.json`. From the repository root, refresh it
from a tournament output:

```console
python3 scripts/publish_frontier12_pages.py \
  /path/to/frontier12-2026-v2 \
  web/public/results/frontier12-2026-v2.json \
  --report /path/to/tournament_report.html
```

Commit the updated JSON. `.github/workflows/pages.yml` rebuilds and publishes
the static site after the change reaches `main`; no runtime credentials or
machine-specific runtime metadata are included in the public snapshot.

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
