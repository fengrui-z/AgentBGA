"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { mergeMatchSnapshot } from "./snapshot-state";
import ArenaPage from "./arena/page";
import { CarcassonneTable, CarcassonnePlayerPanel, type CarcassonneView, type CarcassonnePlayer } from "./carcassonne-table";
import { WingspanTable, WingspanPlayerPanel, type WingspanView, type WingspanPlayer } from "./wingspan-table";
import { HarmoniesTable, HarmoniesPlayerPanel, type HarmoniesView, type HarmoniesPlayer } from "./harmonies-table";
import { BurgundyTable, BurgundyPlayerPanel, burgundyActionLabel, type BurgundyView, type BurgundyPlayer } from "./burgundy-table";
import {
  ArkNovaPlayerSummary, ArkNovaTable,
  type ArkPlayerView, type ArkView,
} from "./ark-nova-table";
import { canAddToken, counts, resolveSelection, selectionCandidates, tokenTotal } from "./splendor-selection";
import "./splendor-table.css";
import "./human-play.css";
import {ActionChoices, HumanConfirmation, readableMove} from "./human-controls";

// ── i18n ─────────────────────────────────────────────────────────────
type Lang = "zh" | "en";
type ArkMapId = "map-0" | "map-a";
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
    auth_api_key: "API Key（按量）", auth_subscription: "ChatGPT 订阅", auth_grok: "SuperGrok 订阅（本机登录）",
    og_harness: "Agent Harness", og_direct: "直连模型 API",
    ph_model: "可选择或输入 model-id", ph_key: "仅在本次对局使用",
    ph_endpoint: "如 http://127.0.0.1:8000/v1（本地模型 / 网关）",
    add_human: "＋ 添加人类", add_ai: "＋ 添加 AI / 基线", shuffle: "⤨ 随机座次",
    start: "开始对局 →", starting: "正在入席…", err_start: "无法启动对局",
    reconnect: "重新连接对局", reconnecting: "正在连接…", reconnect_id: "对局 ID", reconnect_hint: "Web 服务未重启时，可输入对局 ID 无缝恢复可视化与实时记录。",
    human_note: "轮到该座位时在牌桌上操作", random_note: "无需 API，自动随机行动",
    seat_label: "座位", player_label: "玩家",
    move_up: "前移", move_down: "后移", remove: "移除",
    // table header
    live_table: "Live Table", trade_arena: "Trade Arena", controlled_arena: "Controlled Arena",
    match: "对局", turn: "回合", decision: "决策",
    s_finished: "已结束", s_wait_pause: "等待暂停", s_paused: "已暂停", s_active: "进行中",
    processing: "处理中…", resume: "▶ 继续对局", pause: "Ⅱ 暂停", new_match: "新对局",
    watch_live: "观战已有牌桌", watch: "开始观战 →", watching: "正在接入…",
    watch_id: "搜索对局 ID、玩家或游戏", live_tables: "本地牌桌", no_tables: "还没有可观战的对局。CLI 或 Web 开桌后会出现在这里。",
    no_matching_tables: "没有匹配的牌桌，请更换搜索内容。",
    spectator: "观战", err_watch: "无法接入对局",
    err_pause: "无法更新暂停状态", err_submit: "无法提交行动",
    err_ws: "实时连接已断开，可刷新页面后重新开始。", call_failed: "调用失败",
    pause_pending: "等待当前模型完成…", paused: "对局已暂停",
    pause_pending_desc: "返回的这一手会正常落盘，下一位不会开始思考。",
    paused_desc: "牌桌停在安全的回合边界，点击“继续对局”即可恢复。",
    // human turn
    your_turn: "YOUR TURN · SEAT", pick_action: "，请选择行动", legal_opts: "个合法选项",
    submitting: "提交中…", returning: "归还", buying: "支付", reserving: "预留",
    selection_expired: "当前选择已失效，请根据最新局面重新选择。",
    azul_source_required: "请先选择砖块来源。", azul_color_required: "请选择要拿取的颜色。", azul_destination_required: "请选择图案线或地板线。",
    // splendor board
    supply: "供应区", gem_bank: "宝石银行", nobles: "贵族", available: "AVAILABLE",
    tier: "TIER", cards_unit: "张",
    reserve_label: "预留", buy_label: "购买",
    // player panel
    tokens: "宝石", engine: "引擎", purchased: "已购", reserved: "预留", nobles_owned: "贵族",
    // ark nova
    ark_eyebrow: "ARK NOVA · OFFICIAL BASE CANDIDATE",
    ark_phase_select: "正在选择起始手牌", ark_phase_play: "多阶段对局进行中",
    ark_phase_note: "当前对局运行基础版官方语义候选：255 张实体卡、5 种行动牌、Map 0 与 Map A 已接入统一规则引擎。",
    ark_tracks: "TRACKS / BREAK", ark_tracks_h: "公共轨道", cur_decision: "CURRENT DECISION",
    ark_display: "CARD DISPLAY", ark_display_h: "中央卡牌展示区", deck: "牌库", discard: "弃牌",
    ark_after_select: "起始选牌后翻开",
    ark_assoc: "ASSOCIATION BOARD", ark_assoc_h: "协会板与基础保育项目",
    ark_partner: "合作动物园", ark_uni: "大学", ark_donation: "捐款", ark_blocked: "双人封锁", ark_avail: "可用",
    ark_zoo: "ZOO MAP", ark_zoo_h: "玩家动物园", ark_zoo_unit: "官方坐标 footprint",
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
    winner: "WINNER", play_again: "再来一局", match_over: "对局结束", view_final_board: "查看终局游戏界面",
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
    auth_api_key: "API key (usage-based)", auth_subscription: "ChatGPT subscription", auth_grok: "SuperGrok subscription (local login)",
    og_harness: "Agent Harness", og_direct: "Direct model API",
    ph_model: "Pick or type model-id", ph_key: "Used for this match only",
    ph_endpoint: "e.g. http://127.0.0.1:8000/v1 (local model / gateway)",
    add_human: "+ Add human", add_ai: "+ Add AI / baseline", shuffle: "⤨ Shuffle seats",
    start: "Start match →", starting: "Seating…", err_start: "Failed to start match",
    reconnect: "Reconnect match", reconnecting: "Connecting…", reconnect_id: "Match ID", reconnect_hint: "If the Web service has not restarted, enter the match ID to restore the live table and event stream.",
    human_note: "Play at the table when it's this seat's turn", random_note: "No API needed, random actions",
    seat_label: "Seat", player_label: "Player",
    move_up: "Move up", move_down: "Move down", remove: "Remove",
    live_table: "Live Table", trade_arena: "Trade Arena", controlled_arena: "Controlled Arena",
    match: "Match", turn: "Turn", decision: "Decision",
    s_finished: "Finished", s_wait_pause: "Waiting to pause", s_paused: "Paused", s_active: "Running",
    processing: "Working…", resume: "▶ Resume", pause: "Ⅱ Pause", new_match: "New match",
    watch_live: "Watch an existing table", watch: "Watch →", watching: "Opening…",
    watch_id: "Search match ID, player, or game", live_tables: "Local tables", no_tables: "No watchable tables yet. CLI or web matches will show up here.",
    no_matching_tables: "No matching tables. Try another search.",
    spectator: "Spectator", err_watch: "Failed to watch match",
    err_pause: "Failed to update pause state", err_submit: "Failed to submit action",
    err_ws: "Live connection dropped. Refresh and restart.", call_failed: "Call failed",
    pause_pending: "Waiting for the model to finish…", paused: "Match paused",
    pause_pending_desc: "The pending move will commit normally; the next seat will not start.",
    paused_desc: "The table stops at a safe turn boundary. Click Resume to continue.",
    your_turn: "YOUR TURN · SEAT", pick_action: ", choose an action", legal_opts: "legal options",
    submitting: "Submitting…", returning: "Return", buying: "Pay", reserving: "Reserve",
    selection_expired: "This choice is no longer legal. Choose again from the latest position.",
    azul_source_required: "Choose a tile source first.", azul_color_required: "Choose the color to draft.", azul_destination_required: "Choose a pattern line or the floor.",
    supply: "Supply", gem_bank: "Gem Bank", nobles: "Nobles", available: "AVAILABLE",
    tier: "TIER", cards_unit: "cards",
    reserve_label: "Reserve", buy_label: "Buy",
    tokens: "Gems", engine: "Engine", purchased: "Purchased", reserved: "Reserved", nobles_owned: "Nobles",
    ark_eyebrow: "ARK NOVA · OFFICIAL BASE CANDIDATE",
    ark_phase_select: "Selecting starting hand", ark_phase_play: "Multi-phase match in progress",
    ark_phase_note: "This match runs the official-base semantic candidate: all 255 physical cards, five Action cards, Map 0, and Map A are wired into one rules engine.",
    ark_tracks: "TRACKS / BREAK", ark_tracks_h: "Public tracks", cur_decision: "CURRENT DECISION",
    ark_display: "CARD DISPLAY", ark_display_h: "Card display", deck: "Deck", discard: "Discard",
    ark_after_select: "Revealed after pick",
    ark_assoc: "ASSOCIATION BOARD", ark_assoc_h: "Association board & conservation projects",
    ark_partner: "Partner zoos", ark_uni: "Universities", ark_donation: "Donations", ark_blocked: "Two-player locked", ark_avail: "available",
    ark_zoo: "ZOO MAP", ark_zoo_h: "Player zoo", ark_zoo_unit: "Official coordinate footprint",
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
    winner: "WINNER", play_again: "Play again", match_over: "Match over", view_final_board: "View final game state",
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

