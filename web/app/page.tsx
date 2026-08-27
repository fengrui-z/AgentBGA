"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ArkNovaWorkbench } from "./ark-nova-workbench";
import {
  ArkNovaPlayerSummary, ArkNovaTable,
  type ArkPlayerView, type ArkView,
} from "./ark-nova-table";

// ── i18n ─────────────────────────────────────────────────────────────
type Lang = "zh" | "en";
type Dict = Record<string, string>;
const ARK_ACTION_LABELS: Record<Lang, Record<string, string>> = {
  zh: {animals: "动物", cards: "卡牌", build: "建造", association: "协会", sponsors: "赞助商"},
  en: {animals: "Animals", cards: "Cards", build: "Build", association: "Association", sponsors: "Sponsors"},
};
const STR: Record<Lang, Dict> = {
  zh: {
    // hero
    hero_eyebrow: "AGENT BOARD GAME ARENA",
    hero_title_a: "把模型放上牌桌，",
    hero_title_b: "看见",
    hero_title_c: "每一次决策。",
    hero_mark_1: "多游戏插件", hero_mark_2: "座位隔离观察", hero_mark_3: "完整对局引擎", hero_mark_ark: "SEMANTIC WORKBENCH",
    // setup
    new_table: "NEW TABLE", create_table: "创建一桌", g_human: "人类 vs Agent", g_harness: "Harness 对战",
    players_count: "PLAYERS", pick_game: "选择游戏",
    f_name: "选手名", f_provider: "Harness / 服务商", f_backend: "运行方式", f_endpoint: "Endpoint",
    f_model: "模型名", f_key: "API Key", f_auth: "Codex 认证", f_seed: "Seed", f_speed: "每步间隔",
    auth_api_key: "API Key（按量）", auth_subscription: "ChatGPT 订阅",
    og_harness: "Agent Harness", og_direct: "直连模型 API",
    ph_model: "可选择或输入 model-id", ph_key: "仅在本次对局使用",
    ph_endpoint: "如 http://127.0.0.1:8000/v1（本地模型 / 网关）",
    add_human: "＋ 添加人类", add_ai: "＋ 添加 AI / 基线", shuffle: "⤨ 随机座次",
    start: "开始对局 →", starting: "正在入席…", err_start: "无法启动对局",
    human_note: "轮到该座位时在牌桌上操作", random_note: "无需 API，自动随机行动",
    seat_label: "座位", player_label: "玩家",
    move_up: "前移", move_down: "后移", remove: "移除",
    // table header
    live_table: "Live Table", trade_arena: "Trade Arena", controlled_arena: "Controlled Arena",
    match: "对局", turn: "回合", decision: "决策",
    s_finished: "已结束", s_wait_pause: "等待暂停", s_paused: "已暂停", s_active: "进行中",
    processing: "处理中…", resume: "▶ 继续对局", pause: "Ⅱ 暂停", new_match: "新对局",
    err_pause: "无法更新暂停状态", err_submit: "无法提交行动",
    err_ws: "实时连接已断开，可刷新页面后重新开始。", call_failed: "调用失败",
    pause_pending: "等待当前模型完成…", paused: "对局已暂停",
    pause_pending_desc: "返回的这一手会正常落盘，下一位不会开始思考。",
    paused_desc: "牌桌停在安全的回合边界，点击“继续对局”即可恢复。",
    // human turn
    your_turn: "YOUR TURN · SEAT", pick_action: "，请选择行动", legal_opts: "个合法选项",
    submitting: "提交中…", returning: "归还", buying: "支付", reserving: "预留",
    // splendor board
    supply: "供应区", gem_bank: "宝石银行", nobles: "贵族", available: "AVAILABLE",
    tier: "TIER", cards_unit: "张",
    reserve_label: "预留", buy_label: "购买",
    // player panel
    tokens: "宝石", engine: "引擎", purchased: "已购", reserved: "预留", nobles_owned: "贵族",
    // ark nova
    ark_eyebrow: "ARK NOVA · OFFICIAL BASE CANDIDATE",
    ark_phase_select: "正在选择起始手牌", ark_phase_play: "多阶段对局进行中",
    ark_phase_note: "当前对局运行基础版官方语义候选：255 张实体卡、5 种行动牌与新手地图已接入统一规则引擎。",
    ark_tracks: "TRACKS / BREAK", ark_tracks_h: "公共轨道", cur_decision: "CURRENT DECISION",
    ark_display: "CARD DISPLAY", ark_display_h: "中央卡牌展示区", deck: "牌库", discard: "弃牌",
    ark_after_select: "起始选牌后翻开",
    ark_assoc: "ASSOCIATION BOARD", ark_assoc_h: "协会板与基础保育项目",
    ark_partner: "合作动物园", ark_uni: "大学", ark_donation: "捐款", ark_blocked: "双人封锁", ark_avail: "可用",
    ark_zoo: "MAP 0", ark_zoo_h: "玩家动物园", ark_zoo_unit: "新手地图 · 官方坐标 footprint",
    ark_zoo_note: "水域、山脉、覆盖奖励与多格建筑均由后端以 axial coordinate 校验。",
    hand: "手牌", money_c: "₡",
    // brass
    brass_canal: "运河时代", brass_rail: "铁路时代", round: "轮",
    brass_actions: "ACTIONS", coal_market: "煤炭市场", iron_market: "铁市场", turn_order: "行动顺序",
    brass_map_h: "产业城市与连接网络", industries_unit: "产业", links_unit: "连接",
    brass_conn: "连接位", canal: "运河", rail: "铁路", not_built: "未铺设",
    brass_merchants: "商人区", any_goods: "任意商品", blank: "空白",
    flipped: "已翻面", not_flipped: "未翻面",
    // century
    century_status: "丝路香料市场", century_note: "获取商人牌构筑转化引擎，完成订单赚取声望。商队最多携带",
    caravan_unit: "份香料。", point_cards: "POINT CARDS", order_market: "订单市场",
    merchant_cards: "MERCHANT CARDS", trade_market: "商路市场", deck_label: "牌库",
    caravan_spice: "商队香料", gold_coin: "金币", silver_coin: "银币", orders: "订单",
    avail_merchant: "可用商人牌", played: "已打出", need_rest: "需要休息收回卡牌",
    card_spice: "牌上香料", century_legend_note: "界面仅使用结构化数值与原创色块，不包含出版商卡图。",
    upgrade_unit: "升级", gain_spice: "获得香料", repeat_trade: "重复交易",
    // timeline / chat
    model_stream: "MODEL STREAM", chat_h: "模型 Chat", waiting_model: "等待模型开始思考…",
    waiting_note: "当前里程碑不启动模型；这里将在行动状态机接通后显示思考、工具调用与回复。",
    thinking: "思考过程", collapsible: "可折叠", answer: "回复", attempt: "尝试", generating: "生成中",
    actions: "ACTIONS", decision_log: "决策记录", view_tool: "查看工具数据",
    // winner
    winner: "WINNER", play_again: "再来一局", match_over: "对局结束",
    // describeAction
    da_error: "调用失败", da_abort: "对局中止",
    // humanActionText / tokens
    take_tokens: "拿取宝石", buy_visible: "购买公开牌", buy_reserved: "购买预留牌",
    reserve_visible: "预留公开牌", reserve_deck: "预留牌库顶牌", choose_noble: "选择贵族", pass: "其他",
  },
  en: {
    hero_eyebrow: "AGENT BOARD GAME ARENA",
    hero_title_a: "Put models at the table,",
    hero_title_b: "watch",
    hero_title_c: "every decision.",
    hero_mark_1: "Multi-game plugins", hero_mark_2: "Seat-isolated views", hero_mark_3: "Full-match engine", hero_mark_ark: "SEMANTIC WORKBENCH",
    new_table: "NEW TABLE", create_table: "New table · ", g_human: "Human vs Agent", g_harness: "Harness Battle",
    players_count: "PLAYERS", pick_game: "Select game",
    f_name: "Player name", f_provider: "Harness / provider", f_backend: "Runtime", f_endpoint: "Endpoint",
    f_model: "Model id", f_key: "API key", f_auth: "Codex auth", f_seed: "Seed", f_speed: "Step interval",
    auth_api_key: "API key (usage-based)", auth_subscription: "ChatGPT subscription",
    og_harness: "Agent Harness", og_direct: "Direct model API",
    ph_model: "Pick or type model-id", ph_key: "Used for this match only",
    ph_endpoint: "e.g. http://127.0.0.1:8000/v1 (local model / gateway)",
    add_human: "+ Add human", add_ai: "+ Add AI / baseline", shuffle: "⤨ Shuffle seats",
    start: "Start match →", starting: "Seating…", err_start: "Failed to start match",
    human_note: "Play at the table when it's this seat's turn", random_note: "No API needed, random actions",
    seat_label: "Seat", player_label: "Player",
    move_up: "Move up", move_down: "Move down", remove: "Remove",
    live_table: "Live Table", trade_arena: "Trade Arena", controlled_arena: "Controlled Arena",
    match: "Match", turn: "Turn", decision: "Decision",
    s_finished: "Finished", s_wait_pause: "Waiting to pause", s_paused: "Paused", s_active: "Running",
    processing: "Working…", resume: "▶ Resume", pause: "Ⅱ Pause", new_match: "New match",
    err_pause: "Failed to update pause state", err_submit: "Failed to submit action",
    err_ws: "Live connection dropped. Refresh and restart.", call_failed: "Call failed",
    pause_pending: "Waiting for the model to finish…", paused: "Match paused",
    pause_pending_desc: "The pending move will commit normally; the next seat will not start.",
    paused_desc: "The table stops at a safe turn boundary. Click Resume to continue.",
    your_turn: "YOUR TURN · SEAT", pick_action: ", choose an action", legal_opts: "legal options",
    submitting: "Submitting…", returning: "Return", buying: "Pay", reserving: "Reserve",
    supply: "Supply", gem_bank: "Gem Bank", nobles: "Nobles", available: "AVAILABLE",
    tier: "TIER", cards_unit: "cards",
    reserve_label: "Reserve", buy_label: "Buy",
    tokens: "Gems", engine: "Engine", purchased: "Purchased", reserved: "Reserved", nobles_owned: "Nobles",
    ark_eyebrow: "ARK NOVA · OFFICIAL BASE CANDIDATE",
    ark_phase_select: "Selecting starting hand", ark_phase_play: "Multi-phase match in progress",
    ark_phase_note: "This match runs the official-base semantic candidate: all 255 physical cards, five Action cards, and Map 0 are wired into one rules engine.",
    ark_tracks: "TRACKS / BREAK", ark_tracks_h: "Public tracks", cur_decision: "CURRENT DECISION",
    ark_display: "CARD DISPLAY", ark_display_h: "Card display", deck: "Deck", discard: "Discard",
    ark_after_select: "Revealed after pick",
    ark_assoc: "ASSOCIATION BOARD", ark_assoc_h: "Association board & conservation projects",
    ark_partner: "Partner zoos", ark_uni: "Universities", ark_donation: "Donations", ark_blocked: "Two-player locked", ark_avail: "available",
    ark_zoo: "MAP 0", ark_zoo_h: "Player zoo", ark_zoo_unit: "Beginner map · official coordinate footprint",
    ark_zoo_note: "Water, rock, placement bonuses, and polyhex buildings are validated by the backend in axial coordinates.",
    hand: "Hand", money_c: "₡",
    brass_canal: "Canal Era", brass_rail: "Rail Era", round: "round",
    brass_actions: "ACTIONS", coal_market: "Coal market", iron_market: "Iron market", turn_order: "Turn order",
    brass_map_h: "Industry cities & network", industries_unit: "industries", links_unit: "links",
    brass_conn: "Connection spaces", canal: "Canal", rail: "Rail", not_built: "Unbuilt",
    brass_merchants: "Merchants", any_goods: "Any goods", blank: "Blank",
    flipped: "Flipped", not_flipped: "Not flipped",
    century_status: "Silk-Road Spice Market", century_note: "Acquire merchant cards to build a conversion engine; complete orders for VP. Caravan holds up to",
    caravan_unit: "spice.", point_cards: "POINT CARDS", order_market: "Order market",
    merchant_cards: "MERCHANT CARDS", trade_market: "Trade market", deck_label: "Deck",
    caravan_spice: "Caravan spices", gold_coin: "Gold", silver_coin: "Silver", orders: "Orders",
    avail_merchant: "Merchant cards", played: "Played", need_rest: "Rest to recover cards",
    card_spice: "Spices on card", century_legend_note: "UI uses structured values & original color tiles only; no publisher artwork.",
    upgrade_unit: "Upgrade", gain_spice: "Gain spice", repeat_trade: "Repeat trade",
    model_stream: "MODEL STREAM", chat_h: "Model chat", waiting_model: "Waiting for the model to think…",
    waiting_note: "This milestone doesn't launch a model; thinking, tool calls and replies show here once wired up.",
    thinking: "Reasoning", collapsible: "collapsible", answer: "Answer", attempt: "attempt", generating: "generating",
    actions: "ACTIONS", decision_log: "Decision log", view_tool: "View tool data",
    winner: "WINNER", play_again: "Play again", match_over: "Match over",
    da_error: "Call failed", da_abort: "Match aborted",
    take_tokens: "Take gems", buy_visible: "Buy visible card", buy_reserved: "Buy reserved card",
    reserve_visible: "Reserve visible card", reserve_deck: "Reserve from deck", choose_noble: "Choose noble", pass: "Other",
  },
};
function makeT(lang: Lang) {
  return (key: string): string => STR[lang][key] ?? STR.zh[key] ?? key;
}
const LangCtx = createContext<Lang>("zh");
const useLang = () => useContext(LangCtx);

type Backend = "openai" | "anthropic" | "gemini" | "claude" | "pi" | "codex" | "opencode" | "dsh" | "hermes" | "minimal" | "human" | "random";
type Provider = "custom" | "claude_code" | "pi" | "codex" | "opencode" | "dsh" | "hermes" | "minimal" | "deepseek" | "dashscope" | "zhipu" | "minimax";
type GameId = "splendor" | "azul" | "ark_nova" | "brass_birmingham" | "century_spice_road" | "seven_wonders";
type ReasoningEffort = "none" | "minimal" | "low" | "medium" | "high" | "max" | "xhigh";
type AuthMode = "api_key" | "subscription";
type PlayerForm = { id: string; name: string; provider: Provider; backend: Backend; model: string; base_url: string; api_key: string; auth_mode: AuthMode; reasoning_effort: ReasoningEffort };
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
type AzulColor = "blue" | "yellow" | "red" | "black" | "white";
type AzulCounts = Record<AzulColor, number>;
type AzulPlayerView = {
  seat: number; score: number; completed_rows: number; floor: string[];
  pattern_lines: {line: number; capacity: number; color: AzulColor | null; count: number; complete: boolean}[];
  wall: {color: AzulColor; occupied: boolean}[][];
};
type AzulView = {
  game: "azul"; rules_version: string; implementation_status: string; status: string; phase: string;
  round: number; turn_count: number; active_seat: number; round_start_seat: number; bag_count: number; lid_count: number;
  center_has_start_marker: boolean; start_marker_holder_seat: number | null;
  factories: {id: string; tiles: AzulCounts}[]; center: AzulCounts;
  wall_pattern: AzulColor[][]; players: AzulPlayerView[];
};
type BrassIndustry = {
  id: string; tile_id?: string; industry: string; level: number; owner: number; location: string;
  resources: number; flipped: boolean; vp: number; income_spaces: number; link_icons: number;
};
type BrassPlayerView = {
  seat: number; money: number; income_position: number; vp: number; spent_this_round: number;
  hand_count: number; hand: {id?: string; card_type?: string; location?: string; industry?: string; industries?: string[]; hidden?: true}[];
  discard: unknown[]; wild_cards: {location: number; industry: number}; links_remaining: number;
  industry_stacks: Record<string, {level: number}[]>;
};
type BrassView = {
  game: "brass_birmingham"; rules_version: string; implementation_status: string; status: string;
  phase: string; era: "canal" | "rail"; round: number; turn_count: number; decision_count: number;
  active_seat: number; turn_order: number[]; turn: {decision: string; actions_remaining: number; actions_total: number};
  deck_count: number; markets: Record<"coal" | "iron", {prices: number[]; occupied: boolean[]}>;
  board: {
    locations: {id: string; kind: string; industry_slots: {id: string; accepts: string[]; industry_id: string | null}[]}[];
    merchant_locations: {id: string; slots: {id: string; buys: string; beer: number}[]}[];
    connection_spaces: {id: string; endpoints: string[]; available_eras: string[]}[];
    industries: BrassIndustry[]; links: {id: string; connection_id: string; owner: number; era: string}[];
  };
  players: BrassPlayerView[];
};
type SpiceName = "turmeric" | "saffron" | "cardamom" | "cinnamon";
type SpicePool = Record<SpiceName, number>;
type CenturyMerchant = {id: string; kind: "gain" | "upgrade" | "trade"; upgrades: number; input: SpicePool; output: SpicePool};
type CenturyPoint = {id: string; points: number; cost: SpicePool};
type CenturyPlayerView = {
  seat: number; spices: SpicePool; hand: CenturyMerchant[]; played: CenturyMerchant[];
  point_cards: CenturyPoint[]; coins: {gold: number; silver: number}; score: number;
};
type CenturyView = {
  game: "century_spice_road"; rules_version: string; status: string; phase: string;
  turn_count: number; active_seat: number; caravan_limit: number;
  merchant_deck_count: number; merchant_market: {card: CenturyMerchant; spices: SpicePool}[];
  point_deck_count: number; point_market: CenturyPoint[];
  coins: {gold: number; silver: number; silver_position: number}; players: CenturyPlayerView[];
};
type SevenResource = "wood" | "stone" | "clay" | "ore" | "glass" | "papyrus" | "cloth";
type SevenBenefit = {
  type: string; amount?: number; resources?: SevenResource[]; directions?: ("left" | "right")[];
  scope?: ("self" | "left" | "right")[]; color?: SevenCard["color"]; colors?: SevenCard["color"][];
  coin_cost?: number; symbol?: string; effect?: string;
};
type SevenCard = {
  id: string; name: string; age: number; color: "brown" | "gray" | "blue" | "yellow" | "red" | "green" | "purple";
  minimum_players: number; cost: Record<SevenResource, number>; coin_cost: number;
  production: SevenResource[][]; points: number; military: number; science: string | null; effect: string | null;
  chain_from: string[]; chain_to: string[]; benefits: SevenBenefit[]; current_points?: number;
};
type SevenStage = {
  stage: number; built: boolean; cost: Record<SevenResource, number>; points?: number; coins?: number;
  military?: number; science_wild?: number; special?: string; production?: SevenResource[][]; benefits: SevenBenefit[];
};
type SevenResourceUnit = {
  source_type: "wonder_start" | "card" | "wonder_stage"; source_id: string; source_name: string;
  options: SevenResource[]; tradeable: boolean; source_color?: SevenCard["color"];
  kind?: "production" | "trade_discount"; directions?: ("left" | "right")[]; stage?: number; unit?: number;
};
type SevenPurchase = {
  direction: "left" | "right"; seat: number; coins: number; resources: Partial<Record<SevenResource, number>>;
};
type SevenPlayerView = {
  seat: number; coins: number; wonder: string; wonder_name: string; wonder_side: "day" | "night";
  starting_resource: SevenResource; wonder_stages: SevenStage[]; city: SevenCard[];
  military_strength: number; military_tokens: number[]; military_tokens_by_age: number[][]; score: number;
  score_breakdown: Record<string, number>; hand_count: number; hand: (SevenCard | {hidden: true})[];
  choice_submitted: boolean; resource_units: SevenResourceUnit[];
};
type SevenView = {
  game: "seven_wonders"; rules_version: string; viewer_seat: number; status: string; phase: string; age: number; pick: number;
  turn_count: number; decision_count: number; active_seat: number; pass_direction: "left" | "right";
  discard_count: number; pending_choice_seats: number[]; players: SevenPlayerView[];
};
type GameDescription = {id: GameId; name: string; rules_version: string; implementation_status: string; runnable: boolean};
type Snapshot = {
  match_id: string; game: GameId; game_description: GameDescription; version: number; status: string; turn_count: number; decision_count?: number; active_seat: number;
  paused: boolean; pause_pending: boolean;
  human_turn?: {seat: number; player: string; version: number; legal_actions: LegalAction[]} | null;
  players: {seat: number; name: string; backend: string; model?: string; reasoning_effort?: string}[]; views: (View | AzulView | ArkView | BrassView | CenturyView | SevenView)[];
  spectator_view?: ArkView;
};
type LegalAction = {id: string; action: Record<string, unknown>};
type TimelineEvent = {
  type: string; player?: string; seat?: number; error?: string; turns?: number;
  backend?: string; agent?: {latency_ms?: number; action_latency_ms?: number; process_latency_ms?: number}; action?: Record<string, unknown>;
  rankings?: {player: string}[]; channel?: "reasoning" | "content"; delta?: string; attempt?: number; version?: number;
  harness?: string; tool?: string; arguments?: unknown; result?: unknown; action_id?: string;
};
type Timeline = { seq: number; event: TimelineEvent; snapshot?: Snapshot };
type ChatTurn = {
  key: string; seat: number; player: string; backend: string; attempt: number;
  reasoning: string; content: string; status: "thinking" | "done" | "error";
  startedAt: number; actionLatencyMs?: number; processLatencyMs?: number;
};

