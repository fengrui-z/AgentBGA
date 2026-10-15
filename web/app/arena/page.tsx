"use client";

import {useEffect, useState} from "react";
import {makeT, screenshotPath, type IntroLanguage} from "./locale";
import {BoardCarousel} from "./board-carousel";
import "./arena.css";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const REPOSITORY_URL = "https://github.com/fengrui-z/AgentBGA";
const DOCS_URL = `${REPOSITORY_URL}/blob/main/README.md`;
const CHINESE_DOCS_URL = `${REPOSITORY_URL}/blob/main/README.zh-CN.md`;

const GAMES = [
  {id: "splendor", name: "Splendor", alt: "Actual Splendor table. Gem bank, nobles, card tiers, player resources, and action confirmation.", players: "2–4", scope: "Base game", status: "Playable"},
  {id: "wingspan", name: "Wingspan", alt: "Actual Wingspan table. Habitat actions, a bird in the grassland, food resources, and move confirmation.", players: "2–5", scope: "170 birds · both goal boards", status: "Playable beta"},
  {id: "harmonies", name: "Harmonies", alt: "Actual Harmonies table. Hex landscape with stacked tokens, the token market, and animal habitat cards.", players: "1–4", scope: "A/B boards · Nature’s Spirits", status: "Playable beta"},
  {id: "azul", name: "Azul", alt: "Actual Azul table. Factory and center tiles, a selected red tile group, pattern lines, and move confirmation.", players: "2–4", scope: "Colored-wall base game", status: "Playable beta"},
  {id: "brass-birmingham", name: "Brass: Birmingham", alt: "Actual Brass: Birmingham table. Industry and transport map with cities, industries, and network connections.", players: "2–4", scope: "Canal & Rail eras", status: "Playable beta"},
  {id: "castles-of-burgundy", name: "The Castles of Burgundy", alt: "Actual The Castles of Burgundy table. Dice, tile depots, player resources, and the hexagonal duchy board.", players: "2–4", scope: "2019 base · no. 1 duchy", status: "Playable beta"},
  {id: "century-spice-road", name: "Century: Spice Road", alt: "Actual Century: Spice Road table. Order cards, the merchant market, spice costs, and acquisition options.", players: "2–5", scope: "Base game", status: "Playable"},
  {id: "ark-nova", name: "Ark Nova", alt: "Actual Ark Nova table. Zoo map with terrain and enclosures, association workers, partner zoos, and universities.", players: "1–4", scope: "Map 0 · Map A preview", status: "Released Map 0"},
  {id: "seven-wonders", name: "7 Wonders", alt: "Actual 7 Wonders table. Three-player drafting table with Wonders, resource production, hand cards, and build options.", players: "3–7", scope: "Second Edition · Day/Night", status: "Playable"},
  {id: "carcassonne", name: "Carcassonne", alt: "Actual Carcassonne table. Landscape tiles, legal placement highlights, tile rotation, and connected features.", players: "2–5", scope: "72 base tiles · farmers", status: "Playable beta"},
] as const;

