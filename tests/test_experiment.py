from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from agentbga.cli import main
from agentbga.experiment import RESULTS_SCHEMA, run_experiment, schedule_experiment, validate_experiment


def random_competitor(identifier: str) -> dict:
    return {"id": identifier, "player": {"name": identifier.upper(), "backend": "random"}}


class ExperimentTests(unittest.TestCase):
    def test_duel_schedule_pairs_seeds_and_seat_orders(self):
        manifest = {
            "schema_version": "agentbga.experiment.v1",
            "experiment_id": "duel-one",
            "mode": "duel",
            "games": ["splendor"],
            "competitors": [random_competitor("alpha"), random_competitor("beta")],
            "schedule": {"seeds": [11, 12]},
        }
        validate_experiment(manifest)
        schedule = schedule_experiment(manifest)
        self.assertEqual(4, len(schedule))
        self.assertEqual(["alpha", "beta"], [item.id for item in schedule[0].competitors])
        self.assertEqual(["beta", "alpha"], [item.id for item in schedule[1].competitors])
        self.assertEqual([11, 11, 12, 12], [item.seed for item in schedule])

    def test_tournament_uses_all_cyclic_seat_rotations(self):
        manifest = {
            "schema_version": "agentbga.experiment.v1",
            "experiment_id": "league-one",
            "mode": "tournament",
            "games": ["splendor"],
            "competitors": [random_competitor(name) for name in ("a", "b", "c", "d")],
            "schedule": {"seeds": [7], "player_counts": [3]},
        }
        schedule = schedule_experiment(manifest)
        # C(4, 3) groups, with three cyclic seat orders each.
        self.assertEqual(12, len(schedule))
        first_group = schedule[:3]
        self.assertEqual(
            [["a", "b", "c"], ["b", "c", "a"], ["c", "a", "b"]],
            [[item.id for item in match.competitors] for match in first_group],
        )

    def test_series_memory_follows_participant_while_seats_alternate(self):
        manifest = {
            "schema_version": "agentbga.experiment.v1",
            "experiment_id": "adapt-one",
            "mode": "series",
            "games": ["splendor"],
            "competitors": [
                {"id": "learner", "player": {
                    "name": "Learner", "backend": "minimal", "model": "model-a",
                }, "memory": {"scope": "series"}},
                {"id": "control", "player": {
                    "name": "Control", "backend": "minimal", "model": "model-b",
                }, "memory": {"scope": "match"}},
            ],
            "series": {"length": 3, "replicates": 2},
            "schedule": {"seeds": [10, 11, 12]},
        }
        schedule = schedule_experiment(manifest)
        self.assertEqual(6, len(schedule))
        self.assertEqual(
            ["learner", "control"], [item.id for item in schedule[0].competitors]
        )
        self.assertEqual(
            ["control", "learner"], [item.id for item in schedule[1].competitors]
        )
        self.assertEqual("adapt-one:splendor:r1", schedule[0].series_id)
        self.assertEqual("adapt-one:splendor:r2", schedule[3].series_id)

    def test_results_are_emitted_atomically_every_n_matches(self):
        manifest = {
            "schema_version": "agentbga.experiment.v1",
            "experiment_id": "duel-results",
            "mode": "duel",
            "games": ["splendor"],
            "competitors": [random_competitor("alpha"), random_competitor("beta")],
            "schedule": {"seeds": [3, 4]},
            "results": {"emit_every": 2},
        }
        with tempfile.TemporaryDirectory() as directory:
            result = run_experiment(manifest, directory, max_turns=250)
            self.assertEqual(RESULTS_SCHEMA, result["schema_version"])
            self.assertTrue(result["complete"])
            self.assertEqual(4, result["summary"]["completed_matches"])
            self.assertTrue((Path(directory) / "latest.json").is_file())
            self.assertTrue((Path(directory) / "final.json").is_file())
            self.assertTrue((Path(directory) / "results-000002.json").is_file())
            self.assertTrue((Path(directory) / "results-000004.json").is_file())
            self.assertFalse((Path(directory) / "latest.json.tmp").exists())
            loaded = json.loads((Path(directory) / "final.json").read_text())
            self.assertEqual(4, len(loaded["matches"]))
            self.assertEqual(64, len(loaded["integrity"]["content_digest"]))

    def test_cli_validates_experiment_manifest(self):
        manifest = {
            "schema_version": "agentbga.experiment.v1",
            "experiment_id": "duel-cli",
            "mode": "duel",
            "games": ["splendor"],
            "competitors": [random_competitor("alpha"), random_competitor("beta")],
            "schedule": {"seeds": [5]},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment.json"
            path.write_text(json.dumps(manifest))
            output = StringIO()
            with redirect_stdout(output):
                code = main(["experiment", "validate", "--config", str(path)])
            self.assertEqual(0, code)
            self.assertEqual(2, json.loads(output.getvalue())["data"]["scheduled_matches"])


if __name__ == "__main__":
    unittest.main()
