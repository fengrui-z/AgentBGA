# AgentBGA 项目分析 Review 汇报

> 审查日期：2026-08-15
> 审查范围：`src/`（Python 规则引擎与后端）、`web/`（前端）、`tests/`（114 个测试）、`docs/`、Git 历史（12 个 commit）
> 验证方式：阅读全部核心源码 + 运行完整测试套件（114 passed）+ CLI 冒烟测试（三款游戏各跑完一局随机对局 + `match verify` 重放校验）

---

## 一、项目在做什么

**AgentBGA 是一个面向"长时程 LLM 智能体"研究的 CLI-first 桌游竞技场**。它不是一个普通在线桌游平台，而是一个可复现的实验环境，用于回答一个核心研究问题：

> 在几十个回合的多玩家策略桌游中，智能体能否保持目标、持续规划、理解对手、管理资源？能力究竟来自模型、Harness，还是二者的组合？

项目把评测对象定义为完整的智能体组合 `Agent = Model × Harness × Memory × Prompt × Tool × Compute Budget`，并试图把每个变量拆开做可复现比较（如"OpenCode + DeepSeek vs Codex + DeepSeek"）。

### 当前交付物（全部可运行）

| 组件 | 状态 | 说明 |
|---|---|---|
| **Splendor（璀璨宝石）** | `playable` | 基础版完整规则：90 张发展牌/10 张贵族、拿取/预留/购买、金币、贵族、终局轮与官方破平 |
| **Ark Nova（方舟动物园）** | `controlled_core` | 受控核心 V2：初始手牌、五张行动牌状态机、升级、Break、合作动物园折扣、捐款、释放动物、受控效果原语、生成式终局目标、隐藏信息；使用研究卡池，无出版商数据 |
| **Brass: Birmingham（伯明翰）** | `playable_beta`（未提交！） | 完整官方数据（城市、连接、商人、市场、45 张玩家版图）、运河/铁路双时代、7 种行动决策步骤、负收入清算、两次计分 |
| **可复用机制内核** | `agentbga.mechanics` | ActionSpace、DecisionStep、资源账本、卡牌区域与隐藏投影、轨道、六边形/图拓扑、市场轨道、行动预算、稳定排序、排名 |
| **CLI** | 完成 | `games` / `match`（create/observe/act/events/verify/replay/harness-events）/ `run` / `doctor` / `web` |
| **模型控制器** | 完成 | OpenAI 兼容、Anthropic、Gemini 直连 API + random + human |
| **Harness 控制器** | 完成 | Claude Code（MCP）、Pi（原生扩展）、Codex（MCP）、OpenCode（MCP）、DeepSeek Harness（dsh，MCP）、Hermes Agent（MCP），持久 session、独立工作区、统一工具协议 |
| **Web 实时桌台** | 完成 | 每座位独立配置、SSE 直播、人类 vs 智能体、回合边界暂停、国内模型服务预设（DeepSeek/阿里百炼/智谱/MiniMax） |
| **持久化** | 完成 | SQLite（WAL）+ 事件溯源 + 快照 + 状态哈希 + 精确重放/校验 |

---

## 二、架构分析

### 2.1 分层结构（干净，职责清晰）

```
CLI / Web / MCP(seat_mcp) / Harness
        │  全部调用同一应用服务（store + runner）
        ▼
GameRegistry ──► GamePlugin 协议（runtime_checkable）
        │          │           │
   splendor.py  ark_nova.py  brass_birmingham.py
        └──────────┴──┬─────────┘
               mechanics 内核（11 个模块，无游戏策略）
```

核心约定（`docs/architecture.md` 中提出且代码确实遵守了）：

1. **纯确定性规则核心**：`state + action → events + new_state`，核心无 I/O、无时钟、无网络；随机全部由 seed 驱动。实测同一 seed 的 setup 结果逐字节一致。
2. **事件溯源 + 快照**：`events` 表只追加，每事件带 `state_hash`；`replay` 命令只凭 seed + 已接受动作重放并校验哈希，不一致即抛错。实测 `match verify` 通过。
3. **观察 ≠ 状态**：座位观察是投影（`observe(state, seat)`），对手预留牌只暴露数量（`hidden_items`），核心状态才含全部隐藏信息。契约测试断言"非当前座位永远拿不到合法动作"。
4. **只接受结构化动作**：自由文本永远不进规则引擎；动作经 `ActionSpace` 生成**绑定版本号的 action ID**（`sha256(version:phase:canonical_action)`），过期/非法动作原子失败，`expected_version` CAS 防并发。
5. **CLI 是唯一公共契约**：所有命令输出带 `schema_version` 的 JSON/JSONL，错误走 stderr + 稳定退出码（2 输入错误 / 4 找不到 / 5 版本冲突 / 6 非法动作 / 7 智能体错误 / 8 运行时错误），人机共用同一接口。

