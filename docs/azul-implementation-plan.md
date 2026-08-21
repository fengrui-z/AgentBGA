# Azul implementation plan

本文档是下游开发 Agent 的执行规格，用于在 AgentBGA 中加入可运行、可重放、
可由 Human/API Agent/Harness 使用的《Azul》基础版规则插件。实现时应优先遵守
本文档已经冻结的接口与边界；如果发现官方规则与本文档冲突，应先记录规则来源和
影响范围，再修改规则版本、测试与本文档，不能仅在代码中加入未说明的特殊分支。

## 1. 目标与非目标

### 1.1 目标

- 实现 2–4 人《Azul》基础版完整对局。
- 仅实现彩色墙面（colored wall）一面。
- 使用确定性 seed 完成初始洗袋和后续 lid 回袋。
- 遵守现有 `GamePlugin`、`ActionSpace`、观察投影、事件、状态哈希和重放契约。
- 支持 CLI、Runner、Store、随机基线、Human、直接模型和全部 Harness 后端。
- 提供不含出版商图片的专属 Web 棋盘和人类操作界面。
- 对所有关键官方规则场景、瓷砖守恒、终局、平局和跨进程重放提供测试。
- 将合法动作空间保持为有界、无排列冗余的结构化集合。

### 1.2 非目标

- 不实现灰色墙面变体。
- 不实现 Crystal Mosaic 或任何扩展。
- 不实现 Azul: Stained Glass of Sintra、Summer Pavilion、Queen's Garden、
  Azul Duel 等其他作品。
- 不复制出版商美术、版图图像或大段规则文本。
- 不为 Azul 新建通用规则 DSL。
- 不把 Azul 的工厂选取、彩色墙模板或计分规则放入 `agentbga.mechanics`。
- 不在 CLI、Store、Runner 或 Web API 中实现游戏规则。
- 不为了前端逐步点选而拆分权威规则 transition。

## 2. 规则基线与版本

权威基线：Next Move Games 英文基础版规则书：

<https://cdn.svc.asmodee.net/production-nextmove/uploads/sites/4/2024/06/EN-Azul-Rules-Next-Move-web.pdf>

规则范围：

- 100 块瓷砖，每种颜色 20 块；
- 2/3/4 人分别使用 5/7/9 个工厂展示盘；
- 每个工厂在正常补充时抽取 4 块瓷砖；
- 工厂展示、中央区、pattern lines、彩色墙、floor line；
- 工厂选取、中央区选取、起始玩家标记；
- 自动 wall-tiling、相邻计分、floor 罚分；
- 横行触发终局；
- 完整横行、纵列和同色套装终局奖励；
- 官方平局规则。

建议常量：

```python
RULES_VERSION = "next-move-2018-base-colored-wall-1.0"
SCHEMA_VERSION = "agentbga.azul.state.v1"
```

规则变化原则：

- 仅修改显示文案、CSS 或非语义 observation 字段时，不需要改变规则版本。
- 任何改变合法动作、洗袋顺序、计分、终局、平局或状态转移结果的修改，必须提升
  `RULES_VERSION`。
- 改变持久化状态结构时，提升 `SCHEMA_VERSION`；如旧状态无法重放，同时提升
  `RULES_VERSION`。

## 3. 与现有架构的一致性

必须实现 `src/agentbga/game.py` 中的完整 `GamePlugin` 协议：

```text
describe
setup/new_game
observe
legal_actions
apply_action
rankings
validate_state
state_hash
```

必须复用：

- `ActionSpace`：生成与当前状态版本绑定的稳定 action ID；
- `state_digest`：生成 canonical JSON 状态哈希；
- `action_accepted`：每个成功 transition 的第一个事件；
- `domain_event`：构造后续语义事件；
- `assign_competition_ranks`：处理官方平局名次；
- `validate_unique_items`：如适合，用于内部唯一瓷砖 ID 守恒。

插件继续独立拥有：

- 工厂和中央区选取规则；
- pattern line 合法性；
- floor 溢出；
- 彩色墙模板；
- round 结束检测；
- wall-tiling 顺序；
- 相邻计分、floor 罚分和终局奖励；
- lid 回袋和工厂补充策略。

不要因为墙是 5×5 网格就强行使用现有 axial hex topology。Azul 只需要本地的正交
邻接计算；在第二款游戏确实需要相同矩形网格原语之前，不应扩大 mechanics API。

## 4. 文件改动总览

### 4.1 新增文件

```text
src/agentbga/azul.py
tests/test_azul.py
```

### 4.2 必须修改

```text
src/agentbga/registry.py
src/agentbga/game_profile.py
tests/test_game_contract.py        # 增加 runnable/profile 一致性保护时
tests/test_store.py
tests/test_cli.py                   # 至少覆盖 describe/create/observe 之一
tests/test_web.py
web/app/page.tsx
web/app/globals.css
web/tests/rendered-html.test.mjs
README.md
web/README.md
docs/architecture.md
docs/project-overview.zh-CN.md
```

### 4.3 原则上不需要修改

```text
src/agentbga/game.py
src/agentbga/store.py
src/agentbga/runner.py
src/agentbga/cli.py
src/agentbga/mechanics/*
```

CLI 的 `--game` choices 来自 registry；Store 和 Runner 已通过 `GamePlugin` 调用游戏。
如果实现过程中需要在这些通用层加入 `if game_id == "azul"`，应先暂停并重新检查
设计。Azul 没有私密玩家数据，也不需要类似 Ark Nova 起始手牌的事件脱敏特判。

## 5. 游戏模块结构

建议 `src/agentbga/azul.py` 依次包含：

```text
imports
RuleError
rules/schema constants
tile and wall constants
describe
setup helpers / new_game
state_hash
tile/color and zone helpers
legal-action helpers / legal_actions
draft transition helpers
round-resolution and scoring helpers
apply_action
score / rankings
observe projection helpers / observe
validate_state
```

不要把 Web 文案、CSS 色值或玩家显示名称写入规则模块。

## 6. 常量和物理组件

### 6.1 颜色

使用稳定、全小写的协议标识：

```python
COLORS = ("blue", "yellow", "red", "black", "white")
TILES_PER_COLOR = 20
TOTAL_TILES = 100
```

