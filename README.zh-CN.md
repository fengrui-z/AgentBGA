# AgentBGA

[English](README.md) · **简体中文**

与 AI 智能体玩策略桌游、观看智能体对战，并回放它们的决策。
AgentBGA 提供十款确定性游戏引擎、本地浏览器牌桌，以及用于比较模型、
智能体运行框架（harness）和记忆策略的命令行工具。

**从这里开始：**[本地游玩](#本地游玩) · [接入智能体](#接入智能体) ·
[支持的游戏](#支持的游戏) · [查看对局与决策记录](#查看对局与决策记录) ·
[运行实验](#运行实验)

## 本地游玩

需要 **Python 3.11+** 和 **Node.js 22.13+**（含 npm）。在终端执行以下命令；
Python CLI 可以直接从源码目录运行，无需安装 Python 包。

```bash
git clone https://github.com/fengrui-z/AgentBGA.git
cd AgentBGA
cd web
npm ci
npm run build
cd ..
./agentbga web
```

打开 **[http://127.0.0.1:8765](http://127.0.0.1:8765)**，先体验一局：

1. 选择 **璀璨宝石 / Splendor**，设置两名玩家。
2. 一名设为 **人类玩家 / Human**，另一名设为 **Random**，无需 API key。
3. 开始对局，在牌桌上选择行动，检查预览后确认。

界面支持中英文切换。当前决策和自己的玩家摘要靠近牌桌，桌面布局利用宽屏并排显示信息；
完整玩家详情可按需展开。Agent 输出和 Action 记录可以分别收起。
较大的地图仍可使用地图内的缩放或滚动控件。

实时牌桌**仅监听 localhost**，没有多用户身份认证，适合在可信设备上使用。
Node.js 用于构建前端，构建完成后由 Python 提供页面。
公开的 GitHub Pages 页面只展示项目与静态实验结果，不提供在线比赛服务。

<details>
<summary><strong>只想用终端？仅需 Python 即可跑一局。</strong></summary>

在仓库根目录运行两名随机玩家的璀璨宝石对局：

```bash
./agentbga run --game splendor --players 2 --controllers random,random --seed 42
```

不需要 Node.js、API key、外部智能体 CLI 或安装 Python 包。
结果会包含对局 ID；加上 `--jsonl` 可以逐条输出决策事件。

</details>

## 接入智能体

每个座位独立配置控制器。建议先让一名智能体与人类或随机玩家对战，
再通过[玩家配置文件](docs/usage.zh-CN.md#agents)让多个模型或 harness 同桌比较。
只需安装自己选用的外部 CLI。

<details>
<summary><strong>使用本机已登录的 Codex / ChatGPT 订阅</strong></summary>

安装 Codex CLI 后，在运行 AgentBGA 的同一台机器上登录：

```bash
codex login
```

在浏览器中将智能体座位设为 **Codex → ChatGPT 订阅**，填写账号可用的模型名，
另一个座位设为 **人类玩家**。订阅模式无需填写 API key 或自定义 endpoint。

如果使用 CLI，先把示例中的模型改成账号可用的模型，再运行：

```bash
./agentbga doctor --players-config examples/codex-subscription-vs-random.json
./agentbga run --players-config examples/codex-subscription-vs-random.json --seed 42 --jsonl
```

`doctor` 检查本地可执行文件和登录状态，不代表已验证在线模型权限或剩余订阅额度。
详见[认证与配置说明](docs/usage.zh-CN.md#agents)。

</details>

<details>
<summary><strong>接入模型 API、OpenAI 兼容端点或其他 harness</strong></summary>

下面使用兼容 OpenAI Chat Completions 的端点。
将 `YOUR_MODEL` 替换为端点支持的模型：

```bash
export OPENAI_API_KEY='YOUR_API_KEY'
./agentbga run --players 2 --controllers openai,random \
  --base-url https://api.openai.com/v1 --model YOUR_MODEL --seed 42 --jsonl
```

使用本地模型或网关时，修改 `--base-url` 和模型 ID。
在浏览器中则选择提供商与运行方式，填写对应模型和凭证。

还支持 Anthropic、Gemini API，以及 OpenCode、Codex、DSh、Hermes、Claude Code、
Pi、Qwen Code、Cursor、Grok Build 和内置 Minimal harness。
详见[后端列表与配置指南](docs/usage.zh-CN.md#agents)。

</details>

## 支持的游戏

十款游戏均提供浏览器牌桌和可设置随机种子的 CLI 引擎。
“可玩测试版”表示实现仍在持续验证；评测时请留意具体规则范围。
CLI 的 `--game` 使用下表中的游戏 ID。

| 游戏 | 游戏 ID | 人数 | 实现范围 / 状态 |
| --- | --- | --- | --- |
| 璀璨宝石 / Splendor | `splendor` | 2–4 | 基础版；可玩 |
| 展翅翱翔 / Wingspan | `wingspan` | 2–5 | 170 张基础鸟牌、26 张奖励卡、两种目标板；可玩测试版 |
| 自然和弦 / Harmonies | `harmonies` | 1–4 | A/B 面、32 张动物卡、可选自然之灵；可玩测试版 |
| 花砖 / Azul | `azul` | 2–4 | 彩色墙面基础版；可玩测试版 |
| 伯明翰 / Brass: Birmingham | `brass_birmingham` | 2–4 | 运河与铁路两个时代；可玩测试版 |
| 勃艮第城堡 / The Castles of Burgundy | `castles_of_burgundy` | 2–4 | 2019 基础版，共用 1 号领地；可玩测试版 |
| 香料之路 / Century: Spice Road | `century_spice_road` | 2–5 | 基础版；可玩 |
| 方舟动物园 / Ark Nova | `ark_nova` | 1–4 | 已发布基础版 Map 0；Map A 需主动选择，属于预览版 |
| 七大奇迹 / 7 Wonders | `seven_wonders` | 3–7 | 第二版基础规则，日/夜奇迹；可玩 |
| 卡卡颂 / Carcassonne | `carcassonne` | 2–5 | 72 张基础地块，含农夫；可玩测试版 |

不接模型也能单人游玩：选择 **方舟动物园** 或 **自然和弦**，使用 **Solo** 预设。
七大奇迹至少需要三名玩家，可以补一个人类、随机或智能体座位。
变体与未包含内容见[游戏设置和操作说明](docs/usage.zh-CN.md#games)。

## 查看对局与决策记录

对局默认保存在 `.agentbga/agentbga.sqlite3`。可以在创建页面打开最近的对局，
也可以访问 `http://127.0.0.1:8765/?match=MATCH_ID`。
观战 CLI 对局不会接管原来的运行进程；网页暂停功能适用于从网页运行的对局。

将 `MATCH_ID` 替换为运行结果中的对局 ID：

```bash
./agentbga match events MATCH_ID --jsonl
./agentbga match verify MATCH_ID --json
./agentbga match replay MATCH_ID --json
./agentbga match traces MATCH_ID --json
```

游戏事件记录已接受的行动；harness trace 进一步记录提示词、工具调用、调用结果和
后端实际提供的模型输出，不保证能获得模型的内部推理。
Trace 文件位于 `.agentbga/runs/_traces/MATCH_ID/seat-N/`。
人类和随机玩家的操作可以通过游戏事件查看，不需要模型 trace。

逐回合导出方式见 [trace 与用量指标](docs/usage.zh-CN.md#traces)。
分享结果时，应保留原始 trace 和本地运行数据的私密性。

## 运行实验

用 **duel** 比较配对种子与双方座次，用 **tournament** 比较多人组合，
用 **series** 研究连续对局中的记忆。先根据自己的环境配置示例中的模型、端点和凭证：

```bash
./agentbga experiment validate --config examples/experiment-duel.json
./agentbga experiment run --config examples/experiment-duel.json \
  --out .agentbga/experiments/duel-001
```

验证命令检查实验配置，不测试提供商访问权限。
实验逐批写入结果并生成最终文件，其中包含可获得的 harness 用量与失败指标。
[实验模式、记忆与结果文件 →](docs/usage.zh-CN.md#experiments)

## 深入阅读

| 你想做什么 | 文档 |
| --- | --- |
| 配置 harness、游戏变体、trace 或 CLI 行动 | [使用指南](docs/usage.zh-CN.md) |
| 高效查询大量合法行动 | [合法行动查询（英文）](docs/legal-action-queries.md) |
| 理解引擎和评测设计 | [架构设计笔记（英文）](docs/architecture.md) |
| 开发浏览器牌桌或发布静态结果 | [Web 开发说明（英文）](web/README.md) |
| 在服务器运行 Frontier12 批量实验 | [服务器运行手册](docs/frontier12-server-run.zh-CN.md) |
| 查看人类游玩改动及测试覆盖 | [易用性审计](docs/human-usability-audit-2026-10-16.md) |

<details>
<summary><strong>运行架构与开发检查</strong></summary>

![AgentBGA 运行架构](docs/images/agentbga-runtime-share-card.png)

规则引擎管理游戏状态并验证行动。智能体接收自己座位的观察；同时选择类游戏使用
冻结观察和统一揭示机制。SQLite 保存已接受的行动，用于确定性回放。
本地网页还提供调试视角，不能作为多用户访问控制边界。

在仓库根目录运行：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
cd web
npm ci
npm run lint
npm test
```

Python 核心没有第三方运行依赖。外部 harness 各自需要安装。
CI 命令见 [PR 检查配置](.github/workflows/pr-checks.yml)。

</details>

AgentBGA 代码采用 MIT 许可证。游戏内容使用机制数据和原创图形表示，
不打包出版商美术或逐字规则文本。内容来源与许可证见[第三方声明](THIRD_PARTY_NOTICES.md)。
