"use client";

import {type ReactNode, useMemo, useState} from "react";
import {createPortal} from "react-dom";

export type ArkLang = "zh" | "en";
export type ArkIdentity = {seat: number; name: string; backend?: string; model?: string};
export type ArkLegalAction = {id: string; action: Record<string, unknown>};
export type ArkCard = {
  id?: string; card_type?: string; tags?: string[]; continent?: string; implementation?: string;
  display_title?: string; display_summary?: string;
  cost?: number; enclosure_size?: number; appeal?: number; conservation?: number; reputation?: number;
  level?: number; income?: number; enclosure_id?: string; objective?: string; per?: number; maximum?: number; hidden?: true;
  icons?: Record<string, number>; requirements?: Array<string | Record<string, unknown>>;
  rock_requirement?: number; water_requirement?: number; special_enclosure?: string | null;
  abilities?: {keyword?: string; name_cn?: string; name_en?: string; effect_cn?: string; effect_en?: string; value?: unknown}[];
  mechanism_notes?: {timing?: string; summary_cn?: string; summary_en?: string}[];
  resolved_mechanics?: {timing: string; timing_cn: string; timing_en: string; description_cn: string; description_en: string; op?: string; source?: string}[];
  criterion_cn?: string; criterion_en?: string;
  tiers?: {id?: string; requirement?: number | string | null; conservation?: number; reputation?: number}[];
};
export type ArkActionCard = {action: string; strength: number; upgraded: boolean; tokens: string[]};
export type ArkCell = {
  q: number; r: number; terrain: "water" | "rock" | "buildable";
  placement_bonus?: ArkEffect; requires_build_upgrade?: boolean;
};
export type ArkBuilding = {
  id: string; type: string; size: number; shape_id?: string; rotation?: number; occupied: boolean; cells: {q: number; r: number}[];
};
export type ArkMap = {
  id: string; name: string; geometry_status: string; reference_status?: string; cells: ArkCell[]; buildings: ArkBuilding[];
  placement_bonus_slots?: {q: number; r: number; effect: ArkEffect}[];
  conservation_reward_slots?: {milestone: number; kind: string}[];
};
export type ArkPlayerSummaryView = {
  resources: {money: number; x_tokens: number; hand_count: number; hand_limit: number};
  tracks: {appeal: number; conservation: number; reputation: number; current_score?: number};
  counters: {continents: Record<string, number>; animals: Record<string, number>};
  action_cards: ArkActionCard[];
  association: {workers: ArkPlayerView["association_workers"]; partner_zoos: string[]; universities: string[]};
  conservation: {tokens_on_map: number; action_upgrades_claimed: number[]; bonuses_claimed: number[]; final_card_choice_resolved: boolean};
  supported_projects: string[];
};
export type ArkMapDisplay = {
  placement_rewards: {q: number; r: number; effect: {type?: string; amount?: number}; status: "available" | "claimed"; building_id?: string | null}[];
  conservation_rewards: {milestone: number; kind: string; status: "available" | "claimed"}[];
  player_board?: {
    partner_zoo_ladder: ArkAssetLadderSlot[]; university_ladder: ArkAssetLadderSlot[];
    workers: {available: number; committed: number; locked: {slot: number; status: string; unlock_reward?: ArkEffect | null}[]};
    conservation_programs: {kind: string; slots: {id: string; reward: ArkEffect; status: string}[]}[];
  };
  coverage?: {covered: number; total: number; complete: boolean; reward?: {type?: string; amount?: number}; status: "available" | "claimed"};
};
type ArkEffect = {type?: string; amount?: number; target_strength?: number};
type ArkAssetLadderSlot = {level: number; asset?: string | null; reward?: ArkEffect | null; status: "claimed" | "empty"};
export type ArkPlayerView = {
  seat: number; money: number; x_tokens: number; appeal: number; conservation: number; reputation: number;
  action_cards: ArkActionCard[];
  association_workers: {active: number; reserve: number; committed: {task?: string; workers?: number}[]};
  partner_zoos: string[]; universities: string[]; map: ArkMap; hand_count: number; initial_draw_count: number;
  initial_keep_required: number; hand: ArkCard[]; initial_draw: ArkCard[]; played_cards: ArkCard[];
  final_scoring_cards: (ArkCard | {hidden: true})[]; supported_projects: string[];
  upgrade_rewards_claimed: number[]; conservation_rewards_claimed?: number[];
  conservation_tokens_on_map?: number; final_card_choice_resolved: boolean;
  public_summary?: ArkPlayerSummaryView; map_display?: ArkMapDisplay;
};
export type ArkProject = {
  id: string; tag: string; levels: number[]; claims?: {seat: number; level: number}[]; implementation?: string;
  blocked_levels?: string[];
  display_title?: string; display_summary?: string; criterion_cn?: string; criterion_en?: string;
  tiers?: {id?: string; requirement?: number | string | null; conservation?: number; reputation?: number}[];
};
export type ArkView = {
  game: "ark_nova"; rules_version: string; implementation_status: string; status: string; phase: string;
  viewer_seat?: number;
  turn_count: number; decision_count: number; active_seat: number;
  turn: {active_seat: number; decision: string; action_card: string | null; remaining_plays: number};
  break_track: {position: number; limit?: number; start_marker: string; triggered: boolean};
  card_display: ArkCard[]; game_board_bonus_tiles: {
    id: string; milestone?: number; available?: boolean; label?: string; label_cn?: string; label_en?: string;
    implementation?: string; effects?: ({type?: string; amount?: number; op?: string; args?: Record<string, unknown>})[];
  }[];
  deck_count: number; discard_count: number; base_conservation_projects: ArkProject[];
  association_board: {
    partner_zoos: Record<string, number>; universities: Record<string, number>; blocked_two_player: string[];
    donations: {seat: number; cost: number}[];
  };
  association_display?: {
    partner_zoos: {id: string; remaining: number; owners: number[]}[];
    universities: {id: string; remaining: number; owners: number[]}[];
    workers: {seat: number; task?: string; workers?: number}[];
    donations: {seat: number; cost: number}[];
    donation_slots?: {position: number; cost: number; status: "available" | "claimed"; seat?: number | null}[];
    blocked_spaces: string[];
  };
  public_tracks?: Record<"break" | "appeal" | "conservation" | "reputation", {
    minimum: number; maximum: number; markers: {seat?: number; id?: string; position: number}[];
    rewards?: {position: number; symbol: string; kind: string}[];
    display_access?: {slot: number; minimum_reputation: number; maximum_reputation?: number; requires_cards_upgrade?: boolean}[];
  }> & {appeal_conservation?: {
    minimum: number; maximum: number; appeal_maximum: number; conservation_maximum: number;
    income: {appeal: number; money: number}[];
    conservation_spaces: {conservation: number; axis: number; score_offset: number}[];
    appeal_markers: {seat: number; position: number}[];
    conservation_markers: {seat: number; value: number; position: number; score_offset: number}[];
  }};
  players: ArkPlayerView[];
  pending_choice?: {choice_id: string; seat: number; prompt: string; options: {id: string; label: string}[]} | null;
};

const PLAYER_COLORS = ["#b85643", "#356f91", "#718b45", "#b48828"];
const CONTINENTS = ["africa", "europe", "asia", "americas", "australia"];
const ANIMAL_TAGS = ["bird", "predator", "herbivore", "reptile", "primate"];
const EXTRA_TAGS = ["bear", "petting_zoo", "research", "rock", "water"];
const ACTION_LABELS: Record<string, {zh: string; en: string}> = {
  animals: {zh: "动物", en: "Animals"}, cards: {zh: "卡牌", en: "Cards"},
  build: {zh: "建造", en: "Build"}, association: {zh: "协会", en: "Association"},
  sponsors: {zh: "赞助商", en: "Sponsors"},
};
const CONTINENT_META: Record<string, {mark: string; zh: string; en: string}> = {
  africa: {mark: "AF", zh: "非洲", en: "Africa"}, europe: {mark: "EU", zh: "欧洲", en: "Europe"},
  asia: {mark: "AS", zh: "亚洲", en: "Asia"}, americas: {mark: "AM", zh: "美洲", en: "Americas"},
  australia: {mark: "AU", zh: "澳洲", en: "Australia"},
};
const TAG_META: Record<string, {mark: string; zh: string; en: string}> = {
  bird: {mark: "B", zh: "鸟类", en: "Bird"}, predator: {mark: "P", zh: "肉食", en: "Predator"},
  herbivore: {mark: "H", zh: "草食", en: "Herbivore"}, reptile: {mark: "R", zh: "爬行", en: "Reptile"},
  primate: {mark: "M", zh: "猴类", en: "Primate"}, bear: {mark: "BE", zh: "熊", en: "Bear"},
  petting_zoo: {mark: "PE", zh: "萌宠", en: "Petting"}, research: {mark: "RS", zh: "研究", en: "Research"},
  rock: {mark: "MT", zh: "山", en: "Rock"}, water: {mark: "WT", zh: "水", en: "Water"},
};
const BUILDING_META: Record<string, {mark: string; zh: string; en: string}> = {
  standard_enclosure: {mark: "E", zh: "普通围栏", en: "Enclosure"}, pavilion: {mark: "P", zh: "凉亭", en: "Pavilion"},
  kiosk: {mark: "K", zh: "商亭", en: "Kiosk"}, petting_zoo: {mark: "PE", zh: "萌宠动物园", en: "Petting zoo"},
  reptile_house: {mark: "RH", zh: "爬行动物馆", en: "Reptile house"},
  large_bird_aviary: {mark: "BA", zh: "大型鸟舍", en: "Bird aviary"},
};

function copy(lang: ArkLang, zh: string, en: string) { return lang === "zh" ? zh : en; }
function playerName(identities: ArkIdentity[], seat: number, lang: ArkLang) {
  return identities.find(player => player.seat === seat)?.name || `${copy(lang, "玩家", "Player")} ${seat + 1}`;
}
function knownCard(card: ArkCard): card is ArkCard & {hidden?: never} { return !card.hidden; }
function actionType(item: ArkLegalAction) {
  const raw = String(item.action.type);
  if (raw === "draw_cards_action_card") return "draw_cards";
  const aliases: Record<string, string> = {
    start_action: "select_action", take_x_token_action: "take_x_token",
    begin_cards_draw: "draw_cards", snap_cards_action_card: "snap_card",
    discard_cards_action_card: "discard_card",
    select_animal_card: "play_animal", play_selected_animal: "play_animal_enclosure",
    play_sponsor_card: "play_sponsor", advance_sponsors_break: "advance_break",
    finish_sponsors_action: "finish_action", finish_animals_action: "finish_action",
    finish_build_action: "finish_action", finish_association_action: "finish_association_tasks",
    perform_association_task: "association_task", make_association_donation: "make_donation",
  };
  return aliases[raw] || raw;
}
function actionCardId(item: ArkLegalAction) {
  return String(item.action.card_id || item.action.instance_id || "");
}
function actionCardName(item: ArkLegalAction) {
  return String(item.action.action_card || item.action.action_card_id || "");
}
function sameCardIds(left: unknown, right: string[]) {
  return Array.isArray(left) && [...left].map(String).sort().join("|") === [...right].sort().join("|");
}
function cardTypeLabel(card: ArkCard, lang: ArkLang) {
  if (card.hidden) return copy(lang, "隐藏牌", "Hidden card");
  if (card.card_type === "animal") return copy(lang, "动物", "Animal");
  if (card.card_type === "sponsor") return copy(lang, "赞助商", "Sponsor");
  if (card.card_type === "conservation_project") return copy(lang, "保护项目", "Project");
  if (card.card_type === "final_scoring") return copy(lang, "终局计分", "Final scoring");
  return card.card_type?.replaceAll("_", " ") || copy(lang, "动物园牌", "Zoo card");
}

function cardTitle(card: ArkCard, lang: ArkLang) {
  if (card.hidden) return copy(lang, "隐藏卡牌", "Hidden card");
  return card.display_title || card.id || cardTypeLabel(card, lang);
}

function humanIcon(icon: string, lang: ArkLang) {
  if (CONTINENT_META[icon]) return CONTINENT_META[icon][lang];
  if (TAG_META[icon]) return TAG_META[icon][lang];
  const labels: Record<string, {zh: string; en: string}> = {
    science: {zh: "研究", en: "Research"}, partner_zoo: {zh: "合作动物园", en: "Partner zoo"},
    university: {zh: "大学", en: "University"}, conservation: {zh: "保护", en: "Conservation"},
  };
  return labels[icon]?.[lang] || icon.replaceAll("_", " ");
}

