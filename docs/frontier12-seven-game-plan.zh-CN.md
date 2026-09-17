# Frontier12：七个新游戏的 336 场覆盖计划

状态：**仅计划，尚未启动模型比赛**。本轮在包含卡卡颂的代码上另开分支，
建立独立批次 `frontier12-seven-games-20260917-b01`。

首阶段目标是补齐环境覆盖：12 个 participant，每个新游戏每人出场 12 次，
统一三人局。因此每游戏 `12 × 12 ÷ 3 = 48` 场，七游戏共 **336 场**，
共 1,008 个 participant-session；每人合计 84 次出场。
这些数字是覆盖预算，**不保证排名精度、置信区间宽度或统计功效**。

## 1. 游戏范围与固定条件

| 游戏 | game ID | 首阶段场数 | 每人出场 | 每人座位 0 / 1 / 2 |
|---|---|---:|---:|---:|
| Azul / 花砖物语 | `azul` | 48 | 12 | 4 / 4 / 4 |
| Ark Nova / 方舟动物园 | `ark_nova` | 48 | 12 | 4 / 4 / 4 |
| The Castles of Burgundy / 勃艮第城堡 | `castles_of_burgundy` | 48 | 12 | 4 / 4 / 4 |
| Century: Spice Road / 香料之路 | `century_spice_road` | 48 | 12 | 4 / 4 / 4 |
| Harmonies / 自然和弦 | `harmonies` | 48 | 12 | 4 / 4 / 4 |
| Wingspan / 展翅翱翔 | `wingspan` | 48 | 12 | 4 / 4 / 4 |
| Carcassonne / 卡卡颂 | `carcassonne` | 48 | 12 | 4 / 4 / 4 |
| **合计** | **7 个游戏** | **336** | **84** | **28 / 28 / 28** |

既有 Splendor、7 Wonders、Brass: Birmingham 不计入这 336 场。
Ark Nova 的历史规则版本不另算一个游戏；Catan 不属于本次范围。

使用当前引擎默认基础规则，不引入扩展或变体：Ark Nova 使用 Map 0；
Harmonies 使用 A 板且关闭 Nature's Spirits；Wingspan 使用默认绿色目标板；
卡卡颂使用包含农夫的 72 张基础板块。具体 rules version 和 Ark Nova 内容散列
记录在 [赛程报告](plans/frontier12-seven-games/schedule-report.json)。
执行前须再次核对默认设置；如默认值改变，重新冻结计划与批次。

## 2. 12 个 participant

以已发布的 `web/public/results/frontier12-2026-v2.json` 中实际参赛名单为基准。
它与早期 `frontier12-tournament.json` 不同：使用 Pro 0813，并以
Qwen3.7 Plus × OpenCode 替代 DeepSeek Flash × OpenCode。

| participant ID | 模型请求值 | Harness | reasoning effort 草案 |
|---|---|---|---|
| `gpt56-sol-codex` | `gpt-5.6-sol` | Codex | xhigh |
| `gpt56-terra-codex` | `gpt-5.6-terra` | Codex | xhigh |
| `gpt56-luna-codex` | `gpt-5.6-luna` | Codex | xhigh |
| `gpt56-sol-opencode` | `gpt-5.6-sol` | OpenCode | xhigh |
| `qwen38-max-qwen` | `qwen3.8-max` | Qwen Code | max |
| `qwen38-max-opencode` | `qwen3.8-max` | OpenCode | max |
| `glm52-opencode` | `glm-5.2` | OpenCode | high |
| `deepseek-v4-pro-0813-dsh` | `deepseek-v4-pro-0813` | DSh | max |
| `deepseek-v4-pro-0813-opencode` | `deepseek-v4-pro-0813` | OpenCode | max |
| `deepseek-v4-flash-0731-dsh` | `deepseek-v4-flash` | DSh | max |
| `qwen37-plus-opencode` | `qwen3.7-plus` | OpenCode | max |
| `kimi-k27-code-opencode` | `kimi-k2.7-code` | OpenCode | none / thinking-only |

participant 是“模型 × harness × 执行配置”，不是裸模型。以上请求值、effort 和
endpoint 沿用仓库中可核对的配置作为开赛草案，不代表已经验证当前服务可用性。
Flash 的 ID 保留历史 `0731` 标签，但请求仍是可变别名：**本轮实际 revision 未确认**。
其他无不可变 snapshot 的模型同样标记 unknown，不能由显示名推断版本一致。
Kimi 的 `none` 沿用现有适配器约定，实际 thinking 行为仍须锁定和记录。

## 3. 可复现赛程

