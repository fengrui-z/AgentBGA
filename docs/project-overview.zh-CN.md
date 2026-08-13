# AgentBGA：项目现状与研究目标

## 项目简介

AgentBGA 是一个面向大语言模型智能体的桌游竞技与评测框架。项目希望用长时程、多玩家策略桌游，研究模型能否持续规划、理解对手、管理资源，并在几十个回合后仍保持连贯的策略。

AgentBGA 的评测对象不仅是语言模型本身，而是完整的智能体组合：

```text
Agent = Model × Harness × Memory × Prompt × Tool Interface × Compute Budget
```

这里的 Harness 指运行和组织模型的智能体框架，例如 Claude Code、Codex、OpenCode 和 Pi。相同模型放入不同 Harness 后，可能表现出不同的工具使用方式、记忆能力、成本、可靠性和游戏策略。AgentBGA 希望把这些因素拆开并进行可复现的比较。

## 当前实现

项目目前已经实现一个可以运行的《璀璨宝石》基础版规则环境，支持 2–4 名玩家。

### 游戏与对局

- 支持 Agent vs Agent、Agent vs Human 和 Human vs Human。
- 支持公开市场、发展牌购买与预留、宝石和黄金、永久折扣、贵族及终局结算。
- 每个座位只能看到符合规则的信息；对手预留牌的数量公开，具体内容隐藏。
- 所有合法动作都有与当前状态绑定的 action ID，过期或非法动作无法改变游戏状态。
- 随机设置由 seed 控制，对局可以验证和重放。
- 玩家顺序可在前端快速调整或随机排列。

### 模型和 Harness

直接 API 后端目前支持：

- OpenAI-compatible Chat Completions
- Anthropic Messages
- Google Gemini
- 随机策略和人类玩家

第三方 Harness 目前支持：

- Claude Code
- Codex
- OpenCode
- Pi

每个座位可以独立配置 Harness、模型名称、API endpoint 和 API key，因此可以进行诸如以下实验：

```text
OpenCode + DeepSeek
vs
Codex + DeepSeek
```

也可以固定 Harness、替换模型，或者构造完整的 Model × Harness 交叉评测。

每个 Harness 座位拥有独立的工作目录和跨回合 session。模型通过三个统一工具参与游戏：

```text
observe()              查看本座位当前可见状态
legal_actions()        获取当前全部合法动作
submit_action(id)      提交且仅提交一个合法动作
```

Harness 默认允许最多 600 秒完成一次决策，并统一请求最高思考强度。最终实际支持程度仍取决于模型服务是否兼容对应的 reasoning 参数和 API 协议。

### CLI 与前端

核心功能都通过机器可读的 CLI 暴露，可被脚本、模型工具或 MCP 客户端调用，包括：

```text
agentbga match create
agentbga match observe
agentbga match legal-actions
agentbga match act
agentbga match status
agentbga match events
agentbga match harness-events
agentbga match replay
agentbga match verify
agentbga run
agentbga web
```

本地 Web 前端支持：

- 配置 2–4 个玩家；
- 为每个玩家填写 Harness、endpoint、API key 和模型名；
- 选择常用国内模型服务预设；
- 实时查看市场、宝石、发展牌、预留牌和分数；
- 实时查看模型公开输出、思考流、错误和工具调用；
- 在人类回合直接选择合法动作；
- 在回合边界安全暂停和继续比赛。

### 日志与复现

每场比赛使用唯一的 `match_id`，并在 SQLite 中保存：

- 玩家、模型和 Harness 配置（不保存 API key）；
- 每个被接受的游戏动作和领域事件；
- 每次模型调用的耗时、session、fallback 和错误摘要；
- Harness 启动、结束以及工具调用审计；
- 当前状态、状态版本和状态哈希。

完整动作历史可以重放并验证最终状态。当前模型逐字输出和思考流只用于实时前端展示，尚未作为研究数据完整持久化。

## 研究目标

AgentBGA 的长期目标不是制作一个普通的在线桌游平台，而是把复杂策略桌游建设成研究长时程智能体的可控实验环境。

核心研究问题包括：

1. 固定模型时，更换 Harness 会在多大程度上改变胜率、成本和策略行为？
2. 固定 Harness 时，不同模型的相对排名是否稳定？
3. Model × Harness 是否存在显著交互，甚至造成模型排名反转？
4. 智能体能否跨几十个回合保持目标、追踪对手并在计划受阻后重新规划？
5. 完整对话、结构化记忆、摘要和无记忆设置分别如何影响长程表现？
6. 更高推理预算带来的收益是否足以抵消 token、费用和延迟？

项目计划从单纯胜率扩展到更细致的能力测量，例如：

- 非法动作率、重试率和工具调用可靠性；
- 资源浪费、折扣投资回报和终局时机；
- 目标持续性与重新规划速度；
- 对手意图识别和阻断质量；
- 每个有效动作的 token、费用和延迟；
- 在固定预算下的胜率—成本—延迟 Pareto 前沿。

## 下一阶段

近期最重要的工作是把当前原型提升为论文级评测平台：

- 增加完全可控的 Minimal Harness，作为第三方 Harness 的实验对照组；
- 持久化规范化的请求、响应、token、费用、延迟和 Harness 版本；
- 改进第三方 Harness 错误捕获，区分模型失败、API 兼容问题和工具失败；
- 使用容器或更强沙箱隔离全局配置、提示词、技能和用户文件；
- 为不同模型服务增加能力协商，避免发送不支持的 reasoning 参数；
- 正式评测时关闭随机 fallback，避免把 API 故障误计为模型行为；
- 建立随机、启发式、搜索、强化学习和人类基线；
- 进行多 seed、座位交换和对手轮换的大规模比赛；
- 从完整对局抽取关键局面，建立可重复的离线战略诊断集；
- 继续加入具有空间规划、随机性、隐藏信息和复杂引擎构筑机制的原创游戏环境。

最终希望形成一个开放、可复现的长时程多智能体研究平台，并系统回答：在真实的连续决策环境中，智能体能力究竟来自模型、Harness，还是二者的组合。

## 项目链接

- GitHub：<https://github.com/fengrui-z/AgentBGA>
- 详细架构：[architecture.md](architecture.md)
- 使用与运行方式：[README.md](../README.md)
