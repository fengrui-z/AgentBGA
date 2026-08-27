import json
from pathlib import Path
import tempfile
import unittest

from agentbga.ark_nova_official import load_content_pack
from agentbga.ark_nova_official.actions import complete_action_execution, start_action
from agentbga.ark_nova_official.reference_import import (
    ReferenceImportError,
    audit_reference_gaps,
    build_semantic_collections,
    import_reference_pack,
    load_reference_dataset,
    require_no_blocking_reference_gaps,
)
from agentbga.ark_nova_official.cards import entry_is_eligible, play_entry_semantics
from agentbga.ark_nova_official.semantics import EvaluationContext, SemanticEngine
from agentbga.ark_nova_official.state import new_semantic_state


class ArkNovaReferenceImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.source = cls.root / "reference-input" / "ark-nova-base" / "ark_nova_base_cards.json"
        if not cls.source.is_file():
            raise unittest.SkipTest("local Ark Nova reference dataset is not installed")

    @staticmethod
    def settle_effect_order(engine, state):
        while (
            state["resolution"]["pending_choice"] is not None
            and state["resolution"]["pending_choice"].get("continuation", {}).get("type")
            == "choose_effect_order"
        ):
            choice = state["resolution"]["pending_choice"]
            state, _ = engine.submit_choice(
                state, choice["seat"], choice["choice_id"], ["effect-0"],
            )
        return state

    def test_reference_has_exact_card_ranges_and_physical_expansion(self):
        data = load_reference_dataset(self.source)
        self.assertEqual(255, len(data["physical_255"]))
        self.assertEqual(128, len(data["animals"]))
        self.assertEqual(5, len(data["action_cards"]))
        self.assertEqual(4, sum(
            row["unique_id"] == "A-BUILD" for row in data["physical_255"]
        ))

    def test_imported_entries_preserve_structured_facts_but_not_uncompiled_effects(self):
        data = load_reference_dataset(self.source)
        collections = build_semantic_collections(data)
        cheetah = collections["animals"][0]
        self.assertEqual("ark-nova:animal-401", cheetah["id"])
        self.assertEqual(17, cheetah["facts"]["cost"])
        self.assertEqual("sprint", cheetah["facts"]["abilities"][0]["key"])
        self.assertEqual("move_track", cheetah["effects"][0]["op"])
        self.assertEqual("draw_cards", cheetah["effects"][1]["op"])
        self.assertEqual("compiled", cheetah["facts"]["semantic_compile_status"])
        self.assertEqual("transcribed", cheetah["review"]["status"])
        project = collections["base_conservation_projects"][0]
        self.assertEqual("transcribed", project["review"]["status"])
        self.assertEqual("compiled", project["facts"]["semantic_compile_status"])
        self.assertEqual(3, len(project["facts"]["levels"]))
        final_card = collections["final_scoring_cards"][0]
        self.assertEqual("compiled", final_card["facts"]["semantic_compile_status"])
        self.assertEqual("threshold", final_card["facts"]["scoring"]["mode"])

        lion = collections["animals"][1]
        self.assertEqual(
            {"op": "has_icon", "args": {"icon": "predator", "count": 3}},
            lion["requirements"][0],
        )
        solo = next(item for item in collections["animals"] if item["id"] == "ark-nova:animal-458")
        self.assertEqual(["pilfer"], solo["facts"]["solo_replaces_ops"])
        self.assertEqual(2, solo["facts"]["solo_effects"][0]["args"]["amount"])

    def test_rejects_a_missing_physical_copy(self):
        data = json.loads(self.source.read_text(encoding="utf-8"))
        data["physical_255"].pop()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ReferenceImportError, "expected 255"):
                load_reference_dataset(path)

    def test_reference_gap_audit_closes_all_animal_parameter_and_compiler_work(self):
        gaps = audit_reference_gaps(load_reference_dataset(self.source))
        self.assertEqual({
            "blocking_parameter_records": 0,
            "animal_compiler_records": 0,
            "uncompiled_sponsor_effect_records": 0,
            "uncompiled_sponsor_requirement_records": 0,
            "uncompiled_project_tiers": 0,
            "uncompiled_final_scoring_tiers": 0,
        }, gaps["summary"])
        self.assertEqual([], gaps["missing_printed_parameters"])
        self.assertEqual([], gaps["animal_compiler_backlog"])
        require_no_blocking_reference_gaps(gaps)

    def test_generated_authoring_pack_passes_existing_content_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pack"
            source_pack = self.root / "content-packs" / "ark-nova" / "base-en-draft"
            target.mkdir()
            for path in source_pack.iterdir():
                if path.is_file():
                    (target / path.name).write_bytes(path.read_bytes())
            report = import_reference_pack(self.source, target)
            pack = load_content_pack(target)
            self.assertEqual(255, report["physical_cards"])
            self.assertEqual(235, report["authoring_entries_imported"])
            self.assertEqual(44, report["compiled_ability_keywords"])
            self.assertEqual(128, report["fully_compiled_animals"])
            self.assertEqual("Cheetah", pack.entry("ark-nova:animal-401").display_title)
            self.assertEqual(17, pack.entry("ark-nova:animal-401").facts["cost"])
            self.assertTrue((target / "action_cards.reference.json").is_file())
            self.assertTrue((target / "data_gaps.reference.json").is_file())

    def test_compiled_animal_requirements_are_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pack"
            source_pack = self.root / "content-packs" / "ark-nova" / "base-en-draft"
            target.mkdir()
            for path in source_pack.iterdir():
                if path.is_file():
                    (target / path.name).write_bytes(path.read_bytes())
            import_reference_pack(self.source, target)
            pack = load_content_pack(target)
            engine = SemanticEngine()
            state = new_semantic_state(2)

            lion = pack.entry("ark-nova:animal-402")
            self.assertFalse(entry_is_eligible(engine, state, 0, lion))
            state["players"][0]["icons"]["predator"] = 3
            self.assertTrue(entry_is_eligible(engine, state, 0, lion))

            upgraded = pack.entry("ark-nova:animal-421")
            self.assertFalse(entry_is_eligible(engine, state, 0, upgraded))
            next(card for card in state["players"][0]["action_cards"]
                 if card["action"] == "animals")["upgraded"] = True
            self.assertTrue(entry_is_eligible(engine, state, 0, upgraded))

            partner_animals = [
                entry for entry in pack.collections["animals"]
                if any(requirement["op"] == "matching_partner_zoo" for requirement in entry.requirements)
            ]
            self.assertEqual(15, len(partner_animals))
            for partner in partner_animals:
                continent = partner.facts["continents"][0]
                requirement = next(item for item in partner.requirements if item["op"] == "matching_partner_zoo")
                context = EvaluationContext(
                    state=state, actor_seat=0,
                    card={"id": partner.id, "kind": partner.kind, "facts": dict(partner.facts)},
                )
                state["players"][0]["partner_zoos"] = [
                    next(value for value in ("africa", "europe", "asia", "americas", "australia") if value != continent)
                ]
                self.assertFalse(engine.evaluate(requirement, context), partner.display_title)
                state["players"][0]["partner_zoos"] = [continent]
                self.assertTrue(engine.evaluate(requirement, context), partner.display_title)

    def test_compiled_direct_rewards_and_sprint_execute_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pack"
            source_pack = self.root / "content-packs" / "ark-nova" / "base-en-draft"
            target.mkdir()
            for path in source_pack.iterdir():
                if path.is_file():
                    (target / path.name).write_bytes(path.read_bytes())
            import_reference_pack(self.source, target)
            pack = load_content_pack(target)
            state = new_semantic_state(2)
            state["zoo_deck"] = [{"id": f"deck-{index}"} for index in range(4)]

            state, events = play_entry_semantics(
                SemanticEngine(), state, 0, pack.entry("ark-nova:animal-401"),
            )
            self.assertEqual(6, state["players"][0]["tracks"]["appeal"])
            self.assertEqual(3, len(state["players"][0]["hand"]))
            self.assertEqual(1, len(state["zoo_deck"]))
            self.assertTrue(any(event["type"] == "cards_drawn" for event in events))

    def test_worker_and_multiplier_abilities_update_engine_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pack"
            source_pack = self.root / "content-packs" / "ark-nova" / "base-en-draft"
            target.mkdir()
            for path in source_pack.iterdir():
                if path.is_file():
                    (target / path.name).write_bytes(path.read_bytes())
            import_reference_pack(self.source, target)
            pack = load_content_pack(target)
            state = new_semantic_state(2)
            player = state["players"][0]
            next(card for card in player["action_cards"]
                 if card["action"] == "animals")["upgraded"] = True

            state, _ = play_entry_semantics(
                SemanticEngine(), state, 0, pack.entry("ark-nova:animal-421"),
            )
            self.assertEqual({"active": 2, "reserve": 2, "committed": []},
                             state["players"][0]["association_workers"])

            state["players"][0]["icons"]["science"] = 2
            state, events = play_entry_semantics(
                SemanticEngine(), state, 0, pack.entry("ark-nova:animal-434"),
            )
            sponsors = next(card for card in state["players"][0]["action_cards"]
                            if card["action"] == "sponsors")
            self.assertEqual("multiplier", sponsors["tokens"][0]["type"])
            self.assertTrue(any(event["type"] == "action_token_added" for event in events))

    def test_sun_bathing_and_pouch_use_explicit_hand_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pack"
            source_pack = self.root / "content-packs" / "ark-nova" / "base-en-draft"
            target.mkdir()
            for path in source_pack.iterdir():
                if path.is_file():
                    (target / path.name).write_bytes(path.read_bytes())
            import_reference_pack(self.source, target)
            pack = load_content_pack(target)
            engine = SemanticEngine()
            state = new_semantic_state(2)
            player = state["players"][0]
            player["partner_zoos"].append("australia")
            player["hand"] = [{"id": "hand-a"}, {"id": "hand-b"}, {"id": "hand-c"}]
            old_money = player["money"]

            state, _ = play_entry_semantics(
                engine, state, 0, pack.entry("ark-nova:animal-422"),
            )
            state = self.settle_effect_order(engine, state)
            pending = state["resolution"]["pending_choice"]
            self.assertEqual(0, pending["minimum"])
            self.assertEqual(3, pending["maximum"])
            state, _ = engine.submit_choice(state, 0, pending["choice_id"], ["hand-a", "hand-b"])
            self.assertEqual(old_money + 8, state["players"][0]["money"])
            self.assertEqual(["hand-c"], [card["id"] for card in state["players"][0]["hand"]])

            state["players"][0]["icons"]["science"] = 1
            old_appeal = state["players"][0]["tracks"]["appeal"]
            state, _ = play_entry_semantics(
                engine, state, 0, pack.entry("ark-nova:animal-425"),
            )
            state = self.settle_effect_order(engine, state)
            pending = state["resolution"]["pending_choice"]
            state, _ = engine.submit_choice(state, 0, pending["choice_id"], ["hand-c"])
            pouch = next(card for card in state["players"][0]["played_cards"]
                         if card["id"] == "ark-nova:animal-425")
            self.assertEqual(["hand-c"], [card["id"] for card in pouch["tucked_cards"]])
            self.assertEqual(old_appeal + 6, state["players"][0]["tracks"]["appeal"])

    def test_hunter_perception_and_snapping_preserve_card_zones(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pack"
            source_pack = self.root / "content-packs" / "ark-nova" / "base-en-draft"
            target.mkdir()
            for path in source_pack.iterdir():
                if path.is_file():
                    (target / path.name).write_bytes(path.read_bytes())
            import_reference_pack(self.source, target)
            pack = load_content_pack(target)
            engine = SemanticEngine()

            state = new_semantic_state(2)
            state["players"][0]["partner_zoos"].append("africa")
            state["zoo_deck"] = [
                {"id": "animal-a", "kind": "animal"},
                {"id": "sponsor-a", "kind": "sponsor"},
                {"id": "animal-b", "kind": "animal"},
                {"id": "sponsor-b", "kind": "sponsor"},
            ]
            state, _ = play_entry_semantics(
                engine, state, 0, pack.entry("ark-nova:animal-403"),
            )
            state = self.settle_effect_order(engine, state)
            pending = state["resolution"]["pending_choice"]
            self.assertEqual({"animal-a", "animal-b"}, {option["id"] for option in pending["options"]})
            state, _ = engine.submit_choice(state, 0, pending["choice_id"], ["animal-b"])
            self.assertEqual(["animal-b"], [card["id"] for card in state["players"][0]["hand"]])
            self.assertEqual(3, len(state["zoo_discard"]))

            state = new_semantic_state(2)
            state["players"][0]["icons"]["bird"] = 2
            state["zoo_deck"] = [{"id": f"perception-{index}"} for index in range(4)]
            state, _ = play_entry_semantics(
                engine, state, 0, pack.entry("ark-nova:animal-503"),
            )
            state = self.settle_effect_order(engine, state)
            pending = state["resolution"]["pending_choice"]
            state, _ = engine.submit_choice(
                state, 0, pending["choice_id"], ["perception-1", "perception-3"],
            )
            self.assertEqual(2, len(state["players"][0]["hand"]))
            self.assertEqual(2, len(state["zoo_discard"]))

            state = new_semantic_state(2)
            state["players"][0]["icons"]["reptile"] = 3
            state["card_display"] = [{"id": "display-a"}, {"id": "display-b"}]
            state["zoo_deck"] = [{"id": "refill-a"}, {"id": "refill-b"}]
            state, _ = play_entry_semantics(
                engine, state, 0, pack.entry("ark-nova:animal-469"),
            )
            state = self.settle_effect_order(engine, state)
            first = state["resolution"]["pending_choice"]
            state, _ = engine.submit_choice(state, 0, first["choice_id"], ["display-a"])
            second = state["resolution"]["pending_choice"]
            self.assertIn("refill-b", {option["id"] for option in second["options"]})
            state, _ = engine.submit_choice(state, 0, second["choice_id"], ["refill-b"])
            self.assertEqual({"display-a", "refill-b"}, {
                card["id"] for card in state["players"][0]["hand"]
            })
            self.assertEqual(2, len(state["card_display"]))

    def test_scavenging_draws_from_discard_and_returns_unkept_cards(self):
        engine = SemanticEngine()
        state = new_semantic_state(2, seed=17)
        state["zoo_discard"] = [{"id": f"discard-{index}"} for index in range(5)]
        state, _ = engine.start_effects(state, 0, [{
            "op": "scavenge_discard", "args": {"draw": 3, "keep": 1},
            "timing": "on_play",
        }], source_id="test:scavenging")
        pending = state["resolution"]["pending_choice"]
        self.assertEqual(1, pending["minimum"])
        self.assertEqual(3, len(pending["options"]))
        kept_id = pending["options"][1]["id"]
        state, events = engine.submit_choice(state, 0, pending["choice_id"], [kept_id])
        self.assertEqual([kept_id], [card["id"] for card in state["players"][0]["hand"]])
        self.assertEqual(4, len(state["zoo_discard"]))
        self.assertTrue(any(event["type"] == "scavenging_resolved" for event in events))

    def test_digging_cycles_display_and_hand_then_can_stop(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["card_display"] = [{"id": "display-a"}, {"id": "display-b"}]
        state["players"][0]["hand"] = [{"id": "hand-a"}]
        state["zoo_deck"] = [{"id": "refill-hand"}, {"id": "refill-display"}]
        state, _ = engine.start_effects(state, 0, [{
            "op": "dig_cards", "args": {"maximum": 3}, "timing": "on_play",
        }], source_id="test:digging")

        first = state["resolution"]["pending_choice"]
        state, _ = engine.submit_choice(
            state, 0, first["choice_id"], ["display:display-a"],
        )
        self.assertEqual({"display-b", "refill-display"}, {
            card["id"] for card in state["card_display"]
        })
        second = state["resolution"]["pending_choice"]
        state, _ = engine.submit_choice(state, 0, second["choice_id"], ["hand:hand-a"])
        self.assertEqual(["refill-hand"], [card["id"] for card in state["players"][0]["hand"]])
        third = state["resolution"]["pending_choice"]
        state, events = engine.submit_choice(state, 0, third["choice_id"], ["stop"])
        self.assertIsNone(state["resolution"]["pending_choice"])
        self.assertEqual({"display-a", "hand-a"}, {card["id"] for card in state["zoo_discard"]})
        self.assertTrue(any(event["type"] == "digging_stopped" for event in events))

    def test_venom_uses_appeal_timing_and_lowest_action_slots(self):
        engine = SemanticEngine()
        state = new_semantic_state(3)
        state["players"][0]["tracks"]["appeal"] = 10
        state["players"][1]["tracks"]["appeal"] = 8
        state["players"][2]["tracks"]["appeal"] = 12
        state, _ = engine.start_effects(state, 0, [{
            "op": "apply_interaction_tokens",
            "args": {"token": "venom", "amount": 2, "track_mode": "appeal"},
            "timing": "interaction",
        }], source_id="test:venom", card={"facts": {"appeal": 4}})
        pending = state["resolution"]["pending_choice"]
        self.assertEqual({"before_appeal", "after_appeal"}, {
            option["id"] for option in pending["options"]
        })
        state, _ = engine.submit_choice(state, 0, pending["choice_id"], ["before_appeal"])
        for seat in (1, 2):
            cards = sorted(state["players"][seat]["action_cards"], key=lambda card: card["position"])
            self.assertEqual(["venom"], [token["type"] for token in cards[0]["tokens"]])
            self.assertEqual(["venom"], [token["type"] for token in cards[1]["tokens"]])
            self.assertFalse(cards[2]["tokens"])

    def test_constriction_uses_leading_tracks_high_slots_and_immunity(self):
        engine = SemanticEngine()
        state = new_semantic_state(4)
        actor = state["players"][0]
        actor["tracks"].update({"appeal": 10, "conservation": 3})
        state["players"][1]["tracks"].update({"appeal": 11, "conservation": 4})
        state["players"][2]["tracks"].update({"appeal": 4, "conservation": 9})
        state["players"][3]["tracks"].update({"appeal": 12, "conservation": 5})
        state["players"][3]["played_cards"].append({"id": "ark-nova:sponsor-225"})
        top = max(state["players"][1]["action_cards"], key=lambda card: card["position"])
        top["tokens"].append({"type": "constriction", "source_id": "older"})
        state, events = engine.start_effects(state, 0, [{
            "op": "apply_interaction_tokens",
            "args": {"token": "constriction", "track_mode": "appeal_and_conservation"},
            "timing": "interaction",
        }], source_id="test:constriction", card={"facts": {"appeal": 0}})
        cards = sorted(
            state["players"][1]["action_cards"], key=lambda card: card["position"], reverse=True,
        )
        self.assertEqual(1, len(cards[0]["tokens"]))
        self.assertEqual(["constriction"], [token["type"] for token in cards[1]["tokens"]])
        self.assertFalse(any(card["tokens"] for card in state["players"][2]["action_cards"]))
        self.assertFalse(any(card["tokens"] for card in state["players"][3]["action_cards"]))
        event = next(event for event in events if event["type"] == "interaction_tokens_placed")
        self.assertEqual({"requested": 2, "placed": 1}, {
            "requested": event["requested"], "placed": event["placed"],
        })

    def test_clever_waits_for_action_finish_then_repositions_with_shifting(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pack"
            source_pack = self.root / "content-packs" / "ark-nova" / "base-en-draft"
            target.mkdir()
            for path in source_pack.iterdir():
                if path.is_file():
                    (target / path.name).write_bytes(path.read_bytes())
            import_reference_pack(self.source, target)
            pack = load_content_pack(target)
            engine = SemanticEngine()
            state = new_semantic_state(2)
            state["phase"] = "active"
            state["players"][0]["x_tokens"] = 1
            state, _ = start_action(state, 0, "animals", x_by_execution=(1,))
            state, _ = play_entry_semantics(
                engine, state, 0, pack.entry("ark-nova:animal-405"),
            )
            self.assertIsNone(state["resolution"]["pending_choice"])
            self.assertEqual(1, len(state["turn"]["action_session"]["after_finishing_effects"]))

            state, _ = complete_action_execution(
                engine, state, 0, {"performed": True, "cards": ["ark-nova:animal-405"]},
            )
            pending = state["resolution"]["pending_choice"]
            self.assertEqual(0, pending["minimum"])
            state, events = engine.submit_choice(state, 0, pending["choice_id"], ["build"])
            positions = {
                card["action"]: card["position"] for card in state["players"][0]["action_cards"]
            }
            self.assertEqual(1, positions["build"])
            self.assertEqual(2, positions["animals"])
            self.assertEqual(3, positions["cards"])
            self.assertTrue(any(event["type"] == "action_card_repositioned" for event in events))
            self.assertEqual(1, state["active_seat"])

    def test_resistance_keeps_one_final_scoring_card_and_discards_the_other(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["final_scoring_deck"] = [
            {"id": "final-a"}, {"id": "final-b"}, {"id": "final-c"},
        ]
        state, _ = engine.start_effects(state, 0, [{
            "op": "draw_keep_final_scoring", "args": {"draw": 2, "keep": 1},
            "timing": "on_play",
        }], source_id="test:resistance")
        pending = state["resolution"]["pending_choice"]
        self.assertEqual({"final-b", "final-c"}, {option["id"] for option in pending["options"]})
        state, events = engine.submit_choice(state, 0, pending["choice_id"], ["final-b"])
        self.assertEqual(["final-b"], [
            card["id"] for card in state["players"][0]["final_scoring_cards"]
        ])
        self.assertEqual(["final-c"], [card["id"] for card in state["final_scoring_discard"]])
        self.assertEqual(["final-a"], [card["id"] for card in state["final_scoring_deck"]])
        self.assertTrue(any(event["type"] == "final_scoring_cards_drawn" for event in events))

    def test_sponsor_magnet_leaves_gaps_until_action_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pack"
            source_pack = self.root / "content-packs" / "ark-nova" / "base-en-draft"
            target.mkdir()
            for path in source_pack.iterdir():
                if path.is_file():
                    (target / path.name).write_bytes(path.read_bytes())
            import_reference_pack(self.source, target)
            pack = load_content_pack(target)
            engine = SemanticEngine()
            state = new_semantic_state(2)
            state["phase"] = "active"
            state["players"][0]["icons"]["americas"] = 1
            state["players"][0]["x_tokens"] = 1
            state["card_display"] = [
                {"id": "animal-a", "kind": "animal"},
                {"id": "sponsor-a", "kind": "sponsor"},
                {"id": "animal-b", "kind": "animal"},
                {"id": "sponsor-b", "kind": "sponsor"},
                {"id": "animal-c", "kind": "animal"},
                {"id": "animal-d", "kind": "animal"},
            ]
            state["zoo_deck"] = [{"id": "refill-a"}, {"id": "refill-b"}]
            state, _ = start_action(state, 0, "animals", x_by_execution=(1,))
            state, _ = play_entry_semantics(
                engine, state, 0, pack.entry("ark-nova:animal-437"),
            )
            self.assertEqual(4, len(state["card_display"]))
            self.assertEqual({"sponsor-a", "sponsor-b"}, {
                card["id"] for card in state["players"][0]["hand"]
            })
            state, events = complete_action_execution(
                engine, state, 0, {"performed": True, "cards": ["ark-nova:animal-437"]},
            )
            self.assertEqual(6, len(state["card_display"]))
            self.assertTrue(any(event["type"] == "card_display_refilled" for event in events))


if __name__ == "__main__":
    unittest.main()