### 2.2 关键实现亮点

- **零第三方依赖**：SSE 流式解析、MCP stdio JSON-RPC、子进程 selectors 多路复用、HTTP 客户端全部手写于标准库——`pyproject.toml` 的 `dependencies = []` 是真实可信的。
- **隐藏信息纪律**：`_public_game_event` 把 `choose_initial_hand` 的卡牌列表投影为 `kept_count`；Harness 提示词明确"隐藏的对手信息按设计不可得"；审计事件可含私有观察，因此被标注为"管理员/研究导出"。
- **密钥纪律**：API key 只从环境变量读取、只进进程内存；`PlayerConfig.api_key` 带 `repr=False, compare=False`；harness 子进程环境会剔除所有含 KEY/TOKEN/SECRET/PASSWORD/CREDENTIAL 的变量再注入指定密钥；输出、数据库、事件、命令行（`_redact_text`）均做脱敏；Web 服务**拒绝非 localhost 绑定**（因为要接收凭据）。
- **Harness 提交权威性**：MCP 服务器是唯一权威通道——prose、直接写文件、最终 JSON 消息都不能改棋盘；每个回合先清空 `submission.json`，只能提交一次，且 ID 必须在当前合法集合内。
- **暂停语义**：Web 暂停在回合边界生效（模型生成中的响应让它完成并落子后再停），状态机 `paused / pause_pending / at_pause_gate` 实现严谨，有测试覆盖。
- **流式带宽控制**：`agent_stream`/`harness_output` 等 token 增量事件不携带全量快照（注释明确说明原因），其余事件才附快照，避免长时间推理流产生数百 MB 流量。

### 2.3 与架构文档的偏差（可接受，但值得记录）

- 文档建议 pydantic/Typer/uv/官方 MCP SDK（Python 3.12），实现选择了纯标准库（README 已说明"stdlib sufficient"，是自洽的取舍）。
- 文档规划的 `arena`（锦标赛）、`mcp serve`、`db`、`agent` 命令组、`fork`/`export` 均未实现；无贪婪/启发式/搜索基线（只有 random 与 human）。

---

## 三、三款游戏的完成度

### Splendor（经典-1.0，`playable`）
- 卡牌数据来自研究数据源（Rinascimento CSV，注意源码中显式处理了"花色索引顺序与成本列顺序不同"的坑，有注释）。
- 规则覆盖：三种拿取（3 色各 1 / 同色 2 需银行≥4）、预留（可见/牌堆顶、上限 3、金币）、购买（可见/预留、永久折扣 + 金币通配）、10 币上限原子归还、贵族阶段（多贵族可选中显式成为独立 phase，不藏进引擎裁决）、15 分终局轮 + 官方破平（分数 → 购卡数）。
- **pass 兜底**：只在"无任何印行规则动作"的病理状态下生成（注释解释了该状态可达），保证全转移函数完备。
- 不变式校验：代币/卡牌守恒、数量唯一性、上限约束，每步 transition 后自动检查。

### Ark Nova（受控核心 V2，`controlled_core`）
- 诚实标注：研究生成卡池（128 动物 + 64 赞助 + 20 项目 + 12 终局目标 + 9 奖励板块），"implementation: controlled_effect_primitives" 逐卡标注；出版商卡牌能力与已验证地图足迹**明确 deferred**，UI/API 用 `controlled_core` 标签避免与未来完整版混淆。
- 已实现：初始手牌选择（独立 phase + 决策上限）、行动牌力量移动与升级里程碑、Break 轨道（含玩家数差异化上限）、协会板（合作动物园/大学/捐款阶梯/释放项目）、地图 A 示意图（轴向六边形、地形、放置奖励）、隐藏信息、终局目标计分。
- 设计上把"何时合法、效果顺序、计分"留在插件内，内核只提供 `advance_track`、`axial_hex_neighbors` 等机制。

### Brass: Birmingham（`playable_beta`，未提交）
- 数据面很扎实：官方 20 城 + 5 商人城 + 连接图（运河/铁路时代区分）、双轨、行业板块 45 张逐张数据（等级/份数/费用/产出/VP/收入格/链接图标/可开发性）、玩家数定制牌堆与商人板块、收入轨道。
- 规则面：Build/Sell（显式资源来源选择，煤/铁/啤酒可来自市场或对手）、Network（含双铁轨）、Develop、Loan、Scout、Pass；资源枯竭翻转产业并推进收入格；负收入清算作为显式决策步骤；运河→铁路跨时代（计分、清场、重洗、发牌）；终局收入等级破平。
- 内核新增贡献：`ActionBudget`、`stable_metric_order`（金钱花费决定下轮顺序）、`MarketTrack`（显式购买/补货顺序）、`SupplySource`、`NetworkEdge` 拓扑。