const GEM_ORDER = ["red", "green", "white", "blue", "black", "gold"] as const;
const BONUS_ORDER = GEM_ORDER.slice(0, 5);
const GEM_META: Record<string, {label: Record<Lang,string>; mark: string}> = {
  red: { mark: "●", label: {zh: "红宝石", en: "Ruby"} }, green: { mark: "⬟", label: {zh: "祖母绿", en: "Emerald"} },
  white: { mark: "◇", label: {zh: "钻石", en: "Diamond"} }, blue: { mark: "◆", label: {zh: "蓝宝石", en: "Sapphire"} },
  black: { mark: "⬢", label: {zh: "玛瑙", en: "Onyx"} }, gold: { mark: "★", label: {zh: "黄金", en: "Gold"} },
};
const SPICE_ORDER: SpiceName[] = ["turmeric", "saffron", "cardamom", "cinnamon"];
const SPICE_META: Record<SpiceName, {label: Record<Lang,string>; short: Record<Lang,string>}> = {
  turmeric: {label: {zh:"姜黄",en:"Turmeric"}, short: {zh:"黄",en:"T"}}, saffron: {label: {zh:"藏红花",en:"Saffron"}, short: {zh:"红",en:"S"}},
  cardamom: {label: {zh:"豆蔻",en:"Cardamom"}, short: {zh:"绿",en:"C"}}, cinnamon: {label: {zh:"肉桂",en:"Cinnamon"}, short: {zh:"褐",en:"N"}},
};
const AZUL_COLORS: AzulColor[] = ["blue", "yellow", "red", "black", "white"];
const AZUL_FLOOR_PENALTIES = [-1, -1, -2, -2, -2, -3, -3] as const;
const AZUL_META: Record<AzulColor, Record<Lang, string>> = {
  blue: {zh: "蓝色", en: "Blue"}, yellow: {zh: "黄色", en: "Yellow"}, red: {zh: "红色", en: "Red"},
  black: {zh: "黑色", en: "Black"}, white: {zh: "白色", en: "White"},
};
const GAME_COPY: Record<GameId, {eyebrow: string; name: Record<Lang,string>; description: Record<Lang,string>; badge: string; note: Record<Lang,string>}> = {
  splendor: {eyebrow: "SPLENDOR", name: {zh:"璀璨宝石",en:"Splendor"}, description: {zh:"配置 2–4 名模型或人类玩家。轮到你时直接在牌桌选择合法行动；每个 Agent Harness 都可独立设置思考强度。",en:"Configure 2–4 model or human players. On your turn, pick a legal action at the table; each agent harness can use its own reasoning effort."}, badge: "PLAYABLE", note: {zh:"完整基础版引擎",en:"Full base-game engine"}},
  azul: {eyebrow: "AZUL", name: {zh:"花砖物语",en:"Azul"}, description: {zh:"从工厂展示区或中央区选取同色花砖，规划图案线并铺设墙面；兼顾相邻计分、地板罚分与终局时机。",en:"Draft one color from factories or the center, fill pattern lines and tile your wall while balancing adjacency, floor penalties and endgame timing."}, badge: "PLAYABLE BETA", note: {zh:"选砖 · 拼墙 · 空间规划",en:"Draft · tile · spatial planning"}},
  ark_nova: {eyebrow: "ARK NOVA", name: {zh:"方舟动物园",en:"Ark Nova"}, description: {zh:"基础版 255 张实体卡、5 种行动牌与新手地图已接入可审计语义引擎，覆盖条件、费用、触发、互动、收入与终局计分。",en:"All 255 physical base cards, five Action cards, and the beginner map run through an auditable semantic engine covering requirements, costs, triggers, interaction, income, and final scoring."}, badge: "OFFICIAL BASE CANDIDATE", note: {zh:"完整卡牌语义 · Map 0 · P8 门禁",en:"Complete card semantics · Map 0 · P8 gate"}},
  brass_birmingham: {eyebrow: "BRASS: BIRMINGHAM", name: {zh:"伯明翰",en:"Brass: Birmingham"}, description: {zh:"测试模型在双时代经济网络中的长期规划：产业建设、资源来源、商人出售、动态顺位和运河到铁路的资产转换。",en:"Test long-term planning in a two-era economic network: industry building, resource sourcing, merchant selling, dynamic turn order and canal-to-rail transitions."}, badge: "PLAYABLE BETA", note: {zh:"产业 · 网络 · 双时代经济",en:"Industry · network · two-era economy"}},
  century_spice_road: {eyebrow: "CENTURY: SPICE ROAD", name: {zh:"香料之路",en:"Century: Spice Road"}, description: {zh:"经营自己的商队：获取商人牌、升级或交换香料、争夺金币银币，并抢先完成高分订单。支持 2–5 名玩家。",en:"Run your caravan: acquire merchant cards, upgrade or trade spices, race for gold and silver coins to fulfill high-score orders. 2–5 players."}, badge: "CLASSIC BASE", note: {zh:"商人牌 · 香料引擎 · 订单竞速",en:"Merchant cards · spice engine · order race"}},
  seven_wonders: {eyebrow: "7 WONDERS", name: {zh:"七大奇迹",en:"7 Wonders"}, description: {zh:"在三个时代中密封选牌并传递手牌，通过生产、贸易、军事、科技与奇迹建设塑造古代文明。支持 3–7 名玩家。",en:"Draft sealed choices across three Ages, passing hands while developing production, trade, military, science and a Wonder. 3–7 players."}, badge: "SECOND EDITION BASE", note: {zh:"轮抽 · 邻城贸易 · 七维计分",en:"Draft · neighbor trade · seven-part scoring"}},
};
const BACKENDS: Record<Backend, {label: Record<Lang, string>; url: string; key: string; model: string}> = {
  openai: { label: {zh: "OpenAI 兼容", en: "OpenAI-compatible"}, url: "https://api.openai.com/v1", key: "", model: "" },
  anthropic: { label: {zh: "Anthropic", en: "Anthropic"}, url: "https://api.anthropic.com", key: "", model: "" },
  gemini: { label: {zh: "Gemini", en: "Gemini"}, url: "https://generativelanguage.googleapis.com/v1beta", key: "", model: "" },
  claude: { label: {zh: "Claude Code", en: "Claude Code"}, url: "https://api.anthropic.com", key: "", model: "" },
  pi: { label: {zh: "Pi", en: "Pi"}, url: "https://api.openai.com/v1", key: "", model: "" },
  codex: { label: {zh: "Codex Harness", en: "Codex Harness"}, url: "https://api.openai.com/v1", key: "", model: "" },
  opencode: { label: {zh: "OpenCode Harness", en: "OpenCode Harness"}, url: "https://api.deepseek.com", key: "", model: "" },
  dsh: { label: {zh: "DeepSeek Harness", en: "DeepSeek Harness"}, url: "https://api.deepseek.com", key: "", model: "" },
  hermes: { label: {zh: "Hermes Agent", en: "Hermes Agent"}, url: "https://api.deepseek.com", key: "", model: "" },
  minimal: { label: {zh: "Minimal Harness", en: "Minimal Harness"}, url: "https://api.deepseek.com", key: "", model: "" },
  human: { label: {zh: "人类玩家", en: "Human player"}, url: "", key: "", model: "" },
  random: { label: {zh: "随机基线", en: "Random baseline"}, url: "", key: "", model: "" },
};
const HARNESS_BACKENDS = new Set<Backend>(["claude", "pi", "codex", "opencode", "dsh", "hermes", "minimal"]);
const REASONING_OPTIONS: {value: ReasoningEffort; label: Record<Lang,string>}[] = [
  {value: "none", label: {zh: "关闭", en: "Off"}}, {value: "minimal", label: {zh: "Minimal", en: "Minimal"}},
  {value: "low", label: {zh: "Low", en: "Low"}}, {value: "medium", label: {zh: "Medium", en: "Medium"}},
  {value: "high", label: {zh: "High", en: "High"}}, {value: "max", label: {zh: "Max", en: "Max"}},
  {value: "xhigh", label: {zh: "XHigh", en: "XHigh"}},
];
const PROVIDERS: Record<Provider, {label: Record<Lang,string>; backend: Backend; url: string; models: string[]; note: Record<Lang,string>}> = {
  custom: {label: {zh:"自定义 / 本地模型",en:"Custom / Local"}, backend: "openai", url: "", models: [], note: {zh:"网关代理、本地模型、特殊 endpoint：手动填 Endpoint + 模型 ID。运行时选对应的执行方式",en:"Gateway, local model, or special endpoint: enter endpoint + model ID. Pick the runtime separately"}},
  claude_code: {label: {zh:"Claude Code",en:"Claude Code"}, backend: "claude", url: "https://api.anthropic.com", models: ["claude-sonnet-4-6", "claude-opus-4-6"], note: {zh:"Claude Code 持久 session + 座位隔离 MCP",en:"Persistent session + seat-isolated MCP"}},
  pi: {label: {zh:"Pi",en:"Pi"}, backend: "pi", url: "https://api.openai.com/v1", models: ["gpt-5.6"], note: {zh:"Pi 持久 session + AgentBGA 专用工具扩展；兼容自定义 OpenAI Endpoint",en:"Persistent session + AgentBGA tool extension; any OpenAI-compatible endpoint"}},
  codex: {label: {zh:"Codex",en:"Codex"}, backend: "codex", url: "https://api.openai.com/v1", models: ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex-spark"], note: {zh:"可复用本机 codex login 的 ChatGPT 订阅，或使用按量 API Key；自定义 Endpoint 必须支持 Responses API",en:"Reuse the local codex login ChatGPT subscription or use a metered API key; custom endpoints must support the Responses API"}},
  opencode: {label: {zh:"OpenCode",en:"OpenCode"}, backend: "opencode", url: "https://api.deepseek.com", models: ["deepseek-v4-flash", "deepseek-v4-pro"], note: {zh:"OpenCode 持久 session + 座位隔离 MCP",en:"Persistent session + seat-isolated MCP"}},
  dsh: {label: {zh:"DeepSeek Harness",en:"DeepSeek Harness"}, backend: "dsh", url: "https://api.deepseek.com", models: ["deepseek-v4-flash", "deepseek-v4-pro"], note: {zh:"DeepSeek Harness (dsh) headless + 座位隔离 MCP；每回合独立 session，workspace 笔记持久",en:"dsh headless + seat-isolated MCP; fresh session each turn, workspace notes persist"}},
  hermes: {label: {zh:"Hermes Agent",en:"Hermes Agent"}, backend: "hermes", url: "https://api.deepseek.com", models: ["deepseek-v4-flash", "deepseek-v4-pro"], note: {zh:"Hermes Agent 持久 session + 独立 HERMES_HOME + 座位隔离 MCP",en:"Persistent session + isolated HERMES_HOME + seat-isolated MCP"}},
  minimal: {label: {zh:"Minimal Harness",en:"Minimal Harness"}, backend: "minimal", url: "https://api.deepseek.com", models: ["deepseek-v4-flash", "deepseek-v4-pro"], note: {zh:"纯 Python minimal harness；直接 LLM API + 5 工具；无外部进程，认知干预可配置",en:"Pure-Python minimal harness; direct LLM API + 5 tools; no external process"}},
  deepseek: {label: {zh:"DeepSeek 官方",en:"DeepSeek official"}, backend: "openai", url: "https://api.deepseek.com", models: ["deepseek-v4-flash", "deepseek-v4-pro"], note: {zh:"官方按量付费 API",en:"Official pay-as-you-go API"}},
  dashscope: {label: {zh:"阿里云百炼",en:"Alibaba Bailian"}, backend: "openai", url: "https://dashscope.aliyuncs.com/compatible-mode/v1", models: ["qwen3.7-plus", "qwen3.6-plus", "qwen3.5-flash", "qwen3.7-max"], note: {zh:"华北 2 按量付费，不是 Coding Plan",en:"North-China 2 pay-as-you-go, not Coding Plan"}},
  zhipu: {label: {zh:"智谱开放平台",en:"Zhipu Open Platform"}, backend: "openai", url: "https://open.bigmodel.cn/api/paas/v4", models: ["glm-5.2", "glm-5", "glm-4.7"], note: {zh:"开放平台按量付费 Endpoint",en:"Open-platform pay-as-you-go endpoint"}},
  minimax: {label: {zh:"MiniMax 官方",en:"MiniMax official"}, backend: "openai", url: "https://api.minimaxi.com/v1", models: ["MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.5-highspeed"], note: {zh:"国内开放平台 OpenAI 兼容 API",en:"China open-platform OpenAI-compatible API"}},
};

function player(seed: number, backend: Backend = "openai"): PlayerForm {
  return { id: `player-${seed}-${backend}`, name: `Agent ${seed}`, provider: "custom", backend, model: "", base_url: BACKENDS[backend].url, api_key: "", auth_mode: "api_key", reasoning_effort: "max" };
}

function deepseekHarnessPlayer(seed: number, backend: "opencode" | "dsh" | "hermes" | "minimal"): PlayerForm {
  return {
    id: `player-${seed}-${backend}`, name: `Agent ${seed}`, provider: backend, backend,
    model: "deepseek-v4-flash", base_url: "https://api.deepseek.com", api_key: "",
    auth_mode: "api_key", reasoning_effort: "max",
  };
}

function codexHarnessPlayer(seed: number): PlayerForm {
  return {
    id: `player-${seed}-codex`, name: `Agent ${seed}`, provider: "codex", backend: "codex",
    model: "gpt-5.6", base_url: "https://api.openai.com/v1", api_key: "",
    auth_mode: "api_key", reasoning_effort: "max",
  };
}

function humanPlayer(seed: number): PlayerForm {
  return {id: `player-${seed}-human`, name: seed === 1 ? "你" : `玩家 ${seed}`, provider: "custom", backend: "human", model: "", base_url: "", api_key: "", auth_mode: "api_key", reasoning_effort: "max"};
}

function api(path: string) { return path; }

function Gem({color, value, compact = false}: {color: string; value: number; compact?: boolean}) {
  const lang = useLang();
  const meta = GEM_META[color];
  return <span className={`gem gem-${color} ${compact ? "gem-compact" : ""}`} title={meta?.label[lang]}>
    <b>{meta?.mark}</b><span>{value}</span>
  </span>;
}

function Cost({cost}: {cost: Record<string, number>}) {
  return <div className="costs">{BONUS_ORDER.filter(color => (cost[color] ?? 0) > 0).map(color =>
    <Gem key={color} color={color} value={cost[color]} compact />
  )}</div>;
}

function DevCard({card, small = false, reserved = false}: {card: Card; small?: boolean; reserved?: boolean}) {
  return <article className={`dev-card card-${card.bonus} ${small ? "dev-card-small" : ""} ${reserved ? "dev-card-reserved" : ""}`} title={card.id}>
    <div className="card-top"><strong>{card.points || "·"}</strong><span>{GEM_META[card.bonus]?.mark}</span></div>
    <Cost cost={card.cost} />
  </article>;
}

function PlayerPanel({player: p, identity, active}: {player: PlayerView; identity?: Snapshot["players"][number]; active: boolean}) {
  const lang = useLang(); const t = makeT(lang);
  return <section className={`player-panel ${active ? "active-player" : ""}`}>
    <header>
      <div><span className="seat-label">{t("seat_label")} {p.seat + 1}</span><h3>{identity?.name || `Agent ${p.seat + 1}`}</h3></div>
      <div className="score"><strong>{p.score}</strong><span>{lang === "zh" ? "声望" : "pts"}</span></div>
    </header>
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}{identity?.reasoning_effort && <b>{lang === "zh" ? `思考：${identity.reasoning_effort}` : `reasoning: ${identity.reasoning_effort}`}</b>}</div>
    <div className="asset-row"><span className="asset-title">{t("tokens")}</span><div>{GEM_ORDER.map(c => <Gem key={c} color={c} value={p.tokens[c]} compact />)}</div></div>
    <div className="asset-row"><span className="asset-title">{t("engine")}</span><div>{BONUS_ORDER.map(c => <Gem key={c} color={c} value={p.bonuses[c]} compact />)}</div></div>
    <div className="owned-head"><span>{lang === "zh" ? "已购发展牌" : "Purchased cards"}</span><b>{p.purchased_count}</b></div>
    <div className="owned-cards">{p.purchased.length ? p.purchased.map(card => <DevCard key={card.id} card={card} small />) : <em>{lang === "zh" ? "尚未建立引擎" : "No engine yet"}</em>}</div>
    <div className="reserve-row"><span>{t("reserved")} {p.reserved_count}/3</span><div>{p.reserved.map((card, i) => "hidden" in card ? <i className="reserved-hidden" key={i}>?</i> : <DevCard key={card.id} card={card} reserved />)}</div></div>
    {p.nobles.length > 0 && <div className="noble-owned">{t("nobles_owned")} × {p.nobles.length}</div>}
  </section>;
}

