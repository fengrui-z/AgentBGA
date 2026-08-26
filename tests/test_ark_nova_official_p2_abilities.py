import unittest

from agentbga.ark_nova_official import ContentEntry, SemanticEngine, new_semantic_state
from agentbga.ark_nova_official.abilities import compile_animal_ability
from agentbga.ark_nova_official.actions import (
    complete_action_execution,
    current_action_execution,
    legal_action_starts,
    start_action,
)
from agentbga.ark_nova_official.cards import play_entry_semantics


class ArkNovaOfficialP2AbilityTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticEngine()
        self.state = new_semantic_state(2, seed=47)

    def test_assertion_takes_one_physical_base_project_from_unused_supply(self):
        self.state["base_project_supply"] = [
            {"id": "project-copy-101", "entry_id": "ark-nova:base-project-101"},
            {"id": "project-copy-108", "entry_id": "ark-nova:base-project-108"},
        ]
        effects = compile_animal_ability({"key": "assertion", "value": ""})
        state, _ = self.engine.start_effects(
            self.state, 0, effects, source_id="animal:assertion",
        )
        self.assertEqual(2, len(self.engine.legal_choice_actions(state, 0)))
        choice = next(
            item["action"] for item in self.engine.legal_choice_actions(state, 0)
            if item["action"]["option_ids"] == ["project-copy-108"]
        )
        state, events = self.engine.submit_choice(
            state, 0, choice["choice_id"], choice["option_ids"],
        )
        self.assertEqual(["project-copy-108"], [
            card["id"] for card in state["players"][0]["hand"]
        ])
        self.assertEqual(["project-copy-101"], [
            card["id"] for card in state["base_project_supply"]
        ])
        self.assertTrue(any(event["type"] == "base_project_taken" for event in events))

    @staticmethod
    def _animal_entry(card_id, *, icons, ability, printed_appeal=0):
        effects = []
        if printed_appeal:
            effects.append({
                "op": "move_track", "timing": "on_play",
                "args": {"track": "appeal", "amount": printed_appeal},
            })
        effects.extend(compile_animal_ability(ability))
        return ContentEntry(
            id=card_id, kind="animal", official_component_id=None,
            source_ids=(), display_title=card_id, display_summary="",
            facts={"tags": list(icons), "icons": list(icons), "appeal": printed_appeal},
            requirements=(), effects=tuple(effects), references=(),
            review_status="scenario_tested", scenario_tests=(),
            reviewer=None, second_reviewer=None,
        )

    def test_pack_counts_the_new_animal_and_all_existing_predator_icons(self):
        self.state["players"][0]["icons"]["predator"] = 2
        entry = self._animal_entry(
            "ark-nova:animal-pack-test", icons=["predator"],
            ability={"key": "pack", "value": ""}, printed_appeal=4,
        )
        state, _ = play_entry_semantics(self.engine, self.state, 0, entry)
        self.assertEqual(3, state["players"][0]["icons"]["predator"])
        self.assertEqual(7, state["players"][0]["tracks"]["appeal"])

    def test_petting_zoo_animals_gain_three_six_then_nine_appeal(self):
        entry = self._animal_entry(
            "ark-nova:animal-pet-test", icons=["pet"],
            ability={"key": "petting_zoo_animal", "value": ""},
        )
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, entry, instance_id="pet-1",
        )
        self.assertEqual(3, state["players"][0]["tracks"]["appeal"])
        state, _ = play_entry_semantics(
            self.engine, state, 0, entry, instance_id="pet-2",
        )
        self.assertEqual(9, state["players"][0]["tracks"]["appeal"])
        state, _ = play_entry_semantics(
            self.engine, state, 0, entry, instance_id="pet-3",
        )
        self.assertEqual(18, state["players"][0]["tracks"]["appeal"])

    def test_pilfering_leader_decides_between_random_card_and_five_money(self):
        self.state["players"][0]["tracks"]["appeal"] = 7
        self.state["players"][1]["tracks"]["appeal"] = 9
        self.state["players"][1]["hand"] = [
            {"id": "target-card-1"}, {"id": "target-card-2"},
        ]
        effects = compile_animal_ability({"key": "pilfering_1", "value": ""})
        state, _ = self.engine.start_effects(
            self.state, 0, effects, source_id="animal:pilfering-1",
        )
        pending = state["resolution"]["pending_choice"]
        self.assertEqual(1, pending["seat"])
        self.assertEqual({"give_card", "give_money"}, {
            option["id"] for option in pending["options"]
        })
        state, events = self.engine.submit_choice(
            state, 1, pending["choice_id"], ["give_money"],
        )
        self.assertEqual(30, state["players"][0]["money"])
        self.assertEqual(20, state["players"][1]["money"])
        self.assertTrue(any(
            event["type"] == "pilfering_money_transferred" for event in events
        ))

    def test_pilfering_empty_hand_forces_all_available_money_below_five(self):
        self.state["players"][0]["tracks"]["appeal"] = 7
        self.state["players"][1]["tracks"]["appeal"] = 9
        self.state["players"][1]["money"] = 3
        effects = compile_animal_ability({"key": "pilfering_1", "value": ""})
        state, _ = self.engine.start_effects(
            self.state, 0, effects, source_id="animal:pilfering-fallback",
        )
        pending = state["resolution"]["pending_choice"]
        self.assertEqual(["give_money"], [option["id"] for option in pending["options"]])
        state, _ = self.engine.submit_choice(
            state, 1, pending["choice_id"], ["give_money"],
        )
        self.assertEqual(28, state["players"][0]["money"])
        self.assertEqual(0, state["players"][1]["money"])

    def test_pilfering_two_resolves_appeal_then_conservation_leaders(self):
        state = new_semantic_state(3, seed=47)
        state["players"][0]["tracks"].update({"appeal": 6, "conservation": 0})
        state["players"][1]["tracks"].update({"appeal": 10, "conservation": 1})
        state["players"][2]["tracks"].update({"appeal": 8, "conservation": 3})
        state["players"][1]["hand"] = [{"id": "appeal-leader-card"}]
        state["players"][2]["hand"] = [{"id": "conservation-leader-card"}]
        effects = compile_animal_ability({"key": "pilfering_2", "value": ""})
        state, _ = self.engine.start_effects(
            state, 0, effects, source_id="animal:pilfering-2",
        )
        first = state["resolution"]["pending_choice"]
        self.assertEqual(1, first["seat"])
        state, events = self.engine.submit_choice(
            state, 1, first["choice_id"], ["give_card"],
        )
        self.assertTrue(any(
            event["type"] == "pilfering_card_transferred" for event in events
        ))
        second = state["resolution"]["pending_choice"]
        self.assertEqual(2, second["seat"])
        state, _ = self.engine.submit_choice(
            state, 2, second["choice_id"], ["give_card"],
        )
        self.assertEqual(2, len(state["players"][0]["hand"]))

    def test_hypnosis_uses_opponent_slot_side_and_tokens_then_moves_own_card(self):
        self.state["players"][0]["tracks"]["appeal"] = 6
        self.state["players"][1]["tracks"]["appeal"] = 10
        target_build = next(
            card for card in self.state["players"][1]["action_cards"]
            if card["action"] == "build"
        )
        target_build["upgraded"] = True
        target_build["tokens"] = [
            {"type": "venom", "source_id": "venom-source"},
            {"type": "constriction", "source_id": "constriction-source"},
            {"type": "multiplier", "source_id": "multiplier-source"},
        ]
        effects = compile_animal_ability({"key": "hypnosis", "value": 3})
        state, _ = self.engine.start_effects(
            self.state, 0, effects, source_id="animal:hypnosis",
        )
        pending = state["resolution"]["pending_choice"]
        self.assertEqual(0, pending["seat"])
        build_option = next(
            option for option in pending["options"]
            if option["value"]["target_action_card_id"] == "build"
        )
        state, events = self.engine.submit_choice(
            state, 0, pending["choice_id"], [build_option["id"]],
        )
        self.assertTrue(any(event["type"] == "hypnosis_action_granted" for event in events))
        self.assertEqual("build", state["turn"]["hypnosis_action"]["action"])

        state["phase"] = "active"
        starts = legal_action_starts(state, 0)
        self.assertTrue(starts)
        self.assertTrue(all(item["action"]["action_card_id"] == "build" for item in starts))
        selected = next(item["action"] for item in starts if item["action"]["x_by_execution"] == [0])
        state, _ = start_action(
            state, 0, selected["action_card_id"],
            x_by_execution=selected["x_by_execution"], multiplier_tokens=0,
        )
        execution = current_action_execution(state, 0)
        self.assertEqual(1, execution["strength"])
        self.assertTrue(execution["upgraded"])
        state, _ = complete_action_execution(
            self.engine, state, 0, {"performed": True, "test": "hypnosis"},
        )
        own_build = next(
            card for card in state["players"][0]["action_cards"]
            if card["action"] == "build"
        )
        target_build = next(
            card for card in state["players"][1]["action_cards"]
            if card["action"] == "build"
        )
        self.assertEqual(1, own_build["position"])
        self.assertEqual(["multiplier"], [token["type"] for token in target_build["tokens"]])
        self.assertEqual(1, state["active_seat"])

    def test_boost_chooses_slot_one_or_five_for_the_named_action_card(self):
        effects = compile_animal_ability({"key": "boost_association", "value": ""})
        state, _ = self.engine.start_effects(
            self.state, 0, effects, source_id="animal:boost-association",
        )
        pending = state["resolution"]["pending_choice"]
        self.assertEqual({"association-to-1", "association-to-5"}, {
            option["id"] for option in pending["options"]
        })
        state, _ = self.engine.submit_choice(
            state, 0, pending["choice_id"], ["association-to-5"],
        )
        association = next(
            card for card in state["players"][0]["action_cards"]
            if card["action"] == "association"
        )
        self.assertEqual(5, association["position"])

    def test_action_keyword_grants_only_the_named_normal_extra_action(self):
        effects = compile_animal_ability({"key": "action_building", "value": ""})
        state, _ = self.engine.start_effects(
            self.state, 0, effects, source_id="animal:action-build",
        )
        self.assertEqual("build", state["turn"]["extra_action"]["action"])
        state["phase"] = "active"
        starts = legal_action_starts(state, 0)
        self.assertTrue(starts)
        self.assertEqual({"build"}, {
            next(
                card["action"] for card in state["players"][0]["action_cards"]
                if card["id"] == item["action"]["action_card_id"]
            )
            for item in starts
        })

    def test_iconic_animal_counts_matching_icons_in_all_zoos_and_caps_at_eight(self):
        self.state["players"][0]["icons"]["asia"] = 2
        self.state["players"][1]["icons"]["asia"] = 7
        entry = self._animal_entry(
            "ark-nova:animal-iconic-test", icons=["reptile", "asia"],
            ability={"key": "iconic_animal", "value": "Asia"}, printed_appeal=2,
        )
        state, _ = play_entry_semantics(self.engine, self.state, 0, entry)
        self.assertEqual(10, state["players"][0]["tracks"]["appeal"])

    def test_inventive_bear_counts_all_zoos_and_caps_reward_at_three(self):
        self.state["players"][1]["icons"]["bear"] = 4
        entry = self._animal_entry(
            "ark-nova:animal-inventive-bear-test", icons=["bear"],
            ability={"key": "inventive_bear", "value": ""},
        )
        state, _ = play_entry_semantics(self.engine, self.state, 0, entry)
        self.assertEqual(3, state["players"][0]["x_tokens"])

    def test_inventive_primate_uses_one_three_five_threshold_table(self):
        self.state["players"][0]["icons"]["primate"] = 2
        entry = self._animal_entry(
            "ark-nova:animal-inventive-primate-test", icons=["primate"],
            ability={"key": "inventive_primary", "value": ""},
        )
        state, _ = play_entry_semantics(self.engine, self.state, 0, entry)
        self.assertEqual(2, state["players"][0]["x_tokens"])

    def test_dominance_introduces_primates_only_when_not_already_in_play(self):
        self.state["base_project_supply"] = [{
            "id": "project-copy-108", "entry_id": "ark-nova:base-project-108",
        }]
        effects = compile_animal_ability({"key": "dominance", "value": ""})
        state, events = self.engine.start_effects(
            self.state, 0, effects, source_id="animal:dominance",
        )
        self.assertEqual([], state["base_project_supply"])
        self.assertEqual([{
            "id": "ark-nova:base-project-108", "base": True, "claims": [],
        }], state["conservation_projects"])
        self.assertTrue(any(event["type"] == "base_project_introduced" for event in events))

        state["base_project_supply"] = [{
            "id": "duplicate-copy-108", "entry_id": "ark-nova:base-project-108",
        }]
        state, events = self.engine.start_effects(
            state, 0, effects, source_id="animal:dominance:again",
        )
        self.assertEqual(1, len(state["conservation_projects"]))
        self.assertEqual(1, len(state["base_project_supply"]))
        self.assertTrue(any(event["type"] == "base_project_already_in_play" for event in events))

    def test_posturing_places_up_to_printed_number_for_free_and_may_stop(self):
        effects = compile_animal_ability({"key": "posturing", "value": 2})
        state, _ = self.engine.start_effects(
            self.state, 0, effects, source_id="animal:posturing",
        )
        pending = state["resolution"]["pending_choice"]
        placement = next(
            option for option in pending["options"]
            if isinstance(option.get("value"), dict)
            and option["value"].get("building_type") == "pavilion"
            and all(
                "placement_bonus" not in cell
                for cell in state["players"][0]["map"]["cells"]
                if (cell["q"], cell["r"]) in {
                    (placed["q"], placed["r"]) for placed in option["value"]["cells"]
                }
            )
        )
        state, events = self.engine.submit_choice(
            state, 0, pending["choice_id"], [placement["id"]],
        )
        self.assertEqual(1, len(state["players"][0]["map"]["buildings"]))
        self.assertEqual(25, state["players"][0]["money"])
        self.assertEqual(1, state["players"][0]["tracks"]["appeal"])
        self.assertTrue(any(event["type"] == "free_building_placed" for event in events))
        second = state["resolution"]["pending_choice"]
        stop = next(option for option in second["options"] if option["id"] == "stop")
        state, events = self.engine.submit_choice(
            state, 0, second["choice_id"], [stop["id"]],
        )
        self.assertIsNone(state["resolution"]["pending_choice"])
        self.assertEqual(1, len(state["players"][0]["map"]["buildings"]))
        self.assertTrue(any(event["type"] == "free_building_placement_stopped" for event in events))

    def test_peacocking_uses_fixed_large_bird_aviary_shape(self):
        effects = compile_animal_ability({"key": "peacocking", "value": ""})
        state, _ = self.engine.start_effects(
            self.state, 0, effects, source_id="animal:peacocking",
        )
        pending = state["resolution"]["pending_choice"]
        placement = next(
            option for option in pending["options"]
            if isinstance(option.get("value"), dict)
        )
        state, _ = self.engine.submit_choice(
            state, 0, pending["choice_id"], [placement["id"]],
        )
        building = state["players"][0]["map"]["buildings"][0]
        self.assertEqual("large_bird_aviary", building["type"])
        self.assertEqual(5, len(building["cells"]))
        self.assertEqual(25, state["players"][0]["money"])


if __name__ == "__main__":
    unittest.main()
