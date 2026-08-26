"""Project-authored human-readable summaries for semantic operations."""

from __future__ import annotations

from typing import Any, Mapping

from .content import ContentEntry


_ZH_REFS = {
    "actor.money": "你的资金",
    "actor.x_tokens": "你的 X 标记",
    "actor.tracks.appeal": "你的魅力",
    "actor.tracks.conservation": "你的保育点",
    "actor.tracks.reputation": "你的声望",
    "actor.hand_count": "你的手牌数",
    "target.money": "目标玩家的资金",
    "state.player_count": "玩家人数",
    "state.break.position": "休息轨当前位置",
    "actor.university_count": "你的大学数量",
    "actor.supported_project_count": "你已支持的保护项目数量",
    "actor.distinct_continent_animal_category_count": "你拥有的不同洲与动物类别图标数量",
    "actor.distinct_animal_category_count": "你拥有的不同动物类别图标数量",
    "actor.kiosk_count": "你的商亭数量",
    "actor.occupied_standard_enclosure_size_1_count": "你已入住的1格普通围栏数量",
    "actor.all_border_buildable_spaces_covered": "你是否覆盖全部可建造边缘格",
    "actor.map_complete": "你的地图是否完全覆盖",
    "actor.rock_requirement_total": "你已打出牌上的岩石要求总数",
    "actor.water_requirement_total": "你已打出牌上的水域要求总数",
    "actor.small_animal_count": "你的小型动物数量",
    "actor.large_animal_count": "你的大型动物数量",
    "binding.adjacent_water_cells": "本次建筑覆盖且邻接水域的格数",
    "binding.adjacent_rock_cells": "本次建筑覆盖且邻接岩石的格数",
    "actor.water_spaces_connected": "你的水域是否全部连通",
    "actor.rock_spaces_connected": "你的岩石是否全部连通",
    "actor.side_entrance_income_building_count": "侧入口收入建筑数量",
    "actor.connected_water_space_count": "连通水域格数量",
    "actor.unconnected_water_space_count": "未连通水域格数量",
    "actor.connected_rock_space_count": "连通岩石格数量",
    "actor.unconnected_rock_space_count": "未连通岩石格数量",
    "actor.connected_uncovered_border_space_count": "连通的未覆盖边缘格数量",
    "actor.empty_buildable_group_of_six_count": "连续6格空置可建土地组数量",
    "actor.connected_placement_bonus_space_count": "连通的放置奖励格数量",
    "actor.unconnected_placement_bonus_space_count": "未连通的放置奖励格数量",
}

_EN_REFS = {
    "actor.money": "your money", "actor.x_tokens": "your X tokens",
    "actor.tracks.appeal": "your appeal", "actor.tracks.conservation": "your conservation",
    "actor.tracks.reputation": "your reputation", "actor.hand_count": "your hand size",
    "target.money": "the target player's money", "state.player_count": "the player count",
    "state.break.position": "the Break track position",
    "actor.university_count": "your university count",
    "actor.supported_project_count": "your supported-project count",
    "actor.distinct_continent_animal_category_count": "your distinct continent and animal-category icon count",
    "actor.distinct_animal_category_count": "your distinct animal-category icon count",
    "actor.kiosk_count": "your kiosk count",
    "actor.occupied_standard_enclosure_size_1_count": "your occupied size-1 standard-enclosure count",
    "actor.all_border_buildable_spaces_covered": "all your buildable border spaces being covered",
    "actor.map_complete": "your map being completely covered",
    "actor.rock_requirement_total": "the total rock requirements on your played cards",
    "actor.water_requirement_total": "the total water requirements on your played cards",
    "actor.small_animal_count": "your small-animal count",
    "actor.large_animal_count": "your large-animal count",
    "binding.adjacent_water_cells": "spaces covered by this building that are adjacent to water",
    "binding.adjacent_rock_cells": "spaces covered by this building that are adjacent to rock",
    "actor.water_spaces_connected": "all your water spaces being connected",
    "actor.rock_spaces_connected": "all your rock spaces being connected",
    "actor.side_entrance_income_building_count": "your side-entrance income-building count",
    "actor.connected_water_space_count": "your connected-water-space count",
    "actor.unconnected_water_space_count": "your unconnected-water-space count",
    "actor.connected_rock_space_count": "your connected-rock-space count",
    "actor.unconnected_rock_space_count": "your unconnected-rock-space count",
    "actor.connected_uncovered_border_space_count": "your connected uncovered-border-space count",
    "actor.empty_buildable_group_of_six_count": "your groups of six connected empty buildable spaces",
    "actor.connected_placement_bonus_space_count": "your connected placement-bonus-space count",
    "actor.unconnected_placement_bonus_space_count": "your unconnected placement-bonus-space count",
}

