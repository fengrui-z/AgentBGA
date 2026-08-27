"use client";

import {useEffect, useMemo, useState, type CSSProperties} from "react";
import Link from "next/link";
import "./arena.css";

type LeaderboardEntry = {
  average_rank: number; backend: string; completed: number; display_name: string;
  elo: number; failed_exposures: number; first_place_equivalent: number; model: string;
  participant_id: string; pairwise_comparisons: number; pws: number;
  rating_rank: number; scheduled: number;
};
type TokenEntry = {
  participant_id: string; short_name: string; successful_sessions: number;
  mean_total_tokens_m: number; median_total_tokens_m: number; efficiency_frontier: boolean;
};
type GameTokenEntry = {
  participant_id: string; game: string; successful_sessions: number;
  mean_total_tokens_m: number; median_total_tokens_m: number;
  mean_input_tokens_m?: number; mean_cached_input_tokens_m?: number;
  mean_output_tokens_m?: number; elo?: number; elo_rank?: number;
};
type TokenEfficiency = {
  source_report: string; successful_sessions: number; coverage_rate: number;
  entries: TokenEntry[]; by_game: GameTokenEntry[];
};
type FrontierData = {
  dataset_id: string; generated_at: string; leaderboard: LeaderboardEntry[];
  rating: {centre: number; failed_matches: string; method: string};
  results: {completed: number; failed: number; reported: number; scheduled: number};
  schedule: {
    appearances_per_condition: number; matches: number;
    pair_exposures: {maximum: number; minimum: number; zero_pairs: number};
    participants: number; seat_exposures_per_stratum: {exact: boolean};
    strata: Record<string, number>;
  };
  token_efficiency?: TokenEfficiency;
  tournament_id: string;
};
type SortKey = "elo" | "pws" | "average_rank";
type GameId = "splendor" | "seven_wonders" | "brass_birmingham";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const DATA_URL = `${BASE_PATH}/results/frontier12-2026-v2.json`;
const GAME_NAMES: Record<string, string> = {
  brass_birmingham: "Brass: Birmingham",
  seven_wonders: "7 Wonders",
  splendor: "Splendor",
};
const SORT_OPTIONS: [SortKey, string][] = [
  ["elo", "Elo"], ["pws", "PWS"], ["average_rank", "平均名次"],
];

