from __future__ import annotations

from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
import itertools
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from examples import qwen_codex_pilot
from examples.qwen_codex_pilot import build_schedule, load_config, write_scores


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "examples" / "qwen-codex-pilot.json"


class QwenCodexPilotTests(unittest.TestCase):
    def test_small_schedule_is_balanced_across_33_matches(self):
        config = load_config(CONFIG)
        schedule = build_schedule(config)
        self.assertEqual(6, len(config["participants"]))
        self.assertEqual(10, config["schedule"]["workers"])
        self.assertEqual(33, len(schedule))
        self.assertEqual({16}, set(Counter(
            identifier for match in schedule for identifier in match["participants"]
        ).values()))
        self.assertEqual({
            ("splendor", 2): 6,
            ("splendor", 3): 4,
            ("splendor", 4): 3,
            ("seven_wonders", 3): 4,
            ("seven_wonders", 4): 3,
            ("brass_birmingham", 2): 6,
            ("brass_birmingham", 3): 4,
            ("brass_birmingham", 4): 3,
        }, Counter((match["game"], match["player_count"]) for match in schedule))
        pair_exposure = Counter(
            tuple(sorted(pair))
            for match in schedule
            for pair in itertools.combinations(match["participants"], 2)
        )
        self.assertEqual(15, len(pair_exposure))
        self.assertEqual({6, 7}, set(pair_exposure.values()))
        self.assertEqual(
            {row["id"] for row in config["participants"]},
            {identifier for match in schedule[:4] for identifier in match["participants"]},
        )

    def test_matrix_prioritizes_qwen_and_uses_codex_subscription(self):
        config = load_config(CONFIG)
        qwen = [
            row for row in config["participants"]
            if str(row["player"].get("model", "")).lower().startswith("qwen")
        ]
        codex = [
            row for row in config["participants"] if row["player"]["backend"] == "codex"
        ]
        self.assertEqual(3, len(qwen))
        self.assertEqual({"qwen3.8-max", "qwen3.8-27B"}, {
            row["player"]["model"] for row in qwen
        })
        mimo = next(
            row for row in config["participants"]
            if row["player"]["model"] == "mimo-v2.5-pro"
        )
        self.assertEqual("pi", mimo["player"]["backend"])
        self.assertEqual("https://token-plan-cn.xiaomimimo.com/v1", mimo["player"]["base_url"])
        self.assertEqual("MIMO_API_KEY", mimo["player"]["api_key_env"])
        self.assertEqual({"gpt-5.6-sol", "gpt-5.6-luna"}, {
            row["player"]["model"] for row in codex
        })
        self.assertEqual({"subscription"}, {
            row["player"]["auth_mode"] for row in codex
        })
        self.assertTrue(all("api_key_env" not in row["player"] for row in codex))
        self.assertEqual({"pi", "opencode", "codex"}, {
            row["player"]["backend"] for row in config["participants"]
        })
        self.assertEqual({"pi", "opencode"}, {
            row["player"]["backend"]
            for row in qwen if row["player"]["model"] == "qwen3.8-max"
        })

    def test_failed_rows_remain_visible_in_score_artifacts(self):
        rows = [{
            "status": "error",
            "participants": [
                {"participant_id": "alpha", "seat": 0},
                {"participant_id": "beta", "seat": 1},
            ],
        }]
        with tempfile.TemporaryDirectory() as directory:
            leaderboard = write_scores(rows, Path(directory))
            self.assertEqual({1}, {row["failed_exposures"] for row in leaderboard})
            self.assertTrue((Path(directory) / "summary.json").is_file())
            self.assertTrue((Path(directory) / "leaderboard.csv").is_file())

    def test_runner_completes_schedule_with_ten_workers_and_incremental_jsonl(self):
        def fake_run_one(match, participants, _output, **_kwargs):
            participant_rows = [
                {"participant_id": identifier, "seat": seat}
                for seat, identifier in enumerate(match["participants"])
            ]
            return {
                "ordinal": match["ordinal"],
                "status": "ok",
                "game": match["game"],
                "seed": match["seed"],
                "player_count": match["player_count"],
                "participants": participant_rows,
                "result": {"rankings": [
                    {"seat": seat, "rank": seat + 1}
                    for seat in range(len(participant_rows))
                ]},
            }

        report = {
            "credentials": {
                "DASHSCOPE_API_KEY": {"configured": True},
                "MIMO_API_KEY": {"configured": True},
            },
            "codex_subscription": {"configured": True, "status": "Logged in using ChatGPT"},
            "harnesses": {
                name: {"path": f"/bin/{name}", "version": "test"}
                for name in ("codex", "opencode", "pi")
            },
            "endpoints": [],
        }
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(qwen_codex_pilot, "runtime_report", return_value=report), \
                mock.patch.object(qwen_codex_pilot, "run_one", side_effect=fake_run_one), \
                redirect_stdout(StringIO()):
            output = Path(directory) / "run"
            result = qwen_codex_pilot.command_run(SimpleNamespace(
                config=CONFIG,
                out=output,
                workers=10,
                limit=None,
                dry_run=False,
                overwrite=False,
            ))
            self.assertEqual(0, result)
            self.assertEqual(33, len((output / "matches.jsonl").read_text().splitlines()))
            self.assertEqual(33, len(qwen_codex_pilot.read_jsonl(output / "matches.jsonl")))
            self.assertTrue((output / "leaderboard.csv").is_file())


if __name__ == "__main__":
    unittest.main()
