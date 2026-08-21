from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from agentbga.cli import main
from agentbga.experiment import (
    RESULTS_SCHEMA,
    SQLITE_INTEGER_MAX,
    run_experiment,
    schedule_experiment,
    validate_experiment,
)
from agentbga.memory import memory_identity, stable_session_id


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
        self.assertEqual(
            ["control", "learner"], [item.id for item in schedule[3].competitors]
        )
        self.assertEqual(
            {"learner": 3, "control": 3},
            {
                competitor: sum(
                    item.competitors[0].id == competitor for item in schedule
                )
                for competitor in ("learner", "control")
            },
        )

    def test_series_replicate_seeds_are_disjoint_for_wide_input_ranges(self):
        manifest = {
            "schema_version": "agentbga.experiment.v1",
            "experiment_id": "wide-seeds",
            "mode": "series",
            "games": ["splendor"],
            "competitors": [
                {"id": "alpha", "player": {
                    "name": "Alpha", "backend": "minimal", "model": "model-a",
                }, "memory": {"scope": "series"}},
                {"id": "beta", "player": {
                    "name": "Beta", "backend": "minimal", "model": "model-b",
                }},
            ],
            "series": {"length": 2, "replicates": 2},
            "schedule": {"seeds": [1, 1_000_001]},
        }
        schedule = schedule_experiment(manifest)
        self.assertEqual(
            [1, 1_000_001, 1_000_002, 2_000_002],
            [item.seed for item in schedule],
        )
        self.assertEqual(
            [1, 1_000_001, 1, 1_000_001],
            [item.base_seed for item in schedule],
        )
        self.assertEqual(len(schedule), len({item.seed for item in schedule}))

    def test_schedule_rejects_duplicate_and_overflowing_series_seeds(self):
        manifest = {
            "schema_version": "agentbga.experiment.v1",
            "experiment_id": "invalid-seeds",
            "mode": "series",
            "games": ["splendor"],
            "competitors": [
                {"id": "alpha", "player": {
                    "name": "Alpha", "backend": "minimal", "model": "model-a",
                }, "memory": {"scope": "series"}},
                {"id": "beta", "player": {
                    "name": "Beta", "backend": "minimal", "model": "model-b",
                }},
            ],
            "series": {"length": 2, "replicates": 2},
            "schedule": {"seeds": [4, 4]},
        }
        with self.assertRaisesRegex(ValueError, "must not contain duplicates"):
            schedule_experiment(manifest)
        manifest["schedule"]["seeds"] = [SQLITE_INTEGER_MAX - 1, SQLITE_INTEGER_MAX]
        with self.assertRaisesRegex(ValueError, "exceed SQLite"):
            schedule_experiment(manifest)

    def test_repeated_series_runs_use_distinct_private_memory_namespaces(self):
        manifest = {
            "schema_version": "agentbga.experiment.v1",
            "experiment_id": "isolated-series",
            "mode": "series",
            "games": ["splendor"],
            "competitors": [
                {"id": "learner", "player": {
                    "name": "Learner", "backend": "minimal", "model": "model-a",
                }, "memory": {"scope": "series"}},
                {"id": "control", "player": {
                    "name": "Control", "backend": "minimal", "model": "model-b",
                }},
            ],
            "series": {"length": 2},
            "schedule": {"seeds": [21, 22]},
        }
        captured: list[list] = []

        def fake_run(_store, match_id, players, **_kwargs):
            captured.append(players)
            return {"match_id": match_id, "status": "finished"}

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "agentbga.experiment.run_match", side_effect=fake_run,
        ):
            first = run_experiment(manifest, Path(directory) / "first")
            second = run_experiment(manifest, Path(directory) / "second")

        first_configs = [
            next(config for config in players if config.participant_id == "learner")
            for players in captured[:2]
        ]
        second_configs = [
            next(config for config in players if config.participant_id == "learner")
            for players in captured[2:]
        ]
        self.assertTrue(
            all(config.memory_namespace == first["run_id"] for config in first_configs)
        )
        self.assertTrue(
            all(config.memory_namespace == second["run_id"] for config in second_configs)
        )
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertNotIn("memory_namespace", first_configs[0].public_dict())

        root = Path("/benchmark-memory")
        first_identity = memory_identity(root, first_configs[0], "match-one", 0)
        same_run_identity = memory_identity(root, first_configs[1], "match-two", 1)
        repeated_identity = memory_identity(root, second_configs[0], "match-one", 0)
        self.assertEqual(first_identity.workspace, same_run_identity.workspace)
        self.assertEqual(stable_session_id(first_identity), stable_session_id(same_run_identity))
        self.assertNotEqual(first_identity.workspace, repeated_identity.workspace)
        self.assertNotEqual(stable_session_id(first_identity), stable_session_id(repeated_identity))
        self.assertEqual("isolated-series:splendor:r1", first_identity.scope_id)

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
