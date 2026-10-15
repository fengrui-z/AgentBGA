# Project introduction page

The public [GitHub Pages site](https://fengrui-z.github.io/AgentBGA/) is a project
introduction: real game tables, implemented modules, game coverage, and links to
the bilingual documentation. It does not host matches. The page lives in
`web/app/arena/`; the local application links to it from `/arena`.

## Screenshots

The ten JPEGs in `web/public/showcase/` were captured from the actual local web
application on 2026-10-16, after the ten-game human-usability update. They use an
isolated demonstration database, seed 42, a human seat, and random opponents (three players for 7 Wonders; two for the
other games).
No model service or paid API was used, and the images are not benchmark evidence.

| Image | What it shows | Capture size |
| --- | --- | --- |
| `splendor.jpg` | Gem bank, nobles, card tiers, player resources, and action confirmation | 1280 × 720 |
| `wingspan.jpg` | Habitat actions, a played bird, food resources, and confirmation | 1280 × 720 |
| `brass-birmingham.jpg` | Focus-map view with industries and transport connections | 1280 × 720 |
| `carcassonne.jpg` | Landscape, legal spaces, tile rotation, and connected features | 1280 × 720 |
| `harmonies.jpg` | Hex landscape, stacked tokens, token market, and animal habitats | 1280 × 720 |
| `azul.jpg` | Factory and center tiles, pattern lines, and a selected move preview | 1280 × 720 |
| `castles-of-burgundy.jpg` | Dice, tile depots, resources, and the duchy board | 1280 × 720 |
| `century-spice-road.jpg` | Order cards, merchant market, spice costs, and acquisition options | 1280 × 720 |
| `ark-nova.jpg` | Zoo map, enclosures, association workers, partner zoos, and universities | 1280 × 720 |
| `seven-wonders.jpg` | Three-player drafting, Wonders, resources, hand cards, and build options | 1280 × 720 |

To refresh an image, run an isolated local match, use generic player names, and
capture the real interface through the browser. Keep credentials, private logs,
and personal identifiers out of the viewport. Retain the capture dimensions or
update the corresponding image attributes. The hero cycles through all ten games
in a cover-flow carousel, starting with Splendor. Previous/next buttons wrap at
both ends; the ten labeled dots jump directly to a game. The arrow buttons also
accept Left/Right keys, and horizontal pointer drags or touch swipes change slides.
Vertical touch scrolling remains available. Dragging does not open an image;
clicking the active board opens the full-size capture. No automatic rotation is
used, and reduced-motion preferences disable the slide animation. The separate
Wingspan/Brass/Carcassonne detail gallery remains available below the hero.

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
wide-screen, and mobile layouts; navigate all ten hero slides in both directions,
including wraparound and direct selection; check keyboard navigation, horizontal
dragging versus vertical scrolling, and full-size image links; switch the detail
gallery; and verify the documentation links. All site assets must resolve
under the repository base path. The existing Pages workflow deploys the site
after these files reach `main`.
