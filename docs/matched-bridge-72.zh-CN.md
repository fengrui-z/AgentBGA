# Qwen3.8 Max / DeepSeek V4 Flash 0731：72 场 matched harness bridge

本方案是新增的独立补赛批次，不追加到旧 Frontier12 身份或成本汇总中。
本次交付为实验设置与离线赛程导出，不会调用模型或启动比赛。
仅评估 Splendor 和 7 Wonders，将运行预算集中在这两个游戏的配对比较。

## 设计与规模

| Focal 模型 | 对照 arm | 处理 arm | 每个游戏 paired blocks | 两游戏场数 |
|---|---|---|---:|---:|
| `qwen3.8-max` | OpenCode | Qwen Code | 9 | 36 |
| `deepseek-v4-flash-0731` | OpenCode | DSh | 9 | 36 |
| 合计 | | | | **72** |

游戏为 Splendor、7 Wonders，全部 3 人局；每游戏 36 场。
规模为 `2 models × 2 games × 9 blocks × 2 harnesses`。

两个固定 anchor 为 Qwen3.8 Max / OpenCode 与 DeepSeek V4 Flash 0731 / OpenCode。
二者在每场均出场，使用独立的 anchor participant ID；它们与 focal 即使模型相同，
也不共享会话。没有 series memory。每场都是新比赛，anchor 根据本局状态决策，
不重放另一场的动作。结论针对这个固定对手组合，不外推到所有对手池。

## 路由与协议

- 全部 focal 和 anchor 使用 `https://dashscope.aliyuncs.com/compatible-mode/v1`，
  API key 仅通过 `DASHSCOPE_API_KEY` 提供。
- DeepSeek 固定请求 `deepseek-v4-flash-0731`，不改用 `deepseek-v4-flash` alias，
  不回退到 DeepSeek 官方 API 或 OpenRouter。
- Qwen 固定请求 `qwen3.8-max`。该 ID 未包含日期，不能据此宣称 provider 内部快照
  已经不可变；正式运行应记录 provider 返回的模型标识并缩短批次时间跨度。
- 配置统一请求 `reasoning_effort=max`。这不是相等的实际 thinking tokens 或费用。
  不同 CLI 的请求转换仍需在独立链路探针中核对，静态配置校验不证明远端接受该参数。
- runner 层 `retries=0`、`fallback=fail`。保留各 harness 自身的会话、纠错和
  continuation 行为作为被比较系统的一部分；不能解释为“无恢复”实验。
- 沿用当前 HarnessAgent 每次 choose 的默认 600 秒超时、相同游戏 MCP 接口与权限策略。
  CLI 内部 prompt、上下文管理和重试实现可以不同，属于 harness 包的总效果。
  当前接口没有跨 CLI 统一的硬 token／美元预算，不能将结果称为等 token 对比。
- 游戏规则固定为 `classic-1.0`、`second-edition-base-1.0`。
  正式运行同时保存 Git commit 和 Qwen Code、OpenCode、DSh 的版本，不在批次中升级。

## 配对与顺序

每游戏有 9 个公共 scenario，总计 18 个。每个 scenario 的环境 seed、focal seat、
两个 anchor 的座位与配置，在两个模型间也完全相同。每个 scenario 产生四场比赛：
Qwen 两个 harness 与 DeepSeek 两个 harness；形成两个 pair，总计 36 pairs。

每模型／游戏的 focal seat 0、1、2 各有 3 blocks，每 block 两场。每轮座位轮换后
翻转 anchor 的环形方向；由于每座位只有三个 blocks，两个方向是 2:1，不能称为
左右邻居方向完全平衡。每对内部、跨模型相同 scenario 的座位则完全匹配。

`base_seed=2026091401` 控制环境；`order_seed=2026091402` 控制运行顺序。
环境 seed 不等于 LLM sampling seed。每格九对中，两个 arm 先运行的次数为 4/5；
pair 顺序随机打散，pair 内两场相邻。按导出的顺序执行，默认一场接一场；如另接并发
调度器，必须以 pair 为队列单位，并让 pair 内串行，避免先跑完一种 harness。

## 离线检查与导出

从仓库根目录运行，不需要 API key：

```sh
python3 examples/matched_harness_bridge.py
python3 examples/matched_harness_bridge.py --out .agentbga/matched-bridge-72-plan
```

输出目录必须为空，避免覆盖已冻结的计划：

```text
config.json       原始配置
summary.json      72 场、36 pairs、18 scenarios、每格座位和顺序平衡、SHA256
schedule.json     每场完整配置，含 pair_id / scenario_id / focal_seat / arm
schedule.csv      可直接查看的逐场座位表
players/*.json    72 份兼容现有 agentbga run 的玩家配置
commands.json     顺序排列的 CLI argv、工作目录、环境设置及输出路径
matches/          为每场独立 SQLite 预留
results/          为 stdout/stderr 预留
```

配置不是 `balanced-tournament.v1`，不要交给 `frontier12_tournament.py`，否则不能
保留这套配对设计。导出器只生成计划与命令，**没有批量执行或自动恢复功能**。
`commands.json` 中每条 argv 可由现有 CLI 执行，PYTHONPATH 和 cwd 一并提供；
执行时需要保存退出码、开始／结束时间、stdout 和 stderr，并关联 ordinal/pair_id。
不得将“产生了 stdout”当成比赛成功，也不得把失败场静默重跑直到成功。

正式比赛前，在独立目录做链路探针，覆盖 Qwen/OpenCode、Qwen/Qwen Code、
DeepSeek/OpenCode、DeepSeek/DSh 四种 focal 配置。探针不能混入这 72 场确认样本。
若日期模型在 DashScope 不可用，停止该配置，修改实验 ID 后再生成新计划，禁止
在旧身份下切换路由。离线导出不验证账号额度、远端模型可用性或 CLI 的实际请求参数。

## 分析约定

主 contrast 方向固定：

- Qwen：`PWS(Qwen Code) − PWS(OpenCode)`。
- DeepSeek：`PWS(DSh) − PWS(OpenCode)`。

三人正常终局时，focal PWS 是对两位 anchor 分别计胜 1、平 0.5、负 0 后的均值，
不是只记是否第一。`contrast_sign` 对对照 arm 为 -1、处理 arm 为 +1；不要用
执行先后决定差值符号。每个 pair 一条差值，每格 9 条，不将 turn/tool call 或
同局的两位对手视为独立样本。

同时报告全体已分配比赛的正常终局率、失败责任及 continuation 情况。
任意一臂未正常终局时，该 pair 的终局 PWS 差值记为缺失，不能静默删除后声称
总体因果提升；另列有效配对数、失败模式并做预先确定的缺失结果敏感性分析。
双臂完成子集的 PWS 仅是条件性结果。正常终局判断需核对引擎状态，不能只看进程退出码。

OpenCode 两个 focal 模型共享 18 个 scenario，可另做同 harness 的模型差值；
Qwen Code 与 DSh 不是同一种处理，不能把两组效果直接合称统一的 H1 主效应。
游戏交互分别对每个模型计算；跨模型联合重采样保留整个 scenario 的四场结构。
9 blocks 是固定预算下的初始精度，报告区间而不预设显著或排序反转必然成立。

成本只保留新批次的原始 telemetry、来源和缺失标记。此次设置没有修复旧成本数据，
也没有证明不同 harness 的 token 计量已经可比；在校准完成前不合并成本排行榜。
