from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import random
import tempfile
import time
import unittest

from agentbga import carcassonne as c
from agentbga.agent_context import prepare_seat_context
from agentbga.carcassonne.catalog import oriented
from agentbga.legal_action_query import query_actions
from agentbga.store import ConflictError, Store
from agentbga.web import MatchHub


def graph_state(tiles, tokens=(), players=3):
    """Small topological fixtures, independent of the draw/starting-tile protocol."""
    state = c.new_game(players, 1)
    state["board"] = {}
    counts = Counter()
    for code, x, y, rotation in tiles:
        counts[code] += 1
        state["board"][f"{x},{y}"] = {"tile_id": f"{code}-{counts[code]}", "x": x, "y": y, "rotation": rotation}
    state["meeples"] = [{"tile": key, "feature": feature, "seat": seat} for key, feature, seat in tokens]
    for player in state["players"]:
        player["meeples_available"] -= sum(m["seat"] == player["seat"] for m in state["meeples"])
    return state


def draw(state, tile_id):
    if state["current_tile"]:
        state["deck"].append(state["current_tile"])
    state["deck"].remove(tile_id)
    state["current_tile"] = tile_id
    c.validate_state(state)


def act(state, **action):
    return c.apply_action(state, state["active_seat"], action)


class CarcassonneTests(unittest.TestCase):
    def test_catalog_counts_and_port_partition_for_every_rotation(self):
        self.assertEqual(72, len(c.TILES))
        self.assertEqual("D-1", c.START_TILE)
        self.assertEqual(dict(zip("ABCDEFGHIJKLMNOPQRSTUVWX", (2, 4, 1, 4, 5, 2, 1, 3, 2, 3, 3, 3, 2, 3, 2, 3, 1, 3, 2, 1, 8, 9, 4, 1))),
                         {code: tile["count"] for code, tile in c.CATALOG.items()})
        self.assertEqual(10, sum(tile["count"] * sum(f["shields"] for f in tile["features"]) for tile in c.CATALOG.values()))
        for code in c.CATALOG:
            for rotation in range(4):
                tile = oriented(code, rotation)
                fields = [p for f in tile["features"] if f["kind"] == "field" for p in f["ports"]]
                self.assertEqual(sorted(fields), [p for p in range(8) if tile["edges"][p // 2] != "city"])
                for edge, kind in enumerate(tile["edges"]):
                    if kind != "field":
                        self.assertEqual(1, sum(edge in f["ports"] for f in tile["features"] if f["kind"] == kind))
                for f in tile["features"]:
                    for city in f.get("cities", []):
                        self.assertTrue(any(g["id"] == city and g["kind"] == "city" for g in tile["features"]))

    def test_setup_seed_and_validation(self):
        for players in range(2, 6):
            state = c.new_game(players, 42)
            self.assertEqual(70, len(state["deck"]))
            self.assertEqual(state, c.new_game(players, 42))
            self.assertEqual([7] * players, [p["meeples_available"] for p in state["players"]])
            c.validate_state(json.loads(json.dumps(state)))
        for players in (0, 1, 6, True, 2.0):
            with self.assertRaises(c.RuleError):
                c.new_game(players, 0)
        with self.assertRaises(c.RuleError):
            c.new_game(2, 0, {"river": True})

    def test_observations_hide_draw_order_seed_and_are_independent(self):
        state = c.new_game(2, 31)
        other = deepcopy(state)
        other["deck"].reverse()
        other["seed"] = 432
        for seat in range(2):
            view = c.observe(state, seat)
            self.assertEqual(view, c.observe(other, seat))
            self.assertNotIn("seed", view)
            self.assertNotIn("deck", view)
            view["board"][0]["features"][0]["ports"].clear()
            view["players"][0]["score"] = 400
        self.assertEqual(0, state["players"][0]["score"])
        self.assertEqual([0], c.CATALOG["D"]["features"][0]["ports"])

    def test_placement_matches_all_neighbors_and_requires_an_edge(self):
        state = c.new_game(2, 1)
        draw(state, "E-1")
        for invalid in ({"x": 1, "y": 1, "rotation": 0}, {"x": 0, "y": 0, "rotation": 0},
                        {"x": 0, "y": -1, "rotation": 0}, {"x": 0, "y": -1, "rotation": True},
                        {"x": 0, "y": -1, "rotation": 2.0}, {"x": 0, "y": -1, "rotation": 4}):
            before = c.state_hash(state)
            with self.assertRaises(c.RuleError):
                act(state, type="place_tile", **invalid)
            self.assertEqual(before, c.state_hash(state))
        with self.assertRaises(c.RuleError):
            c.apply_action(state, 1, c.legal_actions(state, 0)[0]["action"])
        self.assertEqual([], c.legal_actions(state, 1))
        with self.assertRaises(c.RuleError):
            c.legal_actions(state, -1)
        # Empty center has road on its west neighbor and city on its north neighbor.
        probe = graph_state([("U", -1, 0, 1), ("E", 0, -1, 2)])
        self.assertFalse(any(a["x"] == a["y"] == 0 for a in c.placements(probe, "U-2")))
        self.assertTrue(any(a["x"] == a["y"] == 0 for a in c.placements(probe, "D-2")))

    def test_claim_newly_completed_city_before_scoring_and_return_follower(self):
        state = c.new_game(2, 1)
        draw(state, "E-1")
        state, events = act(state, type="place_tile", x=0, y=-1, rotation=2)
        self.assertEqual("place_meeple", state["phase"])
        self.assertEqual(0, state["active_seat"])
        self.assertFalse(any(e["type"] == "feature_scored" for e in events))
        self.assertIn({"type": "place_meeple", "feature": "c0"}, [a["action"] for a in c.legal_actions(state, 0)])
        state, events = act(state, type="place_meeple", feature="c0")
        self.assertEqual(4, state["players"][0]["score"])
        self.assertEqual(7, state["players"][0]["meeples_available"])
        self.assertEqual([], state["meeples"])
        self.assertEqual(1, state["active_seat"])
        self.assertEqual(1, sum(e["type"] == "feature_scored" for e in events))
        c._score_features(state, [])
        self.assertEqual(4, state["players"][0]["score"])

    def test_no_direct_claim_of_occupied_feature_including_own_followers(self):
        state = c.new_game(2, 1)
        draw(state, "U-1")
        state, _ = act(state, type="place_tile", x=1, y=0, rotation=1)
        state, _ = act(state, type="place_meeple", feature="r0")
        draw(state, "U-2")
        state, _ = act(state, type="place_tile", x=2, y=0, rotation=1)
        for seat in (0, 1):
            state["active_seat"] = seat
            self.assertNotIn({"type": "place_meeple", "feature": "r0"}, [a["action"] for a in c.legal_actions(state, seat)])
        state["players"][1]["meeples_available"] = 0
        self.assertEqual([{"type": "skip_meeple"}], [a["action"] for a in c.legal_actions(state, 1)])

    def test_disconnected_cities_and_crossroads_stay_separate(self):
        for code, expected in (("H", 2), ("I", 2), ("F", 1), ("N", 1)):
            state = graph_state([(code, 0, 0, 0)])
            self.assertEqual(expected, sum(f["kind"] == "city" for f in c.feature_graph(state)[0]))
        for code, expected in (("L", 3), ("W", 3), ("X", 4)):
            self.assertEqual(expected, sum(f["kind"] == "road" for f in c.feature_graph(graph_state([(code, 0, 0, 0)]))[0]))
        self.assertEqual(1, sum(f["kind"] == "field" for f in c.feature_graph(graph_state([("A", 0, 0, 0)]))[0]))
        self.assertEqual(2, sum(f["kind"] == "field" for f in c.feature_graph(graph_state([("S", 0, 0, 0)]))[0]))

    def test_shield_city_completion_majority_and_full_ties(self):
        tiles = [("F", 0, 0, 0), ("E", -1, 0, 1), ("E", 1, 0, 3)]
        for tokens, scores in [
            ([("0,0", "c0", 0), ("-1,0", "c0", 1)], [8, 8, 0]),
            ([("0,0", "c0", 0), ("-1,0", "c0", 0), ("1,0", "c0", 1)], [8, 0, 0]),
        ]:
            state = graph_state(tiles, tokens)
            c._score_features(state, [])
            self.assertEqual(scores, [p["score"] for p in state["players"]])
            self.assertEqual([7, 7, 7], [p["meeples_available"] for p in state["players"]])

    def test_reconnected_segments_count_a_tile_once_and_fields_deduplicate_cities(self):
        tiles = [("H", 0, 0, 0), ("N", -1, 0, 0), ("N", -1, -1, 1),
                 ("F", 0, -1, 0), ("N", 1, -1, 2), ("M", 1, 0, 3)]
        state = graph_state(tiles, [("0,0", "f0", 0), ("0,-1", "c0", 1)])
        components, lookup = c.feature_graph(state)
        city = components[lookup["0,0:c0"]]
        self.assertEqual(lookup["0,0:c0"], lookup["0,0:c1"])
        self.assertTrue(city["complete"])
        self.assertEqual(6, len(city["tiles"]))
        self.assertEqual(16, city["points"])
        field = components[lookup["0,0:f0"]]
        self.assertEqual([city["id"]], field["adjacent_cities"])
        c._score_features(state, [])
        self.assertEqual([0, 16, 0], [p["score"] for p in state["players"]])
        self.assertEqual(1, len(state["meeples"]))
        c._score_features(state, [], final=True)
        self.assertEqual([3, 16, 0], [p["score"] for p in state["players"]])

    def test_road_loop_and_reconnected_junction_count_once(self):
        tiles = [("W", 0, 0, 0), ("V", -1, 0, 2), ("V", -1, -1, 3),
                 ("U", 0, -1, 1), ("V", 1, -1, 0), ("V", 1, 0, 1)]
        state = graph_state(tiles, [("0,0", "r0", 0), ("0,-1", "r0", 1)])
        components, lookup = c.feature_graph(state)
        self.assertEqual(lookup["0,0:r0"], lookup["0,0:r2"])
        self.assertNotEqual(lookup["0,0:r0"], lookup["0,0:r1"])
        c._score_features(state, [])
        self.assertEqual([6, 6, 0], [p["score"] for p in state["players"]])
        loop = graph_state([("V", 0, 0, 3), ("V", 1, 0, 0), ("V", 1, 1, 1), ("V", 0, 1, 2)], [("0,0", "r0", 0)])
        c._score_features(loop, [])
        self.assertEqual(4, loop["players"][0]["score"])

    def test_fields_connect_across_correct_side_of_road_and_score_only_finished_cities(self):
        state = graph_state([("D", 0, 0, 0), ("E", 0, -1, 2), ("U", 1, 0, 1)],
                            [("0,-1", "f0", 0), ("1,0", "f1", 1)])
        components, lookup = c.feature_graph(state)
        self.assertEqual(lookup["0,0:f0"], lookup["1,0:f1"])
        self.assertNotEqual(lookup["0,0:f1"], lookup["1,0:f1"])
        c._score_features(state, [])
        self.assertEqual(2, len(state["meeples"]))
        c._score_features(state, [], final=True)
        self.assertEqual([3, 3, 0], [p["score"] for p in state["players"]])
        unfinished = graph_state([("E", 0, 0, 0)], [("0,0", "f0", 0)])
        c._score_features(unfinished, [], final=True)
        self.assertEqual(0, unfinished["players"][0]["score"])

    def test_merged_fields_award_majority_and_full_ties(self):
        tiles = [("D", 0, 0, 0), ("E", 0, -1, 2), ("U", 1, 0, 1), ("U", 2, 0, 1)]
        for tokens, expected in [
            ([("0,0", "f0", 0), ("1,0", "f1", 1)], [3, 3, 0]),
            ([("0,0", "f0", 0), ("1,0", "f1", 1), ("2,0", "f1", 0)], [3, 0, 0]),
        ]:
            state = graph_state(tiles, tokens)
            c._score_features(state, [], final=True)
            self.assertEqual(expected, [p["score"] for p in state["players"]])

    def test_monastery_scoring_counts_diagonals_and_final_incomplete_features(self):
        tiles = [("B", 0, 0, 0), ("B", -1, -1, 0), ("B", 1, -1, 0), ("B", 1, 1, 0),
                 ("A", -1, 1, 1), ("E", 0, -1, 0), ("E", 1, 0, 1), ("E", 0, 1, 2), ("E", -1, 0, 3)]
        state = graph_state(tiles, [("0,0", "m0", 0)])
        c._score_features(state, [])
        self.assertEqual(9, state["players"][0]["score"])
        state = graph_state(tiles[:4], [("0,0", "m0", 0)])
        c._score_features(state, [])
        self.assertEqual(0, state["players"][0]["score"])
        c._score_features(state, [], final=True)
        self.assertEqual(4, state["players"][0]["score"])
        state = graph_state([("F", 0, 0, 0), ("U", 0, 1, 1)], [("0,0", "c0", 0), ("0,1", "r0", 1)])
        c._score_features(state, [], final=True)
        self.assertEqual([2, 1, 0], [p["score"] for p in state["players"]])

    def test_unplaceable_tile_redraws_for_same_seat_and_exhaustion_finishes(self):
        state = graph_state([("B", 0, 0, 0)])
        state["deck"] = ["B-2", "C-1"]
        state["current_tile"] = None
        events = []
        c._draw(state, events)
        self.assertEqual(["C-1"], state["discarded"])
        self.assertEqual("B-2", state["current_tile"])
        self.assertEqual(0, state["active_seat"])
        self.assertEqual(["tile_discarded", "tile_drawn"], [e["type"] for e in events])
        state["deck"] = ["C-1"]
        c._draw(state, [])
        self.assertEqual("finished", state["status"])

    def test_final_tile_allows_follower_then_final_scoring_and_shared_victory(self):
        state = c.new_game(2, 1)
        draw(state, "E-1")
        # Controlled late-game fixture preserves physical inventory in the discard pile.
        state["discarded"].extend(state["deck"])
        state["deck"] = []
        state, _ = act(state, type="place_tile", x=0, y=1, rotation=1)
        self.assertEqual("active", state["status"])
        state, events = act(state, type="place_meeple", feature="c0")
        self.assertEqual("finished", state["status"])
        self.assertEqual(1, state["players"][0]["score"])
        self.assertEqual([], c.legal_actions(state, state["active_seat"]))
        self.assertTrue(any(e.get("final") for e in events))
        state["players"][1]["score"] = 1
        self.assertEqual([1, 1], [r["rank"] for r in c.rankings(state)])

    def test_validator_detects_corrupted_inventory_and_geometry(self):
        for corrupt in (lambda s: s["deck"].pop(), lambda s: s["players"][0].update(meeples_available=6),
                        lambda s: s["board"]["0,0"].update(rotation=1)):
            state = c.new_game(2, 1)
            corrupt(state)
            with self.assertRaises(AssertionError):
                c.validate_state(state)

    def test_all_player_counts_finish_deterministically_with_conservation(self):
        for players in range(2, 6):
            for seed in range(6):
                state = c.new_game(players, seed)
                rng = random.Random(seed + 7)
                replay = deepcopy(state)
                while state["status"] == "active":
                    action = rng.choice(c.legal_actions(state, state["active_seat"]))["action"]
                    seat = state["active_seat"]
                    before = c.state_hash(state)
                    next_state, events = c.apply_action(state, seat, action)
                    self.assertEqual(before, c.state_hash(state))
                    state = next_state
                    replay, replay_events = c.apply_action(replay, seat, action)
                    self.assertEqual(events, replay_events)
                    self.assertEqual(state, replay)
                    self.assertLessEqual(state["turn_count"], 142)
                self.assertEqual(72, len(state["board"]) + len(state["discarded"]))
                self.assertEqual([7] * players, [p["meeples_available"] for p in state["players"]])


class CarcassonneIntegrationTests(unittest.TestCase):
    def test_seat_query_supports_negative_coordinates_and_preserves_ids(self):
        state = c.new_game(2, 7)
        draw(state, "E-1")
        with tempfile.TemporaryDirectory() as directory:
            context = prepare_seat_context(Path(directory) / "context.json", match_id="test", seat=0,
                                           version=0, observation=c.observe(state, 0), legal=c.legal_actions(state, 0))
            page = query_actions(context, {"filters": {"y": -1, "rotation": 2}})
            self.assertTrue(page["actions"])
            self.assertTrue(all(a["y"] == -1 and a["rotation"] == 2 for a in page["actions"]))
            self.assertEqual({a["id"] for a in c.legal_actions(state, 0) if a["action"]["y"] == -1 and a["action"]["rotation"] == 2},
                             {a["id"] for a in page["actions"]})

    def test_store_full_match_replay_and_stale_action_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "matches.sqlite3")
            self.addCleanup(store.close)
            match_id, version, state = store.create(5, 17, "carcassonne")
            rng = random.Random(33)
            while state["status"] == "active":
                action = rng.choice(c.legal_actions(state, state["active_seat"]))["action"]
                version, state, _ = store.act(match_id, state["active_seat"], version, action)
            with self.assertRaises(ConflictError):
                store.act(match_id, 0, 0, {"type": "skip_meeple"})
            frames = store.replay(match_id)
            self.assertEqual(version + 1, len(frames))
            self.assertEqual(c.state_hash(state), frames[-1]["state_hash"])
            self.assertEqual(c.RULES_VERSION, store.rules_version(match_id))

    def test_web_human_game_finishes_and_reopens(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "matches.sqlite3"
            hub = MatchHub(db)
            snapshot = hub.create({"game": "carcassonne", "seed": 17, "speed_ms": 0,
                                   "players": [{"name": f"Human {i}", "backend": "human"} for i in range(2)]})
            match_id, rng = snapshot["match_id"], random.Random(5)
            seen = set()
            deadline = time.monotonic() + 20
            try:
                while time.monotonic() < deadline:
                    snapshot = hub.get(match_id)
                    if snapshot["status"] == "finished":
                        break
                    turn = snapshot.get("human_turn")
                    if turn:
                        choice = rng.choice(turn["legal_actions"])
                        seen.add(choice["action"]["type"])
                        hub.submit_human_action(match_id, turn["seat"], turn["version"], choice["id"])
                    else:
                        time.sleep(.002)
                self.assertEqual("finished", snapshot["status"])
                self.assertEqual({"place_tile", "place_meeple", "skip_meeple"}, seen)
                restored = MatchHub(db).get(match_id)
                self.assertEqual(snapshot["rankings"], restored["rankings"])
                self.assertEqual(snapshot["views"], restored["views"])
            finally:
                with hub.condition:
                    hub.matches[match_id]["running"] = False
                    hub.condition.notify_all()
