"use client";

import { useEffect, useMemo, useState } from "react";

type Lang = "zh" | "en";
type Collection =
  | "animals"
  | "sponsors"
  | "zoo_conservation_projects"
  | "base_conservation_projects"
  | "final_scoring"
  | "bonus_tiles"
  | "maps";
type CatalogEntry = {
  id: string;
  collection: Collection;
  kind: string;
  official_component_id: string | null;
  title: string;
  summary: string;
  facts: {catalog_status?: string; catalog_traits?: string[]; [key: string]: unknown};
  requirements: string[];
  effects: {timing: string; description: string}[];
  review_status: string;
  scenario_tests: string[];
};
type Catalog = {
  schema_version: string;
  pack: {
    id: string;
    rules_version: string;
    content_version: string;
    status: string;
    content_sha256: string;
  };
  coverage: {
    total: number;
    collections: Record<Collection, number>;
    review: Record<string, number>;
    roster_indexed: number;
    semantic_entries: number;
    scenario_covered_entries: number;
    unentered: number;
  };
  entries: CatalogEntry[];
};

const COLLECTIONS: Collection[] = [
  "animals", "sponsors", "zoo_conservation_projects", "base_conservation_projects",
  "final_scoring", "bonus_tiles", "maps",
];
const COLLECTION_COPY: Record<Collection, {zh: string; en: string; short: string}> = {
  animals: {zh: "动物牌", en: "Animals", short: "ANM"},
  sponsors: {zh: "赞助商", en: "Sponsors", short: "SPN"},
  zoo_conservation_projects: {zh: "动物园保育项目", en: "Zoo projects", short: "ZCP"},
  base_conservation_projects: {zh: "基础保育项目", en: "Base projects", short: "BCP"},
  final_scoring: {zh: "终局计分", en: "Final scoring", short: "FIN"},
  bonus_tiles: {zh: "奖励板块", en: "Bonus tiles", short: "BON"},
  maps: {zh: "动物园地图", en: "Zoo maps", short: "MAP"},
};
const ACTIONS = ["CARDS", "BUILD", "ANIMALS", "ASSOCIATION", "SPONSORS"];

function stageEntries(entry: CatalogEntry, timings: string[]) {
  return entry.effects.filter(effect => timings.includes(effect.timing));
}

function RulesInspector({entry, lang}: {entry: CatalogEntry; lang: Lang}) {
  const zh = lang === "zh";
  const isExecutableCard = entry.review_status !== "unentered"
    && !["bonus_tiles", "maps"].includes(entry.collection);
  const stages = [
    {id: "requirements", title: zh ? "条件" : "Requirements", values: entry.requirements},
    {id: "immediate", title: zh ? "即时效果" : "Immediate", values: stageEntries(entry, ["on_play", "immediate", "on_support", "on_release"]).map(value => value.description)},
    {id: "ongoing", title: zh ? "持续效果" : "Ongoing", values: stageEntries(entry, ["ongoing", "income", "on_trigger"]).map(value => value.description)},
    {id: "interaction", title: zh ? "互动效果" : "Interaction", values: stageEntries(entry, ["interaction"]).map(value => value.description)},
    {id: "endgame", title: zh ? "终局计分" : "Endgame", values: stageEntries(entry, ["end_of_game"]).map(value => value.description)},
  ];
  const traits = Array.isArray(entry.facts.catalog_traits) ? entry.facts.catalog_traits : [];
  return <article className="ark-rule-inspector">
    <header>
      <div><span>{entry.official_component_id ? `#${entry.official_component_id}` : "ID —"}</span><small>{COLLECTION_COPY[entry.collection].short}</small></div>
      <h3>{entry.title}</h3>
      <b className={`ark-review review-${entry.review_status}`}>{entry.review_status.replaceAll("_", " ")}</b>
    </header>
    <p>{isExecutableCard
      ? (zh ? "结构化事实与效果已接入基础版 Map 0 发布引擎；下方按执行阶段展示人类可读摘要。" : "Structured facts and effects are wired into the released base-game Map 0 engine; the stages below are human-readable execution summaries.")
      : (zh ? "这是一条非卡牌组件目录记录，保留为后续地图或奖励板块扩展范围。" : "This non-card component remains a roster record for later map or bonus-tile expansion.")}</p>
    {traits.length > 0 && <div className="ark-traits">{traits.map(trait => <span key={trait}>{trait}</span>)}</div>}
    <div className="ark-rule-stages">{stages.map((stage, index) => <section key={stage.id}>
      <i>{index + 1}</i><div><b>{stage.title}</b>{stage.values.length > 0 ? stage.values.map((value, item) => <span key={item}>{value}</span>) : <small>{isExecutableCard ? (stage.id === "requirements" ? (zh ? "无额外条件" : "No extra requirement") : (zh ? "无此阶段效果" : "No effect at this stage")) : (zh ? "待规则复核" : "Pending rules review")}</small>}</div>
    </section>)}</div>
  </article>;
}

