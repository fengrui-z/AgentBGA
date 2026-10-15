# Project introduction page

The public [GitHub Pages site](https://fengrui-z.github.io/AgentBGA/) is a project
introduction: real game tables, implemented modules, game coverage, and links to
the bilingual documentation. It does not host matches. The page lives in
`web/app/arena/`; the local application links to it from `/arena`.

## Languages

The navigation includes a Chinese/English switch. Copy, game names, accessibility
labels, documentation links, carousel images, and the detail gallery all follow
the selected language. Switching preserves the selected carousel and gallery
games. `?lang=zh` and `?lang=en` are shareable links and override the browser
preference stored under `agentbga-intro-lang`. English remains the static-export
default; preferences restore after hydration. Storage is optional and is separate
from the local game's own language preference.

## Screenshots

The ten English JPEGs in `web/public/showcase/` and ten Chinese captures in
`web/public/showcase/zh/` were captured from the actual local web
application on 2026-10-16, after the ten-game human-usability update. They use an
isolated demonstration database, seed 42, a human seat, and random opponents (three players for 7 Wonders; two for the
other games).
The Chinese set was recaptured with the game UI switched to Chinese and generic
Chinese player names. These are genuine interface captures; card titles or
technical labels that the game itself retains in English remain unchanged.
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

To refresh an image, run an isolated local match, use generic player names, switch
the game to the target language, and capture the real interface through the
browser. Use the same filename in the English root or Chinese `zh/` directory. Keep credentials, private logs,
and personal identifiers out of the viewport. Retain the capture dimensions or
update the corresponding image attributes. The hero cycles through all ten games
in a cover-flow carousel, starting with Splendor. Previous/next buttons wrap at
both ends; the ten labeled dots jump directly to a game. The arrow buttons also
accept Left/Right keys, and horizontal pointer drags or touch swipes change slides.
Vertical touch scrolling remains available. Dragging does not open an image;
clicking the active board opens the full-size capture. No automatic rotation is
used, and reduced-motion preferences disable the slide animation. The separate
Wingspan/Brass/Carcassonne detail gallery remains available below the hero.

## Benchmark publication

Benchmark results are withheld from the current source tree and website. The
introduction displays implemented functionality and real game interfaces. Keep
experiment summaries, raw traces, and local analysis reports outside
`web/public`; removing a chart or link does not prevent static assets from being
published. The build rejects `web/public/results`, and the Pages workflow checks
that the deployment artifact has no `results` directory.

The result-export script remains available for local analysis. Store its output
in an ignored local directory such as `.agentbga/analysis/`. A future benchmark
release should explicitly review both the dataset and its presentation before
changing these checks. Deleting files from the current tree does not erase prior
Git commits or previously published copies.

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
gallery; verify both language directions, refresh persistence and explicit language
links; and check that every Chinese image and full-size link uses `showcase/zh/`.
Verify the localized documentation links. All site assets must resolve
under the repository base path. The existing Pages workflow deploys the site
after these files reach `main`.
