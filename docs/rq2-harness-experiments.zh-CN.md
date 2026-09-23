# RQ2：Qwen 系列的 harness 配对与历史信息干预

本协议锚定 Qwen3.8 Flash 与 Qwen3.8 Max，比较 OpenCode 和 Qwen Code；GLM 5.2（服务 ID `glm-5.2`）作为可选的异家族复验。提交内容是可运行的实验设施和先导协议，不包含新的模型成绩。不要将随机 smoke 或测试替身的结果写入论文。

## 科学问题与默认规模

RQ2a：同一名义模型在匹配游戏、初始种子、焦点席位与对手配置后，竞争表现是否随 harness 改变？两个模型的 harness 增益是否不同？

RQ2b：从相同局面、相同可见信息开始，向两个 harness 补充同一份历史观察窗口，是否改变它们之间的表现差距？

| 项目 | 冻结设置 |
|---|---|
| 主模型 | Qwen3.8 Flash；Qwen3.8 Max 是同家族复验 |
| 游戏 | Splendor、7 Wonders，均为三人完整规则 |
| 焦点 harness | OpenCode / Qwen Code |
| 两个 anchor | Flash/OpenCode、Max/OpenCode，身份与填座顺序不随实验条件改变 |
| 独立场景 | 每游戏 6 个新种子；焦点席位按 0、1、2 轮换，各出现两次 |
| 默认完整对局 | 2 模型 × 2 harness × 2 游戏 × 6 场景 = **48 局** |
| 顺序 | 冻结 RNG 种子后随机化场景顺序与场景内配置顺序 |
| 记忆 | 每条配置/每次尝试均创建新 match、workspace 和 session；禁止跨场迁移 |
| 运行上限 | 每次焦点/anchor 决策的外部进程 180 秒，绝对 turn_count 上限 500 |
| 失败规则 | 无内部重试、无随机 fallback；明确记录失败，后续重跑单列 |

这是先导规模，**不是功效保证**。用先导的配对增益及交互方差，按预先选择的最小有意义差异或区间精度规划独立确认集；不得重复增样直到显著。两个游戏分别报告，不跨游戏混合原生分数。模型大小不同也不自动识别容量的因果效应。

每个模型的主效应为 `mean(PWS_QwenCode − PWS_OpenCode)`；模型交互是两模型该增益的直接差。PWS 从最终名次逐对计算，平局给半分，不使用 `(3-rank)/2` 处理有平局的结果。

主分析单位为场景。CI 对完整场景内的差值重采样，保留模型/harness 配对。自动报告的是逐游戏、逐比较的探索性 95% percentile 区间，未做多重校正；少量场景不能支持强确认性结论。确认实验须另行冻结主要对比、样本量和多重比较规则。

## 1. 无付费调用地检查计划

在仓库根目录执行（Python 3.11+，macOS/Linux）：

```bash
PYTHONPATH=src python -m agentbga.rq2 plan examples/rq2-qwen-pilot.json --out .agentbga/rq2-smoke
PYTHONPATH=src python -m agentbga.rq2 run .agentbga/rq2-smoke --smoke --max-matches 4
PYTHONPATH=src python -m agentbga.rq2 analyze .agentbga/rq2-smoke
```

安装包后可使用相同参数的 `agentbga-rq2` 命令。`plan` 只校验并冻结配置，绝不调用模型；`run --smoke` 将所有座位替换成随机控制器，输出明确标记 `smoke: true`。smoke 和真实模型运行不能使用同一个输出目录。

`--max-matches` 是本次命令最多启动的**尝试数**，不是 token/USD 预算。默认每次必须明确提供该参数；没有后台调度，也不会自动启动整套付费赛程。

## 2. 完整对局复验

安装 `opencode` 与 `qwen`，在启动进程的环境中配置 `DASHSCOPE_API_KEY`。不要将密钥写入 manifest、命令参数或日志。模板沿用项目中的 DashScope 接入方式；具体账户对三个模型的授权和别名解析仍需在实际运行环境验证。

