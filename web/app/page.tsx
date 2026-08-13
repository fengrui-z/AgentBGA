"use client";

import { useMemo, useRef, useState } from "react";

type Backend = "openai" | "anthropic" | "gemini" | "claude" | "pi" | "codex" | "opencode" | "human" | "random";
type Provider = "custom" | "claude_code" | "pi" | "codex" | "opencode" | "deepseek" | "dashscope" | "zhipu" | "minimax";
type GameId = "splendor" | "ark_nova";
type PlayerForm = { id: string; name: string; provider: Provider; backend: Backend; model: string; base_url: string; api_key: string };
type Card = { id: string; tier: number; bonus: string; points: number; cost: Record<string, number> };
type PlayerView = {
  seat: number; tokens: Record<string, number>; bonuses: Record<string, number>; score: number;
  purchased_count: number; purchased: Card[]; reserved_count: number; reserved: (Card | {hidden: true})[];
  nobles: {id: string; points: number; required: Record<string, number>}[];
};
type View = {
  game: "splendor"; status: string; active_seat: number; turn_count: number; phase: string; bank: Record<string, number>;
  market: Record<string, Card[]>; deck_counts: Record<string, number>; players: PlayerView[];
  available_nobles: {id: string; points: number; required: Record<string, number>}[];
};
type ArkCard = {id?: string; card_type?: string; tags?: string[]; implementation?: string; hidden?: true};
type ArkActionCard = {action: string; strength: number; upgraded: boolean; tokens: string[]};
type ArkMap = {
  id: string; name: string; geometry_status: string;
  cells: {q: number; r: number; terrain: "water" | "rock" | "buildable"}[];
  buildings: {id: string; type: string; size: number; occupied: boolean; cells: {q: number; r: number}[]}[];
};
type ArkPlayerView = {
  seat: number; money: number; x_tokens: number; appeal: number; conservation: number; reputation: number;
  action_cards: ArkActionCard[]; association_workers: {active: number; reserve: number; committed: unknown[]};
  partner_zoos: string[]; universities: string[]; map: ArkMap; hand_count: number; initial_draw_count: number;
  initial_keep_required: number; hand: ArkCard[]; initial_draw: ArkCard[]; played_cards: ArkCard[]; final_scoring_cards: (ArkCard | {hidden: true})[];
};
type ArkView = {
  game: "ark_nova"; rules_version: string; implementation_status: string; status: string; phase: string;
  turn_count: number; decision_count: number; active_seat: number; turn: {active_seat: number; decision: string; action_card: string | null; remaining_plays: number};
  break_track: {position: number; start_marker: string; triggered: boolean}; card_display: ArkCard[];
  game_board_bonus_tiles: {id: string; implementation: string}[];
  deck_count: number; discard_count: number; base_conservation_projects: {id: string; tag: string; levels: number[]}[];
  association_board: {partner_zoos: Record<string, number>; universities: Record<string, number>; blocked_two_player: string[]};
  players: ArkPlayerView[];
};
type GameDescription = {id: GameId; name: string; rules_version: string; implementation_status: string; runnable: boolean};
type Snapshot = {
  match_id: string; game: GameId; game_description: GameDescription; version: number; status: string; turn_count: number; decision_count?: number; active_seat: number;
  paused: boolean; pause_pending: boolean;
  human_turn?: {seat: number; player: string; version: number; legal_actions: LegalAction[]} | null;
  players: {seat: number; name: string; backend: string; model?: string; reasoning_effort?: string}[]; views: (View | ArkView)[];
};
type LegalAction = {id: string; action: Record<string, unknown>};
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
  human: { label: "人类玩家", url: "", key: "", model: "" },
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

function humanPlayer(seed: number): PlayerForm {
  return {id: crypto.randomUUID(), name: seed === 1 ? "你" : `玩家 ${seed}`, provider: "custom", backend: "human", model: "", base_url: "", api_key: ""};
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
  if (!["decision", "turn"].includes(event.type)) return event.type;
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
  if (["choose_initial_hand", "select_action", "take_x_token", "draw_cards", "snap_card",
    "discard_card", "break_discard", "place_building", "play_animal", "association_task",
    "play_sponsor", "advance_break", "finish_action"].includes(String(action.type))) {
    return `${who}：${humanActionText(action)}`;
  }
  return `${who}：${action.type}`;
}