type Backend = "openai" | "anthropic" | "gemini" | "claude" | "pi" | "qwen" | "codex" | "cursor" | "grok" | "opencode" | "dsh" | "hermes" | "minimal" | "human" | "random";
type Provider = "custom" | "claude_code" | "pi" | "qwen" | "codex" | "cursor" | "grok" | "opencode" | "dsh" | "hermes" | "minimal" | "deepseek" | "dashscope" | "zhipu" | "minimax";
type GameId = "carcassonne" | "wingspan" | "harmonies" | "splendor" | "azul" | "ark_nova" | "brass_birmingham" | "castles_of_burgundy" | "century_spice_road" | "seven_wonders";
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
type BrassMapPoint = {x: number; y: number; kind: "industry" | "merchant" | "farm"};
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
  paused: boolean; pause_pending: boolean; running?: boolean; mode?: "live" | "spectator" | "store"; event_seq?: number;
  human_turn?: {seat: number; player: string; version: number; legal_actions: LegalAction[]} | null;
  players: {seat: number; name: string; backend: string; model?: string; reasoning_effort?: string}[]; views: (View | AzulView | ArkView | BrassView | BurgundyView | CenturyView | SevenView | HarmoniesView | WingspanView | CarcassonneView)[];
  spectator_view?: ArkView;
  rankings?: {seat: number; player: string}[];
};
type TableSummary = {
  match_id: string; game: GameId; status: string; turn_count: number; seed: number;
  mode?: string; active_seat?: number;
  players: {seat: number; name: string; backend: string; model?: string}[];
};
type LegalAction = {id: string; label?: string; benefit_summary?: string; benefit_summary_cn?: string; action: Record<string, unknown>};
type TimelineEvent = {
  type: string; player?: string; seat?: number; error?: string; turns?: number;
  backend?: string; agent?: {latency_ms?: number; action_latency_ms?: number; process_latency_ms?: number}; action?: Record<string, unknown>;
  rankings?: {player: string}[]; channel?: "reasoning" | "content"; delta?: string; attempt?: number; version?: number;
  harness?: string; tool?: string; arguments?: unknown; result?: unknown; action_id?: string;
  noble_id?: string; card_id?: string;
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
  carcassonne: {eyebrow: "CARCASSONNE", name: {zh:"卡卡颂",en:"Carcassonne"}, description: {zh:"旋转并拼接中世纪地形，派遣随从建设城市、道路、修道院与田野。支持 2–5 人基础版，包含农夫计分。",en:"Build a shared medieval landscape, claim cities, roads, monasteries and fields. 2–5 players, base game with farmers."}, badge:"PLAYABLE BETA", note:{zh:"72 块地形 · 随从调度 · 区域争夺",en:"72 tiles · follower management · area majority"}},
  wingspan: {eyebrow: "WINGSPAN", name: {zh:"展翅翱翔",en:"Wingspan"}, description: {zh:"吸引鸟类来到森林、草原与湿地，建立联动引擎，争夺四轮目标。支持 2–5 人基础版。",en:"Attract birds to forest, grassland and wetland habitats. Build your engine across four rounds. 2–5 players, base game."}, badge:"PLAYABLE BETA", note:{zh:"170 张鸟牌 · 栖息地引擎 · 四轮目标",en:"170 birds · habitat engines · round goals"}},
  harmonies: {eyebrow: "HARMONIES", name: {zh:"自然和弦",en:"Harmonies"}, description: {zh:"在六角棋盘上叠放地形、连接河流，为动物营造栖息地。支持 1–4 人、双面地图与自然之灵。",en:"Stack landscapes, connect rivers and create animal habitats on a hex board. 1–4 players, both boards and optional Nature’s Spirits."}, badge: "PLAYABLE BETA", note: {zh:"地形堆叠 · 动物栖息地 · 空间规划",en:"Landscapes · habitats · spatial planning"}},
  azul: {eyebrow: "AZUL", name: {zh:"花砖物语",en:"Azul"}, description: {zh:"从工厂展示区或中央区选取同色花砖，规划图案线并铺设墙面；兼顾相邻计分、地板罚分与终局时机。",en:"Draft one color from factories or the center, fill pattern lines and tile your wall while balancing adjacency, floor penalties and endgame timing."}, badge: "PLAYABLE BETA", note: {zh:"选砖 · 拼墙 · 空间规划",en:"Draft · tile · spatial planning"}},
  ark_nova: {eyebrow: "ARK NOVA", name: {zh:"方舟动物园",en:"Ark Nova"}, description: {zh:"基础版 255 张实体卡、5 种行动牌、Map 0 与 Map A 已接入可审计语义引擎，覆盖条件、费用、触发、互动、收入与终局计分。",en:"All 255 physical base cards, five Action cards, Map 0, and Map A run through an auditable semantic engine covering requirements, costs, triggers, interaction, income, and final scoring."}, badge: "OFFICIAL BASE CANDIDATE", note: {zh:"完整卡牌语义 · Map 0 / Map A",en:"Complete card semantics · Map 0 / Map A"}},
  brass_birmingham: {eyebrow: "BRASS: BIRMINGHAM", name: {zh:"伯明翰",en:"Brass: Birmingham"}, description: {zh:"测试模型在双时代经济网络中的长期规划：产业建设、资源来源、商人出售、动态顺位和运河到铁路的资产转换。",en:"Test long-term planning in a two-era economic network: industry building, resource sourcing, merchant selling, dynamic turn order and canal-to-rail transitions."}, badge: "PLAYABLE BETA", note: {zh:"产业 · 网络 · 双时代经济",en:"Industry · network · two-era economy"}},
  castles_of_burgundy: {eyebrow: "THE CASTLES OF BURGUNDY", name: {zh:"勃艮第城堡",en:"The Castles of Burgundy"}, description: {zh:"用双骰经营自己的领地：从仓库取板块、铺设六角区域、交易货物，并用工人修正点数，在五个阶段中建立连锁收益。",en:"Develop a duchy with two dice: take and place hexes, trade goods, adjust results with workers, and chain tile effects across five phases."}, badge: "2019 BASE", note: {zh:"骰子规划 · 六角领地 · 连锁效果",en:"Dice planning · hex duchy · combos"}},
  century_spice_road: {eyebrow: "CENTURY: SPICE ROAD", name: {zh:"香料之路",en:"Century: Spice Road"}, description: {zh:"经营自己的商队：获取商人牌、升级或交换香料、争夺金币银币，并抢先完成高分订单。支持 2–5 名玩家。",en:"Run your caravan: acquire merchant cards, upgrade or trade spices, race for gold and silver coins to fulfill high-score orders. 2–5 players."}, badge: "CLASSIC BASE", note: {zh:"商人牌 · 香料引擎 · 订单竞速",en:"Merchant cards · spice engine · order race"}},
  seven_wonders: {eyebrow: "7 WONDERS", name: {zh:"七大奇迹",en:"7 Wonders"}, description: {zh:"在三个时代中密封选牌并传递手牌，通过生产、贸易、军事、科技与奇迹建设塑造古代文明。支持 3–7 名玩家。",en:"Draft sealed choices across three Ages, passing hands while developing production, trade, military, science and a Wonder. 3–7 players."}, badge: "SECOND EDITION BASE", note: {zh:"轮抽 · 邻城贸易 · 七维计分",en:"Draft · neighbor trade · seven-part scoring"}},
};
const BACKENDS: Record<Backend, {label: Record<Lang, string>; url: string; key: string; model: string}> = {
  openai: { label: {zh: "OpenAI 兼容", en: "OpenAI-compatible"}, url: "https://api.openai.com/v1", key: "", model: "" },
  anthropic: { label: {zh: "Anthropic", en: "Anthropic"}, url: "https://api.anthropic.com", key: "", model: "" },
  gemini: { label: {zh: "Gemini", en: "Gemini"}, url: "https://generativelanguage.googleapis.com/v1beta", key: "", model: "" },
  claude: { label: {zh: "Claude Code", en: "Claude Code"}, url: "https://api.anthropic.com", key: "", model: "" },
  pi: { label: {zh: "Pi", en: "Pi"}, url: "https://api.openai.com/v1", key: "", model: "" },
  qwen: { label: {zh: "Qwen Code", en: "Qwen Code"}, url: "https://coding.dashscope.aliyuncs.com/v1", key: "", model: "" },
  codex: { label: {zh: "Codex Harness", en: "Codex Harness"}, url: "https://api.openai.com/v1", key: "", model: "" },
  cursor: { label: {zh: "Cursor CLI", en: "Cursor CLI"}, url: "", key: "", model: "" },
  grok: { label: {zh: "Grok Build", en: "Grok Build"}, url: "https://api.x.ai/v1", key: "", model: "grok-4.6" },
  opencode: { label: {zh: "OpenCode Harness", en: "OpenCode Harness"}, url: "https://api.deepseek.com", key: "", model: "" },
  dsh: { label: {zh: "DeepSeek Harness", en: "DeepSeek Harness"}, url: "https://api.deepseek.com", key: "", model: "" },
  hermes: { label: {zh: "Hermes Agent", en: "Hermes Agent"}, url: "https://api.deepseek.com", key: "", model: "" },
  minimal: { label: {zh: "Minimal Harness", en: "Minimal Harness"}, url: "https://api.deepseek.com", key: "", model: "" },
  human: { label: {zh: "人类玩家", en: "Human player"}, url: "", key: "", model: "" },
  random: { label: {zh: "随机基线", en: "Random baseline"}, url: "", key: "", model: "" },
};
const HARNESS_BACKENDS = new Set<Backend>(["claude", "pi", "qwen", "codex", "cursor", "grok", "opencode", "dsh", "hermes", "minimal"]);
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
  qwen: {label: {zh:"Qwen Code",en:"Qwen Code"}, backend: "qwen", url: "https://coding.dashscope.aliyuncs.com/v1", models: ["qwen3-coder-plus"], note: {zh:"Qwen Code 持久 session + 独立 QWEN_HOME + 仅座位 MCP 工具；默认阿里云 Coding Plan Endpoint",en:"Persistent session + isolated QWEN_HOME + seat-only MCP tools; defaults to the Alibaba Cloud Coding Plan endpoint"}},
  codex: {label: {zh:"Codex",en:"Codex"}, backend: "codex", url: "https://api.openai.com/v1", models: ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex-spark"], note: {zh:"可复用本机 codex login 的 ChatGPT 订阅，或使用按量 API Key；自定义 Endpoint 必须支持 Responses API",en:"Reuse the local codex login ChatGPT subscription or use a metered API key; custom endpoints must support the Responses API"}},
  cursor: {label: {zh:"Cursor CLI",en:"Cursor CLI"}, backend: "cursor", url: "", models: ["gpt-5.6-sol", "grok-4.6"], note: {zh:"Cursor Agent CLI 持久 session + 独立数据目录 + 仅座位 MCP 工具；使用 Cursor API Key",en:"Persistent Cursor Agent CLI session + isolated data directory + seat-only MCP tools; uses a Cursor API key"}},
  grok: {label: {zh:"Grok Build",en:"Grok Build"}, backend: "grok", url: "https://api.x.ai/v1", models: ["grok-4.6", "grok-4.5", "grok-build"], note: {zh:"可复用本机 grok login 的 SuperGrok 订阅，或使用 API Key；订阅模式使用模型默认思考强度，可用模型见 grok models",en:"Reuse local grok login for SuperGrok or use an API key. Subscription mode uses native reasoning defaults; see grok models."}},
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

function Gem({color, value, compact = false}: {color: string; value: number | string; compact?: boolean}) {
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
      <div className="score"><strong>{p.score}</strong><span>/15 {lang === "zh" ? "分" : "pts"}</span></div>
    </header>
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}{identity?.reasoning_effort && <b>{lang === "zh" ? `思考：${identity.reasoning_effort}` : `reasoning: ${identity.reasoning_effort}`}</b>}</div>
    <div className="asset-row"><span className="asset-title">{t("tokens")} {tokenTotal(p.tokens)}/10</span><div>{GEM_ORDER.map(c => <Gem key={c} color={c} value={p.tokens[c]} compact />)}</div></div>
    <div className="asset-row"><span className="asset-title">{lang === "zh" ? "永久折扣" : "Discounts"}</span><div>{BONUS_ORDER.map(c => <Gem key={c} color={c} value={p.bonuses[c]} compact />)}</div></div>
    <details className="sp-player-details"><summary>{lang === "zh" ? "已购发展牌" : "Purchased cards"} · {p.purchased_count}</summary>
    <div className="owned-cards">{p.purchased.length ? p.purchased.map(card => <DevCard key={card.id} card={card} small />) : <em>{lang === "zh" ? "尚未建立引擎" : "No engine yet"}</em>}</div>
    </details><details className="reserve-row"><summary>{t("reserved")} {p.reserved_count}/3</summary><div>{p.reserved.map((card, i) => "hidden" in card ? <i className="reserved-hidden" key={i}>?</i> : <DevCard key={card.id} card={card} reserved />)}</div></details>
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
    <details className="century-player-cards"><summary>{lang === "zh" ? "商人牌" : "Merchant cards"} · {p.hand.length} / {p.played.length}</summary><div className="century-hand-head"><span>{t("avail_merchant")}</span><b>{p.hand.length}</b><small>{t("played")} {p.played.length}</small></div>
    <div className="century-hand">{p.hand.map(card => <CenturyMerchantCard key={card.id} card={card} small/>)}{p.hand.length === 0 && <em>{t("need_rest")}</em>}</div><div className="century-used-cards">{p.played.map(card => <CenturyMerchantCard key={card.id} card={card} small/>)}</div></details>
  </section>;
}