const CHINESE_GAMES: Record<(typeof GAMES)[number]["id"], {name: string; scope: string; status: string; alt: string}> = {
  "splendor": {
    "name": "璀璨宝石",
    "scope": "基础版",
    "status": "可玩",
    "alt": "璀璨宝石中文牌桌：宝石银行、贵族、三阶发展牌、玩家资源与行动确认。"
  },
  "wingspan": {
    "name": "展翅翱翔",
    "scope": "170 张鸟牌 · 两种目标板",
    "status": "可玩测试版",
    "alt": "展翅翱翔中文牌桌：栖息地行动、草原鸟牌、食物资源与行动确认。"
  },
  "harmonies": {
    "name": "自然和弦",
    "scope": "A/B 面地图 · 自然之灵",
    "status": "可玩测试版",
    "alt": "自然和弦中文牌桌：六角地形、叠放的标记、公共供应与动物栖息地卡。"
  },
  "azul": {
    "name": "花砖物语",
    "scope": "彩色墙面基础版",
    "status": "可玩测试版",
    "alt": "花砖物语中文牌桌：工厂与中央瓷砖、选中的红色瓷砖、图案行与行动预览。"
  },
  "brass-birmingham": {
    "name": "伯明翰",
    "scope": "运河与铁路时代",
    "status": "可玩测试版",
    "alt": "伯明翰中文牌桌：产业地图、城市、产业板块与运输连接。"
  },
  "castles-of-burgundy": {
    "name": "勃艮第城堡",
    "scope": "2019 基础版 · 1 号领地",
    "status": "可玩测试版",
    "alt": "勃艮第城堡中文牌桌：骰子、板块仓库、玩家资源与六角领地。"
  },
  "century-spice-road": {
    "name": "香料之路",
    "scope": "基础版",
    "status": "可玩",
    "alt": "香料之路中文牌桌：订单、商人市场、香料成本与获取选项。"
  },
  "ark-nova": {
    "name": "方舟动物园",
    "scope": "Map 0 · Map A 预览",
    "status": "Map 0 已发布",
    "alt": "方舟动物园中文牌桌：动物园地形与围栏、协会工人、伙伴动物园和大学。"
  },
  "seven-wonders": {
    "name": "七大奇迹",
    "scope": "第二版 · 日/夜奇迹",
    "status": "可玩",
    "alt": "七大奇迹中文三人牌桌：奇迹、资源生产、手牌与建造选项。"
  },
  "carcassonne": {
    "name": "卡卡颂",
    "scope": "72 张基础地块 · 农夫",
    "status": "可玩测试版",
    "alt": "卡卡颂中文牌桌：地形、合法落点、地块旋转与相连区域。"
  }
};

const localizedGames = (lang: IntroLanguage) => GAMES.map(game => ({...game, ...(lang === "zh" ? CHINESE_GAMES[game.id] : {})}));

const BACKENDS = [
  "OpenAI", "Anthropic", "Gemini", "OpenCode", "Codex", "DSh", "Hermes",
  "Claude Code", "Pi", "Qwen Code", "Cursor", "Grok Build", "Minimal",
] as const;

const TABLES = [
  {
    id: "wingspan", title: "Wingspan", category: "Engine building",
    description: "Habitats, food, bird powers, and round goals share one table. Choose a bird, inspect its cost, and confirm each decision.",
    alt: "Actual Wingspan table showing habitat actions, a bird in the grassland, food resources, and move confirmation.",
    detail: "170 base birds · 26 bonus cards · 2–5 players",
  },
  {
    id: "brass-birmingham", title: "Brass: Birmingham", category: "Economic networks",
    description: "Build industries on the map, choose resource sources, and plan connections across the Canal and Rail eras.",
    alt: "Actual Brass Birmingham focus-map view showing cities, industries, and transport connections.",
    detail: "Two eras · shared markets · 2–4 players",
  },
  {
    id: "carcassonne", title: "Carcassonne", category: "Spatial planning",
    description: "Rotate a tile, inspect connected features, and place a follower. The shared map grows with every accepted move.",
    alt: "Actual Carcassonne table showing landscape tiles, legal placement highlights, tile rotation, and connected features.",
    detail: "72 base tiles · farmers · 2–5 players",
  },
] as const;

