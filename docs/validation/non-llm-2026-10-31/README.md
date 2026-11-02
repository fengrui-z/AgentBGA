# 非 LLM 基线验证 — 2026-10-31

验证代码版本：`5eb6ae9`。三种算法各运行十款默认规则游戏的一场完整自对局（seed 42），共 30 场；七大奇迹三人，其余两人。所有对局均完成且逐步重放哈希一致，random fallback 为 0。

| 游戏 | Greedy 决策数 | Heuristic 决策数 | ISMCTS 决策数 | 重放 |
|---|---:|---:|---:|---|
| splendor | 70 | 72 | 72 | 通过 |
| azul | 49 | 51 | 50 | 通过 |
| ark_nova | 511 | 350 | 668 | 通过 |
| brass_birmingham | 271 | 282 | 202 | 通过 |
| castles_of_burgundy | 152 | 178 | 179 | 通过 |
| century_spice_road | 132 | 160 | 152 | 通过 |
| seven_wonders | 54 | 55 | 55 | 通过 |
| harmonies | 91 | 91 | 97 | 通过 |
| wingspan | 194 | 230 | 194 | 通过 |
| carcassonne | 142 | 142 | 142 | 通过 |

预算：greedy/heuristic 使用 `max_candidates=8,time_limit_ms=0`；ISMCTS 使用 `max_candidates=8,iterations=8,max_steps=6,time_limit_ms=100`。其余参数使用默认值。时间预算为软限制，因此 ISMCTS 的动作序列可能随机器负载改变。

结果是接入正确性证据，不是棋力评测或统计显著性结论。完整 JSON 包含规则版本、参数、计算量、排名和最终状态哈希。原始 SQLite 对局保留在本机 `/private/tmp/agentbga-final-validation/<backend>/`；不把二进制数据库提交进仓库。

附加检查：

- 最终全量 Python：597 项，1 项跳过，其余通过。
- 新增基线测试：15 项，涵盖各游戏、最少/最多人数、额外设置、信息保持、预算和恢复。
- greedy 分支基线测试：8 项通过；heuristic 分支：9 项通过。
- 前端 TypeScript、build、npm test 均通过；lint 无错误，有 1 条原有图片提示。
- pre-commit 所有检查通过。
- CLI 的 doctor 与 greedy/heuristic 完整对局通过。

复跑方式见 [参数与验证指南](../../non-llm-baselines.zh-CN.md)。