**实测**：三款游戏 random vs random 均完整跑通（Splendor 94 回合、Ark Nova 60 回合+终局、Brass 双时代 199 个决策），`match verify` 重放哈希一致。

---

## 四、测试与质量状况

```
114 tests passed + 21 subtests（19 秒）
```

| 文件 | 数量 | 覆盖 |
|---|---|---|
| test_brass_birmingham | 32 | 官方例外规则场景（无板块开局、单图标槽优先级、陶器铁路时代例外、双轨啤酒连通、收入破平）、双时代回归 |
| test_ark_nova | 19 | 初始手牌、行动牌状态机、Break、隐藏信息、终局 |
| test_web | 14 | SSE 流、暂停/恢复、人类回合等待与校验、密钥不落库、拒绝非 localhost、快照轻量化 |
| test_agents | 10 | 三家 API 的请求/响应/流式解析（mock）、JSON 提取容错、重试与 fallback |
| test_harness | 9 | seat 工具单次提交、MCP 工具集、命令构造与 session 恢复、环境密钥过滤 |
| test_mechanics | 12 | 内核各原语（含无效输入拒绝） |
| test_store | 6 | 事件追加、版本冲突、重放校验 |
| test_cli | 5 | 输出契约、退出码 |
| test_splendor | 4 | 拿取/购买/贵族/守恒 |
| test_game_contract | 3 | 对**每个注册游戏**做确定性、协议、错误座位断言（跨游戏契约） |

质量信号：
- 契约测试按 `game_ids()` 遍历，新增游戏自动获得协议检查——这是插件体系健康的证据。
- 隐藏信息、并发版本冲突、密钥不落库这类"负面能力"都有专门测试。
- 没有 CI 配置文件、没有覆盖率统计；Python 侧无 lint/type-check 配置。

---

## 五、发现的问题与风险（按严重程度排序）

### 🔴 高优先级

1. **一半的工作量尚未提交**：`brass_birmingham.py`（1750 行，全项目最大的文件）、`mechanics/markets.py`、`supply.py`、`turns.py`、`tests/test_brass_birmingham.py` 全部是 untracked；另有 12 个已跟踪文件被修改（含架构文档、registry、web）。当前分支 `agent/improve-human-game-ui`。**这是最大的工程风险**：任何误操作都会丢掉第三款游戏。

2. **README 与现状严重脱节**：README 只字未提 Brass: Birmingham（一个 `runnable: true`、32 个测试的游戏），"Current status" 一节仍停留在 Ark Nova 计划阶段；`docs/project-overview.zh-CN.md` 同样未提 Brass。README 声称"Planned next for Ark Nova"的许多条目实际已部分完成，但 Brass 这个更大的进展反而缺席。

3. **没有 CI**：仓库无 `.github/`。且测试必须在 `PYTHONPATH=src` 或安装包后才能跑（裸 `pytest` 会 ImportError）——无人值守环境下这必然红。架构文档承诺的"跨进程 seed 确定性测试""golden replay fixtures""序列化兼容测试"也尚未落地为自动化测试。

### 🟡 中优先级

4. **Web 工具链存在 beta 与遗留物**：前端用 `vinext 1.0.0-beta.2`（Next.js-on-Vite 的 beta 版）+ Cloudflare wrangler 全家桶，但实际部署是 Python `http.server` 托管静态产物；仓库里残留 `web/worker/index.ts`（Cloudflare Worker 入口）、`web/.openai/hosting.json`、`web/.wrangler/`、`web/.vite/` 等与当前运行方式无关的文件。依赖面（React 19 + vinext + vite 8 + wrangler + tailwind 4）对一个本地静态 UI 而言偏重，且 beta 工具链有升级断裂风险。

5. **通用 CLI 泄漏游戏特例**：`cli.py` 的 `act` 分支硬编码了 `"kept_count": 4`（Ark Nova 初始手牌保留数），`store.py` 的 `_public_game_event` 也特判 `choose_initial_hand`。目前只有 Ark Nova 用它，尚可接受，但违反了"CLI 不得实现游戏规则"的架构原则，第三款带初始选牌的游戏出现时就会出错。

