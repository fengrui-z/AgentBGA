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
    def test_games_endpoint_lists_registered_renderers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok")
            handler = type(
                "TestWebHandler", (WebHandler,),
                {"hub": MatchHub(root / "matches.sqlite3"), "static_dir": root},
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                response = json.load(urllib.request.urlopen(
                    f"http://127.0.0.1:{server.server_port}/api/games"
                ))
            finally:
                server.shutdown()
                server.server_close()
            self.assertEqual(["splendor", "ark_nova"], [game["id"] for game in response["games"]])

    def test_ark_nova_setup_snapshot_uses_game_renderer_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            created = hub.create({
                "game": "ark_nova", "seed": 42,
                "players": [
                    {"name": "Red", "backend": "random"},
                    {"name": "Blue", "backend": "random"},
                ],
            })
            self.assertEqual("ark_nova", created["game"])
            self.assertEqual("setup_only", created["game_description"]["implementation_status"])
            self.assertEqual("setup", created["status"])
            self.assertFalse(hub.events_after(created["match_id"], -1, wait=0)[1])
            self.assertEqual("ark_nova", created["views"][0]["game"])

    def test_ark_nova_setup_does_not_require_or_launch_model_credentials(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("agentbga.web.run_match") as run:
            created = MatchHub(Path(directory) / "matches.sqlite3").create({
                "game": "ark_nova", "seed": 7,
                "players": [
                    {"name": "Harness A", "backend": "opencode", "model": "model-a"},
                    {"name": "Harness B", "backend": "codex", "model": "model-b"},
                ],
            })
            self.assertEqual("setup", created["status"])
            run.assert_not_called()

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

            def fake_run(_store, _match_id, players, sink, turn_gate):
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

            def fake_run(_store, _match_id, _players, sink, turn_gate):
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

            hub.matches[created["match_id"]]["running"] = True
            hub._publish(created["match_id"], {
                "type": "harness_tool_result", "seat": 0, "tool": "observe", "result": {"large": True},
            })
            events, _ = hub.events_after(created["match_id"], -1, wait=0)
            tool_result = next(item for item in events if item["event"]["type"] == "harness_tool_result")
            self.assertNotIn("snapshot", tool_result)

    def test_pause_waits_at_turn_boundary_and_resume_releases_match(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            model_started = threading.Event()
            may_finish_turn = threading.Event()
            reached_next_turn = threading.Event()

            def fake_run(_store, _match_id, _players, sink, turn_gate):
                turn_gate()
                model_started.set()
                may_finish_turn.wait(2)
                sink({"type": "turn", "version": 1, "seat": 0, "player": "API",
                      "backend": "openai", "action": {"type": "pass"}})
                turn_gate()
                reached_next_turn.set()
                sink({"type": "match_failed", "error": "test stop"})

            with mock.patch("agentbga.web.run_match", side_effect=fake_run):
                created = hub.create({"players": [
                    {"name": "API", "backend": "openai", "model": "m", "api_key": "test"},
                    {"name": "Baseline", "backend": "random"},
                ]})
                self.assertTrue(model_started.wait(2))
                requested = hub.set_paused(created["match_id"], True)
                self.assertTrue(requested["paused"])
                self.assertTrue(requested["pause_pending"])
                may_finish_turn.set()

                deadline = time.monotonic() + 2
                while hub.get(created["match_id"])["pause_pending"] and time.monotonic() < deadline:
                    time.sleep(0.01)
                paused = hub.get(created["match_id"])
                self.assertTrue(paused["paused"])
                self.assertFalse(paused["pause_pending"])
                self.assertFalse(reached_next_turn.is_set())

                resumed = hub.set_paused(created["match_id"], False)
                self.assertFalse(resumed["paused"])
                self.assertTrue(reached_next_turn.wait(2))
                deadline = time.monotonic() + 2
                while hub.events_after(created["match_id"], -1, wait=0)[1] and time.monotonic() < deadline:
                    time.sleep(0.01)

    def test_model_player_requires_nonempty_key(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            with self.assertRaisesRegex(ValueError, "requires api_key"):
                hub.create({"players": [
                    {"name": "API", "backend": "openai", "model": "m", "api_key": ""},
                    {"name": "Baseline", "backend": "random"},
                ]})

    def test_human_turn_waits_for_current_legal_action(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            completed = threading.Event()

            def fake_run(_store, _match_id, players, sink, turn_gate, human_choice):
                turn_gate()
                action_id = human_choice(
                    0, 0, {"viewer_seat": 0},
                    [{"id": "a-human", "action": {"type": "pass", "reason": "test"}}],
                )
                sink({"type": "turn", "version": 1, "seat": 0, "player": players[0].name,
                      "backend": "human", "action_id": action_id, "action": {"type": "pass"}})
                sink({"type": "match_failed", "error": "test stop"})
                completed.set()

            with mock.patch("agentbga.web.run_match", side_effect=fake_run):
                created = hub.create({"players": [
                    {"name": "You", "backend": "human"},
                    {"name": "Bot", "backend": "random"},
                ]})
                deadline = time.monotonic() + 2
                snapshot = hub.get(created["match_id"])
                while not snapshot["human_turn"] and time.monotonic() < deadline:
                    time.sleep(0.01)
                    snapshot = hub.get(created["match_id"])

                self.assertEqual("You", snapshot["human_turn"]["player"])
                with self.assertRaisesRegex(ValueError, "stale|another seat"):
                    hub.submit_human_action(created["match_id"], 1, 0, "a-human")
                with self.assertRaisesRegex(ValueError, "not legal"):
                    hub.submit_human_action(created["match_id"], 0, 0, "a-wrong")
                submitted = hub.submit_human_action(created["match_id"], 0, 0, "a-human")
                self.assertIsNone(submitted["human_turn"])
                self.assertTrue(completed.wait(2))

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

    def test_http_human_action_endpoint_validates_and_submits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<h1>AgentBGA</h1>", encoding="utf-8")
            hub = MatchHub(root / "matches.sqlite3")
            ready = threading.Event()
            finished = threading.Event()

            def fake_run(_store, _match_id, _players, sink, turn_gate, human_choice):
                turn_gate()
                ready.set()
                selected = human_choice(
                    0, 0, {"viewer_seat": 0},
                    [{"id": "a-http", "action": {"type": "pass", "reason": "test"}}],
                )
                sink({"type": "turn", "version": 1, "seat": 0, "backend": "human",
                      "action_id": selected, "action": {"type": "pass"}})
                sink({"type": "match_failed", "error": "test stop"})
                finished.set()

            with mock.patch("agentbga.web.run_match", side_effect=fake_run):
                created = hub.create({"players": [
                    {"name": "You", "backend": "human"},
                    {"name": "Bot", "backend": "random"},
                ]})
                handler = type("TestWebHandler", (WebHandler,), {"hub": hub, "static_dir": root})
                server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    self.assertTrue(ready.wait(2))
                    deadline = time.monotonic() + 2
                    while not hub.get(created["match_id"])["human_turn"] and time.monotonic() < deadline:
                        time.sleep(0.01)
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/matches/{created['match_id']}/action",
                        data=json.dumps({"seat": 0, "expected_version": 0, "action_id": "a-http"}).encode(),
                        headers={"Content-Type": "application/json"}, method="POST",
                    )
                    response = json.load(urllib.request.urlopen(request))
                finally:
                    server.shutdown()
                    server.server_close()
            self.assertIsNone(response["human_turn"])
            self.assertTrue(finished.wait(2))

    def test_web_server_refuses_nonlocal_bind_and_missing_build(self):
        with self.assertRaisesRegex(ValueError, "localhost"):
            serve("0.0.0.0", 8765)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, "npm run build"):
                serve("127.0.0.1", 8765, static_dir=directory)


if __name__ == "__main__":
    unittest.main()
