import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest import mock

from agentbga.store import Store
from agentbga.web import MatchHub, WebHandler, serve


class WebTests(unittest.TestCase):
    def test_random_match_streams_snapshots_until_finished(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            created = hub.create({
                "seed": 23,
                "speed_ms": 0,
                "players": [
                    {"name": "Red", "backend": "random"},
                    {"name": "Blue", "backend": "random"},
                ],
            })
            after = -1
            events = []
            deadline = time.monotonic() + 10
            running = True
            while running and time.monotonic() < deadline:
                batch, running = hub.events_after(created["match_id"], after, wait=0.25)
                events.extend(batch)
                if batch:
                    after = batch[-1]["seq"]

            self.assertFalse(running)
            self.assertEqual("match_finished", events[-1]["event"]["type"])
            self.assertEqual("finished", events[-1]["snapshot"]["status"])
            self.assertEqual(2, len(events[-1]["snapshot"]["views"]))
            self.assertEqual(["Red", "Blue"], [p["name"] for p in created["players"]])

    def test_inline_api_key_reaches_agent_but_is_not_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "matches.sqlite3"
            captured = threading.Event()
            seen = {}

            def fake_run(_store, _match_id, players, sink):
                seen["key"] = players[0].api_key
                seen["public"] = players[0].public_dict()
                captured.set()
                sink({"type": "agent_stream", "version": 0, "seat": 0, "player": "API",
                      "backend": "openai", "attempt": 1, "channel": "reasoning", "delta": "thinking"})
                sink({"type": "match_failed", "error": "test stop"})

            with mock.patch("agentbga.web.run_match", side_effect=fake_run):
                created = MatchHub(db).create({
                    "players": [
                        {"name": "API", "backend": "openai", "model": "m",
                         "base_url": "https://example.test/v1", "api_key": "top-secret"},
                        {"name": "Baseline", "backend": "random"},
                    ]
                })
                self.assertTrue(captured.wait(2))

            self.assertEqual("top-secret", seen["key"])
            self.assertNotIn("api_key", seen["public"])
            store = Store(db)
            try:
                persisted = json.dumps(store.players(created["match_id"]))
            finally:
                store.close()
            self.assertNotIn("top-secret", persisted)

    def test_stream_delta_does_not_duplicate_full_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            ready = threading.Event()

            def fake_run(_store, _match_id, _players, sink):
                sink({"type": "agent_started", "version": 0, "seat": 0, "player": "API",
                      "backend": "openai", "attempt": 1})
                sink({"type": "agent_stream", "version": 0, "seat": 0, "player": "API",
                      "backend": "openai", "attempt": 1, "channel": "content", "delta": "chunk"})
                sink({"type": "match_failed", "error": "test stop"})
                ready.set()

            with mock.patch("agentbga.web.run_match", side_effect=fake_run):
                created = hub.create({"players": [
                    {"name": "API", "backend": "openai", "model": "m", "api_key": "test"},
                    {"name": "Baseline", "backend": "random"},
                ]})
                self.assertTrue(ready.wait(2))
            events, _ = hub.events_after(created["match_id"], -1, wait=0)
            stream = next(item for item in events if item["event"]["type"] == "agent_stream")
            self.assertEqual("chunk", stream["event"]["delta"])
            self.assertNotIn("snapshot", stream)

    def test_model_player_requires_nonempty_key(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            with self.assertRaisesRegex(ValueError, "requires api_key"):
                hub.create({"players": [
                    {"name": "API", "backend": "openai", "model": "m", "api_key": ""},
                    {"name": "Baseline", "backend": "random"},
                ]})

    def test_http_health_and_static_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<h1>AgentBGA</h1>", encoding="utf-8")
            handler = type("TestWebHandler", (WebHandler,), {
                "hub": MatchHub(root / "matches.sqlite3"), "static_dir": root,
            })
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                health = json.load(urllib.request.urlopen(base + "/api/health"))
                page = urllib.request.urlopen(base + "/").read().decode()
            finally:
                server.shutdown()
                server.server_close()
            self.assertTrue(health["ok"])
            self.assertIn("AgentBGA", page)

    def test_web_server_refuses_nonlocal_bind_and_missing_build(self):
        with self.assertRaisesRegex(ValueError, "localhost"):
            serve("0.0.0.0", 8765)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, "npm run build"):
                serve("127.0.0.1", 8765, static_dir=directory)


if __name__ == "__main__":
    unittest.main()
