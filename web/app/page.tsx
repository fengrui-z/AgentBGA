"use client";

import { useMemo, useRef, useState } from "react";

type Backend = "openai" | "anthropic" | "gemini" | "claude" | "pi" | "codex" | "opencode" | "random";
type Provider = "custom" | "claude_code" | "pi" | "codex" | "opencode" | "deepseek" | "dashscope" | "zhipu" | "minimax";
type PlayerForm = { id: string; name: string; provider: Provider; backend: Backend; model: string; base_url: string; api_key: string };
type Card = { id: string; tier: number; bonus: string; points: number; cost: Record<string, number> };
type PlayerView = {
  seat: number; tokens: Record<string, number>; bonuses: Record<string, number>; score: number;
  purchased_count: number; purchased: Card[]; reserved_count: number; reserved: (Card | {hidden: true})[];
  nobles: {id: string; points: number; required: Record<string, number>}[];
};
type View = {
  status: string; active_seat: number; turn_count: number; phase: string; bank: Record<string, number>;
  market: Record<string, Card[]>; deck_counts: Record<string, number>; players: PlayerView[];
  available_nobles: {id: string; points: number; required: Record<string, number>}[];
};
type Snapshot = {
  match_id: string; version: number; status: string; turn_count: number; active_seat: number;
  paused: boolean; pause_pending: boolean;
  players: {seat: number; name: string; backend: string; model?: string; reasoning_effort?: string}[]; views: View[];
};
type TimelineEvent = {
  type: string; player?: string; seat?: number; error?: string; turns?: number;
  backend?: string; agent?: {latency_ms?: number}; action?: Record<string, unknown>;
  rankings?: {player: string}[]; channel?: "reasoning" | "content"; delta?: string; attempt?: number; version?: number;
  harness?: string; tool?: string; arguments?: unknown; result?: unknown; action_id?: string;
};
type Timeline = { seq: number; event: TimelineEvent; snapshot?: Snapshot };
type ChatTurn = {
  key: string; seat: number; player: string; backend: string; attempt: number;
  reasoning: string; content: string; status: "thinking" | "done" | "error";
  startedAt: number; latencyMs?: number;
};

const GEM_META: Record<string, {label: string; mark: string}> = {
  white: { label: "钻石", mark: "◇" }, blue: { label: "蓝宝石", mark: "◆" },
  green: { label: "祖母绿", mark: "⬟" }, red: { label: "红宝石", mark: "●" },
  black: { label: "玛瑙", mark: "⬢" }, gold: { label: "黄金", mark: "★" },
};
const BACKENDS: Record<Backend, {label: string; url: string; key: string; model: string}> = {
  openai: { label: "OpenAI 兼容", url: "https://api.openai.com/v1", key: "", model: "" },
  anthropic: { label: "Anthropic", url: "https://api.anthropic.com", key: "", model: "" },
  gemini: { label: "Gemini", url: "https://generativelanguage.googleapis.com/v1beta", key: "", model: "" },
  claude: { label: "Claude Code", url: "https://api.anthropic.com", key: "", model: "" },
  pi: { label: "Pi", url: "https://api.openai.com/v1", key: "", model: "" },
  codex: { label: "Codex Harness", url: "https://api.openai.com/v1", key: "", model: "" },
  opencode: { label: "OpenCode Harness", url: "https://api.deepseek.com", key: "", model: "" },
  random: { label: "随机基线", url: "", key: "", model: "" },
};
const PROVIDERS: Record<Provider, {label: string; backend: Backend; url: string; models: string[]; note: string}> = {
  custom: {label: "自定义 / 代理平台", backend: "openai", url: "", models: [], note: "手动填写协议、Endpoint 和模型 ID"},
  claude_code: {label: "Claude Code", backend: "claude", url: "https://api.anthropic.com", models: ["claude-sonnet-4-6", "claude-opus-4-6"], note: "Claude Code 持久 session + 座位隔离 MCP"},
  pi: {label: "Pi", backend: "pi", url: "https://api.openai.com/v1", models: ["gpt-5.6"], note: "Pi 持久 session + AgentBGA 专用工具扩展；兼容自定义 OpenAI Endpoint"},
  codex: {label: "Codex", backend: "codex", url: "https://api.openai.com/v1", models: ["gpt-5.6", "gpt-5.6-terra", "gpt-5.3-codex"], note: "Codex 持久 session + 座位隔离 MCP；自定义 Endpoint 自动使用兼容协议"},
  opencode: {label: "OpenCode", backend: "opencode", url: "https://api.deepseek.com", models: ["deepseek-v4-flash", "deepseek-v4-pro"], note: "OpenCode 持久 session + 座位隔离 MCP"},
  deepseek: {label: "DeepSeek 官方", backend: "openai", url: "https://api.deepseek.com", models: ["deepseek-v4-flash", "deepseek-v4-pro"], note: "官方按量付费 API"},
  dashscope: {label: "阿里云百炼", backend: "openai", url: "https://dashscope.aliyuncs.com/compatible-mode/v1", models: ["qwen3.7-plus", "qwen3.6-plus", "qwen3.5-flash", "qwen3.7-max"], note: "华北 2 按量付费，不是 Coding Plan"},
  zhipu: {label: "智谱开放平台", backend: "openai", url: "https://open.bigmodel.cn/api/paas/v4", models: ["glm-5.2", "glm-5", "glm-4.7"], note: "开放平台按量付费 Endpoint"},
  minimax: {label: "MiniMax 官方", backend: "openai", url: "https://api.minimaxi.com/v1", models: ["MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.5-highspeed"], note: "国内开放平台 OpenAI 兼容 API"},
};