function percent(value: number) { return `${(value * 100).toFixed(1)}%`; }
function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", timeZone: "UTC",
  }).format(new Date(value));
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function EfficiencyCharts({data}: {data: FrontierData}) {
  const [selectedGame, setSelectedGame] = useState<GameId>("splendor");
  const token = data.token_efficiency;
  if (!token) return null;
  const tokens = new Map(token.entries.map(item => [item.participant_id, item]));
  const ordered = data.leaderboard.flatMap(item => {
    const metric = tokens.get(item.participant_id);
    return metric ? [{...metric, rating: item}] : [];
  });
  const maximumMean = Math.max(...ordered.map(item => item.mean_total_tokens_m), 1);
  const games: GameId[] = ["splendor", "seven_wonders", "brass_birmingham"];
  const byGame = new Map(token.by_game.map(item => [`${item.participant_id}:${item.game}`, item]));
  const heatRows = ordered.filter(item => games.every(game => byGame.has(`${item.participant_id}:${game}`)));
  const gameComparison = token.by_game
    .filter(item => item.game === selectedGame && item.elo != null && item.mean_input_tokens_m != null && item.mean_cached_input_tokens_m != null && item.mean_output_tokens_m != null)
    .flatMap(item => {
      const rating = data.leaderboard.find(entry => entry.participant_id === item.participant_id);
      const overall = tokens.get(item.participant_id);
      return rating && overall ? [{...item, rating, short_name: overall.short_name}] : [];
    })
    .sort((left, right) => (right.elo ?? 0) - (left.elo ?? 0));
  const maximumGameTokens = Math.max(...gameComparison.map(item => item.mean_total_tokens_m), 1);

  return <section className="analysis-section">
    <header className="analysis-heading">
      <div><span>EFFICIENCY ANALYSIS</span><h2>Elo 之外，模型要花多少上下文？</h2></div>
      <p>复用实验报告的效率前沿、均值/中位数和分游戏热力图口径。Token 为 provider telemetry，不等同于 API 账单。</p>
    </header>
    <div className="analysis-grid">
      <figure className="chart-card scatter-card">
        <figcaption><strong>Elo × 平均总 Token / session</strong><span>越靠左上越优；圆点大小表示成功 sessions，描边点属于效率前沿。</span></figcaption>
        <div className="scatter-wrap">
          <div className="scatter-y-label">Elo ↑</div>
          <div className="scatter-stage" role="img" aria-label="Elo 与平均总 Token 效率前沿散点图">
            {[1700, 1600, 1500, 1400, 1300].map(value => <span className="y-tick" key={value} style={{"--tick": `${(1700 - value) / 450 * 100}%`} as CSSProperties}>{value}</span>)}
            {[5, 15, 25, 35, 45].map(value => <span className="x-tick" key={value} style={{"--tick": `${(value - 5) / 40 * 100}%`} as CSSProperties}>{value}M</span>)}
            {ordered.map(item => {
              const x = clamp((item.mean_total_tokens_m - 5) / 40 * 100, 1, 99);
              const y = clamp((1700 - item.rating.elo) / 450 * 100, 1, 99);
              const size = 11 + (item.successful_sessions - 48) / 39 * 8;
              return <button type="button" key={item.participant_id} aria-label={`${item.rating.display_name}: ${item.rating.elo.toFixed(1)} Elo, ${item.mean_total_tokens_m.toFixed(2)}M mean tokens, ${item.successful_sessions} sessions`} className={`scatter-point backend-${item.rating.backend} ${item.efficiency_frontier ? "is-frontier" : ""}`} style={{"--x": `${x}%`, "--y": `${y}%`, "--size": `${size}px`} as CSSProperties}>
                {item.efficiency_frontier && <em>{item.short_name}</em>}
                <b>{item.rating.display_name}</b><small>{item.rating.elo.toFixed(1)} Elo · {item.mean_total_tokens_m.toFixed(2)}M · {item.successful_sessions} sessions</small>
              </button>;
            })}
          </div>
          <div className="scatter-x-label">平均总 Token / session →</div>
        </div>
      </figure>
      <figure className="chart-card bars-card">
        <figcaption><strong>平均值 vs 中位数</strong><span>长条为均值，短线为中位数；差距越大，长局尾部影响越明显。</span></figcaption>
        <div className="token-bars">
          {ordered.map(item => <div className="token-bar-row" key={item.participant_id}>
            <span>{item.short_name}</span>
            <div><b style={{width: `${item.mean_total_tokens_m / maximumMean * 100}%`}}/><i style={{left: `${item.median_total_tokens_m / maximumMean * 100}%`}}/></div>
            <strong>{item.mean_total_tokens_m.toFixed(1)}M</strong>
          </div>)}
        </div>
        <div className="bar-legend"><span><i/>平均</span><span><i/>中位数</span></div>
      </figure>
      <figure className="chart-card game-compare-card">
        <figcaption>
          <div><strong>分游戏 Elo × Token 构成</strong><span>游戏内 Elo 独立拟合并以 1500 为中心；Token 为每个成功 session 的平均值。</span></div>
          <div className="game-tabs" role="tablist" aria-label="选择要比较的游戏">
            {games.map(game => <button type="button" role="tab" aria-selected={selectedGame === game} className={selectedGame === game ? "active" : ""} key={game} onClick={() => setSelectedGame(game)}>{GAME_NAMES[game]}</button>)}
          </div>
        </figcaption>
        <div className="game-compare-head"><span>配置</span><span>游戏 Elo（中心 1500）</span><span>平均 Token / session</span></div>
        <div className="game-compare-list" role="tabpanel" aria-label={`${GAME_NAMES[selectedGame]} Elo 与 Token 构成`}>
          {gameComparison.map(item => {
            const elo = item.elo ?? 1500;
            const eloDelta = elo - 1500;
            const eloWidth = Math.min(Math.abs(eloDelta) / 600 * 50, 50);
            const input = item.mean_input_tokens_m ?? 0;
            const cached = item.mean_cached_input_tokens_m ?? 0;
            const output = item.mean_output_tokens_m ?? 0;
            return <article key={item.participant_id}>
              <div className="game-competitor"><b>{item.elo_rank}</b><span><strong>{item.short_name}</strong><small>{item.successful_sessions} sessions</small></span></div>
              <div className="game-elo">
                <div aria-hidden="true"><i className={eloDelta >= 0 ? "positive" : "negative"} style={{"--elo-width": `${eloWidth}%`} as CSSProperties}/></div>
                <strong>{elo.toFixed(1)}</strong>
              </div>
              <div className="game-token">
                <div className="token-stack" role="img" aria-label={`${item.rating.display_name}: total ${item.mean_total_tokens_m.toFixed(3)}M tokens; input ${input.toFixed(3)}M; cached input ${cached.toFixed(3)}M; output ${output.toFixed(3)}M`}>
                  <i className="token-input" style={{width: `${input / maximumGameTokens * 100}%`}} title={`Input（非缓存） ${input.toFixed(3)}M`}/>
                  <i className="token-cached" style={{width: `${cached / maximumGameTokens * 100}%`}} title={`Cached input ${cached.toFixed(3)}M`}/>
                  <i className="token-output" style={{width: `${output / maximumGameTokens * 100}%`}} title={`Output ${output.toFixed(3)}M`}/>
                </div>
                <strong>{item.mean_total_tokens_m.toFixed(2)}M</strong>
              </div>
            </article>;
          })}
        </div>
        <div className="game-token-legend"><span><i className="token-input"/>Input（非缓存）</span><span><i className="token-cached"/>Cached input</span><span><i className="token-output"/>Output</span><small>条长按当前游戏最高总量统一缩放</small></div>
      </figure>
      <figure className="chart-card heatmap-card">
        <figcaption><strong>分游戏平均总 Token / session</strong><span>同一配置在不同流程长度下的上下文消耗；深色代表更高 Token。</span></figcaption>
        <div className="heatmap-scroll">
          <div className="token-heatmap">
            <div/><b>Splendor</b><b>7 Wonders</b><b>Brass</b>
            {heatRows.map(item => <div className="heat-row" key={item.participant_id}>
              <strong>{item.short_name}</strong>
              {games.map(game => {
                const cell = byGame.get(`${item.participant_id}:${game}`)!;
                const intensity = Math.sqrt(cell.mean_total_tokens_m / 112);
                const lightness = 96 - intensity * 62;
                return <span key={game} title={`${item.rating.display_name} · ${GAME_NAMES[game]}: ${cell.mean_total_tokens_m.toFixed(2)}M`} style={{background: `hsl(143 36% ${lightness}%)`, color: lightness < 58 ? "#fff" : "#172019"}}>{cell.mean_total_tokens_m.toFixed(1)}M<small>{cell.successful_sessions} sessions</small></span>;
              })}
            </div>)}
          </div>
        </div>
        <div className="heat-note">仅展示三款游戏均有成功样本的 {heatRows.length} 个配置 · 数据源 {token.source_report}</div>
      </figure>
    </div>
  </section>;
}