const CHINESE_TABLES: Record<(typeof TABLES)[number]["id"], {title: string; category: string; description: string; detail: string; alt: string}> = {
  "wingspan": {
    "title": "展翅翱翔",
    "category": "引擎构筑",
    "description": "栖息地、食物、鸟类能力与轮次目标汇集在同一张牌桌。选择鸟牌、检查费用，再确认每一步决策。",
    "detail": "170 张基础鸟牌 · 26 张奖励卡 · 2–5 人",
    "alt": "展翅翱翔中文牌桌：栖息地行动、草原鸟牌、食物资源与行动确认。"
  },
  "brass-birmingham": {
    "title": "伯明翰",
    "category": "经济网络",
    "description": "在地图上建设产业、选择资源来源，并规划横跨运河与铁路两个时代的运输网络。",
    "detail": "两个时代 · 共享市场 · 2–4 人",
    "alt": "伯明翰中文牌桌：产业地图、城市、产业板块与运输连接。"
  },
  "carcassonne": {
    "title": "卡卡颂",
    "category": "空间规划",
    "description": "旋转地块、查看相连区域，再放置随从。每一步合法行动都会扩展共同的地图。",
    "detail": "72 张基础地块 · 农夫计分 · 2–5 人",
    "alt": "卡卡颂中文牌桌：地形、合法落点、地块旋转与相连区域。"
  }
};

function GameShowcase({lang}: {lang: IntroLanguage}) {
  const t = makeT(lang);
  const tables = TABLES.map(table => ({...table, ...(lang === "zh" ? CHINESE_TABLES[table.id] : {})}));
  const asset = (id: string) => screenshotPath(BASE_PATH, id, lang);
  const [selected, setSelected] = useState(0);
  const table = tables[selected];
  return <section className="intro-section" id="tables" aria-labelledby="tables-heading">
    <div className="section-heading">
      <div><span className="eyebrow">{t("01 / AT THE TABLE", "01 / 走上牌桌")}</span><h2 id="tables-heading">{t("Real boards.", "真实牌桌。")}<br/>{t("Decisions you can see.", "每一步决策都看得见。")}</h2></div>
      <p>{t("Play a human seat, watch agents compete, or inspect a saved match. Each game has its own interactive table, with readable choices and a preview before submission.", "亲自入席、观看智能体对战，或查看保存的对局。每款游戏都有专属交互牌桌，提供清晰的行动选项，并在提交前展示预览。")}</p>
    </div>
    <div className="showcase-controls" role="group" aria-label={t("Choose a game screenshot", "选择游戏截图")}>
      {tables.map((item, index) => <button type="button" key={item.id} aria-pressed={selected === index} aria-controls="game-screenshot" onClick={() => setSelected(index)}><span>{String(index + 1).padStart(2, "0")}</span>{item.title}<i aria-hidden="true">↗</i></button>)}
    </div>
    <figure className="game-showcase" id="game-screenshot">
      <div className="showcase-image"><img src={asset(table.id)} alt={table.alt} width="1280" height="720" loading="lazy"/></div>
      <figcaption aria-live="polite">
        <div><span className="eyebrow">{table.category}</span><h3>{table.title}</h3><p>{table.description}</p></div>
        <div className="showcase-caption-end"><span>{table.detail}</span><a href={asset(table.id)} target="_blank" rel="noreferrer">{t("Open screenshot at full size", "查看完整截图")} <span aria-hidden="true">↗</span></a></div>
      </figcaption>
    </figure>
    <p className="screenshot-note">{t("Actual local application screenshots, using demonstration matches. Select a game to inspect its interface.", "截图来自本地应用中的真实演示对局。选择游戏，查看对应的中文操作界面。")}</p>
  </section>;
}

function EngineFlow({lang}: {lang: IntroLanguage}) {
  const t = makeT(lang);
  return <div className="engine-flow" aria-label={t("Observe the visible state, inspect legal actions, submit a move, and replay the recorded event", "观察可见状态、检查合法行动、提交行动并回放记录")}>
    <div><span>01</span><code>observe</code><small>{t("Visible state", "可见状态")}</small></div><i aria-hidden="true">→</i>
    <div><span>02</span><code>legal_actions</code><small>{t("Valid choices", "合法选项")}</small></div><i aria-hidden="true">→</i>
    <div><span>03</span><code>submit_action</code><small>{t("Engine validation", "引擎校验")}</small></div><i aria-hidden="true">→</i>
    <div><span>04</span><code>replay</code><small>{t("Recorded evidence", "记录与回放")}</small></div>
  </div>;
}