function CenturyBoard({view, seat, actions = [], disabled, onChoose}: {view?: CenturyView; seat:number; actions?: LegalAction[]; disabled?: boolean; onChoose: (item: LegalAction) => void}) {
  const lang = useLang(); const t = makeT(lang); const zh = lang === "zh";
  if (!view) return null;
  const own = view.players[seat];
  const options = (items: LegalAction[], label: string) => <ActionChoices actions={items} label={label} describe={item => readableMove(item.action, view, lang, humanItemText(item, lang))} lang={lang} disabled={disabled} onChoose={onChoose}/>;
  return <div className="century-board">
    <section className="century-status"><div><h2>{t("century_status")}</h2><p>{t("century_note")} {view.caravan_limit} {t("caravan_unit")}</p></div>{options(actions.filter(a=>a.action.type === "rest"),zh ? "休息" : "Rest")}</section>
    <section className="century-point-market"><header><h3>{t("order_market")}</h3><b>{t("deck_label")} {view.point_deck_count}</b></header><div>{view.point_market.map((card,index)=><div className="century-point-slot" key={card.id}>{index===0&&view.coins.gold>0&&<span className="century-coin coin-gold">{t("gold_coin")} × {view.coins.gold}</span>}{index===view.coins.silver_position&&view.coins.silver>0&&<span className="century-coin coin-silver">{t("silver_coin")} × {view.coins.silver}</span>}<CenturyPointCard card={card}/>{options(actions.filter(a=>a.action.type==="claim_point" && Number(a.action.position)===index),zh?`完成订单 ${index+1}`:`Claim order ${index+1}`)}</div>)}</div></section>
    <section className="century-merchant-market"><header><h3>{t("trade_market")}</h3><b>{t("deck_label")} {view.merchant_deck_count}</b></header><div>{view.merchant_market.map((slot,index)=><div className="century-merchant-slot" key={slot.card.id}><span className="century-market-index">{index+1}</span><CenturyMerchantCard card={slot.card}/><div className="century-card-spices"><span>{t("card_spice")}</span><Spices pool={slot.spices} compact/></div>{options(actions.filter(a=>a.action.type==="acquire_merchant"&&Number(a.action.position)===index),zh?`获取商人 ${index+1}`:`Acquire merchant ${index+1}`)}</div>)}</div></section>
    <section className="century-play-hand"><header><h3>{zh?"你的商人牌":"Your merchants"}</h3><Spices pool={own.spices} compact/></header><div>{own.hand.map((card,index)=><article key={card.id}><CenturyMerchantCard card={card}/>{options(actions.filter(a=>a.action.type==="play_merchant"&&a.action.card_id===card.id),zh?`打出商人 ${index+1}`:`Play merchant ${index+1}`)}</article>)}</div><details><summary>{zh?`已使用 ${own.played.length} 张 · 休息后收回`:`${own.played.length} used · recover by resting`}</summary><div className="century-used-cards">{own.played.map(card=><CenturyMerchantCard key={card.id} card={card} small/>)}</div></details></section>
    <section className="century-legend">{SPICE_ORDER.map((color,i)=><span key={color}><i className={`spice spice-${color}`}/>{SPICE_META[color].label[lang]} · {i+1}</span>)}</section>
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

function SevenActionPicker({actions, view, names, disabled, onChoose}: {actions: LegalAction[]; view?: SevenView; names: Record<number,string>; disabled: boolean; onChoose: (item: LegalAction)=>void; onReset?:()=>void}) {
  const lang=useLang(); const zh=lang==="zh";
  const cards=view?.players.find(p=>p.seat===view.viewer_seat)?.hand.filter((c):c is SevenCard=>!("hidden" in c)) || [];
  const ids=new Set(cards.map(c=>c.id));
  return <div className="seven-action-picker">{cards.map(card=><section key={card.id} className="seven-action-card"><SevenCardTile card={card}/><div>{["build_card","build_wonder","sell_card"].map(kind=><ActionChoices key={kind} actions={actions.filter(a=>a.action.card_id===card.id&&a.action.type===kind)} label={`${card.name} · ${kind==="sell_card"?(zh?"出售 +3 金币":"Sell +3 coins"):kind==="build_wonder"?(zh?"建造奇迹":"Build Wonder"):(zh?"建造":"Build")}`} describe={a=>kind==="sell_card"?(zh?"出售 +3 金币":"Sell +3 coins"):`${kind==="build_wonder"?`${zh?"阶段":"Stage"} ${a.action.stage} · `:""}${sevenPaymentSummary(a.action,lang,names)}`} lang={lang} disabled={disabled} onChoose={onChoose}/>)}</div></section>)}{actions.filter(a=>!ids.has(String(a.action.card_id))).map(a=><button key={a.id} disabled={disabled} onClick={()=>onChoose(a)}>{humanActionText(a.action,lang)}</button>)}</div>;
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

function SevenBoard({view, spectatorViews, identities = [], actions = [], disabled, onChoose}: {view?: SevenView; spectatorViews?: SevenView[]; identities?: Snapshot["players"]; actions?: LegalAction[]; disabled: boolean; onChoose: (item: LegalAction)=>void; onReset?:()=>void}) {
  const lang = useLang(); const zh = lang === "zh";
  if (!view) return null;
  const viewer = view.players.find(player => player.seat === view.viewer_seat) ?? view.players[0];
  const visibleHand = viewer.hand.filter((card): card is SevenCard => !("hidden" in card));
  return <div className="seven-board">
    <section className="seven-status"><div><span>7 WONDERS · BASE GAME</span><h2>{zh ? `时代 ${view.age} · 第 ${view.pick} 轮选牌` : `Age ${view.age} · Pick ${view.pick}`}</h2></div><p>{zh ? `手牌向${view.pass_direction === "left" ? "左" : "右"}传递；选择在所有座位提交前保持密封。资源是每轮可重复使用的生产能力。` : `Hands pass ${view.pass_direction}; choices remain sealed until all seats submit. Resources are reusable production, not inventory.`}</p><code>{view.rules_version}</code></section>
    <section className="seven-draft-track"><div>{[1,2,3].map(age => <span key={age} className={age === view.age ? "active" : age < view.age ? "done" : ""}>AGE {age}</span>)}</div><b>{zh ? `弃牌 ${view.discard_count}` : `Discard ${view.discard_count}`}</b><small>{zh ? `已提交 ${view.pending_choice_seats.length}/${view.players.length}` : `Sealed ${view.pending_choice_seats.length}/${view.players.length}`}</small></section>
    <div className="seven-neighbor-resources">{view.players.map(p=><article key={p.seat}><b>{identities.find(i=>i.seat===p.seat)?.name} · {p.wonder_name}</b><SevenResourceProduction units={p.resource_units} compact/></article>)}</div>
    {actions.length > 0 ? <SevenActionPicker actions={actions} view={view} names={Object.fromEntries(identities.map(p=>[p.seat,p.name]))} disabled={disabled} onChoose={onChoose}/> : spectatorViews ? <SevenSpectatorHands views={spectatorViews} identities={identities}/> : <section className="seven-hand"><header><div><span>DRAFT HAND</span><h3>{zh ? `座位 ${viewer.seat + 1} 的当前手牌` : `Seat ${viewer.seat + 1} current hand`}</h3></div><b>{visibleHand.length || viewer.hand_count} {zh ? "张" : "cards"}</b></header><div>{visibleHand.map(card => <SevenCardTile key={card.id} card={card}/>)}{!visibleHand.length && <em>{zh ? "该手牌对当前观察者隐藏" : "This hand is hidden from the current viewer"}</em>}</div></section>}
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
    <details><summary>{zh?"查看图案线、墙面与地板":"View patterns, wall and floor"}</summary><div className="azul-player-board">{p.pattern_lines.map((line, row) => <div className="azul-player-board-row" key={line.line}>
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
    </div></details>
  </section>;
}

function AzulBoard({view, seat, actions = [], disabled, onChoose, onReset}: {view?: AzulView; seat:number; actions?: LegalAction[]; disabled: boolean; onChoose: (item: LegalAction)=>void; onReset?:()=>void}) {
  const lang=useLang(); const zh=lang==="zh";
  const [pick,setPick]=useState<{source:string; color:AzulColor}|null>(null);
  if (!view) return null;
  const own=view.players[seat];
  const choices=pick ? actions.filter(a=>a.action.source===pick.source && a.action.color===pick.color) : [];
  const supply=pick?.source==="center" ? view.center : view.factories.find(f=>f.id===pick?.source)?.tiles;
  const count=pick ? supply?.[pick.color] || 0 : 0;
  const marker=pick?.source==="center" && view.center_has_start_marker ? 1 : 0;
  const describe=(destination:string) => {
    const line=own.pattern_lines.find(l=>`pattern-line-${l.line}`===destination);
    const placed=line ? Math.min(count,line.capacity-line.count) : 0;
    const overflow=count-placed;
    const penalty=AZUL_FLOOR_PENALTIES.slice(own.floor.length,own.floor.length+overflow+marker).reduce((a,b)=>a+b,0);
    return zh ? `放入 ${placed} · 溢出 ${overflow}${marker?" + 起始标记":""} · 新增罚分 ${penalty}` : `Place ${placed} · overflow ${overflow}${marker?" + start marker":""} · extra penalty ${penalty}`;
  };
  const offer=(source:string,tiles:AzulCounts)=><div className="azul-source-colors">{AZUL_COLORS.filter(c=>tiles[c]>0).map(color=><button type="button" key={color} aria-label={`${source==="center"?(zh?"中央区":"Center"):`${zh?"工厂":"Factory"} ${source.replace("factory-","")}`} · ${AZUL_META[color][lang]} × ${tiles[color]}`} aria-pressed={pick?.source===source&&pick.color===color} disabled={disabled || !actions.some(a=>a.action.source===source&&a.action.color===color)} onClick={()=>{setPick({source,color}); onReset?.();}}><AzulTile color={color} count={tiles[color]}/><span>{AZUL_META[color][lang]}</span></button>)}</div>;
  return <div className="azul-board">
    <section className="azul-status"><h2>{zh?`第 ${view.round} 轮`:`Round ${view.round}`}</h2><p>{zh?"1 · 点选工厂或中央区的颜色　2 · 点选目标行　3 · 确认":"1 · Choose a source color　2 · Choose a row　3 · Confirm"}</p></section>
    <div className="azul-play-layout"><div><section className="azul-factories"><header><h3>{zh?"工厂展示区":"Factories"}</h3><small>{zh?`袋中 ${view.bag_count} · 盒盖 ${view.lid_count}`:`Bag ${view.bag_count} · Lid ${view.lid_count}`}</small></header><div>{view.factories.map((f,i)=><article key={f.id}><b>{i+1}</b>{offer(f.id,f.tiles)}</article>)}</div></section>
    <section className="azul-center"><header><h3>{zh?"中央区":"Center"}</h3></header>{view.center_has_start_marker&&<i className="azul-marker">1</i>}{offer("center",view.center)}</section></div>
    <section className="azul-destinations"><h3>{zh?"你的图案线与墙面":"Your pattern lines and wall"}</h3><p role="status">{pick?`${AZUL_META[pick.color][lang]} × ${count}`:(zh?"先点选一种颜色":"Choose a source color first")}</p>{own.pattern_lines.map((line,row)=>{const a=choices.find(a=>a.action.destination===`pattern-line-${line.line}`);return <div className="azul-target-row" key={line.line}><button type="button" disabled={disabled||!a} onClick={()=>a&&onChoose(a)} aria-label={`${zh?"图案线":"Pattern line"} ${line.line} · ${describe(`pattern-line-${line.line}`)}`}><b>{line.line}</b><span className="azul-pattern-line">{Array.from({length:line.capacity},(_,i)=>line.color&&i<line.count?<AzulTile key={i} color={line.color}/>:<i className="azul-tile empty" key={i}/>)}</span><small>{pick?describe(`pattern-line-${line.line}`):`${line.count}/${line.capacity}`}</small></button><span className="azul-wall-row">{own.wall[row].map((cell,i)=><i key={i} className={`azul-wall-cell azul-${cell.color} ${cell.occupied?"occupied":""}`}><span/></i>)}</span></div>;})}
    <button className="azul-floor-target" type="button" disabled={disabled||!choices.some(a=>a.action.destination==="floor")} onClick={()=>{const a=choices.find(a=>a.action.destination==="floor");if(a)onChoose(a);}}>{zh?"全部放到地板线":"All to floor"} · {describe("floor")}</button><div className="azul-floor-track">{AZUL_FLOOR_PENALTIES.map((n,i)=><span key={i} className={`azul-floor-slot ${own.floor[i]?"occupied":""}`}><small>{n}</small>{own.floor[i]==="start-player-marker"?<i className="azul-marker">1</i>:own.floor[i]?<AzulTile color={own.floor[i] as AzulColor}/>:<i className="azul-floor-empty"/>}</span>)}</div></section></div>
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
  if (event.type === "match_created") return zh ? "对局开始" : "Match started";
  if (event.type === "noble_acquired") {
    const who = event.player || names[event.seat ?? 0] || `${zh ? "座位" : "Seat"} ${(event.seat ?? 0) + 1}`;
    return zh ? `${who} 获得贵族 ${event.noble_id}` : `${who} gains noble ${event.noble_id}`;
  }
  if (event.type === "card_reserved") {
    const who = event.player || names[event.seat ?? 0] || `${zh ? "座位" : "Seat"} ${(event.seat ?? 0) + 1}`;
    const card = event.card_id ? String(event.card_id) : (zh ? "一张牌" : "a card");
    return zh ? `${who} 预留 ${card}` : `${who} reserves ${card}`;
  }
  if (!["decision", "turn", "action_accepted"].includes(event.type)) return event.type;
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
  if (["draft_tiles", "place_meeple", "skip_meeple"].includes(String(action.type)) || (action.type === "place_tile" && "x" in action)) return `${who}${zh ? "：" : ": "}${humanActionText(action, lang)}`;
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
      : Array.isArray(action.upgrades) ? (zh ? `，升级 ${(action.upgrades as SpiceName[]).map(value => `${SPICE_META[value]?.label[lang] || value} → ${SPICE_META[SPICE_ORDER[SPICE_ORDER.indexOf(value)+1]]?.label[lang] || "?"}`).join("；") || "0 级"}` : `, upgrade ${(action.upgrades as SpiceName[]).map(value => `${SPICE_META[value]?.label[lang] || value} → ${SPICE_META[SPICE_ORDER[SPICE_ORDER.indexOf(value)+1]]?.label[lang] || "?"}`).join("；")}`) : "";
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
  if (action.type === "take_tile") return zh ? `用${action.source === "bonus" ? "城堡奖励" : `骰子 ${Number(action.die_index) + 1}`}从 ${action.depot} 号仓库拿取 ${action.tile_id}${action.workers ? `（工人 ${action.workers}）` : ""}` : `Use ${action.source === "bonus" ? "castle bonus" : `die ${Number(action.die_index) + 1}`} to take ${action.tile_id} from depot ${action.depot}${action.workers ? ` (${action.workers} workers)` : ""}`;
  if (action.type === "place_tile" && "x" in action) return zh ? `地形放置到 (${action.x}, ${action.y})，旋转 ${Number(action.rotation) * 90}°` : `Place tile at (${action.x}, ${action.y}), rotated ${Number(action.rotation) * 90}°`;
  if (action.type === "place_meeple") return zh ? `派遣随从到 ${action.feature}` : `Place follower on ${action.feature}`;
  if (action.type === "skip_meeple") return zh ? "跳过随从放置" : "Skip follower placement";
  if (action.type === "place_tile") return zh ? `铺设 ${action.tile_id} 到 ${action.cell_id}${action.workers ? `（工人 ${action.workers}）` : ""}` : `Place ${action.tile_id} at ${action.cell_id}${action.workers ? ` (${action.workers} workers)` : ""}`;
  if (action.type === "sell_goods" || action.type === "sell_goods_effect") return zh ? `出售 ${action.goods_type} 号货物` : `Sell goods type ${action.goods_type}`;
  if (action.type === "take_workers") return zh ? `${action.source === "bonus" ? "用城堡奖励" : "用骰子"}获得工人` : `${action.source === "bonus" ? "Use castle bonus to" : "Use die to"} take workers`;
  if (action.type === "buy_tile") return zh ? `支付 ${action.silver} 银币和 ${action.workers} 工人购买 ${action.tile_id}` : `Pay ${action.silver} silver and ${action.workers} workers for ${action.tile_id}`;
  if (action.type === "choose_tile") return zh ? `选择 ${action.tile_id}（${action.depot} 号仓库）` : `Choose ${action.tile_id} from depot ${action.depot}`;
  if (action.type === "choose_goods") return zh ? `从 ${action.depot}${action.adjacent_depot ? `、${action.adjacent_depot}` : ""} 号仓库拿取 ${Array.isArray(action.goods_types) ? action.goods_types.join("、") : ""} 号货物` : `Take goods ${Array.isArray(action.goods_types) ? action.goods_types.join(", ") : ""} from depot ${action.depot}${action.adjacent_depot ? ` and ${action.adjacent_depot}` : ""}`;
  if (action.type === "place_tile_effect") return zh ? `市政厅铺设 ${action.tile_id} 到 ${action.cell_id}` : `Town hall places ${action.tile_id} at ${action.cell_id}`;
  if (action.type === "skip_effect") return zh ? "跳过可选即时效果" : "Skip optional immediate effect";
  if (action.type === "end_turn") return zh ? "结束本回合" : "End turn";
  if (action.type === "select_action" && action.action) return zh ? `选择 ${BL[String(action.action)] || String(action.action).toUpperCase()}行动` : `Choose ${BL[String(action.action)] || String(action.action)} action`;
  if (action.type === "select_action") return zh ? `使用 ${ARK_ACTION_LABELS[lang][String(action.action_card)] || action.action_card}，强度 ${action.strength}${action.x_tokens ? `（X +${action.x_tokens}）` : ""}` : `Use ${ARK_ACTION_LABELS[lang][String(action.action_card)] || action.action_card}, strength ${action.strength}${action.x_tokens ? ` (X +${action.x_tokens})` : ""}`;
  if (action.type === "start_action") {
    const allocations = Array.isArray(action.x_by_execution) ? action.x_by_execution.map(Number) : [0];
    const multiplier = Number(action.multiplier_tokens || 0);
    const card = String(action.action_card_id || "");
    return zh
      ? `使用${ARK_ACTION_LABELS[lang][card] || card}${multiplier ? `并消耗 X2 标记，连续执行两次（X 分配 ${allocations.join("/")}）` : "，执行一次"}`
      : `Use ${ARK_ACTION_LABELS[lang][card] || card}${multiplier ? ` with X2, performing it twice (X allocation ${allocations.join("/")})` : " once"}`;
  }
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
  if (action.type === "take_build_reward_card") return action.source === "deck" ? (zh ? "覆盖奖励：从牌库抽1张" : "Placement reward: draw 1 card from the deck") : (zh ? `覆盖奖励：拿取声望范围内的展示牌 ${action.card_id}` : `Placement reward: take ${action.card_id} from within Reputation range`);
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

function humanItemText(item: LegalAction, lang: Lang, brassView?: BrassView) {
  const text = humanActionText(item.action, lang, brassView);
  if (item.action.type === "advance_sponsors_break" && item.label) {
    const amounts = item.label.match(/Advance Break (\d+) and gain (\d+) money/);
    if (amounts) return lang === "zh" ? `推进休息 ${amounts[1]} 格，获得 ${amounts[2]} 金币` : item.label;
  }
  return text === String(item.action.type) ? item.label || text.replaceAll("_", " ") : text;
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
    choose_conservation_bonus: "选择保育奖励", take_map_card: "拿取地图奖励牌", take_build_reward_card: "拿取覆盖奖励牌", clever_action_card: "机敏奖励", finish_association_tasks: "结束协会任务",
    discard_wild: "弃置万能牌", scout_discard_extra: "侦察弃牌", develop_tiles: "选择研发板块",
    build_industry: "选择产业与城市", build_link: "铺设运河", select_network_count: "铁路数量",
    select_network_link: "选择铁路", take_resource: "选择资源来源", sell_industry: "出售产业",
    finish_sell: "结束出售", merchant_bonus_develop: "商人研发奖励", liquidate_industry: "变卖产业",
    play_merchant: "打出商人牌", acquire_merchant: "获取商人牌", claim_point: "完成订单", rest: "休息",
    draft_tiles: "选取并放置花砖",
    take_tile: "拿取板块", place_tile: "铺设板块", sell_goods: "出售货物", take_workers: "获得工人",
    buy_tile: "购买板块", choose_tile: "选择板块", choose_goods: "选择货物", sell_goods_effect: "建筑出售效果",
    place_tile_effect: "建筑铺设效果", skip_effect: "跳过即时效果", end_turn: "结束回合",
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
    choose_conservation_bonus: "Conservation bonus", take_map_card: "Map card reward", take_build_reward_card: "Placement card reward", clever_action_card: "Clever reward", finish_association_tasks: "End association tasks",
    discard_wild: "Discard wild card", scout_discard_extra: "Scout discard", develop_tiles: "Select develop tiles",
    build_industry: "Choose industry & city", build_link: "Build canal", select_network_count: "Rail count",
    select_network_link: "Choose rail link", take_resource: "Choose resource source", sell_industry: "Sell industry",
    finish_sell: "End sell", merchant_bonus_develop: "Merchant develop bonus", liquidate_industry: "Liquidate industry",
    play_merchant: "Play merchant card", acquire_merchant: "Acquire merchant card", claim_point: "Complete order", rest: "Rest",
    draft_tiles: "Draft and place tiles",
    take_tile: "Take tile", place_tile: "Place tile", sell_goods: "Sell goods", take_workers: "Take workers",
    buy_tile: "Buy tile", choose_tile: "Choose tile", choose_goods: "Choose goods", sell_goods_effect: "Building sell effect",
    place_tile_effect: "Building place effect", skip_effect: "Skip immediate effect", end_turn: "End turn",
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

const ARK_TABLE_ACTION_TYPES = new Set([
  "choose_initial_hand", "select_action", "start_action", "take_x_token", "take_x_token_action", "cancel_action", "draw_cards", "snap_card", "discard_card",
  "place_building", "play_animal", "finish_action", "association_task", "make_donation",
  "perform_association_task", "make_association_donation", "finish_association_action",
  "upgrade_association_reward_card",
  "place_unique_sponsor_building",
  "finish_association_tasks", "advance_break", "play_sponsor", "break_discard",
  "resolve_semantic_choice",
  "choose_conservation_bonus", "upgrade_action_card", "keep_final_card", "take_map_card",
  "take_build_reward_card",
  "clever_action_card", "begin_cards_draw", "draw_cards_action_card", "snap_cards_action_card", "discard_cards_action_card",
  "begin_animals_action", "select_animal_card", "play_selected_animal", "play_sponsor_card", "advance_sponsors_break",
  "finish_sponsors_action", "finish_animals_action", "finish_build_action",
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

function SplendorTable({actions, view, seat, disabled, selected, issue, onSelect, onSubmit, activeName, lastMove}: {
  actions: LegalAction[]; view: View; seat: number; disabled: boolean; selected: LegalAction | null; issue?: string;
  onSelect: (item: LegalAction | null, requirement?: string) => void; onSubmit: (item: LegalAction) => void;
  activeName: string; lastMove: string;
}) {
  const lang = useLang(); const zh = lang === "zh";
  const [selection, setSelection] = useState<"take" | LegalAction | null>(null);
  const [take, setTake] = useState<Record<string, number>>({});
  const [returned, setReturned] = useState<Record<string, number>>({});
  const p = view.players[seat];
  const takeActions = actions.filter(item => item.action.type === "take_tokens");
  const candidates = selection ? selectionCandidates(actions, selection, take) : [];
  const returnRequired = tokenTotal(counts(candidates[0]?.action.return));
  const remaining = returnRequired - tokenTotal(returned);
  const reservation = selection !== null && selection !== "take" && String(selection.action.type).startsWith("reserve_");
  const gained = selection === "take" ? take : reservation ? {gold: view.bank.gold > 0 ? 1 : 0} : {};
  const afterTake = Object.fromEntries(GEM_ORDER.map(color => [color, (p.tokens[color] ?? 0) + (gained[color] ?? 0)]));
  const yourTurn = actions.length > 0;
  const takeHint = zh ? "取 3 种各 1 颗，或同色 2 颗（库存 ≥4）；选好后确认。" : "Take 3 different colors, or 2 of one color (supply ≥4), then confirm.";
  const paymentChoices = selection && selection !== "take" && String(selection.action.type).startsWith("buy_")
    ? actions.filter(item => item.action.type === selection.action.type && item.action.card_id === selection.action.card_id) : [];

  function clear() { setSelection(null); setTake({}); setReturned({}); onSelect(null); }
  function updateSelection(nextSelection: "take" | LegalAction, nextTake: Record<string, number>, nextReturn: Record<string, number>) {
    setSelection(nextSelection); setTake(nextTake); setReturned(nextReturn);
    const choices = selectionCandidates(actions, nextSelection, nextTake);
    onSelect(resolveSelection(choices, nextReturn));
  }
  function chooseAction(item: LegalAction) {
    if (String(item.action.type).startsWith("reserve_")) updateSelection(item, {}, {});
    else { setSelection(item); setTake({}); setReturned({}); onSelect(item); }
  }
  function cardName(card: Card) { return zh ? `${card.tier}阶${GEM_META[card.bonus].label[lang]}牌 · ${card.points}分` : `Tier ${card.tier} ${GEM_META[card.bonus].label[lang]} · ${card.points} pts`; }
  function preview(item: LegalAction) {
    const kind = String(item.action.type);
    const card = findActionCard(item.action, view);
    if (card) return `${kind.startsWith("buy_") ? (zh ? "购买" : "Buy ") : (zh ? "预留" : "Reserve ")}${cardName(card)}`;
    if (kind === "reserve_deck") return zh ? `从 ${item.action.tier} 阶牌堆预留` : `Reserve from tier ${item.action.tier}`;
    if (kind === "choose_noble") return zh ? "邀请所选贵族 · +3 分" : "Invite selected noble · +3 pts";
    return humanActionText(item.action, lang);
  }
  function renderCard(card: Card, index: number, reserved = false) {
    const buys = actions.filter(item => item.action.type === (reserved ? "buy_reserved" : "buy_visible") && item.action.card_id === card.id);
    const buy = [...buys].sort((a, b) => (counts(a.action.payment).gold ?? 0) - (counts(b.action.payment).gold ?? 0))[0];
    const reserve = actions.find(item => item.action.type === "reserve_visible" && item.action.card_id === card.id);
    const missing = Object.fromEntries(BONUS_ORDER.map(c => [c, Math.max(0, (card.cost[c] ?? 0) - (p.bonuses[c] ?? 0) - (p.tokens[c] ?? 0))]));
    const shortfall = Math.max(0, tokenTotal(missing) - (p.tokens.gold ?? 0));
    const label = `${cardName(card)} (${index + 1})`;
    const picked = selection !== "take" && selection?.action.card_id === card.id;
    return <article key={card.id} className={`sp-card card-${card.bonus} ${picked ? "is-selected" : ""} ${shortfall === 0 ? "is-affordable" : ""}`} aria-label={label}>
      <header><strong>{card.points}<small>{zh ? "分" : "pts"}</small></strong><span title={zh ? `永久${GEM_META[card.bonus].label[lang]}折扣 +1` : `Permanent ${GEM_META[card.bonus].label[lang]} discount +1`}>{GEM_META[card.bonus].mark}<small>+1</small></span></header>
      <div className="sp-cost" aria-label={zh ? "原价" : "Printed cost"}><Cost cost={card.cost}/></div>
      <small className="sp-affordability" title={zh ? `已计入永久折扣及黄金；缺少颜色：${tokenText(missing, lang) || "无"}` : `After discounts and gold; missing colors: ${tokenText(missing, lang) || "none"}`}>
        {shortfall ? (zh ? `还差 ${shortfall} 颗` : `${shortfall} gems short`) : (zh ? "可以购买" : "Affordable")}
      </small>
      {yourTurn && <div className="sp-card-actions">
        <button type="button" disabled={disabled || !buy} aria-label={`${zh ? "购买" : "Buy "}${label}`} aria-pressed={picked && String(selection?.action.type).startsWith("buy_")} onClick={() => chooseAction(buy)}>{zh ? "购买" : "Buy"}</button>
        {!reserved && <button type="button" disabled={disabled || !reserve} title={p.reserved_count >= 3 ? (zh ? "预留已达上限 3 张" : "Reserve limit: 3") : (zh ? "预留并获得 1 黄金（有库存时）" : "Reserve and gain 1 gold if available")} aria-label={`${zh ? "预留" : "Reserve "}${label}`} aria-pressed={picked && reservation} onClick={() => chooseAction(reserve!)}>{zh ? "预留" : "Reserve"}</button>}
      </div>}
    </article>;
  }

  return <div className="sp-table">
    <div className={`sp-turn-status ${yourTurn ? "is-your-turn" : ""}`} role="status"><strong>{yourTurn ? (zh ? "轮到你了" : "Your turn") : view.status === "finished" ? (zh ? "对局结束" : "Game over") : (zh ? `${activeName} 行动中` : `${activeName}'s turn`)}</strong><span>{zh ? "目标 15 分 · 宝石上限 10" : "Target 15 pts · Gem limit 10"}</span>
      <details className="sp-rules"><summary>{zh ? "玩法" : "Rules"}</summary><p>{zh ? "每回合选择拿宝石、购买或预留一张牌。牌右上角是永久折扣；左上角是分数；底部色块是原价。黄金可替代任意颜色，预留上限 3 张。只有 1–2 种颜色有库存时可各拿 1 颗。贵族只检查永久折扣，满足条件得 3 分。有人达到 15 分后，完成该轮；同分时购牌较少者胜。" : "Take gems, buy or reserve one card per turn. Top right: permanent discount; top left: points; bottom: printed cost. Gold is wild; reserve up to 3 cards. If only 1–2 colors remain, take one of each. Nobles require permanent discounts and award 3 points. At 15 points, finish the round; fewer purchased cards break ties."}</p></details>
    </div>
    <section className="sp-bank" aria-label={zh ? "宝石银行" : "Gem bank"}>
      <header><h2>{zh ? "宝石银行" : "Gem bank"}</h2><small>{yourTurn ? takeHint : (zh ? "色块数字为剩余库存" : "Numbers show remaining supply")}</small></header>
      <div className="sp-bank-gems">{GEM_ORDER.map(color => {
        const amount = selection === "take" ? take[color] ?? 0 : 0;
        const label = GEM_META[color].label[lang];
        return <div className={`sp-bank-gem ${amount ? "is-selected" : ""}`} key={color}>
          <button type="button" disabled={disabled || !canAddToken(takeActions, "take", selection === "take" ? take : {}, color)} aria-label={zh ? `拿取${label}，已选 ${amount} 颗` : `Take ${label}, ${amount} selected`} onClick={() => updateSelection("take", {...(selection === "take" ? take : {}), [color]: amount + 1}, {})}><Gem color={color} value={view.bank[color]}/><span>{label}</span></button>
          {yourTurn && color !== "gold" ? <div><button type="button" disabled={disabled || !amount} aria-label={zh ? `少取一颗${label}` : `Remove one ${label}`} onClick={() => updateSelection("take", {...take, [color]: amount - 1}, {})}>−</button><span>{zh ? "选" : "Pick"} <b>{amount}</b></span></div> : <small>{color === "gold" ? (zh ? "预留时获得" : "Via reserve") : ""}</small>}
        </div>;
      })}</div>
    </section>
    <section className="sp-nobles" aria-label={zh ? "贵族与折扣进度" : "Nobles and discount progress"}>
      <h2>{zh ? "贵族" : "Nobles"}<small>{zh ? "永久折扣 / 要求" : "Discounts / required"}</small></h2>
      <div>{view.available_nobles.map((n, index) => {
        const choice = actions.find(item => item.action.type === "choose_noble" && item.action.noble_id === n.id);
        return <article key={n.id} className={selected?.action.noble_id === n.id ? "is-selected" : ""}><strong>3<small>{zh ? "分" : "pts"}</small></strong><div>{BONUS_ORDER.filter(c => n.required[c]).map(c => <span key={c} className={`sp-noble-requirement ${(p.bonuses[c] ?? 0) >= n.required[c] ? "met" : ""}`} title={GEM_META[c].label[lang]}><Gem color={c} value={`${Math.min(p.bonuses[c] ?? 0, n.required[c])}/${n.required[c]}`} compact/></span>)}</div>{choice && <button disabled={disabled} onClick={() => chooseAction(choice)}>{zh ? `选择贵族 ${index + 1}` : `Choose noble ${index + 1}`}</button>}</article>;
      })}</div>
    </section>
    <section className="sp-market" aria-label={zh ? "发展牌市场" : "Development market"}>{[3,2,1].map(tier => {
      const reserveDeck = actions.find(item => item.action.type === "reserve_deck" && Number(item.action.tier) === tier);
      return <div className="sp-tier" key={tier}><div className="sp-tier-label"><strong>{zh ? `${tier} 阶` : `Tier ${tier}`}</strong><span>{view.deck_counts[String(tier)]} {zh ? "张" : "left"}</span>{yourTurn && <button disabled={disabled || !reserveDeck} aria-pressed={selection !== "take" && selection?.action.type === "reserve_deck" && Number(selection.action.tier) === tier} onClick={() => chooseAction(reserveDeck!)}>{zh ? "盲抽预留" : "Reserve deck"}</button>}</div><div className="sp-market-cards">{view.market[String(tier)].map((card, i) => renderCard(card, i))}</div></div>;
    })}</section>
    {p.reserved_count > 0 && <section className="sp-reserved"><h2>{zh ? "你的预留" : "Your reserves"} <small>{p.reserved_count}/3</small></h2><div>{p.reserved.map((card, i) => "hidden" in card ? <span key={i}>?</span> : renderCard(card, i, true))}</div></section>}
    {yourTurn && <section className="sp-confirm" aria-label={zh ? "行动预览与确认" : "Action preview and confirmation"}>
      {returnRequired > 0 && <div className="sp-return"><strong>{zh ? `退回宝石 · 还需 ${remaining} 颗` : `Return gems · ${remaining} remaining`}</strong><span>{zh ? `拿取后 ${tokenTotal(afterTake)} / 上限 10，可退回刚拿到的宝石或黄金。` : `${tokenTotal(afterTake)} held / limit 10. You may return new gems or gold.`}</span><div>{GEM_ORDER.filter(c => afterTake[c] > 0).map(color => <div key={color}><button disabled={disabled || !canAddToken(candidates, "return", returned, color)} aria-label={zh ? `退回${GEM_META[color].label[lang]}，已选 ${returned[color] ?? 0} 颗` : `Return ${GEM_META[color].label[lang]}, ${returned[color] ?? 0} selected`} onClick={() => updateSelection(selection!, take, {...returned, [color]: (returned[color] ?? 0) + 1})}><Gem color={color} value={afterTake[color] - (returned[color] ?? 0)} compact/><span>−{returned[color] ?? 0}</span></button><button disabled={disabled || !returned[color]} aria-label={zh ? `少退一颗${GEM_META[color].label[lang]}` : `Return one fewer ${GEM_META[color].label[lang]}`} onClick={() => updateSelection(selection!, take, {...returned, [color]: returned[color] - 1})}>↶</button></div>)}</div></div>}
      {paymentChoices.length > 1 && <label className="sp-payment">{zh ? "支付方式" : "Payment"}<select disabled={disabled} value={selected?.id || ""} onChange={e => { const choice = paymentChoices.find(item => item.id === e.target.value); if (choice) chooseAction(choice); }}>{paymentChoices.map(item => <option key={item.id} value={item.id}>{tokenText(counts(item.action.payment), lang) || (zh ? "免费" : "Free")}</option>)}</select></label>}
      <div className="sp-confirm-row"><div role="status"><strong>{selected ? preview(selected) : reservation ? preview(selection!) : selection === "take" ? (zh ? `已选 ${tokenTotal(take)} 颗 · 继续选择` : `${tokenTotal(take)} selected · keep choosing`) : (zh ? "点击银行拿宝石，或在牌上购买 / 预留" : "Choose gems from the bank, or buy / reserve a card")}</strong><small>{selected?.action.payment ? `${zh ? "支付：" : "Pay: "}${tokenText(counts(selected.action.payment), lang) || (zh ? "免费" : "Free")}` : reservation ? (view.bank.gold ? (zh ? "获得 1 颗黄金" : "Gain 1 gold") : (zh ? "黄金已用尽，本次无黄金" : "No gold left in the bank")) : (zh ? "确认前可修改选择" : "You can change your selection before confirming")}{selected && tokenTotal(counts(selected.action.return)) > 0 ? ` · ${zh ? "退回：" : "Return: "}${tokenText(counts(selected.action.return), lang)}` : ""}</small></div><button className="sp-clear" disabled={disabled || !selection} onClick={clear}>{zh ? "清空" : "Clear"}</button><button className="sp-submit" disabled={disabled || !selected} onClick={() => selected && onSubmit(selected)}>{disabled ? (zh ? "等待中…" : "Waiting…") : (zh ? "确认行动" : "Confirm move")}</button></div>
      {actions.filter(item => item.action.type === "pass").map(item => <button key={item.id} disabled={disabled} onClick={() => chooseAction(item)}>{zh ? "无可用行动，跳过" : "No moves available · pass"}</button>)}
      {issue && <p role="alert">{issue}</p>}
    </section>}
    {lastMove && <p className="sp-last-move"><b>{zh ? "最近行动" : "Last move"}</b> {lastMove}</p>}
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
const BRASS_MAP_POINTS: Record<string, BrassMapPoint> = {
  warrington: {x: 135, y: 45, kind: "merchant"},
  stoke_on_trent: {x: 245, y: 140, kind: "industry"},
  stone: {x: 205, y: 245, kind: "industry"},
  leek: {x: 455, y: 60, kind: "industry"},
  belper: {x: 650, y: 72, kind: "industry"},
  nottingham: {x: 870, y: 112, kind: "merchant"},
  uttoxeter: {x: 465, y: 210, kind: "industry"},
  derby: {x: 690, y: 225, kind: "industry"},
  stafford: {x: 315, y: 335, kind: "industry"},
  burton_on_trent: {x: 555, y: 330, kind: "industry"},
  farm_brewery_cannock: {x: 190, y: 410, kind: "farm"},
  cannock: {x: 390, y: 420, kind: "industry"},
  tamworth: {x: 670, y: 420, kind: "industry"},
  shrewsbury: {x: 75, y: 505, kind: "merchant"},
  coalbrookdale: {x: 245, y: 520, kind: "industry"},
  wolverhampton: {x: 390, y: 520, kind: "industry"},
  walsall: {x: 525, y: 520, kind: "industry"},
  nuneaton: {x: 745, y: 540, kind: "industry"},
  dudley: {x: 430, y: 625, kind: "industry"},
  birmingham: {x: 590, y: 645, kind: "industry"},
  coventry: {x: 775, y: 665, kind: "industry"},
  farm_brewery_kidderminster_worcester: {x: 170, y: 720, kind: "farm"},
  kidderminster: {x: 300, y: 725, kind: "industry"},
  redditch: {x: 595, y: 770, kind: "industry"},
  oxford: {x: 825, y: 795, kind: "merchant"},
  worcester: {x: 335, y: 845, kind: "industry"},
  gloucester: {x: 570, y: 875, kind: "merchant"},
};
const BRASS_SEAT_COLORS = ["#c9483d", "#d9a52f", "#7650a0", "#5a6d78"];

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

function BrassLiveMap({view, players, humanActions = [], disabled, submitting, selectedActionId, onChoose}: {
  view: BrassView; players: Snapshot["players"]; humanActions?: LegalAction[];
  disabled: boolean; submitting: string; selectedActionId: string; onChoose?: (item: LegalAction) => void;
}) {
  const lang = useLang(); const zh = lang === "zh";
  const [zoom, setZoom] = useState(1);
  const [expanded, setExpanded] = useState(false);
  const [choiceTarget, setChoiceTarget] = useState<{label: string; actions: LegalAction[]} | null>(null);
  useEffect(() => {
    if (!expanded) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setExpanded(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [expanded]);
  const choiceIsCurrent = choiceTarget?.actions.every(action => humanActions.some(item => item.id === action.id));
  const currentChoice = choiceIsCurrent ? choiceTarget : null;
  const industryById = new Map(view.board.industries.map(industry => [industry.id, industry]));
  const linksByConnection = new Map(view.board.links.map(link => [link.connection_id, link]));
  const merchantById = new Map(view.board.merchant_locations.map(merchant => [merchant.id, merchant]));
  const targetActions = (values: unknown[]) => {
    const keys = values.filter((value): value is string => typeof value === "string");
    return humanActions.filter(item => keys.includes(String(item.action.slot_id || "")) || keys.includes(String(item.action.industry_id || "")) || keys.includes(String(item.action.source_id || "")));
  };
  const choose = (label: string, actions: LegalAction[]) => {
    if (!actions.length || disabled || !onChoose) return;
    if (actions.length === 1) onChoose(actions[0]);
    else setChoiceTarget({label, actions});
  };
  return <section className={`brass-live-map ${expanded ? "is-expanded" : ""}`} aria-label={zh ? "伯明翰实时互动地图" : "Brass Birmingham live interactive map"}>
    <header><div><span>LIVE NETWORK MAP</span><h3>{zh ? "实时产业与交通地图" : "Live industry & network map"}</h3></div><div className="brass-map-tools"><i>{humanActions.length ? (zh ? "可点击高亮目标" : "Highlighted targets are clickable") : (zh ? "实时观战" : "Live spectator")}</i><button className="map-focus" onClick={() => setExpanded(value => !value)} aria-label={expanded ? (zh ? "退出专注地图" : "Exit map focus") : (zh ? "专注地图" : "Focus map")}>{expanded ? "×" : "⛶"}</button><button onClick={() => setZoom(value => Math.max(.82, value - .14))} aria-label={zh ? "缩小地图" : "Zoom out"}>−</button><b>{Math.round(zoom * 100)}%</b><button onClick={() => setZoom(value => Math.min(1.55, value + .14))} aria-label={zh ? "放大地图" : "Zoom in"}>＋</button></div></header>
    <div className="brass-map-legend"><span><i className="legend-open"/>{zh ? "可用线路" : "Available"}</span>{players.map(player => <span key={player.seat}><i style={{background: BRASS_SEAT_COLORS[player.seat]}}/>{player.name}</span>)}<span><i className="legend-action"/>{zh ? "本步合法目标" : "Legal target"}</span></div>
    <div className="brass-map-viewport">
      <div className="brass-map-stage" style={{width: `${zoom * 100}%`}}>
        <svg className="brass-route-layer" viewBox="0 0 1000 920" role="img" aria-label={zh ? "运河与铁路连接" : "Canal and rail connections"}>
          <defs><filter id="routeGlow"><feGaussianBlur stdDeviation="4" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
          {view.board.connection_spaces.map(connection => {
            const points = connection.endpoints.map(endpoint => BRASS_MAP_POINTS[endpoint]).filter(Boolean);
            if (points.length < 2) return null;
            const built = linksByConnection.get(connection.id);
            const actions = humanActions.filter(item => item.action.connection_id === connection.id);
            const eraActive = connection.available_eras.includes(view.era);
            const hub = points.length === 2 ? null : {x: points.reduce((sum, point) => sum + point.x, 0) / points.length, y: points.reduce((sum, point) => sum + point.y, 0) / points.length};
            const segments = hub ? points.map(point => [point, hub]) : [[points[0], points[1]]];
            const label = connection.endpoints.map(endpoint => brassLocationLabel(endpoint, lang)).join(" ↔ ");
            return <g key={connection.id} className={`brass-route ${built ? `built seat-${built.owner}` : eraActive ? "era-active" : "era-inactive"} ${actions.length ? "actionable" : ""} ${actions.some(item => item.id === selectedActionId) ? "selected" : ""}`} style={built ? {"--route-color": BRASS_SEAT_COLORS[built.owner]} as CSSProperties : undefined}>
              {segments.map(([start, end], index) => <g key={index}><line className="route-visible" x1={start.x} y1={start.y} x2={end.x} y2={end.y}/><line className="route-hit" x1={start.x} y1={start.y} x2={end.x} y2={end.y} tabIndex={actions.length ? 0 : -1} role={actions.length ? "button" : undefined} aria-label={actions.length ? `${label} · ${zh ? "选择线路" : "choose route"}` : label} onClick={() => choose(label, actions)} onKeyDown={event => {if ((event.key === "Enter" || event.key === " ") && actions.length) choose(label, actions);}}/></g>)}
            </g>;
          })}
        </svg>
        {view.board.locations.map(location => {
          const point = BRASS_MAP_POINTS[location.id]; if (!point) return null;
          return <article key={location.id} className={`brass-map-city kind-${point.kind}`} style={{left: `${point.x / 10}%`, top: `${point.y / 9.2}%`}}>
            <h4>{brassLocationLabel(location.id, lang)}</h4><div className="brass-map-slots">{location.industry_slots.map(slot => {
              const tile = slot.industry_id ? industryById.get(slot.industry_id) : undefined;
              const actions = targetActions([slot.id, tile?.id]);
              const label = tile ? `${BRASS_INDUSTRY_LABELS[lang][tile.industry]} L${tile.level}` : slot.accepts.map(kind => BRASS_INDUSTRY_LABELS[lang][kind]).join("/");
              return <button key={slot.id} className={`${tile ? `occupied seat-${tile.owner}` : "vacant"} ${actions.length ? "actionable" : ""} ${actions.some(item => item.id === selectedActionId) ? "selected" : ""}`} disabled={!actions.length || disabled} onClick={() => choose(`${brassLocationLabel(location.id, lang)} · ${label}`, actions)} title={`${label}${actions.length ? ` · ${zh ? "点击选择" : "click to choose"}` : ""}`}>
                {tile ? <><i className={`industry-mark industry-${tile.industry}`}/><b>L{tile.level}</b><small>{tile.flipped ? "✓" : tile.resources ? `×${tile.resources}` : "○"}</small></> : <>{slot.accepts.map(kind => <i key={kind} className={`industry-mark industry-${kind}`}/>)}</>}
              </button>;
            })}</div>
          </article>;
        })}
        {Object.entries(BRASS_MAP_POINTS).filter(([, point]) => point.kind === "merchant").map(([locationId, point]) => {
          const merchant = merchantById.get(locationId);
          return <article key={locationId} className={`brass-map-merchant ${merchant ? "active" : "inactive"}`} style={{left: `${point.x / 10}%`, top: `${point.y / 9.2}%`}}><h4>{brassLocationLabel(locationId, lang)}</h4><div>{merchant ? merchant.slots.map(slot => {const actions = targetActions([slot.id]); return <button key={slot.id} className={`${actions.length ? "actionable" : ""} ${actions.some(item => item.id === selectedActionId) ? "selected" : ""}`} disabled={!actions.length || disabled} onClick={() => choose(`${brassLocationLabel(locationId, lang)} · ${slot.buys}`, actions)}><span>{slot.buys === "any" ? "◆" : slot.buys === "blank" ? "—" : <i className={`industry-mark industry-${slot.buys}`}/>}</span><b>{slot.beer ? "🍺" : "·"}</b></button>;}) : <small>{zh ? "本人数无商人牌" : "No merchant tile"}</small>}</div></article>;
        })}
      </div>
    </div>
    {currentChoice && <div className="brass-map-choice"><header><div><span>{zh ? "地图目标" : "Map target"}</span><b>{currentChoice.label}</b></div><button onClick={() => setChoiceTarget(null)}>×</button></header><div>{currentChoice.actions.map(item => <button key={item.id} className={selectedActionId === item.id ? "selected" : ""} aria-pressed={selectedActionId === item.id} disabled={disabled} onClick={() => onChoose?.(item)}><strong>{humanActionText(item.action, lang, view)}</strong>{submitting === item.id && <small>{zh ? "提交中…" : "Submitting…"}</small>}</button>)}</div></div>}
  </section>;
}

function BrassBoard({view, players, humanActions, disabled, submitting, selectedActionId, onChoose}: {view?: BrassView; players: Snapshot["players"]; humanActions?: LegalAction[]; disabled?: boolean; submitting?: string; selectedActionId?: string; onChoose?: (item: LegalAction) => void}) {
  const lang = useLang(); const t = makeT(lang); const zh = lang === "zh";
  if (!view) return null;
  return <div className="brass-board">
    <section className="brass-status"><div><span>BRASS · BIRMINGHAM</span><h2>{view.era === "canal" ? t("brass_canal") : t("brass_rail")} · {zh ? `第 ${view.round} 轮` : `Round ${view.round}`}</h2></div><div><small>CURRENT DECISION</small><strong>{zh ? ({choose_action:"选择行动",choose_discard:"选择弃牌",build:"选择产业位置",network:"铺设网络",develop:"研发",sell:"出售产业",resource:"选择资源来源"} as Record<string,string>)[view.turn.decision] || view.turn.decision.replaceAll("_", " ") : view.turn.decision.replaceAll("_", " ")}</strong><b>{view.turn.actions_remaining}/{view.turn.actions_total} {t("brass_actions")}</b></div><code>{view.rules_version}</code></section>
    <section className="brass-economy-board"><BrassMarket label={t("coal_market")} market={view.markets.coal} resource="coal"/><BrassMarket label={t("iron_market")} market={view.markets.iron} resource="iron"/><div className="brass-deck"><span>{t("deck_label")}</span><strong>{view.deck_count}</strong><small>{t("turn_order")} · {view.turn_order.map(seat => players[seat]?.name || seat + 1).join(" → ")}</small></div></section>
    {Boolean(humanActions?.length) && <section className="brass-command-bar" aria-label={zh?"当前行动选项":"Current action options"}>{Object.entries(groupActions(humanActions || [])).map(([kind,items])=><ActionChoices key={kind} actions={items} label={ACTION_GROUPS[lang][kind] || kind} describe={a=>humanActionText(a.action,lang,view)} lang={lang} disabled={disabled} onChoose={a=>onChoose?.(a)}/>)}</section>}
    <BrassLiveMap view={view} players={players} humanActions={humanActions} disabled={Boolean(disabled)} submitting={submitting || ""} selectedActionId={selectedActionId || ""} onChoose={onChoose}/>
  </div>;
}


function ArkNovaBoard({view, players, legalActions, submitting, selectedActionId, onChoose}: {
  view?: ArkView; players: Snapshot["players"]; legalActions: LegalAction[]; submitting: string;
  selectedActionId: string;
  onChoose: (item: LegalAction) => void;
}) {
  const lang = useLang();
  return <ArkNovaTable view={view} identities={players} lang={lang} legalActions={legalActions} submitting={submitting} selectedActionId={selectedActionId} onChoose={onChoose}/>;
}

export default function Home() {
  if (process.env.NEXT_PUBLIC_PAGES_RESULTS === "true") return <ArenaPage/>;
  return <LocalHome/>;
}

function LocalHome() {
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
  const [showMatchLog, setShowMatchLog] = useState(false);
  const [agentOutputCollapsed, setAgentOutputCollapsed] = useState(false);
  const [actionLogCollapsed, setActionLogCollapsed] = useState(false);
  const [players, setPlayers] = useState<PlayerForm[]>([
    deepseekHarnessPlayer(1, "opencode"),
    codexHarnessPlayer(2),
  ]);
  const [seed, setSeed] = useState("42");
  const [speed, setSpeed] = useState(650);
  const [soloStartingAppeal, setSoloStartingAppeal] = useState<0 | 10 | 20>(20);
  const [wingspanGoalBoard, setWingspanGoalBoard] = useState("green");
  const [harmoniesSide, setHarmoniesSide] = useState<"A" | "B">("A");
  const [harmoniesSpirits, setHarmoniesSpirits] = useState(false);
  const [arkMap, setArkMap] = useState<ArkMapId>("map-0");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [timeline, setTimeline] = useState<Timeline[]>([]);
  const [chat, setChat] = useState<ChatTurn[]>([]);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [controlling, setControlling] = useState(false);
  const [submittingAction, setSubmittingAction] = useState("");
  const [humanActionState, setHumanActionState] = useState<{turnKey: string; selected: LegalAction | null; requirement: string; issue: string} | null>(null);
  const [tables, setTables] = useState<TableSummary[]>([]);
  const [watchId, setWatchId] = useState("");
  const sourceRef = useRef<EventSource | null>(null);
  const finalBoardRef = useRef<HTMLElement | null>(null);
  const watchingRef = useRef(false);
  const humanTurnKey = snapshot?.human_turn ? `${snapshot.match_id}:${snapshot.human_turn.seat}:${snapshot.human_turn.version}` : "";
  const currentHumanActionState = humanActionState?.turnKey === humanTurnKey ? humanActionState : null;
  const selectedHumanAction = currentHumanActionState?.selected ?? null;
  const humanSeat = snapshot?.human_turn?.seat ?? snapshot?.players.find(player => player.backend === "human")?.seat ?? 0;
  const viewer = snapshot?.views[humanSeat];
  const splendorView = snapshot?.game === "splendor" ? viewer as View : undefined;
  const carcassonneView = snapshot?.game === "carcassonne" ? viewer as CarcassonneView : undefined;
  const wingspanView = snapshot?.game === "wingspan" ? viewer as WingspanView : undefined;
  const harmoniesView = snapshot?.game === "harmonies" ? viewer as HarmoniesView : undefined;
  const azulView = snapshot?.game === "azul" ? viewer as AzulView : undefined;
  const arkView = snapshot?.game === "ark_nova"
    ? (snapshot.spectator_view ?? viewer) as ArkView : undefined;
  const brassView = snapshot?.game === "brass_birmingham" ? viewer as BrassView : undefined;
  const burgundyView = snapshot?.game === "castles_of_burgundy" ? viewer as BurgundyView : undefined;
  const centuryView = snapshot?.game === "century_spice_road" ? viewer as CenturyView : undefined;
  const sevenView = snapshot?.game === "seven_wonders" ? viewer as SevenView : undefined;
  const sevenSpectatorViews = snapshot?.game === "seven_wonders" && !snapshot.players.some(player => player.backend === "human")
    ? snapshot.views as SevenView[] : undefined;
  const isArkTableAction = (item: LegalAction) => ARK_TABLE_ACTION_TYPES.has(String(item.action.type));
  const arkFallbackActions = snapshot?.game === "ark_nova" ? (snapshot.human_turn?.legal_actions || []).filter(item => !isArkTableAction(item)) : [];
  const maxPlayers = game === "seven_wonders" ? 7 : ["century_spice_road", "wingspan", "carcassonne"].includes(game) ? 5 : 4;
  const minPlayers = ["ark_nova", "harmonies"].includes(game) ? 1 : game === "seven_wonders" ? 3 : 2;
  const names = useMemo(() => Object.fromEntries((snapshot?.players || []).map(p => [p.seat, p.name])), [snapshot]);
  const spectator = snapshot?.mode === "spectator";
  const filteredTables = useMemo(() => {
    const query = watchId.trim().toLocaleLowerCase(lang === "zh" ? "zh-CN" : "en");
    if (!query) return tables;
    return tables.filter(table => {
      const gameName = GAME_COPY[table.game]?.name[lang] || table.game;
      const status = table.status === "finished" ? t("s_finished") : t("s_active");
      return [table.match_id, table.game, gameName, status, ...table.players.map(player => player.name)]
        .some(value => String(value || "").toLocaleLowerCase(lang === "zh" ? "zh-CN" : "en").includes(query));
    });
  }, [lang, tables, t, watchId]);
  const watchTarget = useMemo(() => {
    const query = watchId.trim();
    const exact = tables.find(table => table.match_id.toLowerCase() === query.toLowerCase());
    if (exact) return exact.match_id;
    if (filteredTables.length === 1) return filteredTables[0].match_id;
    return /^[a-f\d]{8,}$/i.test(query) ? query : "";
  }, [filteredTables, tables, watchId]);

  async function watchMatch(matchId: string) {
    const id = matchId.trim().toLowerCase();
    if (!id || watchingRef.current && snapshot?.match_id === id) return;
    watchingRef.current = true;
    setStarting(true); setError(""); setTimeline([]); setChat([]); sourceRef.current?.close();
    try {
      const response = await fetch(api(`/api/matches/${id}`));
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || t("err_watch"));
      attachMatch(data as Snapshot, true);
    } catch (e) {
      watchingRef.current = false;
      setError(e instanceof Error ? e.message : String(e));
    } finally { setStarting(false); }
  }

  useEffect(() => {
    if (snapshot) return;
    const controller = new AbortController();
    function loadTables() {
      fetch(api("/api/matches"), {signal: controller.signal})
        .then(response => response.ok ? response.json() as Promise<{matches: TableSummary[]}> : Promise.reject())
        .then(data => setTables(data.matches || []))
        .catch(() => {});
    }
    loadTables();
    const timer = window.setInterval(loadTables, 4000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [snapshot]);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("match");
    if (requested && !watchingRef.current) void watchMatch(requested);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updatePlayer(id: string, patch: Partial<PlayerForm>) {
    setPlayers(current => current.map(p => {
      if (p.id !== id) return p;
      if (patch.backend && patch.backend !== p.backend) {
        const defaults = BACKENDS[patch.backend];
        return {...p, ...patch, provider: patch.backend === "grok" ? "grok" : "custom", base_url: defaults.url, model: defaults.model, api_key: "", auth_mode: patch.backend === "grok" ? "subscription" : "api_key"};
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

  function setSoloMatch() {
    if (game !== "harmonies") setGame("ark_nova");
    setPlayers([humanPlayer(1)]);
  }

  function selectGame(next: GameId) {
    setGame(next);
    const maximum = next === "seven_wonders" ? 7 : ["century_spice_road", "wingspan", "carcassonne"].includes(next) ? 5 : 4;
    const minimum = ["ark_nova", "harmonies"].includes(next) ? 1 : next === "seven_wonders" ? 3 : 2;
    setPlayers(current => {
      const selected = current.slice(0, maximum);
      while (selected.length < minimum) selected.push(player(selected.length + 1, "random"));
      return selected;
    });
  }

  function selectProvider(id: string, provider: Provider) {
    const preset = PROVIDERS[provider];
    setPlayers(current => current.map(p => p.id === id ? {
      ...p, provider, backend: provider === "custom" ? p.backend : preset.backend,
      base_url: provider === "custom" ? p.base_url : preset.url,
      ...(provider === "grok" ? {auth_mode: "subscription" as AuthMode, api_key: ""} : {}),
      model: provider === "custom" ? p.model : preset.models[0],
      reasoning_effort: ["codex", "qwen"].includes(preset.backend) && p.reasoning_effort === "none" ? "max" : p.reasoning_effort,
    } : p));
  }

  function updateMatchUrl(matchId?: string) {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (matchId) url.searchParams.set("match", matchId);
    else url.searchParams.delete("match");
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  }

  function attachMatch(data: Snapshot, resetHistory = true) {
    sourceRef.current?.close();
    if (resetHistory) { setTimeline([]); setChat([]); }
    setSnapshot(data); setGame(data.game);
    updateMatchUrl(data.match_id);
    requestAnimationFrame(() => window.scrollTo({top: 0, behavior: "smooth"}));
    const source = new EventSource(api(`/api/matches/${data.match_id}/events`));
    source.addEventListener("match", raw => {
      const item: Timeline = JSON.parse((raw as MessageEvent).data);
      if (item.snapshot) setSnapshot(current => mergeMatchSnapshot(current, item.snapshot!));
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
      if (!["agent_stream", "harness_output"].includes(event.type)) setTimeline(current => current.some(existing => existing.seq === item.seq) ? current : [...current, item]);
      if (["match_finished", "match_failed"].includes(item.event.type)) source.close();
    });
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) setError(lang === "zh" ? "实时连接已断开；只要 Web 服务未重启，可使用本页恢复链接重新连接。" : "Live connection closed. If the Web service is still running, use this page's reconnect link.");
    };
    sourceRef.current = source;
  }

  function leaveMatch() {
    sourceRef.current?.close(); sourceRef.current = null;
    watchingRef.current = false;
    setSnapshot(null); setTimeline([]); setChat([]); setError("");
    updateMatchUrl();
  }

  function viewFinalBoard() {
    finalBoardRef.current?.scrollIntoView({behavior: "smooth", block: "start"});
  }

  async function startMatch() {
    setStarting(true); setError(""); setTimeline([]); setChat([]); sourceRef.current?.close();
    try {
      const response = await fetch(api("/api/matches"), {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          game, seed: seed === "" ? null : Number(seed), speed_ms: speed,
          ...(game === "wingspan" ? {game_config: {goal_board: wingspanGoalBoard}} : {}),
          ...(game === "harmonies" ? {game_config: {board_side: harmoniesSide, nature_spirits: harmoniesSpirits}} : {}),
          ...(game === "ark_nova" ? {game_config: {
            map: arkMap,
            ...(players.length === 1 ? {solo_starting_appeal: soloStartingAppeal} : {}),
          }} : {}),
          players: players.map(p => ({
            name: p.name, backend: p.backend, model: p.model,
            ...(["codex", "grok"].includes(p.backend) ? {auth_mode: p.auth_mode} : {}),
            ...(!(["codex", "grok"].includes(p.backend) && p.auth_mode === "subscription") ? {base_url: p.base_url, api_key: p.api_key} : {}),
            ...((HARNESS_BACKENDS.has(p.backend) && !(p.backend === "grok" && p.auth_mode === "subscription")) ? {reasoning_effort: p.reasoning_effort} : {}),
          })),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || "无法启动对局");
      attachMatch(data as Snapshot, true);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setStarting(false); }
  }

  async function togglePause() {
    if (!snapshot || snapshot.status !== "active") return;
    setControlling(true); setError("");
    try {
      const action = snapshot.paused || snapshot.mode === "spectator" || snapshot.running === false ? "resume" : "pause";
      const playerPayload = players.length === snapshot.players.length && players.every((player, index) => {
        const persisted = snapshot.players[index];
        return player.name === persisted?.name && player.backend === persisted?.backend;
      }) ? players.map(player => ({
        name: player.name, backend: player.backend, model: player.model,
        ...(["codex", "grok"].includes(player.backend) ? {auth_mode: player.auth_mode} : {}),
        ...(!(["codex", "grok"].includes(player.backend) && player.auth_mode === "subscription") ? {
          base_url: player.base_url, api_key: player.api_key,
        } : {}),
        ...((HARNESS_BACKENDS.has(player.backend) && !(player.backend === "grok" && player.auth_mode === "subscription")) ? {reasoning_effort: player.reasoning_effort} : {}),
      })) : undefined;
      const response = await fetch(api(`/api/matches/${snapshot.match_id}/${action}`), {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(action === "resume" && playerPayload ? {players: playerPayload} : {}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || "无法更新暂停状态");
      if (snapshot.mode === "spectator" || snapshot.running === false) attachMatch(data, false);
      else setSnapshot(current => mergeMatchSnapshot(current, data));
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
      setSnapshot(current => mergeMatchSnapshot(current, data)); setHumanActionState(null);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      setHumanActionState(current => current?.turnKey === humanTurnKey ? {...current, issue: message} : current);
    }
    finally { setSubmittingAction(""); }
  }

  function stageHumanAction(item: LegalAction | null, requirement = "") {
    if (!humanTurnKey) return;
    setError("");
    setHumanActionState({turnKey: humanTurnKey, selected: item, requirement, issue: ""});

  }

  if (!snapshot) return <main className="setup-shell">
    <section className="hero">
      <a className="arena-link" href={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/arena`}>About AgentBGA →</a>
      <button className="lang-toggle" onClick={toggleLang} aria-label="Switch language">{zh ? "EN" : "中文"}</button>
      <div className="eyebrow">{t("hero_eyebrow")} / {GAME_COPY[game].eyebrow}</div>
      <h1>{t("hero_title_a")}<br/><i>{t("hero_title_b")}</i>{t("hero_title_c")}</h1>
      <p>{GAME_COPY[game].description[lang]}</p>
      <div className="hero-marks"><span>{t("hero_mark_1")}</span><span>{t("hero_mark_2")}</span><span>{game === "ark_nova" ? t("hero_mark_ark") : t("hero_mark_3")}</span></div>
    </section>
    <section className="setup-card">
      <section className="live-tables">
        <header>
          <div><span>{t("live_tables")}</span><h2>{t("watch_live")}</h2></div>
          <form className="watch-form" onSubmit={event => { event.preventDefault(); if (watchTarget) void watchMatch(watchTarget); }}>
            <label htmlFor="watch-id">{t("watch_id")}</label>
            <input id="watch-id" type="search" value={watchId} spellCheck={false} autoComplete="off" placeholder={t("watch_id")} aria-controls="live-table-results" onChange={event => setWatchId(event.target.value)}/>
            <button type="submit" disabled={starting || !watchTarget}>{starting ? t("watching") : t("watch")}</button>
          </form>
        </header>
        <div className="live-table-results-meta" aria-live="polite"><span>{filteredTables.length} / {tables.length}</span><small>{watchId.trim() ? t("watch_id") : zh ? "滚轮浏览牌桌" : "Scroll to browse tables"}</small></div>
        <div className="live-table-list" id="live-table-results">
          {tables.length === 0 && <p className="live-table-empty">{t("no_tables")}</p>}
          {tables.length > 0 && filteredTables.length === 0 && <p className="live-table-empty">{t("no_matching_tables")}</p>}
          {filteredTables.map(table => {
            const names = table.players.map(player => player.name).filter(Boolean);
            const title = names.length ? names.join(" vs ") : table.match_id;
            return <button type="button" key={table.match_id} onClick={() => void watchMatch(table.match_id)}>
              <strong>{title}</strong>
              <span>{GAME_COPY[table.game]?.name[lang] || table.game} · {t("turn")} {table.turn_count} · {table.status === "finished" ? t("s_finished") : t("s_active")}</span>
              <code>{table.match_id}</code>
            </button>;
          })}
        </div>
      </section>
      <div className="game-picker" role="group" aria-label={t("pick_game")}>{(Object.keys(GAME_COPY) as GameId[]).map(id => <button key={id} className={game === id ? "selected" : ""} onClick={() => selectGame(id)}><span>{GAME_COPY[id].badge}</span><b>{GAME_COPY[id].name[lang]}</b><small>{GAME_COPY[id].note[lang]}</small></button>)}</div>
      <header><div><span>{t("new_table")}</span><h2>{t("create_table")}{GAME_COPY[game].name[lang]}</h2></div><div className="matchup-presets">{["ark_nova", "harmonies"].includes(game) && <button className={players.length === 1 ? "selected-preset" : ""} onClick={setSoloMatch}>{zh ? "单人模式" : "Solo"}</button>}<button onClick={() => setMatchup("human")}>{t("g_human")}</button><button onClick={() => setMatchup("harness")}>{t("g_harness")}</button><b>{players.length} {t("players_count")}</b></div></header>
      <div className="players-config">{players.map((p, index) => <article className="player-config" key={p.id}>
        <div className="seat-order"><b>0{index + 1}</b><div><button disabled={index === 0} aria-label={`${p.name} ${t("move_up")}`} onClick={() => movePlayer(index, -1)}>↑</button><button disabled={index === players.length - 1} aria-label={`${p.name} ${t("move_down")}`} onClick={() => movePlayer(index, 1)}>↓</button></div></div>
        <div className="field grow"><label htmlFor={`${p.id}-name`}>{t("f_name")}</label><input id={`${p.id}-name`} value={p.name} onChange={e => updatePlayer(p.id, {name: e.target.value})}/></div>
        {!(["random", "human"] as Backend[]).includes(p.backend) && <>
          <div className="field provider-field"><label htmlFor={`${p.id}-provider`}>{t("f_provider")}</label><select id={`${p.id}-provider`} value={p.provider} onChange={e => selectProvider(p.id, e.target.value as Provider)}><optgroup label={t("og_harness")}>{(["claude_code", "pi", "qwen", "codex", "cursor", "grok", "opencode", "dsh", "hermes", "minimal"] as Provider[]).map(id => <option key={id} value={id}>{PROVIDERS[id].label[lang]}</option>)}</optgroup><optgroup label={t("og_direct")}>{(["custom", "deepseek", "dashscope", "zhipu", "minimax"] as Provider[]).map(id => <option key={id} value={id}>{PROVIDERS[id].label[lang]}</option>)}</optgroup></select></div>
          <div className="field backend-field"><label htmlFor={`${p.id}-backend`}>{t("f_backend")}</label><select id={`${p.id}-backend`} value={p.backend} onChange={e => updatePlayer(p.id, {backend: e.target.value as Backend})}>{Object.entries(BACKENDS).filter(([id]) => id !== "random").map(([id, b]) => <option key={id} value={id}>{b.label[lang]}</option>)}</select></div>
          {["codex", "grok"].includes(p.backend) && <div className="field auth-field"><label htmlFor={`${p.id}-auth`}>{t("f_auth")}</label><select id={`${p.id}-auth`} value={p.auth_mode} onChange={e => updatePlayer(p.id, {auth_mode: e.target.value as AuthMode})}><option value="subscription">{t(p.backend === "grok" ? "auth_grok" : "auth_subscription")}</option><option value="api_key">{t("auth_api_key")}</option></select></div>}
          {!(["codex", "grok"].includes(p.backend) && p.auth_mode === "subscription") && <div className="field grow endpoint-field"><label htmlFor={`${p.id}-endpoint`}>{t("f_endpoint")}</label><input id={`${p.id}-endpoint`} value={p.base_url} placeholder={t("ph_endpoint")} onChange={e => updatePlayer(p.id, {provider: "custom", base_url: e.target.value})}/></div>}
          <div className="field model-field"><label htmlFor={`${p.id}-model`}>{t("f_model")}</label><input id={`${p.id}-model`} list={`${p.id}-models`} placeholder={t("ph_model")} value={p.model} onChange={e => updatePlayer(p.id, {model: e.target.value})}/><datalist id={`${p.id}-models`}>{PROVIDERS[p.provider].models.map(model => <option key={model} value={model}/>)}</datalist></div>
          {!(["codex", "grok"].includes(p.backend) && p.auth_mode === "subscription") && <div className="field key-field"><label htmlFor={`${p.id}-key`}>{t("f_key")}</label><input id={`${p.id}-key`} type="password" autoComplete="off" placeholder={t("ph_key")} value={p.api_key} onChange={e => updatePlayer(p.id, {api_key: e.target.value})}/></div>}
          {(HARNESS_BACKENDS.has(p.backend) && !(p.backend === "grok" && p.auth_mode === "subscription")) && <div className="field reasoning-field"><label htmlFor={`${p.id}-reasoning`}>Reasoning Effort</label><select id={`${p.id}-reasoning`} value={p.reasoning_effort} onChange={e => updatePlayer(p.id, {reasoning_effort: e.target.value as ReasoningEffort})}>{REASONING_OPTIONS.filter(option => !["codex", "qwen"].includes(p.backend) || option.value !== "none").map(option => <option key={option.value} value={option.value}>{option.label[lang]}</option>)}</select></div>}
          <div className="provider-note">{PROVIDERS[p.provider].note[lang]}</div>
        </>}
        {(["random", "human"] as Backend[]).includes(p.backend) && <div className="field manual-backend"><label htmlFor={`${p.id}-backend`}>{t("f_backend")}</label><select id={`${p.id}-backend`} value={p.backend} onChange={e => updatePlayer(p.id, {backend: e.target.value as Backend})}>{Object.entries(BACKENDS).map(([id, b]) => <option key={id} value={id}>{b.label[lang]}</option>)}</select><small>{p.backend === "human" ? t("human_note") : t("random_note")}</small></div>}
        {players.length > minPlayers && <button className="remove" aria-label={`${t("remove")} ${p.name}`} onClick={() => setPlayers(x => x.filter(y => y.id !== p.id))}>×</button>}
      </article>)}</div>
      <div className="setup-actions">
        <button className="add-player human-add" disabled={players.length >= maxPlayers} onClick={() => setPlayers(x => [...x, humanPlayer(x.length + 1)])}>{t("add_human")}</button>
        <button className="add-player" disabled={players.length >= maxPlayers} onClick={() => setPlayers(x => [...x, player(x.length + 1, "random")])}>{t("add_ai")}</button>
        <button className="shuffle-order" onClick={shufflePlayers}>{t("shuffle")}</button>
        {game === "wingspan" && <div className="field"><label htmlFor="wingspan-goals">{zh ? "目标计分" : "Goal scoring"}</label><select id="wingspan-goals" value={wingspanGoalBoard} onChange={e => setWingspanGoalBoard(e.target.value)}><option value="green">{zh ? "绿色 · 排名竞争" : "Green · competitive"}</option><option value="blue">{zh ? "蓝色 · 每项最多 5 分" : "Blue · up to 5 per goal"}</option></select></div>}
        {game === "harmonies" && <><div className="field"><label htmlFor="harmonies-side">{zh ? "个人地图" : "Personal board"}</label><select id="harmonies-side" value={harmoniesSide} onChange={e => setHarmoniesSide(e.target.value as "A" | "B")}><option value="A">A · {zh ? "河流" : "Rivers"}</option><option value="B">B · {zh ? "岛屿" : "Islands"}</option></select></div><div className="field"><label htmlFor="harmonies-spirits">{zh ? "自然之灵" : "Nature’s Spirits"}</label><select id="harmonies-spirits" value={String(harmoniesSpirits)} onChange={e => setHarmoniesSpirits(e.target.value === "true")}><option value="false">{zh ? "关闭 · 推荐初次游戏" : "Off · first game"}</option><option value="true">{zh ? "开启 · 额外计分目标" : "On · extra scoring goals"}</option></select></div></>}
        {game === "ark_nova" && <div className="field ark-map-setup"><label htmlFor="ark-zoo-map">{zh ? "动物园地图" : "Zoo map"}</label><select id="ark-zoo-map" value={arkMap} onChange={event => setArkMap(event.target.value as ArkMapId)}><option value="map-0">Map 0 · {zh ? "空地图开局" : "empty-map setup"}</option><option value="map-a">Map A · {zh ? "预置 3 格围栏与商亭" : "3-space enclosure + kiosk"}</option></select><small>{arkMap === "map-a" ? (zh ? "Map A 的两座开局建筑免费且已经放置。" : "Map A's two setup buildings are free and already placed.") : (zh ? "Map 0 不提供免费开局建筑。" : "Map 0 has no free setup buildings.")}</small></div>}
        {game === "ark_nova" && players.length === 1 && <div className="field ark-solo-setup"><label htmlFor="ark-solo-appeal">{zh ? "单人难度 / 初始魅力" : "Solo difficulty / starting Appeal"}</label><select id="ark-solo-appeal" value={soloStartingAppeal} onChange={event => setSoloStartingAppeal(Number(event.target.value) as 0 | 10 | 20)}><option value={20}>{zh ? "标准 · 魅力 20" : "Standard · Appeal 20"}</option><option value={10}>{zh ? "进阶 · 魅力 10" : "Advanced · Appeal 10"}</option><option value={0}>{zh ? "专家 · 魅力 0" : "Expert · Appeal 0"}</option></select><small>{zh ? "固定 6 轮，共 27 次行动；最终分数达到 0 即获胜。" : "Six fixed rounds, 27 turns total; finish with at least 0 VP to win."}</small></div>}
        <div className="field mini"><label htmlFor="match-seed">{t("f_seed")}</label><input id="match-seed" inputMode="numeric" value={seed} onChange={e => setSeed(e.target.value)}/></div>
        <div className="field mini speed"><label htmlFor="match-speed">{t("f_speed")} <b>{speed}ms</b></label><input id="match-speed" type="range" min="0" max="2000" step="50" value={speed} onChange={e => setSpeed(Number(e.target.value))}/></div>
        <button className="start" disabled={starting} onClick={startMatch}>{starting ? t("starting") : t("start")}</button>
      </div>
      {game === "ark_nova" && <div className="setup-scope-note"><b>{GAME_COPY.ark_nova.badge}</b> {zh ? "基础版 128 动物、64 赞助商、32 保育项目、11 终局计分和 5 种行动牌均已程式化；实体 255 张清单用于校验重复牌与牌库守恒。" : "The base set's 128 Animals, 64 Sponsors, 32 Conservation Projects, 11 Final Scoring cards, and five Action cards are executable; the 255-card physical roster validates duplicates and deck conservation."}</div>}
      {game === "wingspan" && <div className="setup-scope-note"><b>PLAYABLE BETA</b> {zh ? "170 张基础鸟牌、26 张奖励卡、双面轮末目标；支持 2–5 人，不含教学牌、扩展和 Automa 单人模式。" : "170 base birds, 26 bonus cards and double-sided round goals. 2–5 players; excludes Swift-Start, expansions and solo Automa."}</div>}
      {game === "harmonies" && <div className="setup-scope-note"><b>PLAYABLE BETA</b> {zh ? "支持 32 张编号动物牌、120 枚地形、双面棋盘、单人规则和可选自然之灵；使用原创 SVG 图形与社区转录的牌组数据。" : "32 numbered animal cards, 120 tokens, both boards, solo rules and optional spirits; original SVG graphics and community-transcribed card data."}</div>}
      {game === "azul" && <div className="setup-scope-note"><b>{GAME_COPY.azul.badge}</b> {zh ? "支持彩色墙基础版、100 枚具名花砖、工厂与中央区选砖、图案线、地板罚分、相邻计分、终局奖励和确定性回放；不包含灰墙玩法、扩展或出版商美术。" : "Supports the colored-wall base game, 100 identity-safe tiles, factory/center drafting, pattern lines, floor penalties, adjacency scoring, endgame bonuses and deterministic replay; no gray wall, expansions or publisher artwork."}</div>}
      {game === "brass_birmingham" && <div className="setup-scope-note"><b>{GAME_COPY.brass_birmingham.badge}</b> {zh ? "支持官方人数牌组、产业板、市场、商人、Build/Sell/Develop、单双铁路、负收入变卖、双时代计分与完整回放；界面不包含出版商美术。" : "Supports official player counts, industry board, markets, merchants, Build/Sell/Develop, single/double rail, negative-income liquidation, two-era scoring and full replay; no publisher artwork."}</div>}
      {game === "castles_of_burgundy" && <div className="setup-scope-note"><b>{GAME_COPY.castles_of_burgundy.badge}</b> {zh ? "支持 164 枚六角板块、42 枚货物、双骰行动、工人修骰、六类区域、建筑即时效果、修道院能力、顺位与终局计分；使用共同 1 号领地，不含扩展和出版商美术。" : "Supports 164 hex tiles, 42 goods, two-die turns, worker adjustments, six region types, building effects, monasteries, turn order and final scoring; common duchy no. 1, no expansions or publisher artwork."}</div>}
      {game === "century_spice_road" && <div className="setup-scope-note"><b>{GAME_COPY.century_spice_road.badge}</b> {zh ? "完整基础牌组数值、重复交易、升级、市场压香料、商队容量、金币银币、终局与计分均已接通；不包含出版商卡图。" : "Full base-set values, repeat trades, upgrades, market spice, caravan capacity, gold/silver coins, endgame and scoring wired up; no publisher artwork."}</div>}
      {game === "seven_wonders" && <div className="setup-scope-note"><b>{GAME_COPY.seven_wonders.badge}</b> {zh ? "支持 148 张基础牌、日/夜双面奇迹、密封同步选牌、邻城贸易、链式建造、军事、科技、商会与七类计分；不包含扩展或出版商美术。" : "Supports all 148 base cards, Day/Night Wonders, sealed simultaneous drafting, neighbor trade, chains, military, science, guilds and seven-part scoring; no expansions or publisher artwork."}</div>}
      {error && <div className="error">{error}</div>}
    </section>
  </main>;

 return <main className={`table-shell human-play game-${snapshot.game} ${showMatchLog ? "match-log-open" : ""} ${snapshot.game === "splendor" ? `game-splendor ${showMatchLog ? "sp-log-open" : ""}` : ""} ${snapshot.game === "harmonies" ? "game-harmonies" : snapshot.game === "wingspan" ? "game-wingspan" : ""}`}>
    <header className="table-header">
      <div><span className="brand-mark">ABGA</span><strong>{snapshot.game === "harmonies" ? GAME_COPY.harmonies.name[lang] : snapshot.game_description.name} {snapshot.game === "harmonies" ? "" : snapshot.game === "splendor" ? t("live_table") : snapshot.game === "century_spice_road" ? t("trade_arena") : t("controlled_arena")}</strong></div>
      <div className="match-meta"><span>{t("match")} <a className="match-reconnect-link" href={`?match=${snapshot.match_id}`} title={lang === "zh" ? "此对局的恢复链接" : "Reconnect link for this match"}><code>{snapshot.match_id}</code></a></span><span>{t("turn")} <b>{snapshot.game === "harmonies" ? harmoniesView?.round : snapshot.game === "wingspan" ? wingspanView?.round : snapshot.turn_count}</b>{["harmonies", "wingspan"].includes(snapshot.game) && <> · {t("decision")} <b>{snapshot.turn_count}</b></>}{snapshot.game === "ark_nova" && <> · {t("decision")} <b>{snapshot.decision_count ?? arkView?.decision_count}</b></>}</span>{spectator && <span className="status status-setup">{t("spectator")}</span>}<span className={`status ${snapshot.paused ? "status-paused" : `status-${snapshot.status}`}`}>{snapshot.status !== "active" ? t("s_finished") : snapshot.paused ? (snapshot.pause_pending ? t("s_wait_pause") : t("s_paused")) : t("s_active")}</span></div>
      <div className="table-actions">
        <button className="lang-toggle" onClick={toggleLang} aria-label="Switch language">{zh ? "EN" : "中文"}</button>
        {(!spectator || snapshot.status === "active") && <button className={`pause-button ${(snapshot.paused || spectator || snapshot.running === false) ? "is-paused" : ""}`} disabled={snapshot.status !== "active" || controlling} aria-pressed={snapshot.paused} onClick={togglePause}>{controlling ? t("processing") : (snapshot.paused || spectator || snapshot.running === false) ? t("resume") : t("pause")}</button>}
        {<button aria-expanded={showMatchLog} aria-controls="match-log" onClick={() => setShowMatchLog(value => !value)}>{zh ? "对局记录" : "Match log"}</button>}
        <button onClick={leaveMatch}>{t("new_match")}</button>
      </div>
    </header>
    {error && <div className="table-error" role="alert">{error}</div>}
    {snapshot.status === "finished" && <section className="winner-summary" aria-label={t("match_over")}>
      <div><span>{t("winner")}</span><strong>{snapshot.rankings?.[0]?.player || timeline.at(-1)?.event.rankings?.[0]?.player || t("match_over")}</strong></div>
      <div><button className="view-final-board" onClick={viewFinalBoard}>{t("view_final_board")}</button><button onClick={leaveMatch}>{t("play_again")}</button></div>
    </section>}
    <div className="table-grid">
      <aside className="players-column">{[...snapshot.players].sort((a,b) => Number(b.seat === humanSeat) - Number(a.seat === humanSeat)).map(identity => {
        // Ark Nova agent-only matches use a dedicated omniscient Web projection;
        // player/agent observations remain seat-isolated in the runner.
        const visiblePlayer = snapshot.game === "ark_nova"
          ? arkView?.players[identity.seat] : viewer?.players[identity.seat];
        return snapshot.game === "splendor"
          ? <PlayerPanel key={identity.seat} player={visiblePlayer as PlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>
          : snapshot.game === "carcassonne"
            ? <CarcassonnePlayerPanel key={identity.seat} player={visiblePlayer as CarcassonnePlayer} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat} lang={lang}/>
          : snapshot.game === "wingspan"
            ? <WingspanPlayerPanel key={identity.seat} player={visiblePlayer as WingspanPlayer} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat} lang={lang}/>
          : snapshot.game === "harmonies"
            ? <HarmoniesPlayerPanel key={identity.seat} player={visiblePlayer as HarmoniesPlayer} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat} lang={lang}/>
          : snapshot.game === "azul"
            ? <AzulPlayerPanel key={identity.seat} player={visiblePlayer as AzulPlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat} holdsStartMarker={azulView?.start_marker_holder_seat === identity.seat}/>
          : snapshot.game === "ark_nova"
            ? <ArkPlayerPanel key={identity.seat} player={visiblePlayer as ArkPlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>
            : snapshot.game === "brass_birmingham"
              ? <BrassPlayerPanel key={identity.seat} player={visiblePlayer as BrassPlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>
              : snapshot.game === "castles_of_burgundy"
                ? <BurgundyPlayerPanel key={identity.seat} player={visiblePlayer as BurgundyPlayer} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat} lang={lang}/>
              : snapshot.game === "century_spice_road"
                ? <CenturyPlayerPanel key={identity.seat} player={visiblePlayer as CenturyPlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>
                : <SevenPlayerPanel key={identity.seat} player={visiblePlayer as SevenPlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>;
      })}</aside>
      <section className={`board ${snapshot.human_turn ? "has-human-action" : ""}`} ref={finalBoardRef}>
        {snapshot.paused && <div className={`pause-notice ${snapshot.pause_pending ? "pending" : ""}`}><strong>{snapshot.pause_pending ? t("pause_pending") : t("paused")}</strong><span>{snapshot.pause_pending ? t("pause_pending_desc") : t("paused_desc")}</span></div>}
        {snapshot.human_turn && snapshot.game !== "splendor" && <section className="human-turn" aria-live="polite">
          <header><div><span>YOUR TURN · SEAT {snapshot.human_turn.seat + 1}</span><h2>{snapshot.human_turn.player}{t("pick_action")}</h2></div><b>{snapshot.human_turn.legal_actions.length} {t("legal_opts")}</b></header>
          {snapshot.game === "ark_nova" && arkFallbackActions.length > 0 && <div className="human-action-groups">{Object.entries(groupActions(arkFallbackActions)).map(([kind, actions]) => <ActionChoices key={kind} actions={actions} label={ACTION_GROUPS[lang][kind] || kind} describe={item => humanItemText(item, lang)} lang={lang} disabled={Boolean(submittingAction) || snapshot.paused} onChoose={stageHumanAction}/>)}</div>}

        </section>}
        {snapshot.game === "splendor" ? <>{splendorView && <SplendorTable key={humanTurnKey || snapshot.match_id} view={splendorView} seat={humanSeat} actions={snapshot.human_turn?.legal_actions || []} disabled={Boolean(submittingAction) || snapshot.paused} selected={selectedHumanAction} issue={currentHumanActionState?.issue} onSelect={stageHumanAction} onSubmit={item => void submitHumanAction(item)} activeName={names[snapshot.active_seat] || "Agent"} lastMove={(() => {const last = timeline.filter(item => ["decision", "turn"].includes(item.event.type)).at(-1); return last ? describeAction(last, names, lang) : "";})()}/>}</>
          : snapshot.game === "carcassonne" ? <CarcassonneTable key={snapshot.match_id} view={carcassonneView} lang={lang} identities={snapshot.players} actions={snapshot.human_turn?.legal_actions} disabled={Boolean(submittingAction) || snapshot.paused} onChoose={item => stageHumanAction(item)} onReset={() => stageHumanAction(null)}/>
          : snapshot.game === "wingspan" ? <WingspanTable key={wingspanView?.turn_count} view={wingspanView} lang={lang} identities={snapshot.players} actions={snapshot.human_turn?.legal_actions} disabled={Boolean(submittingAction) || snapshot.paused} onChoose={item => stageHumanAction(item)} onReset={() => stageHumanAction(null)}/>
          : snapshot.game === "harmonies" ? <HarmoniesTable key={harmoniesView?.turn_count} view={harmoniesView} lang={lang} identities={snapshot.players} actions={snapshot.human_turn?.legal_actions} disabled={Boolean(submittingAction) || snapshot.paused} onChoose={item => stageHumanAction(item)} onReset={() => stageHumanAction(null)}/>
          : snapshot.game === "azul" ? <AzulBoard key={humanTurnKey || snapshot.match_id} view={azulView} seat={humanSeat} actions={snapshot.human_turn?.legal_actions} disabled={Boolean(submittingAction) || snapshot.paused} onChoose={stageHumanAction} onReset={() => stageHumanAction(null)}/>
          : snapshot.game === "ark_nova" ? <ArkNovaBoard view={arkView} players={snapshot.players} legalActions={snapshot.human_turn?.legal_actions || []} submitting={submittingAction} selectedActionId={selectedHumanAction?.id || submittingAction} onChoose={item => stageHumanAction(item)}/>
          : snapshot.game === "brass_birmingham" ? <BrassBoard view={brassView} players={snapshot.players} humanActions={snapshot.human_turn?.legal_actions} disabled={Boolean(submittingAction) || snapshot.paused} submitting={submittingAction} selectedActionId={selectedHumanAction?.id} onChoose={item => stageHumanAction(item)}/>
          : snapshot.game === "castles_of_burgundy" ? <BurgundyTable key={humanTurnKey || snapshot.match_id} view={burgundyView} lang={lang} actions={snapshot.human_turn?.legal_actions} disabled={Boolean(submittingAction) || snapshot.paused} onChoose={stageHumanAction} onReset={() => stageHumanAction(null)}/>
          : snapshot.game === "century_spice_road" ? <CenturyBoard view={centuryView} seat={humanSeat} actions={snapshot.human_turn?.legal_actions} disabled={Boolean(submittingAction) || snapshot.paused} onChoose={stageHumanAction}/>
          : <SevenBoard view={sevenView} spectatorViews={sevenSpectatorViews} identities={snapshot.players} actions={snapshot.human_turn?.legal_actions} disabled={Boolean(submittingAction) || snapshot.paused} onChoose={stageHumanAction}/>}
        {snapshot.human_turn && snapshot.game !== "splendor" && <HumanConfirmation label={selectedHumanAction ? readableMove(selectedHumanAction.action, viewer, lang, snapshot.game === "castles_of_burgundy" ? burgundyActionLabel(selectedHumanAction, lang) : humanItemText(selectedHumanAction, lang, brassView)) : ""} selected={selectedHumanAction} requirement={currentHumanActionState?.requirement} issue={currentHumanActionState?.issue} busy={Boolean(submittingAction)} disabled={Boolean(submittingAction) || snapshot.paused} lang={lang} onClear={() => stageHumanAction(null)} onConfirm={() => selectedHumanAction && void submitHumanAction(selectedHumanAction)}/>}
      </section>
      <aside className={`timeline ${agentOutputCollapsed ? "agent-output-collapsed" : ""} ${actionLogCollapsed ? "action-log-collapsed" : ""}`} id="match-log">
        <header><div><span>{t("model_stream")}</span><h2>{t("chat_h")}</h2></div><div className="log-panel-tools"><i className={snapshot.status === "active" && (!snapshot.paused || snapshot.pause_pending) ? "pulse" : ""}/><button type="button" className="log-panel-toggle" aria-expanded={!agentOutputCollapsed} aria-controls="agent-output-content" aria-label={zh ? `${agentOutputCollapsed ? "展开" : "收起"} Agent 输出` : `${agentOutputCollapsed ? "Expand" : "Collapse"} Agent output`} onClick={() => setAgentOutputCollapsed(value => !value)}>{agentOutputCollapsed ? (zh ? "展开" : "Expand") : (zh ? "收起" : "Collapse")} <span aria-hidden="true">{agentOutputCollapsed ? "▸" : "▾"}</span></button></div></header>
        <div className="chat-list" id="agent-output-content" hidden={agentOutputCollapsed}>{chat.length === 0 && <p className="waiting">{snapshot.game_description.runnable ? t("waiting_model") : t("waiting_note")}</p>}{chat.map(turn => <article className={`chat-turn chat-${turn.status}`} key={turn.key}>
          <header><strong>{turn.player}</strong><span>{turn.backend} · {t("attempt")} {turn.attempt}{turn.status === "thinking" ? ` · ${t("generating")}` : turn.processLatencyMs !== undefined ? ` · ${lang === "zh" ? "行动" : "action"} ${((turn.actionLatencyMs ?? turn.processLatencyMs) / 1000).toFixed(1)}s · ${lang === "zh" ? "进程" : "process"} ${(turn.processLatencyMs / 1000).toFixed(1)}s` : ""}</span></header>
          {turn.reasoning && <details open><summary>{t("thinking")}{turn.status === "done" ? ` · ${t("collapsible")}` : ""}</summary><pre>{turn.reasoning}</pre></details>}
          {turn.content && <div className="model-answer"><b>{t("answer")}</b><pre>{turn.content}</pre></div>}
          {turn.status === "thinking" && <div className="typing"><i/><i/><i/></div>}
        </article>)}</div>
        <section className="action-drawer"><header><span>{t("actions")}</span><strong>{t("decision_log")}</strong><b>{timeline.filter(item => ["decision", "turn"].includes(item.event.type)).length}</b><button type="button" className="log-panel-toggle" aria-expanded={!actionLogCollapsed} aria-controls="action-log-content" aria-label={zh ? `${actionLogCollapsed ? "展开" : "收起"} Action 记录` : `${actionLogCollapsed ? "Expand" : "Collapse"} Action log`} onClick={() => setActionLogCollapsed(value => !value)}>{actionLogCollapsed ? (zh ? "展开" : "Expand") : (zh ? "收起" : "Collapse")} <span aria-hidden="true">{actionLogCollapsed ? "▸" : "▾"}</span></button></header>
          <div id="action-log-content" hidden={actionLogCollapsed}>{[...timeline].reverse().filter(item => !["agent_started", "agent_finished"].includes(item.event.type)).slice(0, 40).map(item => <article key={item.seq} className={`event event-${item.event.type}`}>
            <span>{String(item.seq + 1).padStart(3,"0")}</span><div><p>{describeAction(item, names, lang)}</p>{item.event.backend && <small>{item.event.backend}{item.event.agent?.process_latency_ms !== undefined ? ` · ${lang === "zh" ? "行动" : "action"} ${item.event.agent.action_latency_ms ?? "—"}ms · ${lang === "zh" ? "进程" : "process"} ${item.event.agent.process_latency_ms}ms` : item.event.agent?.latency_ms ? ` · ${item.event.agent.latency_ms}ms` : ""}</small>}
              {item.event.tool && (item.event.arguments !== undefined || item.event.result !== undefined) && <details className="tool-payload"><summary>{t("view_tool")}</summary><pre>{JSON.stringify(item.event.result ?? item.event.arguments, null, 2)}</pre></details>}
            </div>
          </article>)}</div>
        </section>
      </aside>
    </div>
  </main>;
}
