#!/usr/bin/env python3
"""Create the public Frontier12 data file consumed by the GitHub Pages UI."""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


USD_CNY = 6.7811
PRICING_AS_OF = "2026-08-28"


def _openai_rmb(input_usd: float, cached_usd: float, output_usd: float) -> dict[str, float]:
    return {
        "input_rmb_per_m": round(input_usd * USD_CNY, 4),
        "cached_input_rmb_per_m": round(cached_usd * USD_CNY, 4),
        "output_rmb_per_m": round(output_usd * USD_CNY, 4),
        "native_currency": "USD",
        "native_input_per_m": input_usd,
        "native_cached_input_per_m": cached_usd,
        "native_output_per_m": output_usd,
        "source": "openai",
        "source_url": "https://developers.openai.com/api/docs/models/compare",
    }


MODEL_PRICING: dict[str, dict[str, Any]] = {
    "gpt-5.6-sol": _openai_rmb(4.0, 0.4, 20.0),
    "gpt-5.6-terra": _openai_rmb(2.0, 0.2, 12.0),
    "gpt-5.6-luna": _openai_rmb(0.2, 0.02, 1.2),
    "deepseek-v4-flash-0731": {
        "input_rmb_per_m": 3.0,
        "cached_input_rmb_per_m": 0.3,
        "output_rmb_per_m": 9.0,
        "source": "qianwen",
        "source_url": "https://www.qianwenai.com/models/deepseek-v4-flash-0731",
        "price_note": "busy hours (08:00–22:00 Asia/Shanghai)",
    },
    "deepseek-v4-pro-0813": {
        "input_rmb_per_m": 9.0,
        "cached_input_rmb_per_m": 0.9,
        "output_rmb_per_m": 27.0,
        "source": "qianwen",
        "source_url": "https://www.qianwenai.com/models/deepseek-v4-pro-0813",
        "price_note": "busy hours (08:00–22:00 Asia/Shanghai)",
    },
    "glm-5.2": {
        "input_rmb_per_m": 8.0,
        "cached_input_rmb_per_m": 2.0,
        "output_rmb_per_m": 28.0,
        "source": "qianwen",
        "source_url": "https://www.qianwenai.com/models/glm-5.2",
    },
    "kimi-k2.7-code": {
        "input_rmb_per_m": 6.5,
        "cached_input_rmb_per_m": 1.3,
        "output_rmb_per_m": 27.0,
        "source": "qianwen",
        "source_url": "https://www.qianwenai.com/models/kimi-k2.7-code",
    },
    "qwen3.7-plus": {
        "input_rmb_per_m": 1.6,
        "cached_input_rmb_per_m": 0.32,
        "output_rmb_per_m": 6.4,
        "source": "qianwen",
        "source_url": "https://www.qianwenai.com/models/qwen3.7-plus",
        "price_note": "current promotional price, input <=256K",
    },
    "qwen3.8-max": {
        "input_rmb_per_m": 12.0,
        "cached_input_rmb_per_m": 1.5,
        "output_rmb_per_m": 36.0,
        "source": "qianwen",
        "source_url": "https://www.qianwenai.com/models/qwen3.8-max",
    },
}

PRICING_SOURCES = [
    {
        "id": "qianwen",
        "label": "千问 AI 模型市场",
        "url": "https://www.qianwenai.com/models",
    },
    {
        "id": "openai",
        "label": "OpenAI API model pricing",
        "url": "https://developers.openai.com/api/docs/models/compare",
    },
    {
        "id": "fx",
        "label": "2026-08-28 人民币汇率中间价",
        "url": "https://www.news.cn/20260828/8ded7ca354aa4c95b9a24a3cdd0b4fb8/c.html",
    },
]