function readableRequirements(card: ArkCard) {
  return (card.requirements || []).filter((item): item is string => typeof item === "string" && Boolean(item.trim()));
}

function readableTiers(card: ArkCard) {
  return (card.tiers || []).filter(tier => tier.requirement !== undefined && tier.requirement !== null);
}

function readableMechanisms(card: ArkCard, lang: ArkLang) {
  if (card.resolved_mechanics?.length) return card.resolved_mechanics.map(mechanic => ({
    name: lang === "zh" ? mechanic.timing_cn : mechanic.timing_en,
    text: lang === "zh" ? mechanic.description_cn : mechanic.description_en,
    timing: mechanic.timing,
  }));
  const abilities = (card.abilities || []).map(ability => ({
    name: (lang === "zh" ? ability.name_cn : ability.name_en) || ability.keyword || copy(lang, "能力", "Ability"),
    text: (lang === "zh" ? ability.effect_cn : ability.effect_en) || "",
    timing: "ability",
  }));
  const sponsorNotes = (card.mechanism_notes || []).map(note => ({
    name: note.timing?.replaceAll("_", " ") || copy(lang, "机制", "Mechanism"),
    text: (lang === "zh" ? note.summary_cn : note.summary_en) || "",
    timing: note.timing || "reference",
  }));
  return [...abilities, ...sponsorNotes].filter(item => item.name || item.text);
}

function readableCardLabel(card: ArkCard, lang: ArkLang) {
  if (card.hidden) return cardTitle(card, lang);
  const requirements = readableRequirements(card);
  const mechanisms = readableMechanisms(card, lang);
  return [
    cardTitle(card, lang), cardTypeLabel(card, lang),
    card.cost !== undefined ? `${copy(lang, "费用", "Cost")} ${card.cost}` : "",
    card.level !== undefined ? `${copy(lang, "等级", "Level")} ${card.level}` : "",
    requirements.length ? `${copy(lang, "要求", "Requirements")} ${requirements.join("、")}` : "",
    mechanisms.map(item => `${item.name}: ${item.text}`).join("；"),
  ].filter(Boolean).join("；");
}

function cardCriterion(card: ArkCard, lang: ArkLang) {
  return (lang === "zh" ? card.criterion_cn : card.criterion_en) || card.objective?.replaceAll("_", " ") || "";
}

function cardIcons(card: ArkCard) {
  return Object.entries(card.icons || {}).filter(([, count]) => Number(count) > 0);
}

function shouldShowSummary(card: ArkCard) {
  if (!card.display_summary) return false;
  if (card.card_type === "sponsor" && /^Level \d+ sponsor; timings:/i.test(card.display_summary)) return false;
  if (["conservation_project", "final_scoring"].includes(card.card_type || "") && /structured reward|conservation project|endgame scoring card/i.test(card.display_summary)) return false;
  return true;
}

function CardDetailsOverlay({card, lang, open, pinned, onClose}: {
  card: ArkCard; lang: ArkLang; open: boolean; pinned: boolean; onClose: () => void;
}) {
  if (!open || typeof document === "undefined") return null;
  const title = cardTitle(card, lang);
  const requirements = readableRequirements(card);
  const mechanisms = readableMechanisms(card, lang);
  const tiers = readableTiers(card);
  const icons = cardIcons(card);
  const criterion = cardCriterion(card, lang);
  const special = card.special_enclosure ? BUILDING_META[card.special_enclosure]?.[lang] || card.special_enclosure.replaceAll("_", " ") : copy(lang, "普通围栏", "Standard enclosure");
  return createPortal(<aside className={`ark-card-details-overlay card-${card.card_type || "unknown"} ${pinned ? "is-pinned" : ""}`} role={pinned ? "dialog" : "tooltip"} aria-label={`${title} · ${copy(lang, "完整说明", "Full details")}`}>
    <header><div><span>{cardTypeLabel(card, lang)}</span><h3>{title}</h3><small>{card.id}</small></div>{pinned && <button type="button" onClick={onClose} aria-label={copy(lang, "关闭完整说明", "Close full details")}>×</button>}</header>
    {card.card_type === "animal" && <div className="ark-card-detail-stats">
      <span><b>{copy(lang, "费用", "Cost")}</b><strong>₡{card.cost ?? 0}</strong></span>
      <span><b>{copy(lang, "围栏", "Enclosure")}</b><strong>{special} {card.enclosure_size ?? "—"}</strong></span>
      <span><b>{copy(lang, "地形", "Terrain")}</b><strong>{(card.rock_requirement || 0) > 0 ? `⛰ ×${card.rock_requirement}` : ""}{(card.water_requirement || 0) > 0 ? ` 💧 ×${card.water_requirement}` : ""}{!(card.rock_requirement || card.water_requirement) ? copy(lang, "无要求", "None") : ""}</strong></span>
      <span><b>{copy(lang, "轨道收益", "Track gains")}</b><strong>{copy(lang, "魅力", "Appeal")} {card.appeal ?? 0} · {copy(lang, "保护", "Conservation")} {card.conservation ?? 0} · {copy(lang, "声望", "Reputation")} {card.reputation ?? 0}</strong></span>
    </div>}
    {card.card_type === "sponsor" && <div className="ark-card-detail-stats"><span><b>{copy(lang, "行动强度", "Action strength")}</b><strong>{card.level ?? "—"}</strong></span></div>}
    {shouldShowSummary(card) && <p className="ark-card-details-summary">{card.display_summary}</p>}
    <dl>
      {requirements.length > 0 && <div><dt>{copy(lang, "打出要求", "Play requirements")}</dt><dd>{requirements.join("；")}</dd></div>}
      {icons.length > 0 && <div><dt>{copy(lang, "获得图标", "Gained icons")}</dt><dd>{icons.map(([icon, count]) => `${humanIcon(icon, lang)}${count > 1 ? ` ×${count}` : ""}`).join("、")}</dd></div>}
      {criterion && <div><dt>{copy(lang, "检查内容与判定条件", "Criterion")}</dt><dd>{criterion}</dd></div>}
      {mechanisms.map((item, index) => <div key={`${item.name}-${index}`} className={`mechanic-timing-${item.timing}`}><dt>{item.name}</dt><dd>{item.text || copy(lang, "按结构化效果执行", "Resolve the structured effect")}</dd></div>)}
      {tiers.length > 0 && <div><dt>{copy(lang, "全部档位", "All tiers")}</dt><dd className="ark-card-details-tiers">{tiers.map((tier, index) => <span key={tier.id || index}><b>{copy(lang, "条件", "Check")} {String(tier.requirement)}</b><i>→</i><strong>{copy(lang, "保护", "Conservation")} +{tier.conservation ?? 0}</strong>{Number(tier.reputation || 0) > 0 && <small>{copy(lang, "声望", "Reputation")} +{tier.reputation}</small>}</span>)}</dd></div>}
    </dl>
    {!pinned && <footer>{copy(lang, "点击卡牌上的信息按钮可固定此说明。", "Click the card's info button to pin these details.")}</footer>}
  </aside>, document.body);
}

function ReadableCardFace({card, lang, selectionControl}: {
  card: ArkCard; lang: ArkLang; selectionControl?: ReactNode;
}) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [pinned, setPinned] = useState(false);
  if (card.hidden) return <div className="ark-readable-card-face is-hidden"><header className="ark-readable-card-heading"><i>?</i><div><b>{copy(lang, "隐藏卡牌", "Hidden card")}</b><small>{copy(lang, "仅牌背公开", "Only the card back is public")}</small></div>{selectionControl}</header></div>;
  const title = cardTitle(card, lang);
  const requirements = readableRequirements(card);
  const mechanisms = readableMechanisms(card, lang);
  const tiers = readableTiers(card);
  const icons = cardIcons(card);
  const criterion = cardCriterion(card, lang);
  const special = card.special_enclosure ? BUILDING_META[card.special_enclosure]?.[lang] || card.special_enclosure.replaceAll("_", " ") : copy(lang, "普通围栏", "Enclosure");
  const primaryMechanism = mechanisms[0];
  const infoLabel = `${copy(lang, "查看完整卡牌说明", "Show full card details")}：${title}`;
  const badge = card.card_type === "animal" ? <div className="ark-card-habitat-badge" title={`${special} ${card.enclosure_size ?? "—"}`}><strong>{card.enclosure_size ?? "—"}</strong><small>{special}</small><span>{(card.rock_requirement || 0) > 0 && <>⛰{card.rock_requirement}</>}{(card.water_requirement || 0) > 0 && <>💧{card.water_requirement}</>}</span></div>
    : card.card_type === "sponsor" ? <div className="ark-card-strength-badge"><strong>{card.level ?? "—"}</strong><small>{copy(lang, "行动强度", "Strength")}</small></div>
    : <div className="ark-card-criterion-badge"><strong>✓</strong><small>{copy(lang, "判定", "Check")}</small></div>;
  return <div className={`ark-readable-card-face face-${card.card_type || "unknown"}`} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
    <header className="ark-readable-card-heading">{badge}<div><b>{title}</b><small>{card.id}</small></div>{selectionControl}</header>
    {card.card_type === "animal" && <>
      <p className="ark-readable-card-cost"><b>{copy(lang, "费用", "Cost")} ₡{card.cost ?? 0}</b><span>{requirements.length ? `${copy(lang, "要求", "Requirements")} · ${requirements.join(" · ")}` : copy(lang, "无额外打出要求", "No extra play requirement")}</span></p>
      {icons.length > 0 && <div className="ark-readable-card-icons" aria-label={copy(lang, "获得图标", "Gained icons")}>{icons.map(([icon, count]) => <span key={icon} title={humanIcon(icon, lang)}><b>{humanIcon(icon, lang)}</b>{count > 1 ? ` ×${count}` : ""}</span>)}</div>}
      <div className="ark-readable-card-tracks"><span><b>{copy(lang, "魅力", "Appeal")}</b><strong>{card.appeal ?? 0}</strong></span><span><b>{copy(lang, "保护", "Conservation")}</b><strong>{card.conservation ?? 0}</strong></span><span><b>{copy(lang, "声望", "Reputation")}</b><strong>{card.reputation ?? 0}</strong></span></div>
      <p className="ark-readable-card-mechanism"><b>{copy(lang, "能力", "Ability")}</b><span>{primaryMechanism ? `${primaryMechanism.name}${primaryMechanism.text ? ` · ${primaryMechanism.text}` : ""}` : copy(lang, "无即时能力", "No immediate ability")}</span></p>
    </>}
    {card.card_type === "sponsor" && <>
      <p className="ark-readable-card-requirement"><b>{copy(lang, "条件", "Requirements")}</b><span>{requirements.length ? requirements.join(" · ") : copy(lang, "无额外条件", "None")}</span></p>
      {icons.length > 0 && <div className="ark-readable-card-icons" aria-label={copy(lang, "获得图标", "Gained icons")}>{icons.map(([icon, count]) => <span key={icon} title={humanIcon(icon, lang)}><b>{humanIcon(icon, lang)}</b>{count > 1 ? ` ×${count}` : ""}</span>)}</div>}
      <div className="ark-readable-card-mechanisms">{(mechanisms.length ? mechanisms.slice(0, 2) : [{name: copy(lang, "作用", "Effect"), text: shouldShowSummary(card) ? card.display_summary || "" : copy(lang, "结构化效果见详情", "See structured details"), timing: "fallback"}]).map((mechanic, index) => <p key={`${mechanic.name}-${index}`} className={`ark-readable-card-mechanism timing-${mechanic.timing}`}><b>{mechanic.name}</b><span>{mechanic.text}</span></p>)}</div>
    </>}
    {["conservation_project", "final_scoring"].includes(card.card_type || "") && <>
      <p className="ark-readable-card-criterion"><b>{copy(lang, "检查", "Check")}</b><span>{criterion || copy(lang, "依据卡牌条件计数", "Count the card criterion")}</span></p>
      {tiers.length > 0 && <div className="ark-readable-card-tiers" aria-label={copy(lang, "计分档位", "Scoring tiers")}>{tiers.map((tier, index) => <span key={tier.id || index}><b>{String(tier.requirement)}</b><i>→</i><strong>{copy(lang, "保护", "C")} +{tier.conservation ?? 0}</strong>{Number(tier.reputation || 0) > 0 && <small>{copy(lang, "声望", "R")} +{tier.reputation}</small>}</span>)}</div>}
    </>}
    {!["animal", "sponsor", "conservation_project", "final_scoring"].includes(card.card_type || "") && <p className="ark-readable-card-mechanism"><b>{copy(lang, "效果", "Effect")}</b><span>{primaryMechanism?.text || card.display_summary || copy(lang, "查看完整说明", "See details")}</span></p>}
    <button type="button" className="ark-readable-card-info" aria-label={infoLabel} aria-expanded={pinned} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} onClick={() => setPinned(value => !value)}>i</button>
    <CardDetailsOverlay card={card} lang={lang} open={hovered || focused || pinned} pinned={pinned} onClose={() => setPinned(false)}/>
  </div>;
}

