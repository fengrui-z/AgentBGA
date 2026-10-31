import json
from pathlib import Path
import tempfile
import unittest

from agentbga.agents import PlayerConfig
from agentbga.baselines import build_baseline
from agentbga.experiment import run_experiment, validate_experiment
from agentbga.registry import get_game
from agentbga.store import Store
from agentbga.web import MatchHub


class BaselineIntegrationTests(unittest.TestCase):
    def test_web_resume_preserves_parameters_without_credentials(self):
        raw = [
            {"name": "A", "backend": "ismcts", "algorithm_params": {"seed": 12}},
            {"name": "B", "backend": "greedy"},
        ]
        configs = MatchHub._player_configs(raw, minimum=2, maximum=2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.db"
            store = Store(path)
            mid, _, _ = store.create(2, 42)
            store.set_players(mid, [p.public_dict() for p in configs])
            store.close()
            hub = MatchHub(path)
            self.assertEqual(configs, hub._resume_player_configs(mid, None))
            raw[0]["algorithm_params"]["seed"] = 13
            with self.assertRaisesRegex(ValueError, "persisted"):
                hub._resume_player_configs(mid, raw)

    def test_experiment_records_baseline_metadata_and_paired_seats(self):
        manifest = {
            "schema_version": "agentbga.experiment.v1",
            "experiment_id": "baseline-test",
            "mode": "duel",
            "games": ["splendor"],
            "schedule": {"seeds": [42]},
            "competitors": [
                {
                    "id": b,
                    "player": {
                        "name": b,
                        "backend": b,
                        "algorithm_params": {"max_candidates": 8},
                    },
                }
                for b in ("greedy", "heuristic")
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            result = run_experiment(manifest, directory)
            self.assertEqual(2, result["summary"]["completed_matches"])
            for row in result["matches"]:
                metrics = row["result"]["baseline_metrics"]["players"]
                self.assertEqual(2, len(metrics))
                self.assertTrue(
                    all(p["decisions"] > 0 and p["fallbacks"] == 0 for p in metrics)
                )
                self.assertTrue(
                    all(p["algorithm_params"]["max_candidates"] == 8 for p in metrics)
                )
        manifest["games"] = ["seven_wonders"]
        with self.assertRaisesRegex(ValueError, "player count"):
            validate_experiment(manifest)

    def test_resume_reconstructs_same_decision_stream(self):
        game = get_game("splendor")
        state = game.setup(2, 42)
        for backend in ("greedy", "heuristic", "ismcts"):
            params = {"max_candidates": 4, "time_limit_ms": 0}
            if backend == "ismcts":
                params.update(iterations=8, max_steps=4)
            config = PlayerConfig.from_dict(
                {"name": backend, "backend": backend, "algorithm_params": params}, 0
            )
            a = build_baseline(config, game, 0)
            b = build_baseline(config, game, 0)
            a.bind(state, 19)
            b.bind(json.loads(json.dumps(state)), 19)
            observation = game.observe(state, 0)
            legal = game.legal_actions(state, 0)
            self.assertEqual(
                a.choose(observation, legal)[0], b.choose(observation, legal)[0]
            )