function player(seed: number, backend: Backend = "openai"): PlayerForm {
  return { id: crypto.randomUUID(), name: `Agent ${seed}`, provider: "custom", backend, model: "", base_url: BACKENDS[backend].url, api_key: "" };
}

function deepseekHarnessPlayer(seed: number, backend: "opencode" | "codex"): PlayerForm {
  return {
    id: crypto.randomUUID(), name: `Agent ${seed}`, provider: backend, backend,
    model: "deepseek-v4-flash", base_url: "https://api.deepseek.com", api_key: "",
  };
}

function api(path: string) { return path; }

function Gem({color, value, compact = false}: {color: string; value: number; compact?: boolean}) {
  const meta = GEM_META[color];
  return <span className={`gem gem-${color} ${compact ? "gem-compact" : ""}`} title={meta?.label}>
    <b>{meta?.mark}</b><span>{value}</span>
  </span>;
}

function Cost({cost}: {cost: Record<string, number>}) {
  return <div className="costs">{Object.entries(cost).filter(([, amount]) => amount > 0).map(([color, amount]) =>
    <Gem key={color} color={color} value={amount} compact />
  )}</div>;
}

function DevCard({card, small = false}: {card: Card; small?: boolean}) {
  return <article className={`dev-card card-${card.bonus} ${small ? "dev-card-small" : ""}`} title={card.id}>
    <div className="card-top"><strong>{card.points || "·"}</strong><span>{GEM_META[card.bonus]?.mark}</span></div>
    <Cost cost={card.cost} />
  </article>;
}

function PlayerPanel({player: p, identity, active}: {player: PlayerView; identity?: Snapshot["players"][number]; active: boolean}) {
  return <section className={`player-panel ${active ? "active-player" : ""}`}>
    <header>
      <div><span className="seat-label">座位 {p.seat + 1}</span><h3>{identity?.name || `Agent ${p.seat + 1}`}</h3></div>
      <div className="score"><strong>{p.score}</strong><span>声望</span></div>
    </header>
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}{identity?.reasoning_effort && <b>思考：最高</b>}</div>
    <div className="asset-row"><span className="asset-title">宝石</span><div>{Object.keys(GEM_META).map(c => <Gem key={c} color={c} value={p.tokens[c]} compact />)}</div></div>
    <div className="asset-row"><span className="asset-title">引擎</span><div>{Object.keys(GEM_META).slice(0, 5).map(c => <Gem key={c} color={c} value={p.bonuses[c]} compact />)}</div></div>
    <div className="owned-head"><span>已购发展牌</span><b>{p.purchased_count}</b></div>
    <div className="owned-cards">{p.purchased.length ? p.purchased.map(card => <DevCard key={card.id} card={card} small />) : <em>尚未建立引擎</em>}</div>
    <div className="reserve-row"><span>预留 {p.reserved_count}/3</span><div>{p.reserved.map((card, i) => "hidden" in card ? <i key={i}>?</i> : <DevCard key={card.id} card={card} small />)}</div></div>
    {p.nobles.length > 0 && <div className="noble-owned">贵族 × {p.nobles.length}</div>}
  </section>;
}

