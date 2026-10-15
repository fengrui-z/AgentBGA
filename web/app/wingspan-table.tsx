"use client";

import {useState} from "react";

type Lang = "zh" | "en";
type Action = {id: string; action: Record<string, unknown>};
type Habitat = "forest" | "grassland" | "wetland";
export type WingspanCard = {
  id: string; name: string; points: number; nest: string; egg_limit: number; wingspan: number;
  habitats: Habitat[]; cost: Record<string, number>; cost_choice: boolean; color: string;
  power_summary: string; power_summary_cn?: string; eggs?: number; cache?: Record<string, number>; tucked_count?: number;
};
type Bonus = {id: string; name: string; metric: string; thresholds: [number, number][]; multiplier: number; count?: number; points?: number};
export type WingspanPlayer = {
  seat: number; food: Record<string, number>; hand: WingspanCard[]; hand_count: number;
  bonuses: Bonus[]; bonus_choices: Bonus[]; bonus_count: number;
  habitats: Record<Habitat, WingspanCard[]>; score: number; score_breakdown: Record<string, number>;
  actions_left: number; turns: number; round_points: number[];
};
export type WingspanView = {
  game: "wingspan"; rules_version: string; viewer_seat: number; status: string; phase: string;
  round: number; turn_count: number; completed_turns: number; active_seat: number; turn_owner: number;
  first_player: number; goal_board: string; feeder: string[]; tray: (WingspanCard | null)[];
  deck_count: number; bonus_deck_count: number; goals: string[];
  goal_history: {round: number; goal: string; quantities: number[]; points: number[]}[];
  players: WingspanPlayer[]; pending: Record<string, unknown> | null; draft: WingspanCard[]; rules: Record<string, string>;
};
const HABITATS: Habitat[] = ["forest", "grassland", "wetland"];
const WORDS: Record<string, [string, string]> = {
  forest:["森林","Forest"], grassland:["草原","Grassland"], wetland:["湿地","Wetland"],
  invertebrate:["无脊椎动物","Invertebrate"], seed:["种子","Seed"], fish:["鱼","Fish"], fruit:["果实","Fruit"], rodent:["啮齿动物","Rodent"], wild:["任意食物","Any food"],
  bowl:["碗巢","Bowl"], cavity:["洞巢","Cavity"], ground:["地巢","Ground"], platform:["平台巢","Platform"], star:["万能巢","Wild nest"],
  birds:["鸟牌","Birds"], eggs:["鸟蛋","Eggs"], cached_food:["贮食","Cached food"], tucked_cards:["压卡","Tucked cards"], round_goals:["轮末目标","Round goals"], bonus_cards:["奖励卡","Bonus cards"],
};
const MARKS: Record<string, string> = {invertebrate:"∿",seed:"❧",fish:"⋊",fruit:"●",rodent:"◕",wild:"✧"};
function word(key: string, lang: Lang) { return WORDS[key]?.[lang === "zh" ? 0 : 1] || key; }
function goalName(key: string, lang: Lang) {
  if (key === "birds_total") return lang === "zh" ? "全部鸟类数量" : "Total birds";
  if (key === "egg_sets") return lang === "zh" ? "三栖息地鸟蛋套数" : "Egg sets across habitats";
  const [kind, target] = key.split("_");
  return `${word(target, lang)} · ${kind === "nested" ? (lang === "zh" ? "有蛋的鸟" : "birds with eggs") : word(kind, lang)}`;
}
function Food({food, count, lang}: {food: string; count?: number; lang: Lang}) {
  return <span className={`ws-food ws-food-${food}`} title={word(food,lang)} aria-label={`${word(food,lang)}${count === undefined ? "" : ` ${count}`}`}><i aria-hidden="true">{MARKS[food]}</i><span>{word(food,lang)}</span>{count !== undefined && <b>{count}</b>}</span>;
}
export function WingspanBird({card, lang, actions = [], disabled, onChoose}: {card: WingspanCard; lang: Lang; actions?: Action[]; disabled?: boolean; onChoose?: (a: Action) => void}) {
  const zh = lang === "zh";
  return <article className={`ws-bird ws-power-${card.color}`}>
    <header><span>{card.habitats.map(h => word(h,lang)).join(" / ")}</span><b>{card.points}<small> {zh ? "分" : "pts"}</small></b></header>
    <div className="ws-bird-mark" aria-hidden="true"><svg viewBox="0 0 160 70"><path d="M16 48 Q39 2 78 31 Q98 0 139 14 L104 35 Q133 40 146 61 Q101 44 81 42 Q48 48 16 48Z"/><circle cx="104" cy="23" r="2"/></svg></div>
    <h4>{card.name}</h4><div className="ws-cost">{Object.entries(card.cost).map(([f,n]) => <Food key={f} food={f} count={n} lang={lang}/>)}{card.cost_choice && <small>{zh ? "任选一种" : "choose one"}</small>}{!Object.keys(card.cost).length && <small>{zh ? "无食物费用" : "No food cost"}</small>}</div>
    <div className="ws-bird-facts"><span>{word(card.nest,lang)}</span><span>↔ {card.wingspan} cm</span><span>◯ {card.eggs ?? 0}/{card.egg_limit}</span></div>
    <p className="ws-power-text"><b>{({brown:zh ? "激活时" : "When activated",white:zh ? "打出时" : "When played",pink:zh ? "回合之间" : "Between turns",none:"—"})[card.color]}</b>{zh ? card.power_summary_cn || card.power_summary : card.power_summary}</p>
    {card.tucked_count !== undefined && <div className="ws-bird-counters"><span>{zh ? "压卡" : "Tucked"} <b>{card.tucked_count}</b></span><span>{zh ? "贮食" : "Cached"} <b>{Object.values(card.cache || {}).reduce((a,b)=>a+b,0)}</b></span></div>}
    {actions.map(a => <button type="button" key={a.id} disabled={disabled} onClick={()=>onChoose?.(a)}>{a.action.type === "play_bird" ? `${zh ? "打出至" : "Play in"} ${word(String(a.action.habitat),lang)}` : a.action.type === "lay_egg" ? (zh ? "放置鸟蛋" : "Lay egg") : a.action.type === "pay_egg" ? (zh ? "支付鸟蛋" : "Spend egg") : a.action.type === "activate_power" ? (zh ? "激活能力" : "Activate") : (zh ? "选择" : "Choose")}</button>)}
  </article>;
}
function bonusRule(b: Bonus, lang: Lang) {
  const zh=lang==="zh";
  const metrics: Record<string,[string,string]> = {low_points:["每只价值 0–3 分的鸟","Birds worth 0–3 points"],flocking:["具有群聚能力的鸟","Birds with flocking powers"],predator:["具有捕食能力的鸟","Birds with predator powers"],four_eggs:["至少有 4 枚蛋的鸟","Birds with at least 4 eggs"],has_egg:["至少有 1 枚蛋的鸟","Birds with at least 1 egg"],large:["翼展大于 65 cm 的鸟","Birds over 65 cm"],small:["翼展不超过 30 cm 的鸟","Birds up to 30 cm"],only_invertebrate:["食物费用只有无脊椎动物的鸟","Birds eating only invertebrates"],hand:["终局手牌数量","Bird cards in hand at game end"],fewest_habitat:["鸟数最少的栖息地中的鸟","Birds in your least-populated habitat"]};
  let metric=metrics[b.metric]?.[zh?0:1];
  if(!metric) {
    const [kind,value]=b.metric.split(":");
    if(kind==="name") metric=({Anatomist:["英文名称含身体部位的鸟","Birds with body parts in English names"],Cartographer:["英文名称含地理词的鸟","Birds with geography in English names"],Historian:["以人名命名的鸟","Birds named after people"],Photographer:["英文名称含颜色的鸟","Birds with colors in English names"]} as Record<string,[string,string]>)[value]?.[zh?0:1];
    else if(kind==="food") metric=zh?`费用中含${word(value,lang)}图标的鸟`:`Birds showing ${word(value,lang)} in their cost`;
    else if(kind==="nest") metric=zh?`${word(value,lang)}或万能巢的鸟`:`Birds with ${word(value,lang)} or wild nests`;
    else if(kind==="only") metric=zh?`只能在${word(value,lang)}生活的鸟`:`Birds restricted to ${word(value,lang)}`;
  }
  return `${metric || b.name} · ${b.multiplier ? `${b.multiplier} ${lang === "zh" ? "分 / 个" : "points each"}` : b.thresholds.map(([n,p])=>`${n}+ → ${p}`).join(" / ")}`; }
