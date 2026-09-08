"""Multi-seed random-baseline audit with replayable, readable decision records."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Iterable, Mapping, Sequence

from .plugin import ArkNovaOfficialPlugin


AUDIT_SCHEMA_VERSION = "agentbga.ark_nova.random_audit.v1"
DEFAULT_SOLO_SEEDS = (1, 7, 42, 20260829, 999999937)
DEFAULT_TWO_PLAYER_SEEDS = (1, 7, 42)
_ACTION_NAMES = {
    "animals": "动物", "build": "建造", "association": "协会",
    "cards": "卡牌", "sponsors": "赞助商",
}
_TYPE_NAMES = {
    "choose_initial_hand": "选择初始手牌",
    "start_action": "开始行动",
    "take_x_token_action": "拿取 1 枚 X 标记并结束回合",
    "select_animal_card": "选择要打出的动物",
    "play_selected_animal": "将所选动物放入围栏",
    "finish_animals_action": "结束动物行动",
    "place_building": "放置建筑",
    "finish_build_action": "结束建造行动",
    "perform_association_task": "执行协会事务",
    "make_association_donation": "协会捐款",
    "finish_association_action": "结束协会行动",
    "begin_cards_draw": "开始抽牌",
    "draw_cards_action_card": "抽取卡牌",
    "snap_cards_action_card": "拿取展示区卡牌",
    "discard_cards_action_card": "弃置卡牌",
    "play_sponsor_card": "打出赞助商",
    "advance_sponsors_break": "以赞助商行动推进休息轨道",
    "finish_sponsors_action": "结束赞助商行动",
    "resolve_semantic_choice": "解决规则选择",
    "place_unique_sponsor_building": "放置赞助商独特建筑",
    "upgrade_association_reward_card": "升级行动卡牌",
    "discard_final_scoring_card": "弃置一张终局计分牌",
}


def _card_titles(plugin: ArkNovaOfficialPlugin) -> dict[str, str]:
    titles: dict[str, str] = {}
    prefixes = {
        "animal": "zoo", "sponsor": "zoo",
        "zoo_conservation_project": "zoo",
        "base_conservation_project": "base-project",
        "final_scoring": "final",
    }
    for entries in plugin.pack.collections.values():
        for entry in entries:
            titles[entry.id] = entry.display_title
            component = entry.official_component_id
            prefix = prefixes.get(entry.kind)
            if component and prefix:
                titles[f"{prefix}-{component}"] = entry.display_title
    return titles


def _named(value: Any, titles: Mapping[str, str]) -> str:
    if isinstance(value, str) and value in titles:
        return f"{titles[value]}（{value}）"
    return str(value)


def describe_action(action: Mapping[str, Any], titles: Mapping[str, str]) -> str:
    """Render an accepted protocol action as compact, non-publisher wording."""

    action_type = str(action.get("type", "unknown"))
    label = _TYPE_NAMES.get(action_type, action_type)
    if action_type == "choose_initial_hand":
        cards = "、".join(_named(value, titles) for value in action.get("card_ids", []))
        return f"{label}：{cards}"
    if action_type == "start_action":
        name = _ACTION_NAMES.get(str(action.get("action_card_id")), str(action.get("action_card_id")))
        x_spent = sum(int(value) for value in action.get("x_by_execution", []))
        multiplier = int(action.get("multiplier_tokens", 0))
        extras = []
        if x_spent:
            extras.append(f"花费 X×{x_spent}")
        if multiplier:
            extras.append(f"双倍标记×{multiplier}")
        return f"{label}：{name}" + (f"（{'，'.join(extras)}）" if extras else "")
    if action_type == "take_x_token_action":
        name = _ACTION_NAMES.get(str(action.get("action_card_id")), str(action.get("action_card_id")))
        return f"{label}（{name}）"
    if action_type in {"select_animal_card", "play_sponsor_card", "discard_cards_action_card"}:
        return f"{label}：{_named(action.get('card_id'), titles)}"
    if action_type in {"draw_cards_action_card", "snap_cards_action_card"}:
        source = action.get("source", "deck")
        position = action.get("display_position")
        suffix = f"展示位 {position}" if position is not None else ("牌库" if source == "deck" else str(source))
        return f"{label}：{suffix}"
    if action_type == "place_building":
        cells = " ".join(f"({item['q']},{item['r']})" for item in action.get("cells", []))
        return (
            f"{label}：{action.get('building_type')}，{action.get('size')} 格，"
            f"旋转 {action.get('rotation')}，位置 {cells}，费用 {action.get('cost')}"
        )
    if action_type == "place_unique_sponsor_building":
        cells = " ".join(f"({item['q']},{item['r']})" for item in action.get("cells", []))
        return f"{label}：{_named(action.get('card_id'), titles)}，位置 {cells}"
    if action_type == "perform_association_task":
        detail = action.get("continent") or action.get("university") or action.get("project_id") or ""
        return (
            f"{label}：{action.get('task_id')} {detail}，强度 {action.get('strength')}，"
            f"事务员 {action.get('workers')}"
        ).strip()
    if action_type == "make_association_donation":
        return f"{label}：支付 {action.get('cost')} 钱"
    if action_type == "resolve_semantic_choice":
        choices = "、".join(_named(value, titles) for value in action.get("option_ids", []))
        return f"{label}：{choices}"
    ignored = {"type", "choice_id"}
    detail = "，".join(
        f"{key}={_named(value, titles)}"
        for key, value in action.items() if key not in ignored
    )
    return label + (f"：{detail}" if detail else "")


def _player_snapshot(player: Mapping[str, Any]) -> dict[str, Any]:
    tracks = player["tracks"]
    return {
        "money": int(player["money"]),
        "x": int(player["x_tokens"]),
        "appeal": int(tracks["appeal"]),
        "conservation": int(tracks["conservation"]),
        "reputation": int(tracks["reputation"]),
        "hand": len(player["hand"]),
        "played": len(player["played_cards"]),
        "buildings": len(player["map"]["buildings"]),
        "workers_available": int(player["association_workers"]["active"]),
    }


def _state_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    track = state["break"]
    return {
        "phase": state["phase"],
        "active_seat": int(state["active_seat"]),
        "turn": int(state["turn"]["number"]),
        "break_count": int(track["count"]),
        "break_position": int(track["position"]),
        "solo_round": track.get("solo_round"),
        "solo_tokens_left": track.get("solo_tokens_left"),
        "players": [_player_snapshot(player) for player in state["players"]],
    }


def _snapshot_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    changes = []
    labels = {
        "money": "钱", "x": "X", "appeal": "魅力", "conservation": "保护",
        "reputation": "声望", "hand": "手牌", "played": "已打出牌",
        "buildings": "建筑", "workers_available": "可用事务员",
    }
    for seat, (left, right) in enumerate(zip(before["players"], after["players"]), 1):
        player_changes = [
            f"{labels[key]} {left[key]}→{right[key]}"
            for key in labels if left[key] != right[key]
        ]
        if player_changes:
            changes.append(f"座位 {seat}：" + "；".join(player_changes))
    if before["turn"] != after["turn"]:
        changes.append(f"回合 {before['turn']}→{after['turn']}")
    if before["break_count"] != after["break_count"]:
        changes.append(f"休息次数 {before['break_count']}→{after['break_count']}")
    if before.get("solo_tokens_left") != after.get("solo_tokens_left"):
        changes.append(f"单人标记 {before.get('solo_tokens_left')}→{after.get('solo_tokens_left')}")
    return changes or ["无可见资源变化"]


def _assert_audit_invariants(
    plugin: ArkNovaOfficialPlugin, state: Mapping[str, Any], players: int,
) -> None:
    plugin.validate_state(dict(state))
    finite_donations = [
        int(item["cost"]) for item in state["donations_made"]
        if item.get("cost") in {2, 5, 7, 10}
    ]
    if len(finite_donations) != len(set(finite_donations)):
        raise AssertionError("a finite Association donation space was occupied twice")
    if players == 1:
        track = state["break"]
        if track["mode"] != "solo_round":
            raise AssertionError("solo game is not using the solo round board")
        total = int(track["solo_total_tokens"])
        left = int(track["solo_tokens_left"])
        round_number = int(track["solo_round"])
        if total != 8 - round_number or not 0 <= left <= total:
            raise AssertionError("solo token schedule is inconsistent")
    if players == 2:
        if state["break"]["mode"] != "shared_track" or state["break"]["limit"] != 9:
            raise AssertionError("two-player game must use a nine-space Break track")
        projects = state["conservation_projects"]
        original = [project for project in projects if project.get("base")][:3]
        expected = [["high"], ["middle"], ["low"]]
        if [project.get("blocked_levels", []) for project in original] != expected:
            raise AssertionError("two-player base-project blocking is inconsistent")
        if len([project for project in projects if not project.get("base")]) > 2:
            raise AssertionError("more than two played Zoo conservation projects are active")


def _result_digest(result: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def run_audited_baseline(
    players: int, seed: int, *, maximum_turns: int = 1000,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Run one random game, enforce invariants, and return replayable records."""

    plugin = ArkNovaOfficialPlugin()
    titles = _card_titles(plugin)
    state = plugin.setup(players, seed)
    initial_state_hash = plugin.state_hash(state)
    rng = random.Random(f"ark-nova-map0-release:{players}:{seed}")
    decisions: list[dict[str, Any]] = []
    event_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    _assert_audit_invariants(plugin, state, players)
    while state["status"] != "finished":
        turn = int(state["turn"]["number"])
        if turn > maximum_turns:
            raise AssertionError(f"{players}P seed {seed} exceeded {maximum_turns} turns")
        seats = plugin.decision_seats(state)
        if not seats or len(seats) != len(set(seats)):
            raise AssertionError("decision-seat routing is empty or duplicated")
        seat = int(seats[0])
        actions = plugin.legal_actions(state, seat)
        action_ids = [item["id"] for item in actions]
        if not actions or len(action_ids) != len(set(action_ids)):
            raise AssertionError("legal-action list is empty or contains duplicate IDs")
        selected_wrapper = actions[rng.randrange(len(actions))]
        if selected_wrapper not in actions:
            raise AssertionError("random baseline selected an action outside the legal list")
        action = deepcopy(selected_wrapper["action"])
        before = _state_snapshot(state)
        next_state, events = plugin.apply_action(state, seat, action)
        _assert_audit_invariants(plugin, next_state, players)
        after = _state_snapshot(next_state)
        action_type = str(action.get("type", "unknown"))
        event_types = [str(event.get("type", "unknown")) for event in events]
        action_counts[action_type] += 1
        event_counts.update(event_types)
        decisions.append({
            "decision": len(decisions) + 1,
            "turn_before": turn,
            "phase_before": state["phase"],
            "seat": seat,
            "legal_action_count": len(actions),
            "selected_action_id": selected_wrapper["id"],
            "action": action,
            "action_text": describe_action(action, titles),
            "event_types": event_types,
            "state_changes": _snapshot_delta(before, after),
            "state_hash_after": plugin.state_hash(next_state),
        })
        state = next_state

    if players == 1:
        if state["turn"]["number"] != 27 or state["break"]["count"] != 5:
            raise AssertionError("solo game did not finish after the official 27 turns / five Breaks")
    results = deepcopy(state["endgame"]["results"])
    if not isinstance(results, list) or len(results) != players:
        raise AssertionError("finished game has no complete ranking")
    summary = {
        "players": players,
        "seed": seed,
        "status": "passed",
        "turns": int(state["turn"]["number"]),
        "decisions": len(decisions),
        "breaks": int(state["break"]["count"]),
        "initial_state_hash": initial_state_hash,
        "final_state_hash": plugin.state_hash(state),
        "winner_seats": [int(row["seat"]) for row in results if row["rank"] == 1],
        "rankings": results,
        "action_type_counts": dict(sorted(action_counts.items())),
        "event_type_counts": dict(sorted(event_counts.items())),
    }
    summary["result_sha256"] = _result_digest(summary)
    return summary, decisions, deepcopy(state)


