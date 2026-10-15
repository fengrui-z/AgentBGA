"use client";

import {useState} from "react";
import {BoardCarousel} from "./board-carousel";
import "./arena.css";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const REPOSITORY_URL = "https://github.com/fengrui-z/AgentBGA";
const DOCS_URL = `${REPOSITORY_URL}/blob/main/README.md`;
const asset = (name: string) => `${BASE_PATH}/showcase/${name}.jpg`;

const GAMES = [
  {id: "splendor", name: "Splendor", alt: "Actual Splendor table. Gem bank, nobles, card tiers, player resources, and action confirmation.", players: "2–4", scope: "Base game", status: "Playable"},
  {id: "wingspan", name: "Wingspan", alt: "Actual Wingspan table. Habitat actions, a bird in the grassland, food resources, and move confirmation.", players: "2–5", scope: "170 birds · both goal boards", status: "Playable beta"},
  {id: "harmonies", name: "Harmonies", alt: "Actual Harmonies table. Hex landscape with stacked tokens, the token market, and animal habitat cards.", players: "1–4", scope: "A/B boards · Nature’s Spirits", status: "Playable beta"},
  {id: "azul", name: "Azul", alt: "Actual Azul table. Factory and center tiles, a selected red tile group, pattern lines, and move confirmation.", players: "2–4", scope: "Colored-wall base game", status: "Playable beta"},
  {id: "brass-birmingham", name: "Brass: Birmingham", alt: "Actual Brass: Birmingham table. Industry and transport map with cities, industries, and network connections.", players: "2–4", scope: "Canal & Rail eras", status: "Playable beta"},
  {id: "castles-of-burgundy", name: "The Castles of Burgundy", alt: "Actual The Castles of Burgundy table. Dice, tile depots, player resources, and the hexagonal duchy board.", players: "2–4", scope: "2019 base · no. 1 duchy", status: "Playable beta"},
  {id: "century-spice-road", name: "Century: Spice Road", alt: "Actual Century: Spice Road table. Order cards, the merchant market, spice costs, and acquisition options.", players: "2–5", scope: "Base game", status: "Playable"},
  {id: "ark-nova", name: "Ark Nova", alt: "Actual Ark Nova table. Zoo map with terrain and enclosures, association workers, partner zoos, and universities.", players: "1–4", scope: "Map 0 · Map A preview", status: "Released Map 0"},
  {id: "seven-wonders", name: "7 Wonders", alt: "Actual 7 Wonders table. Three-player drafting table with Wonders, resource production, hand cards, and build options.", players: "3–7", scope: "Second Edition · Day/Night", status: "Playable"},
  {id: "carcassonne", name: "Carcassonne", alt: "Actual Carcassonne table. Landscape tiles, legal placement highlights, tile rotation, and connected features.", players: "2–5", scope: "72 base tiles · farmers", status: "Playable beta"},
] as const;

const BACKENDS = [
  "OpenAI", "Anthropic", "Gemini", "OpenCode", "Codex", "DSh", "Hermes",
  "Claude Code", "Pi", "Qwen Code", "Cursor", "Grok Build", "Minimal",
] as const;

const TABLES = [
  {
    id: "wingspan", title: "Wingspan", category: "Engine building",
    description: "Habitats, food, bird powers, and round goals share one table. Choose a bird, inspect its cost, and confirm each decision.",
    alt: "Actual Wingspan table showing habitat actions, a bird in the grassland, food resources, and move confirmation.",
    detail: "170 base birds · 26 bonus cards · 2–5 players",
  },
  {
    id: "brass-birmingham", title: "Brass: Birmingham", category: "Economic networks",
    description: "Build industries on the map, choose resource sources, and plan connections across the Canal and Rail eras.",
    alt: "Actual Brass Birmingham focus-map view showing cities, industries, and transport connections.",
    detail: "Two eras · shared markets · 2–4 players",
  },
  {
    id: "carcassonne", title: "Carcassonne", category: "Spatial planning",
    description: "Rotate a tile, inspect connected features, and place a follower. The shared map grows with every accepted move.",
    alt: "Actual Carcassonne table showing landscape tiles, legal placement highlights, tile rotation, and connected features.",
    detail: "72 base tiles · farmers · 2–5 players",
  },
] as const;

