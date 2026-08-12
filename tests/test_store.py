import tempfile
import unittest
from pathlib import Path

from agentbga import splendor
from agentbga.store import ConflictError, Store


class StoreTests(unittest.TestCase):
    def test_create_act_and_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            match_id, version, state = store.create(2, 1)
            action = splendor.legal_actions(state, 0)[0]["action"]
            version, _, events = store.act(match_id, 0, version, action)
            self.assertEqual(1, version)
            self.assertTrue(events)
            with self.assertRaises(ConflictError):
                store.act(match_id, 1, 0, action)
            replay = store.replay(match_id)
            self.assertEqual(1, replay[-1]["version"])
            store.close()


if __name__ == "__main__":
    unittest.main()