function ProjectDetailsInfo({project, title, criterion, tiers, lang}: {
  project: ArkProject; title: string; criterion: string; tiers: NonNullable<ArkProject["tiers"]>; lang: ArkLang;
}) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [pinned, setPinned] = useState(false);
  const card: ArkCard = {id: project.id, card_type: "conservation_project", display_title: title, criterion_cn: criterion, criterion_en: criterion, tiers};
  return <span className="ark-project-details-trigger" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
    <button type="button" className="ark-project-info" aria-label={`${copy(lang, "查看完整保护项目说明", "Show full project details")}：${title}`} aria-expanded={pinned} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} onClick={() => setPinned(value => !value)}>i</button>
    <CardDetailsOverlay card={card} lang={lang} open={hovered || focused || pinned} pinned={pinned} onClose={() => setPinned(false)}/>
  </span>;
}
function countPlayed(player: ArkPlayerView, field: "continent" | "tag", value: string) {
  const projected = field === "continent" ? player.public_summary?.counters.continents : player.public_summary?.counters.animals;
  if (projected && value in projected) return projected[value];
  return player.played_cards.filter(knownCard).filter(card => field === "continent"
    ? card.card_type === "animal" && card.continent === value
    : card.tags?.includes(value)).length;
}
function benefitLabel(effect: {type?: string; amount?: number} | undefined, lang: ArkLang) {
  if (!effect?.type) return "—";
  if (effect.type === "take_card") return copy(lang, "拿取卡牌", "take card");
  if (effect.type === "clever") return copy(lang, "机敏：行动牌移至 1", "clever: move action to 1");
  const labels: Record<string, {zh: string; en: string}> = {
    gain_money: {zh: "金币", en: "money"}, gain_x_token: {zh: "X 标记", en: "X token"},
    gain_reputation: {zh: "声望", en: "reputation"}, gain_appeal: {zh: "魅力", en: "appeal"},
    gain_conservation: {zh: "保护", en: "conservation"}, draw_cards: {zh: "抽牌", en: "draw cards"},
    action_upgrade: {zh: "行动牌升级", en: "action upgrade"}, gain_worker: {zh: "事务员", en: "worker"},
    gain_determination: {zh: "精选", en: "determination"}, gain_enclosure: {zh: "围栏", en: "enclosure"},
  };
  const label = labels[effect.type];
  return `${label ? label[lang] : effect.type.replaceAll("_", " ")} +${effect.amount ?? 0}`;
}

function currentTrackScore(player: ArkPlayerView) {
  const projected = player.public_summary?.tracks.current_score;
  if (projected !== undefined) return projected;
  const conservationScore = player.conservation <= 10
    ? -14 + 2 * player.conservation : -24 + 3 * player.conservation;
  return player.appeal + conservationScore;
}

export function ArkNovaPlayerSummary({player, identity, active = false, lang}: {
  player: ArkPlayerView; identity?: ArkIdentity; active?: boolean; lang: ArkLang;
}) {
  const handLimit = player.public_summary?.resources.hand_limit ?? (player.universities.includes("hand-limit-5") ? 5 : 3);
  const actions = [...(player.public_summary?.action_cards || player.action_cards)].sort((a, b) => a.strength - b.strength);
  return <section className={`player-panel ark-public-summary ${active ? "active-player" : ""}`}
    style={{"--player-color": PLAYER_COLORS[player.seat] || PLAYER_COLORS[0]} as React.CSSProperties}>
    <header>
      <div><span className="seat-label">{copy(lang, "座位", "Seat")} {player.seat + 1}{active ? ` · ${copy(lang, "行动中", "ACTIVE")}` : ""}</span><h3>{identity?.name || `${copy(lang, "玩家", "Player")} ${player.seat + 1}`}</h3></div>
      <div className="ark-summary-totals">
        <span className="ark-summary-money" title={copy(lang, "金币", "Money")}><strong>{player.money}</strong><small>₡</small></span>
        <span className="ark-summary-score" title={copy(lang, "当前分数 = 魅力 + 保护点数分值", "Current score = Appeal + Conservation score")}><strong>{currentTrackScore(player)}</strong><small>{copy(lang, "分", "VP")}</small></span>
      </div>
    </header>
    <div className="ark-summary-primary" aria-label={copy(lang, "主要公开资源", "Public resources")}>
      <span><i>×</i><b>{player.x_tokens}</b><small>X</small></span>
      <span><i>R</i><b>{player.reputation}</b><small>{copy(lang, "声望", "REP")}</small></span>
      <span><i>C</i><b>{player.conservation}</b><small>{copy(lang, "保护", "CON")}</small></span>
      <span><i>A</i><b>{player.appeal}</b><small>{copy(lang, "魅力", "APL")}</small></span>
      <span><i>H</i><b>{player.hand_count}/{handLimit}</b><small>{copy(lang, "手牌", "HAND")}</small></span>
    </div>
    <div className="ark-summary-actions" aria-label={copy(lang, "行动牌顺序和强度", "Action card order and strength")}>
      {actions.map(card => <span key={card.action} className={`action-${card.action} action-level-${card.upgraded ? "ii" : "i"}`} title={`${ACTION_LABELS[card.action]?.[lang] || card.action} · ${card.strength}`}>
        <b>{card.strength}</b><em>{ACTION_LABELS[card.action]?.[lang] || card.action}</em><i>{card.upgraded ? "II" : "I"}{card.tokens.length ? ` · X${card.tokens.length}` : ""}</i>
      </span>)}
    </div>
    <SummaryCounterRow values={CONTINENTS} player={player} kind="continent" lang={lang}/>
    <SummaryCounterRow values={ANIMAL_TAGS} player={player} kind="tag" lang={lang}/>
    <SummaryCounterRow values={EXTRA_TAGS} player={player} kind="tag" lang={lang}/>
    <div className="ark-summary-workers">
      <span>{copy(lang, "事务员", "Workers")} <b>{player.association_workers.active}</b> / {player.association_workers.reserve}</span>
      <span>{copy(lang, "已派出", "Committed")} <b>{player.association_workers.committed.reduce((sum, item) => sum + (item.workers || 1), 0)}</b></span>
      <span>{copy(lang, "保护标记", "Conservation tokens")} <b>{player.conservation_tokens_on_map ?? "—"}</b></span>
    </div>
    <details className="ark-summary-assets">
      <summary>{copy(lang, "资产与公开牌", "Assets & public cards")}</summary>
      <div><b>{copy(lang, "合作动物园", "Partner zoos")}</b><span>{player.partner_zoos.length ? player.partner_zoos.map(value => CONTINENT_META[value]?.[lang] || value).join(" · ") : "—"}</span></div>
      <div><b>{copy(lang, "大学", "Universities")}</b><span>{player.universities.length ? player.universities.join(" · ") : "—"}</span></div>
      <div><b>{copy(lang, "保护项目", "Projects")}</b><span>{player.supported_projects.length || "—"}</span></div>
      <div><b>{copy(lang, "已打出", "Played")}</b><span>{player.played_cards.filter(knownCard).map(card => `${card.card_type?.slice(0, 1).toUpperCase()} · ${card.id}`).join(" / ") || "—"}</span></div>
    </details>
  </section>;
}

function SummaryCounterRow({values, player, kind, lang}: {
  values: string[]; player: ArkPlayerView; kind: "continent" | "tag"; lang: ArkLang;
}) {
  return <div className={`ark-counter-row counter-${kind}`}>{values.map(value => {
    const meta = kind === "continent" ? CONTINENT_META[value] : TAG_META[value];
    return <span key={value} title={meta?.[lang] || value}><i>{meta?.mark || value.slice(0, 2).toUpperCase()}</i><b>{countPlayed(player, kind, value)}</b></span>;
  })}</div>;
}

function trackRewardLabel(kind: string, lang: ArkLang) {
  const labels: Record<string, [string, string]> = {
    action_upgrade: ["升级一张行动卡牌", "Upgrade one action card"],
    action_upgrade_or_worker: ["升级一张行动卡牌，或者增加一名协会事务员", "Upgrade one action card or gain one association worker"],
    choose_board_bonus: ["选择该档仍可用的奖励；3/4 人局也可选择 5 金币", "Choose an available reward; in 3/4-player games, 5 money is also available"],
    final_card_choice: ["两张终局牌中弃置一张", "Discard one of your two final scoring cards"],
    gain_worker: ["增加一名协会事务员", "Gain one association worker"],
    take_card_or_deck: ["从声望范围拿一张牌，或从牌库抽一张", "Take a card in reputation range or draw from the deck"],
    gain_conservation: ["获得 1 保护点数", "Gain 1 conservation point"],
    gain_x_token: ["获得 1 个 X 标记", "Gain 1 X-token"],
  };
  return labels[kind]?.[lang === "zh" ? 0 : 1] || kind.replaceAll("_", " ");
}

function bonusTileLabel(tile: ArkView["game_board_bonus_tiles"][number], lang: ArkLang) {
  return (lang === "zh" ? tile.label_cn : tile.label_en) || tile.label || tile.id;
}

function bonusTileSymbol(id: string) {
  if (id.includes("reputation")) return "R+2";
  if (id.includes("x-3")) return "X×3";
  if (id.includes("enclosure")) return "E3";
  if (id.includes("cards-3")) return "▣×3";
  if (id.includes("money-10")) return "₡10";
  if (id.includes("money-5")) return "₡5";
  if (id.includes("multiplier")) return "×2";
  if (id.includes("university")) return "U";
  if (id.includes("partner-zoo")) return "Z";
  return "◇";
}

function TrackLane({label, tone, min = 0, max, values, rewards = [], lang}: {
  label: string; tone: string; min?: number; max: number; values: {seat: number; value: number; name: string}[];
  rewards?: {position: number; symbol: string; kind: string}[]; lang: ArkLang;
}) {
  const positions = Array.from({length: max - min + 1}, (_, value) => value + min);
  return <div className={`ark-ruler ark-ruler-${tone}`}>
    <header><b>{label}</b><span>{values.map(item => `${item.name} ${item.value}`).join(" · ")}</span></header>
    <div className="ark-ruler-cells" style={{gridTemplateColumns: `repeat(${positions.length}, 18px)`}}>
      {positions.map(position => { const reward = rewards.find(item => item.position === position); return <span key={position} className={position % 5 === 0 ? "major" : ""}>
        <small>{position}</small>{reward && <em title={`${label} ${position} · ${trackRewardLabel(reward.kind, lang)}`}>{reward.symbol}</em>}<i>{values.filter(item => item.value === position).map(item => <b key={item.seat} style={{background: PLAYER_COLORS[item.seat]}} title={item.name}>{item.seat + 1}</b>)}</i>
      </span>;})}
    </div>
  </div>;
}

