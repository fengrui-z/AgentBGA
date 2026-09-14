from __future__ import annotations

from collections import Counter, defaultdict
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "matched_harness_bridge", ROOT / "examples" / "matched_harness_bridge.py",
)
assert SPEC is not None and SPEC.loader is not None
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class MatchedHarnessBridgeTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(bridge.DEFAULT_CONFIG.read_text())
        self.schedule = bridge.build_schedule(self.config)

    def test_72_matches_with_nine_seat_balanced_pairs_per_cell(self):
        report = bridge.report(self.config, self.schedule)
        self.assertEqual((72, 36, 18), (
            report["matches"], report["paired_blocks"], report["shared_scenarios"],
        ))
        self.assertEqual(4, len(report["cells"]))
        for cell in report["cells"].values():
            self.assertEqual(18, cell["matches"])
            self.assertEqual(9, cell["paired_blocks"])
            self.assertEqual({0: 3, 1: 3, 2: 3}, cell["focal_blocks_by_seat"])
            self.assertEqual([4, 5], sorted(cell["first_arm_counts"].values()))

    def test_every_adjacent_pair_changes_only_focal_harness_and_identity(self):
        for index in range(0, 72, 2):
            a, b = self.schedule[index:index + 2]
            self.assertEqual(a["pair_id"], b["pair_id"])
            seat = a["focal_seat"]
            for field in ("game", "rules_version", "seed", "focal_seat", "run"):
                self.assertEqual(a[field], b[field])
            for other in range(3):
                if other != seat:
                    self.assertEqual(a["players"][other], b["players"][other])
            def shared(p):
                return {k: v for k, v in p.items()
                        if k not in {"name", "backend", "participant_id"}}
            self.assertEqual(shared(a["players"][seat]), shared(b["players"][seat]))
            self.assertEqual({-1, 1}, {a["contrast_sign"], b["contrast_sign"]})
            self.assertEqual(3, len({p["participant_id"] for p in a["players"]}))

    def test_models_share_scenarios_and_anchor_seats(self):
        self.assertEqual({"splendor", "seven_wonders"},
                         {match["game"] for match in self.schedule})
        scenarios = defaultdict(list)
        for match in self.schedule:
            scenarios[match["scenario_id"]].append(match)
        for matches in scenarios.values():
            self.assertEqual(4, len(matches))
            self.assertEqual(2, len({m["model_id"] for m in matches}))
            self.assertEqual(1, len({m["seed"] for m in matches}))
            self.assertEqual(1, len({m["focal_seat"] for m in matches}))
            anchor_seats = [
                [(i, p) for i, p in enumerate(m["players"]) if i != m["focal_seat"]]
                for m in matches
            ]
            self.assertTrue(all(a == anchor_seats[0] for a in anchor_seats))

    def test_routes_are_all_dashscope_and_deepseek_is_dated(self):
        models = Counter()
        for match in self.schedule:
            for player in match["players"]:
                self.assertEqual("https://dashscope.aliyuncs.com/compatible-mode/v1",
                                 player["base_url"])
                self.assertEqual("DASHSCOPE_API_KEY", player["api_key_env"])
                models[player["model"]] += 1
        self.assertEqual({"qwen3.8-max": 108, "deepseek-v4-flash-0731": 108}, models)

    def test_schedule_is_reproducible_and_order_seed_preserves_scenarios(self):
        self.assertEqual(self.schedule, bridge.build_schedule(self.config))
        changed = copy.deepcopy(self.config)
        changed["schedule"]["order_seed"] += 1
        other = bridge.build_schedule(changed)
        def key(m):
            return m["pair_id"], m["arm"], m["seed"], m["focal_seat"]
        self.assertEqual(set(map(key, self.schedule)), set(map(key, other)))
        self.assertNotEqual(list(map(key, self.schedule)), list(map(key, other)))

    def test_arm_overrides_cannot_silently_change_route_or_effort(self):
        for field in ("base_url", "model", "reasoning_effort"):
            changed = copy.deepcopy(self.config)
            changed["models"][0]["arms"][1][field] = "changed"
            with self.assertRaisesRegex(ValueError, "only harness"):
                bridge.build_schedule(changed)

    def test_pinned_engines_create_identical_start_states_for_each_pair(self):
        from agentbga.registry import get_game

        for index in range(0, len(self.schedule), 2):
            a, b = self.schedule[index:index + 2]
            game = get_game(a["game"], a["rules_version"])
            state_a = game.setup(3, a["seed"], None)
            state_b = game.setup(3, b["seed"], None)
            self.assertEqual(game.state_hash(state_a), game.state_hash(state_b))
            self.assertEqual(a["rules_version"], state_a["rules_version"])

    def test_wrong_size_and_cross_match_memory_rejected(self):
        changed = copy.deepcopy(self.config)
        changed["expected_matches"] = 108
        with self.assertRaisesRegex(ValueError, "computed size"):
            bridge.build_schedule(changed)
        changed = copy.deepcopy(self.config)
        changed["anchors"][0]["player"]["series_id"] = "leaky"
        with self.assertRaisesRegex(ValueError, "cross-match"):
            bridge.build_schedule(changed)

    def test_exported_commands_and_players_are_cli_compatible(self):
        from agentbga.agents import load_players_config
        from agentbga.cli import build_parser

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "plan"
            bridge.export(self.config, self.schedule, output)
            commands = json.loads((output / "commands.json").read_text())
            self.assertEqual(72, len(commands))
            parser = build_parser()
            for match, command in zip(self.schedule, commands):
                args = parser.parse_args(command["argv"][3:])
                self.assertEqual(match["seed"], args.seed)
                self.assertEqual(match["rules_version"], args.rules_version)
                players = load_players_config(args.players_config)
                self.assertEqual(3, len(players))
                self.assertEqual(match["players"][match["focal_seat"]]["model"],
                                 players[match["focal_seat"]].model)
            with self.assertRaisesRegex(ValueError, "must be empty"):
                bridge.export(self.config, self.schedule, output)


if __name__ == "__main__":
    unittest.main()
