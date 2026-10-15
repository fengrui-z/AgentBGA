from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "tournament.py"


class TournamentCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_missing_endpoint_is_rejected_before_credentials_or_matches(self):
        result = self.run_cli("--seeds", "0")
        self.assertEqual(2, result.returncode)
        self.assertIn("--base-url", result.stderr)
        self.assertNotIn("OPENAI_API_KEY", result.stderr)

    def test_explicit_endpoint_reaches_credential_check(self):
        result = self.run_cli("--base-url", "https://gateway.example/v1", "--seeds", "0")
        self.assertEqual(1, result.returncode)
        self.assertIn("OPENAI_API_KEY not set", result.stderr)


if __name__ == "__main__":
    unittest.main()
