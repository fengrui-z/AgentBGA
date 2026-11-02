# 非 LLM 算法基线

AgentBGA 提供 `greedy`、`heuristic`、`ismcts` 三种本地后端，无需模型、API key 或额外运行时依赖。支持注册表中十款游戏的当前默认规则版本；历史规则版本会在开局时明确报错，不会静默使用不匹配的评估器。RL 不在本次范围内。

## 使用

```bash
./agentbga run --game splendor --players 2 --controllers greedy,heuristic --seed 42 --fallback fail
./agentbga run --game azul --players-config examples/ismcts-vs-random.json --seed 42 --fallback fail
./agentbga doctor --players-config examples/heuristic-vs-random.json
```

`examples/greedy-vs-random.json`、`examples/heuristic-vs-random.json` 和 `examples/ismcts-vs-random.json` 给出了可修改的配置。七大奇迹至少需要三人，请增加第三个玩家。Web 的后端选择器也可选择这三个算法并修改参数。

```json
{
  "name": "ISMCTS 512",
  "backend": "ismcts",
  "algorithm_params": {
    "seed": 7,
    "iterations": 512,
    "max_steps": 24,
    "time_limit_ms": 1000,
    "max_candidates": 32,
    "exploration": 1.4,
    "position_weight": 1.0,
    "opponent_weight": 0.25
  }
}
```

此对象是 `agentbga.players.v1` 配置中 `players` 数组的一项。参数也能放进现有 `experiment` 清单的 `competitors[].player`，复用多 seed、换座和多人赛程。

## 参数语义

| 参数 | 适用算法 | 默认值 | 含义 |
|---|---|---|---|
| `seed` | 全部 | 0 | 算法随机种子，独立于隐藏的对局 seed |
| `max_candidates` | 全部 | 32 | 每个搜索决策节点的候选动作上限；0 表示不裁剪 |
| `time_limit_ms` | 全部 | greedy/heuristic 为 0；ISMCTS 为 1000 | 每次决策的软时间预算；0 表示不限时 |
| `position_weight` | heuristic、ISMCTS | 1.0 | 各游戏长期局面特征的权重 |
| `opponent_weight` | heuristic、ISMCTS | 0.25 | 最强对手可见局面价值的扣减权重 |
| `iterations` | ISMCTS | 128 | 每次决策的模拟迭代上限 |
| `max_steps` | ISMCTS | 24 | 每次模拟最多应用多少个原子玩家决策，包含树搜索及 rollout |
| `exploration` | ISMCTS | 1.4 | UCB 探索系数；0 为利用已估计收益 |

候选动作按动作类型轮流抽取，类型内使用种子随机顺序。设置候选上限会改变算法强度；正式比较须报告这个值。Greedy/heuristic 的单步评估仍可能跨越规则引擎自动完成的多项效果。

时间预算在模拟/候选动作之间检查，不能中断已经开始的单次规则计算；一次复杂规则调用可能使实际耗时超过预算。需要严格复现时设置 `time_limit_ms: 0`，使用固定候选数、迭代数和步数。同一座位、状态版本、算法及算法 seed 会重建相同随机流，暂停恢复无需保留进程内 RNG。

同时决策会作为完整的一组模拟，避免后手看到本轮已提交的密封选择。因此 ISMCTS 的 `max_steps` 必须容纳当前同时决策组；例如三人七大奇迹至少为 3。唯一合法动作直接执行，记录 `automatic`，不消耗搜索迭代。

## 三种算法

- **Greedy**：在一个采样世界中评估每个候选动作的后继状态，选择即时分数及当前资源价值最高者。嵌套阶段使用公开的战术优先级打破平局。各候选使用相同模拟随机数，减少抽牌运气造成的偏差。
- **Heuristic**：沿用相同的单步模拟，加上游戏专属局面特征和对手的可见价值。与 greedy 的主要差异是长期价值评估，而不是增加搜索深度。
- **ISMCTS**：每次迭代重新采样隐藏世界；以根玩家的观测组织信息集树，以语义动作组织边，使用边的可用次数计算 UCB。扩展一个新边后随机 rollout，到达步数预算时用启发式价值评估；终局使用成对排名收益。最终按根边访问次数选择行动。未访问动作的平局使用公开的战术优先级。对手模型为均匀合法动作，不假设对手能看到根玩家私牌。

| 游戏 | 即时价值及主要局面特征 |
|---|---|
| Splendor | 声望、折扣、宝石；距可见目标牌的缺口、贵族进度、保留位占用 |
| Azul | 得分、完整图案线、地板罚分；行列成型潜力 |
| Ark Nova | 魅力、保育、资源、空围栏；声望、大学、合作动物园和行动升级 |
| Brass: Birmingham | VP、现金、收入、产业；连接和未翻面的产业潜力 |
| Castles of Burgundy | 得分、工人、银币、仓储；领地占用、区域完成进度和顺位 |
| Century: Spice Road | 得分、香料价值、商人牌；订单资源缺口和可用手牌 |
| 7 Wonders | 当前计分、金币；生产能力、时代和相邻军事差 |
| Harmonies | 当前地形及动物计分；树干/山地基础和动物卡剩余容量 |
| Wingspan | 鸟、蛋、贮食、塞牌和轮目标分；食物、手牌、栖息地引擎与剩余轮数 |
| Carcassonne | 已得分和剩余米宝；己方占有区域的分数及未闭合边 |

这些是可解释的参考策略，未经过大规模调参，不保证 heuristic 或低预算 ISMCTS 在每款游戏都强于 greedy。Wingspan 的当前价值函数不使用隐藏奖励卡分数。

## 信息边界

权威状态仅由 runner 和受信任的采样适配层持有。算法的模拟世界会重新分配隐藏牌区、对手手牌及秘密目标，替换真实 seed/RNG，并保留当前座位能看到的观测和合法选择。七大奇迹未来时代牌堆及未公开公会集合重新采样，同时支持恢复部分已提交的密封选择。

当前信念模型是**无历史的均匀采样近似**：不利用过去看到的传牌或保留牌记录，也不根据对手策略反推手牌；不是完整贝叶斯后验。模拟只修改副本，所有真实动作继续通过现有 runner、版本检查和 Store 提交。规则版本升级后需要更新适配器并重新验证。

## 记录和验证

玩家配置和 `algorithm_params` 保存在数据库中，恢复时校验一致性。每个决策记录算法版本、实际参数、耗时、候选数、模拟步数、迭代数和节点数；结果新增 `baseline_metrics`，与 LLM token 指标分开。

执行全部算法、全部游戏的完整自对局并校验每步重放哈希：

```bash
python3 examples/validate_baselines.py --out .agentbga/baseline-validation \
  --params '{"max_candidates":8,"time_limit_ms":100}'
```

单独验证一个算法，或对随机对手轮换座位：

```bash
python3 examples/validate_baselines.py --backends ismcts --games splendor azul \
  --seeds 42 73 --opponent random --out .agentbga/ismcts-validation \
  --params '{"iterations":32,"max_steps":12,"time_limit_ms":0,"max_candidates":8}'
```

输出目录保留每场 SQLite 对局和 `validation.json`。脚本遇到失败会记录错误，继续完成其余场次，最终返回非零退出码；不会用 random fallback 隐藏算法错误。已存在报告的目录会拒绝覆盖。

单元测试覆盖十款游戏的观测/合法动作保持、最少/最多人数、可选地图、隐藏牌重分配、种子隔离、搜索树展开、预算、同时决策、参数持久化及恢复。完整自对局验证用于确认运行正确性；棋力比较需要另外冻结参数，使用独立测试 seeds 和换座赛程。