如果前端希望把 `white` 显示成浅蓝/青色，只能在 UI 元数据中改变显示，不改变规则
协议标识。

### 6.2 唯一瓷砖 ID

内部为每块物理瓷砖分配稳定 ID：

```text
blue-01 ... blue-20
yellow-01 ... yellow-20
red-01 ... red-20
black-01 ... black-20
white-01 ... white-20
```

状态中保存 ID，action、observation 和公开事件只保存颜色/数量。这样既能严格验证
100 块砖守恒，又不会把无意义的实体身份暴露给模型。

建议提供：

```python
def tile_catalog() -> dict[str, str]: ...  # tile_id -> color
TILES = tile_catalog()

def _tile_color(tile_id: str) -> str: ...
def _color_counts(tile_ids: list[str]) -> dict[str, int]: ...
```

### 6.3 工厂数量

```python
FACTORY_COUNTS = {2: 5, 3: 7, 4: 9}
FACTORY_SIZE = 4
```

工厂使用稳定 ID：

```text
factory-01 ... factory-09
```

### 6.4 彩色墙模板

使用一个 5×5 固定模板。建议协议顺序：

```python
WALL_PATTERN = (
    ("blue",   "yellow", "red",    "black",  "white"),
    ("white",  "blue",   "yellow", "red",    "black"),
    ("black",  "white",  "blue",   "yellow", "red"),
    ("red",    "black",  "white",  "blue",   "yellow"),
    ("yellow", "red",    "black",  "white",  "blue"),
)
```

在实现前用官方版图/规则示意复核一次方向。方向本身不影响纯计分，但属于公开观察和
UI 契约，不能在发布后静默旋转。

### 6.5 Floor 罚分

```python
FLOOR_PENALTIES = (-1, -1, -2, -2, -2, -3, -3)
START_MARKER = "start-player-marker"
```

floor 保存有序 items；items 可以是瓷砖 ID 或 `START_MARKER`。普通瓷砖在七个位置
占满后立即进入 lid，不继续留在 floor。

## 7. 权威状态 schema

建议初始状态形状：

```json
{
  "schema_version": "agentbga.azul.state.v1",
  "rules_version": "next-move-2018-base-colored-wall-1.0",
  "seed": 42,
  "player_count": 2,
  "status": "active",
  "phase": "factory_offer",
  "round": 1,
  "turn_count": 0,
  "active_seat": 0,
  "round_start_seat": 0,
  "shuffle_count": 0,
  "bag": ["... internal tile ids ..."],
  "lid": [],
  "factories": [
    {"id": "factory-01", "tiles": ["blue-01", "red-03", "..."]}
  ],
  "center": [],
  "center_has_start_marker": true,
  "start_marker_holder_seat": null,
  "players": [
    {
      "seat": 0,
      "score": 0,
      "pattern_lines": [
        {"line": 1, "capacity": 1, "tiles": []},
        {"line": 2, "capacity": 2, "tiles": []},
        {"line": 3, "capacity": 3, "tiles": []},
        {"line": 4, "capacity": 4, "tiles": []},
        {"line": 5, "capacity": 5, "tiles": []}
      ],
      "wall": [
        [null, null, null, null, null],
        [null, null, null, null, null],
        [null, null, null, null, null],
        [null, null, null, null, null],
        [null, null, null, null, null]
      ],
      "floor": []
    }
  ]
}
```

说明：

- `turn_count` 每完成一次 `draft_tiles` 增加 1；自动 wall-tiling 不增加 turn。
- `round_start_seat` 记录本轮首家，用于起始玩家标记始终无人领取的规则边界。
- Azul v1 不需要 `decision_count`，Runner 会自然使用 `turn_count`。
- `phase` 只使用 `factory_offer` 和 `finished`，不制造无玩家选择的 scoring phase。
- `wall[row][column]` 保存放入该格的 tile ID 或 `None`。
- `pattern_lines` 中 tiles 必须同色，且数量不超过 capacity。
- `center_has_start_marker` 表示标记仍在中央区。
- 正常情况下标记存在于某个玩家的 `floor`；极端满 floor 情况见第 15 节。
- `start_marker_holder_seat` 表示标记已从 floor 取下、放在玩家面前；它用于标记无法
  进入七个 floor 位置的规则边界，以及对局结束后保留最终持有者。

## 8. Setup 与确定性随机性

### 8.1 `describe`

建议返回：

```json
{
  "id": "azul",
  "name": "Azul",
  "rules_version": "next-move-2018-base-colored-wall-1.0",
  "players": {"minimum": 2, "maximum": 4},
  "hidden_information": false,
  "implementation_status": "playable_beta",
  "runnable": true,
  "decision_model": "one_structured_decision_per_player_turn",
  "default_max_turns": 300,
  "action_types": ["draft_tiles"],
  "wall_variant": "colored",
  "rules_sources": ["Next Move Games Azul base-game English rulebook"],
  "content_scope": "Base game, colored wall, deterministic tiles; no publisher artwork or expansions",
  "win_condition": "Finish after wall-tiling when a player completes a horizontal row; highest score wins, then most completed horizontal rows"
}
```

`default_max_turns` 最终值必须在随机/启发式多 seed 压测后确认。不要为了保证随机策略
一定结束而改变官方终局规则；如均匀 random 过度选择 floor，应改进 baseline，而不是
加入强制终局的 house rule。

### 8.2 `new_game`

接口：

```python
def new_game(
    players: int,
    seed: int,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

规则：

- `players` 只能是 2、3、4；
- v1 对 `config` 只接受 `None` 或 `{}`；
- 初始玩家固定为 seat 0，与项目其他轻型游戏一致；
- 构造 100 个 tile ID；
- 使用 `random.Random(seed).shuffle(bag)`；
- 创建对应数量的 factories；
- 依 factory ID 顺序，每个从 bag 尾部 `pop()` 四块；
- 初始化所有玩家板；
- 返回前调用 `validate_state`。

### 8.3 后续 lid 回袋

不能保存 Python `Random` 对象，也不能使用全局 RNG。建议：

```python
def _derived_shuffle_seed(state: dict[str, Any]) -> int:
    material = (
        f"{state['rules_version']}:{state['seed']}:"
        f"azul-refill:{state['shuffle_count']}"
    )
    return int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big")