function tokenText(tokens: Record<string, number>) {
  return Object.entries(tokens).filter(([, count]) => count > 0)
    .map(([color, count]) => `${GEM_META[color]?.label || color} × ${count}`).join("、");
}

function humanActionText(action: Record<string, unknown>) {
  if (action.type === "choose_initial_hand") return `保留 ${(action.card_ids as string[]).join("、")}`;
  if (action.type === "select_action") return `使用 ${ARK_ACTION_LABELS[String(action.action_card)] || action.action_card}，强度 ${action.strength}${action.x_tokens ? `（X +${action.x_tokens}）` : ""}`;
  if (action.type === "take_x_token") return `将 ${ARK_ACTION_LABELS[String(action.action_card)] || action.action_card} 移到 1 并获得 X token`;
  if (action.type === "draw_cards") return `抽 ${action.draw_count} 张牌${action.discard_count ? `，再弃 ${action.discard_count} 张` : ""}`;
  if (action.type === "snap_card") return `拿取展示区 ${action.card_id}`;
  if (action.type === "discard_card" || action.type === "break_discard") return `弃牌 ${action.card_id || (action.card_ids as string[]).join("、")}`;
  if (action.type === "place_building") return `建造 ${action.building_type}（${action.size} 格，₡${action.cost}）`;
  if (action.type === "play_animal") return `打出动物 ${action.card_id}，使用 ${action.enclosure_id}`;
  if (action.type === "association_task") return `协会任务：${action.task}`;
  if (action.type === "play_sponsor") return `打出赞助商 ${action.card_id}`;
  if (action.type === "advance_break") return `推进 Break ${action.steps} 格，获得 ₡${action.money}`;
  if (action.type === "finish_action") return "结束当前行动";
  if (action.type === "take_tokens") {
    const taken = tokenText((action.take ?? {}) as Record<string, number>);
    const returned = tokenText((action.return ?? {}) as Record<string, number>);
    return `拿取 ${taken}${returned ? `；归还 ${returned}` : ""}`;
  }
  if (action.type === "buy_visible" || action.type === "buy_reserved") {
    const payment = tokenText((action.payment ?? {}) as Record<string, number>);
    return `购买 ${action.card_id}${payment ? `；支付 ${payment}` : "；免费"}`;
  }
  if (action.type === "reserve_visible") return `预留公开牌 ${action.card_id}${action.return && tokenText(action.return as Record<string, number>) ? `；归还 ${tokenText(action.return as Record<string, number>)}` : ""}`;
  if (action.type === "reserve_deck") return `从 ${action.tier} 阶牌库暗中预留一张牌`;
  if (action.type === "choose_noble") return `选择贵族 ${action.noble_id}`;
  return action.type === "pass" ? "跳过本回合" : String(action.type);
}

const ACTION_GROUPS: Record<string, string> = {
  buy_visible: "购买公开牌", buy_reserved: "购买预留牌", take_tokens: "拿取宝石",
  reserve_visible: "预留公开牌", reserve_deck: "预留牌库顶牌", choose_noble: "选择贵族", pass: "其他",
  choose_initial_hand: "选择起始手牌", select_action: "选择行动牌", take_x_token: "替代 X-token 行动",
  draw_cards: "抽牌", snap_card: "拿取展示牌", discard_card: "弃牌", break_discard: "Break 弃牌",
  place_building: "放置建筑", play_animal: "打出动物", association_task: "协会任务",
  play_sponsor: "打出赞助商", advance_break: "推进 Break", finish_action: "结束行动",
};

function groupActions(actions: LegalAction[]) {
  return actions.reduce<Record<string, LegalAction[]>>((groups, item) => {
    const kind = String(item.action.type);
    (groups[kind] ||= []).push(item);
    return groups;
  }, {});
}

