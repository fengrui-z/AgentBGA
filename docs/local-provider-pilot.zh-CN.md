# 本机多 Provider 三游戏 Pilot

这个配置运行 12 个 `Model × Harness × Provider` 条件、66 场比赛，并暂时排除
Codex、GPT-5.6 Sol/Luna、Kimi 与其他尚未配置 endpoint 的模型。

配置文件：`examples/three-game-test-local-providers.json`

## 实验矩阵

- 固定 Minimal 比较 6 个模型：Qwen 3.8 Max、DeepSeek V4 Flash 0731、
  DeepSeek V4 Pro 0813、GLM-5.2、MiMo V2.5 Pro、MiMo V2.5。
- 固定 DeepSeek V4 Pro 0813 比较 Minimal、OpenCode、DSh、Claude Code、Hermes。
- 增加典型组合 MiMo V2.5 Pro × Claude Code 和 GLM-5.2 × Claude Code。
- Pilot 不包含 Direct API 座位。

注意：这里明确使用 `glm-5.2`，不使用 GLM-5.3。

## Endpoint 规则

| Provider | Claude Code | 其他 Harness | 密钥变量 |
|---|---|---|---|
| DashScope | `https://dashscope.aliyuncs.com/compatible-mode/apps/anthropic` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` |
| MiMo Token Plan | `https://token-plan-cn.xiaomimimo.com/anthropic` | `https://token-plan-cn.xiaomimimo.com/v1` | `MIMO_API_KEY` |

JSON 中只保存环境变量名，不保存密钥值。AgentBGA 启动 seat 时会把对应密钥映射到
Claude Code 的 `ANTHROPIC_API_KEY`、DSh 的 `DEEPSEEK_API_KEY`、Hermes 的
`OPENAI_API_KEY`；不同 provider 的原始变量不会互相替代。

## 在 zsh 中输入密钥

推荐交互式输入，密钥不会以明文出现在 shell history：

```console
read -s "DASHSCOPE_API_KEY?DashScope API Key: "
export DASHSCOPE_API_KEY
echo
read -s "MIMO_API_KEY?MiMo API Key: "
export MIMO_API_KEY
echo
```

规则：

1. 每个新终端窗口都要重新输入；不要把真实密钥写入 JSON、README 或提交到 Git。
2. 不推荐把密钥长期写进 `.zshrc`。自动化环境应使用 CI/系统的 secret store。
3. 只检查变量是否存在，不要打印变量内容：

```console
test -n "$DASHSCOPE_API_KEY" && echo "DashScope key: set"
test -n "$MIMO_API_KEY" && echo "MiMo key: set"
```

4. 实验结束后从当前 shell 删除：

```console
unset DASHSCOPE_API_KEY MIMO_API_KEY
```

仓库已经忽略 `.env`，但本实验不自动读取 `.env`，以免不同机器静默采用不同配置。

## 检查与运行

先安装项目，并自行安装配置中实际使用的 Claude Code、OpenCode、DSh、Hermes CLI：

```console
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

检查赛程、密钥和 CLI。输出只显示 `configured: true/false`，不会显示密钥：

```console
PYTHONPATH=src python3 examples/three_game_tournament.py check \
  --config examples/three-game-test-local-providers.json
```

不调用真实 API，先生成并检查 66 场赛程：

```console
PYTHONPATH=src python3 examples/three_game_tournament.py run \
  --config examples/three-game-test-local-providers.json \
  --out .agentbga/three-game-local-pilot-dry \
  --dry-run
```

正式运行：

```console
PYTHONPATH=src python3 examples/three_game_tournament.py run \
  --config examples/three-game-test-local-providers.json \
  --out .agentbga/three-game-local-pilot
```

运行目录中的 `runtime.json` 会记录 Python、Harness 可执行文件路径和版本、endpoint
以及密钥是否已配置，但不会记录密钥。结果写入 `matches.jsonl`、`leaderboard.csv` 和
`summary.json`。

先做一场真实链路测试时，可添加 `--limit 1` 并使用新的输出目录。这个结果仅用于
连通性检查，不应混入正式 Elo。