def verify_replay(
    players: int, seed: int, decisions: Sequence[Mapping[str, Any]], expected_hash: str,
) -> None:
    """Replay every accepted action and compare every recorded state hash."""

    plugin = ArkNovaOfficialPlugin()
    state = plugin.setup(players, seed)
    for record in decisions:
        seat = int(record["seat"])
        action = deepcopy(dict(record["action"]))
        legal = plugin.legal_actions(state, seat)
        if action not in [item["action"] for item in legal]:
            raise AssertionError(f"replay decision {record['decision']} is no longer legal")
        state, _ = plugin.apply_action(state, seat, action)
        actual = plugin.state_hash(state)
        if actual != record["state_hash_after"]:
            raise AssertionError(f"replay diverged at decision {record['decision']}")
    if plugin.state_hash(state) != expected_hash:
        raise AssertionError("replay final state hash differs from the audited run")


def _ranking_text(summary: Mapping[str, Any]) -> str:
    rendered = "；".join(
        f"座位 {int(row['seat']) + 1}: {row['victory_points']} 分（第 {row['rank']}）"
        for row in sorted(summary["rankings"], key=lambda item: item["rank"])
    )
    if summary["players"] == 1:
        rendered += "，单人挑战" + ("成功" if summary["rankings"][0].get("solo_won") else "失败")
    return rendered


