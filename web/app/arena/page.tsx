"use client";

import {useEffect, useState, type CSSProperties} from "react";
import Link from "next/link";
import "./arena.css";

type LeaderboardEntry = {
  backend: string;
  display_name: string;
  elo: number;
  participant_id: string;
};

type TokenEntry = {
  participant_id: string;
  short_name: string;
  successful_sessions: number;
  mean_cost_rmb: number;
};

type GameTokenEntry = {
  participant_id: string;
  game: string;
  successful_sessions: number;
  elo?: number;
  mean_cost_rmb?: number;
};

type TokenEfficiency = {
  successful_sessions: number;
  eligible_sessions: number;
  entries: TokenEntry[];
  by_game: GameTokenEntry[];
  pricing: {as_of: string};
};

type FrontierData = {
  dataset_id: string;
  generated_at: string;
  leaderboard: LeaderboardEntry[];
  results: {completed: number; scheduled: number};
  token_efficiency?: TokenEfficiency;
};

type GameId = "splendor" | "seven_wonders" | "brass_birmingham";
type CostScope = "overall" | GameId;

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const DATA_URL = `${BASE_PATH}/results/frontier12-2026-v2.json`;
const REPOSITORY_URL = "https://github.com/fengrui-z/AgentBGA";
const GAME_NAMES: Record<GameId, string> = {
  splendor: "Splendor",
  seven_wonders: "7 Wonders",
  brass_birmingham: "Brass: Birmingham",
};
const GAMES = [
  ["Splendor", "2–4P · stable"],
  ["Wingspan", "2–5P · beta"],
  ["Harmonies", "1–4P · beta"],
  ["Azul", "2–4P · beta"],
  ["Brass: Birmingham", "2–4P · beta"],
  ["The Castles of Burgundy", "2–4P · beta"],
  ["Century: Spice Road", "2–5P · stable"],
  ["Ark Nova", "1–4P · base game"],
  ["7 Wonders", "3–7P · 2nd edition"],
] as const;
const BACKENDS = [
  "OpenAI", "Anthropic", "Gemini", "OpenCode", "Codex", "DSh", "Hermes",
  "Claude Code", "Pi", "Qwen Code", "Cursor", "Grok Build", "Minimal",
] as const;

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function niceCeiling(value: number) {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const normalized = value / power;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * power;
}