function Spices({pool, compact = false}: {pool: Partial<SpicePool>; compact?: boolean}) {
  const lang = useLang();
  return <span className={`spice-row ${compact ? "spice-row-compact" : ""}`}>{SPICE_ORDER.filter(spice => (pool[spice] ?? 0) > 0).map(spice =>
    <i key={spice} className={`spice spice-${spice}`} title={SPICE_META[spice].label[lang]}><b>{SPICE_META[spice].short[lang]}</b><span>{pool[spice]}</span></i>
  )}</span>;
}

function spiceText(pool: Record<string, unknown>, lang: Lang) {
  return SPICE_ORDER.filter(spice => Number(pool[spice] ?? 0) > 0)
    .map(spice => `${SPICE_META[spice].label[lang]} × ${Number(pool[spice])}`).join(lang === "zh" ? "、" : ", ");
}

function merchantText(card: CenturyMerchant, lang: Lang) {
  if (card.kind === "upgrade") return lang === "zh" ? `升级 ${card.upgrades} 级` : `Upgrade × ${card.upgrades}`;
  if (card.kind === "gain") return lang === "zh" ? "获得香料" : "Gain spice";
  return lang === "zh" ? "重复交易" : "Repeat trade";
}

function CenturyMerchantCard({card, small = false}: {card: CenturyMerchant; small?: boolean}) {
  const lang = useLang();
  return <article className={`century-merchant-card merchant-${card.kind} ${small ? "century-card-small" : ""}`} title={card.id}>
    <header><span>{card.kind === "gain" ? "HARVEST" : card.kind === "upgrade" ? "UPGRADE" : "TRADE"}</span><b>{card.kind === "upgrade" ? `↑${card.upgrades}` : "◆"}</b></header>
    <strong>{merchantText(card, lang)}</strong>
    {card.kind === "trade" && <div className="century-trade"><Spices pool={card.input} compact/><em>→</em><Spices pool={card.output} compact/></div>}
    {card.kind === "gain" && <Spices pool={card.output}/>}
    {card.kind === "upgrade" && <div className="century-upgrade-path">{lang === "zh" ? "黄 → 红 → 绿 → 褐" : "T → S → C → N"}</div>}
  </article>;
}

function CenturyPointCard({card}: {card: CenturyPoint}) {
  return <article className="century-point-card" title={card.id}><strong>{card.points}</strong><span>VP</span><Spices pool={card.cost} compact/></article>;
}

function CenturyPlayerPanel({player: p, identity, active}: {player: CenturyPlayerView; identity?: Snapshot["players"][number]; active: boolean}) {
  const lang = useLang(); const t = makeT(lang);
  const caravanTotal = Object.values(p.spices).reduce((sum, value) => sum + value, 0);
  return <section className={`player-panel century-player-panel ${active ? "active-player" : ""}`}>
    <header><div><span className="seat-label">{t("seat_label")} {p.seat + 1}</span><h3>{identity?.name || `${t("player_label")} ${p.seat + 1}`}</h3></div><div className="century-score"><strong>{p.score}</strong><span>VP</span></div></header>
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}{identity?.reasoning_effort && <b>{lang === "zh" ? `思考：${identity.reasoning_effort}` : `reasoning: ${identity.reasoning_effort}`}</b>}</div>
    <div className="century-caravan"><header><span>{t("caravan_spice")}</span><b>{caravanTotal}/10</b></header><Spices pool={p.spices}/></div>
    <div className="century-assets"><span>{t("gold_coin")} <b>{p.coins.gold}</b></span><span>{t("silver_coin")} <b>{p.coins.silver}</b></span><span>{t("orders")} <b>{p.point_cards.length}</b></span></div>
    <div className="century-hand-head"><span>{t("avail_merchant")}</span><b>{p.hand.length}</b><small>{t("played")} {p.played.length}</small></div>
    <div className="century-hand">{p.hand.map(card => <CenturyMerchantCard key={card.id} card={card} small/>)}{p.hand.length === 0 && <em>{t("need_rest")}</em>}</div>
  </section>;
}

function CenturyBoard({view}: {view?: CenturyView}) {
  const lang = useLang(); const t = makeT(lang);
  if (!view) return null;
  return <div className="century-board">
    <section className="century-status"><div><span>CENTURY · SPICE ROAD</span><h2>{t("century_status")}</h2></div><p>{t("century_note")} {view.caravan_limit} {t("caravan_unit")}</p><code>{view.rules_version}</code></section>
    <section className="century-point-market"><header><div><span>{t("point_cards")}</span><h3>{t("order_market")}</h3></div><b>{t("deck_label")} {view.point_deck_count}</b></header><div>{view.point_market.map((card, index) => <div className="century-point-slot" key={card.id}>{index === 0 && view.coins.gold > 0 && <span className="century-coin coin-gold">{t("gold_coin")} × {view.coins.gold}</span>}{index === view.coins.silver_position && view.coins.silver > 0 && <span className="century-coin coin-silver">{t("silver_coin")} × {view.coins.silver}</span>}<CenturyPointCard card={card}/></div>)}</div></section>
    <section className="century-merchant-market"><header><div><span>{t("merchant_cards")}</span><h3>{t("trade_market")}</h3></div><b>{t("deck_label")} {view.merchant_deck_count}</b></header><div>{view.merchant_market.map((slot, index) => <div className="century-merchant-slot" key={slot.card.id}><span className="century-market-index">0{index + 1}</span><CenturyMerchantCard card={slot.card}/><div className="century-card-spices"><span>{t("card_spice")}</span><Spices pool={slot.spices} compact/></div></div>)}</div></section>
    <section className="century-legend"><span><i className="spice spice-turmeric"/>{SPICE_META.turmeric.label[lang]} · 1</span><span><i className="spice spice-saffron"/>{SPICE_META.saffron.label[lang]} · 2</span><span><i className="spice spice-cardamom"/>{SPICE_META.cardamom.label[lang]} · 3</span><span><i className="spice spice-cinnamon"/>{SPICE_META.cinnamon.label[lang]} · 4</span><small>{t("century_legend_note")}</small></section>
  </div>;
}

const SEVEN_RESOURCE_META: Record<SevenResource, {symbol: string; label: Record<Lang, string>}> = {
  wood: {symbol: "🪵", label: {zh: "木材", en: "Wood"}}, stone: {symbol: "🪨", label: {zh: "石材", en: "Stone"}},
  clay: {symbol: "🧱", label: {zh: "黏土", en: "Clay"}}, ore: {symbol: "💎", label: {zh: "矿石", en: "Ore"}},
  glass: {symbol: "🫙", label: {zh: "玻璃", en: "Glass"}}, papyrus: {symbol: "📜", label: {zh: "莎草纸", en: "Papyrus"}},
  cloth: {symbol: "🧵", label: {zh: "织物", en: "Textile"}},
};
const SEVEN_COLOR_LABELS: Record<SevenCard["color"], Record<Lang, string>> = {
  brown: {zh:"原材料",en:"Raw material"}, gray: {zh:"制成品",en:"Manufactured good"}, blue: {zh:"市政",en:"Civilian"},
  yellow: {zh:"商业",en:"Commercial"}, red: {zh:"军事",en:"Military"}, green: {zh:"科技",en:"Scientific"}, purple: {zh:"协会",en:"Guild"},
};
const SEVEN_COLOR_ORDER: SevenCard["color"][] = ["brown", "gray", "blue", "yellow", "red", "green", "purple"];
const SEVEN_SCIENCE_LABELS: Record<string, Record<Lang, string>> = {
  compass: {zh:"罗盘",en:"Compass"}, gear: {zh:"齿轮",en:"Gear"}, tablet: {zh:"石板",en:"Tablet"},
};
const SEVEN_SCIENCE_SYMBOLS: Record<string, string> = {compass: "🧭", tablet: "🗿", gear: "⚙️"};
const SEVEN_SPECIAL_LABELS: Record<string, Record<Lang, string>> = {
  free_first_color: {zh:"每种颜色的第一张牌免费",en:"First card of each color is free"},
  free_first_age: {zh:"每个时代第一张牌免费",en:"First card of each Age is free"},
  free_last_age: {zh:"每个时代最后一张牌免费",en:"Last card of each Age is free"},
  play_seventh: {zh:"每个时代可打出第七张牌",en:"Play the seventh card each Age"},
  build_discard: {zh:"从弃牌堆免费建造一张牌",en:"Build one discarded card for free"},
};
const SEVEN_SPECIAL_SYMBOLS: Record<string, string> = {
  free_first_color: "🎨✨", free_first_age: "🌅✨", free_last_age: "🌇✨", play_seventh: "7", build_discard: "♻️🏛️",
};

function SevenResourceIcon({resource, count = 1}: {resource: SevenResource; count?: number}) {
  const lang = useLang();
  const meta = SEVEN_RESOURCE_META[resource];
  return <i title={meta.label[lang]} aria-label={`${meta.label[lang]}${count > 1 ? ` × ${count}` : ""}`} className={`seven-resource resource-${resource}`}><span aria-hidden="true">{meta.symbol}</span>{count > 1 ? <b aria-hidden="true">{count}</b> : null}</i>;
}

function SevenResourceOptions({resources}: {resources: SevenResource[]}) {
  const lang = useLang();
  return <span className="seven-resource-options" title={resources.map(resource => SEVEN_RESOURCE_META[resource].label[lang]).join(" / ")}>
    {resources.map((resource, index) => <span key={`${resource}-${index}`}>{index > 0 && <em>/</em>}<SevenResourceIcon resource={resource}/></span>)}
  </span>;
}

function SevenCost({cost, coins = 0}: {cost: Record<SevenResource, number>; coins?: number}) {
  const lang = useLang();
  const resources = (Object.keys(SEVEN_RESOURCE_META) as SevenResource[]).filter(resource => cost[resource] > 0);
  return <span className="seven-cost">{resources.map(resource => <SevenResourceIcon key={resource} resource={resource} count={cost[resource]}/>)}{coins > 0 && <i className="seven-coin-cost" title={lang === "zh" ? `${coins} 金币` : `${coins} coins`} aria-label={lang === "zh" ? `${coins} 金币` : `${coins} coins`}><span aria-hidden="true">💰</span><b aria-hidden="true">{coins}</b></i>}{!resources.length && !coins && <i className="seven-free-cost" title={lang === "zh" ? "免费" : "Free"} aria-label={lang === "zh" ? "免费" : "Free"}>✨</i>}</span>;
}

function sevenScopeText(scope: SevenBenefit["scope"], lang: Lang) {
  const zh = lang === "zh";
  return (scope || []).map(item => item === "self" ? (zh ? "自己" : "your city") : item === "left" ? (zh ? "左邻" : "left neighbor") : (zh ? "右邻" : "right neighbor")).join(zh ? "、" : " + ");
}

function sevenBenefitText(benefit: SevenBenefit, lang: Lang) {
  const zh = lang === "zh"; const amount = benefit.amount ?? 1;
  const color = benefit.color ? SEVEN_COLOR_LABELS[benefit.color][lang] : (benefit.colors || []).map(value => SEVEN_COLOR_LABELS[value][lang]).join("/");
  const scope = sevenScopeText(benefit.scope, lang);
  if (benefit.type === "points") return zh ? `${amount} 胜利点` : `${amount} victory points`;
  if (benefit.type === "coins") return zh ? `${amount} 金币` : `${amount} coins`;
  if (benefit.type === "military") return zh ? `${amount} 军力` : `${amount} military shields`;
  if (benefit.type === "science") return SEVEN_SCIENCE_LABELS[benefit.symbol || ""]?.[lang] || String(benefit.symbol);
  if (benefit.type === "science_wild") return zh ? `${amount} 个任意科技符号` : `${amount} wild science symbol`;
  if (benefit.type === "trade_discount") {
    const direction = (benefit.directions || []).map(value => value === "left" ? (zh ? "左邻" : "left") : (zh ? "右邻" : "right")).join(zh ? "、" : " + ");
    const resources = (benefit.resources || []).map(value => SEVEN_RESOURCE_META[value].label[lang]).join("/");
    return zh ? `向${direction}购买${resources}时每个 ${benefit.coin_cost} 金币` : `Buy ${resources} from ${direction} for ${benefit.coin_cost} coin each`;
  }
  if (benefit.type === "coins_per_card") return zh ? `${scope}每张${color}牌：${amount} 金币` : `${amount} coin per ${color} card in ${scope}`;
  if (benefit.type === "points_per_card") return zh ? `${scope}每张${color}牌：${amount} 分` : `${amount} point per ${color} card in ${scope}`;
  if (benefit.type === "coins_per_stage") return zh ? `${scope}每个奇迹阶段：${amount} 金币` : `${amount} coins per Wonder stage in ${scope}`;
  if (benefit.type === "points_per_stage") return zh ? `${scope}每个奇迹阶段：${amount} 分` : `${amount} point per Wonder stage in ${scope}`;
  if (benefit.type === "points_if_wonder_complete") return zh ? `完成全部奇迹阶段：${amount} 分` : `${amount} points if Wonder is complete`;
  if (benefit.type === "special") return SEVEN_SPECIAL_LABELS[benefit.effect || ""]?.[lang] || String(benefit.effect);
  return benefit.type;
}

function SevenScopeGlyphs({scope}: {scope: SevenBenefit["scope"]}) {
  return <span className="seven-effect-scope" aria-hidden="true">{(scope || []).map(item => <i key={item}>{item === "self" ? "●" : item === "left" ? "←" : "→"}</i>)}</span>;
}

function SevenColorGlyphs({benefit}: {benefit: SevenBenefit}) {
  const colors = benefit.color ? [benefit.color] : (benefit.colors || []);
  return <span className="seven-effect-colors" aria-hidden="true">{colors.map(color => <i key={color} className={`seven-${color}`}/>)}</span>;
}

function SevenBenefitVisual({benefit}: {benefit: SevenBenefit}) {
  const lang = useLang();
  const amount = benefit.amount ?? 1;
  if (benefit.type === "production") return <><b className="seven-production-label">{lang === "zh" ? "生产" : "Produces"}</b><SevenResourceOptions resources={benefit.resources || []}/></>;
  if (benefit.type === "points") return <><b aria-hidden="true">🏆</b><strong aria-hidden="true">{amount}</strong></>;
  if (benefit.type === "coins") return <><b aria-hidden="true">💰</b><strong aria-hidden="true">{amount}</strong></>;
  if (benefit.type === "military") return <><b aria-hidden="true">⚔️</b><strong aria-hidden="true">{amount}</strong></>;
  if (benefit.type === "science") return <strong className="seven-science-symbol" aria-hidden="true">{SEVEN_SCIENCE_SYMBOLS[benefit.symbol || ""] || "🔬"}</strong>;
  if (benefit.type === "science_wild") return <><strong className="seven-science-wild" aria-hidden="true">🧭/🗿/⚙️</strong>{amount > 1 && <strong aria-hidden="true">{amount}</strong>}</>;
  if (benefit.type === "trade_discount") return <><span className="seven-effect-directions" aria-hidden="true">{(benefit.directions || []).map(direction => <i key={direction}>{direction === "left" ? "←" : "→"}</i>)}</span><SevenResourceOptions resources={benefit.resources || []}/></>;
  if (benefit.type === "coins_per_card" || benefit.type === "points_per_card") return <><SevenScopeGlyphs scope={benefit.scope}/><b aria-hidden="true">{benefit.type === "coins_per_card" ? "💰" : "🏆"}</b><strong aria-hidden="true">{amount}</strong><span aria-hidden="true">×</span><SevenColorGlyphs benefit={benefit}/></>;
  if (benefit.type === "coins_per_stage" || benefit.type === "points_per_stage") return <><SevenScopeGlyphs scope={benefit.scope}/><b aria-hidden="true">{benefit.type === "coins_per_stage" ? "💰" : "🏆"}</b><strong aria-hidden="true">{amount}</strong><span aria-hidden="true">×◆</span></>;
  if (benefit.type === "points_if_wonder_complete") return <><span aria-hidden="true">◆✓</span><b aria-hidden="true">🏆</b><strong aria-hidden="true">{amount}</strong></>;
  if (benefit.type === "special") return <strong className="seven-special-symbol" aria-hidden="true">{SEVEN_SPECIAL_SYMBOLS[benefit.effect || ""] || "✨"}</strong>;
  return <strong aria-hidden="true">◆</strong>;
}