def render_decision_markdown(summary: Mapping[str, Any], decisions: Sequence[Mapping[str, Any]]) -> str:
    mode = "单人" if summary["players"] == 1 else "双人"
    lines = [
        f"# {mode}随机基线：seed {summary['seed']}", "",
        f"结果：通过。共 {summary['turns']} 回合、{summary['decisions']} 次决策、"
        f"{summary['breaks']} 次休息。{_ranking_text(summary)}", "",
        f"最终状态哈希：`{summary['final_state_hash']}`", "",
        "下表逐项记录了当时的合法选项数、随机基线实际选择、产生的事件以及公开资源变化。"
        "座位编号在文档中从 1 开始。", "",
        "| 决策 | 回合/阶段 | 座位 | 合法项 | 实际选择 | 公开状态变化 | 主要事件 |",
        "|---:|---|---:|---:|---|---|---|",
    ]
    for record in decisions:
        events = "、".join(record["event_types"])
        changes = "；".join(record["state_changes"])
        safe = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {record['decision']} | {record['turn_before']} / {record['phase_before']} | "
            f"{int(record['seat']) + 1} | {record['legal_action_count']} | "
            f"{safe(record['action_text'])} | {safe(changes)} | {safe(events)} |"
        )
    lines.extend(["", "## 动作类型覆盖", ""])
    for action_type, count in summary["action_type_counts"].items():
        lines.append(f"- `{action_type}`：{count} 次")
    lines.append("")
    return "\n".join(lines)


