# Splendor 跨局记忆实验

评估同一 model、harness、provider 和 effort 的两个独立实例对战时，跨局保留
原生 session 的一方，是否比每局重建 session 的一方获得更高胜率。全部双人局，
仅运行 Splendor。该实验估计跨局记忆的整体效果，不单独识别对手建模的因果贡献。

## 默认配置

`examples/splendor-longterm.json` 中有四个独立 cohort：

| 模型 | Harness |
|---|---|
| Qwen3.8 Max | OpenCode |
| Qwen3.8 Max | Qwen Code |
| DeepSeek V4 Flash 0731 | OpenCode |
| DeepSeek V4 Flash 0731 | DSh |

每个 cohort 内双方共用一份 player 配置，不是不同模型互打。全部固定为 DashScope
`https://dashscope.aliyuncs.com/compatible-mode/v1`，凭据通过 `DASHSCOPE_API_KEY`
提供；请求 `qwen3.8-max` 或 `deepseek-v4-flash-0731`，effort 为 `max`。
需要减少到三个 cohort 时，在生成新计划前从 agents 中删去一个。已有运行不可改配置。

| 阶段 | 每 cohort | 总场数 | 独立 series |
|---|---|---:|---:|
| pilot | 1 × 10 局 | 40 | 4 |
| main | 3 × 20 局 | 240 | 12 |

pilot 与 main 使用不相交的 seed 区间、独立输出目录及记忆 namespace。正式阶段
第 10 和第 20 局为同一轨迹的检查点，不是两个独立样本。pilot 结果用于判断链路、
耗时与方差；默认三个独立重复只提供初步证据，不保证足够统计精度。

## 记忆处理与公平性

- 双方匿名显示为 Player A / Player B，不在指令中告知哪方为 treatment。
  persistent 身份在 replicate 间尽量平衡，三次重复为 2:1；每条 series 随机确定
  persistent 的初始座位，之后每局换座位。身份与记忆所有权不跟随座位改变。
- 两方在单局内都保留正常会话和笔记。Persistent 的原生 session、native storage
  和策略笔记随 series 保留；fresh 每局获得全新 match ID 和独立 workspace。
  Fresh 的旧目录保留用于审计，但新实例不会加载它。
- 每个 replicate 的 persistent 也从空记忆开始。不同 cohort 和不同实验运行
  使用不同 namespace。不能把 pilot 的 session 接到 main。
- 每局第一次模型决策明确指出“新棋盘、新 action IDs、自己的稳定身份和当前座位”，
  避免沿用旧棋盘。规则固定为 `classic-1.0`，每局使用新的环境 seed。
- 两方均接收自己的合法可见终局观察、公开排名与比分，随后在各自原生 session 中
  执行同一段局后 review 指令，区分一般经验和有不确定性的对手倾向，并允许更新
  自己的笔记。Fresh 的这次 review 不会带到下局。
- Review 的游戏工具仍然受 seat scope 限制；legal actions 为空，旧 action ID
  无法提交。不会把对手的私有卡牌、笔记或推理传给另一方。
- 每次决策及 review 默认 600 秒超时，单局最多 250 个引擎 turn。Runner 重试为 0，
  不随机代打、不自动重跑失败场；native harness 自身的纠错机制仍保留。
- Review 的“200 words”是共同提示约束，不是强制 token 限额。Persistent 更长的
  context 和压缩成本属于这项总效果实验的一部分，并非等 token 预算实验。

## 命令

运行环境为 Python 3.11+、macOS/Linux，以及对应的 OpenCode、Qwen Code、DSh CLI。
先离线检查并导出赛程，以下命令不调用模型，也不要求 API key：

```sh
python3 examples/splendor_longterm.py schedule --stage pilot \
  --out .agentbga/longterm-plans/pilot.json
python3 examples/splendor_longterm.py schedule --stage main \
  --out .agentbga/longterm-plans/main.json
```

正式启动需要环境中已有 `DASHSCOPE_API_KEY`，并检查日期模型和 effort 在该账号上
可用。下面是执行命令；离线导出并未实际执行这些比赛：

```sh
python3 examples/splendor_longterm.py run --stage pilot \
  --out .agentbga/splendor-longterm-pilot
```

