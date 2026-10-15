"use client";

import {useState} from "react";
import {ActionChoices, type HumanAction} from "./human-controls";

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

const BUILDING_NAMES: Record<string,[string,string]> = {warehouse:["仓库","Warehouse"],carpenter:["木匠坊","Carpenter"],church:["教堂","Church"],market:["集市","Market"],boarding_house:["旅舍","Boarding house"],bank:["银行","Bank"],town_hall:["市政厅","Town hall"],watchtower:["瞭望塔","Watchtower"],pig:["猪","Pigs"],cow:["牛","Cattle"],sheep:["羊","Sheep"],chicken:["鸡","Chickens"]};
export function burgundyTileName(id: string, lang: Lang) {
  const color=tileColor(id); const stem=id.replace(/^black-/,'').replace(/-\d+$/,'');
  const detail=Object.entries(BUILDING_NAMES).find(([key])=>stem.includes(key));
  if(detail) return detail[1][lang==="zh"?0:1];
  return color ? `${COLOR_META[color][lang]}${color==="monastery"?` ${id.match(/\d+/)?.[0] || ""}`:""}` : id;
}
export function burgundyActionLabel(item: HumanAction, lang: Lang) {
  const a=item.action; const zh=lang==="zh";
  const tile=burgundyTileName(String(a.tile_id || ""),lang);
  const cost=`${a.die_index!==undefined?`${zh?"骰子":"Die"} ${Number(a.die_index)+1} · `:""}${Number(a.workers || 0)} ${zh?"工人":"workers"}${a.silver?` · ${a.silver} ${zh?"银币":"silver"}`:""}`;
  const labels:Record<string,string>={take_tile:zh?`拿取 ${tile} · 仓库 ${a.depot}`:`Take ${tile} · depot ${a.depot}`,place_tile:zh?`铺设 ${tile} → ${a.cell_id}`:`Place ${tile} → ${a.cell_id}`,place_tile_effect:zh?`奖励铺设 ${tile} → ${a.cell_id}`:`Bonus placement ${tile} → ${a.cell_id}`,buy_tile:zh?`购买 ${tile}`:`Buy ${tile}`,choose_tile:zh?`奖励拿取 ${tile} · 仓库 ${a.depot}`:`Bonus tile ${tile} · depot ${a.depot}`,sell_goods:zh?`出售 ${a.goods_type} 号货物`:`Sell goods ${a.goods_type}`,sell_goods_effect:zh?`奖励出售 ${a.goods_type} 号货物`:`Bonus sale ${a.goods_type}`,take_workers:zh?"获得工人":"Take workers",choose_goods:zh?`选择货物 ${(a.goods_types as number[] || []).join(" / ")} · 仓库 ${a.depot}`:`Choose goods ${(a.goods_types as number[] || []).join(" / ")} · depot ${a.depot}`,skip_effect:zh?"跳过奖励":"Skip bonus",end_turn:zh?"结束回合":"End turn"};
  return `${labels[String(a.type)] || String(a.type)} · ${cost}`;
}

function BurgundyDuchy({player,lang,actions,disabled,onTarget}: {player:BurgundyPlayer;lang:Lang;actions:HumanAction[];disabled?:boolean;onTarget:(cell:string)=>void}) {
  return <section className="burgundy-duchy"><header><h3>{lang==="zh"?"你的领地 · 点击高亮格铺设":"Your duchy · select a highlighted hex"}</h3><b>{player.duchy.filter(c=>c.tile_id).length}/37</b></header><div className="burgundy-hex-map">{player.duchy.map(cell=>{
    const legal=actions.some(a=>a.action.cell_id===cell.id);
    return <button type="button" key={cell.id} className={`burgundy-hex hex-${cell.color} ${cell.tile_id?"occupied":""} ${legal?"is-legal":""}`} style={{left:`calc(50% + ${cell.q*39+cell.r*19.5}px)`,top:`calc(50% + ${cell.r*34}px)`}} disabled={disabled||!legal} aria-label={`${lang==="zh"?"铺设到":"Place at"} ${cell.id} · ${COLOR_META[cell.color][lang]} · ${cell.number}`} onClick={()=>onTarget(cell.id)}><small>{cell.number}</small>{cell.tile_id&&<BurgundyTile tileId={cell.tile_id} compact/>}</button>;
  })}</div></section>;
}

