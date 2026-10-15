"use client";

import {useState} from "react";

export type HumanAction = {id: string; action: Record<string, unknown>};
type Lang = "zh" | "en";

/** Variants stay engine-owned: the UI selects an existing action, never rebuilds it. */
export function ActionChoices({actions, label, describe, lang, disabled, onChoose}: {
  actions: HumanAction[]; label: string; describe: (action: HumanAction) => string;
  lang: Lang; disabled?: boolean; onChoose: (action: HumanAction) => void;
}) {
  const [choice, setChoice] = useState("");
  if (!actions.length) return null;
  const selected = actions.find(a => a.id === choice) || actions[0];
  return <div className="human-choices">
    {actions.length > 1 && <label><span>{label} · {lang === "zh" ? "方案" : "Options"}</span><select disabled={disabled} value={selected.id} onChange={e => {setChoice(e.target.value); const next = actions.find(a => a.id === e.target.value); if (next) onChoose(next);}}>{actions.map(a => <option key={a.id} value={a.id}>{describe(a)}</option>)}</select></label>}
    <button type="button" disabled={disabled} aria-label={`${label} · ${describe(selected)}`} onClick={() => onChoose(selected)}>{label}{actions.length === 1 && <small>{describe(selected)}</small>}</button>
  </div>;
}

export function HumanConfirmation({label, selected, requirement, issue, busy, disabled, lang, onClear, onConfirm}: {
  label: string; selected: HumanAction | null; requirement?: string; issue?: string;
  busy: boolean; disabled: boolean; lang: Lang; onClear: () => void; onConfirm: () => void;
}) {
  const zh = lang === "zh";
  return <section className="human-confirmation" aria-label={zh ? "行动预览与确认" : "Action preview and confirmation"}>
    <div role="status"><strong>{selected ? label : requirement || (zh ? "在牌桌上选择行动" : "Choose an action on the table")}</strong><small>{zh ? "确认后执行；确认前可以重新选择。" : "Review before confirming. You can still change your choice."}</small></div>
    <button type="button" disabled={!selected || disabled} onClick={onClear}>{zh ? "清空" : "Clear"}</button>
    <button type="button" className="human-confirm-submit" disabled={!selected || disabled} onClick={onConfirm}>{busy ? (zh ? "提交中…" : "Submitting…") : (zh ? "确认行动" : "Confirm move")}</button>
    {issue && <p role="alert">{issue}</p>}
  </section>;
}

