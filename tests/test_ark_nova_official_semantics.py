import unittest
from pathlib import Path

from agentbga.ark_nova_official import (
    ContentEntry,
    ContentManifest,
    ContentPack,
    EvaluationContext,
    SemanticEngine,
    SemanticRuleError,
    add_project_to_state,
    audit_content_pack,
    check_endgame_trigger,
    new_semantic_state,
    play_entry_semantics,
    present_entry,
    queue_break,
    score_game,
    support_project,
)


def effect(op: str, args: dict, timing: str = "immediate", **extra) -> dict:
    return {"op": op, "args": args, "timing": timing, **extra}


class ArkNovaOfficialSemanticTests(unittest.TestCase):
    def test_predicates_and_safe_value_expressions(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["players"][0]["money"] = 7
        state["players"][0]["tags"]["bear"] = 2
        context = EvaluationContext(
            state=state,
            actor_seat=0,
            card={"facts": {"required_money": 3}},
        )
        predicate = {
            "op": "all",
            "args": {"conditions": [
                {"op": "has_tag", "args": {"tag": "bear", "count": 2}},
                {
                    "op": "compare",
                    "args": {
                        "left": {"ref": "actor.money"},
                        "operator": ">=",
                        "right": {
                            "calc": "multiply",
                            "values": [{"ref": "card.facts.required_money"}, 2],
                        },
                    },
                },
            ]},
        }
        self.assertTrue(engine.evaluate(predicate, context))
        with self.assertRaisesRegex(SemanticRuleError, "not public"):
            engine.evaluate({
                "op": "compare",
                "args": {"left": {"ref": "target.hand"}, "operator": "==", "right": []},
            }, EvaluationContext(state=state, actor_seat=0, target_seat=1))

    def test_effect_queue_pauses_for_benefit_and_opponent_choices(self):
        engine = SemanticEngine()
        state = new_semantic_state(3)
        effects = [
            effect("gain_money", {"amount": 3}),
            effect("choose_one", {"prompt": "Choose benefit", "options": [
                {
                    "id": "appeal",
                    "label": "Appeal",
                    "effects": [effect("move_track", {"track": "appeal", "amount": 2})],
                },
                {
                    "id": "reputation",
                    "label": "Reputation",
                    "effects": [effect("move_track", {"track": "reputation", "amount": 1})],
                },
            ]}),
            effect("choose_opponent", {
                "prompt": "Choose affected zoo",
                "condition": {
                    "op": "compare",
                    "args": {"left": {"ref": "target.money"}, "operator": ">=", "right": 1},
                },
                "effects": [effect("lose_money", {"amount": 2}, "interaction")],
            }, "interaction"),
        ]
        state, first_events = engine.start_effects(
            state, 0, effects, source_id="ark-nova:test-card",
        )
        self.assertEqual(28, state["players"][0]["money"])
        self.assertEqual("Choose benefit", state["resolution"]["pending_choice"]["prompt"])
        self.assertEqual("money_changed", first_events[0]["type"])

        action = next(
            item for item in engine.legal_choice_actions(state, 0)
            if item["action"]["option_ids"] == ["appeal"]
        )["action"]
        state, _ = engine.submit_choice(
            state, 0, action["choice_id"], action["option_ids"],
        )
        self.assertEqual(2, state["players"][0]["tracks"]["appeal"])
        targets = engine.legal_choice_actions(state, 0)
        self.assertEqual([["seat-1"], ["seat-2"]], [item["action"]["option_ids"] for item in targets])

        selected = targets[1]["action"]
        state, events = engine.submit_choice(
            state, 0, selected["choice_id"], selected["option_ids"],
        )
        self.assertEqual(23, state["players"][2]["money"])
        self.assertIsNone(state["resolution"]["pending_choice"])
        self.assertFalse(state["resolution"]["queue"])
        self.assertTrue(any(item["type"] == "money_changed" for item in events))

    def test_milestone_effect_interrupts_remaining_effects(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["milestones"] = [{
            "id": "conservation-2-test",
            "track": "conservation",
            "at": 2,
            "scope": "player",
            "effects": [effect("choose_one", {"options": [
                {"id": "funding", "label": "Funding", "effects": [effect("gain_money", {"amount": 5})]},
                {"id": "reputation", "label": "Reputation", "effects": [
                    effect("move_track", {"track": "reputation", "amount": 1}),
                ]},
            ]})],
        }]
        state, _ = engine.start_effects(state, 0, [
            effect("move_track", {"track": "conservation", "amount": 3}),
            effect("gain_money", {"amount": 1}),
        ], source_id="ark-nova:test-project")
        self.assertEqual(3, state["players"][0]["tracks"]["conservation"])
        self.assertEqual(25, state["players"][0]["money"])
        self.assertEqual(["conservation-2-test"], state["players"][0]["claimed_milestones"])

        funding = engine.legal_choice_actions(state, 0)[0]["action"]
        state, _ = engine.submit_choice(
            state, 0, funding["choice_id"], funding["option_ids"],
        )
        self.assertEqual(31, state["players"][0]["money"])

    def test_ordered_break_uses_choice_window_income_trigger_and_reset(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["phase"] = "active"
        state["players"][0]["hand"] = [{"id": f"card-{index}"} for index in range(5)]
        state["players"][0]["action_cards"][0]["tokens"] = ["venom", "other"]
        state["players"][0]["association_workers"] = {
            "active": 0, "reserve": 3, "committed": ["worker-1"],
        }
        state["players"][0]["income"] = {"appeal": 8, "kiosks": 2, "other": 0}
        state["players"][1]["income"] = {"appeal": 6, "kiosks": 0, "other": 0}
        state["card_display"] = [{"id": f"display-{index}"} for index in range(6)]
        state["zoo_deck"] = [{"id": "deck-1"}, {"id": "deck-2"}]

        state, _ = engine.start_effects(state, 0, [
            effect("add_modifier", {
                "id": "income-test",
                "trigger": "income",
                "effects": [effect("gain_money", {"amount": 2}, "income")],
            }, "ongoing"),
        ], source_id="ark-nova:test-sponsor")
        state, trigger_events = engine.start_effects(state, 0, [
            effect("advance_break", {"amount": state["break"]["limit"]}),
        ], source_id="ark-nova:test-break")
        self.assertTrue(state["break"]["pending"])
        self.assertEqual(1, state["players"][0]["x_tokens"])
        self.assertTrue(any(item["type"] == "break_triggered" for item in trigger_events))

        state, _ = queue_break(engine, state)
        discard_actions = engine.legal_choice_actions(state, 0)
        self.assertEqual(10, len(discard_actions))
        selected = discard_actions[0]["action"]
        state, events = engine.submit_choice(
            state, 0, selected["choice_id"], selected["option_ids"],
        )
        self.assertEqual(3, len(state["players"][0]["hand"]))
        self.assertEqual(["other"], state["players"][0]["action_cards"][0]["tokens"])
        self.assertEqual(1, state["players"][0]["association_workers"]["active"])
        self.assertEqual(37, state["players"][0]["money"])
        self.assertEqual(31, state["players"][1]["money"])
        self.assertEqual(6, len(state["card_display"]))
        self.assertEqual(0, state["break"]["position"])
        self.assertFalse(state["break"]["pending"])
        self.assertEqual(1, state["break"]["count"])
        self.assertEqual("active", state["phase"])
        self.assertEqual(1, state["active_seat"])
        self.assertEqual("break_finished", events[-1]["type"])

    def test_endgame_effects_resolve_before_track_distance_and_tiebreak(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        target_table = [0] * 42
        state["players"][0]["tracks"].update({"appeal": 20, "conservation": 10})
        state["players"][0]["supported_projects"] = ["project-a"]
        state["players"][1]["tracks"].update({"appeal": 19, "conservation": 10})
        state["players"][1]["final_scoring_cards"] = [{
            "id": "ark-nova:test-final",
            "effects": [effect("move_track", {"track": "appeal", "amount": 1}, "end_of_game")],
        }]

        triggered, trigger_events = check_endgame_trigger(
            state, 0, boundary="end_of_turn", target_by_conservation=target_table,
        )
        self.assertTrue(triggered["endgame"]["triggered"])
        self.assertEqual("endgame_triggered", trigger_events[0]["type"])
        scored, events = score_game(engine, triggered, target_table)
        rankings = scored["endgame"]["results"]
        self.assertEqual([0, 1], [row["seat"] for row in rankings])
        self.assertEqual([20, 20], [row["victory_points"] for row in rankings])
        self.assertEqual([1, 2], [row["rank"] for row in rankings])
        self.assertEqual("final_scoring_completed", events[-1]["type"])

    def test_content_audit_and_human_readable_preview_share_the_vocabulary(self):
        engine = SemanticEngine()
        entry = ContentEntry(
            id="ark-nova:test-entry",
            kind="animal",
            official_component_id="test-1",
            source_ids=("test-source",),
            display_title="Semantic test animal",
            display_summary="A project-authored scenario card.",
            facts={"cost": 6},
            requirements=({"op": "has_tag", "args": {"tag": "bear", "count": 1}},),
            effects=(effect("gain_money", {"amount": 3}),),
            references=(),
            review_status="scenario_tested",
            scenario_tests=("semantic-test-entry",),
            reviewer="reviewer-a",
            second_reviewer=None,
        )
        manifest = ContentManifest(
            pack_id="semantic-audit-test",
            rules_version="base-1.2-faq-v2-semantic.1",
            content_version="test.1",
            status="draft",
            distribution_mode="repository_safe",
            sources=("test-source",),
            expected_counts={},
            files={},
            declared_sha256=None,
        )
        pack = ContentPack(
            root=Path("/semantic-test"),
            manifest=manifest,
            collections={"animals": (entry,)},
            content_sha256="0" * 64,
        )
        report = audit_content_pack(pack, engine)
        self.assertEqual(("has_tag",), report.predicate_operations)
        self.assertEqual(("gain_money",), report.effect_operations)
        preview = present_entry(entry)
        self.assertIn("bear", preview["requirements"][0])
        self.assertIn("3", preview["effects"][0]["description"])

        bad_entry = ContentEntry(
            **{**entry.__dict__, "effects": (effect("not_registered", {}),)},
        )
        bad_pack = ContentPack(
            root=pack.root,
            manifest=manifest,
            collections={"animals": (bad_entry,)},
            content_sha256=pack.content_sha256,
        )
        with self.assertRaisesRegex(SemanticRuleError, "unknown effect operation"):
            audit_content_pack(bad_pack, engine)

        system_entry = ContentEntry(
            **{**entry.__dict__, "effects": (effect("reset_break", {}, "system"),)},
        )
        system_pack = ContentPack(
            root=pack.root,
            manifest=manifest,
            collections={"animals": (system_entry,)},
            content_sha256=pack.content_sha256,
        )
        with self.assertRaisesRegex(SemanticRuleError, "system-only effect"):
            audit_content_pack(system_pack, engine)

    def test_content_entry_runs_end_to_end_and_ongoing_trigger_targets_its_owner(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["players"][0]["tags"]["bear"] = 1
        entry = ContentEntry(
            id="ark-nova:vertical-sponsor",
            kind="sponsor",
            official_component_id="vertical-1",
            source_ids=("test-source",),
            display_title="Semantic research sponsor",
            display_summary="Project-authored vertical scenario.",
            facts={"tags": ["science"], "icons": {"research": 2}},
            requirements=({"op": "has_tag", "args": {"tag": "bear", "count": 1}},),
            effects=(
                effect("choose_one", {"options": [
                    {"id": "funding", "label": "Funding", "effects": [
                        effect("gain_money", {"amount": 4}),
                    ]},
                    {"id": "reputation", "label": "Reputation", "effects": [
                        effect("move_track", {"track": "reputation", "amount": 1}),
                    ]},
                ]}),
                effect("add_modifier", {
                    "id": "observe-animal-play",
                    "trigger": "animal_played",
                    "effects": [effect("move_track", {"track": "appeal", "amount": 1}, "on_trigger")],
                }, "ongoing"),
            ),
            references=(),
            review_status="scenario_tested",
            scenario_tests=("vertical-entry",),
            reviewer="reviewer-a",
            second_reviewer=None,
        )

        state, events = play_entry_semantics(engine, state, 0, entry)
        self.assertEqual("semantic_entry_played", events[0]["type"])
        self.assertEqual(1, state["players"][0]["tags"]["science"])
        self.assertEqual(2, state["players"][0]["icons"]["research"])
        funding = engine.legal_choice_actions(state, 0)[0]["action"]
        state, _ = engine.submit_choice(
            state, 0, funding["choice_id"], funding["option_ids"],
        )
        self.assertEqual(29, state["players"][0]["money"])
        self.assertEqual("observe-animal-play", state["players"][0]["modifiers"][0]["id"])

        state, trigger_events = engine.trigger_modifiers(
            state, "animal_played", actor_seat=1,
        )
        self.assertEqual(1, state["players"][0]["tracks"]["appeal"])
        self.assertEqual(0, state["players"][1]["tracks"]["appeal"])
        self.assertEqual(1, trigger_events[0]["modifier_count"])

    def test_conservation_project_claim_resolves_level_bonus_and_display_eviction(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["players"][0]["tags"]["bear"] = 3

        def project(identifier: str) -> ContentEntry:
            return ContentEntry(
                id=identifier,
                kind="zoo_conservation_project",
                official_component_id=identifier.rsplit("-", 1)[-1],
                source_ids=("test-source",),
                display_title="Semantic bear project",
                display_summary="Project-authored project scenario.",
                facts={"levels": [
                    {
                        "id": "low",
                        "requirements": [{"op": "has_tag", "args": {"tag": "bear", "count": 2}}],
                        "conservation": 2,
                        "reputation": 0,
                    },
                    {
                        "id": "high",
                        "requirements": [{"op": "has_tag", "args": {"tag": "bear", "count": 3}}],
                        "conservation": 4,
                        "reputation": 1,
                    },
                ]},
                requirements=(),
                effects=(effect("move_track", {"track": "reputation", "amount": 1}, "on_support"),),
                references=(),
                review_status="scenario_tested",
                scenario_tests=("project-claim",),
                reviewer="reviewer-a",
                second_reviewer=None,
            )

        first = project("ark-nova:test-project-1")
        state = add_project_to_state(state, first, base=False)
        state, events = support_project(
            engine,
            state,
            0,
            first,
            "high",
            token_bonus_effects=[effect("gain_money", {"amount": 3}, "on_support")],
            token_bonus_timing="before",
        )
        self.assertEqual("conservation_project_supported", events[0]["type"])
        self.assertEqual(6, state["players"][0]["project_tokens_available"])
        self.assertEqual(4, state["players"][0]["tracks"]["conservation"])
        self.assertEqual(2, state["players"][0]["tracks"]["reputation"])
        self.assertEqual(28, state["players"][0]["money"])

        state = add_project_to_state(state, project("ark-nova:test-project-2"), base=False)
        state = add_project_to_state(state, project("ark-nova:test-project-3"), base=False)
        self.assertNotIn(first.id, [item["id"] for item in state["conservation_projects"]])
        self.assertEqual(1, state["players"][0]["project_tokens_supply"])
        self.assertEqual([], [
            item for item in state["conservation_projects"] if item["id"] == first.id
        ])


if __name__ == "__main__":
    unittest.main()
