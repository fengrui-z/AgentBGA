# Project introduction page

The public [GitHub Pages site](https://fengrui-z.github.io/AgentBGA/) is a project
introduction: real game tables, implemented modules, game coverage, and links to
the bilingual documentation. It does not host matches. The page lives in
`web/app/arena/`; the local application links to it from `/arena`.

## Screenshots

The four JPEGs in `web/public/showcase/` were captured from the actual local web
application on 2026-10-16, after the ten-game human-usability update. They use an
isolated demonstration database, seed 42, a human seat, and a random baseline.
No model service or paid API was used, and the images are not benchmark evidence.

| Image | What it shows | Capture size |
| --- | --- | --- |
| `splendor.jpg` | Gem bank, nobles, card tiers, player resources, and action confirmation | 1280 × 720 |
| `wingspan.jpg` | Habitat actions, a played bird, food resources, and confirmation | 1280 × 720 |
| `brass-birmingham.jpg` | Focus-map view with industries and transport connections | 1280 × 720 |
| `carcassonne.jpg` | Landscape, legal spaces, tile rotation, and connected features | 1280 × 720 |

To refresh an image, run an isolated local match, use generic player names, and
capture the real interface through the browser. Keep credentials, private logs,
and personal identifiers out of the viewport. Retain the capture dimensions or
update the corresponding image attributes. The hero shows Splendor; the other
three images share a selectable gallery without an inner scrollbar.

## Why there is no benchmark chart

The requested chart scope is **ten games, three-player matches, twelve agent
configurations**, with separate comparisons by game. No locally inspected
summary satisfied that scope as of 2026-10-16:

- The archived public `frontier12-2026-v2.json` snapshot has twelve configurations
  and 396 completed matches, but only three games and mixed player counts.
- A local analysis candidate, `pareto_ten_game.csv` (analysis snapshot
  `expanded_suite_20260921`), has 119 of the expected 120 game/configuration
  entries. Brass is missing one configuration's cost data; the historical three
  games mix player counts, and the seven newer games contain interim results.
- That analysis snapshot reports 341 of 480 planned three-player matches.
  Participant exposure in the seven newer games is uneven. Raw match/session
  records and the Elo fit were not independently validated in this review.

The introduction therefore displays implemented functionality instead of an
incomplete Pareto comparison. The historical public JSON and publishing script
remain unchanged for reproducibility; the page does not fetch them. Local
analysis files are not included in the website.

Before adding a chart, verify the underlying match population, all ten game ×
twelve configuration entries, three-player filtering for both Elo and cost,
completion and seat exposure, and comparable cost/telemetry coverage. State the
snapshot date and any limits. Keep at most one chart component with a game
selector; do not add an overall ranking across incompatible populations.

## Validate and publish

From `web/`, run `npm run lint`, `npx tsc --noEmit`, and `npm test`. The normal
build keeps the local setup at `/` and exports the introduction at `/arena.html`.
Also build with the Pages environment:

```console
NEXT_PUBLIC_BASE_PATH=/AgentBGA NEXT_PUBLIC_PAGES_RESULTS=true npm run build
```

Serve `dist/client` under `/AgentBGA/` when previewing this build. Check desktop,
wide-screen, and mobile layouts; switch all gallery images; open a full-size
screenshot; and verify the documentation links. All site assets must resolve
under the repository base path. The existing Pages workflow deploys the site
after these files reach `main`.
