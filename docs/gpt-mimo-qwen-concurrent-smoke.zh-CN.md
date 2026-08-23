# GPT × MiMo 并发 Smoke Test

这个 setting 只验证 provider、harness、会话恢复和并发稳定性，不用于发布正式 Elo。
四个条件固定为：

| 模型 | Harness | 认证 |
|---|---|---|
| GPT-5.6 Sol | Codex | ChatGPT subscription |
| GPT-5.6 Luna | Codex | ChatGPT subscription |
| MiMo V2.5 Pro | Qwen Code | `MIMO_API_KEY` |
| MiMo V2.5 | Qwen Code | `MIMO_API_KEY` |

赛程包含 6 场 4 人局：宝石商人、七大奇迹、伯明翰各 2 场。每场都包含全部四个
条件，所以每个条件恰好出场 6 次，任意两个条件直接交手 6 次。默认 6 workers；这比
一开始用 10 workers 更便于判断失败来自模型 endpoint、Codex 限流还是 Qwen Code。

MiMo 条件中的 `reasoning_effort: none` 表示 Qwen Code 不向兼容 endpoint 发送额外的
reasoning-effort 覆盖；它不宣称关闭模型自身可能存在的推理过程。

## 安装和认证

固定安装本 setting 验证过的 Qwen Code 和 Codex CLI 版本：

```console
npm i -g @qwen-code/qwen-code@0.22.0 @openai/codex@0.149.0
qwen --version
codex --version
```

输入 MiMo key，并确认 Codex subscription 登录：

```console
read -s "MIMO_API_KEY?MiMo API Key: "
export MIMO_API_KEY
echo
codex login status
```

AgentBGA 会为每个 Qwen Code seat 生成隔离的 `QWEN_HOME`、MiMo provider 和 MCP
配置；不会改写用户的 `~/.qwen/settings.json`，也不会把 key 写入配置。
`check` 只能确认 ChatGPT 登录态；账户是否能在 Codex 中使用两个 GPT-5.6 模型，需要
由下面的两场真实探针确认。

## 分阶段运行

检查 CLI、key、Codex 登录和赛程，不调用模型：

```console
PYTHONPATH=src python3 examples/qwen_codex_pilot.py check \
  --config examples/gpt-mimo-qwen-concurrent-smoke.json
```

先 dry-run：

```console
PYTHONPATH=src python3 examples/qwen_codex_pilot.py run \
  --config examples/gpt-mimo-qwen-concurrent-smoke.json \
  --out .agentbga/gpt-mimo-qwen-dry \
  --dry-run
```

两场真实并发探针；由于都是 4 人局，第一场已经覆盖全部四个条件，第二场用于发现
并发或会话隔离问题：

```console
PYTHONPATH=src python3 examples/qwen_codex_pilot.py run \
  --config examples/gpt-mimo-qwen-concurrent-smoke.json \
  --out .agentbga/gpt-mimo-qwen-probe \
  --limit 2 \
  --workers 2
```

探针通过后运行全部 6 场：

```console
PYTHONPATH=src python3 examples/qwen_codex_pilot.py run \
  --config examples/gpt-mimo-qwen-concurrent-smoke.json \
  --out .agentbga/gpt-mimo-qwen-smoke \
  --workers 6
```

如果 6 场稳定，再把配置中的 `appearances_per_condition` 和 `workers` 同时改为 `3`
和 `9`；这会生成每个游戏 3 场、总计 9 场的第二级压力测试。