```bash
PYTHONPATH=src python -m agentbga.rq2 plan examples/rq2-qwen-pilot.json --out .agentbga/rq2-live
PYTHONPATH=src python -m agentbga.rq2 run .agentbga/rq2-live --max-matches 1
# 检查首局实际请求模型、resolved serving/config manifests、usage 和权限后继续：
PYTHONPATH=src python -m agentbga.rq2 run .agentbga/rq2-live --max-matches 47
```

重新执行会跳过已经成功的配置。失败/中断默认也不自动重跑；使用 `--retry-failed` 会创建新的 match/session 和独立 attempt 文件，从原始开局或原检查点重新开始。原失败记录不覆盖，主分析始终使用第一次尝试。这区别于原论文 bridge 中包含恢复后的最终成绩，不能直接混为同一个 estimand。

输出目录有进程锁，拒绝两个 worker 同时执行同一计划。CLI entrypoint 文件哈希、Python 版本及 smoke/live 模式必须与第一次执行一致。全部 AgentBGA Python 源文件的哈希也冻结于计划中；代码改变需要新计划。

这些检查没有证明 provider alias 指向同一权重快照，也没有冻结 CLI 的全部依赖、系统环境或远端服务。保留运行环境/serving manifests，并在模板的 `snapshot` 字段填写可追溯记录标识。模板使用 `unresolved`，因此只能声明 pilot；`stage=confirmatory` 会拒绝这一占位符。填写字符串只是作者声明，不能替代对记录的核验。

180 秒上限限制的是单次外部进程执行，不代表两 CLI 的 token、内部调用次数或实际 reasoning effort 相等。输入历史的干预也会改变 token 消耗。论文应将该实验称为统一墙钟上限下的完整系统比较。需要等 token 实验时，必须另外实施请求层预算控制，不能事后筛选 token 接近的对局。默认保留所有 provider usage、runtime、重试/失败事件；缺失 usage 不视为零。

## 3. 同局面分叉与共同历史窗口

这条轨道是**新会话条件下的历史信息干预**，不是把另一 CLI 的原生会话直接接管。焦点和两个 anchor 都从新 session 续玩，模型、harness、预算在实验条件间匹配。不能将这些结果与原生完整对局合并为同一排行榜。

在看终局成绩前声明来源策略和抽样规则，例如：固定来源为 Flash/OpenCode，对每个声明的新种子只使用一个来源对局；Splendor 抽取焦点玩家第 12 次决策前，7 Wonders 抽取第 7 次决策前。这里是决策序号，并非所有局面都对应同一策略阶段。报告未到达抽样点的来源对局与原因，不根据胜负、动作分歧或效果挑局面。若需要多个阶段，另设实验并按来源对局聚类，当前实现刻意限制为每个 game/seed 一个检查点。

```bash
PYTHONPATH=src python -m agentbga.rq2 checkpoint \
  --db /path/to/source.sqlite3 --match-id SOURCE_MATCH_ID \
  --decision-index 7 --focal-seat 0 --out .agentbga/checkpoints/seven-001.json
```

也可显式指定 `--version`，但应记录预先选择它的规则。导出前重放源对局并核对哈希；导入后从种子及前缀动作重新执行，每一步核对状态哈希。7 Wonders 有尚未揭示的密封选择时拒绝分叉。输出检查点含引擎私有动作与种子，**属于私有研究工件，不是 agent 输入或公开数据**。

复制示例 manifest，为每游戏的六个种子各导出一个检查点，保持焦点席位均衡，再修改：

```json
{
  "study_id": "rq2-qwen-history-pilot",
  "conditions": ["current_only", "seat_history"],
  "history_window": 6,
  "checkpoint_files": ["checkpoints/seven-001.json", "..."]
}
```

上述 JSON 是对原 manifest 的修改示意，路径相对于 manifest 所在目录。需要每个声明游戏、每个种子的完整路径清单，省略号不能直接执行。

两个条件为：

- `current_only`：新 session，只依赖正常接口提供的当前局面；不额外提供源对局历史。
- `seat_history`：其他条件相同，每次焦点决策附加同一份冻结的最近六次历史观察。窗口从引擎 `observe(state, focal_seat)` 重建；不提供他人隐藏手牌、原始引擎状态、他人的 agent 日志或未来状态。明确标注它们是历史状态，当前状态仍应通过 `observe` 获取。

