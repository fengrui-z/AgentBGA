# Frontier 12 模型 × Harness 比赛：服务器运行说明

本实验沿用 PR #28 的平衡抽样赛制，而不是枚举 12 个 participant 的全部组合。
在每个 `游戏 × 玩家数` 分层中，每个 participant 恰好出场 12 次，并尽可能均衡
两两相遇次数；座位分配是严格平衡的。

## 规模

| 游戏 | 2 人局 | 3 人局 | 4 人局 | 合计 |
|---|---:|---:|---:|---:|
| 宝石商人 | 72 | 48 | 36 | 156 |
| 七大奇迹 | — | 48 | 36 | 84 |
| 伯明翰 | 72 | 48 | 36 | 156 |
| 总计 | 144 | 144 | 108 | **396** |

每个 participant 总计出场 96 次。任意一对 participant 在固定赛程中共同出现
17–20 次，没有零交手 pair。`workers=16` 表示最多并发运行 16 场比赛；同时决策阶段
每场可能再并发调用 4 个 seat，因此模型调用的理论瞬时峰值约为 64。

比赛配置位于 `examples/frontier12-tournament.json`，运行器位于
`examples/frontier12_tournament.py`。

## 服务器准备

要求 Python 3.11+ 和 Node.js 22+。以下版本与生成这份配置时的本地环境一致；正式结果
应固定版本，不要在同一次比赛中滚动升级：

```console
npm install -g \
  @openai/codex@0.149.0 \
  opencode-ai@1.3.17 \
  @qwen-code/qwen-code@0.22.0 \
  @deepseek-ai/dsh@0.1.0-rc.6

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

在无图形界面的服务器上登录 ChatGPT subscription，并检查状态：

```console
codex login --device-auth
codex login status
```

通过服务器 secret manager 或交互式 shell 注入变量。不要把 key 写入 JSON、仓库或
shell history：

```console
read -rs DASHSCOPE_API_KEY
export DASHSCOPE_API_KEY
echo
read -rs OPENAI_API_KEY
export OPENAI_API_KEY
echo
export DASHSCOPE_KIMI_BASE_URL='https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1'
```

`OPENAI_API_KEY` 只供 `GPT-5.6 Sol × OpenCode` 使用；三个 `Codex` participant 使用
ChatGPT subscription。Kimi 使用 workspace-specific endpoint，因此单独由
`DASHSCOPE_KIMI_BASE_URL` 注入。配置中 Kimi 的 `reasoning_effort` 写成 `none` 是为了
不向 thinking-only 模型发送不存在的 effort 档位；OpenCode provider overlay 仍会明确
发送 `enable_thinking=true`。GLM-5.2 overlay 同时固定发送 `tool_stream=true`。

## 检查与小规模探针

只检查 396 场确定性赛程，不调用模型：

```console
PYTHONPATH=src python3 examples/frontier12_tournament.py schedule
```

检查 API key、Kimi endpoint、四个 CLI 和 Codex 登录：

```console
PYTHONPATH=src python3 examples/frontier12_tournament.py check
```

正式比赛前先运行 4 场覆盖全部 12 个 participant 的真实链路探针：

```console
PYTHONPATH=src python3 examples/frontier12_tournament.py run \
  --out .agentbga/frontier12-probe \
  --workers 4 \
  --probe-all-participants
```

探针全部成功后再开始正式比赛，不要把 probe 目录与正式输出目录混用。

## 正式运行与恢复

推荐在 `tmux` 中运行，并把终端输出保存到独立日志：

```console
tmux new -s frontier12
./examples/run-frontier12-server.sh .agentbga/frontier12-2026 2>&1 | tee frontier12.log
```

SSH 断开不影响 `tmux` 内的进程。若服务器或进程中断，使用同一输出目录再次执行同一
命令。启动脚本会自动添加 `--resume --retry-errors`：已成功场次跳过，失败场次生成新的
attempt SQLite，旧 attempt 保留用于审计。

不要同时启动两个 runner 写入同一个输出目录。

## 输出

```text
.agentbga/frontier12-2026/
├── config.json
├── schedule.json
├── runtime.json
├── matches.jsonl
├── leaderboard.csv
├── summary.json
├── matches/
│   └── match-000001-attempt-01.sqlite3
└── results/
    └── match-000001.json
```

每完成一场都会原子写入独立结果文件；每 8 场及最终结束时重建汇总。排行榜使用 PR #28
相同的顺序无关多人 pairwise Bradley–Terry Elo。失败场次保留并计为 failed exposure，
不进入 Elo 拟合。每场 `result.harness_metrics` 同时保存 provider 报告的 token、缓存、
reasoning token、调用次数和延迟，供后续帕累托图计算成本。