def _refill_bag_from_lid(state: dict[str, Any]) -> bool:
    if state["bag"] or not state["lid"]:
        return False
    state["shuffle_count"] += 1
    tiles = list(state["lid"])
    state["lid"] = []
    random.Random(_derived_shuffle_seed(state)).shuffle(tiles)
    state["bag"] = tiles
    return True
```

注意确定 `shuffle_count` 在派生 seed 前后增加的顺序，并用测试固定下来。上面伪代码
采用“先加一，再派生”的约定。

填工厂：

```text
for each factory in stable order:
    while len(factory.tiles) < 4:
        if bag empty:
            try refill from lid
        if bag and lid both empty:
            break
        factory.tiles.append(bag.pop())
```

如果 bag 再次耗尽且 lid 为空，允许后面的工厂少于四块或为空。

## 9. Action schema 与合法动作生成

### 9.1 冻结的 action

只使用一个玩家主动作：

```json
{
  "type": "draft_tiles",
  "source": "factory-03",
  "color": "blue",
  "destination": "pattern-line-4"
}
```

字段约束：

- `type` 固定为 `draft_tiles`；
- `source` 是当前非空 factory ID 或 `center`；
- `color` 是该 source 当前至少出现一次的颜色；
- `destination` 是 `pattern-line-1` ... `pattern-line-5` 或 `floor`。

action 不包含：

- tile ID；
- 选择数量；
- 溢出数量；
- 起始玩家标记；
- 计分结果；
- 下一玩家。

这些都是由 source、color、destination 和当前状态唯一确定的结果。

### 9.2 Pattern line 合法性

给定 line 和选中 color，合法条件：

1. line 未满；
2. line 为空，或已有瓷砖颜色等于选中 color；
3. 对应 wall row 中尚未放置该 color。

选中数量大于 line 剩余容量时仍然合法，多余瓷砖自动进入 floor/lid。

`floor` 始终是合法 destination。官方规则允许玩家主动把全部选中瓷砖放入 floor。

### 9.3 稳定生成顺序

推荐循环顺序：

```text
factories by factory id
then center
    colors by COLORS order
        pattern-line-1 ... pattern-line-5
        then floor
```

不得按 set/dict 的偶然迭代顺序生成 actions。

使用：

```python
ActionSpace.from_actions(
    "factory_offer",
    state["turn_count"],
    actions,
    prefix="azul",
)
```

`legal_actions` 行为：

- seat 越界：抛 `RuleError("seat is out of range")`；
- 已结束：返回 `[]`；
- 非 active seat：返回 `[]`；
- active state 必须至少生成一个 action。

### 9.4 动作空间上界

不要枚举相同颜色瓷砖的排列，不要枚举哪些实体 tile ID 进入 line。合法动作只表达
战略上不同的结果。

4 人局理论峰值应约为：

```text
(remaining factories × up to 4 colors + center up to 5 colors)
× (up to 5 pattern lines + floor)
```

在测试和压测中记录 `len(legal_actions)` 的平均值、P95 和最大值。若最大值显著超过
约 220，应检查是否产生了重复/排列动作，而不是简单提高阈值。

## 10. `apply_action` transition

### 10.1 通用流程

```text
1. 重新调用 legal_actions，取得 canonical legal actions。
2. 用 ActionSpace.require 校验 submitted action。
3. deepcopy state。
4. events = [action_accepted(seat, canonical_action)]。
5. 从 source 取走该 color 的全部 tile IDs。
6. 若 source 是 factory，把其余 tile IDs 依稳定顺序移入 center。
7. 若 source 是 center 且 marker 仍在 center，取得 marker。
8. 将选中瓷砖放入 destination；处理 pattern overflow 和 floor overflow。
9. 记录公开领域事件。
10. turn_count += 1。
11. 若 factories/center 仍有瓷砖，active_seat 顺时针移动。
12. 否则在同一 transition 内自动 resolve round。
13. validate_state(next_state)。
14. 返回 next_state, events。
```

所有异常必须在修改持久状态前发生；Store 会以 transaction 保证提交原子性，但游戏
插件本身也不得部分修改调用者传入的 state。

### 10.2 从 factory 选取

```text
selected = every tile in factory.tiles whose color == action.color
remainder = every other tile
factory.tiles = []
center.extend(remainder)
```

被选择工厂无该颜色的 action 不会出现在 legal actions。

### 10.3 从 center 选取

```text
selected = every tile in center whose color == action.color
center = all other tiles
if center_has_start_marker:
    claim marker before placing selected tiles
```

取得标记发生在本次 selected 瓷砖溢出进入 floor 之前，因此标记占据当前最左侧空位，
后续溢出排在它之后。

### 10.4 放入 pattern line

```text
room = capacity - len(line.tiles)
placed = selected[:room]
overflow = selected[room:]
line.tiles.extend(placed)
send overflow to floor/lid
```

同色瓷砖实体的具体顺序没有策略意义，但必须使用 source 内的稳定顺序，保证 state hash
和 replay 一致。

### 10.5 放入 floor

如果 destination 是 `floor`，全部 selected 依次尝试进入 floor。普通瓷砖：

```text
while len(floor) < 7:
    append tile
remaining tiles -> lid
```

floor 中的 marker 同样占用一个七格位置。普通 tile overflow 直接进入 lid，并生成一条
聚合事件，不需要逐砖事件。

## 11. 自动 round resolution

### 11.1 Round 结束条件

```python
def _factory_offer_empty(state: dict[str, Any]) -> bool:
    return not state["center"] and all(
        not factory["tiles"] for factory in state["factories"]
    )
```

最后一次 `draft_tiles` 完成后如果为真，立即自动结算；不暴露 `score_round` 或
`confirm_scoring` action。

### 11.2 结算顺序

为了得到稳定事件序列：

```text
players by seat ascending
    completed pattern lines from line 1 to line 5
    floor penalty