这不是“无记忆 vs 有记忆”：两条件在分叉后都会形成各自的新会话记忆。它检验的是共同历史窗口的额外支持。当前实现提供原始席位观察窗口，没有策略摘要、推荐动作、LLM judge，也不假定 `semantic_compaction` 开关代表某种已验证认知机制。

计划阶段拒绝超过 100,000 UTF-8 字节的历史提示，以避免 CLI 参数长度限制。若触发，需要在冻结计划前统一缩小 `history_window`；不会在某条分支中静默截断历史。

完整分叉先导为 2 模型 × 2 harness × 2 信息条件 × 2 游戏 × 6 场景 = **96 段续局**。可先只保留 Flash，缩为 **48 段**；这不会支持模型间交互结论。所有分支尝试续玩至终局，触发运行上限则保留为未完成；对手重新响应改变后的局面，不能拼接源日志的后续动作。引擎种子相同也不保证不同轨迹中的每个后续随机事件语义对应。

报告每个 harness 的历史增益，以及

`[QC−OC]seat_history − [QC−OC]current_only`。

差距缩小可支持“共同历史可用性改变系统差异”，不能单凭这一实验断言某个 CLI 的内部记忆实现是唯一原因。增加一般提示的长度控制、严格 token 预算或单步后统一续玩策略，可作为后续针对性的鉴别实验；这些未在本 PR 中冒充已实现功能。

## 4. 结果与缺失规则

- `plan.json`：完整解析后的 manifest、精确规则版本、随机化后的逐局赛程、私有检查点、源码及计划哈希。
- `runtime.json`：本地 CLI entrypoint 哈希、Python 版本及预算解释。
- `matches.sqlite3`：原始规则状态、前缀与续局动作、controller calls、harness events。
- `runs/`：按新 match ID 隔离的原生 session 与逐回合 trace。
- `attempts/ROW/0001.json`：第一尝试；`0002.json` 等为后续尝试。运行前即写 `running`，进程中断不会悄悄消失。
- `attempts/ROW/0001.events.jsonl`：运行事件，排除流式原文；provider 错误使用现有 harness 的脱敏记录。
- `summary.json`：首试完成率、逐模型配对差、直接模型交互、历史干预与差中之差。

若任何必要单元缺失，完整案例均值明确标记为 conditional；不生成该比较的采样 CI。另以未知 PWS 的 `[0,1]` 区间计算全部计划场景上的代数界限，包括未启动场景。界限不是置信区间，也不是把失败记零。报告整局终止的失败座位与事件，避免把 anchor 故障称为焦点 agent 可靠性。

7 Wonders 的原生 final ranking 包含计分分项，可进一步描述金币、军事、科学、公会等得分变化；这仍是行为分析线索，不是机制的因果分解。共同历史的精确字节哈希和字符数会随 attempt 保存，方便核对配对的一致性。

## 5. 可选 GLM / 对手复验

GLM 5.2：复制模板，在 `models` 中只保留 `glm-5.2`，按已核验的服务设置明确写出 `reasoning_effort`（现有项目配置使用 `high`）。保持 anchors 不变。只要六个种子和两个游戏不变，完整对局为 24 局，历史轨道为 48 段续局。不要把不同名义 effort 映射解释为相同算力。

Cross-play：可另存 manifest，把两个 anchors 的 `backend` 都改为 `qwen`，保留模型、种子、席位和预算，在新目录运行。这是独立复验，当前分析器不会自动拟合跨计划的对手交互；如需正式对手×焦点 harness 检验，应先冻结跨计划配对及执行顺序。主 PR 优先完成 Qwen 的受控比较和历史干预，不增加第三种未验证主张。

## 验证

```bash
PYTHONPATH=src python -m unittest discover -s tests -p test_rq2.py -v
PYTHONPATH=src python -m unittest discover -s tests -v
```

测试包括精确前缀恢复、密封决策边界、席位可见性、同场景完整交叉设计、平局 PWS、失败/重跑与中断记账、运行锁、源码和配置漂移、真实引擎随机续局，以及无需网络的 harness 注入测试。