const ARK_ACTION_LABELS: Record<string, string> = {
  animals: "动物", cards: "卡牌", build: "建造", association: "协会", sponsors: "赞助商",
};

function ArkTrack({label, value, tone}: {label: string; value: number; tone: string}) {
  return <div className={`ark-track track-${tone}`}><span>{label}</span><div><i style={{width: `${Math.min(100, Math.max(3, value * 2.5))}%`}}/></div><b>{value}</b></div>;
}

function ArkZooMap({map}: {map: ArkMap}) {
  const occupied = new Set(map.buildings.flatMap(building => building.cells.map(cell => `${cell.q}:${cell.r}`)));
  return <div className="ark-map" aria-label={`${map.name} 六角地图`}>
    {map.cells.map(cell => <i key={`${cell.q}:${cell.r}`} className={`ark-hex terrain-${cell.terrain} ${occupied.has(`${cell.q}:${cell.r}`) ? "is-built" : ""}`}
      style={{left: `calc(50% + ${cell.q * 25 + cell.r * 12.5}px)`, top: `calc(50% + ${cell.r * 22}px)`}}
      title={`(${cell.q}, ${cell.r}) · ${cell.terrain}`}/>) }
  </div>;
}

function ArkPlayerPanel({player: p, identity}: {player: ArkPlayerView; identity?: Snapshot["players"][number]}) {
  return <section className="player-panel ark-player-panel">
    <header><div><span className="seat-label">座位 {p.seat + 1}</span><h3>{identity?.name || `玩家 ${p.seat + 1}`}</h3></div><div className="ark-money"><strong>{p.money}</strong><span>₡</span></div></header>
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}</div>
    <div className="ark-mini-tracks"><span>吸引力 <b>{p.appeal}</b></span><span>保育 <b>{p.conservation}</b></span><span>声望 <b>{p.reputation}</b></span></div>
    <div className="ark-worker-row"><span>X TOKEN <b>{p.x_tokens}/5</b></span><span>协会工人 <b>{p.association_workers.active}</b> + {p.association_workers.reserve}</span></div>
    <div className="ark-actions">{[...p.action_cards].sort((a, b) => b.strength - a.strength).map(card => <div key={card.action} className={`ark-action action-${card.action}`}><b>{card.strength}</b><span>{ARK_ACTION_LABELS[card.action]}</span>{card.upgraded && <i>Ⅱ</i>}</div>)}</div>
    <div className="ark-hidden-row"><span>起始抽牌 <b>{p.initial_draw_count}</b> / 留 {p.initial_keep_required}</span><span>终局牌 <b>{p.final_scoring_cards.length}</b></span></div>
    <div className="ark-hand-preview"><span>手牌 {p.hand_count}</span>{p.hand.slice(0, 6).map((card, index) => <i key={card.id || index} title={card.id || "hidden"}>{card.hidden ? "?" : card.card_type?.slice(0, 1).toUpperCase()}</i>)}</div>
  </section>;
}

function SplendorBoard({view}: {view?: View}) {
  return <>
    <div className="bank-bar"><div><small>供应区</small><strong>宝石银行</strong></div>{view && Object.keys(GEM_META).map(c => <Gem key={c} color={c} value={view.bank[c]}/>)}</div>
    <section className="nobles"><header><span>贵族</span><b>{view?.available_nobles.length || 0} AVAILABLE</b></header><div>{view?.available_nobles.map(n => <article key={n.id}><strong>3</strong><Cost cost={n.required}/></article>)}</div></section>
    <section className="market">{[3,2,1].map(tier => <div className="tier" key={tier}>
      <div className="tier-label"><span>TIER</span><strong>0{tier}</strong><small>{view?.deck_counts[String(tier)]} 张</small></div>
      <div className="market-cards">{view?.market[String(tier)].map(card => <DevCard key={card.id} card={card}/>)}</div>
    </div>)}</section>
  </>;
}