function AppealConservationTrack({view, identities, lang}: {
  view: ArkView; identities: ArkIdentity[]; lang: ArkLang;
}) {
  const track = view.public_tracks?.appeal_conservation;
  const maximum = track?.maximum ?? 114;
  const appealMaximum = track?.appeal_maximum ?? 113;
  const positions = Array.from({length: maximum + 1}, (_, value) => value);
  const income = new Map((track?.income || []).map(item => [item.appeal, item.money]));
  const appealMarkers = track?.appeal_markers || view.players.map(player => ({seat: player.seat, position: player.appeal}));
  const conservationMarkers = track?.conservation_markers || [];
  const rewards = new Map((view.public_tracks?.conservation.rewards || []).map(item => [item.position, item]));
  const incomeSegments = positions.slice(0, appealMaximum + 1).reduce<{start: number; end: number; money: number}[]>((segments, position) => {
    const money = income.get(position);
    if (money === undefined) return segments;
    const previous = segments.at(-1);
    if (previous?.money === money && previous.end + 1 === position) previous.end = position;
    else segments.push({start: position, end: position, money});
    return segments;
  }, []);
  const sortedConservationSpaces = [...(track?.conservation_spaces || [])]
    .sort((left, right) => left.axis - right.axis);
  const conservationSegments = sortedConservationSpaces.map((space, index) => ({
    start: index === 0 ? 0 : space.axis,
    end: index === sortedConservationSpaces.length - 1 ? maximum : sortedConservationSpaces[index + 1].axis - 1,
    space,
  }));
  return <section className="ark-shared-score-track">
    <header><div><b>{copy(lang, "金币收入 / 魅力 / 保护点数", "Income / Appeal / Conservation")}</b><span>{copy(lang, "魅力从左向右；保护点从右向左，标记相遇或越过时触发终局。", "Appeal runs left-to-right; Conservation runs from the opposite end. Meeting or crossing triggers the end.")}</span></div><small>{copy(lang, "横向滑动查看完整 0–113 轨道", "Scroll horizontally for the full 0–113 track")}</small></header>
    <div className="ark-shared-score-scroll"><div className="ark-shared-score-cells" style={{gridTemplateColumns: `repeat(${positions.length}, 22px)`}}>
      {incomeSegments.map(segment => <span key={`income-${segment.start}`} className="ark-score-income-cell" style={{gridColumn: `${segment.start + 1} / ${segment.end + 2}`}} title={`${copy(lang, "魅力", "Appeal")} ${segment.start}–${segment.end} · ${copy(lang, "休息收入", "Break income")} ${segment.money}`}>
        ₡{segment.money}
      </span>)}
      {appealMaximum < maximum && <span className="ark-score-income-cell is-empty" style={{gridColumn: `${appealMaximum + 2} / ${maximum + 2}`}} aria-hidden="true"/>}
      {positions.map(position => {
        const appealHere = appealMarkers.filter(marker => marker.position === position);
        const money = income.get(position);
        const title = money === undefined ? `${copy(lang, "保护起点", "Conservation start")} · C0`
          : `${copy(lang, "魅力", "Appeal")} ${position} · ${copy(lang, "休息收入", "Break income")} ${money} ₡`;
        return <span key={`appeal-${position}`} className={`ark-score-appeal-cell ${position % 5 === 0 ? "major" : ""} ${appealHere.length ? "has-appeal" : ""} ${money === undefined ? "is-endpoint" : ""}`} style={{gridColumn: `${position + 1} / ${position + 2}`}} title={title}>
          <b className="appeal-value">{money === undefined ? "" : position}</b>
          <i className="appeal-markers">{appealHere.map(marker => <em key={marker.seat} style={{background: PLAYER_COLORS[marker.seat]}} title={`${playerName(identities, marker.seat, lang)} · A${position}`}>{marker.seat + 1}</em>)}</i>
        </span>;
      })}
      {conservationSegments.map(({start, end, space}) => {
        const reward = rewards.get(space.conservation);
        const conservationHere = conservationMarkers.filter(marker => marker.value === space.conservation);
        const rewardText = reward ? ` · ${trackRewardLabel(reward.kind, lang)}` : "";
        return <span key={`conservation-${space.conservation}`} className={`ark-score-conservation-cell ${conservationHere.length ? "has-conservation" : ""} ${reward ? "has-reward" : ""}`} style={{gridColumn: `${start + 1} / ${end + 2}`}} title={`C${space.conservation} · ${copy(lang, "魅力范围", "Appeal range")} ${start}–${end} · ${copy(lang, "计分偏移", "score offset")} ${space.score_offset}${rewardText}`}>
          <small className="conservation-score">{space.score_offset}{copy(lang, "分", " VP")}</small>
          <small className="conservation-value">C{space.conservation}</small>
          {reward && <em className="ark-track-reward-badge" title={trackRewardLabel(reward.kind, lang)}>{reward.symbol}</em>}
          <i className="conservation-markers">{conservationHere.map(marker => <em key={marker.seat} style={{background: PLAYER_COLORS[marker.seat]}} title={`${playerName(identities, marker.seat, lang)} · C${marker.value}`}>{marker.seat + 1}</em>)}</i>
        </span>;
      })}
    </div></div>
  </section>;
}

function GameBoard({view, identities, lang, legalActions, submitting, onChoose, selectedAnimal, onSelectAnimal}: {
  view: ArkView; identities: ArkIdentity[]; lang: ArkLang; legalActions: ArkLegalAction[]; submitting: string;
  onChoose?: (action: ArkLegalAction) => void; selectedAnimal: string; onSelectAnimal: (cardId: string) => void;
}) {
  const values = (key: "appeal" | "conservation" | "reputation") => view.players.map(player => ({
    seat: player.seat, value: player[key], name: playerName(identities, player.seat, lang),
  }));
  const maximum = (key: "appeal" | "conservation" | "reputation", floor: number) => Math.max(floor, ...view.players.map(player => player[key] + 3));
  const breakValues = [{seat: view.active_seat, value: view.break_track.position, name: copy(lang, "休息标记", "Break marker")}];
  const displayActions = (card: ArkCard) => legalActions.filter(item => actionCardId(item) === card.id && (item.action.source === "display" || ["snap_card"].includes(actionType(item))));
  const reputationAccess = view.public_tracks?.reputation.display_access || [
    [1, 1], [2, 3], [4, 6], [7, 9], [10, 12], [13, 15],
  ].map(([minimum_reputation, maximum_reputation], index) => ({slot: index + 1, minimum_reputation, maximum_reputation, requires_cards_upgrade: minimum_reputation >= 10}));
  const rewardLegend = [...(view.public_tracks?.conservation.rewards || []), ...(view.public_tracks?.reputation.rewards || [])]
    .filter((reward, index, all) => all.findIndex(candidate => candidate.kind === reward.kind) === index);
  const normalizedBonusTiles = view.game_board_bonus_tiles.map((tile, index) => ({
    ...tile, milestone: tile.milestone ?? (index < 2 ? 5 : 8),
  }));
  const bonusGroups = [5, 8].map(milestone => ({
    milestone,
    tiles: normalizedBonusTiles.filter(tile => tile.milestone === milestone),
  }));
  return <section className="ark-surface ark-game-board">
    <header className="ark-surface-header"><div><span>GAME BOARD</span><h2>{copy(lang, "整体游戏板", "Main game board")}</h2></div><div className="ark-turn-stamp"><span>{copy(lang, "当前决策", "CURRENT DECISION")}</span><b>{view.turn.decision.replaceAll("_", " ")}</b></div></header>
    <div className="ark-game-board-scroll"><div className="ark-game-board-canvas">
      <div className="ark-public-tracks">
        <TrackLane label={copy(lang, "休息", "BREAK")} tone="break" max={view.public_tracks?.break.maximum ?? view.break_track.limit ?? Math.max(9, view.break_track.position + 3)} values={breakValues} rewards={view.public_tracks?.break.rewards} lang={lang}/>
        <AppealConservationTrack view={view} identities={identities} lang={lang}/>
        <TrackLane label={copy(lang, "声望", "REPUTATION")} tone="reputation" min={view.public_tracks?.reputation.minimum ?? 1} max={view.public_tracks?.reputation.maximum ?? maximum("reputation", 15)} values={values("reputation")} rewards={view.public_tracks?.reputation.rewards} lang={lang}/>
        <div className="ark-track-reward-legend"><b>{copy(lang, "进度奖励图例", "TRACK REWARD LEGEND")}</b>{rewardLegend.map(reward => <span key={reward.kind} title={trackRewardLabel(reward.kind, lang)}><i>{reward.symbol}</i>{trackRewardLabel(reward.kind, lang)}</span>)}</div>
      </div>
      <div className="ark-board-lower">
      <section className="ark-card-display">
        <header><b>{copy(lang, "中央卡牌展示区", "Card display")}</b><span>{copy(lang, "牌库", "Deck")} {view.deck_count} · {copy(lang, "弃牌", "Discard")} {view.discard_count}</span></header>
        <div className="ark-reputation-display" aria-label={copy(lang, "声望可拿取范围", "Reputation access range")}>{reputationAccess.map(access => {
          const maximumReputation = access.maximum_reputation ?? access.minimum_reputation;
          const range = access.minimum_reputation === maximumReputation ? `${access.minimum_reputation}` : `${access.minimum_reputation}–${maximumReputation}`;
          return <span key={access.slot} className={access.requires_cards_upgrade ? "requires-cards-ii" : ""} title={`${copy(lang, "声望范围", "Reputation range")} ${range}${access.requires_cards_upgrade ? ` · ${copy(lang, "需要卡牌 II", "Cards II required")}` : ""}`}><b>R {range}{access.requires_cards_upgrade ? " · II" : ""}</b><i>{view.players.filter(player => player.reputation >= access.minimum_reputation && player.reputation <= maximumReputation).map(player => <em key={player.seat} style={{background: PLAYER_COLORS[player.seat]}}>{player.seat + 1}</em>)}</i></span>;
        })}</div>
        <div>{view.card_display.map((card, index) => { const actions = displayActions(card); const animal = actions.find(item => actionType(item) === "play_animal"); return <article key={card.id || index} aria-label={readableCardLabel(card, lang)} className={`ark-readable-card ${card.hidden ? "is-facedown" : `card-${card.card_type}`} ${actions.length ? "is-actionable" : ""} ${animal && card.id === selectedAnimal ? "selected" : ""}`}>
          <ReadableCardFace card={card} lang={lang}/>
          {actions.length > 0 && <footer>{animal && card.id && <button disabled={Boolean(submitting)} aria-pressed={card.id === selectedAnimal} onClick={() => {onSelectAnimal(card.id as string); if (animal.action.type === "select_animal_card") onChoose?.(animal);}}>{card.id === selectedAnimal ? copy(lang, "已选择，去地图选围栏", "Selected; choose an enclosure") : copy(lang, "选择这只动物", "Choose this animal")}</button>}{actions.filter(item => actionType(item) !== "play_animal").map(item => <button key={item.id} disabled={Boolean(submitting)} onClick={() => onChoose?.(item)}>{actionType(item) === "snap_card" ? copy(lang, "拿取", "Snap") : copy(lang, "打出", "Play")}{submitting === item.id ? "…" : ""}</button>)}</footer>}
        </article>;})}</div>
      </section>
      <section className="ark-bonus-bank"><header><b>{copy(lang, "游戏板奖励", "Board bonuses")}</b><span>{copy(lang, "开局从 9 枚中随机抽取 4 枚", "4 of 9 tiles drawn at setup")}</span></header><div className="ark-bonus-milestones">{bonusGroups.map(group => <article key={group.milestone}><header><b>C{group.milestone}</b><span>{copy(lang, "到达时选择一项", "Choose one on arrival")}</span></header><div>{group.tiles.map(tile => <span key={tile.id} className={tile.available === false ? "is-taken" : "is-available"} title={`${copy(lang, `保护 ${group.milestone} 点`, `Conservation ${group.milestone}`)} · ${bonusTileLabel(tile, lang)} · ${tile.available === false ? copy(lang, "已被其他玩家选走", "Already taken") : copy(lang, "仍可选择", "Available")}`}><i>{bonusTileSymbol(tile.id)}</i><b>{bonusTileLabel(tile, lang)}</b><small>{tile.available === false ? copy(lang, "已取走", "TAKEN") : copy(lang, "奖励板块", "BONUS TILE")}</small></span>)}{view.players.length >= 3 && <span className="money-option" title={copy(lang, "3/4 人局固定可选；即使两枚奖励板块已取走仍可选择", "Always available in 3/4-player games, even after both tiles are taken")}><i>₡5</i><b>{copy(lang, "获得 5 金币", "Gain 5 money")}</b><small>{copy(lang, "3/4 人局固定选项", "3/4P FIXED OPTION")}</small></span>}</div></article>)}</div></section>
      </div>
    </div></div>
  </section>;
}

