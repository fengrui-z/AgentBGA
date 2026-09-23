import json
import random
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agentbga import seven_wonders
from agentbga.agents import PlayerConfig
from agentbga.harness import HarnessAgent
from agentbga.rq2 import (
    analyze, canonical, export_checkpoint, history_context, load_plan, main, make_plan,
    pws, rebuild, run_lock, run_study, validate_manifest, write_json,
)
from agentbga.runner import run_match
from agentbga.seat_tool import call_tool
from agentbga.store import Store


ROOT = Path(__file__).resolve().parents[1]


def manifest():
    value = json.loads((ROOT / "examples/rq2-qwen-pilot.json").read_text())
    value["schedule"]["seeds"] = [101, 102, 103]
    value["games"] = ["seven_wonders"]
    value["anchors"] = [{"name": "a", "backend": "random"}, {"name": "b", "backend": "random"}]
    return value


def save_plan(path, value=None):
    plan = make_plan(value or manifest(), path)
    write_json(path / "plan.json", plan)
    return plan


def source_prefix(path, seed=101, rounds=2):
    store = Store(path)
    match_id, version, state = store.create(3, seed, "seven_wonders")
    game = store.game(match_id)
    for _ in range(rounds):
        choices = [(seat, game.legal_actions(state, seat)[0]["action"]) for seat in game.decision_seats(state)]
        for seat, action in choices:
            version, state, _ = store.act(match_id, seat, version, action)
    store.close()
    return match_id, version, state