_ZH_TERMS = {
    "appeal": "魅力", "conservation": "保护点数", "reputation": "声望",
    "money": "金币", "science": "研究", "bird": "鸟类", "predator": "肉食",
    "herbivore": "草食", "reptile": "爬行", "primate": "灵长类", "bear": "熊类",
    "water": "水域", "rock": "岩石", "africa": "非洲", "americas": "美洲",
    "asia": "亚洲", "australia": "澳洲", "europe": "欧洲",
}


def _term(value: Any, *, locale: str) -> str:
    text = str(value)
    if locale == "zh-CN":
        return _ZH_TERMS.get(text, text.replace("_", " "))
    return text.replace("_", " ")


def explain_value(value: Any, *, locale: str = "zh-CN") -> str:
    if isinstance(value, Mapping) and set(value) == {"ref"}:
        reference = str(value["ref"])
        if reference.startswith("actor.icons."):
            icon = _term(reference.rsplit(".", 1)[-1], locale=locale)
            return f"你的{icon}图标数量" if locale == "zh-CN" else f"your {icon} icon count"
        references = _ZH_REFS if locale == "zh-CN" else _EN_REFS
        return references.get(reference, reference.replace("_", " "))
    if isinstance(value, Mapping) and set(value) == {"calc", "values"}:
        rendered = [explain_value(item, locale=locale) for item in value["values"]]
        names = {
            "add": " + ", "multiply": " × ", "minimum": "最小值", "maximum": "最大值",
            "floor_divide": "整除",
        }
        operation = value["calc"]
        if operation in {"add", "multiply"}:
            return f"({names[operation].join(rendered)})"
        return f"{names.get(operation, operation)}({', '.join(rendered)})"
    if isinstance(value, bool):
        return "是" if locale == "zh-CN" and value else "否" if locale == "zh-CN" else str(value).lower()
    return str(value)


def _conditioned(description: str, operation: Mapping[str, Any], *, locale: str) -> str:
    condition = operation.get("when")
    if not isinstance(condition, Mapping):
        return description
    rendered = explain_predicate(condition, locale=locale)
    return f"若{rendered}：{description}" if locale == "zh-CN" else f"If {rendered}: {description}"


def _tier_table(args: Mapping[str, Any], *, locale: str) -> str:
    thresholds = list(args.get("thresholds", []))
    rewards = list(args.get("rewards", []))
    pairs = "，".join(
        f"{threshold}→{reward}" for threshold, reward in zip(thresholds, rewards)
    )
    reward = _term(args.get("reward", "reward"), locale=locale)
    if locale == "zh-CN":
        return f"达到档位时获得{reward}（{pairs}）"
    return f"gain {reward} at the listed thresholds ({pairs})"