def _render_report(report: Mapping[str, Any]) -> str:
    event_counts: Counter[str] = Counter()
    for item in report["results"]:
        event_counts.update(item["event_type_counts"])
    lines = [
        "# 方舟动物园 Map 0 随机基线多 seed 审计", "",
        f"执行日期：{report['executed_on']}。规则版本：`{report['rules_version']}`。", "",
        "本次审计的“通过”表示：随机基线每一步只从引擎给出的合法动作中选择；动作后完整状态校验通过；"
        "212 张实体动物园牌守恒；轨道、资源、地图建筑与声望上限等状态约束通过；单人轮次/捐款占位和"
        "双人休息轨道/基础项目封锁约束通过；并且逐步重放得到相同状态哈希。", "",
        "| 模式 | seed | 结果 | 回合 | 决策 | 休息 | 排名/分数 | 决策记录 |",
        "|---|---:|---|---:|---:|---:|---|---|",
    ]
    for item in report["results"]:
        mode = "单人" if item["players"] == 1 else "双人"
        filename = f"decisions/{'solo' if item['players'] == 1 else 'two-player'}-seed-{item['seed']}.md"
        lines.append(
            f"| {mode} | {item['seed']} | {item['status']} | {item['turns']} | "
            f"{item['decisions']} | {item['breaks']} | {_ranking_text(item)} | [{filename}]({filename}) |"
        )
    lines.extend([
        "", "## 本次发现并修复的问题", "",
        "双人 seed 42 首次运行时，动物的 Assertion 能力尝试从未展示的基础保护项目供应区拿牌。"
        "设置数据在该区保存项目 ID，而语义引擎错误地把 ID 当成卡牌对象读取，导致运行中止。"
        "现在引擎通过内容目录将供应区 ID 安全解析为实体项目牌，转移到手牌后仍维持 212 张动物园牌守恒；"
        "该 seed 已完整复跑并通过逐步重放。", "",
        "修复后未再发现越过合法动作列表、无决策座位、重复动作 ID、非法地图/资源/轨道状态、"
        "卡牌丢失或重放分歧。", "",
        "## 本批实际命中的主要机制", "",
        f"- 打出动物：{event_counts['animal_played']} 次；打出赞助商：{event_counts['sponsor_played']} 次。",
        f"- 支持保护项目：{event_counts['conservation_project_supported']} 次；"
        f"从手牌引入保护项目：{event_counts['conservation_project_introduced']} 次。",
        f"- 放置普通/通用建筑：{event_counts['building_placed']} 次；"
        f"放置赞助商独特建筑：{event_counts['unique_sponsor_building_placed']} 次。",
        f"- 协会捐款：{event_counts['association_donation_made']} 次；"
        f"Assertion 拿取未展示基础项目：{event_counts['base_project_taken']} 次。",
        f"- 完成休息：{event_counts['break_finished']} 次；完成终局计分："
        f"{event_counts['final_scoring_completed']} 场。", "",
        "## 解释边界", "",
        "这是运行时与状态不变量审计，不是穷举证明。随机策略没有覆盖到的卡牌组合、罕见互动和 FAQ 边界"
        "仍需定向场景测试；`summary.json` 中的动作/事件计数可用于定位本批没有命中的机制。", "",
        "机器可读的完整动作、事件类型、状态差异和逐步哈希位于 `traces/*.json`。", "",
    ])
    return "\n".join(lines)