function ArkNovaBoard({view, players}: {view?: ArkView; players: Snapshot["players"]}) {
  if (!view) return null;
  return <div className="ark-board">
    <section className="ark-milestone"><div><span>ARK NOVA · CONTROLLED CORE</span><h2>{view.phase === "initial_hand_selection" ? "正在选择起始手牌" : "多阶段对局进行中"}</h2></div><p>回合、行动牌、建造、动物、协会、赞助商和 Break 已接通；当前使用无特殊能力的研究卡池，不代表完整商业卡池。</p><code>{view.rules_version}</code></section>
    <section className="ark-track-board">
      <div><span>TRACKS / BREAK</span><h3>公共轨道</h3></div>
      <div className="ark-track-stack"><ArkTrack label="BREAK" value={view.break_track.position} tone="break"/><ArkTrack label="ACTIVE APPEAL" value={view.players[view.active_seat]?.appeal || 0} tone="appeal"/><ArkTrack label="ACTIVE CONSERVATION" value={view.players[view.active_seat]?.conservation || 0} tone="conservation"/><ArkTrack label="ACTIVE REPUTATION" value={view.players[view.active_seat]?.reputation || 0} tone="reputation"/></div>
      <div className="ark-decision"><span>CURRENT DECISION</span><strong>{view.turn.decision.replaceAll("_", " ")}</strong><small>{view.phase.replaceAll("_", " ")}</small></div>
    </section>
    <section className="ark-display"><header><div><span>CARD DISPLAY</span><h3>中央卡牌展示区</h3></div><b>牌库 {view.deck_count} · 弃牌 {view.discard_count}</b></header><div>{view.card_display.map((card, index) => <article key={card.id || index} className={card.hidden ? "is-facedown" : ""}><span>0{index + 1}</span><strong>{card.hidden ? "起始选牌后翻开" : card.card_type?.replaceAll("_", " ")}</strong><small>{card.tags?.join(" · ")}</small>{card.id && <code>{card.id}</code>}</article>)}</div></section>
    <section className="ark-association"><header><span>ASSOCIATION BOARD</span><h3>协会板与基础保育项目</h3></header><div className="ark-projects">{view.base_conservation_projects.map(project => <article key={project.id}><b>{project.tag}</b><span>{project.levels.join(" / ")}</span><code>{project.id}</code></article>)}</div><div className="ark-association-meta"><span>合作动物园 {Object.keys(view.association_board.partner_zoos).length}</span><span>大学 {Object.keys(view.association_board.universities).length}</span>{view.association_board.blocked_two_player.length > 0 && <span>双人封锁 {view.association_board.blocked_two_player.length}</span>}</div></section>
    <section className="ark-zoo-section"><header><span>BEGINNER MAP A</span><h3>玩家动物园</h3></header><div>{view.players.map(player => <article key={player.seat}><div><strong>{players[player.seat]?.name || `玩家 ${player.seat + 1}`}</strong><span>3 格起始围栏 · 空置</span></div><ArkZooMap map={player.map}/></article>)}</div><small>本里程碑的坐标为可测试的示意几何；正式 footprint 会在地图规则阶段按规则场景校准。</small></section>
  </div>;
}