- [运行配置](../examples/frontier12-seven-games.json)：首阶段 seed 为 `20260920`。
- [完整 336 场 JSON](plans/frontier12-seven-games/schedule.json)：每场的游戏、seed、座位和序号。
- [完整 CSV](plans/frontier12-seven-games/schedule.csv)：便于人工审阅。
- [赛程报告](plans/frontier12-seven-games/schedule-report.json)：逐游戏的出场、座位、对手和规则版本。
- [计划元数据](plans/frontier12-seven-games/plan.json)：配置与赛程散列、追加规则和共同游戏预算。

直接复用现有确定性 balanced scheduler：严格平衡每人出场和座位，启发式均衡对手，
最后打乱七游戏的运行顺序，避免把一个游戏与单一时间段完全绑定。
在读取任何比赛结果前，从 seed 20260917 起选择首个七游戏均无零交手 pair 的赛程，
最终 seed 为 20260920。每游戏任意两人相遇 1–4 次；配对次数不严格相等，详见报告。
三人局每场产生的三对比较相互依赖，不能把它们当成三个独立样本。

默认 `workers=4`，最多并发四场，保守上界为 12 个活跃 seat session。
这是初始运行设置，不是速度或价格估计。预算以有效逻辑场次计；失败 attempt 的
token 和费用另记。没有新游戏真实轨迹前，不用旧游戏平均耗时推算确定完成时间。

## 4. 开赛前冻结与执行顺序

1. 在计划外做引擎与 harness 链路验证，覆盖七游戏及全部 12 个 participant。
   探针单独目录、单独 seed，不能挑选成功探针回填正式样本。先用实际 token/耗时
   估计运行成本，再冻结正式并发数和预算。
2. 冻结实际模型 revision 及证据、规范化 endpoint、CLI 版本与包/二进制散列、
   Python/Node 版本、代码 commit 与 dirty 文件散列、游戏规则和内容散列、prompt/tool
   策略、reasoning 参数、auth/wire API、超时、重试、fallback、并发数及开始 UTC。
   密钥只留在 secret manager；清单不含密钥。
3. 验证配置、赛程及冻结清单后开始首批 336 场。每个逻辑 ordinal 使用预定 roster、
   座位和 seed，结果与 SQLite attempt 独立保存。
4. `fallback=fail`，不把随机动作接管伪装成正常模型表现。失败保留原始 attempt，
   同配置恢复时复用原 ordinal/seed/座位；记录重试成功与首次成功的区别。
   重试不得覆盖已经成功的比赛，也不能通过更换对手/seed 消除失败。
5. 每个游戏的 48 场全部结案后进行一次诊断。未完成、失败或排名缺失先做质量调查，
   不以扩样替代故障修复；修复若改变执行设置，则开启新批次。

赛程验证命令（不调用模型）：

```console
PYTHONPATH=src python3 examples/frontier12_tournament.py schedule \
  --config examples/frontier12-seven-games.json
```

运行环境检查（检查凭据和 CLI，不启动比赛）：

```console
PYTHONPATH=src python3 examples/frontier12_tournament.py check \
  --config examples/frontier12-seven-games.json
```

完成冻结后，未来正式启动命令为：

```console
PYTHONPATH=src python3 examples/frontier12_tournament.py run \
  --config examples/frontier12-seven-games.json \
  --out .agentbga/frontier12-seven-games-20260917-b01
```

同一冻结环境恢复时添加 `--resume --retry-errors`。
不要直接使用现有 `run-frontier12-server.sh`：它固定旧三游戏配置与 16 workers。

**现有 runner 的限制：**它检查恢复时 config/schedule 是否一致，但不强制比较实际
模型 revision、CLI、代码、endpoint 或默认规则变化，且会重写 `runtime.json`。
本次交付是计划，没有实现这些额外防护。正式执行前必须保存独立的冻结清单并在
每次启动/恢复前核对，或先补齐相应强制检查。`plan.json` 也不是 execution lock。

## 5. 预先规定的追加批次协议

以下作为开赛前冻结的协议草案；阈值不得在看到结果后为追求某个排名而修改。

- 单位：**整个游戏**。每次给全部 12 人各加 12 次出场，即该游戏增加 48 场，
  每人每个座位再增加 4 次。不得只给领先者、落后者或特定对手补样本。
- 检查点：每游戏每人累计 **12、24、36、48** 次有效出场，只在完整批次后检查。
- 诊断指标：每人每场对另外两人的平均 pairwise score，胜 1、平 0.5、负 0；
  再对该人的比赛取平均。这样每场对该人只贡献一个 `[0,1]` 的观测。