function SevenBenefits({benefits, compact = false}: {benefits: SevenBenefit[]; compact?: boolean}) {
  const lang = useLang();
  return <div className={`seven-benefits ${compact ? "compact" : ""}`}>{benefits.map((benefit, index) => {
    const description = sevenBenefitText(benefit, lang);
    return <span className={`seven-benefit benefit-${benefit.type}`} title={description} aria-label={description} key={index}><SevenBenefitVisual benefit={benefit}/></span>;
  })}</div>;
}

function SevenCardTile({card, compact = false}: {card: SevenCard; compact?: boolean}) {
  const lang = useLang();
  return <article className={`seven-card seven-${card.color} ${compact ? "compact" : ""}`} title={card.id}>
    <header><span>AGE {card.age}</span><b>{SEVEN_COLOR_LABELS[card.color][lang]}</b></header>
    <strong>{card.name}</strong>
    <div className="seven-card-cost" title={lang === "zh" ? "建造成本" : "Build cost"}><SevenCost cost={card.cost} coins={card.coin_cost}/></div>
    <SevenBenefits benefits={card.benefits} compact={compact}/>
    {!compact && (card.chain_from.length > 0 || card.chain_to.length > 0) && <footer>{card.chain_from.length > 0 && <span>{lang === "zh" ? "免费前置" : "Free from"}: {card.chain_from.join(" / ")}</span>}{card.chain_to.length > 0 && <span>{lang === "zh" ? "可免费衔接" : "Chains to"}: {card.chain_to.join(" / ")}</span>}</footer>}
  </article>;
}

function SevenResourceProduction({units, compact = false}: {units: SevenResourceUnit[]; compact?: boolean}) {
  const lang = useLang();
  return <div className={`seven-production ${compact ? "compact" : ""}`}>{units.map((unit, index) => {
    const tradeDiscount = unit.kind === "trade_discount";
    const title = tradeDiscount
      ? `${unit.source_name} · ${lang === "zh" ? "邻城交易折扣" : "neighbor trade discount"}`
      : unit.tradeable ? unit.source_name : `${unit.source_name} · ${lang === "zh" ? "仅自己使用" : "owner only"}`;
    return <span className={`${unit.source_color ? `source-colored source-${unit.source_color}` : ""} ${tradeDiscount ? "production-trade-discount" : ""}`} key={`${unit.source_id}-${unit.unit || 0}-${index}`} title={title}>
      {tradeDiscount && <span className="seven-effect-directions" aria-hidden="true">{(unit.directions || []).map(direction => <i key={direction}>{direction === "left" ? "←" : "→"}</i>)}</span>}
      <SevenResourceOptions resources={unit.options}/>{!tradeDiscount && !unit.tradeable && <small aria-label={lang === "zh" ? "仅自己使用" : "Owner only"}>🔒</small>}
    </span>;
  })}</div>;
}

function SevenScienceStats({player, compact = false}: {player: SevenPlayerView; compact?: boolean}) {
  const lang = useLang();
  const counts: Record<"compass" | "tablet" | "gear" | "wild", number> = {compass: 0, tablet: 0, gear: 0, wild: 0};
  const benefits = [
    ...player.city.flatMap(card => card.benefits),
    ...player.wonder_stages.filter(stage => stage.built).flatMap(stage => stage.benefits),
  ];
  for (const benefit of benefits) {
    if (benefit.type === "science" && benefit.symbol && benefit.symbol in counts) counts[benefit.symbol as "compass" | "tablet" | "gear"] += benefit.amount ?? 1;
    if (benefit.type === "science_wild") counts.wild += benefit.amount ?? 1;
  }
  const scienceScore = player.score_breakdown.science ?? 0;
  return <div className={`seven-science-stats ${compact ? "compact" : ""}`} aria-label={lang === "zh" ? `科技符号统计，科技得分 ${scienceScore}` : `Science symbols, ${scienceScore} science points`}>
    <b>{lang === "zh" ? "科技" : "SCI"}</b>
    <span title={SEVEN_SCIENCE_LABELS.compass[lang]}>🧭 <strong>{counts.compass}</strong></span>
    <span title={SEVEN_SCIENCE_LABELS.tablet[lang]}>🗿 <strong>{counts.tablet}</strong></span>
    <span title={SEVEN_SCIENCE_LABELS.gear[lang]}>⚙️ <strong>{counts.gear}</strong></span>
    {counts.wild > 0 && <span title={lang === "zh" ? "任意科技符号" : "Wild science"}>✨ <strong>{counts.wild}</strong></span>}
    <em title={lang === "zh" ? `当前科技得分 ${scienceScore}` : `Current science score ${scienceScore}`}>🏆 {scienceScore}</em>
  </div>;
}

function SevenCivilianScores({player, compact = false}: {player: SevenPlayerView; compact?: boolean}) {
  const lang = useLang();
  const cards = player.city.filter(card => card.color === "blue");
  return <div className={`seven-civilian-scores ${compact ? "compact" : ""}`} aria-label={lang === "zh" ? "已建造市政牌得分" : "Built civilian card scores"}>
    <b>{lang === "zh" ? "市政" : "CIV"}</b>
    <div>{cards.map(card => <span key={card.id} title={`${card.name} · ${card.points} ${lang === "zh" ? "胜利点" : "victory points"}`}><i>{card.name}</i><em>🏆 {card.points}</em></span>)}{!cards.length && <small>—</small>}</div>
  </div>;
}

function SevenGuildScores({player, compact = false}: {player: SevenPlayerView; compact?: boolean}) {
  const lang = useLang();
  const cards = player.city.filter(card => card.color === "purple");
  return <div className={`seven-guild-scores ${compact ? "compact" : ""}`} aria-label={lang === "zh" ? "已建造协会牌得分" : "Built guild card scores"}>
    <b>{lang === "zh" ? "协会" : "GUILD"}</b>
    <div>{cards.map(card => {
      const points = card.current_points ?? 0;
      return <span key={card.id} title={`${card.name} · ${points} ${lang === "zh" ? "当前胜利点" : "current victory points"}`}><i>{card.name}</i><em>🏆 {points}</em></span>;
    })}{!cards.length && <small>—</small>}</div>
  </div>;
}

function SevenMilitaryTokens({player, compact = false}: {player: SevenPlayerView; compact?: boolean}) {
  const lang = useLang();
  const ages = player.military_tokens_by_age;
  return <div className={`seven-military-tokens ${compact ? "compact" : ""}`} aria-label={lang === "zh" ? "各时代战争得分 Token" : "Military conflict tokens by Age"}>
    <b>{lang === "zh" ? "战争" : "WAR"}</b>
    <div>{ages.map((tokens, index) => tokens.length > 0 && <span className={`seven-war-age age-${index + 1}`} key={index}><i>{["I", "II", "III"][index]}</i>{tokens.map((token, tokenIndex) => <em className={token < 0 ? "defeat" : "victory"} key={tokenIndex}>{token}</em>)}</span>)}{!player.military_tokens.length && <small>—</small>}</div>
  </div>;
}

function SevenWonderStageTile({stage}: {stage: SevenStage}) {
  const lang = useLang();
  return <div className={`seven-stage ${stage.built ? "built" : ""}`}><header><b>{stage.stage}</b><span>{stage.built ? (lang === "zh" ? "已建成" : "Built") : (lang === "zh" ? "未建造" : "Unbuilt")}</span></header><SevenCost cost={stage.cost}/><SevenBenefits benefits={stage.benefits} compact/></div>;
}

function SevenPlayerPanel({player: p, identity, active}: {player: SevenPlayerView; identity?: Snapshot["players"][number]; active: boolean}) {
  const lang = useLang(); const t = makeT(lang); const zh = lang === "zh";
  return <section className={`player-panel seven-player-panel ${active ? "active-player" : ""}`}>
    <header><div><span className="seat-label">{t("seat_label")} {p.seat + 1}</span><h3>{identity?.name || `${t("player_label")} ${p.seat + 1}`}</h3></div><div className="seven-score" title={zh ? `${p.score} 胜利点` : `${p.score} victory points`}><strong>{p.score}</strong><span>🏆</span></div></header>
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}</div>
    <div className="seven-wonder-name"><div><span>{p.wonder_name} · {p.wonder_side.toUpperCase()}</span><small>{zh ? "城市初始资源" : "Starting resource"}</small></div><SevenResourceIcon resource={p.starting_resource}/></div>
    <div className="seven-production-block"><b>{zh ? "每轮生产能力" : "Production each round"}</b><SevenResourceProduction units={p.resource_units} compact/><SevenScienceStats player={p} compact/><SevenCivilianScores player={p} compact/><SevenGuildScores player={p} compact/><SevenMilitaryTokens player={p} compact/></div>
    <div className="seven-stages">{p.wonder_stages.map(stage => <SevenWonderStageTile key={stage.stage} stage={stage}/>)}</div>
    <div className="seven-tableau-cards">{p.city.length ? p.city.map(card => <span key={card.id} className={`seven-${card.color}`} title={card.benefits.map(benefit => sevenBenefitText(benefit, lang)).join(" · ")}>{card.name}</span>) : <em>{zh ? "尚未建造建筑" : "No buildings yet"}</em>}</div>
    <div className="seven-assets"><span title={zh ? `${p.coins} 金币` : `${p.coins} coins`}>💰 <b>{p.coins}</b></span><span title={zh ? `${p.military_strength} 军力` : `${p.military_strength} military`}>⚔️ <b>{p.military_strength}</b></span><span title={zh ? `${p.hand_count} 张手牌` : `${p.hand_count} cards`}>🃏 <b>{p.hand_count}</b></span>{p.choice_submitted && <em>{zh ? "已密封提交" : "Choice sealed"}</em>}</div>
  </section>;
}

function sevenPaymentSummary(action: Record<string, unknown>, lang: Lang, names?: Record<number, string>) {
  const zh = lang === "zh"; const payment = (action.payment || {}) as Record<string, number>;
  const purchases = (action.purchases || []) as SevenPurchase[];
  if (action.free_source) return zh ? `免费建造（${action.free_source}）` : `Build free (${action.free_source})`;
  const parts = purchases.map(purchase => {
    const neighbor = names?.[purchase.seat] || `${zh ? "座位" : "seat"} ${purchase.seat + 1}`;
    const direction = purchase.direction === "left" ? (zh ? "左邻" : "left") : (zh ? "右邻" : "right");
    const resources = Object.entries(purchase.resources).filter(([, amount]) => Number(amount) > 0).map(([resource, amount]) => `${SEVEN_RESOURCE_META[resource as SevenResource].symbol}${Number(amount) > 1 ? Number(amount) : ""}`).join(" ");
    return zh ? `向${direction} ${neighbor} 购买 ${resources}，支付 💰${purchase.coins}` : `Buy ${resources} from ${direction} ${neighbor} for 💰${purchase.coins}`;
  });
  if ((payment.bank || 0) > 0) parts.unshift(zh ? `向银行支付 💰${payment.bank}` : `Pay bank 💰${payment.bank}`);
  return parts.length ? parts.join(zh ? "；" : "; ") : (zh ? "使用自己的生产能力" : "Use your own production");
}

function SevenActionPicker({actions, view, names, disabled, submitting, onChoose}: {actions: LegalAction[]; view?: SevenView; names: Record<number, string>; disabled: boolean; submitting: string; onChoose: (item: LegalAction) => void}) {
  const lang = useLang(); const zh = lang === "zh";
  const viewer = view?.players.find(player => player.seat === view.viewer_seat);
  const cards = viewer?.hand.filter((card): card is SevenCard => !("hidden" in card)) || [];
  const cardIds = new Set(cards.map(card => card.id));
  const remaining = actions.filter(item => !cardIds.has(String(item.action.card_id || "")));
  return <div className="seven-action-picker">{cards.map(card => {
    const options = actions.filter(item => item.action.card_id === card.id);
    return <section key={card.id} className="seven-action-card"><SevenCardTile card={card}/><div>{options.map(item => {
      const kind = String(item.action.type); const payment = sevenPaymentSummary(item.action, lang, names);
      const label = kind === "sell_card" ? (zh ? "出售这张牌 · 获得 💰3" : "Sell this card · gain 💰3")
        : kind === "build_wonder" ? (zh ? `用于建造奇迹第 ${item.action.stage} 阶段 · ${payment}` : `Use for Wonder stage ${item.action.stage} · ${payment}`)
        : (zh ? `建造这张牌 · ${payment}` : `Build this card · ${payment}`);
      return <button key={item.id} className={`seven-action-option option-${kind}`} disabled={disabled} title={item.id} onClick={() => onChoose(item)}><b>{kind === "sell_card" ? "💰" : kind === "build_wonder" ? "◆" : "🏛️"}</b><span>{label}</span>{submitting === item.id && <i>{zh ? "提交中…" : "Submitting…"}</i>}</button>;
    })}</div></section>;
  })}{remaining.length > 0 && <section className="seven-extra-actions">{remaining.map(item => <button key={item.id} disabled={disabled} onClick={() => onChoose(item)}>{humanActionText(item.action, lang)}</button>)}</section>}</div>;
}

function SevenCityCardGroups({cards}: {cards: SevenCard[]}) {
  const lang = useLang();
  return <div className="seven-city-card-groups">{SEVEN_COLOR_ORDER.map(color => {
    const group = cards.filter(card => card.color === color);
    if (!group.length) return null;
    return <div className={`seven-city-card-group group-${color}`} aria-label={`${SEVEN_COLOR_LABELS[color][lang]} × ${group.length}`} key={color}>{group.map(card => <span key={card.id} className={`seven-${card.color}`} title={card.benefits.map(benefit => sevenBenefitText(benefit, lang)).join(" · ")}>{card.name}</span>)}</div>;
  })}</div>;
}

function SevenSpectatorHands({views, identities}: {views: SevenView[]; identities: Snapshot["players"]}) {
  const lang = useLang(); const zh = lang === "zh";
  const hands = identities.map(identity => {
    const seatView = views.find(candidate => candidate.viewer_seat === identity.seat);
    const player = seatView?.players.find(candidate => candidate.seat === identity.seat);
    const cards = player?.hand.filter((card): card is SevenCard => !("hidden" in card)) ?? [];
    return {identity, player, cards};
  });
  return <section className="seven-spectator-hands">
    <header><div><span>SPECTATOR HANDS</span><h3>{zh ? "所有座位的当前手牌" : "Current hands at every seat"}</h3></div><small>{zh ? "纯 Agent 对战 · 观察者上帝视角" : "Agent-only match · omniscient spectator view"}</small></header>
    <div>{hands.map(({identity, player, cards}) => <article className={`seven-seat-hand ${player?.choice_submitted ? "choice-submitted" : ""}`} key={identity.seat}>
      <header><div><span>{zh ? `座位 ${identity.seat + 1}` : `SEAT ${identity.seat + 1}`}</span><strong>{identity.name}</strong><code>{identity.backend}</code></div><p>{player?.choice_submitted && <em>{zh ? "已密封提交" : "CHOICE SEALED"}</em>}<b>{player?.hand_count ?? cards.length} {zh ? "张" : "cards"}</b></p></header>
      <div className="seven-seat-hand-cards">{cards.map(card => <SevenCardTile key={card.id} card={card}/>)}{!cards.length && <em>{zh ? "当前没有手牌" : "No cards in hand"}</em>}</div>
    </article>)}</div>
  </section>;
}

function SevenPassRoutes({playerCount, currentAge, identities}: {playerCount: number; currentAge: number; identities: Snapshot["players"]}) {
  const lang = useLang(); const zh = lang === "zh";
  return <div className="seven-pass-routes" aria-label={zh ? "三个时代的手牌传递顺序" : "Hand passing order for all three Ages"}>{[1, 2, 3].map(age => {
    const left = age !== 2;
    const step = left ? -1 : 1;
    const seats = Array.from({length: playerCount + 1}, (_, index) => (index * step + playerCount) % playerCount);
    const route = seats.map(seat => identities.find(identity => identity.seat === seat)?.name || `${zh ? "座位" : "Seat"} ${seat + 1}`).join(" → ");
    return <div className={age === currentAge ? "active" : ""} title={`${zh ? `时代 ${age}` : `Age ${age}`} · ${route}`} key={age}>
      <b>{zh ? `时代 ${age}` : `AGE ${age}`}</b><em>{left ? (zh ? "← 左传" : "← LEFT") : (zh ? "右传 →" : "RIGHT →")}</em>
      <ol>{seats.map((seat, index) => <li key={`${seat}-${index}`}><i>{seat + 1}</i>{index < seats.length - 1 && <span>→</span>}</li>)}</ol>
    </div>;
  })}</div>;
}

