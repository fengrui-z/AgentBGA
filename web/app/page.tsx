"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

// ── i18n ─────────────────────────────────────────────────────────────
type Lang = "zh" | "en";
type Dict = Record<string, string>;
const STR: Record<Lang, Dict> = {
  zh: {
    // hero
    hero_eyebrow: "AGENT BOARD GAME ARENA",
    hero_title_a: "把模型放上牌桌，",
    hero_title_b: "看见",
    hero_title_c: "每一次决策。",
    hero_mark_1: "多游戏插件", hero_mark_2: "座位隔离观察", hero_mark_3: "完整对局引擎", hero_mark_ark: "CONTROLLED CORE",
    // setup
    new_table: "NEW TABLE", create_table: "创建一桌", g_human: "人类 vs Agent", g_harness: "Harness 对战",
    players_count: "PLAYERS", pick_game: "选择游戏",
    f_name: "选手名", f_provider: "Harness / 服务商", f_backend: "运行方式", f_endpoint: "Endpoint",
    f_model: "模型名", f_key: "API Key", f_seed: "Seed", f_speed: "每步间隔",
    og_harness: "Agent Harness", og_direct: "直连模型 API",
    ph_model: "可选择或输入 model-id", ph_key: "仅在本次对局使用",
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
    ark_eyebrow: "ARK NOVA · CONTROLLED CORE",
    ark_phase_select: "正在选择起始手牌", ark_phase_play: "多阶段对局进行中",
    ark_phase_note: "回合、行动牌、建造、动物、协会、赞助商和 Break 已接通；当前使用无特殊能力的研究卡池，不代表完整商业卡池。",
    ark_tracks: "TRACKS / BREAK", ark_tracks_h: "公共轨道", cur_decision: "CURRENT DECISION",
    ark_display: "CARD DISPLAY", ark_display_h: "中央卡牌展示区", deck: "牌库", discard: "弃牌",
    ark_after_select: "起始选牌后翻开",
    ark_assoc: "ASSOCIATION BOARD", ark_assoc_h: "协会板与基础保育项目",
    ark_partner: "合作动物园", ark_uni: "大学", ark_donation: "捐款", ark_blocked: "双人封锁", ark_avail: "可用",
    ark_zoo: "BEGINNER MAP A", ark_zoo_h: "玩家动物园", ark_zoo_unit: "3 格起始围栏 · 空置",
    ark_zoo_note: "本里程碑的坐标为可测试的示意几何；正式 footprint 会在地图规则阶段按规则场景校准。",
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
    hero_mark_1: "Multi-game plugins", hero_mark_2: "Seat-isolated views", hero_mark_3: "Full-match engine", hero_mark_ark: "CONTROLLED CORE",
    new_table: "NEW TABLE", create_table: "New table · ", g_human: "Human vs Agent", g_harness: "Harness Battle",
    players_count: "PLAYERS", pick_game: "Select game",
    f_name: "Player name", f_provider: "Harness / provider", f_backend: "Runtime", f_endpoint: "Endpoint",
    f_model: "Model id", f_key: "API key", f_seed: "Seed", f_speed: "Step interval",
    og_harness: "Agent Harness", og_direct: "Direct model API",
    ph_model: "Pick or type model-id", ph_key: "Used for this match only",
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
    ark_eyebrow: "ARK NOVA · CONTROLLED CORE",
    ark_phase_select: "Selecting starting hand", ark_phase_play: "Multi-phase match in progress",
    ark_phase_note: "Turns, action cards, building, animals, association, sponsors and Break are wired up; uses an ability-free research card pool, not the full commercial pool.",
    ark_tracks: "TRACKS / BREAK", ark_tracks_h: "Public tracks", cur_decision: "CURRENT DECISION",
    ark_display: "CARD DISPLAY", ark_display_h: "Card display", deck: "Deck", discard: "Discard",
    ark_after_select: "Revealed after pick",
    ark_assoc: "ASSOCIATION BOARD", ark_assoc_h: "Association board & conservation projects",
    ark_partner: "Partner zoos", ark_uni: "Universities", ark_donation: "Donations", ark_blocked: "Two-player locked", ark_avail: "available",
    ark_zoo: "BEGINNER MAP A", ark_zoo_h: "Player zoo", ark_zoo_unit: "3-cell starter enclosure · empty",
    ark_zoo_note: "Coordinates are test-only schematic geometry; real footprints land in the map phase.",
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

type Backend = "openai" | "anthropic" | "gemini" | "claude" | "pi" | "codex" | "opencode" | "dsh" | "minimal" | "human" | "random";
type Provider = "custom" | "claude_code" | "pi" | "codex" | "opencode" | "dsh" | "minimal" | "deepseek" | "dashscope" | "zhipu" | "minimax";
type GameId = "splendor" | "ark_nova" | "brass_birmingham" | "century_spice_road";
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
  supported_projects: string[]; upgrade_rewards_claimed: number[]; final_card_choice_resolved: boolean;
};
type ArkView = {
  game: "ark_nova"; rules_version: string; implementation_status: string; status: string; phase: string;
  turn_count: number; decision_count: number; active_seat: number; turn: {active_seat: number; decision: string; action_card: string | null; remaining_plays: number};
  break_track: {position: number; start_marker: string; triggered: boolean}; card_display: ArkCard[];
  game_board_bonus_tiles: {id: string; implementation: string}[];
  deck_count: number; discard_count: number; base_conservation_projects: {id: string; tag: string; levels: number[]}[];
  association_board: {partner_zoos: Record<string, number>; universities: Record<string, number>; blocked_two_player: string[]; donations: {seat: number; cost: number}[]};
  players: ArkPlayerView[];
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
type GameDescription = {id: GameId; name: string; rules_version: string; implementation_status: string; runnable: boolean};
type Snapshot = {
  match_id: string; game: GameId; game_description: GameDescription; version: number; status: string; turn_count: number; decision_count?: number; active_seat: number;
  paused: boolean; pause_pending: boolean;
  human_turn?: {seat: number; player: string; version: number; legal_actions: LegalAction[]} | null;
  players: {seat: number; name: string; backend: string; model?: string; reasoning_effort?: string}[]; views: (View | ArkView | BrassView | CenturyView)[];
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
const GAME_COPY: Record<GameId, {eyebrow: string; name: Record<Lang,string>; description: Record<Lang,string>; badge: string; note: Record<Lang,string>}> = {
  splendor: {eyebrow: "SPLENDOR", name: {zh:"璀璨宝石",en:"Splendor"}, description: {zh:"配置 2–4 名模型或人类玩家。轮到你时直接在牌桌选择合法行动；所有 Agent Harness 固定使用最高思考强度。",en:"Configure 2–4 model or human players. On your turn, pick a legal action at the table; all agent harnesses run at max reasoning."}, badge: "PLAYABLE", note: {zh:"完整基础版引擎",en:"Full base-game engine"}},
  ark_nova: {eyebrow: "ARK NOVA", name: {zh:"方舟动物园",en:"Ark Nova"}, description: {zh:"在受控研究卡池中测试多阶段决策：起始选牌、五张行动牌、六角建造、动物入园、协会任务与 Break 都会逐步提交。",en:"Test multi-stage decisions in a controlled research-card pool: opening hand, five action cards, hex building, animal placement, association tasks and Break."}, badge: "CONTROLLED CORE V2", note: {zh:"升级 · 捐款 · 释放 · 效果系统",en:"Upgrades · donations · release · effect system"}},
  brass_birmingham: {eyebrow: "BRASS: BIRMINGHAM", name: {zh:"伯明翰",en:"Brass: Birmingham"}, description: {zh:"测试模型在双时代经济网络中的长期规划：产业建设、资源来源、商人出售、动态顺位和运河到铁路的资产转换。",en:"Test long-term planning in a two-era economic network: industry building, resource sourcing, merchant selling, dynamic turn order and canal-to-rail transitions."}, badge: "PLAYABLE BETA", note: {zh:"产业 · 网络 · 双时代经济",en:"Industry · network · two-era economy"}},
  century_spice_road: {eyebrow: "CENTURY: SPICE ROAD", name: {zh:"香料之路",en:"Century: Spice Road"}, description: {zh:"经营自己的商队：获取商人牌、升级或交换香料、争夺金币银币，并抢先完成高分订单。支持 2–5 名玩家。",en:"Run your caravan: acquire merchant cards, upgrade or trade spices, race for gold and silver coins to fulfill high-score orders. 2–5 players."}, badge: "CLASSIC BASE", note: {zh:"商人牌 · 香料引擎 · 订单竞速",en:"Merchant cards · spice engine · order race"}},
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
  minimal: { label: {zh: "Minimal Harness", en: "Minimal Harness"}, url: "https://api.deepseek.com", key: "", model: "" },
  human: { label: {zh: "人类玩家", en: "Human player"}, url: "", key: "", model: "" },
  random: { label: {zh: "随机基线", en: "Random baseline"}, url: "", key: "", model: "" },
};
const PROVIDERS: Record<Provider, {label: Record<Lang,string>; backend: Backend; url: string; models: string[]; note: Record<Lang,string>}> = {
  custom: {label: {zh:"自定义 / 代理平台",en:"Custom / gateway"}, backend: "openai", url: "", models: [], note: {zh:"手动填写协议、Endpoint 和模型 ID",en:"Fill in protocol, endpoint and model ID manually"}},
  claude_code: {label: {zh:"Claude Code",en:"Claude Code"}, backend: "claude", url: "https://api.anthropic.com", models: ["claude-sonnet-4-6", "claude-opus-4-6"], note: {zh:"Claude Code 持久 session + 座位隔离 MCP",en:"Persistent session + seat-isolated MCP"}},
  pi: {label: {zh:"Pi",en:"Pi"}, backend: "pi", url: "https://api.openai.com/v1", models: ["gpt-5.6"], note: {zh:"Pi 持久 session + AgentBGA 专用工具扩展；兼容自定义 OpenAI Endpoint",en:"Persistent session + AgentBGA tool extension; any OpenAI-compatible endpoint"}},
  codex: {label: {zh:"Codex",en:"Codex"}, backend: "codex", url: "https://api.openai.com/v1", models: ["gpt-5.6", "gpt-5.6-terra", "gpt-5.3-codex"], note: {zh:"Codex 持久 session + 座位隔离 MCP；自定义 Endpoint 自动使用兼容协议",en:"Persistent session + seat-isolated MCP; custom endpoint auto-compatible"}},
  opencode: {label: {zh:"OpenCode",en:"OpenCode"}, backend: "opencode", url: "https://api.deepseek.com", models: ["deepseek-v4-flash", "deepseek-v4-pro"], note: {zh:"OpenCode 持久 session + 座位隔离 MCP",en:"Persistent session + seat-isolated MCP"}},
  dsh: {label: {zh:"DeepSeek Harness",en:"DeepSeek Harness"}, backend: "dsh", url: "https://api.deepseek.com", models: ["deepseek-v4-flash", "deepseek-v4-pro"], note: {zh:"DeepSeek Harness (dsh) headless + 座位隔离 MCP；每回合独立 session，workspace 笔记持久",en:"dsh headless + seat-isolated MCP; fresh session each turn, workspace notes persist"}},
  minimal: {label: {zh:"Minimal Harness",en:"Minimal Harness"}, backend: "minimal", url: "https://api.deepseek.com", models: ["deepseek-v4-flash", "deepseek-v4-pro"], note: {zh:"纯 Python minimal harness；直接 LLM API + 5 工具；无外部进程，认知干预可配置",en:"Pure-Python minimal harness; direct LLM API + 5 tools; no external process"}},
  deepseek: {label: {zh:"DeepSeek 官方",en:"DeepSeek official"}, backend: "openai", url: "https://api.deepseek.com", models: ["deepseek-v4-flash", "deepseek-v4-pro"], note: {zh:"官方按量付费 API",en:"Official pay-as-you-go API"}},
  dashscope: {label: {zh:"阿里云百炼",en:"Alibaba Bailian"}, backend: "openai", url: "https://dashscope.aliyuncs.com/compatible-mode/v1", models: ["qwen3.7-plus", "qwen3.6-plus", "qwen3.5-flash", "qwen3.7-max"], note: {zh:"华北 2 按量付费，不是 Coding Plan",en:"North-China 2 pay-as-you-go, not Coding Plan"}},
  zhipu: {label: {zh:"智谱开放平台",en:"Zhipu Open Platform"}, backend: "openai", url: "https://open.bigmodel.cn/api/paas/v4", models: ["glm-5.2", "glm-5", "glm-4.7"], note: {zh:"开放平台按量付费 Endpoint",en:"Open-platform pay-as-you-go endpoint"}},
  minimax: {label: {zh:"MiniMax 官方",en:"MiniMax official"}, backend: "openai", url: "https://api.minimaxi.com/v1", models: ["MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.5-highspeed"], note: {zh:"国内开放平台 OpenAI 兼容 API",en:"China open-platform OpenAI-compatible API"}},
};

function player(seed: number, backend: Backend = "openai"): PlayerForm {
  return { id: crypto.randomUUID(), name: `Agent ${seed}`, provider: "custom", backend, model: "", base_url: BACKENDS[backend].url, api_key: "" };
}

function deepseekHarnessPlayer(seed: number, backend: "opencode" | "codex" | "dsh" | "minimal"): PlayerForm {
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
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}{identity?.reasoning_effort && <b>{lang === "zh" ? "思考：最高" : "reasoning: max"}</b>}</div>
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
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}</div>
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

function tokenText(tokens: Record<string, number>, lang: Lang) {
  return GEM_ORDER.filter(color => (tokens[color] ?? 0) > 0)
    .map(color => `${GEM_META[color]?.label[lang] || color} × ${tokens[color]}`).join(lang === "zh" ? "、" : ", ");
}

function describeAction(item: Timeline, names: Record<number, string>, lang: Lang) {
  const t = makeT(lang); const event = item.event; const zh = lang === "zh";
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
    choose_initial_hand: "选择起始手牌", select_action: "选择行动牌", take_x_token: "替代 X-token 行动",
    draw_cards: "抽牌", snap_card: "拿取展示牌", discard_card: "弃牌", break_discard: "Break 弃牌",
    place_building: "放置建筑", play_animal: "打出动物", association_task: "协会任务",
    play_sponsor: "打出赞助商", advance_break: "推进 Break", finish_action: "结束行动",
    make_donation: "捐款", upgrade_action_card: "升级行动牌", keep_final_card: "选择终局牌",
    choose_conservation_bonus: "选择保育奖励", finish_association_tasks: "结束协会任务",
    discard_wild: "弃置万能牌", scout_discard_extra: "侦察弃牌", develop_tiles: "选择研发板块",
    build_industry: "选择产业与城市", build_link: "铺设运河", select_network_count: "铁路数量",
    select_network_link: "选择铁路", take_resource: "选择资源来源", sell_industry: "出售产业",
    finish_sell: "结束出售", merchant_bonus_develop: "商人研发奖励", liquidate_industry: "变卖产业",
    play_merchant: "打出商人牌", acquire_merchant: "获取商人牌", claim_point: "完成订单", rest: "休息",
  },
  en: {
    buy_visible: "Buy visible card", buy_reserved: "Buy reserved card", take_tokens: "Take gems",
    reserve_visible: "Reserve visible card", reserve_deck: "Reserve deck card", choose_noble: "Choose noble", pass: "Other",
    choose_initial_hand: "Choose starting hand", select_action: "Select action card", take_x_token: "X-token action",
    draw_cards: "Draw cards", snap_card: "Take display card", discard_card: "Discard card", break_discard: "Break discard",
    place_building: "Place building", play_animal: "Play animal", association_task: "Association task",
    play_sponsor: "Play sponsor", advance_break: "Advance Break", finish_action: "End action",
    make_donation: "Donate", upgrade_action_card: "Upgrade action card", keep_final_card: "Choose final card",
    choose_conservation_bonus: "Conservation bonus", finish_association_tasks: "End association tasks",
    discard_wild: "Discard wild card", scout_discard_extra: "Scout discard", develop_tiles: "Select develop tiles",
    build_industry: "Choose industry & city", build_link: "Build canal", select_network_count: "Rail count",
    select_network_link: "Choose rail link", take_resource: "Choose resource source", sell_industry: "Sell industry",
    finish_sell: "End sell", merchant_bonus_develop: "Merchant develop bonus", liquidate_industry: "Liquidate industry",
    play_merchant: "Play merchant card", acquire_merchant: "Acquire merchant card", claim_point: "Complete order", rest: "Rest",
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

const ARK_ACTION_LABELS: Record<Lang, Record<string, string>> = {
  zh: { animals: "动物", cards: "卡牌", build: "建造", association: "协会", sponsors: "赞助商" },
  en: { animals: "Animals", cards: "Cards", build: "Build", association: "Association", sponsors: "Sponsors" },
};

function ArkTrack({label, value, tone}: {label: string; value: number; tone: string}) {
  return <div className={`ark-track track-${tone}`}><span>{label}</span><div><i style={{width: `${Math.min(100, Math.max(3, value * 2.5))}%`}}/></div><b>{value}</b></div>;
}

function ArkZooMap({map}: {map: ArkMap}) {
  const lang = useLang();
  const occupied = new Set(map.buildings.flatMap(building => building.cells.map(cell => `${cell.q}:${cell.r}`)));
  return <div className="ark-map" aria-label={`${map.name} ${lang === "zh" ? "六角地图" : "hex map"}`}>
    {map.cells.map(cell => <i key={`${cell.q}:${cell.r}`} className={`ark-hex terrain-${cell.terrain} ${occupied.has(`${cell.q}:${cell.r}`) ? "is-built" : ""}`}
      style={{left: `calc(50% + ${cell.q * 25 + cell.r * 12.5}px)`, top: `calc(50% + ${cell.r * 22}px)`}}
      title={`(${cell.q}, ${cell.r}) · ${cell.terrain}`}/>) }
  </div>;
}

function ArkPlayerPanel({player: p, identity}: {player: ArkPlayerView; identity?: Snapshot["players"][number]}) {
  const lang = useLang(); const t = makeT(lang); const zh = lang === "zh";
  return <section className="player-panel ark-player-panel">
    <header><div><span className="seat-label">{t("seat_label")} {p.seat + 1}</span><h3>{identity?.name || `${t("player_label")} ${p.seat + 1}`}</h3></div><div className="ark-money"><strong>{p.money}</strong><span>₡</span></div></header>
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}</div>
    <div className="ark-mini-tracks"><span>{zh ? "吸引力" : "Appeal"} <b>{p.appeal}</b></span><span>{zh ? "保育" : "Conservation"} <b>{p.conservation}</b></span><span>{zh ? "声望" : "Reputation"} <b>{p.reputation}</b></span></div>
    <div className="ark-worker-row"><span>X TOKEN <b>{p.x_tokens}/5</b></span><span>{zh ? "协会工人" : "Assoc. workers"} <b>{p.association_workers.active}</b> + {p.association_workers.reserve}</span></div>
    <div className="ark-actions">{[...p.action_cards].sort((a, b) => b.strength - a.strength).map(card => <div key={card.action} className={`ark-action action-${card.action}`}><b>{card.strength}</b><span>{ARK_ACTION_LABELS[lang][card.action]}</span>{card.upgraded && <i>Ⅱ</i>}</div>)}</div>
    <div className="ark-hidden-row"><span>{zh ? "起始抽牌" : "Initial draw"} <b>{p.initial_draw_count}</b> / {zh ? "留" : "keep"} {p.initial_keep_required}</span><span>{zh ? "终局牌" : "Final cards"} <b>{p.final_scoring_cards.length}</b></span></div>
    <div className="ark-hidden-row"><span>{t("ark_partner")} <b>{p.partner_zoos.length}</b></span><span>{t("ark_uni")} <b>{p.universities.length}</b></span><span>{zh ? "项目" : "Projects"} <b>{p.supported_projects.length}</b></span></div>
    <div className="ark-hand-preview"><span>{t("hand")} {p.hand_count}</span>{p.hand.slice(0, 6).map((card, index) => <i key={card.id || index} title={card.id || "hidden"}>{card.hidden ? "?" : card.card_type?.slice(0, 1).toUpperCase()}</i>)}</div>
  </section>;
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
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}</div>
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

function ArkNovaBoard({view, players}: {view?: ArkView; players: Snapshot["players"]}) {
  const lang = useLang(); const t = makeT(lang); const zh = lang === "zh";
  if (!view) return null;
  return <div className="ark-board">
    <section className="ark-milestone"><div><span>{t("ark_eyebrow")}</span><h2>{view.phase === "initial_hand_selection" ? t("ark_phase_select") : t("ark_phase_play")}</h2></div><p>{t("ark_phase_note")}</p><code>{view.rules_version}</code></section>
    <section className="ark-track-board">
      <div><span>{t("ark_tracks")}</span><h3>{t("ark_tracks_h")}</h3></div>
      <div className="ark-track-stack"><ArkTrack label="BREAK" value={view.break_track.position} tone="break"/><ArkTrack label="ACTIVE APPEAL" value={view.players[view.active_seat]?.appeal || 0} tone="appeal"/><ArkTrack label="ACTIVE CONSERVATION" value={view.players[view.active_seat]?.conservation || 0} tone="conservation"/><ArkTrack label="ACTIVE REPUTATION" value={view.players[view.active_seat]?.reputation || 0} tone="reputation"/></div>
      <div className="ark-decision"><span>{t("cur_decision")}</span><strong>{view.turn.decision.replaceAll("_", " ")}</strong><small>{view.phase.replaceAll("_", " ")}</small></div>
    </section>
    <section className="ark-display"><header><div><span>{t("ark_display")}</span><h3>{t("ark_display_h")}</h3></div><b>{t("deck")} {view.deck_count} · {t("discard")} {view.discard_count}</b></header><div>{view.card_display.map((card, index) => <article key={card.id || index} className={card.hidden ? "is-facedown" : ""}><span>0{index + 1}</span><strong>{card.hidden ? t("ark_after_select") : card.card_type?.replaceAll("_", " ")}</strong><small>{card.tags?.join(" · ")}</small>{card.id && <code>{card.id}</code>}</article>)}</div></section>
    <section className="ark-association"><header><span>{t("ark_assoc")}</span><h3>{t("ark_assoc_h")}</h3></header><div className="ark-projects">{view.base_conservation_projects.map(project => <article key={project.id}><b>{project.tag}</b><span>{project.levels.join(" / ")}</span><code>{project.id}</code></article>)}</div><div className="ark-association-meta"><span>{t("ark_partner")} {Object.values(view.association_board.partner_zoos).filter(Boolean).length} {t("ark_avail")}</span><span>{t("ark_uni")} {Object.values(view.association_board.universities).filter(Boolean).length} {t("ark_avail")}</span><span>{t("ark_donation")} {view.association_board.donations?.length || 0}</span>{view.association_board.blocked_two_player.length > 0 && <span>{t("ark_blocked")} {view.association_board.blocked_two_player.length}</span>}</div></section>
    <section className="ark-zoo-section"><header><span>{t("ark_zoo")}</span><h3>{t("ark_zoo_h")}</h3></header><div>{view.players.map(player => <article key={player.seat}><div><strong>{players[player.seat]?.name || `${t("player_label")} ${player.seat + 1}`}</strong><span>{t("ark_zoo_unit")}</span></div><ArkZooMap map={player.map}/></article>)}</div><small>{t("ark_zoo_note")}</small></section>
  </div>;
}

export default function Home() {
  const [lang, setLang] = useState<Lang>("zh");
  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("abga-lang") : null;
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
  const humanSeat = snapshot?.human_turn?.seat ?? snapshot?.players.find(player => player.backend === "human")?.seat ?? 0;
  const viewer = snapshot?.views[humanSeat];
  const splendorView = snapshot?.game === "splendor" ? viewer as View : undefined;
  const arkView = snapshot?.game === "ark_nova" ? viewer as ArkView : undefined;
  const brassView = snapshot?.game === "brass_birmingham" ? viewer as BrassView : undefined;
  const centuryView = snapshot?.game === "century_spice_road" ? viewer as CenturyView : undefined;
  const maxPlayers = game === "century_spice_road" ? 5 : 4;
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

  function selectGame(next: GameId) {
    setGame(next);
    if (next !== "century_spice_road") setPlayers(current => current.slice(0, 4));
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
      <button className="lang-toggle" onClick={toggleLang} aria-label="Switch language">{zh ? "EN" : "中文"}</button>
      <div className="eyebrow">{t("hero_eyebrow")} / {GAME_COPY[game].eyebrow}</div>
      <h1>{t("hero_title_a")}<br/><i>{t("hero_title_b")}</i>{t("hero_title_c")}</h1>
      <p>{GAME_COPY[game].description[lang]}</p>
      <div className="hero-marks"><span>{t("hero_mark_1")}</span><span>{t("hero_mark_2")}</span><span>{game === "ark_nova" ? t("hero_mark_ark") : t("hero_mark_3")}</span></div>
    </section>
    <section className="setup-card">
      <div className="game-picker" role="group" aria-label={t("pick_game")}>{(Object.keys(GAME_COPY) as GameId[]).map(id => <button key={id} className={game === id ? "selected" : ""} onClick={() => selectGame(id)}><span>{GAME_COPY[id].badge}</span><b>{GAME_COPY[id].name[lang]}</b><small>{GAME_COPY[id].note[lang]}</small></button>)}</div>
      <header><div><span>{t("new_table")}</span><h2>{t("create_table")}{GAME_COPY[game].name[lang]}</h2></div><div className="matchup-presets"><button onClick={() => setMatchup("human")}>{t("g_human")}</button><button onClick={() => setMatchup("harness")}>{t("g_harness")}</button><b>{players.length} {t("players_count")}</b></div></header>
      <div className="players-config">{players.map((p, index) => <article className="player-config" key={p.id}>
        <div className="seat-order"><b>0{index + 1}</b><div><button disabled={index === 0} aria-label={`${p.name} ${t("move_up")}`} onClick={() => movePlayer(index, -1)}>↑</button><button disabled={index === players.length - 1} aria-label={`${p.name} ${t("move_down")}`} onClick={() => movePlayer(index, 1)}>↓</button></div></div>
        <div className="field grow"><label htmlFor={`${p.id}-name`}>{t("f_name")}</label><input id={`${p.id}-name`} value={p.name} onChange={e => updatePlayer(p.id, {name: e.target.value})}/></div>
        {!(["random", "human"] as Backend[]).includes(p.backend) && <>
          <div className="field provider-field"><label htmlFor={`${p.id}-provider`}>{t("f_provider")}</label><select id={`${p.id}-provider`} value={p.provider} onChange={e => selectProvider(p.id, e.target.value as Provider)}><optgroup label={t("og_harness")}>{(["claude_code", "pi", "codex", "opencode", "dsh", "minimal"] as Provider[]).map(id => <option key={id} value={id}>{PROVIDERS[id].label[lang]}</option>)}</optgroup><optgroup label={t("og_direct")}>{(["custom", "deepseek", "dashscope", "zhipu", "minimax"] as Provider[]).map(id => <option key={id} value={id}>{PROVIDERS[id].label[lang]}</option>)}</optgroup></select></div>
          <div className="field backend-field"><label htmlFor={`${p.id}-backend`}>{t("f_backend")}</label><select id={`${p.id}-backend`} value={p.backend} onChange={e => updatePlayer(p.id, {backend: e.target.value as Backend})}>{Object.entries(BACKENDS).filter(([id]) => id !== "random").map(([id, b]) => <option key={id} value={id}>{b.label[lang]}</option>)}</select></div>
          <div className="field grow endpoint-field"><label htmlFor={`${p.id}-endpoint`}>{t("f_endpoint")}</label><input id={`${p.id}-endpoint`} value={p.base_url} onChange={e => updatePlayer(p.id, {provider: "custom", base_url: e.target.value})}/></div>
          <div className="field model-field"><label htmlFor={`${p.id}-model`}>{t("f_model")}</label><input id={`${p.id}-model`} list={`${p.id}-models`} placeholder={t("ph_model")} value={p.model} onChange={e => updatePlayer(p.id, {model: e.target.value})}/><datalist id={`${p.id}-models`}>{PROVIDERS[p.provider].models.map(model => <option key={model} value={model}/>)}</datalist></div>
          <div className="field key-field"><label htmlFor={`${p.id}-key`}>{t("f_key")}</label><input id={`${p.id}-key`} type="password" autoComplete="off" placeholder={t("ph_key")} value={p.api_key} onChange={e => updatePlayer(p.id, {api_key: e.target.value})}/></div>
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
      {game === "ark_nova" && <div className="setup-scope-note"><b>{GAME_COPY.ark_nova.badge}</b> {zh ? "已支持行动升级、合作动物园折扣、捐款、释放动物、地图奖励、效果原语和终局目标；仍使用结构化研究卡池与示意 Map A，并非完整商业卡池复刻。" : "Supports action upgrades, partner-zoo discounts, donations, animal release, map rewards, effect primitives, final objectives; uses a structured research-card pool and schematic Map A, not the full commercial pool."}</div>}
      {game === "brass_birmingham" && <div className="setup-scope-note"><b>{GAME_COPY.brass_birmingham.badge}</b> {zh ? "支持官方人数牌组、产业板、市场、商人、Build/Sell/Develop、单双铁路、负收入变卖、双时代计分与完整回放；界面不包含出版商美术。" : "Supports official player counts, industry board, markets, merchants, Build/Sell/Develop, single/double rail, negative-income liquidation, two-era scoring and full replay; no publisher artwork."}</div>}
      {game === "century_spice_road" && <div className="setup-scope-note"><b>{GAME_COPY.century_spice_road.badge}</b> {zh ? "完整基础牌组数值、重复交易、升级、市场压香料、商队容量、金币银币、终局与计分均已接通；不包含出版商卡图。" : "Full base-set values, repeat trades, upgrades, market spice, caravan capacity, gold/silver coins, endgame and scoring wired up; no publisher artwork."}</div>}
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
        // Render the whole table from the human seat. Without a human, seat 0 is the spectator view.
        const visiblePlayer = viewer?.players[identity.seat];
        return snapshot.game === "splendor"
          ? <PlayerPanel key={identity.seat} player={visiblePlayer as PlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>
          : snapshot.game === "ark_nova"
            ? <ArkPlayerPanel key={identity.seat} player={visiblePlayer as ArkPlayerView} identity={identity}/>
            : snapshot.game === "brass_birmingham"
              ? <BrassPlayerPanel key={identity.seat} player={visiblePlayer as BrassPlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>
              : <CenturyPlayerPanel key={identity.seat} player={visiblePlayer as CenturyPlayerView} identity={identity} active={snapshot.status === "active" && snapshot.active_seat === identity.seat}/>;
      })}</aside>
      <section className="board">
        {snapshot.paused && <div className={`pause-notice ${snapshot.pause_pending ? "pending" : ""}`}><strong>{snapshot.pause_pending ? t("pause_pending") : t("paused")}</strong><span>{snapshot.pause_pending ? t("pause_pending_desc") : t("paused_desc")}</span></div>}
        {snapshot.human_turn && <section className="human-turn" aria-live="polite">
          <header><div><span>YOUR TURN · SEAT {snapshot.human_turn.seat + 1}</span><h2>{snapshot.human_turn.player}{t("pick_action")}</h2></div><b>{snapshot.human_turn.legal_actions.length} {t("legal_opts")}</b></header>
          <div className="human-action-groups">{Object.entries(groupActions(snapshot.human_turn.legal_actions)).map(([kind, actions]) => <section key={kind}>
            <h3>{ACTION_GROUPS[lang][kind] || kind}<span>{actions.length}</span></h3>
            <div className={CARD_ACTION_TYPES.has(kind) ? "card-action-grid" : kind === "take_tokens" ? "token-action-grid" : undefined}>{actions.map(item => <HumanActionChoice key={item.id} item={item} view={splendorView} brassView={brassView} disabled={Boolean(submittingAction)} submitting={submittingAction === item.id} onChoose={() => submitHumanAction(item)}/>)}</div>
          </section>)}</div>
        </section>}
        {snapshot.game === "splendor" ? <SplendorBoard view={splendorView}/> : snapshot.game === "ark_nova" ? <ArkNovaBoard view={arkView} players={snapshot.players}/> : snapshot.game === "brass_birmingham" ? <BrassBoard view={brassView} players={snapshot.players}/> : <CenturyBoard view={centuryView}/>}
        {snapshot.status === "finished" && <div className="winner-banner"><span>{t("winner")}</span><strong>{timeline.at(-1)?.event.rankings?.[0]?.player || t("match_over")}</strong><button onClick={() => { setSnapshot(null); setTimeline([]); }}>{t("play_again")}</button></div>}
      </section>
      <aside className="timeline">
        <header><div><span>{t("model_stream")}</span><h2>{t("chat_h")}</h2></div><i className={snapshot.status === "active" && (!snapshot.paused || snapshot.pause_pending) ? "pulse" : ""}/></header>
        <div className="chat-list">{chat.length === 0 && <p className="waiting">{snapshot.game_description.runnable ? t("waiting_model") : t("waiting_note")}</p>}{chat.map(turn => <article className={`chat-turn chat-${turn.status}`} key={turn.key}>
          <header><strong>{turn.player}</strong><span>{turn.backend} · {t("attempt")} {turn.attempt}{turn.status === "thinking" ? ` · ${t("generating")}` : turn.latencyMs ? ` · ${(turn.latencyMs / 1000).toFixed(1)}s` : ""}</span></header>
          {turn.reasoning && <details open><summary>{t("thinking")}{turn.status === "done" ? ` · ${t("collapsible")}` : ""}</summary><pre>{turn.reasoning}</pre></details>}
          {turn.content && <div className="model-answer"><b>{t("answer")}</b><pre>{turn.content}</pre></div>}
          {turn.status === "thinking" && <div className="typing"><i/><i/><i/></div>}
        </article>)}</div>
        <section className="action-drawer"><header><span>{t("actions")}</span><strong>{t("decision_log")}</strong><b>{timeline.filter(item => ["decision", "turn"].includes(item.event.type)).length}</b></header>
          <div>{[...timeline].reverse().filter(item => !["agent_started", "agent_finished"].includes(item.event.type)).slice(0, 40).map(item => <article key={item.seq} className={`event event-${item.event.type}`}>
            <span>{String(item.seq + 1).padStart(3,"0")}</span><div><p>{describeAction(item, names, lang)}</p>{item.event.backend && <small>{item.event.backend}{item.event.agent?.latency_ms ? ` · ${item.event.agent.latency_ms}ms` : ""}</small>}
              {item.event.tool && (item.event.arguments !== undefined || item.event.result !== undefined) && <details className="tool-payload"><summary>{t("view_tool")}</summary><pre>{JSON.stringify(item.event.result ?? item.event.arguments, null, 2)}</pre></details>}
            </div>
          </article>)}</div>
        </section>
      </aside>
    </div>
  </main>;
}