class RQ2Tests(unittest.TestCase):
    def test_schedule_has_complete_matched_cells_and_balanced_seats(self):
        value = manifest()
        a = make_plan(value, ROOT)
        b = make_plan(value, ROOT)
        self.assertEqual(a, b)
        self.assertEqual(12, len(a["rows"]))
        for seed in value["schedule"]["seeds"]:
            block = [r for r in a["rows"] if r["seed"] == seed]
            self.assertEqual(4, len(block))
            self.assertEqual(1, len({r["focal_seat"] for r in block}))
            self.assertEqual(4, len({(r["model"], r["harness"]) for r in block}))
        self.assertEqual({0, 1, 2}, {r["focal_seat"] for r in a["rows"]})
        self.assertEqual(12, len({r["row_id"] for r in a["rows"]}))
        self.assertTrue(all(r["rules_version"] == seven_wonders.RULES_VERSION for r in a["rows"]))

    def test_rejects_secrets_unknown_models_unequal_seats_and_unresolved_confirmation(self):
        for mutate in (
            lambda v: v["models"][0].update(api_key="secret"),
            lambda v: v["models"][0].update(model="unknown"),
            lambda v: v["schedule"].update(seeds=[1, 1, 2]),
            lambda v: v["schedule"].update(seeds=[1, 2]),
            lambda v: v["schedule"].update(seeds=[True, 2, 3]),
            lambda v: v.update(stage="confirmatory"),
            lambda v: v["budget"].update(retries=1),
            lambda v: v["models"][0].update(base_url="https://host/v1?api_key=secret"),
        ):
            value = manifest()
            mutate(value)
            with self.assertRaises(ValueError):
                validate_manifest(value)

    def test_checkpoint_rebuild_is_exact_and_does_not_modify_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match_id, version, original = source_prefix(root / "source.db")
            checkpoint = export_checkpoint(root / "source.db", match_id, version, 0)
            destination = Store(root / "branch.db")
            new_id, state, history = rebuild(checkpoint, destination)
            self.assertNotEqual(new_id, match_id)
            self.assertEqual(original, state)
            self.assertEqual(checkpoint["state_hash"], destination.replay(new_id)[-1]["state_hash"])
            self.assertEqual(2, len(history))
            self.assertTrue(all(h["version"] < version for h in history))
            self.assertNotIn('"seed"', canonical(history))
            self.assertNotIn('"pending_choices"', canonical(history))
            for h in history:
                for player in h["observation"]["players"]:
                    if player["seat"] != 0:
                        self.assertTrue(all(card == {"hidden": True} for card in player["hand"]))
            # The copy can continue independently, and remains replayable.
            players = [PlayerConfig.from_dict({"name": str(s), "backend": "random"}, s) for s in range(3)]
            result = run_match(destination, new_id, players)
            self.assertEqual(3, len(result["rankings"]))
            destination.replay(new_id)
            destination.close()
            source = Store(root / "source.db")
            self.assertEqual(original, source.load(match_id)[1])
            source.close()

    def test_checkpoint_rejects_mid_simultaneous_boundary_and_corrupt_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.db"
            match_id, version, _ = source_prefix(path)
            with self.assertRaisesRegex(ValueError, "sealed"):
                export_checkpoint(path, match_id, version - 1, 2)
            checkpoint = export_checkpoint(path, match_id, version, 0)
            checkpoint["prefix"][0]["state_hash"] = "bad"
            with self.assertRaisesRegex(ValueError, "replay mismatch"):
                rebuild(checkpoint)

    def test_checkpoint_selection_uses_predeclared_focal_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.db"
            match_id, _, _ = source_prefix(path, rounds=4)
            checkpoint = export_checkpoint(path, match_id, None, 2, decision_index=3)
            self.assertEqual(6, checkpoint["version"])
            self.assertEqual(3, checkpoint["selection"]["decision_index"])
            with self.assertRaisesRegex(ValueError, "did not reach"):
                export_checkpoint(path, match_id, None, 2, decision_index=50)

    def test_checkpoint_plan_uses_one_source_per_balanced_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = manifest()
            value["checkpoint_files"] = []
            value["conditions"] = ["current_only", "seat_history"]
            for seat, seed in enumerate(value["schedule"]["seeds"]):
                ident, version, _ = source_prefix(root / "source.db", seed)
                path = root / f"{seed}.json"
                write_json(path, export_checkpoint(root / "source.db", ident, version, seat))
                value["checkpoint_files"].append(path.name)
            plan = make_plan(value, root)
            self.assertEqual(24, len(plan["rows"]))
            self.assertEqual(3, len(plan["checkpoints"]))
            value["checkpoint_files"].append(value["checkpoint_files"][0])
            with self.assertRaisesRegex(ValueError, "duplicate checkpoint"):
                make_plan(value, root)

    def test_smoke_is_complete_resumable_and_never_invokes_a_harness(self):
        with tempfile.TemporaryDirectory() as tmp, patch("agentbga.rq2.HarnessAgent") as factory:
            root = Path(tmp)
            plan = save_plan(root)
            first = run_study(root, max_matches=1, smoke=True)
            self.assertEqual(1, first["executed"])
            self.assertFalse(factory.called)
            second = run_study(root, max_matches=20, smoke=True)
            self.assertEqual(11, second["executed"])
            self.assertEqual(0, run_study(root, max_matches=1, smoke=True)["executed"])
            report = analyze(root, 100)
            self.assertTrue(report["smoke"])
            self.assertEqual(12, report["finished_first_attempt"])
            self.assertTrue(all(c["complete_first_attempt_blocks"] == 3 for c in report["contrasts"]))
            self.assertEqual(12, len(list((root / "attempts").glob("*/*.json"))))
            self.assertEqual(plan, load_plan(root))

    def test_failures_and_reruns_are_preserved_and_not_silently_imputed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_plan(root)
            with patch("agentbga.rq2.run_match", side_effect=RuntimeError("secret-token")):
                run_study(root, max_matches=1, smoke=True)
            failed = next((root / "attempts").glob("*/*.json"))
            initial = failed.read_text()
            self.assertNotIn("secret-token", initial)
            self.assertEqual("failed", json.loads(initial)["status"])
            run_study(root, max_matches=12, smoke=True, retry_failed=True)
            self.assertEqual(initial, failed.read_text())
            report = analyze(root, 100)
            self.assertEqual(11, report["finished_first_attempt"])
            self.assertEqual(13, report["attempts"])
            affected = [c for c in report["contrasts"] if c["complete_first_attempt_blocks"] < 3]
            self.assertTrue(affected)
            self.assertTrue(all(c["ci95_pp"] is None for c in affected))

    def test_plan_and_runtime_cannot_change_on_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_plan(root)
            with patch("agentbga.rq2.code_fingerprint", return_value="changed"):
                with self.assertRaisesRegex(ValueError, "source changed"):
                    load_plan(root)
            run_study(root, max_matches=1, smoke=True)
            with patch("agentbga.rq2._runtime_provenance", return_value={"smoke": False}):
                with self.assertRaisesRegex(ValueError, "runtime changed"):
                    run_study(root, max_matches=1)
            plan = json.loads((root / "plan.json").read_text())
            plan["rows"][0]["seed"] += 1
            write_json(root / "plan.json", plan)
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_plan(root)

    def test_execution_lock_prevents_duplicate_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with run_lock(root):
                with self.assertRaisesRegex(ValueError, "another process"):
                    with run_lock(root):
                        pass

    def test_history_prompt_never_silently_truncates(self):
        with self.assertRaisesRegex(ValueError, "reduce history_window"):
            history_context([{"observation": "x" * 100_000}], 6)

    def test_common_history_reaches_both_native_commands_and_traces(self):
        for backend in ("qwen", "opencode"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp, patch(
                "agentbga.harness.shutil.which", return_value=f"/bin/{backend}"
            ):
                config = PlayerConfig.from_dict({"name": backend, "backend": backend, "model": "qwen3.8-flash"}, 0)
                agent = HarnessAgent(config, "context-test", 0, runs_root=tmp, turn_context="SHARED HISTORY FACTS")
                legal = [{"id": "test-action", "action": {"type": "test"}}]

                def fake_run(command):
                    self.assertIn("SHARED HISTORY FACTS", command[-1])
                    call_tool(agent.session.runtime / "turn-context.json", "submit_action", {"action_id": "test-action"})
                    return "", "", 0

                with patch.object(agent, "_run", side_effect=fake_run):
                    action_id, _ = agent.choose({"game": "splendor", "state_version": 0, "turn_count": 0}, legal)
                self.assertEqual("test-action", action_id)
                trace = json.loads((agent.trace_dir / "turn-0000.json").read_text())
                self.assertIn("SHARED HISTORY FACTS", trace["prompt"]["user"])

    def test_analysis_computes_direct_model_interaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = save_plan(root)
            values = {("qwen3.8-flash", "opencode"): 0, ("qwen3.8-flash", "qwen"): .5,
                      ("qwen3.8-max", "opencode"): .25, ("qwen3.8-max", "qwen"): 1}
            for row in plan["rows"]:
                write_json(root / "attempts" / row["row_id"] / "0001.json", {
                    "plan_hash": plan["plan_hash"], "row_id": row["row_id"], "smoke": True,
                    "status": "finished", "pws": values[row["model"], row["harness"]],
                })
            report = analyze(root, 100)
            interaction = next(c for c in report["contrasts"] if c["direction"] == "difference in harness gains")
            self.assertEqual(-25, interaction["complete_case_mean_pp"])
            self.assertEqual([-25, -25], interaction["ci95_pp"])

    def test_fork_runner_injects_history_only_into_focal_and_keeps_memory_isolated(self):
        captured = []

        class FakeHarness:
            def __init__(self, config, ident, seat, **kwargs):
                captured.append((config, ident, seat, kwargs))
                self.rng = random.Random(seat)

            def choose(self, observation, legal, on_stream=None):
                return self.rng.choice(legal)["id"], {}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = manifest()
            value["conditions"] = ["current_only", "seat_history"]
            value["checkpoint_files"] = []
            for seat, seed in enumerate(value["schedule"]["seeds"]):
                ident, version, _ = source_prefix(root / "source.db", seed)
                path = root / f"checkpoint-{seed}.json"
                write_json(path, export_checkpoint(root / "source.db", ident, version, seat))
                value["checkpoint_files"].append(path.name)
            plan = save_plan(root, value)
            with patch("agentbga.rq2.HarnessAgent", FakeHarness), patch.dict(
                "os.environ", {"DASHSCOPE_API_KEY": "test-only-not-a-key"}
            ), patch("agentbga.rq2._runtime_provenance", return_value={"smoke": False, "executables": {}}):
                run_study(root, max_matches=24)
            self.assertEqual(24, len(captured))  # anchors are random
            self.assertEqual(24, len({ident for _, ident, _, _ in captured}))
            for row, (config, ident, seat, kwargs) in zip(plan["rows"], captured):
                self.assertEqual(row["focal_seat"], seat)
                self.assertIsNone(config.series_id)
                self.assertEqual(180, kwargs["timeout"])
                if row["condition"] == "seat_history":
                    self.assertIn("Historical observations", kwargs["turn_context"])
                    self.assertNotIn('"pending_choices"', kwargs["turn_context"])
                else:
                    self.assertEqual("", kwargs["turn_context"])
            report = analyze(root, 100)
            effects = [c for c in report["contrasts"] if c["condition"] == "history_interaction"]
            self.assertEqual(2, len(effects))
            self.assertTrue(all(c["complete_case_mean_pp"] == 0 for c in effects))

    def test_pws_ties_are_half_credit_not_rank_formula(self):
        self.assertEqual(.75, pws([{"seat": 0, "rank": 1}, {"seat": 1, "rank": 1}, {"seat": 2, "rank": 3}], 0))
        self.assertEqual(.5, pws([{"seat": s, "rank": 1} for s in range(3)], 0))

    def test_cli_plan_makes_no_calls(self):
        with tempfile.TemporaryDirectory() as tmp, patch("agentbga.rq2.HarnessAgent") as factory:
            root = Path(tmp)
            path = root / "manifest.json"
            write_json(path, manifest())
            self.assertEqual(0, main(["plan", str(path), "--out", str(root / "plan")]))
            self.assertFalse(factory.called)


if __name__ == "__main__":
    unittest.main()