function AssociationBoard({view, identities, lang, legalActions, submitting, onChoose}: {
  view: ArkView; identities: ArkIdentity[]; lang: ArkLang; legalActions: ArkLegalAction[]; submitting: string;
  onChoose?: (action: ArkLegalAction) => void;
}) {
  const zooStock = view.association_display?.partner_zoos || Object.entries(view.association_board.partner_zoos).map(([id, remaining]) => ({id, remaining, owners: view.players.filter(player => player.partner_zoos.includes(id)).map(player => player.seat)}));
  const universityStock = view.association_display?.universities || Object.entries(view.association_board.universities).map(([id, remaining]) => ({id, remaining, owners: view.players.filter(player => player.universities.includes(id)).map(player => player.seat)}));
  const committed = view.association_display?.workers || view.players.flatMap(player => player.association_workers.committed.map(item => ({...item, seat: player.seat})));
  const associationActive = view.turn.action_card === "association" || view.phase.startsWith("association_");
  const associationActions = associationActive ? legalActions.filter(item => ["association_task", "make_donation", "finish_association_tasks", "finish_action"].includes(String(item.action.type))) : [];
  const taskAction = (task: string, field?: string, value?: string | number) => associationActions.find(item => actionType(item) === "association_task" && (item.action.task === task || item.action.task_id === task.replaceAll("_", "-")) && (!field || item.action[field] === value));
  const reputationAction = taskAction("reputation");
  const donationAction = associationActions.find(item => actionType(item) === "make_donation");
  const finishAction = associationActions.find(item => ["finish_association_tasks", "finish_action"].includes(String(item.action.type)));
  const uniMeta: Record<string, {mark: string; label: string; reward: string}> = {
    "research-2": {mark: "RS×2", label: copy(lang, "研究大学", "Research university"), reward: copy(lang, "获得 2 个研究图标", "2 research icons")},
    "research-reputation": {mark: "RS+R", label: copy(lang, "声望大学", "Reputation university"), reward: copy(lang, "研究图标 ×1、声望 +2", "1 research icon, +2 reputation")},
    "hand-limit-5": {mark: "RS+H5", label: copy(lang, "手牌大学", "Hand university"), reward: copy(lang, "研究图标 ×1、手牌上限 5", "1 research icon, hand limit 5")},
  };
  return <section className="ark-surface ark-association-board">
    <header className="ark-surface-header"><div><span>ASSOCIATION BOARD</span><h2>{copy(lang, "协会板", "Association board")}</h2></div><p>{copy(lang, "空槽会保留，并标出领取者；事务员按实际任务位置显示。", "Empty slots remain visible and show their owner; workers sit on their committed task.")}</p></header>
    <div className="ark-association-lanes">
      <section className={`association-lane lane-two ${reputationAction ? "is-actionable" : ""}`}><header><b>2</b><span>{copy(lang, "声望", "Reputation")}</span></header>{reputationAction && <button className="association-task-button" disabled={Boolean(submitting)} onClick={() => onChoose?.(reputationAction)}><b>+2 R</b><small>{copy(lang, "派出事务员", "Send worker")}</small></button>}<div className="association-workers">{committed.filter(item => item.task === "reputation").map((item, index) => <PlayerToken key={`${item.seat}-${index}`} seat={item.seat} label={playerName(identities, item.seat, lang)}/>)}</div></section>
      <section className="association-lane lane-three"><header><b>3</b><span>{copy(lang, "合作动物园", "Partner zoos")}</span></header><div className="association-stock zoo-stock">{zooStock.map(({id, remaining, owners}) => {
        const meta = CONTINENT_META[id]; const action = taskAction("partner_zoo", "continent", id);
        const ownerText = owners.length ? `${copy(lang, "已拥有", "Owned by")} ${owners.map(seat => playerName(identities, seat, lang)).join(" · ")}` : copy(lang, "无人拥有", "Owned by none");
        return <article key={id} className={`${remaining ? "available" : "taken"} ${action ? "is-actionable" : ""}`}><i>{meta?.mark || id.slice(0, 2).toUpperCase()}</i><div><b>{meta?.[lang] || id}</b><small>{remaining ? `${copy(lang, "本轮可领取", "Available this round")} · ${ownerText}` : `${copy(lang, "本轮已取", "Taken this round")} · ${ownerText}`}</small></div>{remaining ? action ? <button className="association-claim-button" disabled={Boolean(submitting)} onClick={() => onChoose?.(action)}>{copy(lang, "选择", "Choose")}</button> : <em>×1</em> : <span className="association-owner-tokens">{owners.map(seat => <PlayerToken key={seat} seat={seat} label={playerName(identities, seat, lang)}/>)}</span>}</article>;
      })}</div><div className="association-workers">{committed.filter(item => item.task === "partner_zoo").map((item, index) => <PlayerToken key={`${item.seat}-${index}`} seat={item.seat} label={playerName(identities, item.seat, lang)}/>)}</div></section>
      <section className="association-lane lane-four"><header><b>4</b><span>{copy(lang, "大学", "Universities")}</span></header><div className="association-stock university-stock">{universityStock.map(({id, remaining, owners}) => {
        const meta = uniMeta[id] || {mark: "U", label: id, reward: "—"}; const action = taskAction("university", "university", id);
        const ownerText = owners.length ? `${copy(lang, "已拥有", "Owned by")} ${owners.map(seat => playerName(identities, seat, lang)).join(" · ")}` : copy(lang, "无人拥有", "Owned by none");
        return <article key={id} className={`${remaining ? "available" : "taken"} ${action ? "is-actionable" : ""}`}><i>{meta.mark}</i><div><b>{meta.label}</b><small>{remaining ? `${copy(lang, "本轮可领取", "Available this round")} · ${ownerText} · ${meta.reward}` : `${copy(lang, "本轮已取", "Taken this round")} · ${ownerText} · ${meta.reward}`}</small></div>{remaining ? action ? <button className="association-claim-button" disabled={Boolean(submitting)} onClick={() => onChoose?.(action)}>{copy(lang, "选择", "Choose")}</button> : <em>×1</em> : <span className="association-owner-tokens">{owners.map(seat => <PlayerToken key={seat} seat={seat} label={playerName(identities, seat, lang)}/>)}</span>}</article>;
      })}</div><div className="association-workers">{committed.filter(item => item.task === "university").map((item, index) => <PlayerToken key={`${item.seat}-${index}`} seat={item.seat} label={playerName(identities, item.seat, lang)}/>)}</div></section>
      <section className="association-lane lane-five"><header><b>5</b><span>{copy(lang, "保护项目", "Conservation")}</span></header><div className="association-workers">{committed.filter(item => ["conservation_project", "release_animal"].includes(item.task || "")).map((item, index) => <PlayerToken key={`${item.seat}-${index}`} seat={item.seat} label={playerName(identities, item.seat, lang)}/>)}</div></section>
    </div>
    <div className="ark-project-row">{view.base_conservation_projects.map(project => {
      const title = project.display_title || project.tag || project.id;
      const criterion = (lang === "zh" ? project.criterion_cn : project.criterion_en) || project.display_summary || "";
      const tiers: NonNullable<ArkProject["tiers"]> = project.tiers?.length ? project.tiers : project.levels.map(level => ({requirement: level, conservation: level}));
      return <article key={project.id} aria-label={`${title}；${criterion}`}><header><i>✓</i><div><b>{title}</b><small>{criterion || project.id}</small></div></header><div>{tiers.map((tier, index) => {
        const conservation = Number(tier.conservation ?? 0);
        const blocked = Boolean(tier.id && project.blocked_levels?.includes(tier.id));
        const claim = project.claims?.find(item => item.level === conservation);
        const action = taskAction("conservation_project", "project_id", project.id);
        const levelAction = action?.action.level === conservation ? action : associationActions.find(item => item.action.type === "association_task" && item.action.task === "conservation_project" && item.action.project_id === project.id && item.action.level === conservation);
        return <span key={tier.id || index} className={`${claim ? "claimed" : ""} ${!blocked && levelAction ? "is-actionable" : ""} ${blocked ? "is-blocked" : ""}`} title={blocked ? copy(lang, "双人游戏：此槽位被遮住，不允许放置标记", "Two-player game: this slot is covered and cannot receive a token") : `${criterion} · ${copy(lang, "要求", "Requirement")} ${String(tier.requirement ?? "—")} · +${conservation} C`}><b>{String(tier.requirement ?? "—")}</b><i>+{conservation} C{Number(tier.reputation || 0) > 0 ? ` · +${tier.reputation} R` : ""}</i>{blocked ? <small>{copy(lang, "双人封锁", "2P BLOCKED")}</small> : claim ? <PlayerToken seat={claim.seat} label={playerName(identities, claim.seat, lang)}/> : levelAction ? <button disabled={Boolean(submitting)} onClick={() => onChoose?.(levelAction)}>{copy(lang, "支持", "Support")}</button> : <small>{copy(lang, "要求值", "required")}</small>}</span>;
      })}</div><ProjectDetailsInfo project={project} title={title} criterion={criterion} tiers={tiers} lang={lang}/></article>;
    })}</div>
    {associationActions.some(item => item.action.task === "release_animal") && <section className="ark-release-actions"><b>{copy(lang, "动物放归项目", "Animal release projects")}</b><div>{associationActions.filter(item => item.action.task === "release_animal").map(item => <button key={item.id} disabled={Boolean(submitting)} onClick={() => onChoose?.(item)}><span>{String(item.action.card_id)}</span><small>{copy(lang, "放归", "Release")} · {String(item.action.project_card_id)} · {copy(lang, "等级", "level")} {String(item.action.level)}</small></button>)}</div></section>}
    <footer className="ark-donation-row"><b>{copy(lang, "捐款", "Donations")}</b>{(view.association_display?.donation_slots || view.association_board.donations.map((donation, index) => ({position: index + 1, cost: donation.cost, status: "claimed" as const, seat: donation.seat}))).map(slot => <span key={slot.position} className={slot.status}>{slot.seat !== null && slot.seat !== undefined ? <PlayerToken seat={slot.seat} label={playerName(identities, slot.seat, lang)}/> : <small>{slot.position}</small>}<i>{slot.cost} ₡</i></span>)}{donationAction && <button className="ark-donate-button" disabled={Boolean(submitting)} onClick={() => onChoose?.(donationAction)}>{copy(lang, "捐款", "Donate")} {String(donationAction.action.cost)} ₡</button>}{finishAction && <button className="ark-finish-association" disabled={Boolean(submitting)} onClick={() => onChoose?.(finishAction)}>{copy(lang, "结束协会行动", "Finish association")}</button>}{view.association_board.blocked_two_player.length > 0 && <em>{copy(lang, "双人封锁", "2P blocked")} × {view.association_board.blocked_two_player.length}</em>}</footer>
  </section>;
}

function PlayerToken({seat, label}: {seat: number; label: string}) {
  return <b className="ark-player-token" style={{background: PLAYER_COLORS[seat]}} title={label}>{seat + 1}</b>;
}

function hexKey(cell: {q: number; r: number}) { return `${cell.q}:${cell.r}`; }
function buildingName(type: string, lang: ArkLang) { return BUILDING_META[type]?.[lang] || type.replaceAll("_", " "); }

