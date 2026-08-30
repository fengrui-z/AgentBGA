# AgentBGA live table

Static React frontend for the local multi-game AgentBGA server. It renders dedicated
tables for Splendor, Azul, Ark Nova, Brass: Birmingham, Century: Spice Road,
and 7 Wonders.

```console
npm install
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
