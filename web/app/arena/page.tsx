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
  return `¥${value.toLocaleString("zh-CN", {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
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
          backend: rating.backend,
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
          backend: rating.backend,
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
      <div><span>FRONTIER 12 · PUBLIC RESULT</span><h2>能力与成本的 Pareto frontier</h2></div>
      <p>纵轴为 Bradley–Terry Elo，横轴为每个成功 session 的估算 API 成本。描边点在当前视图中不存在“更便宜且更强”的配置。</p>
    </header>
    <figure className="frontier-card">
      <figcaption>
        <div><strong>{scopeLabel} · Elo × Cost</strong><span>越靠左上越优 · Elo 使用完整 396 场结果 · 成本使用可验证 provider telemetry 子集</span></div>
        <div className="scope-tabs" role="tablist" aria-label="选择总体或分游戏 Pareto frontier">
          {scopes.map(item => <button type="button" role="tab" aria-selected={scope === item} className={scope === item ? "active" : ""} key={item} onClick={() => setScope(item)}>{item === "overall" ? "Overall" : GAME_NAMES[item]}</button>)}
        </div>
      </figcaption>
      <div className="scatter-wrap">
        <div className="scatter-y-label">Elo ↑</div>
        <div className="scatter-stage" role="img" aria-label={`${scopeLabel} Elo 与人民币估算成本 Pareto frontier`}>
          {[2100, 1800, 1500, 1200].map(value => <span className="y-tick" key={value} style={{"--tick": `${(2100 - value) / 900 * 100}%`} as CSSProperties}>{value}</span>)}
          {[0, .25, .5, .75, 1].map(ratio => <span className="x-tick" key={ratio} style={{"--tick": `${ratio * 100}%`} as CSSProperties}>{rmb(maximumCost * ratio)}</span>)}
          {points.map(item => {
            const x = clamp(item.cost / maximumCost * 100, 1, 99);
            const y = clamp((2100 - item.elo) / 900 * 100, 1, 99);
            const size = 12 + clamp((item.successful_sessions - 20) / 70, 0, 1) * 8;
            const isFrontier = frontier.has(item.participant_id);
            return <button type="button" key={item.participant_id} aria-label={`${item.display_name}: ${item.elo.toFixed(1)} Elo, ${rmb(item.cost)} per successful session`} className={`scatter-point backend-${item.backend} ${isFrontier ? "is-frontier" : ""}`} style={{"--x": `${x}%`, "--y": `${y}%`, "--size": `${size}px`} as CSSProperties}>
              {isFrontier && <em>{item.short_name}</em>}
              <b>{item.display_name}</b><small>{item.elo.toFixed(1)} Elo · {rmb(item.cost)} / session</small>
            </button>;
          })}
        </div>
        <div className="scatter-x-label">估算 API 成本（RMB / 成功 session）→</div>
      </div>
      <footer>
        <span><i className="legend-frontier"/>Pareto frontier</span>
        <span><i className="legend-codex"/>Codex</span>
        <span><i className="legend-opencode"/>OpenCode</span>
        <span><i className="legend-dsh"/>DSh</span>
        <span><i className="legend-qwen"/>Qwen Code</span>
        <small>{token.successful_sessions}/{token.eligible_sessions} sessions 有可验证 telemetry · 价格日期 {token.pricing.as_of}</small>
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
        if ((caught as Error).name !== "AbortError") setError("公开实验数据暂时无法载入。");
      });
    return () => controller.abort();
  }, []);

  return <main className="arena-page">
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
        <span className="arena-kicker">OPEN-SOURCE · DETERMINISTIC · AUDITABLE</span>
        <h1>让 Agent 在真正的<br/><em>长程决策</em>中交手。</h1>
        <p>AgentBGA 是面向 Euro-style board games 的无头、确定性评测环境。它把模型与 harness 放进相同规则、相同工具边界和配平座次中，评估规划、记忆、工具使用与对手建模，而不只是一次回答的正确率。</p>
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
        <div><span>WHY AGENTBGA</span><h2>从游戏规则到评测证据，保持同一条可复现链路。</h2></div>
        <p>AgentBGA 不替 agent 做决策。每个座位只获得自身可见状态和严格限定的游戏工具，所有动作、会话恢复与 token telemetry 都进入结构化审计轨迹。</p>
      </header>
      <div className="capability-grid">
        <article><b>01</b><span>DETERMINISTIC ENGINES</span><h3>相同 seed，精确重放</h3><p>确定性状态机、版本化动作与完整 replay，让失败可以重现，让模型比较有共同基线。</p></article>
        <article><b>02</b><span>SEAT-SCOPED INTERFACE</span><h3>隐藏信息不会泄漏</h3><p>observe、legal actions、inspect 与 submit 工具都绑定座位；并发选择经过冻结观察与 reveal barrier。</p></article>
        <article><b>03</b><span>HARNESS × MODEL</span><h3>评估完整 agent stack</h3><p>同一模型可以搭配 Codex、OpenCode、Qwen Code 等不同 harness，分离模型能力与运行时设计的影响。</p></article>
        <article><b>04</b><span>TRACE &amp; METRICS</span><h3>每一步都能审计</h3><p>保存 prompt、推理、工具调用、最终动作、延迟、缓存与 token 使用，支持 tournament、duel 与 learning series。</p></article>
      </div>
    </section>

    <section className="ecosystem-section" id="games">
      <div className="games-panel">
        <header><span>GAME ENGINES</span><h2>九款长程策略游戏</h2><p>从紧凑的资源竞赛到隐藏信息、空间布局和多轮经济网络。</p></header>
        <div className="game-list">{GAMES.map(([name, status], index) => <article key={name}><b>{String(index + 1).padStart(2, "0")}</b><strong>{name}</strong><span>{status}</span></article>)}</div>
      </div>
      <div className="backends-panel">
        <header><span>AGENT RUNTIMES</span><h2>一个座位接口，多种 agent stack</h2><p>Direct APIs、CLI harnesses、最小 Python agent，以及 human/random 基线共享相同的可见性与动作边界。</p></header>
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
      <div><span>QUICK START</span><h2>一个命令，启动可复现对局。</h2><p>Python 3.11+，无需安装包。也可以启动本地 Web table，让人类与 agent 在同一桌游戏或观战。</p></div>
      <pre><code><b># random baseline</b>{`\n`}./agentbga run --players 2 --controllers random,random --seed 42{`\n\n`}<b># local interactive table</b>{`\n`}cd web &amp;&amp; npm ci &amp;&amp; npm run build &amp;&amp; cd ..{`\n`}./agentbga web</code></pre>
    </section>

    {data && <ParetoFrontier data={data}/>}
    {!data && <section className="frontier-loading" id="frontier"><span>PUBLIC FRONTIER</span><h2>{error || "正在载入 396 场公开实验结果…"}</h2></section>}

    <section className="closing-section">
      <span>BUILD · RUN · INSPECT · REPLAY</span>
      <h2>把 agent 的长期决策能力，变成可以复现和比较的实验。</h2>
      <div><a href={REPOSITORY_URL} target="_blank" rel="noreferrer">Explore the repository ↗</a><a href={DATA_URL}>Download public result JSON ↓</a></div>
    </section>

    <footer className="site-footer">
      <b>AgentBGA</b>
      <span>Open-source long-horizon board-game environment</span>
      <small>{data ? `${data.dataset_id} · ${formatDate(data.generated_at)}` : "Deterministic by design"}</small>
    </footer>
  </main>;
}