function ZooMap({player, lang, legalActions, submitting, onChoose, selectedAnimal}: {
  player: ArkPlayerView; lang: ArkLang; legalActions: ArkLegalAction[]; submitting: string;
  onChoose?: (action: ArkLegalAction) => void; selectedAnimal: string;
}) {
  const placements = useMemo(() => legalActions.filter(item => item.action.type === "place_building"), [legalActions]);
  const animalActions = useMemo(() => legalActions.filter(item => actionType(item) === "play_animal"), [legalActions]);
  const animalTargets = useMemo(() => legalActions.filter(item => actionType(item) === "play_animal_enclosure"), [legalActions]);
  const buildOptions = useMemo(() => [...new Map(placements.map(item => {
    const rotation = Number(item.action.rotation || 0);
    return [`${item.action.building_type}:${item.action.size}:${rotation}`, {type: String(item.action.building_type), size: Number(item.action.size), rotation}];
  })).values()], [placements]);
  const [selectedBuild, setSelectedBuild] = useState("");
  const effectiveBuild = buildOptions.some(item => `${item.type}:${item.size}:${item.rotation}` === selectedBuild) ? selectedBuild : buildOptions[0] ? `${buildOptions[0].type}:${buildOptions[0].size}:${buildOptions[0].rotation}` : "";
  const animalIds = useMemo(() => [...new Set(animalActions.map(actionCardId))], [animalActions]);
  const effectiveAnimal = animalIds.includes(selectedAnimal) ? selectedAnimal : "";
  const filteredPlacements = placements.filter(item => `${item.action.building_type}:${item.action.size}:${Number(item.action.rotation || 0)}` === effectiveBuild);
  const filteredAnimals = animalActions.filter(item => item.action.card_id === effectiveAnimal);
  const [hoveredAction, setHoveredAction] = useState("");
  const [selectedCellKey, setSelectedCellKey] = useState("");
  const preview = filteredPlacements.find(item => item.id === hoveredAction);
  const previewCells = new Set((((preview?.action.cells || []) as {q: number; r: number}[])).map(hexKey));
  const legalCells = new Set(filteredPlacements.map(item => hexKey(item.action.anchor as {q: number; r: number})));
  const animalEnclosures = new Set([
    ...filteredAnimals.map(item => String(item.action.enclosure_id)),
    ...animalTargets.map(item => String(item.action.building_id)),
  ]);
  const buildingByCell = new Map<string, ArkBuilding>();
  player.map.buildings.forEach(building => building.cells.forEach(cell => buildingByCell.set(hexKey(cell), building)));
  const rewardByCell = new Map((player.map_display?.placement_rewards || []).map(reward => [hexKey(reward), reward]));
  const cardByEnclosure = new Map(player.played_cards.filter(knownCard).filter(card => card.enclosure_id).map(card => [card.enclosure_id as string, card]));
  const hexRadius = 30; const pad = 48;
  const rawPoint = (cell: {q: number; r: number}) => ({
    x: hexRadius * 1.5 * cell.q,
    y: hexRadius * Math.sqrt(3) * (cell.r + cell.q / 2),
  });
  const rawPoints = player.map.cells.map(rawPoint);
  const minimumX = Math.min(...rawPoints.map(value => value.x)); const maximumX = Math.max(...rawPoints.map(value => value.x));
  const minimumY = Math.min(...rawPoints.map(value => value.y)); const maximumY = Math.max(...rawPoints.map(value => value.y));
  const point = (cell: {q: number; r: number}) => { const raw = rawPoint(cell); return {x: pad + raw.x - minimumX, y: pad + raw.y - minimumY}; };
  const width = maximumX - minimumX + pad * 2; const height = maximumY - minimumY + pad * 2;
  function clickCell(cell: ArkCell, building?: ArkBuilding) {
    setSelectedCellKey(hexKey(cell));
    if (!onChoose) return;
    if (effectiveBuild) {
      const action = filteredPlacements.find(item => item.id === hoveredAction)
        || filteredPlacements.find(item => hexKey(item.action.anchor as {q: number; r: number}) === hexKey(cell));
      if (action) onChoose(action);
      return;
    }
    if (building && animalEnclosures.has(building.id)) {
      const action = filteredAnimals.find(item => item.action.enclosure_id === building.id)
        || animalTargets.find(item => item.action.building_id === building.id);
      if (action) onChoose(action);
    }
  }
  function moveFocus(event: React.KeyboardEvent<HTMLButtonElement>, cell: ArkCell) {
    const directions: Record<string, {q: number; r: number}> = {
      ArrowRight: {q: 1, r: 0}, ArrowLeft: {q: -1, r: 0},
      ArrowDown: {q: 0, r: 1}, ArrowUp: {q: 0, r: -1},
    };
    const direction = directions[event.key];
    if (!direction) return;
    event.preventDefault();
    event.currentTarget.parentElement?.querySelector<HTMLButtonElement>(`[data-hex="${cell.q + direction.q}:${cell.r + direction.r}"]`)?.focus();
  }
  const selectedCell = player.map.cells.find(cell => hexKey(cell) === selectedCellKey);
  const selectedBuilding = selectedCell ? buildingByCell.get(selectedCellKey) : undefined;
  const selectedReward = selectedCell ? rewardByCell.get(selectedCellKey) : undefined;
  return <div className="ark-map-workspace">
    {(buildOptions.length > 0 || animalIds.length > 0) && <div className="ark-map-tools">
      {buildOptions.length > 0 && <section><span>1 · {copy(lang, "建筑与旋转", "Building & rotation")}</span><div>{buildOptions.map(item => <button key={`${item.type}:${item.size}:${item.rotation}`} className={effectiveBuild === `${item.type}:${item.size}:${item.rotation}` ? "selected" : ""} onClick={() => {setSelectedBuild(`${item.type}:${item.size}:${item.rotation}`); setHoveredAction("");}}><b>{BUILDING_META[item.type]?.mark || "B"}</b>{buildingName(item.type, lang)} {item.size} · {item.rotation * 60}°</button>)}</div></section>}
      {animalIds.length > 0 && <section className={effectiveAnimal ? "animal-ready" : "animal-waiting"}><span>2 · {copy(lang, "选择围栏", "Choose enclosure")}</span><div><strong>{effectiveAnimal ? `${copy(lang, "已选择", "Selected")} · ${effectiveAnimal}` : copy(lang, "先在上方手牌或展示区选择动物", "First choose an animal in your hand or the display")}</strong></div></section>}
      <p>{effectiveBuild ? copy(lang, "先选择固定形状的旋转方向，再点击绿色锚点；悬停会预览完整占地。", "Choose a fixed-shape rotation, then click a green anchor; hover previews the full footprint.") : effectiveAnimal ? copy(lang, "现在点击高亮的空围栏放入这只动物。打出后如仍可打第二只，请重新选择下一张动物牌。", "Now click a highlighted empty enclosure. If you may play another animal, choose the next card again.") : copy(lang, "尚未选择动物，地图不会预选第一张牌。", "No animal is selected; the map will not choose one automatically.")}</p>
    </div>}
    <div className="ark-map-scroll"><div className="ark-interactive-map" style={{width, height}} aria-label={`${player.map.name} · ${copy(lang, "六边形地图", "hex map")}`}>
      {player.map.cells.map(cell => {
        const key = hexKey(cell); const building = buildingByCell.get(key); const played = building ? cardByEnclosure.get(building.id) : undefined;
        const legal = legalCells.has(key); const animalLegal = building ? animalEnclosures.has(building.id) && !effectiveBuild : false;
        const position = point(cell); const reward = rewardByCell.get(key); const bonusEffect = cell.placement_bonus || reward?.effect; const bonus = benefitLabel(bonusEffect, lang);
        return <button key={key} data-hex={key} type="button" className={`ark-map-hex terrain-${cell.terrain} ${cell.requires_build_upgrade ? "requires-build-upgrade" : ""} ${building ? `is-built building-${building.type}` : ""} ${legal ? "is-legal" : ""} ${previewCells.has(key) ? "is-preview" : ""} ${animalLegal ? "is-animal-target" : ""} ${selectedCellKey === key ? "is-selected" : ""} ${reward?.status === "claimed" ? "bonus-claimed" : ""}`}
          style={{left: position.x, top: position.y}} onClick={() => clickCell(cell, building)}
          onKeyDown={event => moveFocus(event, cell)}
          onMouseEnter={() => {const action = filteredPlacements.find(item => hexKey(item.action.anchor as {q: number; r: number}) === key); setHoveredAction(action?.id || "");}}
          onMouseLeave={() => setHoveredAction("")} disabled={Boolean(submitting)}
          aria-label={`${cell.q}, ${cell.r} · ${cell.terrain}${cell.requires_build_upgrade ? ` · ${copy(lang, "需要建造 II", "requires Build II")}` : ""}${building ? ` · ${buildingName(building.type, lang)} ${building.size}` : ""}${bonusEffect ? ` · ${bonus}` : ""}${reward?.status === "claimed" ? ` · ${copy(lang, "奖励已领取", "reward claimed")}` : ""}`}>
          <small>{cell.q},{cell.r}</small>{cell.requires_build_upgrade && !building && <u>II</u>}{building && <b>{BUILDING_META[building.type]?.mark || "B"}<i>{building.size}</i></b>}{played && <em>{played.id?.replace("research-animal-", "A")}</em>}{bonusEffect && !building && <strong>{bonus}</strong>}{reward?.status === "claimed" && <span>✓</span>}
        </button>;
      })}
    </div></div>
    <div className="ark-map-legend"><span><i className="terrain-buildable"/>{copy(lang, "土地", "Land")}</span><span><i className="terrain-water"/>{copy(lang, "水源", "Water")}</span><span><i className="terrain-rock"/>{copy(lang, "山脉", "Rock")}</span><span><i className="requires-build-upgrade"/>Build II</span><span><i className="is-built"/>{copy(lang, "建筑", "Building")}</span><span><i className="is-legal"/>{copy(lang, "合法落点", "Legal")}</span></div>
    <section className="ark-cell-inspector" aria-live="polite"><span>{copy(lang, "格子检查器", "Cell inspector")}</span>{selectedCell ? <div><b>q {selectedCell.q} · r {selectedCell.r}</b><i>{selectedCell.terrain === "buildable" ? copy(lang, "可建土地", "Buildable land") : selectedCell.terrain === "water" ? copy(lang, "水源", "Water") : copy(lang, "山脉", "Rock")}</i><strong>{selectedBuilding ? `${buildingName(selectedBuilding.type, lang)} · ${copy(lang, "大小", "size")} ${selectedBuilding.size} · ${selectedBuilding.occupied ? copy(lang, "已入住", "occupied") : copy(lang, "空置", "empty")}` : copy(lang, "无建筑", "No building")}</strong><small>{selectedReward ? `${benefitLabel(selectedReward.effect, lang)} · ${selectedReward.status === "claimed" ? copy(lang, "已领取", "claimed") : copy(lang, "未领取", "available")}` : copy(lang, "无放置奖励", "No placement reward")}</small></div> : <p>{copy(lang, "点击任意六边形查看地形、建筑与奖励。方向键可在相邻格间移动焦点。", "Click any hex for terrain, building, and reward details. Arrow keys move focus between adjacent cells.")}</p>}</section>
  </div>;
}

function PendingMapReward({view, player, lang, legalActions, submitting, onChoose}: {
  view: ArkView; player: ArkPlayerView; lang: ArkLang; legalActions: ArkLegalAction[]; submitting: string;
  onChoose?: (action: ArkLegalAction) => void;
}) {
  const actions = legalActions.filter(item => [
    "choose_conservation_bonus", "upgrade_action_card", "keep_final_card", "take_map_card", "clever_action_card",
  ].includes(String(item.action.type)));
  if (!actions.length || !onChoose) return null;
  const kind = String(actions[0].action.type);
  const title = kind === "choose_conservation_bonus" ? copy(lang, "选择保护轨道奖励", "Choose conservation reward")
    : kind === "upgrade_action_card" ? copy(lang, "升级一张行动牌", "Upgrade an action card")
      : kind === "take_map_card" ? copy(lang, "从牌库或声望范围拿一张牌", "Take a card from the deck or reputation range")
        : kind === "clever_action_card" ? copy(lang, "将一张行动牌移到强度 1", "Move an action card to strength 1")
          : copy(lang, "保留一张终局计分牌", "Keep one final-scoring card");
  return <section className="ark-pending-map-reward" aria-live="polite"><span>{copy(lang, "待处理地图奖励", "PENDING MAP REWARD")}</span><h3>{title}</h3><div>{actions.map(item => {
    const actionKind = String(item.action.type);
    const tile = actionKind === "choose_conservation_bonus" && item.action.tile_id
      ? view.game_board_bonus_tiles.find(value => value.id === item.action.tile_id) : undefined;
    const finalCard = actionKind === "keep_final_card"
      ? player.final_scoring_cards.find(card => !card.hidden && card.id === item.action.card_id) as ArkCard | undefined : undefined;
    const displayCard = actionKind === "take_map_card" && item.action.source === "display"
      ? view.card_display.find(card => card.id === item.action.card_id) : undefined;
    const label = actionKind === "choose_conservation_bonus"
      ? item.action.choice === "money" ? `${copy(lang, "金币", "Money")} +${item.action.amount}` : benefitLabel(tile?.effects?.[0], lang)
      : actionKind === "upgrade_action_card" ? ACTION_LABELS[String(item.action.action_card)]?.[lang] || String(item.action.action_card)
        : actionKind === "take_map_card" ? item.action.source === "deck" ? copy(lang, "牌库顶牌", "Top deck card") : `${copy(lang, "展示区", "Display")} ${item.action.display_slot} · ${displayCard ? cardTypeLabel(displayCard, lang) : item.action.card_id}`
          : actionKind === "clever_action_card" ? ACTION_LABELS[String(item.action.action_card)]?.[lang] || String(item.action.action_card)
            : finalCard?.objective ? `${finalCard.objective.replaceAll("_", " ")} · ${copy(lang, "每", "per")} ${finalCard.per ?? "—"}` : String(item.action.card_id);
    const icon = actionKind === "choose_conservation_bonus" ? item.action.choice === "money" ? "₡" : "◇"
      : actionKind === "upgrade_action_card" ? "II" : actionKind === "take_map_card" ? "C"
        : actionKind === "clever_action_card" ? "1" : "F";
    return <button key={item.id} disabled={Boolean(submitting)} onClick={() => onChoose(item)} className={submitting === item.id ? "submitting" : ""}><b>{icon}</b><span>{label}</span><small>{tile?.id || finalCard?.id || displayCard?.id || String(item.action.action_card || item.action.source || "")}</small></button>;
  })}</div></section>;
}