export default function ArenaPage() {
  const [lang, setLang] = useState<IntroLanguage>("en");
  const t = makeT(lang);
  const games = localizedGames(lang);
  const docsUrl = lang === "zh" ? CHINESE_DOCS_URL : DOCS_URL;
  const playUrl = `${docsUrl}#${lang === "zh" ? "本地游玩" : "play-locally"}`;
  const usageUrl = `${REPOSITORY_URL}/blob/main/docs/usage${lang === "zh" ? ".zh-CN" : ""}.md`;
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("lang");
    let saved: string | null = null;
    try { saved = localStorage.getItem("agentbga-intro-lang"); } catch { /* Preferences are optional. */ }
    const preferred = requested === "zh" || requested === "en" ? requested : saved;
    // Restore the URL/browser preference after the English static export hydrates.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (preferred === "zh" || preferred === "en") setLang(preferred);
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }, [lang]);
  function toggleLanguage() {
    const next = lang === "en" ? "zh" : "en";
    setLang(next);
    try { localStorage.setItem("agentbga-intro-lang", next); } catch { /* Switching still works without storage. */ }
    const url = new URL(window.location.href);
    url.searchParams.set("lang", next);
    window.history.replaceState(null, "", url);
  }
  return <main className="arena-page" lang={lang === "zh" ? "zh-CN" : "en"}>
    <nav className="arena-nav" aria-label={t("Project navigation", "项目导航")}>
      <a className="intro-brand" href={`${BASE_PATH}/`}><span>ABGA</span>AgentBGA</a>
      <div><a href="#tables">{t("Game tables", "游戏牌桌")}</a><a href="#modules">{t("How it works", "项目模块")}</a><a href={docsUrl}>{t("Docs", "文档")}</a><button type="button" className="intro-language" onClick={toggleLanguage} aria-label={t("切换为中文", "Switch to English")} lang={lang === "zh" ? "en" : "zh-CN"}>{t("中文", "English")}</button><a className="nav-github" href={REPOSITORY_URL}>GitHub <span aria-hidden="true">↗</span></a></div>
    </nav>

    <div className="intro-shell">
      <header className="intro-hero">
        <div className="hero-copy">
          <span className="eyebrow"><i aria-hidden="true"/> {t("Open-source Agentic Board Game Arena", "开源智能体桌游竞技场")}</span>
          <h1>{t("Long games.", "长局博弈。")}<br/>{t("Real decisions.", "真实决策。")}<br/><span>{t("Inspectable agents.", "看得见的智能体。")}</span></h1>
          <p>{t("Put humans and AI agents at the same table. AgentBGA connects playable strategy games, agent runtimes, and decision traces in one reproducible environment.", "让人类与 AI 智能体同桌竞技。AgentBGA 将可玩的策略桌游、智能体运行框架与决策记录整合到同一个可复现的环境中。")}</p>
          <div className="hero-actions"><a className="primary-action" href={playUrl}>{t("Run it locally", "本地运行")} <span aria-hidden="true">↗</span></a><a className="secondary-action" href="#tables">{t("Explore the tables", "探索牌桌")} <span aria-hidden="true">↓</span></a></div>
          <p className="hero-note">{t("Human vs. agent · Agent vs. agent · Seeded replay", "人类对战智能体 · 智能体相互对战 · 种子复现")}</p>
        </div>
        <BoardCarousel boards={games} basePath={BASE_PATH} lang={lang}/>
      </header>

      <div className="project-facts" aria-label={t("Implemented project capabilities", "已实现的项目能力")}>
        <div><strong>10</strong><span>{t("playable game engines", "款可玩的游戏引擎")}</span></div>
        <div><strong>13</strong><span>{t("model & harness backends", "种模型与运行框架后端")}</span></div>
        <div><strong>3</strong><span>{t("experiment modes", "种实验模式")}</span></div>
        <div><strong>CLI + Web</strong><span>{t("one rules engine", "共用规则引擎")}</span></div>
      </div>

      <GameShowcase lang={lang}/>

      <section className="intro-section modules-section" id="modules" aria-labelledby="modules-heading">
        <div className="section-heading"><div><span className="eyebrow">{t("02 / UNDER THE HOOD", "02 / 核心模块")}</span><h2 id="modules-heading">{t("From a legal move", "从一次合法行动")}<br/>{t("to a replayable result.", "到可回放的结果。")}</h2></div><p>{t("The game engine owns the rules. Players and agents choose actions through the same validated game protocol. The surrounding modules make those decisions playable, repeatable, and inspectable.", "规则由游戏引擎统一执行。人类玩家与智能体通过同一套经过校验的协议选择行动，周边模块让这些决策可操作、可复现、可检查。")}</p></div>
        <EngineFlow lang={lang}/>
        <div className="module-grid">
          <article><span className="module-number">{t("01 / RULES & STATE", "01 / 规则与状态")}</span><h3>{t("Deterministic game engines", "确定性游戏引擎")}</h3><p>{t("Seeded setup, versioned state, legal-action generation, scoring, and persisted replay. Seat-scoped agent observations preserve hidden information.", "支持种子初始化、状态版本、合法行动生成、计分与持久化回放。各座位只获得自身可见的信息，保留游戏中的隐藏信息边界。")}</p><a href={`${REPOSITORY_URL}/blob/main/docs/architecture.md`}>{t("Explore the architecture", "查看架构说明")} <span aria-hidden="true">↗</span></a></article>
          <article><span className="module-number">{t("02 / AGENT RUNTIME", "02 / 智能体运行")}</span><h3>{t("Compare the whole agent", "比较完整的智能体")}</h3><p>{t("Combine a model with its harness, tools, and memory strategy. Each participant gets a dedicated workspace and session scope.", "组合模型、运行框架、工具与记忆策略。每位参与者拥有独立的工作目录和会话范围。")}</p><a href={`${usageUrl}#agents`}>{t("See backend configuration", "查看后端配置")} <span aria-hidden="true">↗</span></a></article>
          <article><span className="module-number">{t("03 / HUMAN PLAY", "03 / 人类游玩")}</span><h3>{t("A table for every game", "每款游戏都有专属牌桌")}</h3><p>{t("Board interactions, payment choices, action previews, and explicit confirmation. Responsive layouts and collapsible logs keep the current decision in view.", "直接操作棋盘、选择支付方式、预览行动并明确确认。响应式布局与可收起的日志，让当前决策始终处于视野中。")}</p><a href={playUrl}>{t("Start a human seat", "以人类玩家入席")} <span aria-hidden="true">↗</span></a></article>
          <article><span className="module-number">{t("04 / EVALUATION", "04 / 实验与评估")}</span><h3>{t("Keep the decision trail", "保留完整决策过程")}</h3><p>{t("Inspect actions, available model outputs, tool calls, latency, and reported token usage. Run paired duels, tournaments, or repeated learning series.", "查看行动、可用的模型输出、工具调用、延迟与上报的 token 用量。支持配对对战、多人锦标赛与重复学习系列。")}</p><a href={`${usageUrl}#traces`}>{t("Inspect traces & results", "查看决策记录与结果")} <span aria-hidden="true">↗</span></a></article>
        </div>
        <div className="runtime-row"><span className="eyebrow">{t("BRING YOUR AGENT", "接入你的智能体")}</span><div>{BACKENDS.map(backend => <span key={backend}>{backend}</span>)}</div><p>{t("Plus human players and a random baseline. Install only the runtime you use.", "同时支持人类玩家与随机基线。只需安装实际使用的运行框架。")}</p></div>
      </section>

      <section className="intro-section" id="games" aria-labelledby="games-heading">
        <div className="section-heading"><div><span className="eyebrow">{t("03 / GAME LIBRARY", "03 / 游戏库")}</span><h2 id="games-heading">{t("Ten games.", "十款游戏。")}<br/>{t("Different ways to plan.", "不同的规划方式。")}</h2></div><p>{t("Resource races, card engines, spatial puzzles, drafting, and economic networks. Every game below has a CLI engine and a dedicated browser table.", "资源竞速、卡牌引擎、空间规划、轮抽与经济网络。以下每款游戏都拥有命令行引擎和专属浏览器牌桌。")}</p></div>
        <div className="game-library">{games.map((game, index) => <article key={game.name}><span className="game-number">{String(index + 1).padStart(2, "0")}</span><div><h3>{game.name}</h3><p>{game.scope}</p></div><div className="game-meta"><span>{game.players}{t(" players", " 人")}</span><small>{game.status}</small></div></article>)}</div>
        <p className="coverage-note">{t("Coverage is shown per game. Playable beta implementations remain under validation; Ark Nova’s Map A is a preview.", "实现范围按游戏列出。“可玩测试版”仍在持续验证；方舟动物园的 Map A 为预览版。")} <a href={`${docsUrl}#${lang === "zh" ? "支持的游戏" : "supported-games"}`}>{t("Read the exact scope →", "查看完整实现范围 →")}</a></p>
      </section>

      <section className="quickstart-section" id="quickstart" aria-labelledby="quickstart-heading">
        <div><span className="eyebrow">{t("04 / TRY IT YOURSELF", "04 / 亲自体验")}</span><h2 id="quickstart-heading">{t("Your first match.", "开始你的第一局。")}<br/>{t("No API key needed.", "无需 API key。")}</h2><p>{t("Clone the repository and run a random baseline with Python 3.11+. Build the local table with Node.js 22.13+ to take a human seat.", "克隆仓库后，可用 Python 3.11+ 运行随机基线。使用 Node.js 22.13+ 构建本地牌桌，即可亲自入席。")}</p><div className="docs-links"><a href={`${DOCS_URL}#play-locally`} lang="en">English quick start ↗</a><a href={CHINESE_DOCS_URL} lang="zh-CN">中文文档 ↗</a></div></div>
        <div className="quickstart-code"><span>{t("TERMINAL / FROM THE REPOSITORY ROOT", "终端 / 在仓库根目录执行")}</span><pre><code><b>{t("# A reproducible baseline", "# 运行可复现的随机基线")}</b>{"\n"}{"./agentbga run --game splendor \\\n  --players 2 --controllers random,random --seed 42"}{"\n\n"}<b>{t("# Open the local table", "# 打开本地牌桌")}</b>{"\n"}{"cd web && npm ci && npm run build && cd ..\n./agentbga web"}</code></pre><small>{t("Open", "打开")} <code>http://127.0.0.1:8765</code>{t(" · Choose Human + Random", " · 选择人类玩家 + 随机玩家")}</small></div>
      </section>
      <p className="hosting-note">{t("This site introduces the project. Interactive matches run locally; GitHub Pages does not host a live game service.", "本站用于介绍项目。交互对局在本地运行；GitHub Pages 不提供在线比赛服务。")}</p>
    </div>

    <footer className="site-footer"><a className="intro-brand" href={`${BASE_PATH}/`}><span>ABGA</span>AgentBGA</a><p>{t("Play. Compare. Inspect. Replay.", "游玩。比较。检查。回放。")}</p><div><a href={REPOSITORY_URL}>{t("Source code ↗", "源代码 ↗")}</a><a href={`${REPOSITORY_URL}/blob/main/THIRD_PARTY_NOTICES.md`}>{t("Content & licenses ↗", "内容与许可 ↗")}</a></div></footer>
  </main>;
}
