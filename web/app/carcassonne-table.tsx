"use client";

import { useState } from "react";

type Lang = "zh" | "en";
type Action = {id: string; action: Record<string, unknown>};
type Feature = {id: string; kind: string; ports: number[]; shields: number; cities?: string[]};
type Tile = {tile_id: string; code: string; rotation: number; x?: number; y?: number; edges: string[]; features: Feature[]};
type Meeple = {tile: string; feature: string; seat: number};
export type CarcassonnePlayer = {seat: number; score: number; meeples_available: number; score_breakdown: Record<string, number>};
export type CarcassonneView = {
  game: "carcassonne"; rules_version: string; status: string; phase: string; active_seat: number;
  viewer_seat: number; turn_count: number; completed_turns: number; last_placed: string | null;
  current_tile: Tile | null; board: Tile[]; meeples: Meeple[]; deck_count: number; discarded: string[];
  players: CarcassonnePlayer[]; rules: Record<string, string>;
  features: {id: string; kind: string; nodes: string[]; tiles: string[]; complete: boolean;
    open_edges: number; points: number; owners: number[]; followers: Record<string, number>; adjacent_cities: string[]}[];
};
const COLORS = ["#c34a3c", "#356da8", "#cf9629", "#7053a0", "#276953"];
const NAMES: Record<string, [string, string]> = {city: ["城市", "City"], road: ["道路", "Road"], field: ["田野", "Field"], monastery: ["修道院", "Monastery"]};
const EDGE = [[50, 0], [100, 50], [50, 100], [0, 50]];
const FIELD_ANCHORS = [[26, 14], [74, 14], [86, 26], [86, 74], [74, 86], [26, 86], [14, 74], [14, 26]];
const localPorts = (f: Feature, rotation: number) => f.ports.map(p => (p - rotation * (f.kind === "field" ? 2 : 1) + (f.kind === "field" ? 8 : 4)) % (f.kind === "field" ? 8 : 4));
function rotatePoint([x, y]: number[], rotation: number): number[] {
  for (let i = 0; i < rotation; i++) [x, y] = [100 - y, x];
  return [x, y];
}
function anchor(feature: Feature, rotation: number) {
  const ports = localPorts(feature, rotation);
  let point = [50, 50];
  if (feature.kind === "field") {
    // A perimeter anchor always lies in its field, even for thin city/road wedges.
    point = FIELD_ANCHORS[Math.min(...ports)];
  } else if (feature.kind === "road") {
    const p = EDGE[ports[0]];
    point = [50 + (p[0] - 50) * .66, 50 + (p[1] - 50) * .66];
  } else if (feature.kind === "city") {
    if (ports.length === 1) point = rotatePoint([50, 16], ports[0]);
    else if (ports.length === 2 && ports.includes(0) && ports.includes(1)) point = [72, 28];
    else if (ports.length === 2 && ports.includes(0) && ports.includes(3)) point = [28, 28];
    else if (ports.length === 3) point = [50, 24];
  }
  return rotatePoint(point, rotation);
}
function cityPath(ports: number[]) {
  if (ports.length === 4) return {path: "M0 0H100V100H0Z", rotate: 0};
  if (ports.length === 3) return {path: "M0 0H100V100Q50 42 0 100Z", rotate: 0};
  if (ports.length === 2 && ports.includes(1) && ports.includes(3)) return {path: "M0 0Q50 30 100 0V100Q50 70 0 100Z", rotate: 0};
  if (ports.length === 2) return {path: "M0 0H100V100Q65 35 0 0Z", rotate: ports.includes(1) ? 0 : 270};
  return {path: "M0 0H100Q100 30 50 30Q0 30 0 0Z", rotate: ports[0] * 90};
}
export function CarcassonneTile({tile, lang, meeples = [], options = [], onChoose, disabled, highlight = false}: {
  tile: Tile; lang: Lang; meeples?: Meeple[]; options?: Action[];
  onChoose?: (a: Action) => void; disabled?: boolean; highlight?: boolean;
}) {
  const roads = tile.features.filter(f => f.kind === "road");
  const label = `${tile.code} · ${tile.rotation * 90}° · ${tile.edges.map(e => NAMES[e][lang === "zh" ? 0 : 1]).join(" / ")}`;
  return <svg viewBox="0 0 100 100" className={`carc-tile ${highlight ? "carc-last" : ""}`} role="group" aria-label={label}>
    <title>{label}</title><rect width="100" height="100" fill="#b0c77c"/>
    <g transform={`rotate(${tile.rotation * 90} 50 50)`}>
      <path d="M8 19l4-4m63 59l5-4M22 88l5-4M86 14l4-3" stroke="#809b56" strokeWidth="2" opacity=".45"/>
      {tile.features.filter(f => f.kind === "city").map(f => {
        const shape = cityPath(localPorts(f, tile.rotation));
        const [x, y] = anchor({...f, ports: localPorts(f, tile.rotation)}, 0);
        return <g key={f.id}><path d={shape.path} transform={`rotate(${shape.rotate} 50 50)`} fill="#ca9169" stroke="#815944" strokeWidth="2"/>
          {f.shields > 0 && <path d={`M${x - 7} ${y - 8}h14v9l-7 6-7-6Z`} fill="#f7db79" stroke="#775635" strokeWidth="1.5"/>}</g>;
      })}
      {roads.map(f => {
        const pts = localPorts(f, tile.rotation).map(p => EDGE[p]);
        const d = pts.length === 2 ? `M${pts[0].join(" ")} Q50 ${tile.code === "D" ? 70 : 50} ${pts[1].join(" ")}` : `M${pts[0].join(" ")} L50 ${["S", "T"].includes(tile.code) ? 72 : 50}`;
        return <g key={f.id}><path d={d} fill="none" stroke="#8c8262" strokeWidth="10"/><path d={d} fill="none" stroke="#f6e8b9" strokeWidth="7"/></g>;
      })}
      {roads.length > 2 && <g><rect x="41" y="41" width="18" height="18" rx="5" fill="#a97752"/><path d="M39 47l11-9 11 9" fill="#914739"/></g>}
      {tile.features.some(f => f.kind === "monastery") && <g><rect x="35" y="41" width="30" height="24" fill="#f3dfb4" stroke="#815944" strokeWidth="2"/><path d="M31 42l19-17 19 17Z" fill="#a5503f"/><rect x="46" y="51" width="8" height="14" fill="#76533c"/></g>}
    </g>
    <rect x="1" y="1" width="98" height="98" fill="none" stroke={highlight ? "#d79823" : "#648052"} strokeWidth={highlight ? 3 : 1}/>
    {meeples.map(m => {
      const f = tile.features.find(f => f.id === m.feature);
      if (!f) return null;
      const [x, y] = anchor(f, tile.rotation);
      return <g key={`${m.seat}-${m.feature}`} transform={`translate(${x} ${y})`}><title>{`${lang === "zh" ? "玩家" : "Seat"} ${m.seat + 1} · ${NAMES[f.kind][lang === "zh" ? 0 : 1]}`}</title>
        {f.kind === "field" ? <rect x="-12" y="-7" width="24" height="14" rx="7" fill={COLORS[m.seat]} stroke="white" strokeWidth="2"/> : <circle r="11" fill={COLORS[m.seat]} stroke="white" strokeWidth="2"/>}
        <text y="4" textAnchor="middle" fill="white" fontSize="12" fontWeight="800">{m.seat + 1}</text></g>;
    })}
    {options.map(a => {
      const f = tile.features.find(f => f.id === a.action.feature);
      if (!f) return null;
      const [x, y] = anchor(f, tile.rotation), enabled = !disabled && Boolean(onChoose);
      const name = `${lang === "zh" ? "派遣随从到" : "Place follower on"} ${NAMES[f.kind][lang === "zh" ? 0 : 1]} ${f.id}`;
      return <g key={a.id} className="carc-feature-target" role="button" tabIndex={enabled ? 0 : -1} aria-label={name} aria-disabled={!enabled}
        onClick={() => enabled && onChoose?.(a)} onKeyDown={e => {if (enabled && ["Enter", " "].includes(e.key)) {e.preventDefault(); onChoose?.(a);}}}>
        <title>{name}</title><circle cx={x} cy={y} r="12" fill="#fff8df" stroke="#235a48" strokeWidth="2"/><text x={x} y={y + 4} textAnchor="middle" fontSize="11" fontWeight="800" fill="#235a48">{f.id}</text></g>;
    })}
  </svg>;
}
function rotateTile(tile: Tile, rotation: number): Tile {
  const delta = rotation - tile.rotation;
  return {...tile, rotation, edges: tile.edges.map((_, i) => tile.edges[(i - delta + 4) % 4]),
    features: tile.features.map(f => ({...f, ports: f.ports.map(p => (p + delta * (f.kind === "field" ? 2 : 1) + (f.kind === "field" ? 8 : 4)) % (f.kind === "field" ? 8 : 4))}))};
}
export function CarcassonnePlayerPanel({player, identity, active, lang}: {
  player?: CarcassonnePlayer; identity: {name: string; seat: number}; active: boolean; lang: Lang;
}) {
  if (!player) return null;
  return <section className={`player-panel carc-player ${active ? "active-player" : ""}`} style={{borderLeftColor: COLORS[player.seat]}}>
    <header><div><span className="seat-label">SEAT {player.seat + 1}</span><h3>{identity.name}</h3></div><strong>{player.score}<small> {lang === "zh" ? "分" : "pts"}</small></strong></header>
    <p>{lang === "zh" ? "可用随从" : "Available followers"} <b>{player.meeples_available}/7</b></p>
    <div className="carc-supply" aria-hidden="true">{Array.from({length: 7}, (_, i) => <i key={i} style={{background: i < player.meeples_available ? COLORS[player.seat] : "#d9d5c8"}}/>)}</div>
    <div className="carc-scores">{Object.entries(player.score_breakdown).map(([kind, score]) => <span key={kind}>{NAMES[kind][lang === "zh" ? 0 : 1]} <b>{score}</b></span>)}</div>
  </section>;
}
export function CarcassonneTable({view, lang, identities, actions = [], onChoose, disabled, onReset}: {
  view?: CarcassonneView; lang: Lang; identities: {seat: number; name: string}[];
  actions?: Action[]; onChoose: (a: Action) => void; disabled?: boolean; onReset?:()=>void;
}) {
  const [rotationChoice, setRotationChoice] = useState<{tileId: string | null; rotation: number}>({tileId: null, rotation: 0});
  const [zoom, setZoom] = useState(76);
  const [selected, setSelected] = useState<string | null>(null);
  if (!view) return null;
  const zh = lang === "zh", placing = view.phase === "place_tile", finished = view.status === "finished";
  const rotation = view.current_tile?.tile_id === rotationChoice.tileId ? rotationChoice.rotation
    : Number(actions.find(a => a.action.type === "place_tile")?.action.rotation ?? 0);
  const positions = actions.filter(a => a.action.type === "place_tile" && a.action.rotation === rotation);
  const followers = actions.filter(a => a.action.type === "place_meeple");
  const skip = actions.find(a => a.action.type === "skip_meeple");
  const last = view.board.find(t => `${t.x},${t.y}` === view.last_placed);
  const preview = view.current_tile ? rotateTile(view.current_tile, rotation) : last;
  const minX = Math.min(...view.board.map(t => t.x!)) - 1, maxX = Math.max(...view.board.map(t => t.x!)) + 1;
  const minY = Math.min(...view.board.map(t => t.y!)) - 1, maxY = Math.max(...view.board.map(t => t.y!)) + 1;
  const width = (maxX - minX + 1) * zoom, height = (maxY - minY + 1) * zoom;
  const inspectKey = selected && view.board.some(t => `${t.x},${t.y}` === selected) ? selected : view.last_placed;
  const featureInfo = view.features.filter(f => f.tiles.includes(inspectKey || ""));
  return <div className="carc-table">
    <header className="carc-heading"><div><span>CARCASSONNE · BASE GAME</span><h2>{zh ? "卡卡颂" : "Build a shared landscape"}</h2><p>{finished ? (zh ? "对局结束 · 已完成终局计分" : "Game complete · final scoring included") : `${identities[view.active_seat]?.name || ""} · ${zh ? `第 ${view.completed_turns + 1} 回合` : `Turn ${view.completed_turns + 1}`}`}</p></div><div className="carc-deck"><strong>{view.deck_count}</strong><span>{zh ? "待抽地形" : "tiles to draw"}</span></div></header>
    {!finished && <section className="carc-turn">
      {preview && <div className="carc-preview"><CarcassonneTile tile={preview} lang={lang} options={!placing ? followers : []} onChoose={onChoose} disabled={disabled}/><small>{preview.code} · {preview.rotation * 90}°</small></div>}
      <div><span className="carc-step">{placing ? "01 / LANDSCAPE" : "02 / FOLLOWER"}</span><h3>{placing ? (zh ? "旋转地形，选择拼接位置" : "Rotate your tile, choose a space") : (zh ? "派遣一名随从，或跳过" : "Place one follower, or skip")}</h3>
        <p>{placing ? (zh ? "高亮空格均匹配当前方向。上、右、下、左对应北、东、南、西。" : "Highlighted spaces match this orientation. North is up; x goes east, y goes south.") : (zh ? "只能放在刚拼上的地形中，且相连区域内不能已有随从。农夫留到终局。" : "Choose an unoccupied feature on the tile just placed. Farmers stay until game end.")}</p>
        {placing && <div className="carc-controls">{[0, 1, 2, 3].map(r => <button type="button" key={r} aria-pressed={r === rotation} disabled={disabled} onClick={() => {setRotationChoice({tileId: view.current_tile?.tile_id || null, rotation: r}); onReset?.();}}>{r * 90}°</button>)}{actions.length > 0 && <small>{positions.length} {zh ? "处可放置" : "legal spaces"}</small>}</div>}
        {!placing && actions.length > 0 && <div className="carc-controls">{followers.map(a => <button type="button" key={a.id} disabled={disabled} onClick={() => onChoose(a)}>{NAMES[last?.features.find(f => f.id === a.action.feature)?.kind || "field"][zh ? 0 : 1]} · {String(a.action.feature)}</button>)}{skip && <button type="button" className="carc-skip" disabled={disabled} onClick={() => onChoose(skip)}>{zh ? "跳过随从 →" : "Skip follower →"}</button>}</div>}
        {actions.length === 0 && <small>{zh ? "正在观看对局" : "Spectating this turn"}</small>}
      </div>
    </section>}
    <section className="carc-map-section"><header><h3>{zh ? "共同版图" : "Shared landscape"}</h3><div className="carc-controls"><button type="button" aria-label={zh ? "缩小棋盘" : "Zoom out"} disabled={zoom <= 40} onClick={() => setZoom(Math.max(40, zoom - 12))}>−</button><span>{Math.round(zoom / 76 * 100)}%</span><button type="button" aria-label={zh ? "放大棋盘" : "Zoom in"} disabled={zoom >= 124} onClick={() => setZoom(Math.min(124, zoom + 12))}>+</button></div></header>
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Focus allows keyboard users to scroll the large board. */}
      <div className="carc-map-scroll" tabIndex={0} role="region" aria-label={zh ? "可滚动地形棋盘" : "Scrollable landscape board"}>
        <div className="carc-map" style={{width, height, backgroundSize: `${zoom}px ${zoom}px`}}>
          {view.board.map(tile => {
            const key = `${tile.x},${tile.y}`, tokens = view.meeples.filter(m => m.tile === key);
            return <div key={key} className={`carc-cell ${inspectKey === key ? "carc-inspected" : ""}`} style={{left: (tile.x! - minX) * zoom, top: (tile.y! - minY) * zoom, width: zoom, height: zoom}}>
              <button type="button" className="carc-inspect-tile" aria-label={`${zh ? "查看地形" : "Inspect tile"} ${key} · ${tile.code}`} onClick={() => setSelected(key)}><CarcassonneTile tile={tile} lang={lang} meeples={tokens} highlight={key === view.last_placed}/></button><small>{key}</small>
            </div>;
          })}
          {positions.map(a => <button type="button" key={a.id} className="carc-cell carc-placement" style={{left: (Number(a.action.x) - minX) * zoom, top: (Number(a.action.y) - minY) * zoom, width: zoom, height: zoom}}
            disabled={disabled} onClick={() => onChoose(a)} aria-label={`${zh ? "放置地形" : "Place tile"} (${a.action.x}, ${a.action.y}) · ${rotation * 90}°`}>
            <span>+</span><small>{String(a.action.x)}, {String(a.action.y)}</small>{preview && <div className="carc-hover-preview"><CarcassonneTile tile={preview} lang={lang}/></div>}
          </button>)}
        </div>
      </div>
      <div className="carc-legend"><span><i style={{background: "#ca9169"}}/>{zh ? "城市" : "City"}</span><span><i style={{background: "#f6e8b9"}}/>{zh ? "道路" : "Road"}</span><span><i style={{background: "#b0c77c"}}/>{zh ? "田野" : "Field"}</span><span>◯ {zh ? "随从" : "Follower"} · ▰ {zh ? "农夫" : "Farmer"}</span><small>{view.board.length}/72 {zh ? "已放置" : "placed"} · {view.discarded.length} {zh ? "已弃置" : "discarded"}</small></div>
    </section>
    {inspectKey && <section className="carc-features"><header><h3>{zh ? "区域详情" : "Connected features"} <small>({inspectKey})</small></h3><span>{zh ? "点击任意地形查看" : "Select any tile to inspect"}</span></header><div>{featureInfo.map(f => <article key={f.id}><b>{NAMES[f.kind][zh ? 0 : 1]} · {f.nodes.filter(n => n.startsWith(`${inspectKey}:`)).map(n => n.split(":")[1]).join(", ")}</b><span>{f.tiles.length} {zh ? "块地形" : "tiles"} · {f.complete ? (zh ? "已完成" : "Complete") : f.kind === "field" ? `${f.adjacent_cities.length} ${zh ? "座完整城市" : "completed cities"}` : `${f.open_edges} ${zh ? "处未封闭" : "open"}`}</span><strong>{f.points} {zh ? "分" : "pts"}</strong><small>{Object.keys(f.followers).length ? Object.entries(f.followers).map(([seat, n]) => `${identities[Number(seat)]?.name || Number(seat) + 1} ×${n}`).join(" · ") : (zh ? "无随从" : "Unoccupied")}</small></article>)}</div><p>{zh ? "分值按当前版图结算计算；田野只计算相邻的完整城市。完成区域在随从放置后结算。" : "Values reflect scoring now; fields count only completed adjacent cities. Completed features score after follower placement."}</p></section>}
    <details className="carc-rules"><summary>{zh ? "玩法与计分速查" : "Rules & scoring"}</summary>{zh ? <ul><li>每回合放置抽到的地形，四边必须与相邻地形一致；随后可放一名随从，再结算。</li><li>道路完成后每块地形 1 分；城市完成后每块地形和每个盾徽各 2 分；修道院被八块地形包围时得 9 分。</li><li>相连区域已有任意玩家的随从时不能直接加入；可以通过拼接合并不同区域。多数玩家得分，并列多数均得全额分数。</li><li>完成区域的所有随从返回库存。农夫始终留在田野，终局时每座相邻完整城市得 3 分，同一城市在同一田野只计一次。</li><li>终局未完成道路每块 1 分，城市每块和每盾各 1 分；修道院按自身加周围地形计分。总分相同共享胜利。</li><li>72 块基础地形，2–5 人，每人 7 名随从。无法放置的牌自动弃掉并重抽；不含河流、修道院长等扩展。</li></ul> : <ul>{Object.values(view.rules).map(rule => <li key={rule}>{rule}</li>)}</ul>}</details>
  </div>;
}