function SevenBoard({view, spectatorViews, identities = []}: {view?: SevenView; spectatorViews?: SevenView[]; identities?: Snapshot["players"]}) {
  const lang = useLang(); const zh = lang === "zh";
  if (!view) return null;
  const viewer = view.players.find(player => player.seat === view.viewer_seat) ?? view.players[0];
  const visibleHand = viewer.hand.filter((card): card is SevenCard => !("hidden" in card));
  return <div className="seven-board">
    <section className="seven-status"><div><span>7 WONDERS · BASE GAME</span><h2>{zh ? `时代 ${view.age} · 第 ${view.pick} 轮选牌` : `Age ${view.age} · Pick ${view.pick}`}</h2></div><p>{zh ? `手牌向${view.pass_direction === "left" ? "左" : "右"}传递；选择在所有座位提交前保持密封。资源是每轮可重复使用的生产能力。` : `Hands pass ${view.pass_direction}; choices remain sealed until all seats submit. Resources are reusable production, not inventory.`}</p><code>{view.rules_version}</code></section>
    <section className="seven-draft-track"><div>{[1,2,3].map(age => <span key={age} className={age === view.age ? "active" : age < view.age ? "done" : ""}>AGE {age}</span>)}</div><b>{zh ? `弃牌 ${view.discard_count}` : `Discard ${view.discard_count}`}</b><small>{zh ? `已提交 ${view.pending_choice_seats.length}/${view.players.length}` : `Sealed ${view.pending_choice_seats.length}/${view.players.length}`}</small></section>
    {spectatorViews ? <SevenSpectatorHands views={spectatorViews} identities={identities}/> : <section className="seven-hand"><header><div><span>DRAFT HAND</span><h3>{zh ? `座位 ${viewer.seat + 1} 的当前手牌` : `Seat ${viewer.seat + 1} current hand`}</h3></div><b>{visibleHand.length || viewer.hand_count} {zh ? "张" : "cards"}</b></header><div>{visibleHand.map(card => <SevenCardTile key={card.id} card={card}/>)}{!visibleHand.length && <em>{zh ? "该手牌对当前观察者隐藏" : "This hand is hidden from the current viewer"}</em>}</div></section>}
    <section className="seven-cities"><header><div><span>CITY TABLEAUS</span><h3>{zh ? "公开城市与生产能力" : "Public cities and production"}</h3></div><SevenPassRoutes playerCount={view.players.length} currentAge={view.age} identities={identities}/></header><div>{view.players.map(player => <article key={player.seat}><header><strong>{player.wonder_name} · {player.wonder_side.toUpperCase()}</strong><b title={zh ? `${player.score} 胜利点` : `${player.score} victory points`}>{player.score} 🏆</b></header><SevenResourceProduction units={player.resource_units}/><SevenScienceStats player={player}/><SevenCivilianScores player={player}/><SevenGuildScores player={player}/><SevenMilitaryTokens player={player}/><SevenCityCardGroups cards={player.city}/></article>)}</div></section>
  </div>;
}

function AzulTile({color, count}: {color: AzulColor; count?: number}) {
  const lang = useLang();
  return <i className={`azul-tile azul-${color}`} title={AZUL_META[color][lang]}>{count && count > 1 ? <b>{count}</b> : null}</i>;
}

function AzulPlayerPanel({player: p, identity, active, holdsStartMarker = false}: {player: AzulPlayerView; identity?: Snapshot["players"][number]; active: boolean; holdsStartMarker?: boolean}) {
  const lang = useLang(); const t = makeT(lang); const zh = lang === "zh";
  return <section className={`player-panel azul-player-panel ${active ? "active-player" : ""}`}>
    <header><div><span className="seat-label">{t("seat_label")} {p.seat + 1}</span><h3>{identity?.name || `${t("player_label")} ${p.seat + 1}`}</h3></div><div className="azul-score"><strong>{p.score}</strong><span>{zh ? "分" : "pts"}</span></div></header>
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}{identity?.reasoning_effort && <b>{zh ? `思考：${identity.reasoning_effort}` : `reasoning: ${identity.reasoning_effort}`}</b>}</div>
    <div className="azul-player-board">{p.pattern_lines.map((line, row) => <div className="azul-player-board-row" key={line.line}>
      <span className="azul-line-number">{line.line}</span>
      <div className="azul-pattern-line" aria-label={`${zh ? "图案线" : "Pattern line"} ${line.line}`}>{Array.from({length: line.capacity}, (_, index) => line.color && index >= line.capacity - line.count ? <AzulTile key={index} color={line.color}/> : <i key={index} className="azul-tile empty"/>)}</div>
      <i className="azul-row-divider" aria-hidden="true"/>
      <div className="azul-wall-row" aria-label={`${zh ? "墙面行" : "Wall row"} ${line.line}`}>{p.wall[row].map((cell, column) => <i key={`${row}-${column}`} className={`azul-wall-cell azul-${cell.color} ${cell.occupied ? "occupied" : ""}`}><span/></i>)}</div>
    </div>)}</div>
    <div className="azul-floor">
      <div className="azul-floor-heading"><span>{zh ? "地板线" : "Floor line"}</span><b>{zh ? `完成行 ${p.completed_rows}` : `${p.completed_rows} rows`}</b></div>
      <div className="azul-floor-track">{AZUL_FLOOR_PENALTIES.map((penalty, index) => {
        const item = p.floor[index];
        return <span className={`azul-floor-slot ${item ? "occupied" : ""}`} key={index} title={`${zh ? "罚分" : "Penalty"} ${penalty}`}>
          <small>{penalty}</small>
          {item === "start-player-marker" ? <i className="azul-marker">1</i> : item ? <AzulTile color={item as AzulColor}/> : <i className="azul-floor-empty"/>}
        </span>;
      })}</div>
      {holdsStartMarker && <div className="azul-marker-overflow"><i className="azul-marker">1</i><span>{zh ? "地板已满；仍持有起始玩家标记，不追加罚分" : "Floor full; holds start marker with no extra penalty"}</span></div>}
    </div>
  </section>;
}

function AzulOffer({counts, expanded = false}: {counts: AzulCounts; expanded?: boolean}) {
  const tiles = expanded
    ? AZUL_COLORS.flatMap(color => Array.from({length: counts[color]}, (_, index) => ({color, key: `${color}-${index}`})))
    : AZUL_COLORS.filter(color => counts[color] > 0).map(color => ({color, key: color}));
  return <div className={`azul-offer ${expanded ? "azul-offer-expanded" : ""}`}>{tiles.map(tile =>
    <AzulTile key={tile.key} color={tile.color} count={expanded ? undefined : counts[tile.color]}/>
  )}</div>;
}

function AzulBoard({view}: {view?: AzulView}) {
  const lang = useLang(); const zh = lang === "zh";
  if (!view) return null;
  return <div className="azul-board">
    <section className="azul-status"><div><span>AZUL · COLORED WALL</span><h2>{zh ? `第 ${view.round} 轮 · 工厂展示阶段` : `Round ${view.round} · Factory offer`}</h2></div><p>{zh ? "选择一个来源中的一种颜色；工厂余砖自动移入中央区。" : "Choose one color from one source; factory remainders move to the center."}</p><code>{view.rules_version}</code></section>
    <section className="azul-factories"><header><div><span>FACTORY DISPLAYS</span><h3>{zh ? "工厂展示区" : "Factories"}</h3></div><b>{zh ? `袋中 ${view.bag_count} · 盒盖 ${view.lid_count}` : `Bag ${view.bag_count} · Lid ${view.lid_count}`}</b></header><div>{view.factories.map((factory, index) => <article key={factory.id}><span>0{index + 1}</span><AzulOffer counts={factory.tiles} expanded/></article>)}</div></section>
    <section className="azul-center"><header><span>CENTER</span><h3>{zh ? "中央区" : "Center"}</h3></header>{view.center_has_start_marker && <i className="azul-marker">1</i>}<AzulOffer counts={view.center}/>{view.start_marker_holder_seat !== null && <small>{zh ? `起始标记：座位 ${view.start_marker_holder_seat + 1}` : `Start marker: seat ${view.start_marker_holder_seat + 1}`}</small>}</section>
    <section className="azul-legend">{AZUL_COLORS.map(color => <span key={color}><AzulTile color={color}/>{AZUL_META[color][lang]}</span>)}<small>{zh ? "原创 CSS 花砖，不包含出版商美术。" : "Original CSS tiles; no publisher artwork."}</small></section>
  </div>;
}

function tokenText(tokens: Record<string, number>, lang: Lang) {
  return GEM_ORDER.filter(color => (tokens[color] ?? 0) > 0)
    .map(color => `${GEM_META[color]?.label[lang] || color} × ${tokens[color]}`).join(lang === "zh" ? "、" : ", ");
}

function describeAction(item: Timeline, names: Record<number, string>, lang: Lang) {
  const event = item.event; const zh = lang === "zh";
  if (event.type === "agent_error") return zh ? `${event.player} 调用失败：${event.error}` : `${event.player} call failed: ${event.error}`;
  if (event.type === "match_failed") return zh ? `对局中止：${event.error}` : `Match aborted: ${event.error}`;
  if (event.type === "match_finished") return zh ? `对局结束，共 ${event.turns} 回合` : `Match finished, ${event.turns} turns`;
  if (event.type === "pause_requested") return zh ? "暂停已请求，将在当前模型完成本手后生效" : "Pause requested; applies after the current model finishes its move";
  if (event.type === "match_paused") return zh ? "对局已暂停在回合边界" : "Match paused at a turn boundary";
  if (event.type === "match_resumed") return zh ? "对局继续" : "Match resumed";
  if (event.type === "harness_tool_call") return zh ? `${event.player} 调用工具 ${event.tool}` : `${event.player} called tool ${event.tool}`;
  if (event.type === "harness_tool_result") return zh ? `${event.player} 收到 ${event.tool} 结果` : `${event.player} got ${event.tool} result`;
  if (event.type === "harness_finished") return zh ? `${event.player} 通过 ${event.harness} 提交 ${event.action_id}` : `${event.player} submitted ${event.action_id} via ${event.harness}`;
  if (event.type === "harness_error") return zh ? `${event.player} Harness 失败：${event.error}` : `${event.player} harness failed: ${event.error}`;
  if (event.type === "break_triggered") return zh ? "休息阶段已触发：所有玩家依次处理休息结算" : "Break triggered: all players resolve the Break sequence";
  if (event.type === "break_finished") return zh ? "休息阶段结束，下一位玩家继续行动" : "Break finished; play continues with the next player";
  if (event.type === "break_hand_limit_checked") return zh ? `座位 ${Number(event.seat) + 1} 检查休息阶段手牌上限` : `Seat ${Number(event.seat) + 1} checks the Break hand limit`;
  if (!["decision", "turn"].includes(event.type)) return event.type;
  const seat = event.seat ?? 0;
  const who = event.player || names[seat] || `${zh ? "座位" : "Seat"} ${seat + 1}`;
  const action = event.action ?? {};
  if (action.type === "take_tokens") {
    const take = tokenText((action.take ?? {}) as Record<string, number>, lang);
    const returned = tokenText((action.return ?? {}) as Record<string, number>, lang);
    return zh ? `${who} 拿取 ${take}${returned ? `，归还 ${returned}` : ""}` : `${who} takes ${take}${returned ? `, returns ${returned}` : ""}`;
  }
  if (action.type === "buy_visible" || action.type === "buy_reserved") return zh ? `${who} 购买 ${action.card_id}` : `${who} buys ${action.card_id}`;
  if (action.type === "reserve_visible") return zh ? `${who} 预留公开牌 ${action.card_id}` : `${who} reserves visible card ${action.card_id}`;
  if (action.type === "reserve_deck") return zh ? `${who} 从 ${action.tier} 阶牌库暗中预留一张牌` : `${who} reserves a card from tier ${action.tier} deck`;
  if (action.type === "choose_noble") return zh ? `${who} 获得贵族 ${action.noble_id}` : `${who} gains noble ${action.noble_id}`;
  if (action.type === "draft_tiles") return `${who}${zh ? "：" : ": "}${humanActionText(action, lang)}`;
  if (action.type === "pass") return zh ? `${who} 无合法行动，跳过回合` : `${who} has no legal move, passing`;
  if (["play_merchant", "acquire_merchant", "claim_point", "rest"].includes(String(action.type))) {
    return `${who}${zh ? "：" : ": "}${humanActionText(action, lang)}`;
  }
  if (["choose_initial_hand", "select_action", "take_x_token", "draw_cards", "snap_card",
    "discard_card", "break_discard", "place_building", "play_animal", "association_task",
    "play_sponsor", "advance_break", "finish_action"].includes(String(action.type))) {
    return `${who}${zh ? "：" : ": "}${humanActionText(action, lang)}`;
  }
  return `${who}${zh ? "：" : ": "}${action.type}`;
}