export default function Home() {
  const [game, setGame] = useState<GameId>("splendor");
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
  const [submittingAction, setSubmittingAction] = useState("");
  const sourceRef = useRef<EventSource | null>(null);
  const splendorView = snapshot?.game === "splendor" ? snapshot.views[0] as View : undefined;
  const arkView = snapshot?.game === "ark_nova" ? snapshot.views[0] as ArkView : undefined;
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

  function movePlayer(index: number, offset: number) {
    setPlayers(current => {
      const destination = index + offset;
      if (destination < 0 || destination >= current.length) return current;
      const ordered = [...current];
      [ordered[index], ordered[destination]] = [ordered[destination], ordered[index]];
      return ordered;
    });
  }

  function shufflePlayers() {
    setPlayers(current => {
      const ordered = [...current];
      for (let index = ordered.length - 1; index > 0; index--) {
        const destination = Math.floor(Math.random() * (index + 1));
        [ordered[index], ordered[destination]] = [ordered[destination], ordered[index]];
      }
      return ordered;
    });
  }

  function setMatchup(kind: "human" | "harness") {
    setPlayers(kind === "human" ? [humanPlayer(1), deepseekHarnessPlayer(2, "opencode")] : [
      deepseekHarnessPlayer(1, "opencode"), deepseekHarnessPlayer(2, "codex"),
    ]);
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
          game, seed: seed === "" ? null : Number(seed), speed_ms: speed,
          ...(game === "ark_nova" ? {game_config: {turn_limit: 60}} : {}),
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

  async function submitHumanAction(item: LegalAction) {
    if (!snapshot?.human_turn || submittingAction) return;
    setSubmittingAction(item.id); setError("");
    try {
      const response = await fetch(api(`/api/matches/${snapshot.match_id}/action`), {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          seat: snapshot.human_turn.seat,
          expected_version: snapshot.human_turn.version,
          action_id: item.id,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || "无法提交行动");
      setSnapshot(data);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setSubmittingAction(""); }
  }

  if (!snapshot) return <main className="setup-shell">
    <section className="hero">
      <div className="eyebrow">AGENT BOARD GAME ARENA / {game === "splendor" ? "SPLENDOR" : "ARK NOVA"}</div>
      <h1>把模型放上牌桌，<br/><i>看见</i>每一次决策。</h1>
      <p>{game === "splendor" ? "配置 2–4 名模型或人类玩家。轮到你时直接在牌桌选择合法行动；所有 Agent Harness 固定使用最高思考强度。" : "在受控研究卡池中测试多阶段决策：起始选牌、五张行动牌、六角建造、动物入园、协会任务与 Break 都会逐步提交。"}</p>
      <div className="hero-marks"><span>多游戏插件</span><span>座位隔离观察</span><span>{game === "splendor" ? "完整引擎" : "CONTROLLED CORE"}</span></div>
    </section>
    <section className="setup-card">
      <div className="game-picker" role="group" aria-label="选择游戏"><button className={game === "splendor" ? "selected" : ""} onClick={() => setGame("splendor")}><span>PLAYABLE</span><b>璀璨宝石</b><small>完整基础版引擎</small></button><button className={game === "ark_nova" ? "selected" : ""} onClick={() => setGame("ark_nova")}><span>CONTROLLED CORE</span><b>方舟动物园</b><small>多阶段状态机 · 研究卡池</small></button></div>
      <header><div><span>NEW TABLE</span><h2>创建一桌{game === "splendor" ? "璀璨宝石" : "方舟动物园"}</h2></div><div className="matchup-presets"><button onClick={() => setMatchup("human")}>人类 vs Agent</button><button onClick={() => setMatchup("harness")}>Harness 对战</button><b>{players.length} PLAYERS</b></div></header>
      <div className="players-config">{players.map((p, index) => <article className="player-config" key={p.id}>
        <div className="seat-order"><b>0{index + 1}</b><div><button disabled={index === 0} aria-label={`将 ${p.name} 前移`} onClick={() => movePlayer(index, -1)}>↑</button><button disabled={index === players.length - 1} aria-label={`将 ${p.name} 后移`} onClick={() => movePlayer(index, 1)}>↓</button></div></div>
        <div className="field grow"><label htmlFor={`${p.id}-name`}>选手名</label><input id={`${p.id}-name`} value={p.name} onChange={e => updatePlayer(p.id, {name: e.target.value})}/></div>
        {!(["random", "human"] as Backend[]).includes(p.backend) && <>
          <div className="field provider-field"><label htmlFor={`${p.id}-provider`}>Harness / 服务商</label><select id={`${p.id}-provider`} value={p.provider} onChange={e => selectProvider(p.id, e.target.value as Provider)}><optgroup label="Agent Harness">{(["claude_code", "pi", "codex", "opencode"] as Provider[]).map(id => <option key={id} value={id}>{PROVIDERS[id].label}</option>)}</optgroup><optgroup label="直连模型 API">{(["custom", "deepseek", "dashscope", "zhipu", "minimax"] as Provider[]).map(id => <option key={id} value={id}>{PROVIDERS[id].label}</option>)}</optgroup></select></div>
          <div className="field backend-field"><label htmlFor={`${p.id}-backend`}>运行方式</label><select id={`${p.id}-backend`} value={p.backend} onChange={e => updatePlayer(p.id, {backend: e.target.value as Backend})}>{Object.entries(BACKENDS).filter(([id]) => id !== "random").map(([id, b]) => <option key={id} value={id}>{b.label}</option>)}</select></div>
          <div className="field grow endpoint-field"><label htmlFor={`${p.id}-endpoint`}>Endpoint</label><input id={`${p.id}-endpoint`} value={p.base_url} onChange={e => updatePlayer(p.id, {provider: "custom", base_url: e.target.value})}/></div>
          <div className="field model-field"><label htmlFor={`${p.id}-model`}>模型名</label><input id={`${p.id}-model`} list={`${p.id}-models`} placeholder="可选择或输入 model-id" value={p.model} onChange={e => updatePlayer(p.id, {model: e.target.value})}/><datalist id={`${p.id}-models`}>{PROVIDERS[p.provider].models.map(model => <option key={model} value={model}/>)}</datalist></div>
          <div className="field key-field"><label htmlFor={`${p.id}-key`}>API Key</label><input id={`${p.id}-key`} type="password" autoComplete="off" placeholder="仅在本次对局使用" value={p.api_key} onChange={e => updatePlayer(p.id, {api_key: e.target.value})}/></div>
          <div className="provider-note">{PROVIDERS[p.provider].note}</div>
        </>}
        {(["random", "human"] as Backend[]).includes(p.backend) && <div className="field manual-backend"><label htmlFor={`${p.id}-backend`}>运行方式</label><select id={`${p.id}-backend`} value={p.backend} onChange={e => updatePlayer(p.id, {backend: e.target.value as Backend})}>{Object.entries(BACKENDS).map(([id, b]) => <option key={id} value={id}>{b.label}</option>)}</select><small>{p.backend === "human" ? "轮到该座位时在牌桌上操作" : "无需 API，自动随机行动"}</small></div>}
        {players.length > 2 && <button className="remove" aria-label={`移除 ${p.name}`} onClick={() => setPlayers(x => x.filter(y => y.id !== p.id))}>×</button>}
      </article>)}</div>
      <div className="setup-actions">
        <button className="add-player human-add" disabled={players.length >= 4} onClick={() => setPlayers(x => [...x, humanPlayer(x.length + 1)])}>＋ 添加人类</button>
        <button className="add-player" disabled={players.length >= 4} onClick={() => setPlayers(x => [...x, player(x.length + 1, "random")])}>＋ 添加 AI / 基线</button>
        <button className="shuffle-order" onClick={shufflePlayers}>⤨ 随机座次</button>
        <div className="field mini"><label htmlFor="match-seed">Seed</label><input id="match-seed" inputMode="numeric" value={seed} onChange={e => setSeed(e.target.value)}/></div>
        <div className="field mini speed"><label htmlFor="match-speed">每步间隔 <b>{speed}ms</b></label><input id="match-speed" type="range" min="0" max="2000" step="50" value={speed} onChange={e => setSpeed(Number(e.target.value))}/></div>
        <button className="start" disabled={starting} onClick={startMatch}>{starting ? "正在入席…" : "开始对局 →"}</button>
      </div>
      {game === "ark_nova" && <div className="setup-scope-note"><b>受控核心版</b> 可完整结束并供 Agent 调用，但使用无特殊能力的结构化研究卡牌和示意 Map A；尚不是完整商业卡池规则实现。</div>}
      {error && <div className="error">{error}</div>}
    </section>
  </main>;

  return <main className="table-shell">
    <header className="table-header">
      <div><span className="brand-mark">ABGA</span><strong>{snapshot.game_description.name} {snapshot.game === "splendor" ? "Live Table" : "Controlled Arena"}</strong></div>
      <div className="match-meta"><span>对局 <code>{snapshot.match_id}</code></span><span>回合 <b>{snapshot.turn_count}</b>{snapshot.game === "ark_nova" && <> · 决策 <b>{snapshot.decision_count ?? arkView?.decision_count}</b></>}</span><span className={`status ${snapshot.paused ? "status-paused" : `status-${snapshot.status}`}`}>{snapshot.status !== "active" ? "已结束" : snapshot.paused ? (snapshot.pause_pending ? "等待暂停" : "已暂停") : "进行中"}</span></div>
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
        return snapshot.game === "splendor"
          ? <PlayerPanel key={identity.seat} player={ownPlayer as PlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>
          : <ArkPlayerPanel key={identity.seat} player={ownPlayer as ArkPlayerView} identity={identity}/>;
      })}</aside>
      <section className="board">
        {snapshot.paused && <div className={`pause-notice ${snapshot.pause_pending ? "pending" : ""}`}><strong>{snapshot.pause_pending ? "等待当前模型完成…" : "对局已暂停"}</strong><span>{snapshot.pause_pending ? "返回的这一手会正常落盘，下一位不会开始思考。" : "牌桌停在安全的回合边界，点击“继续对局”即可恢复。"}</span></div>}
        {snapshot.human_turn && <section className="human-turn" aria-live="polite">
          <header><div><span>YOUR TURN · SEAT {snapshot.human_turn.seat + 1}</span><h2>{snapshot.human_turn.player}，请选择行动</h2></div><b>{snapshot.human_turn.legal_actions.length} 个合法选项</b></header>
          <div className="human-action-groups">{Object.entries(groupActions(snapshot.human_turn.legal_actions)).map(([kind, actions]) => <section key={kind}>
            <h3>{ACTION_GROUPS[kind] || kind}<span>{actions.length}</span></h3>
            <div>{actions.map(item => <button key={item.id} disabled={Boolean(submittingAction)} onClick={() => submitHumanAction(item)}><strong>{humanActionText(item.action)}</strong><small>{item.id}{submittingAction === item.id ? " · 提交中…" : ""}</small></button>)}</div>
          </section>)}</div>
        </section>}
        {snapshot.game === "splendor" ? <SplendorBoard view={splendorView}/> : <ArkNovaBoard view={arkView} players={snapshot.players}/>}
        {snapshot.status === "finished" && <div className="winner-banner"><span>WINNER</span><strong>{timeline.at(-1)?.event.rankings?.[0]?.player || "对局结束"}</strong><button onClick={() => { setSnapshot(null); setTimeline([]); }}>再来一局</button></div>}
      </section>
      <aside className="timeline">
        <header><div><span>MODEL STREAM</span><h2>模型 Chat</h2></div><i className={snapshot.status === "active" && (!snapshot.paused || snapshot.pause_pending) ? "pulse" : ""}/></header>
        <div className="chat-list">{chat.length === 0 && <p className="waiting">{snapshot.game_description.runnable ? "等待模型开始思考…" : "当前里程碑不启动模型；这里将在行动状态机接通后显示思考、工具调用与回复。"}</p>}{chat.map(turn => <article className={`chat-turn chat-${turn.status}`} key={turn.key}>
          <header><strong>{turn.player}</strong><span>{turn.backend} · 尝试 {turn.attempt}{turn.status === "thinking" ? " · 生成中" : turn.latencyMs ? ` · ${(turn.latencyMs / 1000).toFixed(1)}s` : ""}</span></header>
          {turn.reasoning && <details open><summary>思考过程{turn.status === "done" ? " · 可折叠" : ""}</summary><pre>{turn.reasoning}</pre></details>}
          {turn.content && <div className="model-answer"><b>回复</b><pre>{turn.content}</pre></div>}
          {turn.status === "thinking" && <div className="typing"><i/><i/><i/></div>}
        </article>)}</div>
        <section className="action-drawer"><header><span>ACTIONS</span><strong>决策记录</strong><b>{timeline.filter(item => ["decision", "turn"].includes(item.event.type)).length}</b></header>
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
