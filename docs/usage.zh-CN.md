# AgentBGA 使用指南

[English](usage.md) · **简体中文** · [返回 README](../README.zh-CN.md)

首次使用请先看[本地快速开始](../README.zh-CN.md#本地游玩)。
本指南介绍可选配置和检查流程。所有命令均从仓库根目录运行；
模型名、端点地址和环境变量占位内容需要替换成提供商支持的配置。

[智能体](#agents) · [游戏设置](#games) · [Trace](#traces) ·
[实验](#experiments) · [CLI](#cli) · [常见问题](#troubleshooting)

<a id="agents"></a>

## 智能体与认证

通过 `--players-config` 为各座位独立配置：

```bash
./agentbga doctor --players-config examples/multi-llm-match.json
./agentbga run --players-config examples/multi-llm-match.json --seed 42 --jsonl
```

运行前先编辑示例：其中有四种提供商的模型和凭证占位配置。
用 `api_key_env` 指定环境变量名，不要把密钥直接放进 JSON。
玩家数量必须符合所选游戏要求。`doctor` 会检查配置，但通过检查不代表能完成
整局模型对战。调用 API 会消耗所配置提供商的额度。

### 选择后端

每个座位可使用以下控制器：

| 后端 | 类型 | 说明 |
| --- | --- | --- |
| `openai` | 直连 API | 兼容 OpenAI Chat Completions 的端点 |
| `anthropic` | 直连 API | Anthropic Messages API |
| `gemini` | 直连 API | Google Gemini generateContent |
| `opencode` | Harness | CLI + MCP，持久会话 |
| `codex` | Harness | CLI + MCP，持久会话；API key 或 ChatGPT 订阅认证 |
| `dsh` | Harness | DeepSeek Harness，可恢复的无交互冷启动配置 |
| `hermes` | Harness | Hermes Agent + MCP，隔离 home，持久会话 |
| `claude` | Harness | Claude Code + MCP，持久会话 |
| `pi` | Harness | Pi + 原生 TypeScript 扩展，持久会话 |
| `qwen` | Harness | Qwen Code + MCP，隔离提供商配置，持久会话 |
| `cursor` | Harness | Cursor Agent CLI + MCP，隔离数据目录，持久会话 |
| `grok` | Harness | xAI Grok Build CLI + MCP，隔离 home 和沙箱，持久会话；API key 或 SuperGrok 订阅 |
| `minimal` | Harness | 纯 Python 进程内实现，直连模型和 10 个座位限定工具 |
| `human` | — | 浏览器人类游玩 |
| `random` | — | 随机基线 |

各 harness 共用限定座位的工具接口：`observe`、分页 `legal_actions`、
`inspect_card`、`inspect_rules`、`inspect_map`、`inspect_played_cards`、
`inspect_history`、`submit_action`、`read_notes` 和 `write_notes`。
方舟动物园默认提供紧凑观察和状态增量；完整的可见卡牌、地图、已打出卡牌与观察历史
按需加载。`minimal` 完全在 Python 内运行，不需要外部 CLI、MCP 服务或 Node.js。
游戏专用过滤器和有界返回见[合法行动查询（英文）](legal-action-queries.md)。

### Hermes、Qwen Code、Cursor 与 Grok API 配置

`hermes` 后端需要支持 MCP 的 `hermes` 可执行文件。AgentBGA 为座位创建独立的
`HERMES_HOME`，仅配置该座位的 `agentbga` MCP 服务，并通过 Hermes 的自定义
提供商接入所配置的 OpenAI 兼容端点。

`qwen` 后端需要 `qwen` 可执行文件。AgentBGA 创建座位独立的 `QWEN_HOME` 和
`QWEN_RUNTIME_DIR`，配置 OpenAI 兼容模型提供商，禁用环境中的其他工具和记忆，
只暴露该座位的 `agentbga` MCP 工具。使用阿里云 Coding Plan 的示例：

```bash
export BAILIAN_CODING_PLAN_API_KEY='...'
./agentbga doctor --players-config examples/qwen-code-vs-random.json
./agentbga run --players-config examples/qwen-code-vs-random.json --seed 42 --jsonl
```

`cursor` 后端需要 `cursor-agent` 可执行文件和 `CURSOR_API_KEY`。
`grok` 后端需要 xAI 的 `grok` 可执行文件，默认使用 `XAI_API_KEY`。
两者以无交互方式运行并保留原生会话，禁用内置编码和网页工具，仅暴露 AgentBGA 的
座位限定 MCP 工具。用户配置、凭证和会话位于各参与者独立的工作区。

```bash
export CURSOR_API_KEY='...'
export XAI_API_KEY='...'
./agentbga doctor --players-config examples/cursor-cli-vs-grok-build.json
./agentbga run --players-config examples/cursor-cli-vs-grok-build.json --seed 42 --jsonl
```

### Codex 与 ChatGPT 订阅

Codex 可以复用本机 CLI 已认证的 ChatGPT 订阅。先登录，再设置
`auth_mode: "subscription"`，并省略 `base_url` 和 `api_key_env`：

```bash
codex login
./agentbga doctor --players-config examples/codex-subscription-vs-random.json
./agentbga run --players-config examples/codex-subscription-vs-random.json --seed 42 --jsonl
```

订阅模式只把当前 Codex 凭证接入座位独立的 `CODEX_HOME`，强制使用 ChatGPT 登录，
禁用个人插件、技能、shell 访问、历史和记忆；不注入 `OPENAI_API_KEY` 或端点覆盖配置。
默认的 `api_key` 模式仍使用座位独立的按量 API 配置。
Codex 自定义 API 端点必须支持 Responses API（`wire_api: "responses"`）。
请选择账号可用的模型；示例中的模型只是可修改的起点，不代表已验证访问权限。

### Grok Build 与 SuperGrok 订阅

使用订阅认证时，先安装[官方 CLI](https://docs.x.ai/build/overview)，再运行：

```bash
grok login
grok models
./agentbga doctor --players-config examples/grok-subscription-vs-random.json
./agentbga run --game azul --players-config examples/grok-subscription-vs-random.json --seed 42 --jsonl
```

网页选择 **Grok Build → SuperGrok 订阅**。此模式不发送 API key 或端点。
JSON 中必须显式设置 `auth_mode: "subscription"`；省略时仍按 API key 模式运行。
订阅模式在项目中的默认模型为 `grok-4.6`，使用模型原生的思考强度默认值；
也可在 JSON 中显式指定模型支持的 `reasoning_effort`。

订阅模式保留座位独立的 `GROK_HOME` 和严格工具沙箱，通过官方 `GROK_AUTH_PATH`
指向原始登录凭证，由 Grok 管理刷新与文件锁，不复制凭证。
`GROK_DISABLE_API_KEY_AUTH=1` 防止退回按量 API 认证。
只读发现个人插件后按名称禁用，同时禁用技能注入和环境兼容集成。
生成工作区的 Git 边界限制向上发现项目配置。全部现有座位 MCP 工具仍可使用，
包括方舟动物园的检查工具。

配置和 MCP 发现曾在 Grok Build 1.0.30 上验证。`doctor` 检查可执行文件和本地凭证，
不测试在线订阅权限；额度和模型可用性仍取决于账号。离线测试不消耗模型额度，
未提供的用量或费用不能记为零。

### 会话与记忆

各 harness 的普通对局记忆归属于 `(match_id, seat)`。
学习系列中则归属于 `(series_id, participant_id)`，参与者轮换座位时仍保留自己的
会话，不继承对手私有上下文。DSh 使用可恢复的冷启动运行方式；支持原生会话的外部
harness 从同一参与者工作区恢复会话。实验额外加入内部 `run_id` 命名空间，
再次运行同一配置时从干净记忆开始。系列运行不会额外增加赛后复盘回合。

```json
{"backend":"dsh","model":"deepseek-v4-flash","series_id":"anneal-20","participant_id":"learner"}
```

Harness 对局示例：

```bash
export DEEPSEEK_API_KEY=...
./agentbga run --players-config examples/dsh-vs-opencode.json --seed 42 --jsonl
```

<a id="games"></a>

## 游戏设置与操作说明

用 `./agentbga games list --json` 查看已注册游戏，
用 `./agentbga games describe GAME_ID --json` 查看当前实现范围、人数和规则版本。
[README 游戏表](../README.zh-CN.md#支持的游戏)提供简要概览，下面补充特殊设置。
网页中先检查行动预览，再确认；选择卡牌、地块、支付方式或目标可能只是中间步骤，
不等于已经提交行动。

### 方舟动物园 / Ark Nova

默认使用已发布的 Map 0。在 `match create` 或 `run` 中传入 `--map map-a`
可以选择单独标记的 Map A 预览版；Map 1–8 尚未实现。
网页中的单人人类预设无需 API key。卡牌数据描述游戏机制，不打包出版商美术或逐字牌文。

### 自然和弦 / Harmonies

```bash
./agentbga run --game harmonies --players 2 --controllers random,random --seed 42
./agentbga run --game harmonies --players 1 --controllers random --seed 42 \
  --game-config '{"board_side":"B","nature_spirits":true}'
```

网页选择 **自然和弦 / Harmonies**，可选 A 面（河流）或 B 面（岛屿），并可启用自然之灵。
**Solo** 预设无需 API key。拿取地形组后，选择地形并点击高亮六角格。
动物卡显示准确的堆叠高度和动物方块目标；可放置时选择 **安置动物 / Settle animal**
与高亮目标。可选的拿卡、安置动物操作可以穿插于地形放置之间；三块地形放完后选择
**结束回合 / End turn**。

包含确定性回放、累计动物得分、等回合终局、单人市场刷新和太阳评级。
卡牌使用稳定编号与原创 SVG 图示。机制目录由社区转录，标记为可玩测试版；
不包含出版商美术或扩展卡。详见[实现与验证计划（英文）](harmonies-implementation-plan.md)。

### 展翅翱翔 / Wingspan

```bash
./agentbga run --game wingspan --players 2 --controllers random,random --seed 42
./agentbga run --game wingspan --players 5 --controllers random,random,random,random,random \
  --seed 42 --game-config '{"goal_board":"blue"}'
```

网页选择 **展翅翱翔 / Wingspan**，配置 2–5 名人类、随机或模型玩家，
选择绿色竞争目标板或蓝色个人目标板。开局保留鸟牌，每保留一张弃掉一个食物，
再保留一张奖励卡。点击栖息地行动或打出手牌，按提示选择支付和效果。
鸟类能力与奖励条件有中英文描述；与名称相关的奖励按目录中的英文鸟名计算。

包含 170 张原版基础鸟牌、26 张奖励卡、8 块双面目标板、白/棕/粉能力、
精确种子回放与隐藏信息观察。不包含 Swift-Start、扩展、Automa 单人模式或出版商美术。
社区转录的机制目录标记为可玩测试版；详见[实现与验证（英文）](wingspan-implementation-plan.md)
及[第三方声明](../THIRD_PARTY_NOTICES.md)。

### 卡卡颂 / Carcassonne

```bash
./agentbga run --game carcassonne --players 2 --controllers random,random --seed 42
./agentbga run --game carcassonne --players-config examples/carcassonne-random-match.json --seed 42
```

网页选择 **卡卡颂 / Carcassonne**，配置 2–5 名人类、随机或模型玩家。
旋转当前地块并选择高亮位置，再放置一个随从或跳过。可点击任意地块检查连通区域，
滚动或缩放共享地图。包含 72 张基础地块、道路、城市、盾徽、修道院、农夫、
多数并列、终局计分和确定性持久化回放；未来抽牌顺序保持隐藏。
使用原创 SVG 图形，不包含河流、修道院长及其他扩展。
详见[规则、协议与验证（英文）](carcassonne.md)。

<a id="traces"></a>

## Trace 与审计

Harness 模型调用保存为结构化 JSON trace。绕过模型的自动行动记录在游戏事件中；
人类和随机控制器也使用游戏事件，不生成模型 trace。

```bash
./agentbga match traces MATCH_ID --json             # 列出 trace
./agentbga match traces MATCH_ID --seat 0 --turn 7   # 导出指定记录
./agentbga match harness-events MATCH_ID --json     # 工具调用审计
```

文件位于 `.agentbga/runs/_traces/MATCH_ID/seat-N/turn-XXXX.json`，包含提示词、
后端实际暴露的推理/内容、工具调用与结果，以及最终提交。模型内部推理可能不可获取。
还会记录参与者、稳定会话范围、恢复次数和 DSh 压缩事件。
导出指定 trace 时使用列表返回的 turn 值。用量指标见下一节。

<a id="experiments"></a>

## 实验与结果文件

示例配置是模板：付费运行前，先设置可访问的模型、真实端点和凭证环境变量。
尤其要替换示例中出现的 `https://api.example.com/v1`。
验证命令检查配置和赛程，不调用提供商验证凭证或模型权限。

实验支持三种可复现的调度模式：

- `duel`：两名参与者、配对种子、双方座次，不跨局保留记忆。
- `tournament`：配置的每种 2/3/4 人组合及全部循环座次，不跨局保留记忆。
- `series`：两人交替座次连续对局，一方或双方可保留系列记忆，各独立重复之间不共享记忆。
  奇数长度系列会在重复之间交替起始座次；生成的种子区间不重叠，结果保留原始 `base_seed`。

```bash
./agentbga experiment validate --config examples/experiment-duel.json
./agentbga experiment run --config examples/experiment-duel.json \
  --out .agentbga/experiments/duel-001
```

对应示例：[双人对决](../examples/experiment-duel.json)、
[多人锦标赛](../examples/experiment-tournament.json)、
[单边学习系列](../examples/experiment-series-one-sided.json)。

可在服务器恢复运行的 12 名参与者、396 场平衡 Frontier12 锦标赛配置见
[`examples/frontier12-tournament.json`](../examples/frontier12-tournament.json)。
[服务器手册](frontier12-server-run.zh-CN.md)包含凭证检查、覆盖全部参与者的四局探测、
16 worker 执行和恢复步骤。

每次运行以原子写入方式生成累计的 `agentbga.results.v1` 文件：
`latest.json` 在每个配置批次后更新，`results-000020.json` 是不可变检查点示例，
`final.json` 为最终文件。`results.emit_every` 设为 `1` 时每场输出，设为 `N`
时每 N 场输出。格式见[结果 schema](../schemas/results-v1.schema.json)。

已完成对局的结果还包含 `harness_metrics`，按 harness 座位记录提供商报告的输入/输出
token、缓存读写、未缓存输入、推理 token、缓存命中率、控制器调用、失败与随机回退、
会话恢复、上下文压缩，以及进程/行动耗时统计。
对局级缓存命中率为 `cached_input_tokens / input_tokens`；推理 token 是输出 token
的子集，不重复累加。提供商或 harness 没有给出精确用量时，
`token_usage.available` 为 `false`，`totals.complete` 为 `false`，不使用估算值代替。

如果需要带上传凭证，可以在生成时从环境变量读取，无需把 token 写进实验配置：

```json
{"results":{"emit_every":20,"submission_token_env":"AGENTBGA_RESULTS_TOKEN"}}
```

生成文件会包含 `submission.token`；完整性摘要覆盖评测数据，不覆盖传输凭证。
接收服务必须验证 token，并在保存结果前将其移除。这是上传凭证，不是玩家身份认证。
不要公开包含 `submission.token` 的结果文件。

<a id="cli"></a>

## CLI 参考

在源码目录通过 `./agentbga` 运行。将 `MATCH_ID` 替换为已有对局 ID。
座位从 0 编号；提交行动前先读取当前观察和合法行动，`expected_version` 必须与当前状态一致。
下面行动命令中的 `VERSION` 要替换成该整数，`ACTION_ID` 要替换成同一座位、
同一状态下 `legal-actions` 返回的行动 ID。

```bash
./agentbga games list --json
./agentbga match create --game splendor --players 4 --seed 42 --json
./agentbga match create --game azul --players 2 --seed 42 --json
./agentbga match create --game castles_of_burgundy --players 2 --seed 42 --json
./agentbga match create --game seven_wonders --players 3 --seed 42 --json
./agentbga match observe MATCH_ID --seat 0 --json
./agentbga match legal-actions MATCH_ID --seat 0 --json
./agentbga match act MATCH_ID --seat 0 --expected-version VERSION \
  --action-id ACTION_ID --json
./agentbga match events MATCH_ID --jsonl
./agentbga match verify MATCH_ID --json
./agentbga match replay MATCH_ID --json
./agentbga match traces MATCH_ID --json
./agentbga experiment validate --config EXPERIMENT.json
./agentbga experiment run --config EXPERIMENT.json --out RESULTS_DIR
./agentbga web --port 8765
```

<a id="troubleshooting"></a>

## 常见问题

| 现象 | 排查方法 |
| --- | --- |
| `frontend build not found` | 在 `web/` 运行 `npm ci` 和 `npm run build`，再从仓库根目录启动 `./agentbga web`。 |
| 找不到外部 harness 可执行文件 | 安装相应 harness，并确保服务进程的 `PATH` 可以找到它；参见后端列表。 |
| 找不到订阅登录 | 使用运行 AgentBGA 的同一个系统用户登录 CLI，再用玩家配置运行 `doctor`。 |
| 模型拒绝请求 | 检查模型权限、端点、API key 环境变量、思考参数和提供商额度；本地登录检查不能覆盖全部条件。 |
| 游戏不接受所选人数 | 查看 `games describe` 中的人数范围；七大奇迹至少需要三人。 |
| 提交的行动已过期 | 重新读取观察和合法行动，使用当前版本及该状态下的行动。 |
| 模型失败后出现随机行动 | 默认策略为 `--fallback random`；如需失败即停止，使用 `--fallback fail`，并查看失败/回退指标。 |
| 无法从网页暂停 CLI 对局 | 观战不会接管运行进程；暂停控件适用于网页运行的对局。 |

做评测时，按需要显式指定 `--retries`、`--fallback` 和 `--max-turns`，并随结果报告。
达到回合上限时，对局可能仍未结束。缺失用量不能当作零。

Web 服务仅供本地使用，没有参与者登录或座位授权。
API key、CLI 凭证、原始 trace 和运行工作区应保持私密。
发布前检查结果文件；静态 Pages 页面目前不公开实验结果，本地导出应放在 `web/public` 之外。见
[Web 开发说明（英文）](../web/README.md)。