function humanActionText(action: Record<string, unknown>, lang: Lang, brassView?: BrassView) {
  const zh = lang === "zh"; const L = BRASS_INDUSTRY_LABELS[lang]; const BL = BRASS_ACTION_LABELS[lang];
  const sep = zh ? "、" : ", ";
  if (action.type === "draft_tiles") {
    const color = AZUL_META[String(action.color) as AzulColor]?.[lang] || String(action.color);
    const source = action.source === "center" ? (zh ? "中央区" : "center") : (zh ? `工厂 ${String(action.source).replace("factory-", "")}` : `factory ${String(action.source).replace("factory-", "")}`);
    const destination = action.destination === "floor" ? (zh ? "地板线" : "floor") : (zh ? `图案线 ${String(action.destination).replace("pattern-line-", "")}` : `pattern line ${String(action.destination).replace("pattern-line-", "")}`);
    return zh ? `从${source}选取${color}，放到${destination}` : `Take ${color} from ${source} to ${destination}`;
  }
  if (action.type === "choose_initial_hand") {
    if (Array.isArray(action.card_ids)) return zh ? `保留 ${action.card_ids.join("、")}` : `Keep ${action.card_ids.join(", ")}`;
    return zh ? `保留 ${Number(action.kept_count ?? 0)} 张起始手牌` : `Keep ${Number(action.kept_count ?? 0)} starting cards`;
  }
  if (action.type === "play_merchant") {
    const details = action.repetitions !== undefined ? (zh ? `，交易 ${action.repetitions} 次` : `, trade × ${action.repetitions}`)
      : Array.isArray(action.upgrades) ? (zh ? `，升级 ${(action.upgrades as string[]).map(value => SPICE_META[value as SpiceName]?.label[lang] || value).join(" → ") || "0 级"}` : `, upgrade ${(action.upgrades as string[]).map(value => SPICE_META[value as SpiceName]?.label[lang] || value).join(" → ")}`) : "";
    const discarded = spiceText((action.discard ?? {}) as Record<string, unknown>, lang);
    return zh ? `打出 ${action.card_id}${details}${discarded ? `；丢弃 ${discarded}` : ""}` : `Play ${action.card_id}${details}${discarded ? `; discard ${discarded}` : ""}`;
  }
  if (action.type === "acquire_merchant") {
    const payment = Array.isArray(action.payment) ? action.payment.map(value => SPICE_META[value as SpiceName]?.label[lang] || value).join(sep) : "";
    const discarded = spiceText((action.discard ?? {}) as Record<string, unknown>, lang);
    return zh ? `获取市场第 ${Number(action.position) + 1} 张商人牌${payment ? `；放置 ${payment}` : "；免费"}${discarded ? `；丢弃 ${discarded}` : ""}`
      : `Acquire merchant card #${Number(action.position) + 1}${payment ? `; place ${payment}` : "; free"}${discarded ? `; discard ${discarded}` : ""}`;
  }
  if (action.type === "claim_point") return zh ? `完成第 ${Number(action.position) + 1} 张订单（${action.point_id}）` : `Complete order #${Number(action.position) + 1} (${action.point_id})`;
  if (action.type === "rest") return zh ? "休息并收回所有已打出的商人牌" : "Rest and recover all played merchant cards";
  if (action.type === "select_action" && action.action) return zh ? `选择 ${BL[String(action.action)] || String(action.action).toUpperCase()}行动` : `Choose ${BL[String(action.action)] || String(action.action)} action`;
  if (action.type === "select_action") return zh ? `使用 ${ARK_ACTION_LABELS[lang][String(action.action_card)] || action.action_card}，强度 ${action.strength}${action.x_tokens ? `（X +${action.x_tokens}）` : ""}` : `Use ${ARK_ACTION_LABELS[lang][String(action.action_card)] || action.action_card}, strength ${action.strength}${action.x_tokens ? ` (X +${action.x_tokens})` : ""}`;
  if (action.type === "take_x_token") return zh ? `将 ${ARK_ACTION_LABELS[lang][String(action.action_card)] || action.action_card} 移到 1 并获得 X token` : `Move ${ARK_ACTION_LABELS[lang][String(action.action_card)] || action.action_card} to 1, gain X token`;
  if (action.type === "cancel_action") return zh ? `取消 ${ARK_ACTION_LABELS[lang][String(action.action_card)] || action.action_card}，重新选择行动牌` : `Cancel ${ARK_ACTION_LABELS[lang][String(action.action_card)] || action.action_card} and reselect`;
  if (action.type === "draw_cards") return zh ? `抽 ${action.draw_count} 张牌${action.discard_count ? `，再弃 ${action.discard_count} 张` : ""}` : `Draw ${action.draw_count} cards${action.discard_count ? `, discard ${action.discard_count}` : ""}`;
  if (action.type === "snap_card") return zh ? `拿取展示区 ${action.card_id}` : `Take display card ${action.card_id}`;
  if (action.type === "discard_card" || action.type === "break_discard") {
    if (action.type === "discard_card" && brassView) {
      const card = brassView.players[brassView.active_seat]?.hand.find(candidate => candidate.id === action.card_id);
      return zh ? `弃置 ${card ? brassCardLabel(card, lang) : action.card_id}` : `Discard ${card ? brassCardLabel(card, lang) : action.card_id}`;
    }
    const cards = Array.isArray(action.card_ids) ? action.card_ids.join(sep) : "";
    return zh ? `弃牌 ${action.card_id || cards || Number(action.discarded_count ?? 0) + " 张"}` : `Discard ${action.card_id || cards || Number(action.discarded_count ?? 0) + " cards"}`;
  }
  if (action.type === "place_building") return zh ? `建造 ${action.building_type}（${action.size} 格，₡${action.cost}）` : `Build ${action.building_type} (${action.size} cells, ₡${action.cost})`;
  if (action.type === "play_animal") return zh ? `打出动物 ${action.card_id}，使用 ${action.enclosure_id}` : `Place animal ${action.card_id} in ${action.enclosure_id}`;
  if (action.type === "association_task") return zh ? `协会任务：${action.task}` : `Association task: ${action.task}`;
  if (action.type === "make_donation") return zh ? `捐款 ₡${action.cost}，获得 1 保育点` : `Donate ₡${action.cost}, gain 1 conservation`;
  if (action.type === "upgrade_action_card") return zh ? `升级 ${ARK_ACTION_LABELS[lang][String(action.action_card)] || action.action_card} 行动牌` : `Upgrade ${ARK_ACTION_LABELS[lang][String(action.action_card)] || action.action_card} card`;
  if (action.type === "choose_conservation_bonus") return action.choice === "money" ? (zh ? `选择保育奖励：₡${action.amount}` : `Conservation bonus: ₡${action.amount}`) : (zh ? `选择奖励标记 ${action.tile_id}` : `Choose bonus tile ${action.tile_id}`);
  if (action.type === "take_map_card") return action.source === "deck" ? (zh ? "地图奖励：拿取牌库顶牌" : "Map reward: take top deck card") : (zh ? `地图奖励：拿取展示区 ${action.display_slot} 的 ${action.card_id}` : `Map reward: take ${action.card_id} from display slot ${action.display_slot}`);
  if (action.type === "clever_action_card") return zh ? `机敏：将 ${ARK_ACTION_LABELS[lang][String(action.action_card)] || action.action_card} 移到强度 1` : `Clever: move ${ARK_ACTION_LABELS[lang][String(action.action_card)] || action.action_card} to strength 1`;
  if (action.type === "keep_final_card") return zh ? `保留终局牌 ${action.card_id}` : `Keep final card ${action.card_id}`;
  if (action.type === "play_sponsor") return zh ? `打出赞助商 ${action.card_id}` : `Play sponsor ${action.card_id}`;
  if (action.type === "advance_break") return zh ? `推进 Break ${action.steps} 格，获得 ₡${action.money}` : `Advance Break ${action.steps}, gain ₡${action.money}`;
  if (action.type === "finish_action") return zh ? "结束当前行动" : "End current action";
  if (action.type === "discard_wild") return zh ? `弃置万能${action.wild_type === "location" ? "地点" : "产业"}牌` : `Discard wild ${action.wild_type === "location" ? "location" : "industry"} card`;
  if (action.type === "scout_discard_extra") return zh ? `再弃 ${Array.isArray(action.card_ids) ? action.card_ids.join("、") : "2 张牌"}` : `Discard ${Array.isArray(action.card_ids) ? action.card_ids.join(", ") : "2 more cards"}`;
  if (action.type === "develop_tiles") return zh ? `研发 ${Array.isArray(action.industries) ? action.industries.map(value => L[String(value)] || value).join(" + ") : "产业"}` : `Develop ${Array.isArray(action.industries) ? action.industries.map(value => L[String(value)] || value).join(" + ") : "industry"}`;
  if (action.type === "build_industry") return zh ? `在 ${brassLocationLabel(String(action.location_id), lang)} 建造 ${L[String(action.industry)] || action.industry}（£${action.cost}）` : `Build ${L[String(action.industry)] || action.industry} in ${brassLocationLabel(String(action.location_id), lang)} (£${action.cost})`;
  if (action.type === "build_link" || action.type === "select_network_link") {
    const connection = brassView?.board.connection_spaces.find(space => space.id === action.connection_id);
    const route = connection?.endpoints.map(l => brassLocationLabel(l, lang)).join(" ↔ ") || action.connection_id;
    return zh ? `铺设${action.link_kind === "canal" ? "运河" : "铁路"}：${route}` : `Lay ${action.link_kind === "canal" ? "canal" : "rail"}: ${route}`;
  }
  if (action.type === "select_network_count") return zh ? `铺设 ${action.count} 条铁路（基础费用 £${action.cost}）` : `Lay ${action.count} rail links (base cost £${action.cost})`;
  if (action.type === "take_resource") {
    const resource = action.resource === "coal" ? (zh ? "煤炭" : "coal") : action.resource === "iron" ? (zh ? "铁" : "iron") : (zh ? "啤酒" : "beer");
    const industry = brassView?.board.industries.find(candidate => candidate.id === action.source_id);
    const source = action.source === "market" ? (zh ? `${resource}市场` : `${resource} market`) : industry ? (zh ? `${brassLocationLabel(industry.location, lang)}的${L[industry.industry]}` : `${L[industry.industry]} in ${brassLocationLabel(industry.location, lang)}`) : action.source === "merchant" ? (zh ? "商人啤酒" : "merchant beer") : action.source_id;
    return zh ? `从${source}取得${resource}${action.cost ? `（£${action.cost}）` : ""}` : `Take ${resource} from ${source}${action.cost ? ` (£${action.cost})` : ""}`;
  }
  if (action.type === "sell_industry") {
    const industry = brassView?.board.industries.find(candidate => candidate.id === action.industry_id);
    return zh ? `出售${industry ? `${brassLocationLabel(industry.location, lang)}的${L[industry.industry]}` : action.industry_id}给${brassLocationLabel(String(action.merchant_location_id), lang)}`
      : `Sell ${industry ? `${L[industry.industry]} in ${brassLocationLabel(industry.location, lang)}` : action.industry_id} to ${brassLocationLabel(String(action.merchant_location_id), lang)}`;
  }
  if (action.type === "finish_sell") return zh ? "结束出售行动" : "End sell action";
  if (action.type === "merchant_bonus_develop") return zh ? `商人奖励研发 ${action.industry}` : `Merchant develop bonus ${action.industry}`;
  if (action.type === "liquidate_industry") return zh ? `变卖 ${action.industry_id}，获得 £${action.value}` : `Liquidate ${action.industry_id}, gain £${action.value}`;
  if (action.type === "build_card") {
    return zh ? `建造 ${action.card_id}（${sevenPaymentSummary(action, lang)}）` : `Build ${action.card_id} (${sevenPaymentSummary(action, lang)})`;
  }
  if (action.type === "build_wonder") return zh ? `用 ${action.card_id} 建造奇迹第 ${action.stage} 阶段（${sevenPaymentSummary(action, lang)}）` : `Use ${action.card_id} for Wonder stage ${action.stage} (${sevenPaymentSummary(action, lang)})`;
  if (action.type === "sell_card") return zh ? `出售 ${action.card_id}，获得 💰3` : `Sell ${action.card_id} for 💰3`;
  if (action.type === "build_discard") return zh ? `从弃牌堆免费建造 ${action.card_id}` : `Build ${action.card_id} from discard for free`;
  if (action.type === "skip_discard") return zh ? "跳过弃牌堆建造" : "Skip discard construction";
  if (action.type === "take_tokens") {
    const taken = tokenText((action.take ?? {}) as Record<string, number>, lang);
    const returned = tokenText((action.return ?? {}) as Record<string, number>, lang);
    return zh ? `拿取 ${taken}${returned ? `；归还 ${returned}` : ""}` : `Take ${taken}${returned ? `; return ${returned}` : ""}`;
  }
  if (action.type === "buy_visible" || action.type === "buy_reserved") {
    const payment = tokenText((action.payment ?? {}) as Record<string, number>, lang);
    return zh ? `购买 ${action.card_id}${payment ? `；支付 ${payment}` : "；免费"}` : `Buy ${action.card_id}${payment ? `; pay ${payment}` : "; free"}`;
  }
  if (action.type === "reserve_visible") return zh ? `预留公开牌 ${action.card_id}${action.return && tokenText(action.return as Record<string, number>, lang) ? `；归还 ${tokenText(action.return as Record<string, number>, lang)}` : ""}` : `Reserve ${action.card_id}${action.return && tokenText(action.return as Record<string, number>, lang) ? `; return ${tokenText(action.return as Record<string, number>, lang)}` : ""}`;
  if (action.type === "reserve_deck") return zh ? `从 ${action.tier} 阶牌库暗中预留一张牌` : `Reserve a card from tier ${action.tier} deck`;
  if (action.type === "choose_noble") return zh ? `选择贵族 ${action.noble_id}` : `Choose noble ${action.noble_id}`;
  return action.type === "pass" ? (zh ? "跳过本回合" : "Pass turn") : String(action.type);
}

const ACTION_GROUPS: Record<Lang, Record<string, string>> = {
  zh: {
    buy_visible: "购买公开牌", buy_reserved: "购买预留牌", take_tokens: "拿取宝石",
    reserve_visible: "预留公开牌", reserve_deck: "预留牌库顶牌", choose_noble: "选择贵族", pass: "其他",
    choose_initial_hand: "选择起始手牌", select_action: "选择行动牌", take_x_token: "替代 X-token 行动", cancel_action: "返回重选行动",
    draw_cards: "抽牌", snap_card: "拿取展示牌", discard_card: "弃牌", break_discard: "Break 弃牌",
    place_building: "放置建筑", play_animal: "打出动物", association_task: "协会任务",
    play_sponsor: "打出赞助商", advance_break: "推进 Break", finish_action: "结束行动",
    make_donation: "捐款", upgrade_action_card: "升级行动牌", keep_final_card: "选择终局牌",
    choose_conservation_bonus: "选择保育奖励", take_map_card: "拿取地图奖励牌", clever_action_card: "机敏奖励", finish_association_tasks: "结束协会任务",
    discard_wild: "弃置万能牌", scout_discard_extra: "侦察弃牌", develop_tiles: "选择研发板块",
    build_industry: "选择产业与城市", build_link: "铺设运河", select_network_count: "铁路数量",
    select_network_link: "选择铁路", take_resource: "选择资源来源", sell_industry: "出售产业",
    finish_sell: "结束出售", merchant_bonus_develop: "商人研发奖励", liquidate_industry: "变卖产业",
    play_merchant: "打出商人牌", acquire_merchant: "获取商人牌", claim_point: "完成订单", rest: "休息",
    draft_tiles: "选取并放置花砖",
    build_card: "建造建筑", build_wonder: "建造奇迹", sell_card: "出售卡牌",
    build_discard: "墓园建造", skip_discard: "跳过墓园建造",
  },
  en: {
    buy_visible: "Buy visible card", buy_reserved: "Buy reserved card", take_tokens: "Take gems",
    reserve_visible: "Reserve visible card", reserve_deck: "Reserve deck card", choose_noble: "Choose noble", pass: "Other",
    choose_initial_hand: "Choose starting hand", select_action: "Select action card", take_x_token: "X-token action", cancel_action: "Cancel selected action",
    draw_cards: "Draw cards", snap_card: "Take display card", discard_card: "Discard card", break_discard: "Break discard",
    place_building: "Place building", play_animal: "Play animal", association_task: "Association task",
    play_sponsor: "Play sponsor", advance_break: "Advance Break", finish_action: "End action",
    make_donation: "Donate", upgrade_action_card: "Upgrade action card", keep_final_card: "Choose final card",
    choose_conservation_bonus: "Conservation bonus", take_map_card: "Map card reward", clever_action_card: "Clever reward", finish_association_tasks: "End association tasks",
    discard_wild: "Discard wild card", scout_discard_extra: "Scout discard", develop_tiles: "Select develop tiles",
    build_industry: "Choose industry & city", build_link: "Build canal", select_network_count: "Rail count",
    select_network_link: "Choose rail link", take_resource: "Choose resource source", sell_industry: "Sell industry",
    finish_sell: "End sell", merchant_bonus_develop: "Merchant develop bonus", liquidate_industry: "Liquidate industry",
    play_merchant: "Play merchant card", acquire_merchant: "Acquire merchant card", claim_point: "Complete order", rest: "Rest",
    draft_tiles: "Draft and place tiles",
    build_card: "Construct building", build_wonder: "Construct Wonder", sell_card: "Sell card",
    build_discard: "Build from discard", skip_discard: "Skip discard build",
  },
};

function groupActions(actions: LegalAction[]) {
  const groups = actions.reduce<Record<string, LegalAction[]>>((result, item) => {
    const kind = String(item.action.type);
    (result[kind] ||= []).push(item);
    return result;
  }, {});
  const priority: Record<string, number> = {buy_visible: 0, buy_reserved: 1, reserve_visible: 2, take_tokens: 3, reserve_deck: 4};
  return Object.fromEntries(Object.entries(groups).sort(([a], [b]) => (priority[a] ?? 10) - (priority[b] ?? 10)));
}

const CARD_ACTION_TYPES = new Set(["buy_visible", "buy_reserved", "reserve_visible"]);
const CENTURY_ACTION_TYPES = new Set(["play_merchant", "acquire_merchant", "claim_point", "rest"]);
const ARK_TABLE_ACTION_TYPES = new Set([
  "choose_initial_hand", "select_action", "take_x_token", "cancel_action", "draw_cards", "snap_card", "discard_card",
  "place_building", "play_animal", "finish_action", "association_task", "make_donation",
  "perform_association_task", "make_association_donation", "finish_association_action",
  "upgrade_association_reward_card",
  "place_unique_sponsor_building",
  "finish_association_tasks", "advance_break", "play_sponsor", "break_discard",
  "resolve_semantic_choice",
  "choose_conservation_bonus", "upgrade_action_card", "keep_final_card", "take_map_card",
  "clever_action_card",
]);

function findActionCard(action: Record<string, unknown>, view?: View) {
  const cardId = String(action.card_id ?? "");
  if (!cardId || !view) return undefined;
  const visible = Object.values(view.market).flat().find(card => card.id === cardId);
  if (visible) return visible;
  return view.players[view.active_seat]?.reserved.find(
    (card): card is Card => !("hidden" in card) && card.id === cardId,
  );
}

function HumanActionChoice({item, view, brassView, disabled, submitting, onChoose}: {
  item: LegalAction; view?: View; brassView?: BrassView; disabled: boolean; submitting: boolean; onChoose: () => void;
}) {
  const lang = useLang(); const zh = lang === "zh";
  const kind = String(item.action.type);
  if (kind === "take_tokens") {
    const take = (item.action.take ?? {}) as Record<string, number>;
    const returned = (item.action.return ?? {}) as Record<string, number>;
    const returnColors = GEM_ORDER.filter(color => (returned[color] ?? 0) > 0);
    return <button className="token-action-choice" disabled={disabled} onClick={onChoose} aria-label={humanActionText(item.action, lang)} title={`${humanActionText(item.action, lang)} · ${item.id}`}>
      <span className="token-choice-gems">{GEM_ORDER.filter(color => (take[color] ?? 0) > 0).map(color => <Gem key={color} color={color} value={take[color]}/>)}</span>
      {returnColors.length > 0 && <span className="token-choice-return"><b>{zh ? "归还" : "Return"}</b>{returnColors.map(color => <Gem key={color} color={color} value={returned[color]} compact/>)}</span>}
      {submitting && <i>{zh ? "提交中…" : "Submitting…"}</i>}
    </button>;
  }
  if (CENTURY_ACTION_TYPES.has(kind)) return <button className={`century-action-choice century-action-${kind}`} disabled={disabled} onClick={onChoose} title={item.id}>
    <span>{ACTION_GROUPS[lang][kind]}</span><strong>{humanActionText(item.action, lang)}</strong>{submitting && <i>{zh ? "提交中…" : "Submitting…"}</i>}
  </button>;
  const card = CARD_ACTION_TYPES.has(kind) ? findActionCard(item.action, view) : undefined;
  if (!card) return <button disabled={disabled} onClick={onChoose}><strong>{humanActionText(item.action, lang, brassView)}</strong><small>{item.id}{submitting ? (zh ? " · 提交中…" : " · submitting…") : ""}</small></button>;
  const payment = tokenText((item.action.payment ?? item.action.return ?? {}) as Record<string, number>, lang);
  return <button className={`card-action-choice card-${card.bonus}`} disabled={disabled} onClick={onChoose} aria-label={humanActionText(item.action, lang)}>
    <span className="card-action-label">{kind === "reserve_visible" ? (zh ? "预留" : "Reserve") : (zh ? "购买" : "Buy")}</span>
    <span className="card-action-top"><strong>{card.points || "·"}</strong><b>{GEM_META[card.bonus]?.mark}</b></span>
    <Cost cost={card.cost}/>
    {payment && <small>{kind === "reserve_visible" ? (zh ? "归还" : "Return") : (zh ? "支付" : "Pay")}{zh ? "：" : ": "}{payment}</small>}
    {submitting && <i>{zh ? "提交中…" : "Submitting…"}</i>}
  </button>;
}