def write_audit_report(
    output: Path, *, solo_seeds: Sequence[int] = DEFAULT_SOLO_SEEDS,
    two_player_seeds: Sequence[int] = DEFAULT_TWO_PLAYER_SEEDS,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    (output / "decisions").mkdir(exist_ok=True)
    (output / "traces").mkdir(exist_ok=True)
    plugin = ArkNovaOfficialPlugin()
    summaries = []
    for players, seeds in ((1, solo_seeds), (2, two_player_seeds)):
        for seed in seeds:
            summary, decisions, _ = run_audited_baseline(players, int(seed))
            verify_replay(players, int(seed), decisions, summary["final_state_hash"])
            summary["replay_verified"] = True
            summaries.append(summary)
            stem = f"{'solo' if players == 1 else 'two-player'}-seed-{seed}"
            (output / "decisions" / f"{stem}.md").write_text(
                render_decision_markdown(summary, decisions), encoding="utf-8",
            )
            (output / "traces" / f"{stem}.json").write_text(
                json.dumps({"summary": summary, "decisions": decisions}, indent=2,
                           sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    report = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "executed_on": date.today().isoformat(),
        "rules_version": plugin.rules_version,
        "content_sha256": plugin.pack.content_sha256,
        "results": summaries,
    }
    (output / "summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output / "report.md").write_text(_render_report(report), encoding="utf-8")
    return report


def _seeds(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise argparse.ArgumentTypeError("seeds must be comma-separated integers") from error


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit random Ark Nova Map 0 baselines")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solo-seeds", type=_seeds, default=DEFAULT_SOLO_SEEDS)
    parser.add_argument("--two-player-seeds", type=_seeds, default=DEFAULT_TWO_PLAYER_SEEDS)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = write_audit_report(
        args.output, solo_seeds=args.solo_seeds,
        two_player_seeds=args.two_player_seeds,
    )
    print(json.dumps({
        "output": str(args.output), "games": len(report["results"]),
        "decisions": sum(item["decisions"] for item in report["results"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