def _trigger_label(trigger: str, *, locale: str) -> str:
    if trigger == "income":
        return "休息阶段收入时" if locale == "zh-CN" else "During Break income"
    if trigger == "building_placed":
        return "每当你放置建筑时" if locale == "zh-CN" else "Whenever you place a building"
    if trigger == "release_project_supported":
        return "每当你支持放归项目时" if locale == "zh-CN" else "Whenever you support an animal-release project"
    if trigger == "small_animal_played":
        return "每当你打出小型动物时" if locale == "zh-CN" else "Whenever you play a small animal"
    if trigger == "large_animal_played":
        return "每当你打出大型动物时" if locale == "zh-CN" else "Whenever you play a large animal"
    if trigger == "distinct_icon_entered":
        return "每当你的动物园首次获得一种洲或动物类别图标时" if locale == "zh-CN" else "Whenever a continent or animal-category icon new to your zoo enters"
    if trigger.startswith("icon_entered:"):
        _, scope, icon = trigger.split(":", 2)
        label = _term(icon, locale=locale)
        if locale == "zh-CN":
            return f"每当{'你' if scope == 'self' else '任意动物园'}获得{label}图标时"
        return f"Whenever {'your zoo' if scope == 'self' else 'any zoo'} gains a {label} icon"
    return "持续生效" if locale == "zh-CN" else "Ongoing"


def _static_modifier(args: Mapping[str, Any], *, locale: str) -> str:
    kind = str(args.get("kind", ""))
    amount = args.get("amount", 1)
    if locale == "zh-CN":
        labels = {
            "association_project_strength": f"支持保护项目所需的协会行动强度改为{amount}",
            "base_project_wildcard": "可花费这张牌上的1个标记，将其视为支持基础保护项目所需的任意1个图标",
            "engineer_extra_building": "建造行动至少建造1座建筑后，可按正常费用额外建造1座同类非特殊建筑",
            "diversity_researcher": "建造时可使用岩石或水域格，并忽略动物的岩石与水域摆放要求",
            "archeologist_bonus": "获得地图边缘的放置奖励时，可再获得1次未覆盖的放置奖励",
            "repeat_release_projects": "同一个动物放归项目可以被你多次支持",
            "waza_small_animal_program": "动物行动只打出小型动物时，可按正常费用额外打出1只小型动物",
            "animal_cost_discount": f"打出{'小型' if args.get('animal_size') == 'small' else '大型'}动物时少支付{amount}金币",
            "large_animal_ignore_prerequisite": "打出大型动物时可以忽略1项非围栏、非地形条件",
        }
    else:
        labels = {
            "association_project_strength": f"Supporting a conservation project requires Association strength {amount}",
            "base_project_wildcard": "Spend 1 token from this card as any one icon required by a base conservation project",
            "engineer_extra_building": "After building at least one building, you may build one additional non-special building of the same type at normal cost",
            "diversity_researcher": "You may build on rock or water and ignore animals' rock and water placement requirements",
            "archeologist_bonus": "After taking a placement reward on the map border, take one additional uncovered placement reward",
            "repeat_release_projects": "You may support the same animal-release project more than once",
            "waza_small_animal_program": "If the Animals action plays only small animals, you may play one additional small animal at normal cost",
            "animal_cost_discount": f"Pay {amount} less when playing a {'small' if args.get('animal_size') == 'small' else 'large'} animal",
            "large_animal_ignore_prerequisite": "When playing a large animal, ignore one non-enclosure, non-terrain prerequisite",
        }
    return labels.get(kind, f"持续规则：{_term(kind, locale=locale)}" if locale == "zh-CN" else f"Ongoing rule: {_term(kind, locale=locale)}")


def explain_predicate(operation: Mapping[str, Any], *, locale: str = "zh-CN") -> str:
    op = operation["op"]
    args = operation["args"]
    if op in {"all", "any"}:
        joiner = "且" if op == "all" else "或"
        if locale != "zh-CN":
            joiner = " and " if op == "all" else " or "
        return joiner.join(
            f"（{explain_predicate(item, locale=locale)}）" for item in args["conditions"]
        )
    if op == "not":
        child = explain_predicate(args["condition"], locale=locale)
        return f"不满足：{child}" if locale == "zh-CN" else f"not ({child})"
    if op == "compare":
        return (
            f"{explain_value(args['left'], locale=locale)} {args['operator']} "
            f"{explain_value(args['right'], locale=locale)}"
        )
    if op in {"has_tag", "has_icon"}:
        key = args.get("tag" if op == "has_tag" else "icon")
        count = explain_value(args.get("count", 1), locale=locale)
        if locale == "zh-CN":
            noun = "标签" if op == "has_tag" else "图标"
            return f"至少有 {count} 个“{key}”{noun}"
        return f"has at least {count} {key} {'tags' if op == 'has_tag' else 'icons'}"
    if op == "flag_set":
        return f"状态“{args['flag']}”已启用" if locale == "zh-CN" else f"flag {args['flag']} is set"
    if op == "player_count":
        return f"玩家人数为 {args['count']}" if locale == "zh-CN" else f"player count is {args['count']}"
    if op == "in":
        values = ", ".join(explain_value(item, locale=locale) for item in args["values"])
        return f"{explain_value(args['value'], locale=locale)} 属于 [{values}]"
    custom_id = operation.get("custom_id", "unknown")
    return f"自定义条件：{custom_id}" if locale == "zh-CN" else f"custom condition: {custom_id}"