function GameShowcase() {
  const [selected, setSelected] = useState(0);
  const table = TABLES[selected];
  return <section className="intro-section" id="tables" aria-labelledby="tables-heading">
    <div className="section-heading">
      <div><span className="eyebrow">01 / AT THE TABLE</span><h2 id="tables-heading">Real boards.<br/>Decisions you can see.</h2></div>
      <p>Play a human seat, watch agents compete, or inspect a saved match. Each game has its own interactive table, with readable choices and a preview before submission.</p>
    </div>
    <div className="showcase-controls" role="group" aria-label="Choose a game screenshot">
      {TABLES.map((item, index) => <button type="button" key={item.id} aria-pressed={selected === index} aria-controls="game-screenshot" onClick={() => setSelected(index)}><span>{String(index + 1).padStart(2, "0")}</span>{item.title}<i aria-hidden="true">↗</i></button>)}
    </div>
    <figure className="game-showcase" id="game-screenshot">
      <div className="showcase-image"><img src={asset(table.id)} alt={table.alt} width="1280" height="720" loading="lazy"/></div>
      <figcaption aria-live="polite">
        <div><span className="eyebrow">{table.category}</span><h3>{table.title}</h3><p>{table.description}</p></div>
        <div className="showcase-caption-end"><span>{table.detail}</span><a href={asset(table.id)} target="_blank" rel="noreferrer">Open screenshot at full size <span aria-hidden="true">↗</span></a></div>
      </figcaption>
    </figure>
    <p className="screenshot-note">Actual local application screenshots, using demonstration matches. Select a game to inspect its interface.</p>
  </section>;
}

function EngineFlow() {
  return <div className="engine-flow" aria-label="Observe the visible state, inspect legal actions, submit a move, and replay the recorded event">
    <div><span>01</span><code>observe</code><small>Visible state</small></div><i aria-hidden="true">→</i>
    <div><span>02</span><code>legal_actions</code><small>Valid choices</small></div><i aria-hidden="true">→</i>
    <div><span>03</span><code>submit_action</code><small>Engine validation</small></div><i aria-hidden="true">→</i>
    <div><span>04</span><code>replay</code><small>Recorded evidence</small></div>
  </div>;
}