```

所有玩家的 wall-tiling 完成之后，再判断是否有人完成横行。不要在 seat 0 结算完后就
提前结束，以免其他玩家失去本轮得分。

### 11.3 完成 pattern line

对于每条 `len(tiles) == capacity` 的 line：

1. 根据 line 的 row 和 tile color，在 `WALL_PATTERN[row]` 找到目标 column；
2. 从 line 中取一块确定的 tile（建议取列表第一个）放入 wall cell；
3. 其余 tile 放入 lid；
4. 清空 pattern line；
5. 放入墙后立即计算该块瓷砖的相邻得分；
6. 增加玩家 score；
7. 生成 `wall_tile_scored` 事件。

未完成 pattern line 原样保留到下一轮。

### 11.4 相邻计分

新墙格 `(row, col)` 放入后：

```text
horizontal = 包含新砖、向左和向右连续 occupied 的长度
vertical   = 包含新砖、向上和向下连续 occupied 的长度

if horizontal == 1 and vertical == 1:
    points = 1
else:
    points = (horizontal if horizontal > 1 else 0)
           + (vertical if vertical > 1 else 0)
```

当横纵两向都有连接时，新砖在两个长度中各计算一次，这是官方计分规则。

### 11.5 Floor 罚分

按 floor item 当前顺序，将每个 item 对应到：

```text
-1, -1, -2, -2, -2, -3, -3
```

```text
penalty = sum(FLOOR_PENALTIES[:len(floor)])
score = max(0, score + penalty)
```

然后：

- 普通 tile IDs 全部进入 lid；
- marker 不进入 lid；
- 清空 floor；
- 若 marker 原本在 floor，移除它并设置 `start_marker_holder_seat` 为该玩家；满 floor
  边界下 holder 已经记录；
- 以 holder seat 作为下一轮首家；
- 生成 `floor_penalty_applied`。

### 11.6 终局检查和奖励

所有玩家完成本轮 wall-tiling 和 floor penalty 后：

```text
game ends if any player has a fully occupied horizontal wall row
```

结束时对每位玩家增加：

- 每个完整横行 +2；
- 每个完整纵列 +7；
- 每个在墙上出现 5 次的颜色 +10。

生成 `endgame_bonus_scored`，payload 至少包含：

```json
{
  "type": "endgame_bonus_scored",
  "seat": 0,
  "completed_rows": 1,
  "completed_columns": 0,
  "completed_colors": 0,
  "row_points": 2,
  "column_points": 0,
  "color_points": 0,
  "total": 2
}
```

然后：

```text
status = finished
phase = finished
emit match_finished with rankings
```

不结束时：

1. `round += 1`；
2. active seat 设为 `start_marker_holder_seat`；
3. `round_start_seat` 设为同一 seat；
4. 把 marker 重新标记为在 center，并清空 `start_marker_holder_seat`；
5. 必要时把 lid 洗回 bag；
6. 依序补满 factories；
7. 生成 `round_started`。

## 12. 事件 schema

每次成功 transition 的第一个事件必须是：

```json
{"type": "action_accepted", "seat": 0, "action": {"...": "..."}}
```

建议领域事件：

| Event | 触发时机 | 必要 payload |
|---|---|---|
| `tiles_drafted` | 从 source 取砖 | seat, source, color, count |
| `factory_remainder_moved` | 工厂余砖进入 center | source, counts |
| `start_player_marker_taken` | 首次从 center 选砖 | seat, floor_position/overflow |
| `start_player_marker_retained` | 整轮中央区未收到瓷砖 | seat, reason |
| `tiles_placed` | 放入 pattern/floor | seat, destination, color, placed, floor, lid |
| `wall_tile_scored` | 完成线铺墙 | seat, line, color, row, column, points |
| `floor_penalty_applied` | 玩家本轮 floor 结算 | seat, item_count, penalty, score_before, score_after |
| `round_finished` | 所有人结算后 | round |
| `bag_refilled` | lid 洗回 bag | round, shuffle_count, tile_count |
| `round_started` | 新一轮工厂补充完 | round, active_seat, bag_count, lid_count |
| `endgame_bonus_scored` | 终局奖励 | seat, rows, columns, colors, total |
| `match_finished` | 状态进入 finished | rankings |

事件不包含：

- bag 顺序；
- lid 洗牌派生种子；
- tile IDs；
- admin-only 状态。

`tiles_placed` 应聚合记录，不要为每个进入 pattern/floor/lid 的普通砖生成事件，避免日志
膨胀。只有铺墙并产生计分的砖需要逐条语义事件。

## 13. 计分与排名

提供本地 helpers：

```python
def score(state: dict[str, Any], seat: int) -> int: ...
def completed_rows(player: dict[str, Any]) -> int: ...
def completed_columns(player: dict[str, Any]) -> int: ...
def completed_colors(player: dict[str, Any]) -> int: ...
```

`rankings` 行建议：

```json
{
  "seat": 0,
  "score": 67,
  "completed_rows": 2,
  "completed_columns": 0,
  "completed_colors": 1,
  "rank": 1
}
```

官方排序：

```text
score descending
completed_rows descending
remaining tie = shared rank
```

实现：

```python
assign_competition_ranks(
    rows,
    sort_key=lambda row: (
        -row["score"],
        -row["completed_rows"],
        row["seat"],  # 仅保持输出稳定，不参与 tie_key
    ),
    tie_key=lambda row: (
        row["score"],
        row["completed_rows"],
    ),
)
```

不得把 seat 当成官方破平条件。

## 14. Observation 投影

Azul 没有玩家之间的隐藏信息，但未来 bag 顺序仍是 admin-only 状态。所有 seat 的公开
棋盘投影应一致，只允许 `viewer_seat` 字段不同。

建议 observation：

```json
{
  "game": "azul",
  "rules_version": "next-move-2018-base-colored-wall-1.0",
  "implementation_status": "playable_beta",
  "status": "active",
  "phase": "factory_offer",
  "round": 2,
  "turn_count": 17,
  "active_seat": 1,
  "viewer_seat": 0,
  "bag_count": 48,
  "lid_count": 3,
  "center_has_start_marker": false,
  "start_marker_holder_seat": null,
  "factories": [
    {
      "id": "factory-01",
      "tiles": {"blue": 2, "yellow": 0, "red": 1, "black": 1, "white": 0}
    }
  ],
  "center": {"blue": 0, "yellow": 3, "red": 1, "black": 0, "white": 2},
  "wall_pattern": [["blue", "yellow", "red", "black", "white"]],
  "players": [
    {
      "seat": 0,
      "score": 12,
      "pattern_lines": [
        {"line": 1, "capacity": 1, "color": null, "count": 0, "complete": false}
      ],
      "wall": [
        [
          {"color": "blue", "occupied": true},
          {"color": "yellow", "occupied": false}
        ]
      ],
      "floor": ["start-player-marker", "red"],
      "completed_rows": 0
    }
  ],
  "rankings": null
}
```

要求：

- factories/center 只显示颜色数量；
- pattern line 只显示颜色和数量；
- wall 显示预期颜色及 occupied；
- floor 显示颜色或 marker，不显示 tile ID；
- marker 在玩家面前而不在 floor 时，显示 `start_marker_holder_seat`；
- bag/lid 只显示 count；
- finished 时包含 rankings；active 时可以为 `None`。

为避免 UI 和模型各自重建规则，observation 应自描述墙颜色和 line capacity，但不要
包含长篇自然语言规则。

## 15. 起始玩家标记边界

### 15.1 满 floor

规则书要求首次从 center 取砖的玩家把 marker 放到 floor 最左侧空位，但没有清楚描述
该玩家的七个 floor 位置在此之前已经全部占满的情况。这一状态在数字实现中可达，必须
具名冻结，不能依赖列表越界或 UI 行为。

默认裁决 `AZUL-RULE-EDGE-001`：

- 若 floor 尚有位置，把 marker append 到 floor，正常占用相应罚分格；
- 若 floor 已满，marker 不进入 lid，也不挤出已有 tile；
- 设置 `start_marker_holder_seat = seat`；
- marker 仍决定下一轮首家；
- 因没有第八个印刷罚分格，不额外增加罚分；
- 生成 `start_player_marker_taken`，标记 `overflow: true`。

在最终从 `playable_beta` 升为 `playable` 前，应查找官方 FAQ、出版商答复或经过验证的
权威数字实现行为。如果权威裁决不同，应：

1. 更新此节；
2. 更新 focused test；
3. 提升 `RULES_VERSION`；
4. 更新 golden replay hash。

### 15.2 整轮中央区没有瓷砖

所有 factory 都是单色时，玩家可以依次取空每个 factory，而不产生任何余砖进入 center。
此时 marker 没有合法的随砖领取者，但回合仍必须能够确定下一轮首家。

默认裁决 `AZUL-RULE-EDGE-002`：

- 状态显式保存 `round_start_seat`；
- 若 round resolution 时 marker 仍在 center，且没有 floor/holder owner，则本轮首家保留 marker；
- 设置 `center_has_start_marker = false` 和 `start_marker_holder_seat = round_start_seat`；
- 生成 `start_player_marker_retained`，reason 为 `center_received_no_tiles`；
- 若对局继续，正常把 marker 放回 center，并以该 seat 开始下一轮。

## 16. `validate_state` 不变式

每次 `new_game` 和成功 `apply_action` 后调用。至少验证：

### 16.1 顶层

- schema/rules version 精确匹配；
- seed 是整数；
- player_count 是 2、3、4；
- players 长度和 seat 顺序正确；
- status 是 `active` 或 `finished`；
- phase 与 status 对应；
- round >= 1；
- turn_count >= 0；
- shuffle_count >= 0；
- active seat 在范围内。
- round start seat 在范围内。

### 16.2 瓷砖守恒

- 100 个 tile ID 全部来自 `TILES`；
- 每个 ID 在所有 zones 中恰好出现一次；
- zones 包括 bag、lid、factories、center、所有 pattern lines、walls、floors；
- `START_MARKER` 不计入 100 tiles；
- state 内 tile ID 的 catalog color 与所在 line/wall 颜色一致。

### 16.3 Factories 与 center

- factory 数量等于玩家数对应值；
- factory ID 唯一且顺序稳定；
- 单个 factory 不超过 4 tiles；
- center 只含合法 tile IDs；
- active factory-offer 状态至少有一个普通 tile 可选。

### 16.4 玩家板

- score 是非负整数；
- 恰好五条 pattern lines；
- line/capacity 为 1..5；
- line 数量不超过 capacity；
- 每条 line 内 tile 同色；
- line color 尚未存在于对应 wall row；
- wall 恰好 5×5；
- occupied cell 的 tile color 等于 `WALL_PATTERN[row][column]`；
- wall 中不能重复 tile ID；
- floor 最多七个 items；
- floor item 是 tile ID 或 START_MARKER；
- 一个 floor 最多一个 START_MARKER。

### 16.5 Marker

必须且只能满足以下一种状态：

1. `center_has_start_marker is True`，所有 floor 无 marker，holder seat 为 None；
2. `center_has_start_marker is False`，恰有一个 floor 包含 marker，holder seat 为 None；
3. `center_has_start_marker is False`，所有 floor 无 marker，holder seat 是合法 seat。

状态 3 可以出现在满 floor 边界，或对局结束后 marker 已被玩家收回的状态。未结束且
开始新一轮时必须回到状态 1。

### 16.6 结束状态

- finished 状态没有合法 actions；
- finished 至少有一位玩家完成横行；
- finished 不再补充 factories；
- rankings 的 score 等于玩家最终 score。

## 17. GameProfile 与 Harness

在 `src/agentbga/game_profile.py` 中增加 `AZUL_PROFILE`，并与 registry 在同一个集成
提交中加入 `_PROFILES`。

初始建议值：

```text
game_id = azul
game_name = Azul
total_expected_turns = 90          # 压测后校准
endgame_score_threshold = 60       # 压测后校准
turn_structure = single_action
hidden_info_types = []
has_spatial = True
spatial_summary_method = grid
has_card_abilities = False
ability_summary_depth = none
```

语义建议：

```python
resource_categories={
    "tiles": "drafting_resource",
    "floor": "penalty",
}
engine_component_name="pattern lines and completed wall mosaic"
scoring_dimensions=[
    "adjacency",
    "completed_rows",
    "completed_columns",
    "completed_colors",
    "floor_penalties",
]
action_meta_types={
    "draft_tiles": META_BUILD,
}
observation_schema={
    "factories": "market",
    "center": "shared_resources",
    "players": "self_state",
    "wall_pattern": "spatial",
    "bag_count": "meta",
    "lid_count": "meta",
    "rankings": "meta",
}
```

Capability weights 建议：

```text
engine investment     1
resource allocation   3
opponent adaptation   3
phase transition      2
long-range planning   2
active perception     2
endgame calculation   3
combo recognition     1
```

`draft_tiles` 同时可能包含建设、得分准备和阻断，不要仅根据 action type 假装可以推断
阻断意图。Azul 专属评测指标（如 floor penalty rate、每块墙砖平均得分、完成效率）
应作为后续独立任务，不在本次规则插件中扩张通用 capability API。

### 17.1 Profile 完整性保护

当前 runnable registry 与 `_PROFILES` 可能不完全一致。建议新增契约：

```python
runnable = {
    game_id for game_id in game_ids()
    if get_game(game_id).describe().get("runnable", True)
}
assert runnable <= set(all_profiles())
```

该测试会暴露 Century 缺少 profile 的既有问题。处理方式二选一：

1. 推荐：补充 `CENTURY_PROFILE`；
2. 或显式为不支持 profile 的游戏增加通用层能力声明，并让 minimal harness 在创建前
   拒绝，而不是运行时 `get_profile` 才失败。

不要为了让测试只覆盖 Azul 而写 Azul 特判。

## 18. Registry、CLI、Store 与 Runner 集成

### 18.1 Registry

修改：

```python
from . import ark_nova, azul, brass_birmingham, century_spice_road, splendor
```

注册顺序建议把 Azul 放在 Splendor 后：

```python
_ModulePlugin(splendor, "splendor"),
_ModulePlugin(azul, "azul"),
...
```

更新所有断言固定游戏 ID 顺序的测试。

### 18.2 CLI

正常情况下不改逻辑。验证：

```console
agentbga games describe azul
agentbga match create --game azul --players 2 --seed 42 --json
agentbga match observe MATCH_ID --seat 0 --json
agentbga match legal-actions MATCH_ID --seat 0 --json
agentbga run --game azul --players 2 --controllers random,random --seed 42 --jsonl
```

### 18.3 Store

无需 schema migration。Store 已保存 game ID、rules version、JSON state 和 hash。

必须新增 Store/Runner 回归场景：

- 创建 Azul match；
- 用随机 controllers 跑到 finished；
- `result["decisions"] == result["turns"]`；
- `store.replay(match_id)[-1]["version"] == result["version"]`；
- `match verify` 成功；
- public events 不含 bag 顺序或 tile IDs。

### 18.4 Runner

无需 Azul 分支。`default_max_turns` 从 `describe` 读取。

如果随机 baseline 经常超过上限，先统计原因：

- 合法动作是否重复；
- floor 是否在 action 排序/数量中被过度采样；
- 是否存在 round 无法结算 bug；
- 是否错误保留已空 factory/center tile；
- 是否需要独立的轻量 heuristic baseline。

不得在 Runner 中加入 `if azul: force_score`。

## 19. Web 前端实现

当前前端在 `web/app/page.tsx` 手写游戏联合类型和各游戏 renderer。本次按现有结构加入
Azul，不同时进行大规模前端架构重写。

### 19.1 TypeScript 类型

增加：

```typescript
type GameId = "splendor" | "azul" | "ark_nova" | "brass_birmingham" | "century_spice_road";