function rmb(value: number) {
  return `¥${value.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric", month: "2-digit", day: "2-digit", timeZone: "UTC",
  }).format(new Date(value));
}

function ParetoFrontier({data}: {data: FrontierData}) {
  const [scope, setScope] = useState<CostScope>("overall");
  const token = data.token_efficiency;
  if (!token) return null;

  const ratings = new Map(data.leaderboard.map(item => [item.participant_id, item]));
  const overallTokens = new Map(token.entries.map(item => [item.participant_id, item]));
  const scopes: CostScope[] = ["overall", "splendor", "seven_wonders", "brass_birmingham"];
  const points = scope === "overall"
    ? token.entries.flatMap(item => {
        const rating = ratings.get(item.participant_id);
        return rating && Number.isFinite(item.mean_cost_rmb) ? [{
          participant_id: item.participant_id,
          short_name: item.short_name,
          successful_sessions: item.successful_sessions,
          elo: rating.elo,
          display_name: rating.display_name,
          cost: item.mean_cost_rmb,
        }] : [];
      })
    : token.by_game.flatMap(item => {
        if (item.game !== scope || !Number.isFinite(item.elo) || !Number.isFinite(item.mean_cost_rmb)) return [];
        const rating = ratings.get(item.participant_id);
        const overall = overallTokens.get(item.participant_id);
        return rating && overall ? [{
          participant_id: item.participant_id,
          short_name: overall.short_name,
          successful_sessions: item.successful_sessions,
          elo: item.elo!,
          display_name: rating.display_name,
          cost: item.mean_cost_rmb!,
        }] : [];
      });
  const frontier = new Set(points.filter(point => !points.some(other =>
    other.participant_id !== point.participant_id
    && other.cost <= point.cost
    && other.elo >= point.elo
    && (other.cost < point.cost || other.elo > point.elo)
  )).map(point => point.participant_id));
  const maximumCost = niceCeiling(Math.max(...points.map(item => item.cost), 1));
  const scopeLabel = scope === "overall" ? "Overall" : GAME_NAMES[scope];

  return <section className="frontier-section" id="frontier">
    <header className="section-heading frontier-heading">
      <div><span>FRONTIER 12 · PUBLIC RESULT</span><h2>Cost–performance Pareto frontier</h2></div>
      <p>Bradley–Terry Elo is plotted against estimated API cost per successful session. Highlighted points are not dominated by any configuration that is both cheaper and stronger.</p>
    </header>
    <figure className="frontier-card">
      <figcaption>
        <div><strong>{scopeLabel} · Elo × Cost</strong><span>Higher and farther left is better · Elo uses all 396 completed matches · Cost uses validated provider telemetry</span></div>
        <div className="scope-tabs" role="tablist" aria-label="Choose the overall or per-game Pareto frontier">
          {scopes.map(item => <button type="button" role="tab" aria-selected={scope === item} className={scope === item ? "active" : ""} key={item} onClick={() => setScope(item)}>{item === "overall" ? "Overall" : GAME_NAMES[item]}</button>)}
        </div>
      </figcaption>
      <div className="scatter-wrap">
        <div className="scatter-y-label">Elo ↑</div>
        <div className="scatter-stage" role="img" aria-label={`${scopeLabel} Elo and estimated API cost Pareto frontier`}>
          {[2100, 1800, 1500, 1200].map(value => <span className="y-tick" key={value} style={{"--tick": `${(2100 - value) / 900 * 100}%`} as CSSProperties}>{value}</span>)}
          {[0, .25, .5, .75, 1].map(ratio => <span className="x-tick" key={ratio} style={{"--tick": `${ratio * 100}%`} as CSSProperties}>{rmb(maximumCost * ratio)}</span>)}
          {points.map(item => {
            const x = clamp(item.cost / maximumCost * 100, 1, 99);
            const y = clamp((2100 - item.elo) / 900 * 100, 1, 99);
            const size = 12 + clamp((item.successful_sessions - 20) / 70, 0, 1) * 8;
            const isFrontier = frontier.has(item.participant_id);
            return <button type="button" key={item.participant_id} aria-label={`${item.display_name}: ${item.elo.toFixed(1)} Elo, ${rmb(item.cost)} per successful session`} className={`scatter-point ${isFrontier ? "is-frontier" : ""}`} style={{"--x": `${x}%`, "--y": `${y}%`, "--size": `${size}px`} as CSSProperties}>
              {isFrontier && <em>{item.short_name}</em>}
              <b>{item.display_name}</b><small>{item.elo.toFixed(1)} Elo · {rmb(item.cost)} / session</small>
            </button>;
          })}
        </div>
        <div className="scatter-x-label">Estimated API cost (RMB / successful session) →</div>
      </div>
      <footer>
        <span><i className="legend-all"/>All configurations</span>
        <span><i className="legend-frontier"/>Pareto frontier</span>
        <small>{token.successful_sessions} of {token.eligible_sessions} sessions include validated telemetry · Pricing as of {token.pricing.as_of}</small>
      </footer>
    </figure>
  </section>;
}

export default function ArenaPage() {
  const [data, setData] = useState<FrontierData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch(DATA_URL, {signal: controller.signal, cache: "no-store"})
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<FrontierData>;
      })
      .then(setData)
      .catch(caught => {
        if ((caught as Error).name !== "AbortError") setError("Public experiment data is temporarily unavailable.");
      });
    return () => controller.abort();
  }, []);

  return <main className="arena-page" lang="en">
    <nav className="arena-nav">
      <Link href={`${BASE_PATH}/`}><span>ABGA</span> AgentBGA</Link>
      <div className="nav-links">
        <a href="#capabilities">Capabilities</a>
        <a href="#games">Games</a>
        <a href="#frontier">Frontier</a>
        <a href={REPOSITORY_URL} target="_blank" rel="noreferrer">GitHub ↗</a>
      </div>
    </nav>

    <header className="intro-hero">
      <div className="hero-copy">
        <span className="arena-kicker">OPEN-SOURCE ENVIRONMENT FOR LONG-HORIZON AGENTS</span>
        <h1>Evaluate agents in long-horizon strategy games.</h1>
        <p>AgentBGA is a deterministic, headless environment for evaluating model × harness systems in Euro-style board games. It tests planning, memory, tool use, and opponent modeling under the same rules, tool boundaries, and balanced seats.</p>
        <div className="hero-actions">
          <a className="primary-action" href={REPOSITORY_URL} target="_blank" rel="noreferrer">View on GitHub <span>↗</span></a>
          <a className="secondary-action" href="#quickstart">Quick start ↓</a>
        </div>
      </div>
      <aside className="hero-console" aria-label="AgentBGA quick command example">
        <header><i/><i/><i/><span>agentbga / tournament</span></header>
        <pre><code><b>$</b>{[
          " ./agentbga run \\",
          "  --game splendor \\",
          "  --players 2 \\",
          "  --controllers codex,opencode \\",
          "  --seed 42 --jsonl",
        ].join("\n")}</code></pre>
        <div><span>deterministic seed</span><strong>42</strong></div>
        <div><span>seat-scoped tools</span><strong>isolated</strong></div>
        <div><span>trace &amp; replay</span><strong>enabled</strong></div>
      </aside>
      <div className="hero-metrics">
        <article><strong>9</strong><span>BOARD-GAME ENGINES</span></article>
        <article><strong>13</strong><span>MODEL / HARNESS BACKENDS</span></article>
        <article><strong>{data?.results.completed ?? "396"}</strong><span>PUBLIC FRONTIER MATCHES</span></article>
      </div>
    </header>

    <section className="intro-section" id="capabilities">
      <header className="section-heading">
        <div><span>WHY AGENTBGA</span><h2>One reproducible path from game rules to evaluation evidence.</h2></div>
        <p>AgentBGA does not make decisions for the agent. Each seat receives only its visible state and a constrained set of game tools. Actions, session resumes, traces, and token telemetry remain inspectable.</p>
      </header>
      <div className="capability-grid">
        <article><b>01</b><span>DETERMINISTIC ENGINES</span><h3>Exact replay from a seed</h3><p>Deterministic state machines and versioned actions make failures reproducible and comparisons fair.</p></article>
        <article><b>02</b><span>SEAT-SCOPED INTERFACE</span><h3>Hidden information stays hidden</h3><p>Observe, inspect, legal-action, and submit tools are scoped to one seat. Simultaneous choices use frozen observations and a reveal barrier.</p></article>
        <article><b>03</b><span>HARNESS × MODEL</span><h3>Evaluate the full agent stack</h3><p>Pair the same model with Codex, OpenCode, Qwen Code, and other harnesses to measure runtime effects separately from model capability.</p></article>
        <article><b>04</b><span>TRACE &amp; METRICS</span><h3>Audit every decision</h3><p>Record prompts, reasoning, tool calls, final actions, latency, cache use, and tokens across duels, tournaments, and learning series.</p></article>
      </div>
    </section>

    <section className="ecosystem-section" id="games">
      <div className="games-panel">
        <header><span>GAME ENGINES</span><h2>Nine long-horizon strategy games</h2><p>Coverage ranges from compact resource races to hidden information, spatial planning, and multi-round economic networks.</p></header>
        <div className="game-list">{GAMES.map(([name, status], index) => <article key={name}><b>{String(index + 1).padStart(2, "0")}</b><strong>{name}</strong><span>{status}</span></article>)}</div>
      </div>
      <div className="backends-panel">
        <header><span>AGENT RUNTIMES</span><h2>One seat interface, many agent stacks</h2><p>Direct APIs, CLI harnesses, a minimal Python agent, and human or random baselines share the same visibility and action boundaries.</p></header>
        <div className="backend-cloud">{BACKENDS.map(backend => <span key={backend}>{backend}</span>)}</div>
        <div className="pipeline">
          <article><b>01</b><span>Engine state</span></article><i>→</i>
          <article><b>02</b><span>Seat tools</span></article><i>→</i>
          <article><b>03</b><span>Agent session</span></article><i>→</i>
          <article><b>04</b><span>Trace + result</span></article>
        </div>
      </div>
    </section>

    <section className="quickstart-section" id="quickstart">
      <div><span>QUICK START</span><h2>Start a reproducible match with one command.</h2><p>Python 3.11+, with no package install required. Run the local web table to play, configure agents, or spectate a match.</p></div>
      <pre><code><b># random baseline</b>{`\n`}./agentbga run --players 2 --controllers random,random --seed 42{`\n\n`}<b># local interactive table</b>{`\n`}cd web &amp;&amp; npm ci &amp;&amp; npm run build &amp;&amp; cd ..{`\n`}./agentbga web</code></pre>
    </section>

    {data && <ParetoFrontier data={data}/>}
    {!data && <section className="frontier-loading" id="frontier"><span>PUBLIC FRONTIER</span><h2>{error || "Loading the public 396-match result snapshot…"}</h2></section>}

    <section className="closing-section">
      <span>BUILD · RUN · INSPECT · REPLAY</span>
      <h2>Turn long-horizon agent behavior into reproducible, comparable evidence.</h2>
      <div><a href={REPOSITORY_URL} target="_blank" rel="noreferrer">Explore the repository ↗</a></div>
    </section>

    <footer className="site-footer">
      <b>AgentBGA</b>
      <span>Open-source long-horizon board-game environment</span>
      <small>{data ? `${data.dataset_id} · ${formatDate(data.generated_at)}` : "Deterministic by design"}</small>
    </footer>
  </main>;
}
