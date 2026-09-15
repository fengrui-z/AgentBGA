"use client";

type Lang = "zh" | "en";
type BurgundyColor = "building" | "livestock" | "monastery" | "castle" | "mine" | "ship";
type BurgundyCell = {
  id: string; q: number; r: number; color: BurgundyColor; region: string;
  number: number; tile_id: string | null;
};
export type BurgundyPlayer = {
  seat: number; score: number; silver: number; workers: number; bridge: number;
  storage: string[]; goods: Record<string, string[]>; sold_goods: string[];
  duchy: BurgundyCell[];
};
export type BurgundyView = {
  game: "castles_of_burgundy"; rules_version: string; implementation_status: string;
  viewer_seat: number; status: string; phase: string; phase_number: number;
  round_number: number; turn_count: number; active_seat: number; turn_order: number[];
  round_order: number[]; white_die: number; round_dice: Record<string, number[]>;
  remaining_dice: {index: number; value: number}[]; free_actions: number;
  bought_this_turn: boolean; depots: {number: number; tiles: string[]; goods: string[]}[];
  black_depot: string[]; color_bonus_claims: Record<BurgundyColor, number[]>;
  players: BurgundyPlayer[];
};
type PlayerIdentity = {
  seat: number; name: string; backend: string; model?: string; reasoning_effort?: string;
};

const COLOR_META: Record<BurgundyColor, {symbol: string; zh: string; en: string}> = {
  building: {symbol: "⌂", zh: "城镇", en: "Town"},
  livestock: {symbol: "♞", zh: "牧场", en: "Pasture"},
  monastery: {symbol: "✦", zh: "修道院", en: "Monastery"},
  castle: {symbol: "♜", zh: "城堡", en: "Castle"},
  mine: {symbol: "◆", zh: "矿山", en: "Mine"},
  ship: {symbol: "≈", zh: "河流", en: "River"},
};

function tileColor(tileId: string | null): BurgundyColor | null {
  if (!tileId) return null;
  if (tileId === "starting-castle") return "castle";
  const id = tileId.startsWith("black-") ? tileId.slice(6) : tileId;
  return (Object.keys(COLOR_META) as BurgundyColor[])
    .find(color => id.startsWith(color)) ?? null;
}

function BurgundyTile({tileId, compact = false}: {tileId: string; compact?: boolean}) {
  const color = tileColor(tileId) || "castle";
  const black = tileId.startsWith("black-");
  return <i className={`burgundy-tile tile-${color} ${black ? "tile-black" : ""} ${compact ? "compact" : ""}`} title={tileId}>
    <b>{COLOR_META[color].symbol}</b><span>{compact ? "" : COLOR_META[color].en}</span>
  </i>;
}

export function BurgundyPlayerPanel({
  player: p, identity, active, lang,
}: {player: BurgundyPlayer; identity?: PlayerIdentity; active: boolean; lang: Lang}) {
  const zh = lang === "zh";
  const goods = Object.values(p.goods).reduce((sum, pile) => sum + pile.length, 0);
  const placed = p.duchy.filter(cell => cell.tile_id !== null).length;
  return <section className={`player-panel burgundy-player-panel ${active ? "active-player" : ""}`}>
    <header><div><span className="seat-label">{zh ? "座位" : "Seat"} {p.seat + 1}</span><h3>{identity?.name || `${zh ? "玩家" : "Player"} ${p.seat + 1}`}</h3></div><div className="burgundy-score"><strong>{p.score}</strong><span>VP</span></div></header>
    <div className="model-line"><span>{identity?.backend}</span>{identity?.model && <code>{identity.model}</code>}{identity?.reasoning_effort && <b>{zh ? `思考：${identity.reasoning_effort}` : `reasoning: ${identity.reasoning_effort}`}</b>}</div>
    <div className="burgundy-assets"><span>◉ <b>{p.silver}</b> {zh ? "银币" : "silver"}</span><span>⚒ <b>{p.workers}</b> {zh ? "工人" : "workers"}</span><span>↥ <b>{p.bridge}</b> {zh ? "顺位" : "bridge"}</span></div>
    <div className="burgundy-progress"><span>{zh ? "领地" : "Duchy"} <b>{placed}/37</b></span><span>{zh ? "货物" : "Goods"} <b>{goods}</b></span><span>{zh ? "已售" : "Sold"} <b>{p.sold_goods.length}</b></span></div>
    <div className="burgundy-storage"><span>{zh ? "板块仓储" : "Hex storage"} {p.storage.length}/3</span><div>{p.storage.map(tile => <BurgundyTile key={tile} tileId={tile} compact/>)}{p.storage.length === 0 && <em>—</em>}</div></div>
  </section>;
}

