"use client";

import { useState } from "react";

type Lang = "zh" | "en";
type Action = {id: string; action: Record<string, unknown>};
type PatternCell = {q: number; r: number; stack: string[]; animal: boolean};
export type HarmoniesCard = {
  id: string; number: number; name: string; spirit: boolean; points: number[];
  pattern: PatternCell[]; placed: number; remaining: number; complete: boolean; scoring_rule?: string;
};
type Cell = {id: number; q: number; r: number; stack: string[]; cube: string | null};
export type HarmoniesPlayer = {
  seat: number; score: number; turns: number; empty_spaces: number; active_cards: number;
  score_breakdown: Record<string, number>; cells: Cell[]; cards: HarmoniesCard[]; spirit_choices: HarmoniesCard[];
};
export type HarmoniesView = {
  game: "harmonies"; rules_version: string; status: string; phase: string; active_seat: number; viewer_seat: number;
  turn_count: number; completed_turns: number; round: number; board_side: "A" | "B"; nature_spirits: boolean;
  solo_suns: number | null; final_round: number | null; end_reason: string | null; taken_group: number | null; took_card: boolean;
  token_groups: string[][]; pending_tokens: string[]; bag_count: number; deck_count: number;
  market: HarmoniesCard[]; players: HarmoniesPlayer[]; rules: Record<string, string>;
};
const COLORS: Record<string, {fill: string; ink: string; mark: string; zh: string; en: string}> = {
  blue: {fill: "#71b9cd", ink: "#195769", mark: "≈", zh: "水域", en: "Water"},
  gray: {fill: "#a1aab4", ink: "#394755", mark: "▲", zh: "山地", en: "Mountain"},
  brown: {fill: "#b68960", ink: "#583a25", mark: "Ⅱ", zh: "树干", en: "Trunk"},
  green: {fill: "#8baa69", ink: "#304c2c", mark: "♣", zh: "树冠", en: "Foliage"},
  yellow: {fill: "#ebc56b", ink: "#7c5b14", mark: "✦", zh: "田野", en: "Field"},
  red: {fill: "#cf8370", ink: "#7a3a31", mark: "⌂", zh: "建筑", en: "Building"},
  base: {fill: "#ddd1ba", ink: "#6d6050", mark: "?", zh: "红/褐/灰底座", en: "Red/trunk/gray base"},
};
const SCORE_NAMES: Record<string, [string, string]> = {
  trees: ["树木", "Trees"], mountains: ["山脉", "Mountains"], fields: ["田野", "Fields"],
  buildings: ["建筑", "Buildings"], water: ["水域", "Water"], animals: ["动物", "Animals"], spirits: ["自然之灵", "Spirits"],
};
const SPIRITS_ZH: Record<string, string> = {
  h33: "每组田野：3 格及以上 10 分，1–2 格 2 分。", h34: "每组田野 5 分，单格也算。",
  h35: "每棵高度 2 或 3 的树木加 4 分。", h36: "每棵高度 1–2 的树木加 3 分，高度 3 加 1 分。",
  h37: "每组相连的两层建筑加 4 分，单栋也算。", h38: "每组至少两栋的相连建筑加 6 分（勘误后数值）。",
  h39: "每座高度 2 或 3 的山加 4 分，孤山也算。", h40: "每座高度 1–2 的山加 3 分，高度 3 加 1 分，孤山也算。",
  h41: "每组至少 2 格的水域加 7 分。", h42: "每枚水域加 2 分。",
};
function name(card: HarmoniesCard, lang: Lang) {
  return `${card.spirit ? (lang === "zh" ? "自然之灵" : "Spirit") : (lang === "zh" ? "动物" : "Animal")} ${String(card.number).padStart(2, "0")}`;
}
function Token({color, lang}: {color: string; lang: Lang}) {
  const meta = COLORS[color];
  return <span className="harmony-token" style={{background: meta.fill, color: meta.ink}} title={meta[lang]}>{meta.mark}</span>;
}
function xy(q: number, r: number, size = 31) { return [q * size * 1.5, (r + q / 2) * size * Math.sqrt(3)]; }
function Stack({stack, cube, small = false}: {stack: string[]; cube?: string | null; small?: boolean}) {
  const radius = small ? 20 : 24;
  return <g>{stack.map((color, i) => <g key={i} transform={`translate(0,${-i * 7})`}>
    <ellipse cy="4" rx={radius} ry={radius * .64} fill={COLORS[color].ink}/>
    <ellipse rx={radius} ry={radius * .64} fill={COLORS[color].fill} stroke={COLORS[color].ink} strokeWidth="1"/>
    <text y="5" textAnchor="middle" fill={COLORS[color].ink} fontSize="17" fontWeight="700">{COLORS[color].mark}</text>
  </g>)}{cube && <g transform={`translate(9,${-stack.length * 7 - 3})`}><rect x="-6" y="-6" width="12" height="12" rx="2" fill={Number(cube.slice(1)) > 32 ? "#cce0b8" : "#f3b851"} stroke="#77582e" strokeWidth="2"/></g>}</g>;
}
export function Habitat({card, lang}: {card: HarmoniesCard; lang: Lang}) {
  const pts = card.pattern.map(c => xy(c.q, c.r));
  const minX = Math.min(...pts.map(p => p[0])) - 30, minY = Math.min(...pts.map(p => p[1])) - 42;
  const width = Math.max(...pts.map(p => p[0])) - minX + 30, height = Math.max(...pts.map(p => p[1])) - minY + 28;
  return <svg className="harmony-habitat" viewBox={`${minX} ${minY} ${width} ${height}`} role="img" aria-label={`${name(card, lang)} ${lang === "zh" ? "栖息地；方块标记安置位置" : "habitat; cube marks settlement target"}`}>
    <title>{card.pattern.map((c, i) => `${i + 1}: ${c.stack.map(s => COLORS[s][lang]).join(" / ")}${c.animal ? (lang === "zh" ? "，安置动物" : ", settle here") : ""}`).join("; ")}</title>
    {card.pattern.map((c, i) => <g key={i} transform={`translate(${pts[i].join(",")})`}><Stack stack={c.stack} cube={c.animal ? card.id : null} small/></g>)}
  </svg>;
}
function AnimalCard({card, lang, action, onChoose, selected, onSelect, disabled}: {
  card: HarmoniesCard; lang: Lang; action?: Action; onChoose?: (action: Action) => void;
  selected?: boolean; onSelect?: () => void; disabled?: boolean;
}) {
  const zh = lang === "zh";
  return <article className={`harmony-card ${card.complete ? "complete" : ""} ${selected ? "selected" : ""}`}>
    <header><span>{card.spirit ? "NATURE SPIRIT" : "HABITAT"}</span><b>{name(card, lang)}</b></header>
    <Habitat card={card} lang={lang}/>
    <div className="harmony-card-points" aria-label={zh ? "得分进度" : "Scoring progress"}>{card.points.map((p, i) => <span key={i} className={i < card.placed ? "earned" : ""}>{card.spirit ? "✧" : p}<small>{i < card.placed ? "✓" : "▪"}</small></span>)}</div>
    {card.spirit && <p>{zh ? SPIRITS_ZH[card.id] : card.scoring_rule}</p>}
    {card.complete ? <small className="harmony-complete">{zh ? "已完成 · 不占卡槽" : "Complete · slot freed"}</small> : <small>{zh ? `已安置 ${card.placed} / ${card.points.length}` : `Settled ${card.placed} / ${card.points.length}`}</small>}
    {action && <button type="button" disabled={disabled} onClick={() => onChoose?.(action)}>{action.action.type === "choose_spirit" ? (zh ? "选择自然之灵" : "Choose spirit") : (zh ? "拿取动物牌" : "Take animal")}</button>}
    {onSelect && <button type="button" disabled={disabled} aria-pressed={selected} onClick={onSelect}>{zh ? "安置动物 →" : "Settle animal →"}</button>}
  </article>;
}
function HexBoard({player, lang, targets, onCell, disabled}: {
  player: HarmoniesPlayer; lang: Lang; targets?: Set<number>; onCell?: (cell: number) => void; disabled?: boolean;
}) {
  const hex = "31,0 15.5,26.85 -15.5,26.85 -31,0 -15.5,-26.85 15.5,-26.85";
  return <svg className="harmony-hex-board" viewBox="-42 -53 270 306" role="group" aria-label={lang === "zh" ? "六角地形棋盘" : "Hex landscape board"}>
    {player.cells.map(c => {
      const enabled = Boolean(targets?.has(c.id) && !disabled);
      const label = `${lang === "zh" ? "格" : "Cell"} ${c.id + 1}: ${c.stack.length ? c.stack.map(s => COLORS[s][lang]).join(" / ") : (lang === "zh" ? "空地" : "empty")}${c.cube ? ` · ${c.cube}` : ""}`;
      return <g key={c.id} transform={`translate(${xy(c.q, c.r).join(",")})`} className={`harmony-hex ${enabled ? "actionable" : ""}`}>
        <polygon points={hex} fill={enabled ? "#e6efd4" : "#efe8d8"} stroke={enabled ? "#668446" : "#d9ceb8"} strokeWidth={enabled ? 2 : 1}/>
        <g pointerEvents="none"><Stack stack={c.stack} cube={c.cube}/><text className="harmony-cell-number" y="23" textAnchor="middle">{c.id + 1}</text></g>
        {onCell ? <g role="button" tabIndex={enabled ? 0 : -1} aria-disabled={!enabled} aria-label={label} onClick={() => enabled && onCell(c.id)} onKeyDown={e => {if (enabled && (e.key === "Enter" || e.key === " ")) {e.preventDefault(); onCell(c.id);}}}><title>{label}</title><polygon points={hex} fill="transparent"/></g> : <title>{label}</title>}
      </g>;
    })}
  </svg>;
}
export function HarmoniesPlayerPanel({player, identity, active, lang}: {
  player?: HarmoniesPlayer; identity: {name: string; seat: number}; active: boolean; lang: Lang;
}) {
  if (!player) return null;
  return <section className={`player-panel harmony-player-panel ${active ? "active-player" : ""}`}>
    <header><div><span className="seat-label">SEAT {identity.seat + 1}</span><h3>{identity.name}</h3></div><strong>{player.score}<small> {lang === "zh" ? "分" : "pts"}</small></strong></header>
    <div className="harmony-player-facts"><span>{lang === "zh" ? "空格" : "Empty"} <b>{player.empty_spaces}</b></span><span>{lang === "zh" ? "在建栖息地" : "Active habitats"} <b>{player.active_cards}/4</b></span></div>
    <HexBoard player={player} lang={lang}/>
    <div className="harmony-score-grid">{Object.entries(SCORE_NAMES).map(([key, names]) => <span key={key}>{names[lang === "zh" ? 0 : 1]}<b>{player.score_breakdown[key]}</b></span>)}</div>
  </section>;
}
export function HarmoniesTable({view, lang, identities, actions = [], disabled, onChoose}: {
  view?: HarmoniesView; lang: Lang; identities: {seat: number; name: string}[];
  actions?: Action[]; disabled?: boolean; onChoose: (action: Action) => void;
}) {
  const [color, setColor] = useState("");
  const [animal, setAnimal] = useState("");
  const [boardSeat, setBoardSeat] = useState<number | null>(null);
  if (!view) return null;
  const zh = lang === "zh", own = view.players[view.active_seat];
  const seat = boardSeat ?? view.active_seat, player = view.players[seat];
  const interactive = actions.length > 0 && seat === view.active_seat;
  const placements = actions.filter(a => a.action.type === "place_token");
  const selectedColor = view.pending_tokens.includes(color) ? color : String(placements[0]?.action.color || "");
  const selectedAnimal = actions.some(a => a.action.type === "place_animal" && a.action.card_id === animal) ? animal : "";
  const choices = interactive ? actions.filter(a => selectedAnimal ? a.action.type === "place_animal" && a.action.card_id === selectedAnimal : a.action.type === "place_token" && a.action.color === selectedColor) : [];
  const targets = new Set(choices.map(a => Number(a.action.cell)));
  const endActions = actions.filter(a => a.action.type === "end_turn");
  const move = (cell: number) => {const action = choices.find(a => a.action.cell === cell); if (action) onChoose(action);};
  const step = own.spirit_choices.length ? (zh ? "选择你的自然之灵" : "Choose your nature spirit") : view.taken_group === null ? (zh ? "从市场拿取一组三枚地形" : "Take a group of three tokens") : view.pending_tokens.length ? (zh ? "选择地形，点击高亮格放置" : "Choose a token, then a highlighted hex") : (zh ? "安置动物，或结束回合" : "Settle animals or end your turn");
  return <div className="harmony-table">
    <header className="harmony-heading"><div><span>HARMONIES / {view.board_side === "A" ? "RIVERS" : "ISLANDS"}</span><h2>{zh ? "自然和弦" : "A landscape in harmony"}</h2><p>{zh ? `第 ${view.round} 轮 · ${identities[view.active_seat]?.name || ""}` : `Round ${view.round} · ${identities[view.active_seat]?.name || ""}`}</p></div><div className="harmony-supply"><b>{view.bag_count}</b><span>{zh ? "袋中地形" : "tokens in bag"}</span></div></header>
    {view.final_round !== null && <div className="harmony-final" role="status">{view.status === "finished" ? (zh ? "对局结束 · 最终计分" : "Game complete · final scores") : (zh ? "最后一轮 · 所有玩家完成相同回合数后结算" : "Final round · finish with equal turns")}</div>}
    {view.status === "finished" && view.solo_suns !== null && <div className="harmony-final">☀ {view.solo_suns} {zh ? "枚太阳 · 单人成绩" : "suns · solo achievement"}</div>}
    <section className="harmony-market"><header><h3>{zh ? "地形市场" : "Landscape market"}</h3><small>{zh ? "整组拿取 · 任意顺序放置" : "Take one group · place in any order"}</small></header><div className="harmony-groups">{view.token_groups.map((group, i) => {
      const action = actions.find(a => a.action.type === "take_tokens" && a.action.group === i);
      return <button type="button" key={i} aria-label={`${zh ? "拿取地形组" : "Take token group"} ${i + 1}: ${group.map(c => COLORS[c][lang]).join(" / ")}`} disabled={!action || disabled} onClick={() => action && onChoose(action)}><small>0{i + 1}</small><div>{group.length ? group.map((c, j) => <Token color={c} lang={lang} key={j}/>) : <span className="harmony-taken">{zh ? "已拿取" : "Taken"}</span>}</div></button>;
    })}</div></section>
    <section className="harmony-workspace"><div className="harmony-board-heading"><h3>{zh ? "你的自然景观" : "Personal landscapes"}</h3><div>{identities.map(p => <button type="button" key={p.seat} aria-pressed={seat === p.seat} onClick={() => setBoardSeat(p.seat)}>{p.name}</button>)}</div></div>
      {actions.length > 0 && <p className="harmony-step" aria-live="polite">{interactive ? (selectedAnimal ? `${zh ? "点击高亮格安置" : "Select a highlighted hex for"} ${selectedAnimal}` : step) : (zh ? "正在查看其他玩家的景观" : "Viewing another player's landscape")}</p>}
      <div className="harmony-landscape"><HexBoard player={player} lang={lang} targets={targets} onCell={interactive ? move : undefined} disabled={disabled}/><aside><span className="harmony-kicker">{zh ? "当前得分" : "CURRENT SCORE"}</span><strong className="harmony-total">{player.score}</strong><div className="harmony-score-grid">{Object.entries(SCORE_NAMES).map(([key, names]) => <span key={key}>{names[zh ? 0 : 1]}<b>{player.score_breakdown[key]}</b></span>)}</div><p>{zh ? `剩余 ${player.empty_spaces} 格空地。回合结束时 ≤2 格触发终局。` : `${player.empty_spaces} empty hexes. At most 2 at turn end triggers the final round.`}</p></aside></div>
      {interactive && view.pending_tokens.length > 0 && <div className="harmony-pending"><b>{zh ? "待放置" : "To place"}</b>{view.pending_tokens.map((c, i) => <button type="button" key={i} disabled={disabled} aria-label={`${zh ? "选择" : "Select"} ${COLORS[c][lang]}`} aria-pressed={!selectedAnimal && selectedColor === c} onClick={() => {setAnimal(""); setColor(c);}}><Token color={c} lang={lang}/></button>)}</div>}
      {interactive && selectedAnimal && <button type="button" className="harmony-cancel" onClick={() => setAnimal("")}>{zh ? "返回地形放置" : "Back to landscape placement"}</button>}
      {endActions.length > 0 && <div className="harmony-end"><button type="button" disabled={disabled} onClick={() => onChoose(endActions[0])}>{zh ? "结束回合 →" : "End turn →"}</button>{endActions.length > 1 && <details><summary>{zh ? "单人：换一张市场牌并结束" : "Solo: replace a market card and end turn"}</summary>{endActions.slice(1).map(a => <button type="button" key={a.id} disabled={disabled} onClick={() => onChoose(a)}>{zh ? "换掉" : "Replace"} {String(a.action.discard_card).toUpperCase()}</button>)}</details>}</div>}
    </section>
    {own.spirit_choices.length > 0 && <section className="harmony-card-section"><header><h3>{zh ? "选择自然之灵" : "Choose a spirit"}</h3></header><div className="harmony-cards">{own.spirit_choices.map(c => <AnimalCard key={c.id} card={c} lang={lang} action={actions.find(a => a.action.type === "choose_spirit" && a.action.card_id === c.id)} onChoose={onChoose} disabled={disabled}/>)}</div></section>}
    <section className="harmony-card-section"><header><h3>{zh ? "正在营造的栖息地" : "Your habitats"}</h3><small>{player.active_cards}/4 {zh ? "使用中" : "active"}</small></header><div className="harmony-cards">{player.cards.map(c => <AnimalCard key={c.id} card={c} lang={lang} selected={selectedAnimal === c.id && interactive} onSelect={interactive && actions.some(a => a.action.type === "place_animal" && a.action.card_id === c.id) ? () => setAnimal(c.id) : undefined} disabled={disabled}/>)}{player.cards.length === 0 && <p className="harmony-empty">{zh ? "从下方选择动物牌，为它们营造栖息地。" : "Choose an animal card below and build its habitat."}</p>}</div></section>
    <section className="harmony-card-section"><header><h3>{zh ? "动物牌市场" : "Animal market"}</h3><small>{zh ? `牌堆 ${view.deck_count} · 每回合最多拿一张` : `${view.deck_count} in deck · take at most one per turn`}</small></header><div className="harmony-cards">{view.market.map(c => <AnimalCard key={c.id} card={c} lang={lang} action={actions.find(a => a.action.type === "take_animal" && a.action.card_id === c.id)} onChoose={onChoose} disabled={disabled}/>)}</div></section>
    <div className="harmony-legend">{Object.keys(COLORS).filter(c => c !== "base").map(c => <span key={c}><Token color={c} lang={lang}/>{COLORS[c][lang]}</span>)}</div>
    <details className="harmony-rules"><summary>{zh ? "玩法与计分速查" : "Rules & scoring reference"}</summary>{zh ? <ul><li>每回合拿一组地形并全部放置；可以穿插拿一张动物牌和多次安置动物，最后点击结束回合。</li><li>树木 1/3/7 分；相连山脉每格按高度 1/3/7 分；每组至少两格田野 5 分。</li><li>红色建筑只允许两层；周围至少三种顶层颜色得 5 分。树干和单层红色不得地形分。</li><li>A 面河流按最长的最短连通路径计分：1–6 格为 0/2/5/8/11/15 分，此后每格 +4。B 面每个非水域连通岛屿 5 分，空格也属陆地。</li><li>栖息地图案只能旋转，不能镜像，且必须精确匹配高度；动物方块锁定所在格。图案其余格可重复使用。</li><li>动物牌累计得分取最高已揭示数字，不相加；完成牌不占四张上限。自然之灵需安置后才生效。</li><li>袋子不足补充或只剩 ≤2 空格触发最后一轮；总分相同则比较动物方块数。</li><li>单人每回合弃掉未拿的两组地形并重补市场；没拿动物牌时可换一张。</li></ul> : <ul>{Object.entries(view.rules).map(([key, value]) => <li key={key}>{value}</li>)}</ul>}<small>{zh ? "32 张基础动物牌以编号展示；原创地形图形。社区转录牌库，可玩测试版。" : "32 numbered base animal cards; original landscape graphics. Community-transcribed catalog, playable beta."}</small></details>
  </div>;
}