function SemanticChoiceControls({view, legalActions, submitting, onChoose}: {
  view: ArkView; legalActions: ArkLegalAction[]; submitting: string;
  onChoose?: (action: ArkLegalAction) => void;
}) {
  const actions = legalActions.filter(item => actionType(item) === "resolve_semantic_choice");
  if (!actions.length || !onChoose) return null;
  const labels = new Map((view.pending_choice?.options || []).map(option => [option.id, option.label]));
  return <section className="ark-pending-map-reward" aria-live="polite"><span>RULE CHOICE</span><h3>{view.pending_choice?.prompt || "Choose an effect"}</h3><div>{actions.map(item => {
    const ids = Array.isArray(item.action.option_ids) ? item.action.option_ids.map(String) : [];
    return <button key={item.id} disabled={Boolean(submitting)} onClick={() => onChoose(item)}><b>✓</b><span>{ids.map(id => labels.get(id) || id).join(" + ")}</span></button>;
  })}</div></section>;
}

function ActionCardRack({view, player, lang, legalActions, submitting, onChoose, interactive}: {
  view: ArkView; player: ArkPlayerView; lang: ArkLang; legalActions: ArkLegalAction[]; submitting: string;
  onChoose?: (action: ArkLegalAction) => void; interactive: boolean;
}) {
  const selects = legalActions.filter(item => actionType(item) === "select_action");
  const takes = legalActions.filter(item => actionType(item) === "take_x_token");
  const cancel = legalActions.find(item => actionType(item) === "cancel_action");
  const cards = [...player.action_cards].sort((left, right) => left.strength - right.strength);
  return <section className="ark-action-rack" aria-label={copy(lang, "行动卡牌槽位", "Action card slots")}>
    <header><div><span>ACTION CARDS</span><b>{copy(lang, "行动卡牌顺序与强度", "Action card order & strength")}</b></div><small>{copy(lang, "选择按钮显示消耗 X 后的最终强度", "Buttons show final strength after spending X")}</small></header>
    <div>{cards.map(card => {
      const cardSelects = selects.filter(item => actionCardName(item) === card.action);
      const take = takes.find(item => actionCardName(item) === card.action);
      const current = view.turn.action_card === card.action;
      return <article key={card.action} className={`action-${card.action} action-level-${card.upgraded ? "ii" : "i"} ${current ? "current" : ""} ${cardSelects.length || take ? "is-actionable" : ""}`}>
        <i>{card.strength}</i><div><b>{ACTION_LABELS[card.action]?.[lang] || card.action}</b><small>{card.upgraded ? "II" : "I"}{card.tokens.length ? ` · ${copy(lang, "卡上", "on card")} X${card.tokens.length}` : ""}</small></div>
        {interactive && (cardSelects.length > 0 || take) && <footer>
          {cardSelects.map(item => { const x = Array.isArray(item.action.x_by_execution) ? Number(item.action.x_by_execution[0] || 0) : Number(item.action.x_tokens || 0); return <button key={item.id} disabled={Boolean(submitting)} onClick={() => onChoose?.(item)} title={item.id}><b>{card.strength + x}</b><small>{x ? `−${x} X` : copy(lang, "执行", "Use")}</small></button>;})}
          {take && <button className="take-x" disabled={Boolean(submitting)} onClick={() => onChoose?.(take)} title={take.id}><b>+1 X</b><small>{copy(lang, "跳过行动", "Skip action")}</small></button>}
        </footer>}
      </article>;
    })}</div>
    {interactive && cancel && <footer className="ark-cancel-selected-action"><span>{copy(lang, "尚未执行具体效果，可返回重新选择行动牌。", "No specific effect has resolved yet; you can choose another action card.")}</span><button disabled={Boolean(submitting)} onClick={() => onChoose?.(cancel)}>{copy(lang, "返回并重选行动", "Cancel and reselect")}{submitting === cancel.id ? "…" : ""}</button></footer>}
  </section>;
}

function PlayerActionControls({view, lang, legalActions, submitting, onChoose, interactive}: {
  view: ArkView; lang: ArkLang; legalActions: ArkLegalAction[]; submitting: string;
  onChoose?: (action: ArkLegalAction) => void; interactive: boolean;
}) {
  const draw = legalActions.find(item => actionType(item) === "draw_cards");
  const beginAnimals = legalActions.find(item => actionType(item) === "begin_animals_action");
  const advanceBreak = legalActions.find(item => actionType(item) === "advance_break");
  const finish = view.turn.action_card !== "association" ? legalActions.find(item => actionType(item) === "finish_action") : undefined;
  if (!interactive || (!draw && !beginAnimals && !advanceBreak && !finish)) return null;
  return <section className={`ark-player-action-controls action-${view.turn.action_card || "pending"}`} aria-live="polite">
    <header><div><span>CURRENT ACTION</span><b>{ACTION_LABELS[view.turn.action_card || ""]?.[lang] || view.turn.decision.replaceAll("_", " ")}</b></div><small>{copy(lang, "在玩家版图完成当前行动", "Resolve the current action on the player board")}</small></header>
    <div>
      {draw && <button disabled={Boolean(submitting)} onClick={() => onChoose?.(draw)}><b>{copy(lang, "从牌库抽牌", "Draw from deck")}</b><small>{copy(lang, "抽取", "Draw")} {String(draw.action.draw_count)} · {Number(draw.action.discard_count) ? `${copy(lang, "随后弃", "then discard")} ${String(draw.action.discard_count)}` : copy(lang, "无需立即弃牌", "no immediate discard")}</small></button>}
      {beginAnimals && <button disabled={Boolean(submitting)} onClick={() => onChoose?.(beginAnimals)}><b>{copy(lang, "开始选择动物", "Begin selecting Animals")}</b><small>{copy(lang, "随后从手牌或声望范围逐张选择", "Then choose cards one at a time")}</small></button>}
      {advanceBreak && <button disabled={Boolean(submitting)} onClick={() => onChoose?.(advanceBreak)}><b>{copy(lang, "不打赞助商：推进休息", "Skip sponsor: advance Break")}</b><small>+{String(advanceBreak.action.steps)} {copy(lang, "休息格", "Break")} · +{String(advanceBreak.action.money)} ₡</small></button>}
      {finish && <button className="secondary" disabled={Boolean(submitting)} onClick={() => onChoose?.(finish)}>{copy(lang, "结束当前行动", "Finish current action")}</button>}
    </div>
  </section>;
}

function PlayerCardArea({player, lang, legalActions, submitting, onChoose, interactive, selectedAnimal, onSelectAnimal}: {
  player: ArkPlayerView; lang: ArkLang; legalActions: ArkLegalAction[]; submitting: string;
  onChoose?: (action: ArkLegalAction) => void; interactive: boolean;
  selectedAnimal: string; onSelectAnimal: (cardId: string) => void;
}) {
  const comboActions = legalActions.filter(item => ["choose_initial_hand", "break_discard"].includes(actionType(item)));
  const choosingInitial = comboActions.some(item => actionType(item) === "choose_initial_hand");
  const cards = choosingInitial ? player.initial_draw : player.hand;
  const scope = `${player.seat}:${choosingInitial ? "initial" : "hand"}:${cards.map(card => card.id || "hidden").join("|")}`;
  const [selection, setSelection] = useState<{scope: string; ids: string[]}>({scope: "", ids: []});
  const selected = selection.scope === scope ? selection.ids : [];
  const required = comboActions.length && Array.isArray(comboActions[0].action.card_ids) ? comboActions[0].action.card_ids.length : 0;
  const handLimit = player.public_summary?.resources.hand_limit ?? (player.universities.includes("hand-limit-5") ? 5 : 3);
  const breakDiscard = comboActions.some(item => actionType(item) === "break_discard");
  const comboAction = comboActions.find(item => sameCardIds(item.action.card_ids, selected));
  const toggle = (id: string) => setSelection(current => {
    const ids = current.scope === scope ? current.ids : [];
    return {scope, ids: ids.includes(id) ? ids.filter(value => value !== id) : ids.length < required ? [...ids, id] : ids};
  });
  const actionFor = (card: ArkCard, type: string) => legalActions.find(item => actionType(item) === type && actionCardId(item) === card.id && item.action.source !== "display");
  if (!cards.length && !choosingInitial) return null;
  return <section className={`ark-player-cards ${choosingInitial ? "choosing-initial" : ""}`}>
    <header><div><span>{choosingInitial ? "INITIAL DRAW" : "PRIVATE HAND"}</span><b>{choosingInitial ? copy(lang, "选择起始手牌", "Choose starting hand") : copy(lang, "当前手牌", "Current hand")}</b></div><small>{choosingInitial ? `${copy(lang, "选择", "Choose")} ${required} · ${selected.length}/${required}` : `${cards.length}/${handLimit} ${copy(lang, "张", "cards")}${breakDiscard ? ` · ${copy(lang, "需弃", "discard")} ${required}` : ""}`}</small></header>
    <div>{cards.map((card, index) => {
      const discard = knownCard(card) ? actionFor(card, "discard_card") : undefined;
      const sponsor = knownCard(card) ? actionFor(card, "play_sponsor") : undefined;
      const animalAction = knownCard(card) ? legalActions.find(item => actionType(item) === "play_animal" && actionCardId(item) === card.id && item.action.source !== "display") : undefined;
      const animal = Boolean(animalAction);
      const selectedCard = Boolean(card.id && selected.includes(card.id));
      const animalSelected = Boolean(animal && card.id === selectedAnimal);
      return <article key={card.id || `hidden-${index}`} aria-label={readableCardLabel(card, lang)} className={`ark-readable-card ${card.hidden ? "is-facedown" : `card-${card.card_type}`} ${selectedCard || animalSelected ? "selected" : ""} ${(discard || sponsor || animal) ? "is-actionable" : ""}`}>
        <ReadableCardFace card={card} lang={lang} selectionControl={comboActions.length > 0 && card.id ? <button type="button" aria-label={`${selectedCard ? copy(lang, "取消选择", "Deselect") : copy(lang, "选择", "Select")} ${cardTitle(card, lang)}`} aria-pressed={selectedCard} disabled={!interactive || Boolean(submitting)} onClick={() => toggle(card.id as string)}>{selectedCard ? "✓" : "+"}</button> : undefined}/>
        {interactive && !choosingInitial && (discard || sponsor || animal) && <footer>{discard && <button disabled={Boolean(submitting)} onClick={() => onChoose?.(discard)}>{copy(lang, "弃掉", "Discard")}</button>}{sponsor && <button disabled={Boolean(submitting)} onClick={() => onChoose?.(sponsor)}>{copy(lang, "打出", "Play")}</button>}{animal && card.id && <button aria-pressed={animalSelected} disabled={Boolean(submitting)} onClick={() => {onSelectAnimal(card.id as string); if (animalAction?.action.type === "select_animal_card") onChoose?.(animalAction);}}>{animalSelected ? copy(lang, "已选：去地图选围栏", "Selected: choose enclosure") : copy(lang, "选择这只动物", "Choose this animal")}</button>}</footer>}
      </article>;
    })}</div>
    {interactive && comboActions.length > 0 && <footer className="ark-card-selection-footer"><span>{choosingInitial ? copy(lang, "所选牌将成为起始手牌，其余进入弃牌堆。", "Selected cards become your starting hand; the rest are discarded.") : `${copy(lang, "休息阶段需弃掉", "During the Break, discard")} ${required} ${copy(lang, "张，使手牌降至上限", "cards to reach your hand limit of")} ${handLimit}。`}</span><button disabled={!comboAction || Boolean(submitting)} onClick={() => comboAction && onChoose?.(comboAction)}>{choosingInitial ? copy(lang, "确认起始手牌", "Confirm starting hand") : `${copy(lang, "确认弃牌", "Confirm discard")} ${selected.length}/${required}`}{submitting === comboAction?.id ? "…" : ""}</button></footer>}
  </section>;
}