function describeAction(item: Timeline, names: Record<number, string>) {
  const event = item.event;
  if (event.type === "agent_error") return `${event.player} 调用失败：${event.error}`;
  if (event.type === "match_failed") return `对局中止：${event.error}`;
  if (event.type === "match_finished") return `对局结束，共 ${event.turns} 回合`;
  if (event.type === "pause_requested") return "暂停已请求，将在当前模型完成本手后生效";
  if (event.type === "match_paused") return "对局已暂停在回合边界";
  if (event.type === "match_resumed") return "对局继续";
  if (event.type === "harness_tool_call") return `${event.player} 调用工具 ${event.tool}`;
  if (event.type === "harness_tool_result") return `${event.player} 收到 ${event.tool} 结果`;
  if (event.type === "harness_finished") return `${event.player} 通过 ${event.harness} 提交 ${event.action_id}`;
  if (event.type === "harness_error") return `${event.player} Harness 失败：${event.error}`;
  if (event.type !== "turn") return event.type;
  const seat = event.seat ?? 0;
  const who = event.player || names[seat] || `座位 ${seat + 1}`;
  const action = event.action ?? {};
  if (action.type === "take_tokens") {
    const take = Object.entries((action.take ?? {}) as Record<string, number>).map(([c, n]) => `${GEM_META[c]?.label}×${n}`).join("、");
    const returned = Object.entries((action.return ?? {}) as Record<string, number>).map(([c, n]) => `${GEM_META[c]?.label}×${n}`).join("、");
    return `${who} 拿取 ${take}${returned ? `，归还 ${returned}` : ""}`;
  }
  if (action.type === "buy_visible" || action.type === "buy_reserved") return `${who} 购买 ${action.card_id}`;
  if (action.type === "reserve_visible") return `${who} 预留公开牌 ${action.card_id}`;
  if (action.type === "reserve_deck") return `${who} 从 ${action.tier} 阶牌库暗中预留一张牌`;
  if (action.type === "choose_noble") return `${who} 获得贵族 ${action.noble_id}`;
  if (action.type === "pass") return `${who} 无合法行动，跳过回合`;
  return `${who}：${action.type}`;
}

