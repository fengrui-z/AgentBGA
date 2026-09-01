"""Deterministic post-game statistics for completed Ark Nova matches."""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import json
import time
from typing import Any, Mapping, TYPE_CHECKING

from .ark_nova_tracks import conservation_score_offset

if TYPE_CHECKING:
    from .store import Store


REPORT_SCHEMA_VERSION = "agentbga.ark-nova.match-report.v6"

CONTINENT_ICONS = ("africa", "europe", "asia", "australia", "americas")
ANIMAL_ICONS = ("bird", "predator", "herbivore", "bear", "reptile", "primate", "pet")
OTHER_ICONS = ("water", "rock", "research")
ACTION_NAMES = ("build", "animals", "cards", "association", "sponsors")
ENCLOSURE_TYPES = {
    "standard_enclosure", "petting_zoo", "reptile_house", "large_bird_aviary",
}


def _timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def _integer(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _error_kind(message: str) -> str:
    lowered = message.lower()
    if "quota" in lowered or "429" in lowered:
        return "quota"
    if "input length" in lowered or "context" in lowered or "token limit" in lowered:
        return "context_length"
    if "timeout" in lowered:
        return "timeout"
    return "other"


def _played_card_count(player: Mapping[str, Any], card_type: str) -> int:
    """Count durable played cards from the final authoritative state.

    Official semantic cards use ``kind`` while the replay-compatible controlled
    core uses ``card_type``.  Sponsor cards remain in the played zone for the
    rest of the game, so this avoids undercounting unique-building Sponsors
    whose staged placement path does not emit the ordinary ``sponsor_played``
    event.
    """
    played = player.get("played_cards", [])
    if not isinstance(played, list):
        return 0
    return sum(
        isinstance(card, Mapping)
        and card.get("kind", card.get("card_type")) == card_type
        for card in played
    )


def _metric_row(
    key: str, label_zh: str, label_en: str, players: list[dict[str, Any]],
    *, group: str,
) -> dict[str, Any]:
    return {
        "key": key, "label_zh": label_zh, "label_en": label_en, "group": group,
        "values": [player["metrics"].get(key, 0) for player in players],
    }


def _table_rows(players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs = [
        ("thinking_seconds", "思考时间", "Thinking time", "overview"),
        ("initial_order", "首轮顺位", "Initial order", "overview"),
        ("turns", "回合数", "Turns", "overview"),
        ("breaks_triggered", "已触发的休息次数", "Breaks triggered", "overview"),
        ("triggered_endgame", "触发游戏结束", "Triggered endgame", "overview"),
        ("map_id", "地图", "Map", "overview"),
        ("appeal", "魅力", "Appeal", "score"),
        ("conservation", "保护点数", "Conservation", "score"),
        ("final_track_score", "最终成绩", "Final track score", "score"),
        ("score", "终局得分", "Final-scoring points", "score"),
        ("reputation", "声望", "Reputation", "score"),
        ("build_actions", "建造行动", "Build actions", "actions"),
        ("animals_actions", "动物行动", "Animals actions", "actions"),
        ("cards_actions", "卡牌行动", "Cards actions", "actions"),
        ("association_actions", "协会行动", "Association actions", "actions"),
        ("sponsors_actions", "赞助商行动", "Sponsors actions", "actions"),
        ("x_tokens_gained", "获得 X-标记数量", "X-tokens gained", "resources"),
        ("x_token_actions", "行动改为获得 X-标记次数", "Actions converted to X-token", "resources"),
        ("x_tokens_spent", "使用 X-标记数量", "X-tokens spent", "resources"),
        ("money_gained", "获得金钱", "Money gained", "resources"),
        ("income_money", "由收入获得的金钱", "Money gained from income", "resources"),
        ("animal_money_spent", "花费在动物的金钱", "Money spent on Animals", "resources"),
        ("enclosure_money_spent", "花费在饲养区的金钱", "Money spent on enclosures", "resources"),
        ("donation_money_spent", "花费在捐赠的金钱", "Money spent on donations", "resources"),
        ("reputation_range_money_spent", "花费在声望范围的金钱", "Reputation-range surcharge", "resources"),
        ("cards_from_deck", "从牌库抽牌数量", "Cards drawn from deck", "cards"),
        ("cards_from_display", "从声望范围拿牌数量", "Cards taken from display", "cards"),
        ("snapped_cards", "精选卡牌", "Cards snapped", "cards"),
        ("discarded_cards", "弃除卡牌", "Cards discarded", "cards"),
        ("sponsors_played", "打出的赞助商", "Sponsors played", "cards"),
        ("animals_played", "打出的动物", "Animals played", "cards"),
        ("animals_released", "放归的动物", "Animals released", "cards"),
        ("association_workers", "协会事务员人数", "Association workers", "association"),
        ("association_donations", "协会任务：捐赠", "Association: donation", "association"),
        ("association_reputation", "协会任务：声望", "Association: reputation", "association"),
        ("association_partner_zoos", "协会任务：合作动物园", "Association: partner zoo", "association"),
        ("association_universities", "协会任务：大学", "Association: university", "association"),
        ("association_projects", "协会任务：保护项目", "Association: project", "association"),
        ("enclosures_built", "已建造的饲养区", "Enclosures built", "map"),
        ("kiosks_built", "建造贩售亭", "Kiosks built", "map"),
        ("pavilions_built", "建造休憩亭", "Pavilions built", "map"),
        ("unique_buildings_built", "建造独特建筑物", "Unique buildings built", "map"),
        ("covered_hexes", "覆盖的六角格", "Covered hexes", "map"),
        ("empty_hexes", "空置的六角格", "Empty hexes", "map"),
        ("action_cards_upgraded", "升级行动卡牌", "Action cards upgraded", "upgrades"),
        ("animals_upgraded", "升级“动物”行动卡牌", "Animals upgraded", "upgrades"),
        ("build_upgraded", "升级“建造”行动卡牌", "Build upgraded", "upgrades"),
        ("cards_upgraded", "升级“卡牌”行动卡牌", "Cards upgraded", "upgrades"),
        ("sponsors_upgraded", "升级“赞助商”行动卡牌", "Sponsors upgraded", "upgrades"),
        ("association_upgraded", "升级“协会”行动卡牌", "Association upgraded", "upgrades"),
    ]
    icon_labels = {
        "africa": ("非洲图标", "Africa icons"), "europe": ("欧洲图标", "Europe icons"),
        "asia": ("亚洲图标", "Asia icons"), "australia": ("澳洲图标", "Australia icons"),
        "americas": ("美洲图标", "Americas icons"), "bird": ("鸟类图标", "Bird icons"),
        "predator": ("食肉类图标", "Predator icons"), "herbivore": ("食草类图标", "Herbivore icons"),
        "bear": ("熊类图标", "Bear icons"), "reptile": ("爬行类图标", "Reptile icons"),
        "primate": ("灵长类图标", "Primate icons"), "pet": ("萌宠图标", "Petting-zoo icons"),
        "water": ("水域图标", "Water icons"), "rock": ("岩石图标", "Rock icons"),
        "research": ("研究图标", "Research icons"),
    }
    specs.extend(
        (f"icon_{icon}", labels[0], labels[1], "icons")
        for icon, labels in icon_labels.items()
    )
    return [_metric_row(key, zh, en, players, group=group) for key, zh, en, group in specs]


def generate_match_report(
    store: "Store", match_id: str, *, persist: bool = True,
) -> dict[str, Any]:
    """Generate a report exclusively from authoritative match records."""
    version, final_state, _ = store.load(match_id)
    if store.game_id(match_id) != "ark_nova":
        raise ValueError("Ark Nova match reports require an ark_nova match")
    if final_state.get("status") != "finished":
        raise ValueError("match report is available only after the match finishes")

    game = store.game(match_id)
    match_row = store.connection.execute(
        "SELECT created_at,updated_at,seed FROM matches WHERE id=?", (match_id,),
    ).fetchone()
    event_rows = store.connection.execute(
        "SELECT seq,version,seat,event_json,created_at FROM events "
        "WHERE match_id=? ORDER BY seq", (match_id,),
    ).fetchall()
    events = [{
        "seq": row["seq"], "version": row["version"], "seat": row["seat"],
        "created_at": row["created_at"], "event": json.loads(row["event_json"]),
    } for row in event_rows]
    # Older completed matches predate the authoritative endgame score fields.
    # Recover their pre-scoring tracks from the event suffix after the final
    # regular turn so regenerated reports include Sponsor and map rewards too.
    final_scoring_completed_index = next((
        index for index, row in enumerate(events)
        if row["event"].get("type") == "final_scoring_completed"
    ), len(events))
    final_turn_index = max((
        index for index, row in enumerate(events[:final_scoring_completed_index])
        if row["event"].get("type") == "turn_finished"
    ), default=-1)
    endgame_track_deltas: list[Counter[str]] = [
        Counter() for _ in range(final_state["player_count"])
    ]
    for row in events[final_turn_index + 1:final_scoring_completed_index]:
        event = row["event"]
        seat = event.get("seat", row["seat"])
        if (
            event.get("type") == "track_moved"
            and isinstance(seat, int) and 0 <= seat < len(endgame_track_deltas)
            and event.get("track") in {"appeal", "conservation", "reputation"}
        ):
            endgame_track_deltas[seat][str(event["track"])] += _integer(event.get("delta"))
        elif (
            event.get("type") == "final_scoring_card_scored"
            and isinstance(seat, int) and 0 <= seat < len(endgame_track_deltas)
        ):
            # Final Scoring cards update Conservation directly and emit their
            # own score event rather than a generic track_moved event.
            endgame_track_deltas[seat]["conservation"] += _integer(
                event.get("awarded_conservation", event.get("conservation")),
            )
    created_event = events[0]["event"] if events else {}
    initial_state = game.setup(
        final_state["player_count"], final_state["seed"], created_event.get("config") or None,
    )
    identities = store.players(match_id)
    identity_by_seat = {int(row["seat"]): row for row in identities}
    rankings = {int(row["seat"]): row for row in game.rankings(final_state)}

    spectator = getattr(game, "observe_spectator", None)
    if spectator is None:
        spectator = getattr(getattr(game, "module", None), "observe_spectator", None)
    presented = spectator(final_state) if spectator is not None else game.observe(final_state, 0)
    views = {
        int(player.get("seat", index)): player
        for index, player in enumerate(presented.get("players", []))
        if isinstance(player, Mapping)
    }

    metrics = [defaultdict(int) for _ in range(final_state["player_count"])]
    actions = [Counter() for _ in metrics]
    tasks = [Counter() for _ in metrics]
    tracks = [deepcopy(player.get("tracks", {})) for player in initial_state["players"]]
    trend: list[dict[str, Any]] = [{
        "turn": 0, "version": 0, "breaks_completed": 0,
        "players": [{
            "seat": seat,
            "appeal": _integer(player.get("tracks", {}).get("appeal")),
            "conservation": _integer(player.get("tracks", {}).get("conservation")),
            "reputation": _integer(player.get("tracks", {}).get("reputation")),
            "score": _integer(player.get("tracks", {}).get("appeal"))
            + conservation_score_offset(
                _integer(player.get("tracks", {}).get("conservation"))
            ),
        } for seat, player in enumerate(initial_state["players"])],
    }]
    break_count = 0
    break_open = False
    endgame_seat: int | None = None

    for row in events:
        event = row["event"]
        event_type = event.get("type")
        seat = event.get("seat", row["seat"])
        valid_seat = isinstance(seat, int) and 0 <= seat < len(metrics)
        if event_type == "break_triggered":
            break_count += 1
            break_open = True
            if valid_seat:
                metrics[seat]["breaks_triggered"] += 1
                metrics[seat]["x_tokens_gained"] += _integer(event.get("x_token_delta"))
        elif event_type == "break_finished":
            break_open = False
        elif event_type == "endgame_triggered" and valid_seat:
            endgame_seat = seat
        elif event_type == "action_finished" and valid_seat:
            actions[seat][str(event.get("action"))] += 1
        elif event_type == "turn_finished" and valid_seat:
            metrics[seat]["turns"] += 1
            trend.append({
                "turn": _integer(event.get("turn"), len(trend) + 1),
                "version": row["version"], "breaks_completed": break_count,
                "players": [{
                    "seat": player_seat,
                    "appeal": _integer(player_tracks.get("appeal")),
                    "conservation": _integer(player_tracks.get("conservation")),
                    "reputation": _integer(player_tracks.get("reputation")),
                    "score": _integer(player_tracks.get("appeal"))
                    + conservation_score_offset(_integer(player_tracks.get("conservation"))),
                } for player_seat, player_tracks in enumerate(tracks)],
            })
        elif event_type == "track_moved" and valid_seat:
            track = event.get("track")
            if isinstance(track, str):
                tracks[seat][track] = _integer(event.get("value"))
        elif event_type == "x_token_action_completed" and valid_seat:
            metrics[seat]["x_token_actions"] += 1
            metrics[seat]["x_tokens_gained"] += 1
        elif event_type == "x_tokens_changed" and valid_seat:
            metrics[seat]["x_tokens_gained"] += max(0, _integer(event.get("delta")))
        elif event_type == "action_started" and valid_seat:
            metrics[seat]["x_tokens_spent"] += _integer(event.get("x_spent"))
        elif event_type == "break_income_collected" and valid_seat:
            amount = _integer(event.get("amount"))
            metrics[seat]["money_gained"] += amount
            metrics[seat]["income_money"] += amount
        elif event_type == "money_changed" and valid_seat:
            amount = max(0, _integer(event.get("delta")))
            metrics[seat]["money_gained"] += amount
            if break_open:
                metrics[seat]["income_money"] += amount
        elif event_type == "icon_reward_gained" and valid_seat:
            reward = event.get("reward")
            amount = _integer(event.get("amount"))
            if reward == "money":
                metrics[seat]["money_gained"] += amount
                if break_open:
                    metrics[seat]["income_money"] += amount
            elif reward == "x_token":
                metrics[seat]["x_tokens_gained"] += max(0, _integer(event.get("delta"), amount))
        elif event_type == "pilfering_money_transferred":
            target = event.get("target_seat")
            amount = _integer(event.get("amount"))
            if valid_seat:
                metrics[seat]["money_gained"] += amount
            if isinstance(target, int) and 0 <= target < len(metrics):
                metrics[target]["money_lost_to_interaction"] += amount
        elif event_type == "animal_played" and valid_seat:
            metrics[seat]["animals_played"] += 1
            folder = _integer(event.get("folder_cost"))
            metrics[seat]["animal_money_spent"] += max(0, _integer(event.get("cost")) - folder)
            metrics[seat]["reputation_range_money_spent"] += folder
        elif event_type == "sponsor_played" and valid_seat:
            metrics[seat]["sponsors_played"] += 1
            metrics[seat]["reputation_range_money_spent"] += _integer(event.get("folder_cost"))
        elif event_type == "unique_sponsor_building_placed" and valid_seat:
            metrics[seat]["reputation_range_money_spent"] += _integer(event.get("folder_cost"))
        elif event_type == "conservation_project_introduced" and valid_seat:
            metrics[seat]["reputation_range_money_spent"] += _integer(event.get("folder_cost"))
        elif event_type == "animal_released" and valid_seat:
            metrics[seat]["animals_released"] += 1
        elif event_type == "building_placed" and valid_seat:
            building = event.get("building", {})
            if building.get("type") in ENCLOSURE_TYPES:
                metrics[seat]["enclosure_money_spent"] += _integer(event.get("cost"))
        elif event_type == "association_task_performed" and valid_seat:
            tasks[seat][str(event.get("task_id"))] += 1
        elif event_type == "association_donation_made" and valid_seat:
            metrics[seat]["association_donations"] += 1
            metrics[seat]["donation_money_spent"] += _integer(event.get("cost"))
        elif event_type == "cards_action_card_drawn" and valid_seat:
            source = event.get("source")
            metrics[seat]["cards_from_deck" if source == "deck" else "cards_from_display"] += 1
        elif event_type == "cards_drawn" and valid_seat:
            metrics[seat]["cards_from_deck"] += _integer(event.get("count"))
        elif event_type == "revealed_cards_resolved" and valid_seat:
            metrics[seat]["cards_from_deck"] += _integer(event.get("drawn"))
            metrics[seat]["discarded_cards"] += max(
                0, _integer(event.get("drawn")) - _integer(event.get("kept")),
            )
        elif event_type == "map_card_reward_taken" and valid_seat:
            source = event.get("source")
            metrics[seat]["cards_from_deck" if source == "deck" else "cards_from_display"] += 1
        elif event_type == "waza_small_animal_taken" and valid_seat:
            metrics[seat]["cards_from_display"] += 1
        elif event_type == "cards_action_card_snapped" and valid_seat:
            metrics[seat]["snapped_cards"] += 1
        elif event_type == "cards_action_card_discarded" and valid_seat:
            metrics[seat]["discarded_cards"] += 1
        elif event_type == "break_cards_discarded" and valid_seat:
            metrics[seat]["discarded_cards"] += _integer(event.get("count"))
        elif event_type == "sun_bathing_cards_sold" and valid_seat:
            metrics[seat]["discarded_cards"] += _integer(event.get("count"))

    model_quality: list[dict[str, Any]] = []
    model_rows = store.connection.execute(
        "SELECT seat,metadata_json FROM model_calls WHERE match_id=? ORDER BY version", (match_id,),
    ).fetchall()
    by_seat_calls: dict[int, list[dict[str, Any]]] = {seat: [] for seat in range(len(metrics))}
    for row in model_rows:
        by_seat_calls[int(row["seat"])].append(json.loads(row["metadata_json"]))
    for seat in range(len(metrics)):
        calls = by_seat_calls[seat]
        fallback = [call for call in calls if call.get("fallback")]
        errors = Counter(_error_kind(str(call.get("error", ""))) for call in fallback)
        trace_latencies: list[tuple[int, float]] = []
        trace_root = store.path.parent / "runs" / "_traces" / match_id / f"seat-{seat}"
        if trace_root.is_dir():
            for trace_path in trace_root.glob("turn-*.json"):
                try:
                    trace = json.loads(trace_path.read_text(encoding="utf-8"))
                    trace_version = _integer(trace.get("version"), -1)
                    trace_latency = trace.get("process_latency_ms", trace.get("latency_ms"))
                    if trace_version >= 0 and isinstance(trace_latency, (int, float)):
                        trace_latencies.append((trace_version, float(trace_latency)))
                except (OSError, json.JSONDecodeError):
                    continue
        trace_latency_values = [
            latency for _, latency in sorted(trace_latencies, key=lambda item: item[0])
        ]
        latency_values = []
        trace_recovered_calls = 0
        for index, call in enumerate(calls):
            latency = call.get("process_latency_ms", call.get("latency_ms"))
            if not isinstance(latency, (int, float)) and index < len(trace_latency_values):
                latency = trace_latency_values[index]
                if isinstance(latency, (int, float)):
                    trace_recovered_calls += 1
            if isinstance(latency, (int, float)):
                latency_values.append(float(latency))
        thinking_seconds = round(sum(latency_values) / 1000, 3)
        metrics[seat]["thinking_seconds"] = thinking_seconds
        model_quality.append({
            "seat": seat, "model_calls": len(calls),
            "successful_calls": len(calls) - len(fallback),
            "fallback_calls": len(fallback),
            "fallback_rate": round(len(fallback) / len(calls), 4) if calls else 0,
            "recorded_thinking_seconds": thinking_seconds,
            "latency_missing_calls": len(calls) - len(latency_values),
            "trace_recovered_calls": trace_recovered_calls,
            "fallback_error_kinds": dict(sorted(errors.items())),
        })

    report_players: list[dict[str, Any]] = []
    for seat, final_player in enumerate(final_state["players"]):
        identity = identity_by_seat.get(seat, {"seat": seat, "name": f"Seat {seat + 1}", "backend": "unknown"})
        ranking = rankings.get(seat, {})
        view = views.get(seat, final_player)
        player_metrics = metrics[seat]
        final_tracks = final_player.get("tracks", {})
        final_conservation = _integer(final_tracks.get("conservation"))
        map_completion_points = _integer(ranking.get("map_completion_points"))
        final_track_score = _integer(
            ranking.get("final_track_score"),
            _integer(final_tracks.get("appeal")) + map_completion_points
            + conservation_score_offset(final_conservation),
        )
        if isinstance(ranking.get("endgame_scoring_points"), int):
            endgame_scoring_points = int(ranking["endgame_scoring_points"])
        else:
            pre_scoring_appeal = max(
                0,
                _integer(final_tracks.get("appeal"))
                - endgame_track_deltas[seat]["appeal"],
            )
            pre_scoring_conservation = max(
                0,
                final_conservation - endgame_track_deltas[seat]["conservation"],
            )
            endgame_scoring_points = final_track_score - (
                pre_scoring_appeal
                + conservation_score_offset(pre_scoring_conservation)
            )
        player_metrics.update({
            "initial_order": seat + 1,
            "triggered_endgame": seat == endgame_seat,
            "map_id": final_player.get("map", {}).get("id") or final_state.get("map_id") or "map-0",
            "appeal": _integer(final_tracks.get("appeal")),
            "conservation": final_conservation,
            "reputation": _integer(final_tracks.get("reputation")),
            "final_track_score": final_track_score,
            "score": endgame_scoring_points,
        })
        # Sponsors are durable final-state assets.  Count them from the
        # authoritative played zone because mandatory unique-building
        # placements complete through a staged event path.
        player_metrics["sponsors_played"] = _played_card_count(
            final_player, "sponsor",
        )
        for action in ACTION_NAMES:
            player_metrics[f"{action}_actions"] = actions[seat][action]
        player_metrics.update({
            "association_reputation": tasks[seat]["gain-reputation"],
            "association_partner_zoos": tasks[seat]["partner-zoo"],
            "association_universities": tasks[seat]["university"],
            "association_projects": tasks[seat]["conservation-project"],
        })
        workers = final_player.get("association_workers", {})
        player_metrics["association_workers"] = (
            _integer(workers.get("active")) + _integer(workers.get("reserve"))
            + len(workers.get("committed", []))
        )
        buildings = final_player.get("map", {}).get("buildings", [])
        building_counts = Counter(
            str(building.get("type")) for building in buildings if isinstance(building, Mapping)
        )
        player_metrics.update({
            "enclosures_built": sum(building_counts[item] for item in ENCLOSURE_TYPES),
            "kiosks_built": building_counts["kiosk"],
            "pavilions_built": building_counts["pavilion"],
            "unique_buildings_built": sum(
                count for kind, count in building_counts.items() if kind.startswith("unique_sponsor_")
            ),
        })
        coverage = view.get("map_display", {}).get("coverage", {})
        if not coverage:
            occupied_cells = {
                (cell.get("q"), cell.get("r"))
                for building in buildings if isinstance(building, Mapping)
                for cell in building.get("cells", []) if isinstance(cell, Mapping)
            }
            total = len(final_player.get("map", {}).get("buildable_cells", []))
            coverage = {"covered": len(occupied_cells), "total": total}
        player_metrics["covered_hexes"] = _integer(coverage.get("covered"))
        player_metrics["empty_hexes"] = max(
            0, _integer(coverage.get("total")) - _integer(coverage.get("covered")),
        )
        upgraded = {
            str(card.get("action")): bool(card.get("upgraded"))
            for card in final_player.get("action_cards", []) if isinstance(card, Mapping)
        }
        player_metrics["action_cards_upgraded"] = sum(upgraded.values())
        for action in ACTION_NAMES:
            player_metrics[f"{action}_upgraded"] = upgraded.get(action, False)
        # Use the public rules projection here: it folds aliases such as
        # research/science and pet/petting_zoo into the counts shown at the
        # table.  The raw ledger intentionally retains those source names.
        icons = dict(view.get("icons", final_player.get("icons", {})))
        projected_counters = view.get("public_summary", {}).get("counters", {})
        icons.update(projected_counters.get("continents", {}))
        projected_animals = projected_counters.get("animals", {})
        icons.update(projected_animals)
        if "petting_zoo" in projected_animals:
            icons["pet"] = projected_animals["petting_zoo"]
        for icon in (*CONTINENT_ICONS, *ANIMAL_ICONS, *OTHER_ICONS):
            player_metrics[f"icon_{icon}"] = _integer(icons.get(icon))
        report_players.append({
            "seat": seat, "name": identity.get("name", f"Seat {seat + 1}"),
            "backend": identity.get("backend"), "model": identity.get("model"),
            "rank": _integer(ranking.get("rank"), seat + 1),
            "metrics": dict(player_metrics),
        })

    if trend:
        trend.append({
            "turn": _integer(final_state.get("turn_count"), trend[-1]["turn"]),
            "version": version, "breaks_completed": break_count, "final": True,
            "players": [{
                "seat": player["seat"],
                "appeal": player["metrics"]["appeal"],
                "conservation": player["metrics"]["conservation"],
                "reputation": player["metrics"]["reputation"],
                "score": player["metrics"]["final_track_score"],
                "final_scoring_points": player["metrics"]["score"],
            } for player in report_players],
        })

    report_players.sort(key=lambda player: player["rank"])
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "methodology_version": 6,
        "match_id": match_id, "rules_version": final_state.get("rules_version"),
        "content_pack_id": final_state.get("content_pack_id"),
        "content_hash": final_state.get("content_hash"),
        "state_version": version,
        "generated_at": _timestamp(time.time()),
        "duration": {
            "wall_seconds": round(float(match_row["updated_at"] - match_row["created_at"]), 3),
            "started_at": _timestamp(float(match_row["created_at"])),
            "finished_at": _timestamp(float(match_row["updated_at"])),
        },
        "turns": _integer(final_state.get("turn_count")),
        "decisions": _integer(final_state.get("decision_count")),
        "breaks": {"total": break_count},
        "endgame": {"triggered_by_seat": endgame_seat, "reason": "track_crossing"},
        "players": report_players,
        "model_quality": model_quality,
        "score_trend": trend,
        "table": _table_rows(report_players),
        "definitions": {
            "thinking_seconds": "Sum of per-decision process latency. Missing historical fallback latency is recovered from turn traces when available; remaining missing calls are listed separately.",
            "money_gained": "Explicit money-gain, break-income, icon-reward, and pilfering events; temporary Venom reserves/refunds are excluded.",
            "income_money": "Base and recurring money rewards resolved while a break was open.",
            "animal_money_spent": "Animal cost excluding the separate reputation-range surcharge.",
            "enclosure_money_spent": "Paid Build placements whose final building type is an enclosure.",
            "score_trend": "Live track score (Appeal plus the printed Conservation score offset) sampled after every turn. The final sample also includes deferred zoo-map completion points.",
            "final_track_score": "Final Appeal plus the printed Conservation score offset and deferred zoo-map completion points after all endgame effects.",
            "score": "Total points added during final scoring: Appeal from endgame Sponsor effects, the score-offset change from all endgame Conservation awards, and deferred map-completion points.",
        },
    }
    if persist:
        store.save_match_report(match_id, report)
    return report