type AzulColor = "blue" | "yellow" | "red" | "black" | "white";
type AzulCounts = Record<AzulColor, number>;
type AzulPatternLine = {
  line: number;
  capacity: number;
  color: AzulColor | null;
  count: number;
  complete: boolean;
};
type AzulWallCell = {color: AzulColor; occupied: boolean};
type AzulPlayerView = {
  seat: number;
  score: number;
  pattern_lines: AzulPatternLine[];
  wall: AzulWallCell[][];
  floor: (AzulColor | "start-player-marker")[];
  completed_rows: number;
};
type AzulView = {
  game: "azul";
  rules_version: string;
  implementation_status: string;
  status: string;
  phase: string;
  round: number;
  turn_count: number;
  active_seat: number;
  bag_count: number;
  lid_count: number;
  center_has_start_marker: boolean;
  start_marker_holder_seat: number | null;
  factories: {id: string; tiles: AzulCounts}[];
  center: AzulCounts;
  wall_pattern: AzulColor[][];
  players: AzulPlayerView[];
};
```

把 `AzulView` 加入 `Snapshot["views"]` 联合类型。

### 19.2 Game picker

加入中英文 copy：

```text
Name: Azul / 花砖物语（如果项目采用此中文名）
Badge: PLAYABLE BETA
Note: 工厂选砖 · 图案墙 · 空间阻断
```

描述应明确基础版彩色墙面和 2–4 人，不暗示包含扩展。

### 19.3 棋盘组件

新增：

```text
AzulTile
AzulFactory
AzulPatternLines
AzulWall
AzulFloor
AzulPlayerPanel
AzulBoard
```

`AzulBoard` 至少显示：

- round、active seat、bag/lid count；
- 所有 factories；
- center 和 marker；
- 所有玩家的 pattern lines、wall、floor、score；
- finished 后的奖励/排名沿用通用 winner banner。

瓷砖用 CSS 色块、纹理、边框或符号区分，不使用出版商 art。白色瓷砖必须有边框或
图案，保证浅色背景下可见；颜色不能成为唯一信息载体，应同时有短标识或 title/aria。

### 19.4 人类 action picker

后端保持一个原子 `draft_tiles` action，前端对同一批 action IDs 做本地分组：

```text
Step 1: source (factory/center)
Step 2: color
Step 3: destination (pattern line/floor)
Step 4: submit the already-existing matching action ID
```

推荐独立组件：

```typescript
function AzulActionPicker({actions, view, ...}: ...)
```

重要约束：

- picker 不向后端提交中间步骤；
- picker 不自行计算合法性，只过滤服务器已给的 `LegalAction[]`；
- source/color 选择变化时，从 actions 中重算可用 destinations；
- snapshot/version 更新时清空本地 picker 状态；
- 最终只调用现有 `submitHumanAction(item)`；
- 显示目标 line 的现有颜色、容量、将放入数量和预计 overflow；
- 不提交 action JSON，只提交 action ID。

在 human turn renderer 中：

```text
if snapshot.game == azul and all actions are draft_tiles:
    render AzulActionPicker
