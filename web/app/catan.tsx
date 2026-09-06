"use client";

import { useState, type CSSProperties, type KeyboardEvent } from "react";

type Lang = "zh" | "en";
type Resource = "brick" | "lumber" | "wool" | "grain" | "ore";
type Action = {id: string; action: Record<string, unknown>};
type Identity = {seat: number; name: string; backend: string; model?: string; reasoning_effort?: string};
type Vertex = {id: number; x: number; y: number; hexes: number[]; edges: number[]; building: {seat: number; type: "settlement" | "city"} | null; port: "any" | Resource | null};
export type CatanPlayerView = {
  seat: number; resource_count: number; development_count: number; played_knights: number;
  longest_road_length: number; public_score: number; score: number | null;
  roads_remaining: number; settlements_remaining: number; cities_remaining: number;
  resources: Record<Resource, number> | null;
  development_cards: {id: string; type: string; bought_turn: number}[] | null;
};
export type CatanView = {
  game: "catan"; rules_version: string; status: string; phase: string; active_seat: number; turn_seat: number;
  turn_count: number; decision_count: number; robber_hex: number; last_roll: number[] | null;
  bank: Record<Resource, number>; players: CatanPlayerView[]; development_deck_count: number;
  longest_road_seat: number | null; largest_army_seat: number | null;
  discard_remaining: number[]; free_roads_remaining: number;
  trade: Record<string, unknown> | null;
  board: {
    hexes: {id: number; q: number; r: number; x: number; y: number; terrain: Resource | "desert"; number: number | null; vertices: number[]; edges: number[]}[];
    vertices: Vertex[]; edges: {id: number; vertices: number[]; owner: number | null}[];
    ports: {id: number; vertices: number[]; resource: "any" | Resource}[];
  };
};

const RESOURCES: Resource[] = ["brick", "lumber", "wool", "grain", "ore"];
const RESOURCE_META: Record<Resource | "desert", {zh: string; en: string; symbol: string}> = {
  brick: {zh: "砖块", en: "Brick", symbol: "🧱"}, lumber: {zh: "木材", en: "Lumber", symbol: "🪵"},
  wool: {zh: "羊毛", en: "Wool", symbol: "🐑"}, grain: {zh: "谷物", en: "Grain", symbol: "🌾"},
  ore: {zh: "矿石", en: "Ore", symbol: "🪨"}, desert: {zh: "沙漠", en: "Desert", symbol: "☀"},
};
const DEVELOPMENT: Record<string, {zh: string; en: string}> = {
  knight: {zh: "骑士", en: "Knight"}, road_building: {zh: "筑路", en: "Road building"},
  year_of_plenty: {zh: "丰收", en: "Year of plenty"}, monopoly: {zh: "垄断", en: "Monopoly"},
  victory_point: {zh: "胜利点", en: "Victory point"},
};
const SEAT_COLORS = ["#c45137", "#347ba3", "#efc053", "#775694"];
const ACTION_LABELS: Record<string, {zh: string; en: string}> = {
  place_settlement: {zh: "起始村落", en: "Starting settlement"}, place_road: {zh: "起始道路", en: "Starting road"},
  roll_dice: {zh: "掷骰", en: "Roll dice"}, build_road: {zh: "修建道路", en: "Build road"},
  build_settlement: {zh: "建造村落", en: "Build settlement"}, build_city: {zh: "升级城市", en: "Upgrade to city"},
  buy_development_card: {zh: "购买发展卡", en: "Buy development card"}, play_knight: {zh: "打出骑士", en: "Play knight"},
  play_road_building: {zh: "打出筑路", en: "Play road building"}, play_year_of_plenty: {zh: "打出丰收", en: "Play year of plenty"},
  play_monopoly: {zh: "打出垄断", en: "Play monopoly"}, maritime_trade: {zh: "海上贸易", en: "Maritime trade"},
  end_turn: {zh: "结束回合", en: "End turn"}, discard: {zh: "弃置资源", en: "Discard resource"},
  move_robber: {zh: "移动强盗", en: "Move robber"}, steal: {zh: "抽取资源", en: "Steal resource"},
  free_road: {zh: "免费修路", en: "Free road"}, finish_road_building: {zh: "结束筑路", en: "Finish road building"},
  take_resource: {zh: "选择资源", en: "Choose resource"}, propose_trade: {zh: "向玩家提议交易", en: "Propose player trade"},
  trade_amount: {zh: "选择交易资源与数量", en: "Choose trade resource and amount"},
  counter_trade: {zh: "提出还价", en: "Make counteroffer"},
  cancel_trade: {zh: "取消交易", en: "Cancel trade"}, respond_trade: {zh: "回应交易", en: "Respond to trade"},
};