function BurgundyDuchy({player, lang}: {player: BurgundyPlayer; lang: Lang}) {
  return <section className="burgundy-duchy"><header><div><span>DUCHY NO. 1</span><h3>{lang === "zh" ? `座位 ${player.seat + 1} 的领地` : `Seat ${player.seat + 1} duchy`}</h3></div><b>{player.duchy.filter(cell => cell.tile_id).length}/37</b></header>
    <div className="burgundy-hex-map">{player.duchy.map(cell => <i key={cell.id} className={`burgundy-hex hex-${cell.color} ${cell.tile_id ? "occupied" : ""}`}
      style={{left:`calc(50% + ${cell.q * 39 + cell.r * 19.5}px)`, top:`calc(50% + ${cell.r * 34}px)`}}
      title={`${COLOR_META[cell.color][lang]} · ${cell.region} · ${cell.number}`}>
      <small>{cell.number}</small>{cell.tile_id && <BurgundyTile tileId={cell.tile_id} compact/>}
    </i>)}</div>
  </section>;
}

export function BurgundyTable({view, lang}: {view?: BurgundyView; lang: Lang}) {
  const zh = lang === "zh";
  if (!view) return null;
  const player = view.players[view.viewer_seat];
  return <div className="burgundy-board">
    <section className="burgundy-status"><div><span>THE CASTLES OF BURGUNDY · 2019 BASE</span><h2>{zh ? `阶段 ${view.phase_number} · 第 ${view.round_number} 轮` : `Phase ${view.phase_number} · Round ${view.round_number}`}</h2></div><div className="burgundy-dice"><span>{zh ? "白骰" : "White"} <b>{view.white_die}</b></span>{Object.entries(view.round_dice).map(([seat, dice]) => <span key={seat}>S{Number(seat) + 1} <b>{dice.join(" · ")}</b></span>)}</div><code>{view.rules_version}</code></section>
    <section className="burgundy-depots"><header><div><span>NUMBERED DEPOTS</span><h3>{zh ? "六座仓库" : "Six depots"}</h3></div><b>{zh ? `当前顺位 ${view.turn_order.map(seat => seat + 1).join(" → ")}` : `Order ${view.turn_order.map(seat => seat + 1).join(" → ")}`}</b></header><div>{view.depots.map(depot => <article key={depot.number}><strong>{depot.number}</strong><div>{depot.tiles.map(tile => <BurgundyTile key={tile} tileId={tile} compact/>)}{depot.tiles.length === 0 && <em>—</em>}</div><small>{zh ? "货物" : "Goods"} {depot.goods.length}</small></article>)}</div></section>
    <section className="burgundy-black-depot"><header><span>BLACK DEPOT</span><h3>{zh ? "中央黑市" : "Central black depot"}</h3></header><div>{view.black_depot.map(tile => <BurgundyTile key={tile} tileId={tile} compact/>)}</div><small>{zh ? "每回合一次，支付 2 银币" : "Once per turn, pay 2 silver"}</small></section>
    <BurgundyDuchy player={player} lang={lang}/>
    <section className="burgundy-legend">{(Object.keys(COLOR_META) as BurgundyColor[]).map(color => <span key={color}><i className={`legend-${color}`}>{COLOR_META[color].symbol}</i>{COLOR_META[color][lang]}</span>)}<small>{zh ? "原创 CSS 棋盘，不包含出版商美术。" : "Original CSS board; no publisher artwork."}</small></section>
  </div>;
}