/** Resolve card references only from the same seat-scoped view already rendered. */
export function readableMove(action: Record<string, unknown>, view: unknown, lang: Lang, fallback: string) {
  const zh = lang === "zh";
  const names = new Map<string, string>();
  const spiceNames: Record<string,string> = zh ? {yellow:"姜黄",red:"藏红花",green:"豆蔻",brown:"肉桂"} : {yellow:"Turmeric",red:"Saffron",green:"Cardamom",brown:"Cinnamon"};
  const spiceList = (pool: unknown) => Object.entries((pool || {}) as Record<string,number>).filter(([,n])=>n>0).map(([key,n])=>`${spiceNames[key] || key} × ${n}`).join(" + ");
  const collect = (value: unknown) => {
    if (!value || typeof value !== "object") return;
    if (Array.isArray(value)) { value.forEach(collect); return; }
    const row = value as Record<string, unknown>;
    if (row.hidden) return;
    if (typeof row.id === "string" && typeof row.name === "string") names.set(row.id, row.name);
    if (typeof row.id === "string" && ["gain","trade","upgrade"].includes(String(row.kind))) {
      const effect = row.kind === "gain" ? `${zh?"获得":"Gain"} ${spiceList(row.output)}` : row.kind === "trade" ? `${spiceList(row.input)} → ${spiceList(row.output)}` : `${zh?"升级":"Upgrade"} ${row.upgrades}`;
      names.set(row.id, effect);
    }
    if (typeof row.id === "string" && typeof row.points === "number" && row.cost && !row.name && !row.kind) names.set(row.id, `${row.points} ${zh?"分订单":"point order"}`);
    Object.values(row).forEach(collect);
  };
  collect(view);
  const name = (id: unknown) => names.get(String(id)) || String(id || "");
  const colors: Record<string, string> = zh ? {blue:"水域",gray:"山地",brown:"树干",green:"树冠",yellow:"田野",red:"建筑"} : {blue:"water",gray:"mountain",brown:"trunk",green:"canopy",yellow:"field",red:"building"};
  const food: Record<string, string> = zh ? {invertebrate:"无脊椎动物",seed:"种子",fish:"鱼",fruit:"果实",rodent:"啮齿动物",wild:"任意食物"} : {};
  const habitat: Record<string, string> = zh ? {forest:"森林",grassland:"草原",wetland:"湿地"} : {};
  const type = String(action.type);
  const words: Record<string, string> = zh ? {gain_food:"获得食物",lay_eggs:"产蛋",draw_cards:"抽取鸟牌",reroll:"重掷鸟食器骰子",skip:"跳过 / 完成这一步",take_all_food:"获得所有符合的食物",end_turn:"结束回合"} : {gain_food:"Gain food",lay_eggs:"Lay eggs",draw_cards:"Draw birds",reroll:"Reroll feeder dice",skip:"Skip / finish this step",take_all_food:"Take all matching food",end_turn:"End turn"};
  let result = fallback;
  const game = (view as {game?: string} | undefined)?.game;
  if (game === "harmonies") {
    if (type === "take_tokens") result = zh ? `拿取第 ${Number(action.group) + 1} 组地形` : `Take token group ${Number(action.group) + 1}`;
    if (type === "place_token") result = `${colors[String(action.color)] || action.color} → ${zh ? "格" : "hex"} ${Number(action.cell) + 1}`;
    if (type === "take_animal" || type === "choose_spirit") result = `${zh ? "拿取" : "Take"} ${name(action.card_id)}`;
    if (type === "place_animal") result = `${zh ? "安置动物" : "Settle animal"} ${name(action.card_id)} → ${Number(action.cell) + 1}`;
  }
  if (game === "wingspan") {
    result = words[type] || fallback;
    if (type === "keep_birds") result = `${zh ? "保留起始鸟牌" : "Keep starting birds"}: ${(action.card_ids as string[]).map(name).join(" / ") || (zh ? "不留牌" : "none")}`;
    if (["discard_food", "take_food", "pay_food"].includes(type)) result = `${({discard_food:zh?"弃置食物":"Discard food",take_food:zh?"获得食物":"Gain food",pay_food:zh?"支付食物":"Pay food"})[type]}: ${(Array.isArray(action.food) ? action.food : [action.food]).map(f=>food[String(f)] || f).join(" + ")}`;
    if (type === "draw_card") result = action.source === "tray" ? `${zh?"拿取公开鸟牌":"Draw face-up bird"} ${Number(action.slot)+1}` : (zh?"从牌库抽取鸟牌":"Draw a bird from the deck");
    if (type === "play_bird") result = `${zh ? "打出" : "Play"} ${name(action.card_id)} → ${habitat[String(action.habitat)] || action.habitat}`;
    if (["choose_bonus","activate_power","lay_egg","pay_egg","tuck_card","draft_card","discard_card","repeat_power"].includes(type)) result = `${({choose_bonus:zh?"保留奖励卡":"Keep bonus",activate_power:zh?"激活":"Activate",lay_egg:zh?"放置鸟蛋":"Lay egg",pay_egg:zh?"支付鸟蛋":"Spend egg",tuck_card:zh?"压卡":"Tuck",draft_card:zh?"选择":"Draft",discard_card:zh?"弃置":"Discard",repeat_power:zh?"重复能力":"Repeat power"})[type]}: ${name(action.card_id || action.bird_id)}`;
  }
  // Longest IDs first prevents partial replacements of related card IDs.
  for (const [id, title] of [...names].sort((a,b)=>b[0].length-a[0].length)) result = result.replaceAll(id, title);
  return result;
}