function resourceName(value: unknown, lang: Lang) {
  return RESOURCE_META[String(value) as Resource]?.[lang] || (value == null ? (lang === "zh" ? "资源" : "resource") : String(value));
}

export function catanActionText(action: Record<string, unknown>, lang: Lang): string | null {
  const kind = String(action.type);
  const zh = lang === "zh";
  if (!(kind in ACTION_LABELS) || (kind === "take_resource" && ("source" in action || "source_id" in action))) return null;
  const label = ACTION_LABELS[kind][lang];
  if ("vertex" in action) return `${label} · ${zh ? "交点" : "vertex"} ${action.vertex}`;
  if ("edge" in action) return `${label} · ${zh ? "道路位" : "edge"} ${action.edge}`;
  if (kind === "move_robber") return `${label} · ${zh ? "地块" : "hex"} ${action.hex}`;
  if (kind === "steal") return action.victim == null ? (zh ? "完成强盗移动（没有可抽取的玩家）" : "Finish robber move (no player to steal from)") : (zh ? `随机抽取座位 ${Number(action.victim) + 1} 的一张资源` : `Steal one random resource from seat ${Number(action.victim) + 1}`);
  if (kind === "maritime_trade") return zh ? `支付 ${action.ratio} ${resourceName(action.give, lang)}，换取 1 ${resourceName(action.receive, lang)}` : `Trade ${action.ratio} ${resourceName(action.give, lang)} for 1 ${resourceName(action.receive, lang)}`;
  if (["play_monopoly", "discard", "take_resource"].includes(kind)) return `${label} · ${resourceName(action.resource, lang)}${kind === "play_monopoly" ? "" : " × 1"}`;
  if (kind === "propose_trade") return `${label} · ${zh ? "座位" : "seat"} ${Number(action.partner) + 1}`;
  if (kind === "trade_amount") return `${resourceName(action.resource, lang)} × ${action.amount}`;
  if (kind === "respond_trade") return action.accept ? (zh ? "接受交易" : "Accept trade") : (zh ? "拒绝交易" : "Decline trade");
  return label;
}

function CatanResources({pool, lang}: {pool: Partial<Record<Resource, number>>; lang: Lang}) {
  return <div className="catan-resources">{RESOURCES.map(resource => <span className={`catan-resource resource-${resource}`} key={resource} title={RESOURCE_META[resource][lang]}><i aria-hidden="true">{RESOURCE_META[resource].symbol}</i><span>{RESOURCE_META[resource][lang]}</span><b>{pool[resource] ?? 0}</b></span>)}</div>;
}

export function CatanPlayerPanel({player: p, identity, active, lang}: {player: CatanPlayerView; identity: Identity; active: boolean; lang: Lang}) {
  const zh = lang === "zh";
  if (!p) return null;
  return <section className={`player-panel catan-player-panel ${active ? "active-player" : ""}`} style={{"--seat-color": SEAT_COLORS[p.seat]} as CSSProperties}>
    <header><div><span className="seat-label">{zh ? "座位" : "Seat"} {p.seat + 1}</span><h3><i className="catan-seat-color"/>{identity.name}</h3></div><div className="score"><strong>{p.score ?? p.public_score}</strong><span>VP</span></div></header>
    <div className="model-line"><span>{identity.backend}</span>{identity.model && <code>{identity.model}</code>}{identity.reasoning_effort && <b>{identity.reasoning_effort}</b>}</div>
    <div className="catan-player-resources"><header><span>{zh ? "资源手牌" : "Resource cards"}</span><b>{p.resource_count}</b></header>{p.resources ? <CatanResources pool={p.resources} lang={lang}/> : <p>{zh ? "对手资源种类保密" : "Resource types are private"}</p>}</div>
    <div className="catan-player-stats"><span>{zh ? "最长道路" : "Road length"}<b>{p.longest_road_length}</b></span><span>{zh ? "已用骑士" : "Knights played"}<b>{p.played_knights}</b></span></div>
    <div className="catan-piece-supply"><span>{zh ? "剩余棋子" : "Pieces left"}</span><b>{zh ? "道路" : "Roads"} {p.roads_remaining}</b><b>{zh ? "村落" : "Settlements"} {p.settlements_remaining}</b><b>{zh ? "城市" : "Cities"} {p.cities_remaining}</b></div>
    <div className="catan-development"><header><span>{zh ? "发展卡" : "Development cards"}</span><b>{p.development_count}</b></header>{p.development_cards?.map(card => <span key={card.id}>{DEVELOPMENT[card.type]?.[lang] || card.type}</span>)}{p.development_cards === null && p.development_count > 0 && <small>{zh ? "牌面保密" : "Card faces are private"}</small>}</div>
    {p.score === null && <small className="catan-public-score">{zh ? "显示公开胜利点" : "Showing public victory points"}</small>}
  </section>;
}

