import json
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest import mock

from agentbga.agents import PlayerConfig
from agentbga.runner import run_match
from agentbga.store import Store
from agentbga.web import MatchHub, WebHandler, serve


class WebTests(unittest.TestCase):
    def test_harmonies_human_match_finishes_and_reopens(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'matches.sqlite3'
            hub=MatchHub(db)
            created=hub.create({'game':'harmonies','seed':17,'speed_ms':0,
                                'game_config':{'board_side':'B','nature_spirits':True},
                                'players':[{'name':'You','backend':'human'}]})
            match_id=created['match_id'];seen=set();deadline=time.monotonic()+15
            snapshot=created
            try:
                while time.monotonic()<deadline:
                    snapshot=hub.get(match_id)
                    if snapshot['status']=='finished':break
                    turn=snapshot.get('human_turn')
                    if turn:
                        actions=turn['legal_actions']
                        priority={'choose_spirit':0,'place_animal':1,'take_animal':2,'take_tokens':3,'place_token':4,'end_turn':5}
                        item=min(actions,key=lambda a:priority[a['action']['type']])
                        seen.add(item['action']['type'])
                        hub.submit_human_action(match_id,turn['seat'],turn['version'],item['id'])
                    else:
                        time.sleep(.005)
                self.assertEqual('finished',snapshot['status'])
                self.assertTrue({'choose_spirit','take_animal','take_tokens','place_token','end_turn'}<=seen)
                view=snapshot['views'][0]
                self.assertEqual('harmonies',view['game'])
                self.assertEqual(23,len(view['players'][0]['cells']))
                self.assertEqual('B',view['board_side'])
                self.assertIsInstance(view['solo_suns'],int)
                restored=MatchHub(db).get(match_id)
                self.assertEqual(snapshot['rankings'],restored['rankings'])
                self.assertEqual(view,restored['views'][0])
            finally:
                with hub.condition:
                    hub.matches[match_id]['running']=False
                    hub.condition.notify_all()

    def test_finished_ark_nova_match_reopens_with_rankings_and_final_board(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "matches.sqlite3"
            store = Store(database)
            match_id, _, _ = store.create(
                2, 12, "ark_nova", {"turn_limit": 8},
                rules_version="base-1.2-controlled-core.6",
            )
            players = [
                PlayerConfig.from_dict({"name": "A", "backend": "random"}, 0),
                PlayerConfig.from_dict({"name": "B", "backend": "random"}, 1),
            ]
            result = run_match(store, match_id, players, max_turns=20)
            expected_views = [
                store.game(match_id).observe(store.load(match_id)[1], seat)
                for seat in range(2)
            ]
            store.close()

            hub = MatchHub(database)
            restored = hub.get(match_id)

            self.assertEqual("finished", restored["status"])
            self.assertFalse(restored["paused"])
            self.assertEqual(result["rankings"], restored["rankings"])
            self.assertEqual(expected_views, restored["views"])
            self.assertNotIn("match_report", restored)
            events, running = hub.events_after(match_id, -1, wait=0)
            finished = [item["event"] for item in events if item["event"]["type"] == "match_finished"]
            self.assertFalse(running)
            self.assertEqual(1, len(finished))
            self.assertEqual(result["rankings"], finished[0]["rankings"])
            self.assertNotIn("match_report", finished[0])

    def test_official_solo_human_match_finishes_without_optional_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "matches.sqlite3"
            store = Store(database)
            try:
                match_id, _, _ = store.create(1, 42, "ark_nova")
                player = PlayerConfig.from_dict({"name": "Solo human", "backend": "human"}, 0)
                choices = []

                def choose(seat, version, observation, legal):
                    choices.append((seat, version))
                    return legal[0]["id"]

                result = run_match(
                    store, match_id, [player], max_turns=200, human_choice=choose,
                )
                final_state = store.load(match_id)[1]
                self.assertTrue(choices)
                self.assertEqual("finished", final_state["status"])
                self.assertEqual(result["version"], store.replay(match_id)[-1]["version"])
            finally:
                store.close()
            restored = MatchHub(database).get(match_id)
            self.assertEqual("base-1.2-faq-v2-map0.1", restored["rules_version"])
            self.assertEqual(result["rankings"], restored["rankings"])
            self.assertEqual("Solo human", restored["rankings"][0]["player"])
            self.assertTrue(restored["views"][0]["players"])
            self.assertNotIn("match_report", restored)

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
            self.assertEqual(["splendor", "azul", "ark_nova", "brass_birmingham", "castles_of_burgundy", "century_spice_road", "seven_wonders", "harmonies"],
                             [game["id"] for game in response["games"]])

    def test_seven_wonders_setup_snapshot_uses_game_renderer_contract(self):
        stopped = threading.Event()
        def fake_run(_store, _match_id, _players, **options):
            options["sink"]({"type": "match_failed", "error": "test stop"})
            stopped.set()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "agentbga.web.run_match", side_effect=fake_run,
        ):
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            created = hub.create({
                "game": "seven_wonders", "seed": 42,
                "players": [
                    {"name": "Giza", "backend": "random"},
                    {"name": "Babylon", "backend": "random"},
                    {"name": "Rhodos", "backend": "random"},
                ],
            })
            self.assertEqual("seven_wonders", created["game"])
            self.assertEqual("playable", created["game_description"]["implementation_status"])
            self.assertEqual("seven_wonders", created["views"][0]["game"])
            self.assertEqual(3, len(created["players"]))
            self.assertEqual(7, created["views"][0]["players"][0]["hand_count"])
            self.assertEqual([[], [], []], created["views"][0]["players"][0]["military_tokens_by_age"])
            for seat, view in enumerate(created["views"]):
                self.assertTrue(all("hidden" not in card for card in view["players"][seat]["hand"]))
                for other in range(3):
                    if other != seat:
                        self.assertTrue(all(card == {"hidden": True} for card in view["players"][other]["hand"]))
            self.assertTrue(stopped.wait(2))

    def test_azul_setup_snapshot_uses_game_renderer_contract(self):
        stopped = threading.Event()
        def fake_run(_store, _match_id, _players, **options):
            options["sink"]({"type": "match_failed", "error": "test stop"})
            stopped.set()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "agentbga.web.run_match", side_effect=fake_run,
        ):
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            created = hub.create({
                "game": "azul", "seed": 42,
                "players": [
                    {"name": "Red", "backend": "random"},
                    {"name": "Blue", "backend": "random"},
                ],
            })
            self.assertEqual("azul", created["game"])
            self.assertEqual("playable_beta", created["game_description"]["implementation_status"])
            self.assertEqual("azul", created["views"][0]["game"])
            self.assertEqual(5, len(created["views"][0]["factories"]))
            self.assertTrue(stopped.wait(2))

    def test_ark_nova_setup_snapshot_uses_game_renderer_contract(self):
        stopped = threading.Event()
        def fake_run(_store, _match_id, _players, **options):
            options["sink"]({"type": "match_failed", "error": "test stop"})
            stopped.set()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "agentbga.web.run_match", side_effect=fake_run,
        ):
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            created = hub.create({
                "game": "ark_nova", "seed": 42,
                "players": [
                    {"name": "Red", "backend": "random"},
                    {"name": "Blue", "backend": "random"},
                ],
            })
            self.assertEqual("ark_nova", created["game"])
            self.assertEqual("released", created["game_description"]["implementation_status"])
            self.assertEqual("active", created["status"])
            self.assertEqual("ark_nova", created["views"][0]["game"])
            self.assertEqual(
                "休息阶段固定流程",
                created["views"][0]["break_rules_summary"]["title_cn"],
            )
            self.assertIn(
                "estimated_total",
                created["views"][0]["players"][0]["next_break_projection"]["money_income"],
            )
            self.assertEqual("spectator", created["spectator_view"]["viewer_mode"])
            self.assertTrue(all(
                "hidden" not in card
                for player in created["spectator_view"]["players"]
                for card in player["initial_draw"] + player["final_scoring_cards"]
            ))
            self.assertEqual(
                {"hidden": True}, created["views"][0]["players"][1]["initial_draw"][0],
            )
            self.assertTrue(stopped.wait(2))

    def test_ark_nova_web_setup_supports_solo_difficulty_and_board_projection(self):
        stopped = threading.Event()

        def fake_run(_store, _match_id, _players, **options):
            options["sink"]({"type": "match_failed", "error": "test stop"})
            stopped.set()

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "agentbga.web.run_match", side_effect=fake_run,
        ):
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            created = hub.create({
                "game": "ark_nova", "seed": 43,
                "game_config": {"map": "map-0", "solo_starting_appeal": 10},
                "players": [{"name": "Solo", "backend": "human"}],
            })
            view = created["views"][0]
            self.assertEqual(1, created["game_description"]["players"]["minimum"])
            self.assertEqual(10, view["players"][0]["appeal"])
            self.assertEqual(10, view["solo_board"]["starting_appeal"])
            self.assertEqual([7, 6, 5, 4, 3, 2], view["solo_board"]["schedule"])
            self.assertEqual(7, view["solo_board"]["tokens_left"])
            self.assertTrue(stopped.wait(2))

    def test_web_create_can_select_an_exact_rules_version(self):
        stopped = threading.Event()

        def fake_run(_store, _match_id, _players, **options):
            options["sink"]({"type": "match_failed", "error": "test stop"})
            stopped.set()

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "agentbga.web.run_match", side_effect=fake_run,
        ):
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            created = hub.create({
                "game": "ark_nova",
                "rules_version": "base-1.2-controlled-core.6",
                "players": [
                    {"name": "Red", "backend": "random"},
                    {"name": "Blue", "backend": "random"},
                ],
            })
            self.assertEqual(
                "base-1.2-controlled-core.6",
                created["game_description"]["rules_version"],
            )
            self.assertEqual("base-1.2-controlled-core.6", created["rules_version"])
            self.assertTrue(stopped.wait(2))

    def test_brass_setup_snapshot_uses_game_renderer_contract(self):
        stopped = threading.Event()
        def fake_run(_store, _match_id, _players, **options):
            options["sink"]({"type": "match_failed", "error": "test stop"})
            stopped.set()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "agentbga.web.run_match", side_effect=fake_run,
        ):
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            created = hub.create({
                "game": "brass_birmingham", "seed": 42,
                "players": [
                    {"name": "Red", "backend": "random"},
                    {"name": "Blue", "backend": "random"},
                ],
            })
            self.assertEqual("brass_birmingham", created["game"])
            self.assertEqual("playable_beta", created["game_description"]["implementation_status"])
            self.assertEqual("brass_birmingham", created["views"][0]["game"])
            self.assertTrue(stopped.wait(2))

    def test_castles_of_burgundy_setup_snapshot_uses_game_renderer_contract(self):
        stopped = threading.Event()

        def fake_run(_store, _match_id, _players, **options):
            options["sink"]({"type": "match_failed", "error": "test stop"})
            stopped.set()

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "agentbga.web.run_match", side_effect=fake_run,
        ):
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            created = hub.create({
                "game": "castles_of_burgundy", "seed": 42,
                "players": [
                    {"name": "Burgundy", "backend": "random"},
                    {"name": "Loire", "backend": "random"},
                ],
            })
            self.assertEqual("castles_of_burgundy", created["game"])
            self.assertEqual("playable_beta", created["game_description"]["implementation_status"])
            self.assertEqual(37, len(created["views"][0]["players"][0]["duchy"]))
            self.assertEqual(6, len(created["views"][0]["depots"]))
            self.assertTrue(stopped.wait(2))

    def test_century_setup_snapshot_uses_game_renderer_contract(self):
        stopped = threading.Event()
        def fake_run(_store, _match_id, _players, **options):
            options["sink"]({"type": "match_failed", "error": "test stop"})
            stopped.set()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "agentbga.web.run_match", side_effect=fake_run,
        ):
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            created = hub.create({
                "game": "century_spice_road", "seed": 42,
                "players": [
                    {"name": "Red", "backend": "random"},
                    {"name": "Blue", "backend": "random"},
                    {"name": "Green", "backend": "random"},
                    {"name": "Gold", "backend": "random"},
                    {"name": "Brown", "backend": "random"},
                ],
            })
            self.assertEqual("century_spice_road", created["game"])
            self.assertEqual("playable", created["game_description"]["implementation_status"])
            self.assertEqual("century_spice_road", created["views"][0]["game"])
            self.assertEqual(5, len(created["players"]))
            self.assertEqual(6, len(created["views"][0]["merchant_market"]))
            self.assertTrue(stopped.wait(2))

    def test_ark_nova_controlled_core_requires_model_credentials_when_runnable(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("agentbga.web.run_match"):
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            with self.assertRaisesRegex(ValueError, "requires api_key"):
                hub.create({
                    "game": "ark_nova", "seed": 7,
                    "players": [
                        {"name": "Harness A", "backend": "opencode", "model": "model-a"},
                        {"name": "Harness B", "backend": "codex", "model": "model-b"},
                    ],
                })

    def test_ark_nova_random_match_launches_runner(self):
        launched = threading.Event()
        stopped = threading.Event()
        def fake_run(_store, _match_id, _players, **options):
            launched.set()
            options["sink"]({"type": "match_failed", "error": "test stop"})
            stopped.set()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "agentbga.web.run_match", side_effect=fake_run,
        ):
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            created = hub.create({
                "game": "ark_nova", "seed": 7,
                "players": [
                    {"name": "Random A", "backend": "random"},
                    {"name": "Random B", "backend": "random"},
                ],
            })
            self.assertEqual("active", created["status"])
            self.assertTrue(launched.wait(2))
            self.assertTrue(stopped.wait(2))
            deadline = time.monotonic() + 2
            while hub.events_after(created["match_id"], -1, wait=0)[1] and time.monotonic() < deadline:
                time.sleep(0.01)

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
                seen["reasoning_effort"] = players[0].reasoning_effort
                captured.set()
                sink({"type": "agent_stream", "version": 0, "seat": 0, "player": "API",
                      "backend": "codex", "attempt": 1, "channel": "reasoning", "delta": "thinking"})
                sink({"type": "match_failed", "error": "test stop"})

            with mock.patch("agentbga.web.run_match", side_effect=fake_run):
                created = MatchHub(db).create({
                    "players": [
                        {"name": "API", "backend": "codex", "model": "m",
                         "base_url": "https://example.test/v1", "api_key": "top-secret",
                         "reasoning_effort": "low"},
                        {"name": "Baseline", "backend": "random"},
                    ]
                })
                self.assertTrue(captured.wait(2))

            self.assertEqual("top-secret", seen["key"])
            self.assertEqual("low", seen["reasoning_effort"])
            self.assertNotIn("api_key", seen["public"])
            store = Store(db)
            try:
                persisted = json.dumps(store.players(created["match_id"]))
            finally:
                store.close()
            self.assertNotIn("top-secret", persisted)

    def test_codex_subscription_does_not_require_inline_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "matches.sqlite3"
            captured = threading.Event()
            seen = {}

            def fake_run(_store, _match_id, players, sink, turn_gate):
                seen["player"] = players[0]
                captured.set()
                sink({"type": "match_failed", "error": "test stop"})

            with mock.patch("agentbga.web.run_match", side_effect=fake_run):
                created = MatchHub(db).create({
                    "players": [
                        {"name": "Codex", "backend": "codex", "model": "gpt-test",
                         "auth_mode": "subscription"},
                        {"name": "Baseline", "backend": "random"},
                    ]
                })
                self.assertTrue(captured.wait(2))

            self.assertEqual("subscription", seen["player"].auth_mode)
            self.assertIsNone(seen["player"].api_key)
            store = Store(db)
            try:
                persisted = store.players(created["match_id"])[0]
            finally:
                store.close()
            self.assertEqual("subscription", persisted["auth_mode"])
            self.assertNotIn("api_key_env", persisted)

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

    def test_failed_active_match_can_restart_with_retained_player_configs(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = MatchHub(Path(directory) / "matches.sqlite3")
            calls = 0
            second_run = threading.Event()
            finish_second_run = threading.Event()
            fake_done = threading.Event()

            def fake_run(_store, _match_id, players, sink, **_options):
                nonlocal calls
                calls += 1
                self.assertEqual(["random", "human"], [player.backend for player in players])
                if calls == 2:
                    second_run.set()
                    finish_second_run.wait(2)
                sink({"type": "match_failed", "error": "test stop"})
                if calls == 2:
                    fake_done.set()

            with mock.patch("agentbga.web.run_match", side_effect=fake_run):
                created = hub.create({"players": [
                    {"name": "Baseline", "backend": "random"},
                    {"name": "Human", "backend": "human"},
                ]})
                deadline = time.monotonic() + 2
                while hub.get(created["match_id"])["running"] and time.monotonic() < deadline:
                    time.sleep(0.01)
                stopped = hub.get(created["match_id"])
                self.assertFalse(stopped["running"])

                resumed = hub.set_paused(created["match_id"], False)

                self.assertTrue(resumed["running"])
                self.assertTrue(second_run.wait(2))
                finish_second_run.set()
                self.assertTrue(fake_done.wait(2))
                time.sleep(0.05)

    def test_persisted_model_match_requires_fresh_credentials_before_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "matches.sqlite3"
            store = Store(database)
            match_id, _, _ = store.create(2, 9)
            stored_players = [
                PlayerConfig.from_dict({
                    "name": "API", "backend": "openai", "model": "m",
                }, 0),
                PlayerConfig.from_dict({"name": "Baseline", "backend": "random"}, 1),
            ]
            store.set_players(match_id, [player.public_dict() for player in stored_players])
            store.close()

            hub = MatchHub(database)
            hub.watch(match_id)
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
                "agentbga.web.run_match",
            ) as run:
                with self.assertRaisesRegex(ValueError, "fresh ephemeral credentials"):
                    hub.set_paused(match_id, False)
            self.assertEqual("spectator", hub.get(match_id)["mode"])
            run.assert_not_called()
            with hub.condition:
                hub.matches[match_id]["running"] = False
                hub.condition.notify_all()
            time.sleep(0.4)

    def test_persisted_model_match_resumes_with_fresh_matching_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "matches.sqlite3"
            store = Store(database)
            match_id, _, _ = store.create(2, 9)
            stored_players = [
                PlayerConfig.from_dict({
                    "name": "API", "backend": "openai", "model": "m",
                }, 0),
                PlayerConfig.from_dict({"name": "Baseline", "backend": "random"}, 1),
            ]
            store.set_players(match_id, [player.public_dict() for player in stored_players])
            store.close()

            hub = MatchHub(database)
            hub.watch(match_id)
            started = threading.Event()

            def fake_run(_store, _match_id, players, sink, **_options):
                self.assertEqual("fresh-key", players[0].api_key)
                started.set()
                sink({"type": "match_failed", "error": "test stop"})

            with mock.patch("agentbga.web.run_match", side_effect=fake_run):
                resumed = hub.set_paused(match_id, False, resume_players=[
                    {
                        "name": "API", "backend": "openai", "model": "m",
                        "api_key": "fresh-key",
                    },
                    {"name": "Baseline", "backend": "random"},
                ])
                self.assertEqual("live", resumed["mode"])
                self.assertTrue(started.wait(2))
                deadline = time.monotonic() + 2
                while hub.get(match_id)["running"] and time.monotonic() < deadline:
                    time.sleep(0.01)
                time.sleep(0.4)

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

    def test_multiple_human_seats_can_wait_on_the_same_snapshot(self):
        hub = MatchHub()
        match_id = "simultaneous-humans"
        with hub.condition:
            record = {
                "events": [], "snapshot": {"match_id": match_id}, "running": True,
                "paused": False, "at_pause_gate": False,
                "human_pending": {}, "human_submissions": {},
            }
            record["snapshot"] = hub._with_runtime(record["snapshot"], record)
            hub.matches[match_id] = record

        configs = [
            PlayerConfig.from_dict({"name": f"Human {seat}", "backend": "human"}, seat)
            for seat in range(2)
        ]
        results: dict[int, str] = {}

        def wait_for(seat):
            results[seat] = hub._wait_for_human_action(
                match_id, configs, seat, 4, {"viewer_seat": seat},
                [{"id": f"a-{seat}", "action": {"type": "pass"}}],
            )

        threads = [threading.Thread(target=wait_for, args=(seat,)) for seat in range(2)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 2
        while len(hub.get(match_id)["human_turns"]) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual([0, 1], [item["seat"] for item in hub.get(match_id)["human_turns"]])
        hub.submit_human_action(match_id, 1, 4, "a-1")
        hub.submit_human_action(match_id, 0, 4, "a-0")
        for thread in threads:
            thread.join(timeout=2)
        self.assertEqual({0: "a-0", 1: "a-1"}, results)

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

    def test_watch_attaches_cli_match_and_follows_store_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "matches.sqlite3"
            store = Store(db)
            match_id, version, state = store.create(2, 42, "splendor")
            store.set_players(match_id, [
                PlayerConfig.from_dict(
                    {"name": "Grok 4.5", "backend": "grok", "model": "grok-4.5"}, 0,
                ).public_dict(),
                PlayerConfig.from_dict(
                    {"name": "Grok 4.6", "backend": "grok", "model": "grok-4.6"}, 1,
                ).public_dict(),
            ])
            action = store.game(match_id).legal_actions(state, 0)[0]["action"]
            version, state, _ = store.act(match_id, 0, version, action)
            store.close()

            hub = MatchHub(db)
            watched = hub.watch(match_id)
            self.assertEqual("spectator", watched["mode"])
            self.assertEqual("splendor", watched["game"])
            self.assertEqual(1, watched["turn_count"])
            self.assertEqual("Grok 4.5", watched["players"][0]["name"])
            self.assertEqual("Grok 4.6", watched["players"][1]["name"])
            with self.assertRaisesRegex(ValueError, "spectator"):
                hub.set_paused(match_id, True)

            store = Store(db)
            _, state, _ = store.load(match_id)
            action = store.game(match_id).legal_actions(state, 1)[0]["action"]
            store.act(match_id, 1, version, action)
            store.close()

            snapshot = hub.get(match_id)
            deadline = time.monotonic() + 2
            while snapshot["turn_count"] < 2 and time.monotonic() < deadline:
                time.sleep(0.05)
                snapshot = hub.get(match_id)
            self.assertEqual(2, snapshot["turn_count"])
            self.assertEqual(match_id, hub.list_tables()[0]["match_id"])
            self.assertEqual("spectator", hub.list_tables()[0]["mode"])

    def test_http_lists_and_watches_existing_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<h1>AgentBGA</h1>", encoding="utf-8")
            db = root / "matches.sqlite3"
            store = Store(db)
            match_id, _, _ = store.create(2, 7, "splendor")
            store.set_players(match_id, [
                {"name": "A", "backend": "random"},
                {"name": "B", "backend": "random"},
            ])
            store.close()
            handler = type("TestWebHandler", (WebHandler,), {
                "hub": MatchHub(db), "static_dir": root,
            })
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                listed = json.load(urllib.request.urlopen(base + "/api/matches"))
                self.assertEqual(match_id, listed["matches"][0]["match_id"])
                watched = json.load(urllib.request.urlopen(base + f"/api/matches/{match_id}"))
                self.assertEqual("spectator", watched["mode"])
                self.assertEqual("A", watched["players"][0]["name"])
            finally:
                server.shutdown()
                server.server_close()

    def test_web_server_refuses_nonlocal_bind_and_missing_build(self):
        with self.assertRaisesRegex(ValueError, "localhost"):
            serve("0.0.0.0", 8765)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, "npm run build"):
                serve("127.0.0.1", 8765, static_dir=directory)


if __name__ == "__main__":
    unittest.main()