export function WingspanPlayerPanel({player, identity, active, lang}: {player?: WingspanPlayer; identity: {seat: number; name: string}; active: boolean; lang: Lang}) {
  if (!player) return null;
  const zh = lang === "zh";
  return <section className={`player-panel ws-player ${active ? "active-player" : ""}`}><header><div><span className="seat-label">SEAT {identity.seat+1}</span><h3>{identity.name}</h3></div><strong>{player.score}<small> {zh ? "分" : "pts"}</small></strong></header>
    <p>{zh ? "剩余行动" : "Actions left"} <b>{player.actions_left}</b> · {zh ? "手牌" : "Hand"} {player.hand_count}</p>
    <div className="ws-mini-habitats">{HABITATS.map(h=><div key={h} className={`ws-${h}`}><span>{word(h,lang)}</span>{Array.from({length:5},(_,i)=><i key={i} className={player.habitats[h][i] ? "occupied" : ""}/>)}</div>)}</div>
    <div className="ws-food-supply">{Object.entries(player.food).map(([f,n])=><Food key={f} food={f} count={n} lang={lang}/>)}</div>
    <div className="ws-score">{Object.entries(player.score_breakdown).map(([k,n])=><span key={k}>{word(k,lang)}<b>{n}</b></span>)}</div>
    {!("bonus_cards" in player.score_breakdown) && <small>{zh ? "奖励卡得分在终局公开" : "Bonus points revealed at game end"}</small>}
  </section>;
}
const STEPS: Record<string, [string,string]> = {
  setup_keep:["选择起始手牌，每留一张需弃一个食物","Choose starting birds; spend one starting food per kept bird"],
  discard_food:["选择要弃掉的食物","Choose food to discard"],bonus_choose:["保留一张奖励卡","Keep one bonus card"],
  pay_food:["支付鸟牌食物费用；可用任意两份替代一份","Pay food; two food may replace one required food"],
  pay_eggs:["选择鸟蛋支付费用","Choose eggs to spend"],eggs:["选择放置鸟蛋的鸟类","Choose birds for eggs"],
  feeder:["从鸟食器选择食物","Choose food from the feeder"],food:["从供应区选择食物","Choose food from supply"],
  draw:["选择公开鸟牌或从牌堆抽取","Choose a face-up bird or draw from deck"],power:["选择是否激活鸟类能力","Choose whether to activate this bird"],
  tuck:["选择一张手牌压在鸟牌下","Choose a hand card to tuck"],discard_card:["选择一张手牌弃置","Choose a hand card to discard"],
  play:["可以额外打出一张鸟牌","You may play an additional bird"],repeat:["选择要重复的鸟类能力","Choose a power to repeat"],
  move:["迁徙到另一个栖息地","Move to another habitat"],choose_start:["选择从哪位玩家开始拿食物","Choose the first player to gain food"],
  draft_choose:["从这些鸟牌中选一张","Choose one of these birds"],trade:["交换一种食物","Trade one food"],
  food_tuck:["弃食物以压入牌堆的两张牌","Spend food to tuck two deck cards"],feeder_all:["获得鸟食器中的指定食物","Gain all matching feeder food"],
};
export function WingspanTable({view, lang, identities, actions = [], disabled, onChoose, onReset}: {view?: WingspanView; lang: Lang; identities: {seat: number; name: string}[]; actions?: Action[]; disabled?: boolean; onChoose: (a: Action)=>void; onReset?:()=>void}) {
  const [boardSeat,setBoardSeat]=useState<number|null>(null);
  const [kept,setKept]=useState<string[]>([]);
  if (!view) return null;
  const zh=lang==="zh", own=view.players[view.viewer_seat], player=view.players[boardSeat ?? view.viewer_seat];
  const birds=[...own.hand,...view.players.flatMap(p=>HABITATS.flatMap(h=>p.habitats[h])),...view.tray.filter((c):c is WingspanCard=>Boolean(c)),...view.draft];
  const name=(k:unknown)=>birds.find(b=>b.id===k)?.name || own.bonus_choices.find(b=>b.id===k)?.name || String(k);
  const label=(a:Record<string,unknown>)=>{
    const t=String(a.type);
    if(t==="skip") return zh?"跳过 / 完成这一步":"Skip / finish this step";
    if(t==="reroll") return zh?"重掷全部五枚骰子":"Reroll all five dice";
    if(t==="take_all_food") return zh?"拿取所有符合的食物":"Take all matching food";
    if(t==="take_food") return `${a.cache ? (zh?"贮藏":"Cache") : (zh?"获得":"Gain")} ${word(String(a.food),lang)}${a.face ? ` · ${String(a.face).split("/").map(f=>word(f,lang)).join(" / ")}` : ""}`;
    if(t==="discard_food") return `${zh?"弃置":"Discard"} ${word(String(a.food),lang)}`;
    if(t==="pay_food") return `${zh?"支付":"Pay"} ${(a.food as string[]).map(f=>word(f,lang)).join(" + ")}`;
    if(t==="draw_card") return a.source==="deck" ? (zh?"从牌堆抽一张":"Draw from deck") : `${zh?"拿取":"Take"} ${view.tray[Number(a.slot)]?.name}`;
    if(t==="choose_start") return `${zh?"从此玩家开始":"Start with"} ${identities[Number(a.seat)]?.name}`;
    if(t==="move_bird") return `${zh?"迁徙至":"Move to"} ${word(String(a.habitat),lang)}`;
    if(t==="trade_food") return `${word(String(a.give),lang)} → ${word(String(a.receive),lang)}`;
    const verbs:Record<string,string>={activate_power:zh?"激活":"Activate",repeat_power:zh?"重复":"Repeat",discard_card:zh?"弃置":"Discard",tuck_card:zh?"压卡":"Tuck",choose_bonus:zh?"保留":"Keep",draft_card:zh?"选择":"Choose",pay_egg:zh?"支付鸟蛋":"Spend egg",lay_egg:zh?"产蛋":"Lay egg"};
    return `${verbs[t] || t} · ${name(a.card_id || a.bird_id || "")}`;
  };
  const step=String(view.pending?.op || "turn");
  const setup=actions.some(a=>a.action.type==="keep_birds");
  const keepAction=actions.find(a=>a.action.type==="keep_birds" && JSON.stringify([...(a.action.card_ids as string[])].sort())===JSON.stringify([...kept].sort()));
  const cardActions=(c:WingspanCard)=>actions.filter(a=>["play_bird","lay_egg","pay_egg","activate_power"].includes(String(a.action.type)) && (a.action.card_id===c.id || a.action.bird_id===c.id));
  const otherActions=actions.filter(a=>!["keep_birds","play_bird","lay_egg","pay_egg","activate_power","choose_bonus"].includes(String(a.action.type)));
  return <div className={`ws-table ${setup ? "is-setup" : ""}`}>
    <header className="ws-heading"><div><span>WINGSPAN / FIELD NOTES</span><h2>{zh?"展翅翱翔":"A sanctuary takes flight"}</h2><p>{zh?`第 ${view.round} / 4 轮`:`Round ${view.round} of 4`} · {view.goal_board==="green" ? (zh?"竞争目标":"Competitive goals") : (zh?"独立目标":"Individual goals")}</p></div><div className="ws-round-number">{String(view.round).padStart(2,"0")}<small>/ 04</small></div></header>
    <div className="ws-goals">{view.goals.map((g,i)=><article key={g} className={i+1===view.round?"current":""}><span>{zh?"第":"ROUND "}{i+1}{zh?"轮":""}</span><b>{goalName(g,lang)}</b><small>{view.goal_history[i] ? view.goal_history[i].points.map((p,j)=>`${identities[j]?.name}: ${p}`).join(" · ") : view.goal_board==="blue" ? "0–5" : `${4+i} / ${1+i} / ${i}`}</small></article>)}</div>
    {view.status==="finished" && <div className="ws-step" role="status">{zh?"对局结束 · 奖励卡与最终得分已公开":"Game complete · bonus cards and final scores revealed"}</div>}
    <section className="ws-market"><header><h3>{zh?"公共鸟食器":"Shared birdfeeder"}</h3><small>{zh?"取走最后一枚时自动重掷":"Refills when empty"}</small></header><div className="ws-dice">{view.feeder.map((f,i)=><div className="ws-die" key={i}>{f.split("/").map(x=><Food key={x} food={x} lang={lang}/>)}</div>)}</div></section>
    {actions.length>0 && <section className="ws-decision" aria-live="polite"><h3>{STEPS[step]?.[zh?0:1] || (zh?"选择本回合行动":"Choose your action")}</h3>{view.pending?.bird ? <p>{name(view.pending.bird)}</p>:null}
      {setup && <><div className="ws-food-supply">{Object.entries(own.food).map(([f,n])=><Food key={f} food={f} count={n} lang={lang}/>)}</div><div className="ws-setup-picks">{own.hand.map(c=><div className={`ws-setup-card ${kept.includes(c.id)?"selected":""}`} key={c.id}><label><input type="checkbox" checked={kept.includes(c.id)} disabled={disabled} onChange={e=>{setKept(e.target.checked?[...kept,c.id]:kept.filter(k=>k!==c.id)); onReset?.();}}/>{zh?"保留":"Keep"} {c.name}</label><WingspanBird card={c} lang={lang}/></div>)}</div><button type="button" disabled={!keepAction || disabled} onClick={()=>keepAction&&onChoose(keepAction)}>{zh?`保留 ${kept.length} 张鸟牌，支付 ${kept.length} 个食物`:`Keep ${kept.length} birds; discard ${kept.length} food`}</button></>}
      <div className="ws-action-buttons">{otherActions.filter(a=>!["gain_food","lay_eggs","draw_cards"].includes(String(a.action.type)) && !(a.action.type==="draw_card" && a.action.source==="tray")).map(a=><button type="button" disabled={disabled} key={a.id} onClick={()=>onChoose(a)}>{label(a.action)}</button>)}</div>
      {own.bonus_choices.length>0 && <div className="ws-bonuses">{own.bonus_choices.map(b=>{const a=actions.find(a=>a.action.type==="choose_bonus"&&a.action.card_id===b.id);return <article key={b.id}><h4>{b.name}</h4><p>{bonusRule(b,lang)}</p>{a&&<button type="button" disabled={disabled} onClick={()=>onChoose(a)}>{zh?"保留奖励卡":"Keep bonus card"}</button>}</article>;})}</div>}
      {view.draft.length>0&&<div className="ws-cards">{view.draft.map(c=><WingspanBird key={c.id} card={c} lang={lang}/>)}</div>}
    </section>}
    {!setup && <section className="ws-preserve"><header><h3>{zh?"栖息地":"Wildlife preserves"}</h3><nav aria-label={zh?"选择玩家棋盘":"Choose player board"}>{identities.map(p=><button type="button" key={p.seat} aria-pressed={p.seat===player.seat} onClick={()=>setBoardSeat(p.seat)}>{p.name}</button>)}</nav></header>
      {HABITATS.map((h,i)=>{const row=player.habitats[h],kind=["gain_food","lay_eggs","draw_cards"][i],a=actions.find(a=>a.action.type===kind);return <section key={h} className={`ws-habitat ws-${h}`}><div className="ws-habitat-label"><h4>{word(h,lang)}</h4><span>{zh?["获得食物","产下鸟蛋","抽取鸟牌"][i]:["Gain food","Lay eggs","Draw birds"][i]}</span><b>{(i===1?2:1)+Math.floor(row.length/2)}{row.length%2?" +1*":""}</b>{a&&player.seat===own.seat&&<button type="button" disabled={disabled} onClick={()=>onChoose(a)}>{zh?"执行行动":"Take action"}</button>}</div><div className="ws-habitat-cards">{row.map(c=><WingspanBird key={c.id} card={c} lang={lang} actions={player.seat===own.seat?cardActions(c):[]} disabled={disabled} onChoose={onChoose}/>)}{row.length<5&&<div className="ws-empty-slot"><span>{zh?"下个位置":"Next space"} {row.length+1}</span><b>◯ {[0,1,1,2,2][row.length]}</b><small>{zh?"打鸟所需鸟蛋":"eggs to play a bird"}</small></div>}</div></section>;})}
    </section>}
    {!setup && <section className="ws-hand"><header><h3>{zh?"你的手牌":"Your hand"} <small>{own.hand_count}</small></h3><div className="ws-food-supply">{Object.entries(own.food).map(([f,n])=><Food key={f} food={f} count={n} lang={lang}/>)}</div></header><div className="ws-cards">{own.hand.map(c=><WingspanBird key={c.id} card={c} lang={lang} actions={cardActions(c)} disabled={disabled} onChoose={onChoose}/>)}</div><div className="ws-bonuses">{own.bonuses.map(b=><article key={b.id}><h4>{b.name}</h4><p>{bonusRule(b,lang)}</p><strong>{b.points} {zh?"分":"pts"}</strong></article>)}</div></section>}
    <section className="ws-tray"><header><h3>{zh?"公开鸟牌":"Face-up bird tray"}</h3><small>{view.deck_count} {zh?"张在牌堆 · 完整回合结束补充":"in deck · refills at turn end"}</small></header><div className="ws-cards">{view.tray.map((c,i)=>c?<WingspanBird key={c.id} card={c} lang={lang} actions={actions.filter(a=>a.action.type==="draw_card"&&a.action.source==="tray"&&a.action.slot===i)} disabled={disabled} onChoose={onChoose}/>:<div className="ws-empty-slot" key={i}>{zh?"等待回合结束补充":"Refills at turn end"}</div>)}</div></section>
    <details className="ws-rules"><summary>{zh?"规则与计分速查":"Rules & scoring reference"}</summary><p>{zh?"每位玩家四轮共 26 次行动。棕色能力从右向左激活；粉色能力每两个自己的回合之间最多使用一次。* 可支付手牌 / 食物 / 鸟蛋获得一次额外收益。鸟类英文名称用于名称类奖励卡。":"Each player takes 26 actions across four rounds. Brown powers run right to left; pink powers trigger at most once between your turns. * Pay a card / food / egg for one extra benefit."}</p><ul>{Object.values(view.rules).map((r,i)=><li key={i}>{r}</li>)}</ul></details>
  </div>;
}