export default function ArenaPage() {
  return <main className="arena-page" lang="en">
    <nav className="arena-nav" aria-label="Project navigation">
      <a className="intro-brand" href={`${BASE_PATH}/`}><span>ABGA</span>AgentBGA</a>
      <div><a href="#tables">Game tables</a><a href="#modules">How it works</a><a href={DOCS_URL}>Docs</a><a className="nav-github" href={REPOSITORY_URL}>GitHub <span aria-hidden="true">↗</span></a></div>
    </nav>

    <div className="intro-shell">
      <header className="intro-hero">
        <div className="hero-copy">
          <span className="eyebrow"><i aria-hidden="true"/> Open-source Agentic Board Game Arena</span>
          <h1>Long games.<br/>Real decisions.<br/><span>Inspectable agents.</span></h1>
          <p>Put humans and AI agents at the same table. AgentBGA connects playable strategy games, agent runtimes, and decision traces in one reproducible environment.</p>
          <div className="hero-actions"><a className="primary-action" href={`${DOCS_URL}#play-locally`}>Run it locally <span aria-hidden="true">↗</span></a><a className="secondary-action" href="#tables">Explore the tables <span aria-hidden="true">↓</span></a></div>
          <p className="hero-note">Human vs. agent · Agent vs. agent · Seeded replay</p>
        </div>
        <BoardCarousel boards={GAMES} basePath={BASE_PATH}/>
      </header>

      <div className="project-facts" aria-label="Implemented project capabilities">
        <div><strong>10</strong><span>playable game engines</span></div>
        <div><strong>13</strong><span>model &amp; harness backends</span></div>
        <div><strong>3</strong><span>experiment modes</span></div>
        <div><strong>CLI + Web</strong><span>one rules engine</span></div>
      </div>

      <GameShowcase/>

      <section className="intro-section modules-section" id="modules" aria-labelledby="modules-heading">
        <div className="section-heading"><div><span className="eyebrow">02 / UNDER THE HOOD</span><h2 id="modules-heading">From a legal move<br/>to a replayable result.</h2></div><p>The game engine owns the rules. Players and agents choose actions through the same validated game protocol. The surrounding modules make those decisions playable, repeatable, and inspectable.</p></div>
        <EngineFlow/>
        <div className="module-grid">
          <article><span className="module-number">01 / RULES &amp; STATE</span><h3>Deterministic game engines</h3><p>Seeded setup, versioned state, legal-action generation, scoring, and persisted replay. Seat-scoped agent observations preserve hidden information.</p><a href={`${REPOSITORY_URL}/blob/main/docs/architecture.md`}>Explore the architecture <span aria-hidden="true">↗</span></a></article>
          <article><span className="module-number">02 / AGENT RUNTIME</span><h3>Compare the whole agent</h3><p>Combine a model with its harness, tools, and memory strategy. Each participant gets a dedicated workspace and session scope.</p><a href={`${REPOSITORY_URL}/blob/main/docs/usage.md#agents`}>See backend configuration <span aria-hidden="true">↗</span></a></article>
          <article><span className="module-number">03 / HUMAN PLAY</span><h3>A table for every game</h3><p>Board interactions, payment choices, action previews, and explicit confirmation. Responsive layouts and collapsible logs keep the current decision in view.</p><a href={`${DOCS_URL}#play-locally`}>Start a human seat <span aria-hidden="true">↗</span></a></article>
          <article><span className="module-number">04 / EVALUATION</span><h3>Keep the decision trail</h3><p>Inspect actions, available model outputs, tool calls, latency, and reported token usage. Run paired duels, tournaments, or repeated learning series.</p><a href={`${REPOSITORY_URL}/blob/main/docs/usage.md#traces`}>Inspect traces &amp; results <span aria-hidden="true">↗</span></a></article>
        </div>
        <div className="runtime-row"><span className="eyebrow">BRING YOUR AGENT</span><div>{BACKENDS.map(backend => <span key={backend}>{backend}</span>)}</div><p>Plus human players and a random baseline. Install only the runtime you use.</p></div>
      </section>

      <section className="intro-section" id="games" aria-labelledby="games-heading">
        <div className="section-heading"><div><span className="eyebrow">03 / GAME LIBRARY</span><h2 id="games-heading">Ten games.<br/>Different ways to plan.</h2></div><p>Resource races, card engines, spatial puzzles, drafting, and economic networks. Every game below has a CLI engine and a dedicated browser table.</p></div>
        <div className="game-library">{GAMES.map((game, index) => <article key={game.name}><span className="game-number">{String(index + 1).padStart(2, "0")}</span><div><h3>{game.name}</h3><p>{game.scope}</p></div><div className="game-meta"><span>{game.players} players</span><small>{game.status}</small></div></article>)}</div>
        <p className="coverage-note">Coverage is shown per game. Playable beta implementations remain under validation; Ark Nova’s Map A is a preview. <a href={`${DOCS_URL}#supported-games`}>Read the exact scope →</a></p>
      </section>

      <section className="quickstart-section" id="quickstart" aria-labelledby="quickstart-heading">
        <div><span className="eyebrow">04 / TRY IT YOURSELF</span><h2 id="quickstart-heading">Your first match.<br/>No API key needed.</h2><p>Clone the repository and run a random baseline with Python 3.11+. Build the local table with Node.js 22.13+ to take a human seat.</p><div className="docs-links"><a href={`${DOCS_URL}#play-locally`}>English quick start ↗</a><a href={`${REPOSITORY_URL}/blob/main/README.zh-CN.md`} lang="zh-CN">中文文档 ↗</a></div></div>
        <div className="quickstart-code"><span>TERMINAL / FROM THE REPOSITORY ROOT</span><pre><code><b># A reproducible baseline</b>{"\n"}{"./agentbga run --game splendor \\\n  --players 2 --controllers random,random --seed 42"}{"\n\n"}<b># Open the local table</b>{"\n"}{"cd web && npm ci && npm run build && cd ..\n./agentbga web"}</code></pre><small>Open <code>http://127.0.0.1:8765</code> · Choose Human + Random</small></div>
      </section>
      <p className="hosting-note">This site introduces the project. Interactive matches run locally; GitHub Pages does not host a live game service.</p>
    </div>

    <footer className="site-footer"><a className="intro-brand" href={`${BASE_PATH}/`}><span>ABGA</span>AgentBGA</a><p>Play. Compare. Inspect. Replay.</p><div><a href={REPOSITORY_URL}>Source code ↗</a><a href={`${REPOSITORY_URL}/blob/main/THIRD_PARTY_NOTICES.md`}>Content &amp; licenses ↗</a></div></footer>
  </main>;
}