export function ArkNovaWorkbench({lang, compact = false}: {lang: Lang; compact?: boolean}) {
  const zh = lang === "zh";
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [failure, setFailure] = useState("");
  const [collection, setCollection] = useState<Collection | "all">("animals");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/ark-nova-content.json")
      .then(response => {
        if (!response.ok) throw new Error(`catalog ${response.status}`);
        return response.json() as Promise<Catalog>;
      })
      .then(value => { if (active) setCatalog(value); })
      .catch(error => { if (active) setFailure(error instanceof Error ? error.message : String(error)); });
    return () => { active = false; };
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return (catalog?.entries || []).filter(entry => {
      if (collection !== "all" && entry.collection !== collection) return false;
      if (!needle) return true;
      return `${entry.title} ${entry.official_component_id || ""} ${(entry.facts.catalog_traits || []).join(" ")}`.toLocaleLowerCase().includes(needle);
    });
  }, [catalog, collection, query]);
  const selected = catalog?.entries.find(entry => entry.id === selectedId)
    || filtered[0]
    || catalog?.entries[0];

  if (compact) return <section className="ark-workbench ark-workbench-compact">
      <div><span>P8 OFFICIAL BASE</span><h3>{zh ? "基础版卡牌与语义审计" : "Base-card roster & semantic audit"}</h3></div>
    <div className="ark-compact-metrics">
      <span><b>255</b>{zh ? "实体卡" : "physical cards"}</span>
      <span><b>235</b>{zh ? "可执行卡面" : "executable faces"}</span>
      <span><b>5</b>{zh ? "行动牌" : "Action cards"}</span>
    </div>
    <code>{catalog?.pack.content_version || (failure ? "CATALOG ERROR" : "LOADING")}</code>
  </section>;

  return <section className="ark-workbench">
    <header className="ark-workbench-header">
      <div><span>P8 OFFICIAL BASE CANDIDATE</span><h2>{zh ? "规则内容工作台" : "Rules content workbench"}</h2></div>
      <p>{zh ? "255 张实体卡清单负责重复牌与牌库守恒；235 种动物、赞助商、项目和终局卡面，以及 5 种行动牌由封闭语义引擎执行。" : "The 255-card physical roster validates duplicates and deck conservation; 235 Animal, Sponsor, Project, and Final Scoring faces plus five Action cards execute in the closed semantic engine."}</p>
      <code>{catalog?.pack.content_version || (failure ? "CATALOG ERROR" : "LOADING CATALOG")}</code>
    </header>
    <div className="ark-content-metrics">
      <span><small>{zh ? "实体基础卡" : "PHYSICAL BASE CARDS"}</small><b>255</b><i>100%</i></span>
      <span><small>{zh ? "可执行卡面" : "EXECUTABLE FACES"}</small><b>235</b><i>100%</i></span>
      <span><small>{zh ? "行动牌" : "ACTION CARDS"}</small><b>5</b><i>{zh ? "I / II 级" : "LEVEL I / II"}</i></span>
      <span><small>{zh ? "规则门禁" : "RULES GATE"}</small><b>P8</b><i>{zh ? "全量测试" : "full-suite"}</i></span>
    </div>
    <div className="ark-action-grammar">
      <div><span>{zh ? "行动会话语法" : "ACTION SESSION GRAMMAR"}</span><small>{zh ? "选择 → 标记 → 执行 → 结算 → 移位" : "select → token → execute → resolve → shift"}</small></div>
      <div>{ACTIONS.map((action, index) => <i key={action}><b>{index + 1}</b><span>{action}</span>{index === 2 && <em>X</em>}</i>)}</div>
    </div>
    <nav className="ark-catalog-tabs" aria-label={zh ? "内容分类" : "Content collections"}>
      <button className={collection === "all" ? "selected" : ""} onClick={() => setCollection("all")}>{zh ? "全部" : "All"}<b>{catalog?.coverage.total || 0}</b></button>
      {COLLECTIONS.map(value => <button key={value} className={collection === value ? "selected" : ""} onClick={() => setCollection(value)}>{COLLECTION_COPY[value][lang]}<b>{catalog?.coverage.collections[value] || 0}</b></button>)}
    </nav>
    <div className="ark-catalog-toolbar">
      <label><span>{zh ? "检索目录" : "SEARCH ROSTER"}</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder={zh ? "名称、编号或结构标签" : "name, number, or structured trait"}/></label>
      <b>{filtered.length} {zh ? "条记录" : "records"}</b>
    </div>
    {failure ? <div className="ark-catalog-error">{zh ? "内容包加载失败：" : "Catalog failed to load: "}{failure}</div> : <div className="ark-catalog-layout">
      <div className="ark-card-index">{filtered.slice(0, 12).map(entry => <button key={entry.id} className={`${selected?.id === entry.id ? "selected" : ""} card-${entry.collection}`} onClick={() => setSelectedId(entry.id)}>
        <span>{COLLECTION_COPY[entry.collection].short}</span><b>{entry.official_component_id ? `#${entry.official_component_id}` : "SLOT"}</b><strong>{entry.title}</strong><small>{entry.review_status === "unentered" ? (zh ? "扩展目录" : "extension roster") : (zh ? "已接入引擎" : "engine ready")}</small>
      </button>)}</div>
      {selected && <RulesInspector entry={selected} lang={lang}/>} 
    </div>}
    <footer><span>{zh ? "不含出版商美术与逐字牌文" : "No publisher art or verbatim card prose"}</span><code>{catalog?.pack.content_sha256.slice(0, 12) || "sha pending"}</code></footer>
  </section>;
}