def explain_effect(operation: Mapping[str, Any], *, locale: str = "zh-CN") -> str:
    op = operation["op"]
    args = operation["args"]
    amount = explain_value(args.get("amount"), locale=locale) if "amount" in args else None
    if locale != "zh-CN":
        simple = {
            "gain_money": f"gain {amount} money",
            "lose_money": f"lose up to {amount} money",
            "pay_money": f"pay {amount} money",
            "gain_x_token": f"gain {amount} X tokens",
            "advance_break": f"advance the Break track {amount}",
            "draw_cards": f"draw {amount} cards",
            "gain_association_worker": f"gain {amount} Association worker",
            "add_source_card_tokens": f"place {amount} of your player tokens on this card",
            "take_map_reward_card": "take one card from the deck or from within reputation range",
        }
    else:
        simple = {
            "gain_money": f"金币 +{amount}",
            "lose_money": f"失去至多 {amount} 资金",
            "pay_money": f"支付 {amount} 资金",
            "gain_x_token": f"获得 {amount} 个 X 标记",
            "advance_break": f"推进休息轨 {amount} 格",
            "draw_cards": f"抽取 {amount} 张牌",
            "gain_association_worker": f"获得 {amount} 名事务员",
            "add_source_card_tokens": f"在这张牌上放置 {amount} 个自己的玩家标记",
            "take_map_reward_card": "从牌库或声望范围内拿取1张牌",
        }
    if op in simple:
        return _conditioned(simple[op], operation, locale=locale)
    if op == "move_track":
        track = _term(args["track"], locale=locale)
        result = f"{track} +{amount}" if locale == "zh-CN" else f"gain {amount} {track}"
        return _conditioned(result, operation, locale=locale)
    if op == "gain_tiered_reward":
        count = explain_value(args.get("count"), locale=locale)
        result = (
            f"根据{count}，{_tier_table(args, locale=locale)}"
            if locale == "zh-CN" else
            f"Based on {count}, {_tier_table(args, locale=locale)}"
        )
        return _conditioned(result, operation, locale=locale)
    if op == "gain_tiered_icon_reward":
        icon = _term(args.get("icon", "icon"), locale=locale)
        result = (
            f"根据你的{icon}图标数量，{_tier_table(args, locale=locale)}"
            if locale == "zh-CN" else
            f"Based on your {icon} icon count, {_tier_table(args, locale=locale)}"
        )
        return _conditioned(result, operation, locale=locale)
    if op == "choose_one":
        option_separator = "；" if locale == "zh-CN" else "; "
        effect_separator = "，" if locale == "zh-CN" else ", "
        colon = "：" if locale == "zh-CN" else ": "
        options = option_separator.join(
            f"{item.get('label', item['id'])}{colon}"
            + effect_separator.join(explain_effect(effect, locale=locale) for effect in item.get("effects", []))
            for item in args.get("options", [])
        )
        result = f"选择一项（{options}）" if locale == "zh-CN" else f"choose one ({options})"
        return _conditioned(result, operation, locale=locale)
    if op == "choose_opponent":
        nested = "，".join(explain_effect(effect, locale=locale) for effect in args.get("effects", []))
        result = f"选择一名对手：{nested}" if locale == "zh-CN" else f"choose an opponent: {nested}"
        return _conditioned(result, operation, locale=locale)
    if op in {"for_each_opponent", "for_each_player"}:
        nested = "，".join(explain_effect(effect, locale=locale) for effect in args.get("effects", []))
        if locale == "zh-CN":
            result = f"{'每名对手' if op == 'for_each_opponent' else '每名玩家'}：{nested}"
        else:
            result = f"{'each opponent' if op == 'for_each_opponent' else 'each player'}: {nested}"
        return _conditioned(result, operation, locale=locale)
    if op == "add_modifier":
        trigger = str(args.get("trigger", "static"))
        if trigger == "static":
            return _conditioned(_static_modifier(args, locale=locale), operation, locale=locale)
        nested = "；".join(
            explain_effect(effect, locale=locale) for effect in args.get("effects", [])
        )
        label = _trigger_label(trigger, locale=locale)
        result = f"{label}{'：' if locale == 'zh-CN' else ': '}{nested}" if nested else label
        return _conditioned(result, operation, locale=locale)
    if op == "set_flag":
        flag = str(args.get("flag"))
        if flag == "interaction_immunity":
            result = "你不受其他玩家的互动效果影响" if locale == "zh-CN" else "You are immune to other players' interaction effects"
        else:
            result = f"设置状态“{flag}”" if locale == "zh-CN" else f"set state “{flag}”"
        return _conditioned(result, operation, locale=locale)
    if op == "place_free_building":
        buildings = "、".join(_term(item, locale=locale) for item in args.get("building_types", []))
        maximum = args.get("maximum", 1)
        result = f"免费放置{maximum}座{buildings}" if locale == "zh-CN" else f"place up to {maximum} {buildings} for free"
        return _conditioned(result, operation, locale=locale)
    if op == "tuck_hand_cards":
        maximum = args.get("maximum", 1)
        result = f"最多将{maximum}张手牌压在这张牌下" if locale == "zh-CN" else f"tuck up to {maximum} card from your hand under this card"
        return _conditioned(result, operation, locale=locale)
    if op == "reposition_action_card":
        slot = args.get("target_slot", 1)
        result = f"可以将1张行动牌移到强度{slot}" if locale == "zh-CN" else f"you may move one action card to strength {slot}"
        return _conditioned(result, operation, locale=locale)
    if op == "reveal_first_animal_size":
        size = "小型" if args.get("size_class") == "small" else "大型"
        result = f"从牌库寻找并拿取第一张{size}动物" if locale == "zh-CN" else f"search the deck for the first {args.get('size_class')} animal and take it"
        return _conditioned(result, operation, locale=locale)
    if op == "draw_keep_cards":
        draw, keep = args.get("draw", 0), args.get("keep", 0)
        result = f"抽{draw}张牌并保留{keep}张" if locale == "zh-CN" else f"draw {draw} cards and keep {keep}"
        return _conditioned(result, operation, locale=locale)
    if op == "sell_hand_cards":
        maximum = args.get("maximum", 0)
        result = f"最多出售{maximum}张手牌" if locale == "zh-CN" else f"sell up to {maximum} cards from your hand"
        return _conditioned(result, operation, locale=locale)
    if op == "reveal_keep_animal":
        draw = explain_value(args.get("draw", 0), locale=locale)
        keep = args.get("keep", 1)
        result = f"从牌库展示{draw}张动物牌并保留{keep}张" if locale == "zh-CN" else f"reveal {draw} animal cards from the deck and keep {keep}"
        return _conditioned(result, operation, locale=locale)
    if op == "open_bonus_sponsor_play":
        result = "可以额外打出1张赞助商牌" if locale == "zh-CN" else "you may play one additional Sponsor card"
        return _conditioned(result, operation, locale=locale)
    if op == "add_score_entry":
        points = explain_value(args.get("points"), locale=locale)
        result = f"记录 {points} 分（{args.get('category', 'card')}）" if locale == "zh-CN" else f"record {points} points ({args.get('category', 'card')})"
        return _conditioned(result, operation, locale=locale)
    custom_id = operation.get("custom_id")
    result = f"语义效果：{custom_id or op}" if locale == "zh-CN" else f"semantic effect: {custom_id or op}"
    return _conditioned(result, operation, locale=locale)