function FinalScoringCardArea({player, lang, legalActions, submitting, onChoose, interactive}: {
  player: ArkPlayerView; lang: ArkLang; legalActions: ArkLegalAction[]; submitting: string;
  onChoose?: (action: ArkLegalAction) => void; interactive: boolean;
}) {
  const cards = player.final_scoring_cards;
  if (!cards.length) return null;
  return <section className="ark-player-cards ark-final-scoring-cards">
    <header><div><span>FINAL SCORING</span><b>{copy(lang, "终局计分牌", "Final-scoring cards")}</b></div><small>{copy(lang, "任意玩家到达 10 保护点时，每位玩家保留 1 张", "When any player reaches 10 conservation, each player keeps 1")}</small></header>
    <div>{cards.map((card, index) => {
      const keep = !card.hidden ? legalActions.find(item => actionType(item) === "keep_final_card" && item.action.card_id === card.id) : undefined;
      return <article key={!card.hidden && card.id ? card.id : `hidden-final-${index}`} aria-label={readableCardLabel(card, lang)} className={`ark-readable-card ${card.hidden ? "is-facedown" : "card-final card-final_scoring"} ${keep ? "is-actionable" : ""}`}>
        <ReadableCardFace card={card} lang={lang}/>
        {interactive && keep && <footer><button disabled={Boolean(submitting)} onClick={() => onChoose?.(keep)}>{copy(lang, "保留此牌", "Keep this card")}</button></footer>}
      </article>;
    })}</div>
  </section>;
}

function PlayedCardArea({player, lang}: {player: ArkPlayerView; lang: ArkLang}) {
  const groups = [
    {type: "animal", title: copy(lang, "已打出的动物卡牌", "Played animal cards"), mark: "A"},
    {type: "sponsor", title: copy(lang, "已打出的赞助商卡牌", "Played sponsor cards"), mark: "S"},
  ];
  return <section className="ark-played-card-area"><header><span>PLAYED CARDS</span><b>{copy(lang, "玩家已打出的卡牌", "Player's played cards")}</b></header><div>{groups.map(group => {
    const cards = player.played_cards.filter(knownCard).filter(card => card.card_type === group.type);
    return <section key={group.type}><header><b>{group.title}</b><small>{cards.length} {copy(lang, "张", "cards")}</small></header><div>{cards.length ? cards.map(card => <article key={card.id} aria-label={readableCardLabel(card, lang)} className={`ark-readable-card card-${group.type}`}><ReadableCardFace card={card} lang={lang}/>{card.enclosure_id && <footer><span>{copy(lang, "围栏", "Enclosure")} {card.enclosure_id}</span></footer>}</article>) : <em>{copy(lang, "尚无卡牌", "No cards yet")}</em>}</div></section>;
  })}</div></section>;
}

function rewardLabel(effect: ArkEffect | null | undefined, lang: ArkLang) {
  if (!effect) return copy(lang, "无额外奖励", "No extra reward");
  if (effect.type === "action_upgrade") return copy(lang, "行动牌升级", "Action-card upgrade");
  if (effect.type === "gain_worker") return copy(lang, "事务员 +1", "Worker +1");
  if (effect.type === "gain_enclosure") return `${copy(lang, "围栏", "Enclosure")} ${effect.amount}`;
  if (effect.type === "gain_determination") return copy(lang, "精选", "Determination");
  return benefitLabel(effect, lang);
}

function PlayerBoardLists({player, lang}: {player: ArkPlayerView; lang: ArkLang}) {
  const board = player.map_display?.player_board;
  if (!board) return null;
  const associationUpgraded = player.action_cards.find(card => card.action === "association")?.upgraded;
  const assetName = (asset: string | null | undefined) => asset
    ? CONTINENT_META[asset]?.[lang] || asset.replaceAll("-", " ") : copy(lang, "空", "Empty");
  return <>
    <section className="ark-worker-board"><span>{copy(lang, "事务员", "Association workers")}</span>
      <p><b>{copy(lang, "可用事务员", "Available workers")} ×{board.workers.available}</b><small>{copy(lang, "已派出", "Committed")} ×{board.workers.committed}</small></p>
      <ul>{board.workers.locked.map(worker => <li key={worker.slot}><b>{copy(lang, "未解锁", "Locked")}</b><small>{worker.unlock_reward ? rewardLabel(worker.unlock_reward, lang) : "—"}</small></li>)}</ul>
    </section>
    <section className="ark-asset-ladders"><span>{copy(lang, "合作动物园", "Partner zoos")}</span>
      <ol>{board.partner_zoo_ladder.map(slot => <li key={slot.level} className={`${slot.status} ${slot.level >= 3 ? "requires-association-ii" : ""}`}><b>{slot.level}</b><strong>{assetName(slot.asset)}</strong><small>{slot.level >= 3 ? `${copy(lang, "协会 II", "Association II")} · ` : ""}{rewardLabel(slot.reward, lang)}{slot.level >= 3 && !associationUpgraded ? ` · ${copy(lang, "未满足", "required")}` : ""}</small></li>)}</ol>
      <span>{copy(lang, "大学", "Universities")}</span>
      <ol>{board.university_ladder.map(slot => <li key={slot.level} className={slot.status}><b>{slot.level}</b><strong>{assetName(slot.asset)}</strong><small>{rewardLabel(slot.reward, lang)}</small></li>)}</ol>
    </section>
    {board.conservation_programs.map(program => <section key={program.kind} className="ark-program-rewards"><span>{program.kind === "immediate_and_income" ? copy(lang, "保护项目：立即 + 休息收入", "Conservation: immediate + income") : copy(lang, "保护项目：立即奖励", "Conservation: immediate reward")}</span>
      <ul>{program.slots.map(slot => <li key={slot.id} className={slot.status}><b>{slot.status === "claimed" ? "✓" : "○"}</b><strong>{rewardLabel(slot.reward, lang)}</strong><small>{slot.status === "claimed" ? copy(lang, "已开放", "Unlocked") : copy(lang, "未解锁", "Locked")}</small></li>)}</ul>
    </section>)}
  </>;
}

function ZooWorkspace({view, identities, lang, legalActions, submitting, onChoose, selectedAnimal, onSelectAnimal}: {
  view: ArkView; identities: ArkIdentity[]; lang: ArkLang; legalActions: ArkLegalAction[]; submitting: string;
  onChoose?: (action: ArkLegalAction) => void; selectedAnimal: string; onSelectAnimal: (cardId: string) => void;
}) {
  const decisionSeat = legalActions.length > 0 ? (view.viewer_seat ?? view.active_seat) : view.active_seat;
  const [selection, setSelection] = useState({seat: decisionSeat, decision: view.decision_count});
  const selectedSeat = legalActions.length > 0 && selection.decision !== view.decision_count
    ? decisionSeat : selection.seat;
  const seat = view.players.some(player => player.seat === selectedSeat)
    ? selectedSeat : view.active_seat;
  const player = view.players.find(item => item.seat === seat) || view.players[0];
  const interactive = legalActions.length > 0 && seat === decisionSeat;
  return <section className="ark-surface ark-zoo-workspace">
    <header className="ark-surface-header"><div><span>MAP 0 · FLAT-TOP AXIAL</span><h2>{copy(lang, "玩家动物园地图", "Player zoo map")}</h2></div><div className="ark-map-status"><b>{player.map.geometry_status.includes("reference_transcribed") ? copy(lang, "参考图转录几何", "Reference-transcribed geometry") : copy(lang, "受控地图几何", "Controlled map geometry")}</b><span>{player.map.buildings.length} {copy(lang, "座建筑", "buildings")}</span></div></header>
    <nav className="ark-player-tabs" aria-label={copy(lang, "选择玩家地图", "Choose player map")}>{view.players.map(item => <button key={item.seat} className={`${item.seat === seat ? "selected" : ""} ${item.seat === view.active_seat ? "active" : ""}`} onClick={() => setSelection({seat: item.seat, decision: view.decision_count})} style={{"--player-color": PLAYER_COLORS[item.seat]} as React.CSSProperties}><i>{item.seat + 1}</i><span>{playerName(identities, item.seat, lang)}</span><small>{item.seat === view.active_seat ? copy(lang, "行动中", "ACTIVE") : copy(lang, "公开地图", "PUBLIC")}</small></button>)}</nav>
    <ActionCardRack view={view} player={player} lang={lang} legalActions={interactive ? legalActions : []} submitting={submitting} onChoose={interactive ? onChoose : undefined} interactive={interactive}/>
    <PlayerActionControls view={view} lang={lang} legalActions={interactive ? legalActions : []} submitting={submitting} onChoose={interactive ? onChoose : undefined} interactive={interactive}/>
    <PlayerCardArea player={player} lang={lang} legalActions={interactive ? legalActions : []} submitting={submitting} onChoose={interactive ? onChoose : undefined} interactive={interactive} selectedAnimal={selectedAnimal} onSelectAnimal={onSelectAnimal}/>
    <FinalScoringCardArea player={player} lang={lang} legalActions={interactive ? legalActions : []} submitting={submitting} onChoose={interactive ? onChoose : undefined} interactive={interactive}/>
    <div className="ark-zoo-layout">
      <ZooMap player={player} lang={lang} legalActions={interactive ? legalActions : []} submitting={submitting} onChoose={interactive ? onChoose : undefined} selectedAnimal={selectedAnimal}/>
      <aside className="ark-zoo-inspector">
        {interactive && <PendingMapReward
          view={view} player={player} lang={lang} legalActions={legalActions}
          submitting={submitting} onChoose={onChoose}
        />}
        {interactive && <SemanticChoiceControls view={view} legalActions={legalActions} submitting={submitting} onChoose={onChoose}/>} 
        <PlayerBoardLists player={player} lang={lang}/>
        <section className="ark-map-coverage"><span>{copy(lang, "地图覆盖奖励", "Map coverage reward")}</span><p><b>{player.map_display?.coverage ? `${player.map_display.coverage.covered}/${player.map_display.coverage.total}` : "—"}</b><small>{player.map_display?.coverage?.complete ? copy(lang, "地图已完全覆盖", "Map complete") : copy(lang, "覆盖所有可建土地", "Cover all buildable land")}</small></p><p><b>{benefitLabel(player.map_display?.coverage?.reward, lang)}</b><small>{player.map_display?.coverage?.status === "claimed" ? copy(lang, "已领取", "claimed") : copy(lang, "待完成", "pending")}</small></p></section>
      </aside>
    </div>
    <PlayedCardArea player={player} lang={lang}/>
  </section>;
}

export function ArkNovaTable({view, identities, lang, legalActions = [], submitting = "", onChoose}: {
  view?: ArkView; identities: ArkIdentity[]; lang: ArkLang; legalActions?: ArkLegalAction[];
  submitting?: string; onChoose?: (action: ArkLegalAction) => void;
}) {
  const [selectedAnimal, setSelectedAnimal] = useState("");
  if (!view) return <div className="empty-board">Ark Nova</div>;
  return <div className="ark-table-v2">
    <section className="ark-match-banner"><div><span>ARK NOVA · OFFICIAL BASE</span><h1>{view.phase === "initial_hand_selection" ? copy(lang, "正在选择起始手牌", "Selecting starting hand") : view.phase === "initial_map_setup" ? copy(lang, "放置开局围栏与商亭", "Place starter enclosure and kiosk") : copy(lang, "动物园规划桌", "Zoo planning table")}</h1></div><p>{copy(lang, "视觉组件使用结构化状态和原创 CSS 表达，不包含出版商卡图或逐字牌文。", "Components use structured state and original CSS; no publisher card art or verbatim card text.")}</p><code>{view.rules_version}</code></section>
    <GameBoard view={view} identities={identities} lang={lang} legalActions={legalActions} submitting={submitting} onChoose={onChoose} selectedAnimal={selectedAnimal} onSelectAnimal={setSelectedAnimal}/>
    <AssociationBoard view={view} identities={identities} lang={lang} legalActions={legalActions} submitting={submitting} onChoose={onChoose}/>
    <ZooWorkspace view={view} identities={identities} lang={lang} legalActions={legalActions} submitting={submitting} onChoose={onChoose} selectedAnimal={selectedAnimal} onSelectAnimal={setSelectedAnimal}/>
    <details className="ark-content-status"><summary>{copy(lang, "规则版本与内容包状态", "Rules version & content status")}</summary><p>{copy(lang, "当前对局使用基础版程式化卡牌与语义引擎；界面只展示原创的规则摘要。", "This match uses the programmed base-card pack and semantic engine; the UI shows original rules summaries only.")}</p><code>{view.implementation_status}</code></details>
  </div>;
}