export function BurgundyTable({view,lang,actions=[],disabled,onChoose,onReset}: {view?:BurgundyView;lang:Lang;actions?:HumanAction[];disabled?:boolean;onChoose?:(item:HumanAction)=>void;onReset?:()=>void}) {
  const [die,setDie]=useState<number|null>(null);
  const [target,setTarget]=useState<{kind:"tile"|"cell";value:string}|null>(null);
  const zh=lang==="zh";
  if(!view)return null;
  const player=view.players[view.viewer_seat];
  const filtered=die===null?actions:actions.filter(a=>a.action.die_index===undefined||a.action.die_index===die);
  const targetActions=target?filtered.filter(a=>target.kind==="cell"?a.action.cell_id===target.value:a.action.tile_id===target.value):[];
  const placements=target?.kind==="tile"?filtered.filter(a=>a.action.tile_id===target.value && a.action.cell_id):filtered.filter(a=>a.action.cell_id);
  const choose=(items:HumanAction[],label:string)=><ActionChoices actions={items} label={label} describe={a=>burgundyActionLabel(a,lang)} lang={lang} disabled={disabled} onChoose={a=>onChoose?.(a)}/>;
  const tileButton=(id:string)=><button type="button" key={id} className="burgundy-tile-button" disabled={disabled||!filtered.some(a=>a.action.tile_id===id)} aria-pressed={target?.kind==="tile"&&target.value===id} aria-label={`${zh?"选择":"Select"} ${burgundyTileName(id,lang)}`} onClick={()=>{setTarget({kind:"tile",value:id});onReset?.();}}><BurgundyTile tileId={id} compact/><span>{burgundyTileName(id,lang)}</span></button>;
  return <div className="burgundy-board">
    <section className="burgundy-status"><h2>{zh?`阶段 ${view.phase_number} · 第 ${view.round_number} 轮`:`Phase ${view.phase_number} · round ${view.round_number}`}</h2><span>{zh?"白骰":"White die"} {view.white_die}</span><div className="burgundy-dice"><button type="button" aria-pressed={die===null} onClick={()=>{setDie(null);setTarget(null);onReset?.();}}>{zh?"全部骰子":"All dice"}</button>{view.remaining_dice.map(d=><button type="button" key={d.index} aria-pressed={die===d.index} onClick={()=>{setDie(d.index);setTarget(null);onReset?.();}}>{zh?"骰子":"Die"} {d.index+1}: <b>{d.value}</b></button>)}</div></section>
    <div className="burgundy-play-layout"><div><section className="burgundy-depots"><header><h3>{zh?"六座仓库 · 点板块查看费用":"Depots · select a tile to review costs"}</h3></header><div>{view.depots.map(depot=><article key={depot.number}><strong>{depot.number}</strong><div>{depot.tiles.map(tileButton)}</div><small>{zh?"货物":"Goods"} {depot.goods.length}</small></article>)}</div></section>
    <section className="burgundy-black-depot"><header><h3>{zh?"中央黑市":"Black depot"}</h3></header><div>{view.black_depot.map(tileButton)}</div><small>{zh?"通常支付 2 银币；实际费用见方案":"Normally 2 silver; exact cost shown in options"}</small></section>
    <section className="burgundy-storage-play"><h3>{zh?"你的仓储 · 选板块再选格":"Your storage · select a tile then a hex"} {player.storage.length}/3</h3><div>{player.storage.map(tileButton)}</div></section></div>
    <BurgundyDuchy player={player} lang={lang} actions={placements} disabled={disabled} onTarget={cell=>{setTarget({kind:"cell",value:cell});onReset?.();}}/></div>
    {target&&<section className="burgundy-target-choices"><h3>{target.kind==="tile"?burgundyTileName(target.value,lang):`${zh?"位置":"Position"} ${target.value}`}</h3>{choose(targetActions,zh?"选择此方案":"Choose this option")}{!targetActions.length&&<p>{zh?"当前骰子没有可用方案，请换一枚骰子。":"No option for this die; choose another die."}</p>}</section>}
    <div className="burgundy-other-actions">{Object.entries(filtered.filter(a=>!a.action.tile_id&&!a.action.cell_id).reduce<Record<string,HumanAction[]>>((groups,a)=>{(groups[String(a.action.type)] ||= []).push(a);return groups;},{})).map(([kind,items])=><div key={kind}>{choose(items,burgundyActionLabel(items[0],lang).split(" · ")[0])}</div>)}</div>
    <section className="burgundy-legend">{(Object.keys(COLOR_META) as BurgundyColor[]).map(color=><span key={color}><i className={`legend-${color}`}>{COLOR_META[color].symbol}</i>{COLOR_META[color][lang]}</span>)}</section>
  </div>;
}