export default function ArenaPage() {
  const [data, setData] = useState<FrontierData | null>(null);
  const [error, setError] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("elo");

  useEffect(() => {
    const controller = new AbortController();
    fetch(DATA_URL, {signal: controller.signal})
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<FrontierData>;
      })
      .then(setData)
      .catch(caught => {
        if ((caught as Error).name !== "AbortError") setError("结果数据暂时无法载入，请稍后刷新。");
      });
    return () => controller.abort();
  }, []);

  const entries = useMemo(() => [...(data?.leaderboard ?? [])].sort((left, right) =>
    sortKey === "average_rank" ? left.average_rank - right.average_rank : right[sortKey] - left[sortKey]
  ), [data, sortKey]);
  const games = useMemo(() => {
    const totals = new Map<string, number>();
    Object.entries(data?.schedule.strata ?? {}).forEach(([stratum, matches]) => {
      const game = stratum.split(":", 1)[0];
      totals.set(game, (totals.get(game) ?? 0) + matches);
    });
    return [...totals.entries()];
  }, [data]);
  const completion = data ? data.results.completed / data.results.scheduled : 0;

  return <main className="arena-page">
    <nav className="arena-nav">
      <Link href={`${BASE_PATH}/`}><span>ABGA</span> AgentBGA home</Link>
      <div><i/> Frontier 12 · 2026</div>
    </nav>
    <header className="arena-hero">
      <div>
        <span className="arena-kicker">AGENTBGA / MODEL × HARNESS TOURNAMENT</span>
        <h1>Brettspiel Agent Arena<br/><span>Model × Harness</span></h1>
        <p>面向 Euro-style board games（欧式桌游）的 Agent 竞技场。在 Splendor、Brass: Birmingham 与 7 Wonders 中进行座位配平的多人对局，用批量成对 Bradley–Terry 评分比较模型与 Harness 的组合表现。</p>
        <div className="arena-meta"><b>{data?.tournament_id ?? "frontier12-model-harness-2026"}</b><span>UTC {data ? formatDate(data.generated_at) : "—"}</span></div>
      </div>
      <section className="arena-stats">
        <article><span>COMPLETED</span><strong>{data?.results.completed ?? "—"}<small> / {data?.results.scheduled ?? "—"}</small></strong></article>
        <article><span>SUCCESSFUL SESSIONS</span><strong>{data?.token_efficiency?.successful_sessions ?? "—"}</strong></article>
        <article><span>TOKEN COVERAGE</span><strong>{data?.token_efficiency ? percent(data.token_efficiency.coverage_rate) : data ? percent(completion) : "—"}</strong></article>
      </section>
    </header>
    {data && <EfficiencyCharts data={data}/>}
    <section className="arena-grid">
      <section className="leaderboard-card">
        <header>
          <div><span>PUBLIC RESULT SNAPSHOT</span><h2>综合排名</h2></div>
          <div className="sort-tabs" role="group" aria-label="榜单排序方式">
            {SORT_OPTIONS.map(([key, label]) => <button key={key} className={sortKey === key ? "active" : ""} onClick={() => setSortKey(key)}>{label}</button>)}
          </div>
        </header>
        <div className="rating-method"><b>{data?.rating.method ?? "batch-pairwise-bradley-terry"}</b><span>中心分 {data?.rating.centre ?? 1500} · 失败对局不计分但计为 failed exposure</span></div>
        <div className="ladder-head"><span>#</span><span>模型 × Harness</span><span>Elo / PWS</span><span>完成 / 表现</span></div>
        <div className="ladder-list" aria-live="polite">
          {!data && !error && <div className="arena-empty">正在载入实验结果…</div>}
          {error && <div className="arena-empty arena-error">{error}</div>}
          {entries.map((entry, index) => <article key={entry.participant_id}>
            <b className={`place place-${index + 1}`}>{String(index + 1).padStart(2, "0")}</b>
            <div className="competitor"><strong>{entry.display_name}</strong><span>{entry.model} · {entry.backend}</span><code>{entry.participant_id}</code></div>
            <div className="rating"><strong>{entry.elo.toFixed(1)}</strong><span>ELO</span><small>{percent(entry.pws)} PWS</small></div>
            <div className="record"><strong>{entry.completed}<span> / {entry.scheduled}</span></strong><progress max={entry.scheduled} value={entry.completed}/><small>{entry.first_place_equivalent.toFixed(1)} first-place eq. · avg #{entry.average_rank.toFixed(2)}</small></div>
          </article>)}
        </div>
      </section>
      <aside className="arena-side">
        <section className="coverage-card">
          <span>TOURNAMENT COVERAGE</span><h2>三款游戏，九个条件</h2>
          <div>{games.map(([game, matches]) => <article key={game}><div><strong>{GAME_NAMES[game] ?? game}</strong><span>{matches} scheduled</span></div><b style={{"--share": `${matches / (data?.schedule.matches ?? 1) * 100}%`} as CSSProperties}/></article>)}</div>
        </section>
        <section className="method-card">
          <span>FAIRNESS CHECKS</span><h2>配平设计</h2>
          <dl>
            <div><dt>每种游戏人数条件</dt><dd>{data?.schedule.appearances_per_condition ?? "—"} 次 / 配置</dd></div>
            <div><dt>选手两两相遇</dt><dd>{data ? `${data.schedule.pair_exposures.minimum}–${data.schedule.pair_exposures.maximum}` : "—"} 次</dd></div>
            <div><dt>零相遇组合</dt><dd>{data?.schedule.pair_exposures.zero_pairs ?? "—"}</dd></div>
            <div><dt>座位曝光</dt><dd>{data?.schedule.seat_exposures_per_stratum.exact ? "精确配平" : "近似配平"}</dd></div>
          </dl>
        </section>
        <section className="data-card">
          <span>REPRODUCIBLE DATA</span><h2>随仓库更新</h2>
          <p>该页面读取仓库中的脱敏结果快照。结果文件合入 <code>main</code> 后，GitHub Actions 会自动重新构建并发布。</p>
          <a href={DATA_URL}>下载当前 JSON →</a>
        </section>
      </aside>
    </section>
    <footer>Frontier12 public snapshot · {data?.dataset_id ?? "frontier12-2026-v2"} · failures are reported, not silently dropped</footer>
  </main>;
}