export function CatanActionPicker({actions, lang, disabled, selectedId, onChoose}: {actions: Action[]; lang: Lang; disabled: boolean; selectedId: string; onChoose: (action: Action) => void}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const groups = Object.groupBy(actions, item => String(item.action.type));
  return <div className="catan-action-picker">{Object.entries(groups).map(([kind, items = []]) => <section key={kind}>
    {items.length > 6 ? <button className="catan-action-group-toggle" aria-expanded={expanded === kind} onClick={() => setExpanded(expanded === kind ? null : kind)}>{ACTION_LABELS[kind]?.[lang] || kind}<b>{items.length} {expanded === kind ? "−" : "+"}</b></button> : <h3>{ACTION_LABELS[kind]?.[lang] || kind}</h3>}
    {(items.length <= 6 || expanded === kind) && <div>{items.map(item => <button key={item.id} disabled={disabled} className={selectedId === item.id ? "selected" : ""} aria-pressed={selectedId === item.id} onClick={() => onChoose(item)}>{catanActionText(item.action, lang)}</button>)}</div>}
  </section>)}</div>;
}

export function CatanBoard({view, players, lang, humanActions = [], disabled = false, selectedActionId, onChoose}: {view?: CatanView; players: Identity[]; lang: Lang; humanActions?: Action[]; disabled?: boolean; selectedActionId?: string; onChoose: (action: Action) => void}) {
  if (!view) return null;
  const zh = lang === "zh";
  const vertices = new Map(view.board.vertices.map(vertex => [vertex.id, vertex]));
  const xs = view.board.vertices.map(vertex => vertex.x * 72), ys = view.board.vertices.map(vertex => vertex.y * 72);
  const minimumX = Math.min(...xs) - 58, minimumY = Math.min(...ys) - 58;
  const width = Math.max(...xs) - minimumX + 58, height = Math.max(...ys) - minimumY + 58;
  const names = (seat: number | null) => seat === null ? (zh ? "尚无" : "Unclaimed") : players.find(player => player.seat === seat)?.name || `${zh ? "座位" : "Seat"} ${seat + 1}`;
  const phases: Record<string, string> = zh ? {
    setup_settlement: "放置起始村落", setup_road: "放置起始道路", roll: "准备掷骰", main: "建造与贸易", discard: "弃置资源", robber: "移动强盗", steal: "抽取资源", free_roads: "免费修路", year_of_plenty: "选择丰收资源", trade_give: "选择付出的资源", trade_receive: "选择换取的资源", trade_response: "回应交易",
  } : {
    setup_settlement: "Place starting settlement", setup_road: "Place starting road", roll: "Ready to roll", main: "Build and trade", discard: "Discard resources", robber: "Move robber", steal: "Steal a resource", free_roads: "Build free roads", year_of_plenty: "Choose harvest resources", trade_give: "Choose resources to give", trade_receive: "Choose resources to receive", trade_response: "Respond to trade",
  };
  const activate = (item: Action | undefined) => {if (item && !disabled) onChoose(item);};
  const keyboard = (event: KeyboardEvent<SVGGElement>, item: Action | undefined) => {if (event.key === "Enter" || event.key === " ") {event.preventDefault(); activate(item);}};
  const targetAction = (field: string, id: number) => humanActions.find(item => item.action[field] === id);
  return <div className="catan-board">
    <section className="catan-status"><div><span>CATAN</span><h2>{phases[view.phase] || view.phase.replaceAll("_", " ")}</h2><p>{zh ? "当前回合" : "Turn"}: {names(view.turn_seat)} · {zh ? "当前行动" : "Acting"}: {names(view.active_seat)}</p></div><div className="catan-dice"><span>{zh ? "上次掷骰" : "Last roll"}</span><strong>{view.last_roll ? `${view.last_roll[0]} + ${view.last_roll[1]} = ${view.last_roll.reduce((sum, die) => sum + die, 0)}` : "—"}</strong></div></section>
    <section className="catan-bank"><header><h3>{zh ? "资源银行" : "Resource bank"}</h3><span>{zh ? "发展卡牌库" : "Development deck"} <b>{view.development_deck_count}</b></span></header><CatanResources pool={view.bank} lang={lang}/></section>
    <div className="catan-map-heading"><h3>{zh ? "卡坦岛" : "Catan island"}</h3><span>{humanActions.some(item => "vertex" in item.action || "edge" in item.action || "hex" in item.action) ? (zh ? "选择发亮的位置，再确认提交" : "Choose a highlighted location, then confirm") : (zh ? "交点与道路编号对应行动选项" : "Vertex and road numbers match action choices")}</span></div>
    <div className="catan-map"><svg viewBox={`${minimumX} ${minimumY} ${width} ${height}`} aria-label={zh ? "卡坦岛地块、村落、城市与道路" : "Catan hexes, settlements, cities and roads"}>
      <g className="catan-hexes">{view.board.hexes.map(hex => {
        const item = targetAction("hex", hex.id), isRobber = view.robber_hex === hex.id;
        const label = `${zh ? "地块" : "Hex"} ${hex.id} · ${RESOURCE_META[hex.terrain][lang]}${hex.number ? ` · ${hex.number}` : ""}${isRobber ? ` · ${zh ? "强盗" : "Robber"}` : ""}`;
        return <g key={hex.id} className={`catan-hex terrain-${hex.terrain} ${item ? "actionable" : ""} ${item?.id === selectedActionId ? "selected" : ""}`} role={item ? "button" : undefined} tabIndex={item && !disabled ? 0 : undefined} aria-label={item ? catanActionText(item.action, lang) || label : label} aria-disabled={item ? disabled : undefined} onClick={() => activate(item)} onKeyDown={event => keyboard(event, item)}>
          <title>{label}</title><polygon points={hex.vertices.map(id => vertices.get(id)).filter((vertex): vertex is Vertex => Boolean(vertex)).map(vertex => `${vertex.x * 72},${vertex.y * 72}`).join(" ")}/>
          <text x={hex.x * 72} y={hex.y * 72 - 27} className="catan-terrain-label">{RESOURCE_META[hex.terrain].symbol} {RESOURCE_META[hex.terrain][lang]}</text>
          <circle cx={hex.x * 72} cy={hex.y * 72 + 1} r={18} className={`catan-number-token ${[6, 8].includes(hex.number ?? 0) ? "frequent" : ""}`}/>
          <text x={hex.x * 72} y={hex.y * 72 + 7} className={`catan-number ${[6, 8].includes(hex.number ?? 0) ? "frequent" : ""}`}>{isRobber ? "♟" : hex.number ?? "—"}</text>
          <text x={hex.x * 72} y={hex.y * 72 + 35} className="catan-hex-id">{isRobber ? `${zh ? "强盗" : "Robber"} · ` : ""}{hex.id}</text>
        </g>;
      })}</g>
      <g className="catan-ports">{view.board.ports.map(port => {
        const [a, b] = port.vertices.map(id => vertices.get(id));
        if (!a || !b) return null;
        const x = (a.x + b.x) * 36, y = (a.y + b.y) * 36;
        const centerX = (minimumX + width / 2), centerY = (minimumY + height / 2);
        const length = Math.hypot(x - centerX, y - centerY) || 1;
        const dx = (x - centerX) / length * 32, dy = (y - centerY) / length * 32;
        return <g key={port.id}><title>{port.resource === "any" ? (zh ? "通用港口 3:1" : "Generic harbor 3:1") : `${resourceName(port.resource, lang)} 2:1`}</title><line x1={x} y1={y} x2={x + dx} y2={y + dy}/><rect x={x + dx - 27} y={y + dy - 12} width={54} height={24} rx={8}/><text x={x + dx} y={y + dy + 5}>{port.resource === "any" ? "⚓ 3:1" : `${RESOURCE_META[port.resource].symbol} 2:1`}</text></g>;
      })}</g>
      <g className="catan-roads">{view.board.edges.map(edge => {
        const [a, b] = edge.vertices.map(id => vertices.get(id));
        if (!a || !b) return null;
        const item = targetAction("edge", edge.id), owned = edge.owner !== null;
        const label = item ? catanActionText(item.action, lang) || "" : `${zh ? "道路位" : "Edge"} ${edge.id}${owned ? ` · ${names(edge.owner)}` : ""}`;
        return <g key={edge.id} style={{"--seat-color": owned ? SEAT_COLORS[edge.owner!] : "#eee3be"} as CSSProperties} className={`catan-road ${owned ? "owned" : ""} ${item ? "actionable" : ""} ${item?.id === selectedActionId ? "selected" : ""}`} role={item ? "button" : undefined} tabIndex={item && !disabled ? 0 : undefined} aria-label={label} aria-disabled={item ? disabled : undefined} onClick={() => activate(item)} onKeyDown={event => keyboard(event, item)}>
          <title>{label}</title><line className="catan-road-hit" x1={a.x * 72} y1={a.y * 72} x2={b.x * 72} y2={b.y * 72}/><line className="catan-road-visible" x1={a.x * 72} y1={a.y * 72} x2={b.x * 72} y2={b.y * 72}/>{item && <text x={(a.x + b.x) * 36} y={(a.y + b.y) * 36 + 4}>{edge.id}</text>}
        </g>;
      })}</g>
      <g className="catan-vertices">{view.board.vertices.map(vertex => {
        const item = targetAction("vertex", vertex.id), building = vertex.building;
        const label = item ? catanActionText(item.action, lang) || "" : `${zh ? "交点" : "Vertex"} ${vertex.id}${building ? ` · ${names(building.seat)} · ${building.type === "city" ? (zh ? "城市" : "City") : (zh ? "村落" : "Settlement")}` : ""}`;
        return <g key={vertex.id} transform={`translate(${vertex.x * 72} ${vertex.y * 72})`} style={{"--seat-color": building ? SEAT_COLORS[building.seat] : "#fffaf0"} as CSSProperties} className={`catan-vertex ${building ? `built ${building.type}` : ""} ${item ? "actionable" : ""} ${item?.id === selectedActionId ? "selected" : ""}`} role={item ? "button" : undefined} tabIndex={item && !disabled ? 0 : undefined} aria-label={label} aria-disabled={item ? disabled : undefined} onClick={() => activate(item)} onKeyDown={event => keyboard(event, item)}>
          <title>{label}</title>{building?.type === "city" ? <rect x={-13} y={-13} width={26} height={26} rx={3}/> : <circle r={building ? 12 : item ? 12 : 8}/>}<text y={4}>{vertex.id}</text>{building?.type === "city" && <text y={-17} className="catan-city-mark">{zh ? "城" : "CITY"}</text>}
        </g>;
      })}</g>
    </svg></div>
    <div className="catan-map-legend"><span>● {zh ? "村落" : "Settlement"}</span><span>■ {zh ? "城市" : "City"}</span><span>♟ {zh ? "强盗" : "Robber"}</span>{players.map(identity => <span key={identity.seat}><i style={{background: SEAT_COLORS[identity.seat]}}/>{identity.name}</span>)}</div>
    <section className="catan-awards"><div><span>{zh ? "最长道路 · 2 VP" : "Longest road · 2 VP"}</span><strong>{names(view.longest_road_seat)}</strong></div><div><span>{zh ? "最大骑士军 · 2 VP" : "Largest army · 2 VP"}</span><strong>{names(view.largest_army_seat)}</strong></div></section>
    <section className="catan-costs"><h3>{zh ? "建造费用" : "Building costs"}</h3><span>{zh ? "道路" : "Road"}: 🧱 + 🪵</span><span>{zh ? "村落" : "Settlement"}: 🧱 + 🪵 + 🐑 + 🌾</span><span>{zh ? "城市" : "City"}: 🌾 × 2 + 🪨 × 3</span><span>{zh ? "发展卡" : "Development"}: 🐑 + 🌾 + 🪨</span></section>
  </div>;
}