6. **研究可追溯性缺口（项目自己已承认）**：`model_calls` 只存元数据（延迟/token/fallback），模型逐字输出与思考流只用于实时展示、不持久化；`docs/project-overview.zh-CN.md` 已把"持久化规范化请求/响应"列为下一阶段。对"论文级评测平台"的目标这是关键短板。

7. **Web 运行态在进程内**：`MatchHub` 的对局记录、暂停状态、SSE 缓冲都在内存；服务重启即丢（SQLite 里的对局仍可用 CLI 继续，但 Web 上无感知）。线程为 daemon，无优雅关闭。

### 🟢 低优先级 / 观察项

8. 手写 MCP server 是最小实现（无 resources/notifications，工具集固定三个）——够用，但与官方 SDK 的兼容面有限。
9. `harness.py` 的环境过滤按变量名关键字（KEY/TOKEN/SECRET/...）剔除，可能误伤无关变量（如 `COOKIE` 类），方向安全但粒度粗。
10. 无启发式/贪婪/搜索基线，`run` 的 `--fallback random` 会掩盖模型失败——架构文档第 10 节自己也要求"正式评测关闭随机 fallback"，尚未实现开关语义（目前 fallback 策略硬编码 random 或 fail）。
11. `web/page.tsx` 类型与后端观察结构手写对齐（无代码生成/共享 schema），`GameId` 联合类型新增游戏时要手工改 4 处类型定义。
12. 提交历史全部来自同一作者的分支式开发（12 commits），符合个人研究项目形态，但合并提交把每个功能大块合入，评审粒度较粗。

---

## 六、改进建议（按 ROI 排序）

1. **立刻提交当前工作**：把 Brass: Birmingham + 内核扩展 + 测试整理成一个（或几个）commit 推入 main，消除最大风险。
2. **补齐 README**：加入 Brass 章节（数据来源、完成度、运行方式）、更新 Current status、把 docs/project-overview.zh-CN.md 同步。
3. **加 CI**：一个最小的 GitHub Actions（Python 3.11/3.12，`PYTHONPATH=src pytest tests/`；web 侧 `npm run lint` + `npm test`）即可锁住当前质量。
4. **建立 Python 质量门槛**：`ruff` + `mypy`（或 pyright）最小配置；`pyproject.toml` 补 dev 依赖组。
5. **剥离 CLI/store 中的游戏特例**：把 `choose_initial_hand` 的公开投影下沉为"事件携带的公共字段 + 游戏自报的隐私策略"，或至少把 `kept_count` 改为从 state 读取。
6. **短期研究价值最高的三件事**（与项目自己的路线图一致）：持久化规范化模型调用轨迹（请求/响应/费用/延迟/版本）、实现 greedy/启发式基线 + `--fallback none`、补 `arena` 批量调度（多 seed + 座位轮换），它们把平台从"能玩"推向"能出论文数据"。
7. **清理 web 目录**：删除 `worker/index.ts`、`.openai/`、`.wrangler/`、`.vite/` 等非运行所需文件，或明确它们是部署实验并加注释；评估把前端从 vinext beta 锁版本并固定构建产物。
8. **补关键自动化**：跨进程 seed 确定性测试、golden replay fixture（防 rules 变更静默改写旧对局）、Brass 官方规则场景的逐条编号清单（现状测试名已覆盖大部分）。

---

## 七、总体结论

**这是一个架构水准明显高于一般个人项目的科研型基础设施**：确定性规则核心、事件溯源 + 哈希校验重放、座位级隐藏信息投影、版本化 action ID 并发控制、密钥与沙箱纪律，这些"正确性/安全骨架"全部真实落地且有测试背书，而非纸面设计。三款玩法差异极大的游戏（引擎构筑 / 多决策步长时程 / 双时代经济网络）共用同一插件协议与机制内核，证明了扩展路径是通的——Brass 的加入恰好是架构文档 M5"用第二款游戏验证可扩展性"的成功续篇。

主要短板不在代码质量，而在**工程化收尾**：未提交的 Brass、缺席的 README 章节与 CI、偏重的 beta 前端工具链、以及研究数据管线（模型轨迹持久化、基线、锦标赛调度）尚未闭环。清理这些之后，AgentBGA 就具备了作为长时程多智能体评测基准的完整形态。

**一句话总结**：AgentBGA 是一个"把复杂桌游变成可控长时程智能体实验环境"的 CLI-first 平台，目前拥有三款可运行游戏（Splendor 完整、Ark Nova 受控核心、Brass 测试版）、统一协议与机制内核、多模型 × 多 Harness 对比能力与严格的确定性/隐私纪律；下一步的重点是把未提交的工作落地并补齐研究数据管线与 CI。
