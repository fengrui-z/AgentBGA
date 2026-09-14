from __future__ import annotations

import copy
import json
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from agentbga import longterm
from agentbga.agents import AgentError, PlayerConfig
from agentbga.harness import HarnessAgent
from agentbga.memory import memory_identity, stable_session_id
from agentbga.seat_tool import call_tool

ROOT = Path(__file__).resolve().parents[1]


class LocalHarness:
    """Offline agent: real games, deterministic random decisions, native-like storage."""

    created = []
    fail_review = False

    def __init__(self, config, match_id, seat, *, event_sink, timeout, runs_root):
        identity = memory_identity(runs_root, config, match_id, seat)
        identity.workspace.mkdir(parents=True, exist_ok=True)
        self.session = SimpleNamespace(workspace=identity.workspace, session_id=None)
        self.config = config
        self.seat = seat
        self.native_id = stable_session_id(identity)
        self.state_path = identity.workspace / "agentbga-harness-session.json"
        self.notes_path = identity.workspace / "strategy-notes.md"
        if self.state_path.exists():
            self.session.session_id = json.loads(self.state_path.read_text())["session_id"]
        self.notes_at_start = self.notes_path.read_text() if self.notes_path.exists() else ""
        self.rng = random.Random(91 + seat)
        self.event_sink = event_sink
        self.new_match_context = None
        self.created.append(self)

    def choose(self, observation, legal, on_stream=None):
        self.session.session_id = self.native_id
        self.state_path.write_text(json.dumps({"session_id": self.native_id}))
        purchases = [a for a in legal if a["action"]["type"].startswith("buy_")]
        return self.rng.choice(purchases or legal)["id"], {"session_id": self.native_id}

    def review_match(self, observation, feedback):
        self.notes_path.write_text(self.notes_at_start + "one completed game\n")
        if self.fail_review:
            raise AgentError("simulated review failure after memory mutation")
        self.feedback = feedback
        self.review_observation = observation
        return {"status": "ok", "session_id": self.session.session_id}

    def usage_summary(self):
        return {"available": False}


class LongtermTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "examples" / "splendor-longterm.json").read_text())
        LocalHarness.created = []
        LocalHarness.fail_review = False

    def test_schedules_replicates_seats_identity_and_seed_isolation(self):
        pilot = longterm.schedule(self.config, "pilot")
        main = longterm.schedule(self.config, "main")
        self.assertEqual((40, 240), (len(pilot), len(main)))
        self.assertEqual((4, 12), (len({r["series_id"] for r in pilot}),
                                   len({r["series_id"] for r in main})))
        self.assertFalse({r["seed"] for r in pilot} & {r["seed"] for r in main})
        for sid in {r["series_id"] for r in main}:
            rows = [r for r in main if r["series_id"] == sid]
            self.assertEqual(10, sum(r["persistent_seat"] == 0 for r in rows))
            self.assertEqual(1, len({r["persistent_identity"] for r in rows}))
            self.assertEqual(20, len({r["seed"] for r in rows}))
        for row in main:
            a, b = longterm.player_configs(self.config, row, "isolated-run")
            for key in ("backend", "model", "base_url", "api_key_env", "reasoning_effort"):
                self.assertEqual(getattr(a, key), getattr(b, key))
            self.assertEqual(1, sum(bool(p.series_id) for p in (a, b)))
        self.assertEqual(main, longterm.schedule(self.config, "main"))

    def test_native_memory_ownership_tracks_identity_not_seat_or_replicate(self):
        rows = longterm.schedule(self.config, "main")
        roots = []
        fresh = []
        for row in rows[:21]:
            players = longterm.player_configs(self.config, row, "run-a")
            seat = row["persistent_seat"]
            roots.append(memory_identity(Path("/isolated"), players[seat], str(row["ordinal"]), seat).workspace)
            fresh.append(memory_identity(Path("/isolated"), players[1-seat], str(row["ordinal"]), 1-seat).workspace)
        self.assertEqual(1, len(set(roots[:20])))
        self.assertNotEqual(roots[0], roots[20])
        self.assertEqual(21, len(set(fresh)))

    def test_actual_games_resume_at_boundary_and_fresh_notes_stay_empty(self):
        self.config["agents"] = self.config["agents"][:1]
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(longterm, "HarnessAgent", LocalHarness), \
                mock.patch.object(longterm, "runtime_signature", return_value={"test": "offline"}):
            out = Path(directory) / "trial"
            first = longterm.run(self.config, "pilot", out, limit_matches=2)
            checkpoint = json.loads((out / "checkpoint.json").read_text())
            second = longterm.run(self.config, "pilot", out, resume=True, limit_matches=2)
            self.assertEqual((2, 4), (first["reported"], second["reported"]))
            self.assertEqual(checkpoint["run_id"], json.loads((out / "checkpoint.json").read_text())["run_id"])
            persistent = [a for a in LocalHarness.created if a.config.series_id]
            fresh = [a for a in LocalHarness.created if not a.config.series_id]
            self.assertEqual([0, 1, 2, 3], [a.notes_at_start.count("completed") for a in persistent])
            self.assertTrue(all(not a.notes_at_start for a in fresh))
            self.assertEqual(1, len({a.session.session_id for a in persistent}))
            self.assertEqual(4, len({a.session.session_id for a in fresh}))
            self.assertEqual(8, len(list((out / "feedback").glob("*-seat-[01].json"))))
            self.assertEqual(8, len(list((out / "feedback").glob("*-notes.json"))))
            self.assertTrue((out / "trajectory.csv").is_file())
            self.assertTrue(all(len(a.feedback["rankings"]) == 2 for a in LocalHarness.created))
            self.assertTrue(all("persistent" not in a.new_match_context.lower() for a in LocalHarness.created))
            # A session or note disappearing must stop resumption before a call.
            persistent[-1].notes_path.unlink()
            with self.assertRaisesRegex(ValueError, "memory changed or is missing"):
                longterm.run(self.config, "pilot", out, resume=True)

    def test_failed_feedback_keeps_outcome_but_refuses_replay(self):
        self.config["agents"] = self.config["agents"][:1]
        LocalHarness.fail_review = True
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(longterm, "HarnessAgent", LocalHarness), \
                mock.patch.object(longterm, "runtime_signature", return_value={}):
            out = Path(directory) / "trial"
            with self.assertRaisesRegex(RuntimeError, "stopped at match 1"):
                longterm.run(self.config, "pilot", out)
            row = json.loads((out / "results" / "match-0001.json").read_text())
            self.assertTrue(row["terminal"])
            self.assertEqual("error", row["status"])
            with self.assertRaisesRegex(ValueError, "automatic replay refused"):
                longterm.run(self.config, "pilot", out, resume=True)

    def test_changed_protocol_and_inflight_invocation_refuse_resume(self):
        self.config["agents"] = self.config["agents"][:1]
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(longterm, "HarnessAgent", LocalHarness), \
                mock.patch.object(longterm, "runtime_signature", return_value={}):
            out = Path(directory) / "trial"
            longterm.run(self.config, "pilot", out, limit_matches=1)
            changed = copy.deepcopy(self.config)
            changed["run"]["timeout_seconds"] += 1
            with self.assertRaisesRegex(ValueError, "changed"):
                longterm.run(changed, "pilot", out, resume=True)
            p = out / "checkpoint.json"
            checkpoint = json.loads(p.read_text())
            checkpoint["status"] = "running"
            p.write_text(json.dumps(checkpoint))
            with self.assertRaisesRegex(ValueError, "automatic replay refused"):
                longterm.run(self.config, "pilot", out, resume=True)

    def test_result_tampering_is_detected_before_resuming_memory(self):
        self.config["agents"] = self.config["agents"][:1]
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(longterm, "HarnessAgent", LocalHarness), \
                mock.patch.object(longterm, "runtime_signature", return_value={}):
            out = Path(directory) / "trial"
            longterm.run(self.config, "pilot", out, limit_matches=1)
            path = out / "results" / "match-0001.json"
            row = json.loads(path.read_text())
            row["result"]["rankings"][0]["score"] = 999
            path.write_text(json.dumps(row))
            with self.assertRaisesRegex(ValueError, "history is inconsistent"):
                longterm.run(self.config, "pilot", out, resume=True)

    def test_stage_seed_overlap_and_overflow_are_rejected(self):
        self.config["stages"]["main"]["base_seed"] = self.config["stages"]["pilot"]["base_seed"]
        with self.assertRaisesRegex(ValueError, "disjoint"):
            longterm.schedule(self.config, "pilot")
        self.config["stages"]["main"]["base_seed"] = 2**63 - 1
        with self.assertRaisesRegex(ValueError, "SQLite"):
            longterm.schedule(self.config, "main")

    def test_replicates_restart_empty_and_completed_run_does_not_replay(self):
        self.config["agents"] = self.config["agents"][:1]
        self.config["stages"]["pilot"]["replicates"] = 2
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(longterm, "HarnessAgent", LocalHarness), \
                mock.patch.object(longterm, "runtime_signature", return_value={}):
            out = Path(directory) / "trial"
            summary = longterm.run(self.config, "pilot", out)
            self.assertEqual(20, summary["protocol_complete"])
            persistent = [a for a in LocalHarness.created if a.config.series_id]
            self.assertEqual([0, 0], [a.notes_at_start.count("completed") for a in persistent[::10]])
            self.assertNotEqual(persistent[0].session.session_id, persistent[10].session.session_id)
            count = len(LocalHarness.created)
            longterm.run(self.config, "pilot", out, resume=True)
            self.assertEqual(count, len(LocalHarness.created))

    def test_report_exposes_missing_games_and_treats_ties_as_half(self):
        plan = longterm.schedule(self.config, "pilot")[:10]
        rows = []
        for index, score in enumerate((1, 0, 0.5)):
            r = plan[index]
            own = r["persistent_seat"]
            ranks = [1, 2] if score == 1 else [2, 1] if score == 0 else [1, 1]
            rows.append({**r, "status": "ok", "terminal": True, "result": {"rankings": [
                {"seat": own, "rank": ranks[0]}, {"seat": 1-own, "rank": ranks[1]},
            ]}})
        window = longterm.summarize(rows, plan)["series"][0]["windows"]["games_1_10"]
        self.assertEqual(0.5, window["persistent_win_score_completed"])
        self.assertEqual([0.15, 0.85], window["win_score_bounds_all_scheduled"])
        self.assertFalse(window["complete_window"])

    def test_real_harness_review_has_terminal_context_and_no_legal_submission(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("shutil.which", return_value="/bin/fake"):
            player = PlayerConfig.from_dict({**self.config["agents"][0]["player"],
                                            "name": "Player A", "participant_id": "player-a"}, 0)
            agent = HarnessAgent(player, "terminal-test", 0, runs_root=directory)
            agent.session.session_id = "existing-native-session"
            captured = []

            def local_call(command):
                captured.append(command)
                context = agent.session.runtime / "turn-context.json"
                self.assertEqual([], json.loads(context.read_text())["legal_actions"])
                with self.assertRaises(ValueError):
                    call_tool(context, "submit_action", {"action_id": "stale"})
                call_tool(context, "write_notes", {"content": "Opponent tends to reserve."},
                          notes_root=agent.session.workspace)
                return "review complete", "", 0

            with mock.patch.object(agent, "_run", side_effect=local_call):
                result = agent.review_match({"game": "splendor", "state_version": 90, "turn_count": 90},
                                            {"rankings": [{"seat": 0, "rank": 1, "score": 15}]})
            self.assertEqual("ok", result["status"])
            trace = json.loads((agent.trace_dir / "post-match-0090.json").read_text())
            self.assertIn("Do not call submit_action", trace["prompt"]["user"])
            self.assertIsNone(trace["submission"])
            self.assertEqual("existing-native-session", trace["session_id"])


if __name__ == "__main__":
    unittest.main()