export default function Home() {
  const [players, setPlayers] = useState<PlayerForm[]>([
    deepseekHarnessPlayer(1, "opencode"),
    deepseekHarnessPlayer(2, "codex"),
  ]);
  const [seed, setSeed] = useState("42");
  const [speed, setSpeed] = useState(650);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [timeline, setTimeline] = useState<Timeline[]>([]);
  const [chat, setChat] = useState<ChatTurn[]>([]);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [controlling, setControlling] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);
  const view = snapshot?.views[0];
  const names = useMemo(() => Object.fromEntries((snapshot?.players || []).map(p => [p.seat, p.name])), [snapshot]);

  function updatePlayer(id: string, patch: Partial<PlayerForm>) {
    setPlayers(current => current.map(p => {
      if (p.id !== id) return p;
      if (patch.backend && patch.backend !== p.backend) {
        const defaults = BACKENDS[patch.backend];
        return {...p, ...patch, provider: "custom", base_url: defaults.url, model: "", api_key: ""};
      }
      return {...p, ...patch};
    }));
  }

  function selectProvider(id: string, provider: Provider) {
    const preset = PROVIDERS[provider];
    setPlayers(current => current.map(p => p.id === id ? {
      ...p, provider, backend: provider === "custom" ? p.backend : preset.backend,
      base_url: provider === "custom" ? p.base_url : preset.url,
      model: provider === "custom" ? p.model : preset.models[0],
    } : p));
  }

  async function startMatch() {
    setStarting(true); setError(""); setTimeline([]); setChat([]); sourceRef.current?.close();
    try {
      const response = await fetch(api("/api/matches"), {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          seed: seed === "" ? null : Number(seed), speed_ms: speed,
          players: players.map(p => ({
            name: p.name, backend: p.backend, model: p.model,
            base_url: p.base_url, api_key: p.api_key,
          })),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || "无法启动对局");
      setSnapshot(data);
      const source = new EventSource(api(`/api/matches/${data.match_id}/events`));
      source.addEventListener("match", raw => {
        const item: Timeline = JSON.parse((raw as MessageEvent).data);
        if (item.snapshot) setSnapshot(item.snapshot);
        const event = item.event;
        const seat = event.seat ?? 0;
        const attempt = event.attempt ?? 1;
        const key = `${event.version ?? item.snapshot?.version ?? data.version}:${seat}:${attempt}`;
        if (event.type === "agent_started") {
          setChat(current => [...current, {key, seat, attempt, player: event.player || `Agent ${seat + 1}`,
            backend: event.backend || "model", reasoning: "", content: "", status: "thinking", startedAt: Date.now()}]);
        } else if (event.type === "agent_stream" || event.type === "harness_output") {
          setChat(current => {
            const index = [...current].reverse().findIndex(turn => turn.seat === seat && turn.attempt === attempt && turn.status === "thinking");
            if (index < 0) return current;
            const actual = current.length - 1 - index;
            return current.map((turn, i) => i === actual ? {...turn,
              [event.channel === "reasoning" ? "reasoning" : "content"]:
                turn[event.channel === "reasoning" ? "reasoning" : "content"] + (event.delta || "")
            } : turn);
          });
        } else if (event.type === "agent_finished" || event.type === "agent_error") {
          setChat(current => {
            const index = [...current].reverse().findIndex(turn => turn.seat === seat && turn.attempt === attempt && turn.status === "thinking");
            if (index < 0) return current;
            const actual = current.length - 1 - index;
            return current.map((turn, i) => i === actual ? {...turn,
              status: event.type === "agent_error" ? "error" : "done",
              latencyMs: event.agent?.latency_ms,
              content: event.type === "agent_error" && !turn.content ? event.error || "调用失败" : turn.content,
            } : turn);
          });
        }
        if (!["agent_stream", "harness_output"].includes(event.type)) setTimeline(current => [...current, item]);
        if (["match_finished", "match_failed"].includes(item.event.type)) source.close();
      });
      source.onerror = () => {
        if (source.readyState === EventSource.CLOSED) setError("实时连接已断开，可刷新页面后重新开始。");
      };
      sourceRef.current = source;
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setStarting(false); }
  }

  async function togglePause() {
    if (!snapshot || snapshot.status !== "active") return;
    setControlling(true); setError("");
    try {
      const action = snapshot.paused ? "resume" : "pause";
      const response = await fetch(api(`/api/matches/${snapshot.match_id}/${action}`), {method: "POST"});
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || "无法更新暂停状态");
      setSnapshot(data);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setControlling(false); }
  }

  if (!snapshot) return <main className="setup-shell">
    <section className="hero">
      <div className="eyebrow">AGENT BOARD GAME ARENA / SPLENDOR</div>
      <h1>把模型放上牌桌，<br/><i>看见</i>每一次决策。</h1>
      <p>配置 2–4 名不同模型。所有 Agent Harness 固定使用最高思考强度；API 密钥只进入本机进程内存，不会写入浏览器存储、对局数据库或日志。</p>
      <div className="hero-marks"><span>实时行动</span><span>完整引擎</span><span>逐步回放</span></div>
    </section>
    <section className="setup-card">
      <header><div><span>NEW TABLE</span><h2>创建一桌璀璨宝石</h2></div><b>{players.length} PLAYERS</b></header>
      <div className="players-config">{players.map((p, index) => <article className="player-config" key={p.id}>
        <div className="config-index">0{index + 1}</div>
        <div className="field grow"><label htmlFor={`${p.id}-name`}>选手名</label><input id={`${p.id}-name`} value={p.name} onChange={e => updatePlayer(p.id, {name: e.target.value})}/></div>
        {p.backend !== "random" && <>
          <div className="field provider-field"><label htmlFor={`${p.id}-provider`}>Harness / 服务商</label><select id={`${p.id}-provider`} value={p.provider} onChange={e => selectProvider(p.id, e.target.value as Provider)}><optgroup label="Agent Harness">{(["claude_code", "pi", "codex", "opencode"] as Provider[]).map(id => <option key={id} value={id}>{PROVIDERS[id].label}</option>)}</optgroup><optgroup label="直连模型 API">{(["custom", "deepseek", "dashscope", "zhipu", "minimax"] as Provider[]).map(id => <option key={id} value={id}>{PROVIDERS[id].label}</option>)}</optgroup></select></div>
          <div className="field backend-field"><label htmlFor={`${p.id}-backend`}>运行方式</label><select id={`${p.id}-backend`} value={p.backend} onChange={e => updatePlayer(p.id, {backend: e.target.value as Backend})}>{Object.entries(BACKENDS).filter(([id]) => id !== "random").map(([id, b]) => <option key={id} value={id}>{b.label}</option>)}</select></div>
          <div className="field grow endpoint-field"><label htmlFor={`${p.id}-endpoint`}>Endpoint</label><input id={`${p.id}-endpoint`} value={p.base_url} onChange={e => updatePlayer(p.id, {provider: "custom", base_url: e.target.value})}/></div>
          <div className="field model-field"><label htmlFor={`${p.id}-model`}>模型名</label><input id={`${p.id}-model`} list={`${p.id}-models`} placeholder="可选择或输入 model-id" value={p.model} onChange={e => updatePlayer(p.id, {model: e.target.value})}/><datalist id={`${p.id}-models`}>{PROVIDERS[p.provider].models.map(model => <option key={model} value={model}/>)}</datalist></div>
          <div className="field key-field"><label htmlFor={`${p.id}-key`}>API Key</label><input id={`${p.id}-key`} type="password" autoComplete="off" placeholder="仅在本次对局使用" value={p.api_key} onChange={e => updatePlayer(p.id, {api_key: e.target.value})}/></div>
          <div className="provider-note">{PROVIDERS[p.provider].note}</div>
        </>}
        {p.backend === "random" && <div className="field"><label htmlFor={`${p.id}-backend`}>Backend</label><select id={`${p.id}-backend`} value={p.backend} onChange={e => updatePlayer(p.id, {backend: e.target.value as Backend})}>{Object.entries(BACKENDS).map(([id, b]) => <option key={id} value={id}>{b.label}</option>)}</select></div>}
        {players.length > 2 && <button className="remove" aria-label={`移除 ${p.name}`} onClick={() => setPlayers(x => x.filter(y => y.id !== p.id))}>×</button>}
      </article>)}</div>
      <div className="setup-actions">
        <button className="add-player" disabled={players.length >= 4} onClick={() => setPlayers(x => [...x, player(x.length + 1, "random")])}>＋ 添加选手</button>
        <div className="field mini"><label htmlFor="match-seed">Seed</label><input id="match-seed" inputMode="numeric" value={seed} onChange={e => setSeed(e.target.value)}/></div>
        <div className="field mini speed"><label htmlFor="match-speed">每步间隔 <b>{speed}ms</b></label><input id="match-speed" type="range" min="0" max="2000" step="50" value={speed} onChange={e => setSpeed(Number(e.target.value))}/></div>
        <button className="start" disabled={starting} onClick={startMatch}>{starting ? "正在入席…" : "开始对局 →"}</button>
      </div>
      {error && <div className="error">{error}</div>}
    </section>
  </main>;

  return <main className="table-shell">
    <header className="table-header">
      <div><span className="brand-mark">ABGA</span><strong>Splendor Live Table</strong></div>
      <div className="match-meta"><span>对局 <code>{snapshot.match_id}</code></span><span>回合 <b>{snapshot.turn_count}</b></span><span className={`status ${snapshot.paused ? "status-paused" : `status-${snapshot.status}`}`}>{snapshot.status !== "active" ? "已结束" : snapshot.paused ? (snapshot.pause_pending ? "等待暂停" : "已暂停") : "进行中"}</span></div>
      <div className="table-actions">
        <button className={`pause-button ${snapshot.paused ? "is-paused" : ""}`} disabled={snapshot.status !== "active" || controlling} aria-pressed={snapshot.paused} onClick={togglePause}>{controlling ? "处理中…" : snapshot.paused ? "▶ 继续对局" : "Ⅱ 暂停"}</button>
        <button onClick={() => { sourceRef.current?.close(); setSnapshot(null); setTimeline([]); setChat([]); setError(""); }}>新对局</button>
      </div>
    </header>
    {error && <div className="table-error" role="alert">{error}</div>}
    <div className="table-grid">
      <aside className="players-column">{snapshot.players.map(identity => {
        // The spectator sees each agent's own observation. Agents still receive only their seat's view.
        const ownView = snapshot.views[identity.seat];
        const ownPlayer = ownView.players[identity.seat];
        return <PlayerPanel key={identity.seat} player={ownPlayer} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>;
      })}</aside>
      <section className="board">
        {snapshot.paused && <div className={`pause-notice ${snapshot.pause_pending ? "pending" : ""}`}><strong>{snapshot.pause_pending ? "等待当前模型完成…" : "对局已暂停"}</strong><span>{snapshot.pause_pending ? "返回的这一手会正常落盘，下一位不会开始思考。" : "牌桌停在安全的回合边界，点击“继续对局”即可恢复。"}</span></div>}
        <div className="bank-bar"><div><small>供应区</small><strong>宝石银行</strong></div>{view && Object.keys(GEM_META).map(c => <Gem key={c} color={c} value={view.bank[c]}/>)}</div>
        <section className="nobles"><header><span>贵族</span><b>{view?.available_nobles.length || 0} AVAILABLE</b></header><div>{view?.available_nobles.map(n => <article key={n.id}><strong>3</strong><Cost cost={n.required}/></article>)}</div></section>
        <section className="market">{[3,2,1].map(tier => <div className="tier" key={tier}>
          <div className="tier-label"><span>TIER</span><strong>0{tier}</strong><small>{view?.deck_counts[String(tier)]} 张</small></div>
          <div className="market-cards">{view?.market[String(tier)].map(card => <DevCard key={card.id} card={card}/>)}</div>
        </div>)}</section>
        {snapshot.status === "finished" && <div className="winner-banner"><span>WINNER</span><strong>{timeline.at(-1)?.event.rankings?.[0]?.player || "对局结束"}</strong><button onClick={() => { setSnapshot(null); setTimeline([]); }}>再来一局</button></div>}
      </section>
      <aside className="timeline">
        <header><div><span>MODEL STREAM</span><h2>模型 Chat</h2></div><i className={snapshot.status === "active" && (!snapshot.paused || snapshot.pause_pending) ? "pulse" : ""}/></header>
        <div className="chat-list">{chat.length === 0 && <p className="waiting">等待模型开始思考…</p>}{chat.map(turn => <article className={`chat-turn chat-${turn.status}`} key={turn.key}>
          <header><strong>{turn.player}</strong><span>{turn.backend} · 尝试 {turn.attempt}{turn.status === "thinking" ? " · 生成中" : turn.latencyMs ? ` · ${(turn.latencyMs / 1000).toFixed(1)}s` : ""}</span></header>
          {turn.reasoning && <details open><summary>思考过程{turn.status === "done" ? " · 可折叠" : ""}</summary><pre>{turn.reasoning}</pre></details>}
          {turn.content && <div className="model-answer"><b>回复</b><pre>{turn.content}</pre></div>}
          {turn.status === "thinking" && <div className="typing"><i/><i/><i/></div>}
        </article>)}</div>
        <section className="action-drawer"><header><span>ACTIONS</span><strong>行动记录</strong><b>{timeline.filter(item => item.event.type === "turn").length}</b></header>
          <div>{[...timeline].reverse().filter(item => !["agent_started", "agent_finished"].includes(item.event.type)).slice(0, 40).map(item => <article key={item.seq} className={`event event-${item.event.type}`}>
            <span>{String(item.seq + 1).padStart(3,"0")}</span><div><p>{describeAction(item, names)}</p>{item.event.backend && <small>{item.event.backend}{item.event.agent?.latency_ms ? ` · ${item.event.agent.latency_ms}ms` : ""}</small>}
              {item.event.tool && (item.event.arguments !== undefined || item.event.result !== undefined) && <details className="tool-payload"><summary>查看工具数据</summary><pre>{JSON.stringify(item.event.result ?? item.event.arguments, null, 2)}</pre></details>}
            </div>
          </article>)}</div>
        </section>
      </aside>
    </div>
  </main>;
}