- 区间：按完整比赛联合重采样所有座位，10,000 次 percentile bootstrap，
  nominal 95% 区间，随机种子 `20260917`。不能把同场 pair 拆成独立样本。
  某次重采样缺少某个 participant 时重抽该次，记录重抽数量。
- 追加条件：任何 participant 的区间**全宽大于 0.30**，或区间不可用/退化，
  就为该游戏安排下一批 48 场。少于两种观测分数视为退化，零宽区间不能自动停止。
- 停止条件：全部 12 人均达到上述诊断门槛，或达到每人 48 次出场的上限。
  达上限仍过宽、退化或受失败影响时，明确报告“精度未达标/未解决”。

这些 bootstrap 区间是**探索性的精度诊断**。小样本、对手异质性、固定配对和按宽度
停止都会影响解释；这里没有声称序贯 95% 覆盖、同时排名显著性或检验功效。
如要做确认性的“模型 A 优于 B”声明，应另行预注册比较、最小效应、样本量与
多重/序贯校正，使用独立确认数据。

每个追加批次保留独立 ID、config、schedule、manifest 与原始结果；其 base seed
为 `20260920 + 10000000 × (批次号 - 1)`，并核对不与已有 `(game, seed)` 重复。
只列需要追加的游戏，原始赛程永不重写；生成后复核出场与座位平衡。
仅同一冻结 cohort 的追加批次可联合诊断。

预算上限：每游戏最多 `48 × 4 = 192` 场；七游戏最坏共 **1,344 场**，
其中首批 **336**，后续最多 **1,008**。这是追加上限方案，**本次不启动或自动授权
这些追加比赛**。每轮列出触发游戏、区间和新增场数后再安排执行。

## 6. 新批次与历史结果的关系

本轮默认独立 cohort。所有结果身份必须包含 cohort/batch ID 和 participant ID；
模型别名相同或 participant ID 相同，都不能自动将旧新样本合并。

实际模型版本、harness、prompt/tool policy、参数、endpoint、规则/内容或执行设置
发生变化时，新建 cohort，停止向旧批次补入新设置下的结果。
无法核实历史 revision/设置，也按不可直接合并处理。服务端不公开版本时明确记录
unknown 和运行时间窗，不能用相同 alias 充当版本证据。

若需要把本轮扩展成当前设置下的十游戏综合结果，预先指定共同游戏为
Splendor、7 Wonders、Brass: Birmingham，均用三人局、同一 12 人、每人 12 次，
即 **额外 144 场**。这样新 cohort 的十游戏首轮共 **480 场**。
这些共同游戏不计入当前 336 场，也不是自动触发的任务。

共同游戏重跑用于衡量跨期差异、在新设置下补齐覆盖；它**不能证明旧新结果等价**，
不能据此把不同版本拼成一个不带批次标签的排行榜。历史 2/4 人局也不能直接视为
本轮三人局的补样。若版本变化发生在本轮中途，新 cohort 需要重新积累其目标
游戏的数据，而不只是补跑三个共同游戏。

## 7. 首轮结果应如何呈现

交付 participant × game 的覆盖矩阵、逐游戏 PWS 与诊断区间、逐游戏 Bradley–Terry
评分、座位/对手暴露、成功与失败 attempt、首次成功率、token/缓存/reasoning token、
延迟和成本。失败不能当成缺失的零成本，也不能悄悄从可靠性分母中去掉。

综合表现以同 cohort 下七游戏等权宏平均 PWS 为主，同时列出各游戏结果与有效样本数。
追加批次数不同不能让某个游戏因场数更多而主导综合分数；存在未解决失败时，
条件于成功场次的表现必须明确标注，不能声称完整、无偏的全体表现。
现有 runner 的 pooled Elo 可作为原始辅助输出，不应在扩样不均衡后直接当作
等游戏权重的综合结论。

围绕已有配对开展有针对性的后续研究：GPT Sol 的 Codex/OpenCode、Qwen Max 的
Qwen Code/OpenCode、DeepSeek Pro 的 DSh/OpenCode。先展示逐游戏差异，再设计
固定模型 revision、共同 seeds、座位和执行设置的配对 harness 对照；不能把当前
混合比赛直接解释为某个内部模块的因果效果。工具过滤、记忆等消融属于独立实验，
另定预算和批次，不能占用这 336 场基础覆盖样本。

这种“多游戏结果 + 针对性模块研究”的组织方式参考
[Orak](https://arxiv.org/abs/2506.03610)，其多游戏与 agentic module 研究思路用于
指导报告和后续实验设计；这里的 336 场预算与追加阈值是本项目自己的协议。