class _ReportTableParser(HTMLParser):
    """Extract the accessible chart data tables embedded in the HTML report."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: dict[str, list[list[str]]] = {}
        self._table: dict[str, Any] | None = None
        self._in_caption = False
        self._cell: list[str] | None = None
        self._row: list[str] | None = None
        self._row_is_header = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table" and self._table is None:
            self._table = {"caption": [], "rows": []}
        elif self._table is not None and tag == "caption":
            self._in_caption = True
        elif self._table is not None and tag == "tr":
            self._row = []
            self._row_is_header = False
        elif self._table is not None and tag in {"th", "td"}:
            self._cell = []
            self._row_is_header = self._row_is_header or tag == "th"

    def handle_data(self, data: str) -> None:
        if self._table is None:
            return
        if self._in_caption:
            self._table["caption"].append(data)
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._table is None:
            return
        if tag == "caption":
            self._in_caption = False
        elif tag in {"th", "td"} and self._cell is not None:
            if self._row is not None:
                self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row and not self._row_is_header:
                self._table["rows"].append(self._row)
            self._row = None
        elif tag == "table":
            caption = " ".join("".join(self._table["caption"]).split())
            if caption:
                self.tables[caption] = self._table["rows"]
            self._table = None


def _millions(value: str) -> float:
    match = re.search(r"[0-9]+(?:\.[0-9]+)?", value.replace(",", ""))
    if not match:
        raise ValueError(f"Cannot parse token value: {value!r}")
    return float(match.group())


def _artifact_datasets(report_html: str) -> dict[str, list[dict[str, Any]]]:
    """Read the full datasets bundled into a portable Data Analytics report."""

    match = re.search(
        r'<template[^>]*id="data-analytics-portable-artifact-payload-source"[^>]*>'
        r"(.*?)</template>",
        report_html,
        re.DOTALL,
    )
    if not match:
        return {}
    encoded = re.sub(r"\s", "", match.group(1))
    payload = json.loads(gzip.decompress(base64.b64decode(encoded)))
    return payload.get("snapshot", {}).get("datasets", {})


def _cost_breakdown(row: dict[str, Any], pricing: dict[str, Any]) -> dict[str, float]:
    input_cost = round(row["mean_input_tokens_m"] * pricing["input_rmb_per_m"], 4)
    cached_cost = round(
        row["mean_cached_input_tokens_m"] * pricing["cached_input_rmb_per_m"], 4
    )
    output_cost = round(row["mean_output_tokens_m"] * pricing["output_rmb_per_m"], 4)
    return {
        "mean_input_cost_rmb": input_cost,
        "mean_cached_input_cost_rmb": cached_cost,
        "mean_output_cost_rmb": output_cost,
        "mean_cost_rmb": round(input_cost + cached_cost + output_cost, 4),
    }


def _attach_pricing(
    token_efficiency: dict[str, Any], participants: dict[str, Any]
) -> dict[str, Any]:
    participant_prices: dict[str, dict[str, Any]] = {}
    for identifier, player in participants.items():
        model = str(player.get("model", "")).split("/")[-1]
        pricing = MODEL_PRICING.get(model)
        if pricing is None:
            continue
        participant_prices[identifier] = pricing

    for collection in (token_efficiency["entries"], token_efficiency["by_game"]):
        for row in collection:
            pricing = participant_prices.get(row["participant_id"])
            if pricing and all(
                key in row
                for key in (
                    "mean_input_tokens_m",
                    "mean_cached_input_tokens_m",
                    "mean_output_tokens_m",
                )
            ):
                row.update(_cost_breakdown(row, pricing))

    token_efficiency["pricing"] = {
        "as_of": PRICING_AS_OF,
        "currency": "CNY",
        "unit": "per 1M tokens",
        "usd_cny": USD_CNY,
        "models": MODEL_PRICING,
        "sources": PRICING_SOURCES,
        "assumptions": [
            "DeepSeek uses the published busy-hour rate (08:00–22:00 Asia/Shanghai).",
            "Qwen3.7 Plus uses the current promotional <=256K input tier.",
            "Output includes provider-reported reasoning tokens; reasoning is not added a second time.",
            "GPT prices are API-equivalent estimates converted at USD/CNY 6.7811; long-context and cache-write surcharges are not applied because per-request telemetry is unavailable.",
            "Provider telemetry is aggregated per successful session and may differ from an invoice.",
        ],
    }
    return token_efficiency


def _report_token_efficiency(report: Path, participants: dict[str, Any]) -> dict[str, Any]:
    report_html = report.read_text(encoding="utf-8")
    parser = _ReportTableParser()
    parser.feed(report_html)
    identifiers = {player.get("name"): identifier for identifier, player in participants.items()}

    frontier_rows = parser.tables.get("Elo 与平均总 token / session data", [])
    entries = []
    for row in frontier_rows:
        if len(row) < 9 or row[5] not in identifiers:
            continue
        entries.append(
            {
                "participant_id": identifiers[row[5]],
                "short_name": row[4],
                "successful_sessions": int(row[3]),
                "mean_total_tokens_m": _millions(row[6]),
                "median_total_tokens_m": _millions(row[7]),
                "efficiency_frontier": row[8] == "是",
            }
        )

    datasets = _artifact_datasets(report_html)
    elo_by_game = {
        (row["participant_id"], row["game"]): row
        for row in datasets.get("game_elo", [])
    }
    by_game = []
    for row in datasets.get("game_token_usage", []):
        identifier = row.get("participant_id")
        game = row.get("game")
        if identifier not in participants or not game:
            continue
        game_elo = elo_by_game.get((identifier, game), {})
        mean_input = row["avg_uncached_input_m"]
        mean_cached = row["avg_cached_input_m"]
        mean_output = row["avg_output_m"]
        by_game.append(
            {
                "participant_id": identifier,
                "game": game,
                "successful_sessions": row["sessions"],
                "mean_total_tokens_m": round(
                    mean_input + mean_cached + mean_output, 3
                ),
                "median_total_tokens_m": row["median_total_m"],
                "mean_input_tokens_m": mean_input,
                "mean_cached_input_tokens_m": mean_cached,
                # Provider output includes reasoning. Qwen's recovered total
                # omitted this subset, so rebuild the additive billable total
                # from the three non-overlapping components above.
                "mean_output_tokens_m": mean_output,
                "mean_reasoning_tokens_m": row.get("avg_reasoning_m", 0),
                "elo": game_elo.get("elo"),
                "elo_rank": game_elo.get("game_rank"),
            }
        )

    if not by_game:
        game_names = {"Splendor": "splendor", "7 Wonders": "seven_wonders", "Brass": "brass_birmingham"}
        game_rows = parser.tables.get("分游戏平均总 token / session data", [])
        for row in game_rows:
            if len(row) < 6 or row[3] not in identifiers or row[2] not in game_names:
                continue
            by_game.append(
                {
                    "participant_id": identifiers[row[3]],
                    "game": game_names[row[2]],
                    "successful_sessions": int(row[4]),
                    "mean_total_tokens_m": _millions(row[1]),
                    "median_total_tokens_m": _millions(row[5]),
                }
            )

    ranking_rows = datasets.get("ranking", [])
    if ranking_rows and by_game:
        game_rows_by_participant: dict[str, list[dict[str, Any]]] = {}
        for row in by_game:
            game_rows_by_participant.setdefault(row["participant_id"], []).append(row)
        entries = []
        for row in ranking_rows:
            participant_rows = game_rows_by_participant.get(row["participant_id"], [])
            sessions = sum(item["successful_sessions"] for item in participant_rows)
            if not sessions:
                continue

            def weighted(field: str) -> float:
                return round(
                    sum(item[field] * item["successful_sessions"] for item in participant_rows)
                    / sessions,
                    3,
                )

            mean_input = weighted("mean_input_tokens_m")
            mean_cached = weighted("mean_cached_input_tokens_m")
            mean_output = weighted("mean_output_tokens_m")
            mean_reasoning = weighted("mean_reasoning_tokens_m")
            entries.append(
                {
                    "participant_id": row["participant_id"],
                    "short_name": row["short_name"],
                    "successful_sessions": sessions,
                    "mean_total_tokens_m": round(mean_input + mean_cached + mean_output, 3),
                    "median_total_tokens_m": row["median_total_m"],
                    "mean_input_tokens_m": mean_input,
                    "mean_cached_input_tokens_m": mean_cached,
                    "mean_output_tokens_m": mean_output,
                    "mean_reasoning_tokens_m": mean_reasoning,
                    "efficiency_frontier": row["pareto"] == "是",
                }
            )

    if not entries:
        raise ValueError(f"Token efficiency table not found in {report}")
    return _attach_pricing({
        "source_report": report.name,
        "successful_sessions": sum(item["successful_sessions"] for item in entries),
        "coverage_rate": 1.0,
        "entries": entries,
        "by_game": by_game,
    }, participants)


def build_public_data(source: Path, report: Path | None = None) -> dict[str, Any]:
    summary = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    config = json.loads((source / "config.json").read_text(encoding="utf-8"))
    participants = {item["id"]: item["player"] for item in config.get("participants", [])}

    leaderboard = []
    for row in summary.get("leaderboard", []):
        player = participants.get(row["participant_id"], {})
        leaderboard.append(
            {
                **row,
                "display_name": player.get("name", row["participant_id"]),
                "backend": player.get("backend", "unknown"),
                "model": player.get("model", "unknown"),
            }
        )

    schedule = summary.get("schedule", {})
    public_data = {
        "schema_version": "agentbga.frontier12-pages.v1",
        "dataset_id": source.name,
        "tournament_id": summary.get("tournament_id")
        or schedule.get("tournament_id")
        or config.get("tournament_id"),
        "generated_at": summary.get("generated_at"),
        "results": summary.get("results", {}),
        "rating": summary.get("rating", {}),
        "schedule": {
            key: schedule.get(key)
            for key in (
                "appearances_per_condition",
                "matches",
                "pair_exposures",
                "participant_exposures",
                "participants",
                "seat_exposures_per_stratum",
                "strata",
            )
        },
        "leaderboard": leaderboard,
    }
    if report is not None:
        public_data["token_efficiency"] = _report_token_efficiency(report, participants)
    return public_data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Frontier12 result directory")
    parser.add_argument("output", type=Path, help="Public JSON destination")
    parser.add_argument("--report", type=Path, help="HTML analysis report with recovered token telemetry")
    args = parser.parse_args()

    public_data = build_public_data(args.source, args.report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
    temporary.write_text(
        json.dumps(public_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
