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
  mean_input_tokens_m: number; mean_cached_input_tokens_m: number; mean_output_tokens_m: number;
  mean_reasoning_tokens_m?: number;
  mean_input_cost_rmb: number; mean_cached_input_cost_rmb: number;
  mean_output_cost_rmb: number; mean_cost_rmb: number;
};
type GameTokenEntry = {
  participant_id: string; game: string; successful_sessions: number;
  mean_total_tokens_m: number; median_total_tokens_m: number;
  mean_input_tokens_m?: number; mean_cached_input_tokens_m?: number;
  mean_output_tokens_m?: number; elo?: number; elo_rank?: number;
  mean_reasoning_tokens_m?: number;
  mean_input_cost_rmb?: number; mean_cached_input_cost_rmb?: number;
  mean_output_cost_rmb?: number; mean_cost_rmb?: number;
};
type ModelPrice = {
  input_rmb_per_m: number; cached_input_rmb_per_m: number; output_rmb_per_m: number;
  source: string; source_url: string; price_note?: string; native_currency?: string;
};
type Pricing = {
  as_of: string; currency: string; unit: string; usd_cny: number;
  models: Record<string, ModelPrice>;
  sources: {id: string; label: string; url: string}[]; assumptions: string[];
};
type TokenEfficiency = {
  source_report: string; successful_sessions: number; coverage_rate: number;
  entries: TokenEntry[]; by_game: GameTokenEntry[]; pricing: Pricing;
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
type CostScope = "overall" | GameId;

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

function EfficiencyCharts({data}: {data: FrontierData}) {
  const [selectedGame, setSelectedGame] = useState<GameId>("splendor");
  const [selectedCostScope, setSelectedCostScope] = useState<CostScope>("overall");
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
  const costScopes: CostScope[] = ["overall", ...games];
  const scopeLabel = selectedCostScope === "overall" ? "Overall" : GAME_NAMES[selectedCostScope];
  const costComparison = (selectedCostScope === "overall"
    ? ordered.map(item => ({
        participant_id: item.participant_id,
        short_name: item.short_name,
        successful_sessions: item.successful_sessions,
        elo: item.rating.elo,
        backend: item.rating.backend,
        display_name: item.rating.display_name,
        mean_input_cost_rmb: item.mean_input_cost_rmb,
        mean_cached_input_cost_rmb: item.mean_cached_input_cost_rmb,
        mean_output_cost_rmb: item.mean_output_cost_rmb,
        mean_cost_rmb: item.mean_cost_rmb,
      }))
    : token.by_game
        .filter(item => item.game === selectedCostScope && item.elo != null && item.mean_cost_rmb != null)
        .flatMap(item => {
          const rating = data.leaderboard.find(entry => entry.participant_id === item.participant_id);
          const overall = tokens.get(item.participant_id);
          return rating && overall ? [{
            participant_id: item.participant_id,
            short_name: overall.short_name,
            successful_sessions: item.successful_sessions,
            elo: item.elo!,
            backend: rating.backend,
            display_name: rating.display_name,
            mean_input_cost_rmb: item.mean_input_cost_rmb!,
            mean_cached_input_cost_rmb: item.mean_cached_input_cost_rmb!,
            mean_output_cost_rmb: item.mean_output_cost_rmb!,
            mean_cost_rmb: item.mean_cost_rmb!,
          }] : [];
        }));
  const costFrontier = new Set(costComparison.filter(point => !costComparison.some(other =>
    other.participant_id !== point.participant_id
    && other.mean_cost_rmb <= point.mean_cost_rmb
    && other.elo >= point.elo
    && (other.mean_cost_rmb < point.mean_cost_rmb || other.elo > point.elo)
  )).map(point => point.participant_id));
  const maximumCost = niceCeiling(Math.max(...costComparison.map(item => item.mean_cost_rmb), 1));
  const costBars = [...costComparison].sort((left, right) => left.mean_cost_rmb - right.mean_cost_rmb);
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
      <p>成本以成功 session 的 provider token telemetry 估算，不等同于供应商账单；分游戏 Elo 均独立拟合。</p>
    </header>
    <div className="analysis-grid">
      <figure className="chart-card scatter-card cost-scatter-card">
        <figcaption className="chart-controls-caption">
          <div><strong>Elo × 估算 API 成本 / session</strong><span>横轴从 ¥0 开始，纵轴固定为 1200–2100；越靠左上越优，描边点属于当前视图的 Cost–Elo 前沿。</span></div>
          <div className="game-tabs cost-scope-tabs" role="tablist" aria-label="选择总体或分游戏成本与 Elo">
            {costScopes.map(scope => <button type="button" role="tab" aria-selected={selectedCostScope === scope} className={selectedCostScope === scope ? "active" : ""} key={scope} onClick={() => setSelectedCostScope(scope)}>{scope === "overall" ? "Overall" : GAME_NAMES[scope]}</button>)}
          </div>
        </figcaption>
        <div className="scatter-wrap">
          <div className="scatter-y-label">Elo ↑</div>
          <div className="scatter-stage" role="img" aria-label={`${scopeLabel} Elo 与人民币估算成本散点图`}>
            {[2100, 1800, 1500, 1200].map(value => <span className="y-tick" key={value} style={{"--tick": `${(2100 - value) / 900 * 100}%`} as CSSProperties}>{value}</span>)}
            {[0, .25, .5, .75, 1].map(ratio => <span className="x-tick" key={ratio} style={{"--tick": `${ratio * 100}%`} as CSSProperties}>{rmb(maximumCost * ratio)}</span>)}
            {costComparison.map(item => {
              const x = clamp(item.mean_cost_rmb / maximumCost * 100, 1, 99);
              const y = clamp((2100 - item.elo) / 900 * 100, 1, 99);
              const size = 11 + clamp((item.successful_sessions - 40) / 50, 0, 1) * 8;
              const frontier = costFrontier.has(item.participant_id);
              return <button type="button" key={item.participant_id} aria-label={`${item.display_name}: ${item.elo.toFixed(1)} Elo, ${rmb(item.mean_cost_rmb)} per successful session, ${item.successful_sessions} sessions`} className={`scatter-point backend-${item.backend} ${frontier ? "is-frontier" : ""}`} style={{"--x": `${x}%`, "--y": `${y}%`, "--size": `${size}px`} as CSSProperties}>
                {frontier && <em>{item.short_name}</em>}
                <b>{item.display_name}</b><small>{item.elo.toFixed(1)} Elo · {rmb(item.mean_cost_rmb)} / session · {item.successful_sessions} sessions</small>
              </button>;
            })}
          </div>
          <div className="scatter-x-label">估算 API 成本（RMB / 成功 session）→</div>
        </div>
      </figure>
      <figure className="chart-card cost-bars-card">
        <figcaption><strong>{scopeLabel} 成本构成对比</strong><span>同一横轴下拆分 Input（非缓存）、Cached input 与 Output；按总成本从低到高排列。</span></figcaption>
        <div className="cost-bar-list">
          {costBars.map(item => <div className="cost-bar-row" key={item.participant_id}>
            <span>{item.short_name}</span>
            <div className="cost-stack" role="img" aria-label={`${item.display_name}: input ${rmb(item.mean_input_cost_rmb)}, cached input ${rmb(item.mean_cached_input_cost_rmb)}, output ${rmb(item.mean_output_cost_rmb)}, total ${rmb(item.mean_cost_rmb)}`}>
              <i className="cost-input" style={{width: `${item.mean_input_cost_rmb / maximumCost * 100}%`}} title={`Input ${rmb(item.mean_input_cost_rmb)}`}/>
              <i className="cost-cached" style={{width: `${item.mean_cached_input_cost_rmb / maximumCost * 100}%`}} title={`Cached input ${rmb(item.mean_cached_input_cost_rmb)}`}/>
              <i className="cost-output" style={{width: `${item.mean_output_cost_rmb / maximumCost * 100}%`}} title={`Output ${rmb(item.mean_output_cost_rmb)}`}/>
            </div>
            <strong>{rmb(item.mean_cost_rmb)}</strong>
          </div>)}
        </div>
        <div className="game-token-legend cost-legend"><span><i className="cost-input"/>Input（非缓存）</span><span><i className="cost-cached"/>Cached input</span><span><i className="cost-output"/>Output（含 reasoning）</span><small>RMB / 成功 session</small></div>
      </figure>
      <figure className="chart-card pricing-card">
        <figcaption><strong>计价表（RMB / 1M tokens）</strong><span>千问模型市场直接采用人民币价；GPT 使用 OpenAI 官方 API 美元价按 USD/CNY {token.pricing.usd_cny} 折算。</span></figcaption>
        <div className="pricing-scroll"><table>
          <thead><tr><th>Model</th><th>Input</th><th>Cached input</th><th>Output</th><th>口径</th></tr></thead>
          <tbody>{Object.entries(token.pricing.models).map(([model, price]) => <tr key={model}>
            <th><a href={price.source_url} target="_blank" rel="noreferrer">{model}</a></th><td>{rmb(price.input_rmb_per_m)}</td><td>{rmb(price.cached_input_rmb_per_m)}</td><td>{rmb(price.output_rmb_per_m)}</td><td>{price.source === "openai" ? "OpenAI · FX 折算" : "千问 AI"}{price.price_note ? <small>{price.price_note}</small> : null}</td>
          </tr>)}</tbody>
        </table></div>
        <div className="pricing-notes">
          <p><b>估算公式</b> uncached input M × input price + cached input M × cached price + output（含 reasoning）M × output price。</p>
          <ul>{token.pricing.assumptions.map(note => <li key={note}>{note}</li>)}</ul>
          <p className="pricing-sources">价格日期 {token.pricing.as_of} · {token.pricing.sources.map((source, index) => <span key={source.id}>{index > 0 && " · "}<a href={source.url} target="_blank" rel="noreferrer">{source.label}</a></span>)}</p>
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
        <div className="game-token-legend"><span><i className="token-input"/>Input（非缓存）</span><span><i className="token-cached"/>Cached input</span><span><i className="token-output"/>Output（含 reasoning）</span><small>条长按当前游戏最高总量统一缩放</small></div>
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