_TIMING_META = {
    "immediate": {"zh": "即时", "en": "Immediate"},
    "passive": {"zh": "持续", "en": "Ongoing"},
    "income": {"zh": "收入", "en": "Income"},
    "interaction": {"zh": "互动", "en": "Interaction"},
    "endgame": {"zh": "终局", "en": "Endgame"},
}
_TIMING_ORDER = {name: index for index, name in enumerate(_TIMING_META)}


def resolved_effect_timing(operation: Mapping[str, Any]) -> str:
    """Normalize executable effect timing for presentation and filtering."""
    op = str(operation.get("op", ""))
    args = operation.get("args", {})
    if op in {"for_each_opponent", "choose_opponent", "apply_interaction_tokens", "pilfer"}:
        return "interaction"
    if op == "set_flag" and args.get("flag") == "interaction_immunity":
        return "interaction"
    if op == "add_modifier":
        trigger = str(args.get("trigger", "static"))
        if trigger == "income":
            return "income"
        return "passive"
    timing = str(operation.get("timing", "on_play"))
    if timing == "income":
        return "income"
    if timing in {"end_of_game", "endgame"}:
        return "endgame"
    if timing in {"on_trigger", "passive", "ongoing"}:
        return "passive"
    return "immediate"


def resolve_mechanics(
    effects: Any, facts: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Project executable semantics into stable bilingual card mechanics.

    The executable operation remains the source of truth.  Printed icons are
    represented only when a card intentionally has no standalone effect ops.
    """
    rows: list[dict[str, str]] = []
    if isinstance(effects, (list, tuple)):
        for index, operation in enumerate(effects):
            if not isinstance(operation, Mapping) or not operation.get("op"):
                continue
            timing = resolved_effect_timing(operation)
            rows.append({
                "timing": timing,
                "timing_cn": _TIMING_META[timing]["zh"],
                "timing_en": _TIMING_META[timing]["en"],
                "description_cn": explain_effect(operation, locale="zh-CN"),
                "description_en": explain_effect(operation, locale="en"),
                "op": str(operation["op"]),
                "source": "compiled_semantics",
                "order": str(index),
            })
    if not rows and isinstance(facts, Mapping):
        icons = facts.get("icons")
        if isinstance(icons, Mapping) and icons:
            zh = "、".join(
                f"{_term(icon, locale='zh-CN')}图标×{count}"
                for icon, count in icons.items() if int(count) > 0
            )
            en = ", ".join(
                f"{_term(icon, locale='en')} icon ×{count}"
                for icon, count in icons.items() if int(count) > 0
            )
            if zh:
                rows.append({
                    "timing": "passive", "timing_cn": "持续", "timing_en": "Ongoing",
                    "description_cn": f"提供{zh}", "description_en": f"Provides {en}",
                    "op": "printed_icons", "source": "card_facts", "order": "0",
                })
    rows.sort(key=lambda item: (_TIMING_ORDER[item["timing"]], int(item["order"])))
    for item in rows:
        item.pop("order", None)
    return rows


def present_entry(entry: ContentEntry, *, locale: str = "zh-CN") -> dict[str, Any]:
    """Create a UI-safe view from facts and semantics, without copied card prose."""
    return {
        "id": entry.id,
        "kind": entry.kind,
        "official_component_id": entry.official_component_id,
        "title": entry.display_title,
        "summary": entry.display_summary,
        "facts": dict(entry.facts),
        "requirements": [explain_predicate(item, locale=locale) for item in entry.requirements],
        "effects": [{
            "timing": item.get("timing"),
            "description": explain_effect(item, locale=locale),
        } for item in entry.effects],
        "review_status": entry.review_status,
        "scenario_tests": list(entry.scenario_tests),
    }
