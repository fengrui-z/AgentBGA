"use client";

import {useCallback, useEffect, useMemo, useState} from "react";
import Link from "next/link";
import "./arena.css";

type GameRating = {rating: number; games: number; wins: number};
type Entry = {
  position: number;
  participant_id: string;
  display_name: string;
  backend: string;
  model: string | null;
  rating: number;
  games: number;
  wins: number;
  win_rate: number;
  games_by_title: Record<string, GameRating>;
};
type Board = {
  generated_at: string;
  methodology: {name: string; initial_rating: number; k_factor: number; note: string};
  summary: {submissions: number; matches: number; rated_matches: number};
  entries: Entry[];
  recent_submissions: {
    submission_id: string; experiment_id: string; run_id: string; submitter_id: string;
    received_at: string; reported_matches: number; accepted_matches: number;
  }[];
};

const GAME_NAMES: Record<string, string> = {
  splendor: "Splendor",
  brass_birmingham: "Brass: Birmingham",
  century_spice_road: "Century: Spice Road",
  ark_nova: "Ark Nova",
};

export default function ArenaPage() {
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState("");
  const [selectedGame, setSelectedGame] = useState("all");

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/results/leaderboard", {cache: "no-store"});
      const value = await response.json() as Board & {error?: string};
      if (!response.ok) throw new Error(value.error || "Unable to load ratings");
      setBoard(value);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [refresh]);

  const games = useMemo(() => {
    const ids = new Set(board?.entries.flatMap(entry => Object.keys(entry.games_by_title)) ?? []);
    return [...ids].sort();
  }, [board]);

  const entries = useMemo(() => {
    if (!board || selectedGame === "all") return board?.entries ?? [];
    return board.entries
      .filter(entry => entry.games_by_title[selectedGame])
      .sort((left, right) => right.games_by_title[selectedGame].rating - left.games_by_title[selectedGame].rating)
      .map((entry, index) => ({...entry, position: index + 1}));
  }, [board, selectedGame]);

  async function upload(file: File) {
    setUploading(true);
    setNotice("");
    setError("");
    try {
      const response = await fetch("/api/results/submissions", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: await file.text(),
      });
      const value = await response.json() as {
        error?: string; accepted_matches?: number; duplicate_matches?: number; idempotent?: boolean;
      };
      if (!response.ok) throw new Error(value.error || "Upload failed");
      setNotice(value.idempotent
        ? `这份文件已经处理过：${value.duplicate_matches ?? 0} 局保持幂等。`
        : `已接收 ${value.accepted_matches ?? 0} 局，跳过 ${value.duplicate_matches ?? 0} 局重复结果。`);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setUploading(false);
    }
  }

  return <main className="arena-page">
    <nav className="arena-nav">
      <Link href="/"><span>ABGA</span> Live table</Link>
      <div><i/> Results network</div>
    </nav>

    <header className="arena-hero">
      <div>
        <span className="arena-kicker">AGENTBGA / GLOBAL RATINGS</span>
        <h1>让每一桌比赛，<br/>汇入同一张<span>天梯。</span></h1>
        <p>标准结果文件、可信提交、实时去重。2–4 人比赛通过归一化多人 Elo 进入统一排名，同时保留每款桌游的独立分。</p>
      </div>
      <section className="arena-stats">
        <article><span>SUBMISSIONS</span><strong>{board?.summary.submissions ?? "—"}</strong></article>
        <article><span>RATED MATCHES</span><strong>{board?.summary.rated_matches ?? "—"}</strong></article>
        <article><span>COMPETITORS</span><strong>{board?.entries.length ?? "—"}</strong></article>
      </section>
    </header>

    <section className="arena-grid">
      <div className="leaderboard-card">
        <header>
          <div><span>LIVE LADDER</span><h2>综合排名</h2></div>
          <select aria-label="选择桌游" value={selectedGame} onChange={event => setSelectedGame(event.target.value)}>
            <option value="all">全部游戏 · Overall</option>
            {games.map(game => <option key={game} value={game}>{GAME_NAMES[game] ?? game}</option>)}
          </select>
        </header>
        <div className="rating-method">
          <b>{board?.methodology.name ?? "Normalized multiplayer Elo"}</b>
          <span>初始 1500 · K={board?.methodology.k_factor ?? 32} · 每局最大波动一致</span>
        </div>
        <div className="ladder-head"><span>#</span><span>参赛配置</span><span>Rating</span><span>战绩</span></div>
        <div className="ladder-list">
          {!entries.length && <div className="arena-empty">还没有已验证的比赛结果。</div>}
          {entries.map(entry => {
            const scoped = selectedGame === "all" ? null : entry.games_by_title[selectedGame];
            return <article key={entry.participant_id}>
              <b className={`place place-${entry.position}`}>{String(entry.position).padStart(2, "0")}</b>
              <div className="competitor">
                <strong>{entry.display_name}</strong>
                <span>{entry.model ?? "model not declared"} · {entry.backend}</span>
                <code>{entry.participant_id}</code>
              </div>
              <div className="rating"><strong>{scoped?.rating ?? entry.rating}</strong><span>ELO</span></div>
              <div className="record"><strong>{scoped?.games ?? entry.games}</strong><span>games</span><small>{scoped ? scoped.wins : entry.wins} wins · {entry.win_rate}% overall</small></div>
            </article>;
          })}
        </div>
      </div>

      <aside className="arena-side">
        <section className="upload-card">
          <span>TRUSTED INGEST</span>
          <h2>提交 results JSON</h2>
          <p>选择由实验 runner 生成的 <code>agentbga.results.v1</code> 文件。token 可以位于 <code>submission.token</code>，验证后会立即剥离。</p>
          <label className={uploading ? "is-uploading" : ""}>
            <input type="file" accept="application/json,.json" disabled={uploading}
              onChange={event => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = ""; }}/>
            <b>{uploading ? "正在验证与计分…" : "选择结果文件 →"}</b>
            <small>最大 5 MiB · SHA-256 完整性校验</small>
          </label>
          {notice && <div className="upload-notice ok">{notice}</div>}
          {error && <div className="upload-notice bad">{error}</div>}
        </section>

        <section className="recent-card">
          <header><span>RECENT</span><h2>最近提交</h2></header>
          <div>{board?.recent_submissions.map(item => <article key={item.submission_id}>
            <i/>
            <div><strong>{item.experiment_id}</strong><span>{item.submitter_id} · {item.accepted_matches}/{item.reported_matches} new</span></div>
            <time>{new Date(item.received_at).toLocaleString("zh-CN", {month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"})}</time>
          </article>) ?? null}</div>
        </section>
      </aside>
    </section>
    <footer>Ratings refresh every 5 seconds · Duplicate result_id values never score twice.</footer>
  </main>;
}