else:
    render existing generic grouped choices
```

### 19.5 时间线文案

为 `draft_tiles` 增加中英文摘要，例如：

```text
玩家 A 从工厂 03 拿取 3 块蓝色瓷砖，放入第 4 图案行
Player A drafts 3 blue tiles from Factory 03 into pattern line 4
```

count 可以从领域事件读取；若 timeline 当前只使用 action，则显示来源、颜色和目标，
不要在前端重新推断数量。

### 19.6 Web 测试

更新：

- `/api/games` 精确游戏顺序；
- `hub.create({game: "azul"})` snapshot；
- `views[0].game == "azul"`；
- factory 数量和初始玩家数；
- static export 包含 Azul 文案；
- source 中存在 `AzulBoard` 和 `AzulActionPicker`；
- TypeScript build、ESLint（如脚本包含）和 node tests 通过。

## 20. 测试矩阵

新增 `tests/test_azul.py`。测试应通过结构化谓词寻找 action，不依赖 action 列表偶然索引。

建议测试 helper：

```python
def action(state, seat=0, **expected):
    matches = [
        row["action"] for row in azul.legal_actions(state, seat)
        if all(row["action"].get(key) == value for key, value in expected.items())
    ]
    assert len(matches) == 1
    return matches[0]
```

### 20.1 Setup

- `test_setup_is_deterministic`
- `test_different_seeds_change_factory_draws`
- `test_factory_counts_for_two_three_four_players`
- `test_setup_has_100_unique_tiles_across_zones`
- `test_invalid_player_counts_are_rejected`
- `test_game_config_is_rejected_in_v1`

### 20.2 Legal actions

- `test_only_active_seat_has_legal_actions`
- `test_factory_actions_offer_only_present_colors`
- `test_center_actions_offer_only_present_colors`
- `test_floor_is_always_a_destination`
- `test_empty_pattern_line_accepts_color`
- `test_same_color_pattern_line_accepts_color`
- `test_different_color_pattern_line_is_not_legal`
- `test_full_pattern_line_is_not_legal`
- `test_wall_row_existing_color_blocks_pattern_line`
- `test_action_ids_are_unique_and_stable`
- `test_legal_action_count_remains_bounded`

### 20.3 Draft transition

- `test_factory_draft_moves_remainder_to_center`
- `test_factory_draft_takes_all_selected_color`
- `test_center_draft_leaves_other_colors`
- `test_first_center_draft_takes_start_marker`
- `test_later_center_draft_does_not_take_marker_again`
- `test_pattern_line_receives_up_to_capacity`
- `test_pattern_overflow_goes_to_floor_then_lid`
- `test_voluntary_floor_destination_discards_excess_to_lid`
- `test_submitted_noncanonical_action_fails_without_mutation`

### 20.4 Round scoring

- `test_round_ends_only_when_factories_and_center_are_empty`
- `test_incomplete_pattern_lines_survive_round`
- `test_complete_line_moves_one_tile_to_wall_and_rest_to_lid`
- `test_lines_score_top_to_bottom`
- `test_isolated_wall_tile_scores_one`
- `test_horizontal_connection_score`
- `test_vertical_connection_score`
- `test_both_directions_count_new_tile_twice`
- `test_floor_penalty_schedule`
- `test_floor_penalty_never_reduces_score_below_zero`
- `test_start_marker_owner_becomes_next_round_first_player`
- `test_start_marker_is_not_put_in_lid`
- `test_full_floor_marker_edge_001`
- `test_round_with_no_center_tiles_retains_the_round_start_player`

### 20.5 Bag refill

- `test_lid_refills_empty_bag_deterministically`
- `test_refill_shuffle_count_advances_once`
- `test_refill_can_happen_mid_factory_fill`
- `test_factories_may_be_partially_filled_when_tiles_run_out`
- `test_same_seed_and_actions_produce_same_refill_order`

### 20.6 Endgame

- `test_horizontal_row_triggers_end_after_all_players_score`
- `test_vertical_column_does_not_trigger_end_by_itself`
- `test_endgame_row_bonus`
- `test_endgame_column_bonus`
- `test_endgame_color_bonus`
- `test_score_then_completed_rows_tiebreak`
- `test_remaining_tie_has_shared_rank`
- `test_finished_state_has_no_legal_actions`

### 20.7 Observation 与隐私

- `test_observation_contains_public_boards_for_all_players`
- `test_observation_does_not_expose_bag_order`
- `test_observation_does_not_expose_tile_ids`
- `test_seat_observations_differ_only_by_viewer_field`
- `test_finished_observation_contains_rankings`

### 20.8 随机与重放

- 2/3/4 人各至少 10 个 seed 的随机合法 action 对局；
- 每一步 `validate_state`；
- active 状态永远有 legal action；
- 在配置上限内完成绝大多数/全部固定 seeds；
- 对固定 seed/action 轨迹断言最终 state hash；
- Store replay/verify 与当前最终 hash 完全一致。

如果均匀随机对局出现超长尾，不要删除测试。先保留失败 seed，分析是否是规则 bug、动作
重复或 baseline 退化，再决定增加 deterministic heuristic baseline。

## 21. Golden replay

至少增加一个固定轨迹回归测试：

```text
players = 2
seed = 42
每一步用结构化 predicate 选择明确 action
走过：factory、center、marker、overflow、round scoring、bag refill
断言关键中间 hash 和最终 hash
```

不要只保存巨大的完整 state snapshot；优先保存：

- rules version；
- seed/player count；
- canonical actions；
- 关键版本 state hashes；
- 终局 rankings（若轨迹走到终局）。

规则语义修改导致 golden hash 变化时，必须同时检查是否需要提升 rules version。

## 22. 性能与基准检查

完成核心引擎后运行只读统计脚本，至少收集：

- 2/3/4 人；
- 每种人数 100 个 seed；
- 总 turns 分布；
- legal actions 平均值、P95、最大值；
- observation canonical JSON 字节数；
- 每次 transition 平均耗时；
- finished 比例；
- replay hash 一致率。

建议 gate：

```text
empty legal action in active state: 0
invalid state after accepted action: 0
replay mismatch: 0
initial setup nondeterminism: 0
max legal actions: approximately <= 220; investigate if higher
single transition: no unexpected superlinear behavior
```

不要把性能测试的 seed 或动作选择建立在 Python hash 随机化上。

## 23. 文档更新

### README.md

在 Games 中加入：

```text
Azul (2–4 players, playable beta, base colored wall)
```

增加 CLI 示例：

```console
agentbga match create --game azul --players 4 --seed 42 --json
```

### docs/architecture.md

- registry 图加入 Azul plugin；
- 游戏扩展性章节说明 Azul 验证了公开 drafting + 矩形空间计分；
- 明确 wall-tiling 是插件内无决策自动结算；
- 不修改通用架构原则。

### docs/project-overview.zh-CN.md

- 更新当前游戏清单和完成度；
- 说明 Azul 是无隐藏信息、轻中型空间选取基准；
- 不再保留过时的“两款游戏”表述。

### web/README.md

更新当前可渲染游戏清单，避免只写 Splendor/Ark Nova。

## 24. 推荐实施与提交顺序

### Commit 1 — Core model and focused tests

```text
feat(azul): add deterministic base-game rules plugin
```

- 新建 `azul.py`；
- setup、action、transition、round scoring、endgame、observe、validate；
- 新建大部分 `test_azul.py`；
- 暂不注册到全局 registry，避免半成品出现在 CLI/Web。

Gate：

```text
test_azul.py fully passes
```

### Commit 2 — Registry, profile, replay integration

```text
feat(azul): register game and wire harness profile
```

- registry；
- GameProfile；
- contract/CLI/Store tests；
- replay/verify；
- profile 完整性问题处理。

Gate：

```text
all Python tests pass
random matches finish for fixed seed matrix
```

### Commit 3 — Web renderer and human action picker

```text
feat(web): add Azul live table and atomic action picker
```

- TS types；
- game picker；
- board/player components；
- action picker；
- CSS；
- Web/API tests。

Gate：

```text
npm test passes
human can finish a local 2-player match
```

### Commit 4 — Documentation and beta qualification

```text
docs: document Azul rules scope and benchmark integration
```

- README/docs；
- 性能统计结果；
- 规则边界裁决；
- `playable_beta` 资格复核。

如果工作区已有用户改动，必须保留并避免覆盖；不要为整理提交运行 destructive git 命令。

## 25. 验收命令

项目要求 Python 3.11+。先确认解释器：

```console
python3 --version
```

Python 测试：

```console
PYTHONPATH=src python3 -m unittest tests.test_azul -v
PYTHONPATH=src python3 -m unittest tests.test_game_contract -v
PYTHONPATH=src python3 -m unittest tests.test_store -v
PYTHONPATH=src python3 -m unittest tests.test_cli -v
PYTHONPATH=src python3 -m unittest tests.test_web -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

