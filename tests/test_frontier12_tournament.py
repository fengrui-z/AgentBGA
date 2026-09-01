from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples" / "frontier12_tournament.py"
SPEC = importlib.util.spec_from_file_location("frontier12_tournament", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
frontier12 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(frontier12)


class Frontier12TournamentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = frontier12.load_config(ROOT / "examples" / "frontier12-tournament.json")
        cls.schedule = frontier12.build_schedule(cls.config)
        cls.report = frontier12.schedule_report(cls.config, cls.schedule)

    def test_schedule_has_expected_size_and_strata(self):
        self.assertEqual(396, len(self.schedule))
        self.assertEqual({
            "splendor:2p": 72,
            "splendor:3p": 48,
            "splendor:4p": 36,
            "seven_wonders:3p": 48,
            "seven_wonders:4p": 36,
            "brass_birmingham:2p": 72,
            "brass_birmingham:3p": 48,
            "brass_birmingham:4p": 36,
        }, self.report["strata"])

    def test_every_participant_and_seat_is_balanced(self):
        exposures = self.report["participant_exposures"]
        self.assertEqual(96, exposures["minimum"])
        self.assertEqual(96, exposures["maximum"])
        self.assertTrue(self.report["seat_exposures_per_stratum"]["exact"])
        self.assertEqual(0, self.report["pair_exposures"]["zero_pairs"])

    def test_schedule_is_deterministic(self):
        repeated = frontier12.build_schedule(self.config)
        self.assertEqual(self.schedule, repeated)

    def test_kimi_endpoint_is_environment_backed(self):
        kimi = next(
            row for row in self.config["participants"]
            if row["id"] == "kimi-k27-code-opencode"
        )
        self.assertEqual("DASHSCOPE_KIMI_BASE_URL", kimi["player"]["base_url_env"])
        public_probe = frontier12._player_value(
            kimi["player"], require_environment=False,
        )
        self.assertNotIn("base_url_env", public_probe)

    def test_probe_covers_every_participant_in_four_matches(self):
        identifiers = {row["id"] for row in self.config["participants"]}
        probe = frontier12._participant_probe(self.schedule, identifiers, set())
        covered = {identifier for row in probe for identifier in row["participants"]}
        self.assertEqual(identifiers, covered)
        self.assertEqual(4, len(probe))

    def test_resume_requires_the_same_config_and_schedule(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            frontier12._prepare_output(
                output, self.config, self.schedule, resume=False,
            )
            frontier12._prepare_output(
                output, self.config, self.schedule, resume=True,
            )
            changed = {**self.config, "tournament_id": "different-id"}
            with self.assertRaisesRegex(ValueError, "config does not match"):
                frontier12._prepare_output(
                    output, changed, self.schedule, resume=True,
                )


if __name__ == "__main__":
    unittest.main()