function AzulActionPicker({actions, disabled, submitting, onChoose}: {actions: LegalAction[]; disabled: boolean; submitting: string; onChoose: (item: LegalAction) => void}) {
  const lang = useLang(); const zh = lang === "zh";
  const sources = useMemo(() => [...new Set(actions.map(item => String(item.action.source)))], [actions]);
  const [selectedSource, setSelectedSource] = useState("");
  const source = sources.includes(selectedSource) ? selectedSource : sources[0] || "";
  const colors = AZUL_COLORS.filter(color => actions.some(item => item.action.source === source && item.action.color === color));
  const [selectedColor, setSelectedColor] = useState<AzulColor | "">("");
  const color = colors.includes(selectedColor as AzulColor) ? selectedColor : colors[0] || "";
  const choices = actions.filter(item => item.action.source === source && item.action.color === color);
  return <div className="azul-action-picker">
    <div><span>1 · {zh ? "来源" : "Source"}</span>{sources.map(value => <button key={value} className={source === value ? "selected" : ""} onClick={() => {setSelectedSource(value); setSelectedColor("");}} disabled={disabled}>{value === "center" ? (zh ? "中央区" : "Center") : `${zh ? "工厂" : "Factory"} ${value.replace("factory-", "")}`}</button>)}</div>
    <div><span>2 · {zh ? "颜色" : "Color"}</span>{colors.map(value => <button key={value} className={color === value ? "selected" : ""} onClick={() => setSelectedColor(value)} disabled={disabled}><AzulTile color={value}/>{AZUL_META[value][lang]}</button>)}</div>
    <div><span>3 · {zh ? "放置位置" : "Destination"}</span>{choices.map(item => <button key={item.id} onClick={() => onChoose(item)} disabled={disabled}>{item.action.destination === "floor" ? (zh ? "地板线" : "Floor") : `${zh ? "图案线" : "Pattern line"} ${String(item.action.destination).replace("pattern-line-", "")}`}{submitting === item.id && <i>{zh ? "提交中…" : "Submitting…"}</i>}</button>)}</div>
  </div>;
}

function ArkPlayerPanel({player, identity, active}: {player: ArkPlayerView; identity?: Snapshot["players"][number]; active: boolean}) {
  const lang = useLang();
  return <ArkNovaPlayerSummary player={player} identity={identity} active={active} lang={lang}/>;
}

const BRASS_INDUSTRY_LABELS: Record<Lang, Record<string, string>> = {
  zh: { cotton_mill: "棉纺厂", coal_mine: "煤矿", iron_works: "炼铁厂", manufacturer: "制造厂", pottery: "陶瓷厂", brewery: "啤酒厂" },
  en: { cotton_mill: "Cotton mill", coal_mine: "Coal mine", iron_works: "Iron works", manufacturer: "Manufacturer", pottery: "Pottery", brewery: "Brewery" },
};
const BRASS_ACTION_LABELS: Record<Lang, Record<string, string>> = {
  zh: { build: "建造", network: "铺设网络", develop: "研发", sell: "出售", loan: "贷款", scout: "侦察", pass: "跳过" },
  en: { build: "Build", network: "Network", develop: "Develop", sell: "Sell", loan: "Loan", scout: "Scout", pass: "Pass" },
};
const BRASS_LOCATION_ZH: Record<string, string> = {
  belper: "贝尔珀", birmingham: "伯明翰", burton_on_trent: "特伦特河畔伯顿", cannock: "坎诺克",
  coalbrookdale: "科尔布鲁克代尔", coventry: "考文垂", derby: "德比", dudley: "达德利",
  kidderminster: "基德明斯特", leek: "利克", nuneaton: "纽尼顿", redditch: "雷迪奇",
  stafford: "斯塔福德", stoke_on_trent: "特伦特河畔斯托克", stone: "斯通", tamworth: "塔姆沃思",
  uttoxeter: "阿托克斯特", walsall: "沃尔索尔", wolverhampton: "伍尔弗汉普顿", worcester: "伍斯特",
  warrington: "沃灵顿", nottingham: "诺丁汉", shrewsbury: "什鲁斯伯里", gloucester: "格洛斯特", oxford: "牛津",
  farm_brewery_cannock: "坎诺克农场啤酒厂", farm_brewery_kidderminster_worcester: "基德明斯特／伍斯特农场啤酒厂",
};

function brassLocationLabel(location: string, lang: Lang) {
  if (lang === "en") return location.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
  return BRASS_LOCATION_ZH[location] || location.replaceAll("_", " ");
}

function brassCardLabel(card: BrassPlayerView["hand"][number], lang: Lang) {
  const zh = lang === "zh";
  if (card.hidden) return zh ? "隐藏牌" : "Hidden card";
  if (card.card_type === "location" && card.location) return zh ? `${brassLocationLabel(card.location, lang)}地点牌` : `${brassLocationLabel(card.location, lang)} card`;
  const industries = card.industries || (card.industry ? [card.industry] : []);
  return zh
    ? `${industries.map(industry => BRASS_INDUSTRY_LABELS.zh[industry] || industry).join("／") || "产业"}牌`
    : `${industries.map(industry => BRASS_INDUSTRY_LABELS.en[industry] || industry).join("/") || "Industry"} card`;
}

function brassIncomeLevel(position: number) {
  if (position <= 10) return position - 10;
  if (position <= 30) return Math.floor((position - 9) / 2);
  if (position <= 60) return 11 + Math.floor((position - 31) / 3);
  if (position <= 96) return 21 + Math.floor((position - 61) / 4);
  return 30;
}

function BrassPlayerPanel({player: p, identity, active}: {player: BrassPlayerView; identity?: Snapshot["players"][number]; active: boolean}) {
  const lang = useLang(); const t = makeT(lang); const zh = lang === "zh";
  return <section className={`player-panel brass-player-panel ${active ? "active-player" : ""}`}>
    <header><div><span className="seat-label">{t("seat_label")} {p.seat + 1}</span><h3>{identity?.name || `${t("player_label")} ${p.seat + 1}`}</h3></div><div className="brass-vp"><strong>{p.vp}</strong><span>VP</span></div></header>
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}{identity?.reasoning_effort && <b>{lang === "zh" ? `思考：${identity.reasoning_effort}` : `reasoning: ${identity.reasoning_effort}`}</b>}</div>
    <div className="brass-economy"><span>{zh ? "现金" : "Cash"} <b>£{p.money}</b></span><span>{zh ? "收入" : "Income"} <b>{brassIncomeLevel(p.income_position)}</b></span><span>{zh ? "本轮支出" : "Spent this round"} <b>£{p.spent_this_round}</b></span></div>
    <div className="brass-hand"><span>{t("hand")} <b>{p.hand_count}</b></span><span>{zh ? "万能地点" : "Wild location"} <b>{p.wild_cards.location}</b></span><span>{zh ? "万能产业" : "Wild industry"} <b>{p.wild_cards.industry}</b></span></div>
    {p.hand.some(card => !card.hidden) && <div className="brass-hand-cards">{p.hand.map((card, index) => <span key={card.id || index} title={card.id}><b>{brassCardLabel(card, lang)}</b><small>{card.id}</small></span>)}</div>}
    <div className="brass-stack-grid">{Object.entries(p.industry_stacks).map(([industry, stack]) => <span key={industry} title={BRASS_INDUSTRY_LABELS[lang][industry]}><i className={`industry-mark industry-${industry}`}/><b>{stack.length}</b><small>{stack[0] ? `L${stack[0].level}` : "—"}</small></span>)}</div>
    <div className="brass-links">{zh ? "剩余连接片" : "Links remaining"} <b>{p.links_remaining}</b></div>
  </section>;
}

function BrassMarket({label, market, resource}: {label: string; market: {prices: number[]; occupied: boolean[]}; resource: string}) {
  return <div className={`brass-market brass-market-${resource}`}><header><span>{label}</span><b>{market.occupied.filter(Boolean).length}</b></header><div>{market.prices.map((price, index) => <i key={index} className={market.occupied[index] ? "filled" : "empty"} title={`£${price}`}><small>£{price}</small></i>)}</div></div>;
}

function BrassBoard({view, players}: {view?: BrassView; players: Snapshot["players"]}) {
  const lang = useLang(); const t = makeT(lang); const zh = lang === "zh";
  if (!view) return null;
  const industryById = new Map(view.board.industries.map(industry => [industry.id, industry]));
  const linksByConnection = new Map(view.board.links.map(link => [link.connection_id, link]));
  return <div className="brass-board">
    <section className="brass-status"><div><span>BRASS · BIRMINGHAM</span><h2>{view.era === "canal" ? t("brass_canal") : t("brass_rail")} · {zh ? `第 ${view.round} 轮` : `Round ${view.round}`}</h2></div><div><small>CURRENT DECISION</small><strong>{view.turn.decision.replaceAll("_", " ")}</strong><b>{view.turn.actions_remaining}/{view.turn.actions_total} {t("brass_actions")}</b></div><code>{view.rules_version}</code></section>
    <section className="brass-economy-board"><BrassMarket label={t("coal_market")} market={view.markets.coal} resource="coal"/><BrassMarket label={t("iron_market")} market={view.markets.iron} resource="iron"/><div className="brass-deck"><span>{t("deck_label")}</span><strong>{view.deck_count}</strong><small>{t("turn_order")} · {view.turn_order.map(seat => players[seat]?.name || seat + 1).join(" → ")}</small></div></section>
    <section className="brass-map"><header><div><span>BLACK COUNTRY / BIRMINGHAM</span><h3>{t("brass_map_h")}</h3></div><b>{view.board.industries.length} {t("industries_unit")} · {view.board.links.length} {t("links_unit")}</b></header>
      <div className="brass-city-grid">{view.board.locations.filter(location => location.kind === "industry").map(location => <article key={location.id}><h4>{brassLocationLabel(location.id, lang)}</h4><div>{location.industry_slots.map(slot => {const tile = slot.industry_id ? industryById.get(slot.industry_id) : undefined; return <span key={slot.id} className={tile ? `occupied seat-${tile.owner}` : "vacant"} title={slot.accepts.map(kind => BRASS_INDUSTRY_LABELS[lang][kind]).join(" / ")}>{tile ? <><i className={`industry-mark industry-${tile.industry}`}/><b>L{tile.level}</b><small>{tile.flipped ? t("flipped") : tile.resources ? `×${tile.resources}` : t("not_flipped")}</small></> : <small>{slot.accepts.map(kind => BRASS_INDUSTRY_LABELS[lang][kind]).join("/")}</small>}</span>;})}</div></article>)}</div>
    </section>
    <section className="brass-network"><header><span>{t("brass_conn")}</span><b>{view.era === "canal" ? t("canal") : t("rail")}</b></header><div>{view.board.connection_spaces.filter(space => space.available_eras.includes(view.era)).map(space => {const link = linksByConnection.get(space.id); return <span key={space.id} className={link ? `built seat-${link.owner}` : "open"}><b>{space.endpoints.map(l => brassLocationLabel(l, lang)).join(" ↔ ")}</b><small>{link ? players[link.owner]?.name || `${t("seat_label")} ${link.owner + 1}` : t("not_built")}</small></span>;})}</div></section>
    <section className="brass-merchants"><header><span>MERCHANTS</span><h3>{t("brass_merchants")}</h3></header><div>{view.board.merchant_locations.map(merchant => <article key={merchant.id}><b>{brassLocationLabel(merchant.id, lang)}</b>{merchant.slots.map(slot => <span key={slot.id}>{slot.buys === "any" ? t("any_goods") : slot.buys === "blank" ? t("blank") : BRASS_INDUSTRY_LABELS[lang][slot.buys]}<i>{slot.beer ? "🍺" : "—"}</i></span>)}</article>)}</div></section>
  </div>;
}

function SplendorBoard({view}: {view?: View}) {
  const lang = useLang(); const t = makeT(lang); const zh = lang === "zh";
  return <>
    <div className="bank-bar"><div><small>{t("supply")}</small><strong>{t("gem_bank")}</strong></div>{view && GEM_ORDER.map(c => <Gem key={c} color={c} value={view.bank[c]}/>)}</div>
    <section className="nobles"><header><span>{t("nobles")}</span><b>{view?.available_nobles.length || 0} {t("available")}</b></header><div>{view?.available_nobles.map(n => <article key={n.id}><strong>3</strong><Cost cost={n.required}/></article>)}</div></section>
    <section className="market">{[3,2,1].map(tier => <div className="tier" key={tier}>
      <div className="tier-label"><span>{t("tier")}</span><strong>0{tier}</strong><small>{view?.deck_counts[String(tier)]} {zh ? "张" : t("cards_unit")}</small></div>
      <div className="market-cards">{view?.market[String(tier)].map(card => <DevCard key={card.id} card={card}/>)}</div>
    </div>)}</section>
  </>;
}

function ArkNovaBoard({view, players, legalActions, submitting, onChoose}: {
  view?: ArkView; players: Snapshot["players"]; legalActions: LegalAction[]; submitting: string;
  onChoose: (item: LegalAction) => void;
}) {
  const lang = useLang();
  return <ArkNovaTable view={view} identities={players} lang={lang} legalActions={legalActions} submitting={submitting} onChoose={onChoose}/>;
}

export default function Home() {
  const [lang, setLang] = useState<Lang>("zh");
  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("abga-lang") : null;
    // Restoring a browser preference is an intentional client-only synchronization.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (saved === "zh" || saved === "en") setLang(saved);
  }, []);
  function toggleLang() {
    setLang(current => {
      const next: Lang = current === "zh" ? "en" : "zh";
      try { localStorage.setItem("abga-lang", next); } catch { /* ignore */ }
      return next;
    });
  }
  return <LangCtx.Provider value={lang}>
    <HomeInner lang={lang} toggleLang={toggleLang}/>
  </LangCtx.Provider>;
}