可以在完整比赛边界暂停，比如先完成两局及双方 review，再继续同一学习轨迹：

```sh
python3 examples/splendor_longterm.py run --stage pilot \
  --out .agentbga/splendor-longterm-probe --limit-matches 2
python3 examples/splendor_longterm.py run --stage pilot \
  --out .agentbga/splendor-longterm-probe --resume
```

`--limit-matches` 是本次额外执行的总场数，不是每个 cohort 的场数。
当前 runner 串行完成每个 cohort 的 series；同一 series 绝不并行。
文件锁阻止同一目录被两个 runner 同时写入。Main 必须使用新目录：

```sh
python3 examples/splendor_longterm.py run --stage main \
  --out .agentbga/splendor-longterm-main
```

## 检查点与中断语义

每次开始比赛前把 checkpoint 标为 running；只有比赛正常终局、双方 review 成功、
原生 session 身份和记忆指纹检查通过，才写入 ready 检查点。Resume 保留 run_id、
series 所有权和原生 session，跳过已经确认的结果；检查代码、CLI 版本、配置、
赛程、结果摘要及记忆文件指纹是否与检查点一致。

**只支持已确认的局间检查点恢复，不支持在未知状态的模型调用中途自动恢复。**
若中途 Ctrl-C、进程崩溃、模型失败或 review 失败，原生 memory 可能已改变，状态
保留为 running/failed 并拒绝自动重放。不要手改 checkpoint 绕过检查；保留失败
轨迹，并按预先约定的失败处理方案决定后续独立重复，不能挑选成功重跑替换原样本。
若要有计划地暂停，请使用 `--limit-matches`，不要在模型执行期间强行终止。

## 输出与分析

```text
plan.json          冻结配置、阶段、赛程、代码摘要、CLI 路径和版本
checkpoint.json    run_id、下一 ordinal、原生记忆指纹、结果摘要、执行状态
matches/*.sqlite3  每场引擎状态、动作、controller metadata 和工具审计
results/*.json     每场结果、终局状态、review 状态、session ID、局前后记忆指纹
feedback/*.json    局后公开反馈，以及各自局后策略笔记快照
runtime/           隔离的原生 session/workspace 和逐回合、局后 review traces
trajectory.csv     每局胜负（平局 0.5）、比分差、game_index、series、seed、状态
summary.json       每条 series 的 1–10、11–20 局窗口与缺失结果范围
```

记忆指纹覆盖原生 session storage 和策略笔记，不跟随符号链接，也不复制凭据。
它用于检测存储是否丢失／变化，不能证明模型在推理中实际利用了某条记忆；需要结合
trace、笔记快照、压缩事件和策略变化分析。运行目录含原始 agent traces 与本地
native runtime，只在挑选、检查过的结果上做共享，不将整个 runtime 直接发布。

主要读数是每条独立 main series 的第 11–20 局 persistent 胜率，平局记 0.5。
保留全 20 局结果、前半程结果、比分差、正常终局率和 review 失败率。结果统计单位
为独立 series；不同 cohort 使用公共 seed 序列，联合分析时还要保留这个配对结构。
不要对 20 个连续游戏做普通 IID bootstrap，不把同条轨迹的 10/20 局检查点重复计数。

自动 summary 只输出描述性结果，不声称统计显著。Completed win score 明确只覆盖
正常终局；同时列出计划场数、已报告场数、终局数和协议失败数，并输出把未观测结局
分别视为全负／全胜时的胜率范围。终局成功但 review 失败时，保留该局竞技结果，
停止后续轨迹，并将 protocol_complete_window 标为 false。

成本保留 provider/harness 原始 usage 及 review 的独立 usage；部分 CLI 的 token
统计可能是跨 session 累计，不能直接相加解释为逐局新增费用。未校准前不产出等预算
结论。原生 context compaction 可能丢掉早期历史，同一 session ID 不等于无限记忆。

后续若要识别对手建模的独立收益，应另加可审计的“仅一般战略记忆”与“一般记忆＋
对手画像”消融，或配对的新对手迁移测试。当前实验不改变模型权重，也没有该机制消融。
