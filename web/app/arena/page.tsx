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
  tournament_id: string;
};
type SortKey = "elo" | "pws" | "average_rank";

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
        <h1>十二种智能体配置，<br/>放上同一张<span>牌桌。</span></h1>
        <p>在 Splendor、Brass: Birmingham 与 7 Wonders 中进行座位配平的多人对局，用批量成对 Bradley–Terry 评分比较模型与 Harness 的组合表现。</p>
        <div className="arena-meta"><b>{data?.tournament_id ?? "frontier12-model-harness-2026"}</b><span>UTC {data ? formatDate(data.generated_at) : "—"}</span></div>
      </div>
      <section className="arena-stats">
        <article><span>COMPLETED</span><strong>{data?.results.completed ?? "—"}<small> / {data?.results.scheduled ?? "—"}</small></strong></article>
        <article><span>COMPLETION</span><strong>{data ? percent(completion) : "—"}</strong></article>
        <article><span>CONFIGURATIONS</span><strong>{data?.schedule.participants ?? "—"}</strong></article>
      </section>
    </header>
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