CLI smoke：

```console
PYTHONPATH=src python3 -m agentbga games describe azul
PYTHONPATH=src python3 -m agentbga run \
  --game azul \
  --players 2 \
  --controllers random,random \
  --seed 42
```

Web：

```console
cd web
npm test
```

完成后至少人工检查一次：

```console
cd web && npm run build && cd ..
PYTHONPATH=src python3 -m agentbga web
```

在浏览器创建 2 人 Human vs Random Azul，验证 source → color → destination 的 UI 流程、
round scoring、marker 和新一轮首家。

## 26. Definition of Done

只有同时满足以下条件，Azul 才可合入为 `playable_beta`：

- [ ] 官方基础版彩色墙面规则范围已写入 `describe` 和 README。
- [ ] 2/3/4 人 setup 正确且 seed 确定。
- [ ] `draft_tiles` 是唯一主 action，且 action IDs 稳定唯一。
- [ ] 工厂、中央区、pattern line、floor、wall transition 完整。
- [ ] wall-tiling、相邻计分、floor 罚分、补袋自动完成。
- [ ] 横行终局、奖励和官方平局规则完整。
- [ ] 100 块瓷砖在每次 accepted transition 后严格守恒。
- [ ] observation 不泄露 bag 顺序或 tile IDs。
- [ ] registry、GameProfile、minimal harness、CLI、Store、Runner 全链路可用。
- [ ] Store replay/verify hash 一致。
- [ ] 多 seed 随机对局无空动作和状态损坏。
- [ ] Web renderer 和 AzulActionPicker 可完成真实人类对局。
- [ ] Python 和 Web 全套测试通过。
- [ ] README、architecture、project overview、web README 已同步。
- [ ] 没有在通用层加入 Azul 游戏规则特判。
- [ ] 没有引入出版商图片或大段规则原文。
- [ ] 所有规则歧义都有具名裁决和 focused test。

从 `playable_beta` 提升为 `playable` 前，额外要求：

- [ ] 用官方规则逐条复核 focused scenarios。
- [ ] 解决或确认 `AZUL-RULE-EDGE-001`。
- [ ] 固定 golden replay。
- [ ] 完成足量 2/3/4 人 seed 压测。
- [ ] 记录动作空间、局长和 observation 大小统计。

## 27. 下游 Agent 工作原则

1. 先实现规则核心和测试，再注册游戏，再做 Web。
2. 每次修改 transition 后先运行 Azul focused tests，再运行跨游戏 contract tests。
3. 不通过自然语言解析动作；只接受 canonical structured action。
4. 不信任前端计算的合法性或分数；规则插件是唯一权威。
5. 不把内部 tile IDs 暴露给观察、action、公开事件或 UI。
6. 不使用系统时间、全局 RNG、Python hash 或文件内容作为规则输入。
7. 不为通过 random 测试加入 house rule。
8. 不把单游戏政策抽象成 mechanics，除非已有第二个真实调用者和稳定语义。
9. 不顺手重写不相关游戏；如发现现有架构缺口，做最小通用修复并增加契约测试。
10. 完成工作后报告实际改动文件、测试命令、压测统计、剩余规则风险和 rules version。
