# Qwen × Codex 小规模并发 Pilot

这个 pilot 用 6 个 `Model × Harness` 条件，在宝石商人、七大奇迹和伯明翰中运行
33 场平衡比赛。每个条件在每个 `游戏 × 人数` 分层中恰好出场 2 次，默认同时运行
10 场比赛。

## 实验矩阵

| 模型 | Harness | 认证 |
|---|---|---|
| Qwen 3.8 Max | Pi Agent | `DASHSCOPE_API_KEY` |
| Qwen 3.7 Plus | Pi Agent | `DASHSCOPE_API_KEY` |
| Qwen 3.8 27B | Pi Agent | `DASHSCOPE_API_KEY` |
| Qwen 3.8 Max | Claude Code | `DASHSCOPE_API_KEY` |
| GPT-5.6 Sol | Codex | ChatGPT subscription |
| GPT-5.6 Luna | Codex | ChatGPT subscription |

这样同时得到三类比较：固定 Pi 比较三个 Qwen 模型、固定 Qwen 3.8 Max 比较 Pi 和
Claude Code、固定 Codex 比较 Sol 和 Luna。GPT-5.6 的两个名称按当前 Codex 接入
使用；不要把它们当作已经由公开 API 文档确认的模型 ID。

## 赛程

| 游戏 | 2 人局 | 3 人局 | 4 人局 | 合计 |
|---|---:|---:|---:|---:|
| 宝石商人 | 6 | 4 | 3 | 13 |
| 七大奇迹 | — | 4 | 3 | 7 |
| 伯明翰 | 6 | 4 | 3 | 13 |
| 总计 | 12 | 12 | 9 | 33 |

6 个条件形成 15 种两两关系；确定性赛程让每一对共同参赛 6 或 7 次，避免小样本中某些
pair 几乎没有直接交手。

10 workers 表示最多同时运行 10 场；七大奇迹的同时决策阶段可能让每场再并发 4 个
seat，因此理论峰值约为 40 个 CLI/API 请求。服务器应重点监控 DashScope 429、
Codex subscription 限流、内存和 CLI timeout。

## 准备认证

先在服务器安装并固定 Pi Agent、Claude Code 和 Codex CLI 版本，然后登录 Codex：

```console
codex login
codex login status
```

交互式输入 DashScope key，避免写入 shell history：

```console
read -s "DASHSCOPE_API_KEY?DashScope API Key: "
export DASHSCOPE_API_KEY
echo
```

配置只记录环境变量名，不会记录 key。Codex seat 使用 `auth_mode: subscription`，不需要
也不读取 `OPENAI_API_KEY`。

## 检查和运行

检查三种 CLI、DashScope key、Codex 登录和 33 场赛程：

```console
PYTHONPATH=src python3 examples/qwen_codex_pilot.py check
```

不调用真实 API，生成赛程并确认默认是 10 workers：

```console
PYTHONPATH=src python3 examples/qwen_codex_pilot.py run \
  --out .agentbga/qwen-codex-pilot-dry \
  --dry-run
```

先用一场、一个 worker 做真实链路测试：

```console
PYTHONPATH=src python3 examples/qwen_codex_pilot.py run \
  --out .agentbga/qwen-codex-probe \
  --limit 1 \
  --workers 1
```

固定种子下，赛程前 4 场会覆盖全部 6 个条件；要一次检查三个 Qwen ID、Claude Code
endpoint 和两个 Codex 模型，可运行：

```console
PYTHONPATH=src python3 examples/qwen_codex_pilot.py run \
  --out .agentbga/qwen-codex-all-paths-probe \
  --limit 4 \
  --workers 4
```

正式运行 33 场：

```console
PYTHONPATH=src python3 examples/qwen_codex_pilot.py run \
  --out .agentbga/qwen-codex-pilot \
  --workers 10
```

不要让多个 runner 写同一个输出目录。运行时主线程会把每个完成结果立即追加到
`matches.jsonl`；每场使用独立 SQLite。全部结束后会生成 `leaderboard.csv` 和
`summary.json`，评分使用顺序无关的多人 pairwise Bradley–Terry Elo，失败场次单独
报告而不计为比赛结果。

如果运行被中断，保留当前目录作为审计记录，并用新目录重新运行；当前版本不会从部分
`matches.jsonl` 自动续跑。