function HomeInner({lang, toggleLang}: {lang: Lang; toggleLang: () => void}) {
  const t = makeT(lang); const zh = lang === "zh";
  const [game, setGame] = useState<GameId>("splendor");
  const [players, setPlayers] = useState<PlayerForm[]>([
    deepseekHarnessPlayer(1, "opencode"),
    codexHarnessPlayer(2),
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
  const humanSeat = snapshot?.human_turn?.seat ?? snapshot?.players.find(player => player.backend === "human")?.seat ?? 0;
  const viewer = snapshot?.views[humanSeat];
  const splendorView = snapshot?.game === "splendor" ? viewer as View : undefined;
  const azulView = snapshot?.game === "azul" ? viewer as AzulView : undefined;
  const arkView = snapshot?.game === "ark_nova"
    ? (snapshot.spectator_view ?? viewer) as ArkView : undefined;
  const brassView = snapshot?.game === "brass_birmingham" ? viewer as BrassView : undefined;
  const centuryView = snapshot?.game === "century_spice_road" ? viewer as CenturyView : undefined;
  const sevenView = snapshot?.game === "seven_wonders" ? viewer as SevenView : undefined;
  const sevenSpectatorViews = snapshot?.game === "seven_wonders" && !snapshot.players.some(player => player.backend === "human")
    ? snapshot.views as SevenView[] : undefined;
  const isArkTableAction = (item: LegalAction) => ARK_TABLE_ACTION_TYPES.has(String(item.action.type));
  const arkMapInteraction = snapshot?.game === "ark_nova" && Boolean(snapshot.human_turn?.legal_actions.some(isArkTableAction));
  const maxPlayers = game === "seven_wonders" ? 7 : game === "century_spice_road" ? 5 : 4;
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
    const selected = kind === "human" ? [humanPlayer(1), deepseekHarnessPlayer(2, "opencode")] : [
      deepseekHarnessPlayer(1, "opencode"), codexHarnessPlayer(2),
    ];
    if (game === "seven_wonders") selected.push(player(3, "random"));
    setPlayers(selected);
  }

  function selectGame(next: GameId) {
    setGame(next);
    const maximum = next === "seven_wonders" ? 7 : next === "century_spice_road" ? 5 : 4;
    setPlayers(current => {
      const selected = current.slice(0, maximum);
      while (next === "seven_wonders" && selected.length < 3) selected.push(player(selected.length + 1, "random"));
      return selected;
    });
  }

  function selectProvider(id: string, provider: Provider) {
    const preset = PROVIDERS[provider];
    setPlayers(current => current.map(p => p.id === id ? {
      ...p, provider, backend: provider === "custom" ? p.backend : preset.backend,
      base_url: provider === "custom" ? p.base_url : preset.url,
      model: provider === "custom" ? p.model : preset.models[0],
      reasoning_effort: preset.backend === "codex" && p.reasoning_effort === "none" ? "max" : p.reasoning_effort,
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
            ...(p.backend === "codex" ? {auth_mode: p.auth_mode} : {}),
            ...(!(p.backend === "codex" && p.auth_mode === "subscription") ? {base_url: p.base_url, api_key: p.api_key} : {}),
            ...(HARNESS_BACKENDS.has(p.backend) ? {reasoning_effort: p.reasoning_effort} : {}),
          })),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || "无法启动对局");
      setSnapshot(data);
      requestAnimationFrame(() => window.scrollTo({top: 0, behavior: "smooth"}));
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
              actionLatencyMs: event.agent?.action_latency_ms,
              processLatencyMs: event.agent?.process_latency_ms ?? event.agent?.latency_ms,
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
      <button className="lang-toggle" onClick={toggleLang} aria-label="Switch language">{zh ? "EN" : "中文"}</button>
      <div className="eyebrow">{t("hero_eyebrow")} / {GAME_COPY[game].eyebrow}</div>
      <h1>{t("hero_title_a")}<br/><i>{t("hero_title_b")}</i>{t("hero_title_c")}</h1>
      <p>{GAME_COPY[game].description[lang]}</p>
      <div className="hero-marks"><span>{t("hero_mark_1")}</span><span>{t("hero_mark_2")}</span><span>{game === "ark_nova" ? t("hero_mark_ark") : t("hero_mark_3")}</span></div>
    </section>
    <section className="setup-card">
      <div className="game-picker" role="group" aria-label={t("pick_game")}>{(Object.keys(GAME_COPY) as GameId[]).map(id => <button key={id} className={game === id ? "selected" : ""} onClick={() => selectGame(id)}><span>{GAME_COPY[id].badge}</span><b>{GAME_COPY[id].name[lang]}</b><small>{GAME_COPY[id].note[lang]}</small></button>)}</div>
      <header><div><span>{t("new_table")}</span><h2>{t("create_table")}{GAME_COPY[game].name[lang]}</h2></div><div className="matchup-presets"><button onClick={() => setMatchup("human")}>{t("g_human")}</button><button onClick={() => setMatchup("harness")}>{t("g_harness")}</button><b>{players.length} {t("players_count")}</b></div></header>
      {game === "ark_nova" && <ArkNovaWorkbench lang={lang}/>}
      <div className="players-config">{players.map((p, index) => <article className="player-config" key={p.id}>
        <div className="seat-order"><b>0{index + 1}</b><div><button disabled={index === 0} aria-label={`${p.name} ${t("move_up")}`} onClick={() => movePlayer(index, -1)}>↑</button><button disabled={index === players.length - 1} aria-label={`${p.name} ${t("move_down")}`} onClick={() => movePlayer(index, 1)}>↓</button></div></div>
        <div className="field grow"><label htmlFor={`${p.id}-name`}>{t("f_name")}</label><input id={`${p.id}-name`} value={p.name} onChange={e => updatePlayer(p.id, {name: e.target.value})}/></div>
        {!(["random", "human"] as Backend[]).includes(p.backend) && <>
          <div className="field provider-field"><label htmlFor={`${p.id}-provider`}>{t("f_provider")}</label><select id={`${p.id}-provider`} value={p.provider} onChange={e => selectProvider(p.id, e.target.value as Provider)}><optgroup label={t("og_harness")}>{(["claude_code", "pi", "codex", "opencode", "dsh", "hermes", "minimal"] as Provider[]).map(id => <option key={id} value={id}>{PROVIDERS[id].label[lang]}</option>)}</optgroup><optgroup label={t("og_direct")}>{(["custom", "deepseek", "dashscope", "zhipu", "minimax"] as Provider[]).map(id => <option key={id} value={id}>{PROVIDERS[id].label[lang]}</option>)}</optgroup></select></div>
          <div className="field backend-field"><label htmlFor={`${p.id}-backend`}>{t("f_backend")}</label><select id={`${p.id}-backend`} value={p.backend} onChange={e => updatePlayer(p.id, {backend: e.target.value as Backend})}>{Object.entries(BACKENDS).filter(([id]) => id !== "random").map(([id, b]) => <option key={id} value={id}>{b.label[lang]}</option>)}</select></div>
          {p.backend === "codex" && <div className="field auth-field"><label htmlFor={`${p.id}-auth`}>{t("f_auth")}</label><select id={`${p.id}-auth`} value={p.auth_mode} onChange={e => updatePlayer(p.id, {auth_mode: e.target.value as AuthMode})}><option value="subscription">{t("auth_subscription")}</option><option value="api_key">{t("auth_api_key")}</option></select></div>}
          {!(p.backend === "codex" && p.auth_mode === "subscription") && <div className="field grow endpoint-field"><label htmlFor={`${p.id}-endpoint`}>{t("f_endpoint")}</label><input id={`${p.id}-endpoint`} value={p.base_url} placeholder={t("ph_endpoint")} onChange={e => updatePlayer(p.id, {provider: "custom", base_url: e.target.value})}/></div>}
          <div className="field model-field"><label htmlFor={`${p.id}-model`}>{t("f_model")}</label><input id={`${p.id}-model`} list={`${p.id}-models`} placeholder={t("ph_model")} value={p.model} onChange={e => updatePlayer(p.id, {model: e.target.value})}/><datalist id={`${p.id}-models`}>{PROVIDERS[p.provider].models.map(model => <option key={model} value={model}/>)}</datalist></div>
          {!(p.backend === "codex" && p.auth_mode === "subscription") && <div className="field key-field"><label htmlFor={`${p.id}-key`}>{t("f_key")}</label><input id={`${p.id}-key`} type="password" autoComplete="off" placeholder={t("ph_key")} value={p.api_key} onChange={e => updatePlayer(p.id, {api_key: e.target.value})}/></div>}
          {HARNESS_BACKENDS.has(p.backend) && <div className="field reasoning-field"><label htmlFor={`${p.id}-reasoning`}>Reasoning Effort</label><select id={`${p.id}-reasoning`} value={p.reasoning_effort} onChange={e => updatePlayer(p.id, {reasoning_effort: e.target.value as ReasoningEffort})}>{REASONING_OPTIONS.filter(option => p.backend !== "codex" || option.value !== "none").map(option => <option key={option.value} value={option.value}>{option.label[lang]}</option>)}</select></div>}
          <div className="provider-note">{PROVIDERS[p.provider].note[lang]}</div>
        </>}
        {(["random", "human"] as Backend[]).includes(p.backend) && <div className="field manual-backend"><label htmlFor={`${p.id}-backend`}>{t("f_backend")}</label><select id={`${p.id}-backend`} value={p.backend} onChange={e => updatePlayer(p.id, {backend: e.target.value as Backend})}>{Object.entries(BACKENDS).map(([id, b]) => <option key={id} value={id}>{b.label[lang]}</option>)}</select><small>{p.backend === "human" ? t("human_note") : t("random_note")}</small></div>}
        {players.length > 2 && <button className="remove" aria-label={`${t("remove")} ${p.name}`} onClick={() => setPlayers(x => x.filter(y => y.id !== p.id))}>×</button>}
      </article>)}</div>
      <div className="setup-actions">
        <button className="add-player human-add" disabled={players.length >= maxPlayers} onClick={() => setPlayers(x => [...x, humanPlayer(x.length + 1)])}>{t("add_human")}</button>
        <button className="add-player" disabled={players.length >= maxPlayers} onClick={() => setPlayers(x => [...x, player(x.length + 1, "random")])}>{t("add_ai")}</button>
        <button className="shuffle-order" onClick={shufflePlayers}>{t("shuffle")}</button>
        <div className="field mini"><label htmlFor="match-seed">{t("f_seed")}</label><input id="match-seed" inputMode="numeric" value={seed} onChange={e => setSeed(e.target.value)}/></div>
        <div className="field mini speed"><label htmlFor="match-speed">{t("f_speed")} <b>{speed}ms</b></label><input id="match-speed" type="range" min="0" max="2000" step="50" value={speed} onChange={e => setSpeed(Number(e.target.value))}/></div>
        <button className="start" disabled={starting} onClick={startMatch}>{starting ? t("starting") : t("start")}</button>
      </div>
      {game === "ark_nova" && <div className="setup-scope-note"><b>{GAME_COPY.ark_nova.badge}</b> {zh ? "基础版 128 动物、64 赞助商、32 保育项目、11 终局计分和 5 种行动牌均已程式化；实体 255 张清单用于校验重复牌与牌库守恒。" : "The base set's 128 Animals, 64 Sponsors, 32 Conservation Projects, 11 Final Scoring cards, and five Action cards are executable; the 255-card physical roster validates duplicates and deck conservation."}</div>}
      {game === "azul" && <div className="setup-scope-note"><b>{GAME_COPY.azul.badge}</b> {zh ? "支持彩色墙基础版、100 枚具名花砖、工厂与中央区选砖、图案线、地板罚分、相邻计分、终局奖励和确定性回放；不包含灰墙玩法、扩展或出版商美术。" : "Supports the colored-wall base game, 100 identity-safe tiles, factory/center drafting, pattern lines, floor penalties, adjacency scoring, endgame bonuses and deterministic replay; no gray wall, expansions or publisher artwork."}</div>}
      {game === "brass_birmingham" && <div className="setup-scope-note"><b>{GAME_COPY.brass_birmingham.badge}</b> {zh ? "支持官方人数牌组、产业板、市场、商人、Build/Sell/Develop、单双铁路、负收入变卖、双时代计分与完整回放；界面不包含出版商美术。" : "Supports official player counts, industry board, markets, merchants, Build/Sell/Develop, single/double rail, negative-income liquidation, two-era scoring and full replay; no publisher artwork."}</div>}
      {game === "century_spice_road" && <div className="setup-scope-note"><b>{GAME_COPY.century_spice_road.badge}</b> {zh ? "完整基础牌组数值、重复交易、升级、市场压香料、商队容量、金币银币、终局与计分均已接通；不包含出版商卡图。" : "Full base-set values, repeat trades, upgrades, market spice, caravan capacity, gold/silver coins, endgame and scoring wired up; no publisher artwork."}</div>}
      {game === "seven_wonders" && <div className="setup-scope-note"><b>{GAME_COPY.seven_wonders.badge}</b> {zh ? "支持 148 张基础牌、日/夜双面奇迹、密封同步选牌、邻城贸易、链式建造、军事、科技、商会与七类计分；不包含扩展或出版商美术。" : "Supports all 148 base cards, Day/Night Wonders, sealed simultaneous drafting, neighbor trade, chains, military, science, guilds and seven-part scoring; no expansions or publisher artwork."}</div>}
      {error && <div className="error">{error}</div>}
    </section>
  </main>;

 return <main className="table-shell">
    <header className="table-header">
      <div><span className="brand-mark">ABGA</span><strong>{snapshot.game_description.name} {snapshot.game === "splendor" ? t("live_table") : snapshot.game === "century_spice_road" ? t("trade_arena") : t("controlled_arena")}</strong></div>
      <div className="match-meta"><span>{t("match")} <code>{snapshot.match_id}</code></span><span>{t("turn")} <b>{snapshot.turn_count}</b>{snapshot.game === "ark_nova" && <> · {t("decision")} <b>{snapshot.decision_count ?? arkView?.decision_count}</b></>}</span><span className={`status ${snapshot.paused ? "status-paused" : `status-${snapshot.status}`}`}>{snapshot.status !== "active" ? t("s_finished") : snapshot.paused ? (snapshot.pause_pending ? t("s_wait_pause") : t("s_paused")) : t("s_active")}</span></div>
      <div className="table-actions">
        <button className="lang-toggle" onClick={toggleLang} aria-label="Switch language">{zh ? "EN" : "中文"}</button>
        <button className={`pause-button ${snapshot.paused ? "is-paused" : ""}`} disabled={snapshot.status !== "active" || controlling} aria-pressed={snapshot.paused} onClick={togglePause}>{controlling ? t("processing") : snapshot.paused ? t("resume") : t("pause")}</button>
        <button onClick={() => { sourceRef.current?.close(); setSnapshot(null); setTimeline([]); setChat([]); setError(""); }}>{t("new_match")}</button>
      </div>
    </header>
    {error && <div className="table-error" role="alert">{error}</div>}
    <div className="table-grid">
      <aside className="players-column">{snapshot.players.map(identity => {
        // Ark Nova agent-only matches use a dedicated omniscient Web projection;
        // player/agent observations remain seat-isolated in the runner.
        const visiblePlayer = snapshot.game === "ark_nova"
          ? arkView?.players[identity.seat] : viewer?.players[identity.seat];
        return snapshot.game === "splendor"
          ? <PlayerPanel key={identity.seat} player={visiblePlayer as PlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>
          : snapshot.game === "azul"
            ? <AzulPlayerPanel key={identity.seat} player={visiblePlayer as AzulPlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat} holdsStartMarker={azulView?.start_marker_holder_seat === identity.seat}/>
          : snapshot.game === "ark_nova"
            ? <ArkPlayerPanel key={identity.seat} player={visiblePlayer as ArkPlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>
            : snapshot.game === "brass_birmingham"
              ? <BrassPlayerPanel key={identity.seat} player={visiblePlayer as BrassPlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>
              : snapshot.game === "century_spice_road"
                ? <CenturyPlayerPanel key={identity.seat} player={visiblePlayer as CenturyPlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>
                : <SevenPlayerPanel key={identity.seat} player={visiblePlayer as SevenPlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>;
      })}</aside>
      <section className="board">
        {snapshot.paused && <div className={`pause-notice ${snapshot.pause_pending ? "pending" : ""}`}><strong>{snapshot.pause_pending ? t("pause_pending") : t("paused")}</strong><span>{snapshot.pause_pending ? t("pause_pending_desc") : t("paused_desc")}</span></div>}
        {snapshot.human_turn && <section className="human-turn" aria-live="polite">
          <header><div><span>YOUR TURN · SEAT {snapshot.human_turn.seat + 1}</span><h2>{snapshot.human_turn.player}{t("pick_action")}</h2></div><b>{snapshot.human_turn.legal_actions.length} {t("legal_opts")}</b></header>
          {snapshot.game === "azul" ? <AzulActionPicker actions={snapshot.human_turn.legal_actions} disabled={Boolean(submittingAction)} submitting={submittingAction} onChoose={submitHumanAction}/> : snapshot.game === "seven_wonders" ? <SevenActionPicker actions={snapshot.human_turn.legal_actions} view={sevenView} names={names} disabled={Boolean(submittingAction)} submitting={submittingAction} onChoose={submitHumanAction}/> : arkMapInteraction ? <div className="ark-map-action-notice"><div><b>{lang === "zh" ? "请在对应板块直接操作" : "Act directly on the matching board"}</b><span>{lang === "zh" ? "行动牌、手牌和地图位于玩家板；展示牌与抽牌位于整体游戏板；协会事务位于协会板。" : "Action cards, hand, and map are on the player board; display and draw actions are on the main board; association tasks are on the association board."}</span></div>{snapshot.human_turn.legal_actions.filter(item => !isArkTableAction(item)).map(item => <HumanActionChoice key={item.id} item={item} view={splendorView} brassView={brassView} disabled={Boolean(submittingAction)} submitting={submittingAction === item.id} onChoose={() => submitHumanAction(item)}/>)}</div> : <div className="human-action-groups">{Object.entries(groupActions(snapshot.human_turn.legal_actions)).map(([kind, actions]) => <section key={kind}>
            <h3>{ACTION_GROUPS[lang][kind] || kind}<span>{actions.length}</span></h3>
            <div className={CARD_ACTION_TYPES.has(kind) ? "card-action-grid" : kind === "take_tokens" ? "token-action-grid" : undefined}>{actions.map(item => <HumanActionChoice key={item.id} item={item} view={splendorView} brassView={brassView} disabled={Boolean(submittingAction)} submitting={submittingAction === item.id} onChoose={() => submitHumanAction(item)}/>)}</div>
          </section>)}</div>}
        </section>}
        {snapshot.game === "splendor" ? <SplendorBoard view={splendorView}/> : snapshot.game === "azul" ? <AzulBoard view={azulView}/> : snapshot.game === "ark_nova" ? <ArkNovaBoard view={arkView} players={snapshot.players} legalActions={snapshot.human_turn?.legal_actions || []} submitting={submittingAction} onChoose={submitHumanAction}/> : snapshot.game === "brass_birmingham" ? <BrassBoard view={brassView} players={snapshot.players}/> : snapshot.game === "century_spice_road" ? <CenturyBoard view={centuryView}/> : <SevenBoard view={sevenView} spectatorViews={sevenSpectatorViews} identities={snapshot.players}/>}
        {snapshot.status === "finished" && <div className="winner-banner"><span>{t("winner")}</span><strong>{timeline.at(-1)?.event.rankings?.[0]?.player || t("match_over")}</strong><button onClick={() => { setSnapshot(null); setTimeline([]); }}>{t("play_again")}</button></div>}
      </section>
      <aside className="timeline">
        <header><div><span>{t("model_stream")}</span><h2>{t("chat_h")}</h2></div><i className={snapshot.status === "active" && (!snapshot.paused || snapshot.pause_pending) ? "pulse" : ""}/></header>
        <div className="chat-list">{chat.length === 0 && <p className="waiting">{snapshot.game_description.runnable ? t("waiting_model") : t("waiting_note")}</p>}{chat.map(turn => <article className={`chat-turn chat-${turn.status}`} key={turn.key}>
          <header><strong>{turn.player}</strong><span>{turn.backend} · {t("attempt")} {turn.attempt}{turn.status === "thinking" ? ` · ${t("generating")}` : turn.processLatencyMs !== undefined ? ` · ${lang === "zh" ? "行动" : "action"} ${((turn.actionLatencyMs ?? turn.processLatencyMs) / 1000).toFixed(1)}s · ${lang === "zh" ? "进程" : "process"} ${(turn.processLatencyMs / 1000).toFixed(1)}s` : ""}</span></header>
          {turn.reasoning && <details open><summary>{t("thinking")}{turn.status === "done" ? ` · ${t("collapsible")}` : ""}</summary><pre>{turn.reasoning}</pre></details>}
          {turn.content && <div className="model-answer"><b>{t("answer")}</b><pre>{turn.content}</pre></div>}
          {turn.status === "thinking" && <div className="typing"><i/><i/><i/></div>}
        </article>)}</div>
        <section className="action-drawer"><header><span>{t("actions")}</span><strong>{t("decision_log")}</strong><b>{timeline.filter(item => ["decision", "turn"].includes(item.event.type)).length}</b></header>
          <div>{[...timeline].reverse().filter(item => !["agent_started", "agent_finished"].includes(item.event.type)).slice(0, 40).map(item => <article key={item.seq} className={`event event-${item.event.type}`}>
            <span>{String(item.seq + 1).padStart(3,"0")}</span><div><p>{describeAction(item, names, lang)}</p>{item.event.backend && <small>{item.event.backend}{item.event.agent?.process_latency_ms !== undefined ? ` · ${lang === "zh" ? "行动" : "action"} ${item.event.agent.action_latency_ms ?? "—"}ms · ${lang === "zh" ? "进程" : "process"} ${item.event.agent.process_latency_ms}ms` : item.event.agent?.latency_ms ? ` · ${item.event.agent.latency_ms}ms` : ""}</small>}
              {item.event.tool && (item.event.arguments !== undefined || item.event.result !== undefined) && <details className="tool-payload"><summary>{t("view_tool")}</summary><pre>{JSON.stringify(item.event.result ?? item.event.arguments, null, 2)}</pre></details>}
            </div>
          </article>)}</div>
        </section>
      </aside>
    </div>
  </main>;
}
