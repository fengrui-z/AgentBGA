from pathlib import Path
import unittest

from agentbga.ark_nova_official import (
    ContentEntry,
    SemanticEngine,
    add_project_to_state,
    load_content_pack,
    legal_project_levels,
    new_semantic_state,
    play_entry_semantics,
    score_game,
    support_project,
    resolve_mechanics,
)
from agentbga.ark_nova_official.animals_action import _animal_cost
from agentbga.ark_nova_official.animals_action import _animal_entry_is_eligible
from agentbga.ark_nova_official.association_action import _project_task_strength
from agentbga.ark_nova_official.build_action import _claim_map_rewards
from agentbga.ark_nova_official.sponsors_action import (
    apply_bonus_sponsor_action,
    legal_bonus_sponsor_actions,
)


def icon_card(identifier: str, icon: str) -> ContentEntry:
    return ContentEntry(
        id=f"ark-nova:{identifier}",
        kind="animal",
        official_component_id=None,
        source_ids=(),
        display_title=identifier,
        display_summary="Test icon carrier.",
        facts={"tags": [icon], "icons": [icon]},
        requirements=(),
        effects=(),
        references=(),
        review_status="schema_valid",
        scenario_tests=(),
        reviewer=None,
        second_reviewer=None,
    )


class ArkNovaOfficialP3SponsorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.pack = load_content_pack(
            root / "content-packs" / "ark-nova" / "base-en-draft",
        )

    def setUp(self):
        self.engine = SemanticEngine()
        self.state = new_semantic_state(2, seed=73)

    def sponsor(self, component_id: int) -> ContentEntry:
        return self.pack.entry(f"ark-nova:sponsor-{component_id}")

    def test_all_sponsors_project_complete_compiled_mechanics(self):
        allowed_timings = {"immediate", "passive", "income", "interaction", "endgame"}
        for sponsor in self.pack.collections["sponsors"]:
            with self.subTest(card=sponsor.official_component_id):
                mechanics = resolve_mechanics(sponsor.effects, sponsor.facts)
                self.assertTrue(mechanics)
                self.assertTrue(all(item["timing"] in allowed_timings for item in mechanics))
                self.assertTrue(all(item["description_cn"] for item in mechanics))
                self.assertTrue(all(item["description_en"] for item in mechanics))
                self.assertNotIn("语义效果：", str(mechanics))

        veterinarian = resolve_mechanics(self.sponsor(203).effects, self.sponsor(203).facts)
        self.assertEqual(["immediate", "passive", "endgame"], [item["timing"] for item in veterinarian])
        rendered = " ".join(item["description_cn"] for item in veterinarian)
        self.assertIn("大学数量", rendered)
        self.assertIn("协会行动强度改为4", rendered)
        self.assertIn("保护点数", rendered)

    def settle_effect_order(self, state):
        while (
            state["resolution"]["pending_choice"] is not None
            and state["resolution"]["pending_choice"].get("continuation", {}).get("type")
            == "choose_effect_order"
        ):
            choice = state["resolution"]["pending_choice"]
            state, _ = self.engine.submit_choice(
                state, choice["seat"], choice["choice_id"], ["effect-0"],
            )
        return state

    def test_self_and_any_zoo_icon_triggers_include_the_played_sponsor_icon(self):
        self.state["players"][0]["icons"]["science"] = 1
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(202), instance_id="speaker",
        )
        self.assertEqual(1, state["players"][0]["tracks"]["reputation"])

        state, _ = play_entry_semantics(
            self.engine, state, 0, self.sponsor(208), instance_id="library",
        )
        state = self.settle_effect_order(state)
        # Science Library sees its own printed science icon.
        self.assertEqual(27, state["players"][0]["money"])

        state, _ = play_entry_semantics(
            self.engine, state, 1, icon_card("science-animal", "science"),
            instance_id="science-animal-1",
        )
        self.assertEqual(29, state["players"][0]["money"])
        # Spokesperson is self-only, so the opponent's icon grants no reputation.
        self.assertEqual(2, state["players"][0]["tracks"]["reputation"])

    def test_animal_specialists_supply_and_trigger_their_printed_icon(self):
        specialist_icons = {
            236: "primate",
            237: "reptile",
            238: "bird",
            239: "predator",
            240: "herbivore",
        }
        for component_id, icon in specialist_icons.items():
            with self.subTest(component_id=component_id, icon=icon):
                state = new_semantic_state(2, seed=component_id)
                money = state["players"][0]["money"]
                state, events = play_entry_semantics(
                    self.engine, state, 0, self.sponsor(component_id),
                    instance_id=f"specialist-{component_id}",
                )
                state = self.settle_effect_order(state)
                self.assertEqual(1, state["players"][0]["icons"]["person"])
                self.assertEqual(1, state["players"][0]["icons"][icon])
                self.assertEqual(money + 3, state["players"][0]["money"])
                self.assertTrue(any(
                    event.get("type") == "zoo_icon_entered"
                    and event.get("icon") == icon
                    for event in events
                ))

    def test_doubled_science_icon_fires_each_matching_trigger_twice(self):
        self.state["players"][0]["icons"]["science"] = 1
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(202), instance_id="speaker",
        )
        before = state["players"][0]["tracks"]["reputation"]
        state, events = play_entry_semantics(
            self.engine, state, 0, self.sponsor(223), instance_id="institute",
        )
        state = self.settle_effect_order(state)
        self.assertEqual(4, state["players"][0]["icons"]["science"])
        self.assertEqual(before + 2, state["players"][0]["tracks"]["reputation"])
        entered = next(event for event in events if event["type"] == "zoo_icon_entered")
        self.assertEqual(2, entered["count"])

    def test_income_sponsors_resolve_track_token_money_and_tier_tables(self):
        self.state["players"][0]["icons"].update({"science": 4, "primate": 3})
        state = self.state
        for component_id in (206, 209, 220, 231):
            state, _ = play_entry_semantics(
                self.engine, state, 0, self.sponsor(component_id),
                instance_id=f"sponsor-{component_id}",
            )
        conservation = state["players"][0]["tracks"]["conservation"]
        money = state["players"][0]["money"]
        state, _ = self.engine.start_effects(
            state, 0,
            [{"op": "take_income", "args": {}, "timing": "system"}],
            source_id="test:income",
        )
        state = self.settle_effect_order(state)
        self.assertEqual(conservation + 1, state["players"][0]["tracks"]["conservation"])
        # Technology Institute grants one token on play and one at income.
        self.assertEqual(2, state["players"][0]["x_tokens"])
        self.assertEqual(money + 9, state["players"][0]["money"])

    def test_static_sponsor_rules_distinguish_small_large_and_project_strength(self):
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(229), instance_id="small-expert",
        )
        state, _ = play_entry_semantics(
            self.engine, state, 0, self.sponsor(230), instance_id="large-expert",
        )
        state, _ = play_entry_semantics(
            self.engine, state, 0, self.sponsor(203), instance_id="vet",
        )
        player = state["players"][0]

        def animal(size: int) -> ContentEntry:
            return ContentEntry(
                id=f"ark-nova:animal-{size}", kind="animal",
                official_component_id=None, source_ids=(),
                display_title=f"Animal {size}", display_summary="Cost test.",
                facts={"cost": 10, "enclosure_size": size, "continents": []},
                requirements=(), effects=(), references=(),
                review_status="schema_valid", scenario_tests=(),
                reviewer=None, second_reviewer=None,
            )

        self.assertEqual(7, _animal_cost(player, animal(2)))
        self.assertEqual(10, _animal_cost(player, animal(3)))
        self.assertEqual(6, _animal_cost(player, animal(4)))
        self.assertEqual(4, _project_task_strength(player))

    def test_corrected_immediate_rewards_use_live_zoo_counts(self):
        player = self.state["players"][0]
        player["universities"] = ["research-2", "research-reputation"]
        player["icons"]["science"] = 3
        player["supported_projects"] = ["project-a", "project-b", "project-c"]
        initial_money = player["money"]

        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(203), instance_id="vet",
        )
        self.assertEqual(initial_money + 5, state["players"][0]["money"])
        state, _ = play_entry_semantics(
            self.engine, state, 0, self.sponsor(204), instance_id="museum",
        )
        # Science Museum's printed science icon is already in the zoo.
        self.assertEqual(initial_money + 15, state["players"][0]["money"])
        state, _ = play_entry_semantics(
            self.engine, state, 0, self.sponsor(206), instance_id="breakthrough",
        )
        self.assertEqual(6, state["players"][0]["tracks"]["appeal"])
        state, _ = play_entry_semantics(
            self.engine, state, 0, self.sponsor(220), instance_id="grants",
        )
        self.assertEqual(initial_money + 18, state["players"][0]["money"])

    def test_small_and_large_experts_score_existing_animals_on_play(self):
        def animal(identifier: str, size: int) -> ContentEntry:
            return ContentEntry(
                id=f"ark-nova:{identifier}", kind="animal",
                official_component_id=None, source_ids=(),
                display_title=identifier, display_summary="Size fixture.",
                facts={"enclosure_size": size, "tags": [], "icons": []},
                requirements=(), effects=(), references=(),
                review_status="schema_valid", scenario_tests=(),
                reviewer=None, second_reviewer=None,
            )

        state = self.state
        for identifier, size in (("small", 2), ("neutral", 3), ("large", 5)):
            state, _ = play_entry_semantics(
                self.engine, state, 0, animal(identifier, size), instance_id=identifier,
            )
        state, _ = play_entry_semantics(
            self.engine, state, 0, self.sponsor(229), instance_id="small-expert",
        )
        state, _ = play_entry_semantics(
            self.engine, state, 0, self.sponsor(230), instance_id="large-expert",
        )
        self.assertEqual(3, state["players"][0]["tracks"]["appeal"])

    def test_hydrologist_counts_covered_cells_adjacent_to_water(self):
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(241), instance_id="hydrologist",
        )
        # Its own printed water icon is included in the immediate Appeal count.
        self.assertEqual(1, state["players"][0]["tracks"]["appeal"])
        before = state["players"][0]["money"]
        state, events = self.engine.start_effects(
            state, 0, [{
                "op": "trigger_building_placed", "timing": "immediate",
                "args": {"cells": [{"q": -3, "r": 0}, {"q": -3, "r": 1}]},
            }], source_id="test:building",
        )
        # Both cells touch one or more water spaces, but each covered cell pays once.
        self.assertEqual(before + 2, state["players"][0]["money"])
        placed = next(event for event in events if event["type"] == "semantic_building_placed")
        self.assertEqual(2, placed["adjacent_water_cells"])

    def test_migration_recording_rewards_and_repeats_release_projects(self):
        self.state["players"][0]["icons"]["science"] = 1
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(224), instance_id="migration",
        )
        self.assertEqual(1, state["players"][0]["x_tokens"])
        release = ContentEntry(
            id="ark-nova:test-release", kind="zoo_conservation_project",
            official_component_id="test-release", source_ids=(),
            display_title="Test release", display_summary="Release hook fixture.",
            facts={
                "project_type": "release",
                "levels": [
                    {"id": "low", "requirements": [], "conservation": 0, "reputation": 0},
                    {"id": "high", "requirements": [], "conservation": 0, "reputation": 0},
                ],
            },
            requirements=(), effects=(), references=(),
            review_status="schema_valid", scenario_tests=(),
            reviewer=None, second_reviewer=None,
        )
        state = add_project_to_state(state, release, base=False)
        state, _ = support_project(self.engine, state, 0, release, "low")
        state, _ = support_project(self.engine, state, 0, release, "high")
        self.assertEqual(2, state["players"][0]["tracks"]["conservation"])
        claims = state["conservation_projects"][0]["claims"]
        self.assertEqual([0, 0], [claim["seat"] for claim in claims])

    def test_breeding_cooperation_spends_one_stored_token_as_base_project_icon(self):
        self.state["players"][0]["partner_zoos"] = ["africa", "asia"]
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(215), instance_id="cooperation",
        )
        cooperation = state["players"][0]["played_cards"][0]
        self.assertEqual(2, cooperation["stored_tokens"])
        base = ContentEntry(
            id="ark-nova:test-base", kind="base_conservation_project",
            official_component_id="test-base", source_ids=(),
            display_title="Test base", display_summary="Wildcard fixture.",
            facts={"levels": [{
                "id": "one-bird",
                "requirements": [{"op": "has_icon", "args": {"icon": "bird", "count": 1}}],
                "conservation": 1, "reputation": 0,
            }]},
            requirements=(), effects=(), references=(),
            review_status="schema_valid", scenario_tests=(),
            reviewer=None, second_reviewer=None,
        )
        state = add_project_to_state(state, base, base=True)
        levels = legal_project_levels(self.engine, state, 0, base)
        self.assertEqual("cooperation", levels[0]["wildcard_instance_id"])
        state, events = support_project(self.engine, state, 0, base, "one-bird")
        cooperation = next(
            card for card in state["players"][0]["played_cards"]
            if card["id"] == "cooperation"
        )
        self.assertEqual(1, cooperation["stored_tokens"])
        self.assertEqual("cooperation", events[0]["wildcard_instance_id"])

    def test_explorer_rewards_only_new_continent_or_category_icons(self):
        sponsors_card = next(
            card for card in self.state["players"][0]["action_cards"]
            if card["action"] == "sponsors"
        )
        sponsors_card["upgraded"] = True
        self.state["players"][0]["icons"].update({"africa": 1, "bird": 1})
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(262), instance_id="explorer",
        )
        self.assertEqual(29, state["players"][0]["money"])
        state, _ = play_entry_semantics(
            self.engine, state, 0, icon_card("another-bird", "bird"),
            instance_id="another-bird",
        )
        self.assertEqual(29, state["players"][0]["money"])
        state, _ = play_entry_semantics(
            self.engine, state, 0, icon_card("first-asia", "asia"),
            instance_id="first-asia",
        )
        state = self.settle_effect_order(state)
        self.assertEqual(31, state["players"][0]["money"])
        self.assertEqual(1, state["players"][0]["tracks"]["appeal"])

    def test_waza_large_program_places_size_five_and_ignores_one_nonterrain_prerequisite(self):
        player = self.state["players"][0]
        next(card for card in player["action_cards"] if card["action"] == "sponsors")[
            "upgraded"
        ] = True
        player["tracks"]["reputation"] = 6
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(263), instance_id="large-program",
        )
        choice = state["resolution"]["pending_choice"]
        placement = next(option for option in choice["options"] if option["id"] != "stop")
        state, _ = self.engine.submit_choice(
            state, 0, choice["choice_id"], [placement["id"]],
        )
        self.assertTrue(any(
            building["type"] == "standard_enclosure" and building["size"] == 5
            for building in state["players"][0]["map"]["buildings"]
        ))

        def animal(identifier: str, size: int) -> ContentEntry:
            return ContentEntry(
                id=f"ark-nova:{identifier}", kind="animal",
                official_component_id=None, source_ids=(),
                display_title=identifier, display_summary="Ignore fixture.",
                facts={"enclosure_size": size, "tags": [], "icons": []},
                requirements=({
                    "op": "has_icon", "args": {"icon": "bird", "count": 99},
                },),
                effects=(), references=(), review_status="schema_valid",
                scenario_tests=(), reviewer=None, second_reviewer=None,
            )

        self.assertTrue(_animal_entry_is_eligible(
            self.engine, state, 0, animal("large", 4),
        ))
        self.assertFalse(_animal_entry_is_eligible(
            self.engine, state, 0, animal("small", 2),
        ))

    def test_quarantine_uses_physical_instance_and_continent_endgame_scores(self):
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(225), instance_id="physical-225-a",
        )
        self.assertTrue(state["players"][0]["flags"]["interaction_immunity"])
        state["players"][0]["icons"].update({
            "africa": 1, "americas": 1, "asia": 1, "australia": 1, "europe": 1,
        })
        state["endgame"]["final_scoring_discard_completed"] = True
        before = state["players"][0]["tracks"]["conservation"]
        state, _ = score_game(self.engine, state, [0] * 42)
        self.assertEqual(before + 1, state["players"][0]["tracks"]["conservation"])

    def test_import_marks_all_sponsors_compiled_instead_of_noop(self):
        assignment = self.sponsor(227)
        compiled = self.sponsor(205)
        self.assertEqual("compiled", assignment.facts["semantic_compile_status"])
        self.assertEqual([], assignment.facts["unresolved_effect_records"])
        self.assertEqual([], assignment.facts["unresolved_requirements"])
        self.assertEqual("compiled", compiled.facts["semantic_compile_status"])

    def test_waza_special_assignment_searches_and_enforces_chosen_size(self):
        self.state["players"][0]["tracks"]["reputation"] = 6
        self.state["zoo_deck"] = [
            {
                "id": "small-found", "kind": "animal",
                "facts": {"enclosure_size": 2},
            },
            {
                "id": "medium-discard", "kind": "animal",
                "facts": {"enclosure_size": 3},
            },
        ]
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(227), instance_id="assignment",
        )
        choice = state["resolution"]["pending_choice"]
        state, events = self.engine.submit_choice(
            state, 0, choice["choice_id"], ["small"],
        )
        self.assertTrue(state["players"][0]["flags"]["waza_small_only"])
        self.assertEqual(["small-found"], [card["id"] for card in state["players"][0]["hand"]])
        self.assertEqual(["medium-discard"], [card["id"] for card in state["zoo_discard"]])
        self.assertTrue(any(event["type"] == "waza_animal_search_resolved" for event in events))

        small = ContentEntry(
            id="ark-nova:waza-small", kind="animal", official_component_id=None,
            source_ids=(), display_title="Small", display_summary="WAZA fixture.",
            facts={"enclosure_size": 2, "tags": [], "icons": []},
            requirements=(), effects=(), references=(), review_status="schema_valid",
            scenario_tests=(), reviewer=None, second_reviewer=None,
        )
        large = ContentEntry(
            **{**small.__dict__, "id": "ark-nova:waza-large", "display_title": "Large",
               "facts": {"enclosure_size": 4, "tags": [], "icons": []}}
        )
        self.assertTrue(_animal_entry_is_eligible(self.engine, state, 0, small))
        self.assertFalse(_animal_entry_is_eligible(self.engine, state, 0, large))
        before = state["players"][0]["tracks"]["appeal"]
        state, _ = play_entry_semantics(
            self.engine, state, 0, small, instance_id="waza-small-played",
        )
        self.assertEqual(before + 2, state["players"][0]["tracks"]["appeal"])

    def test_diversity_researcher_counts_requirements_and_unlocks_terrain_rule(self):
        player = self.state["players"][0]
        next(card for card in player["action_cards"] if card["action"] == "sponsors")[
            "upgraded"
        ] = True
        player["played_cards"] = [{
            "id": "terrain-animal", "kind": "animal",
            "facts": {"rock_requirement": 2, "water_requirement": 1},
        }]
        before = player["money"]
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(219), instance_id="diversity",
        )
        self.assertEqual(before + 6, state["players"][0]["money"])
        self.assertEqual(2, state["players"][0]["tracks"]["appeal"])
        self.assertTrue(any(
            modifier.get("kind") == "diversity_researcher"
            for modifier in state["players"][0]["modifiers"]
        ))

    def test_archeologist_border_bonus_queues_an_uncovered_bonus_choice(self):
        self.state["players"][0]["icons"]["science"] = 1
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(221), instance_id="archeologist",
        )
        effects, pending = _claim_map_rewards(
            state["players"][0], [{"q": 4, "r": -1}],
        )
        self.assertEqual([], pending)
        self.assertEqual("take_any_map_placement_bonus", effects[0]["op"])
        state, _ = self.engine.start_effects(
            state, 0, effects, source_id="test:border-bonus",
        )
        choice = state["resolution"]["pending_choice"]
        self.assertGreater(len(choice["options"]), 1)
        selected = next(
            option for option in choice["options"]
            if option["value"]["reward"]["type"] == "gain_x_token"
        )
        state, _ = self.engine.submit_choice(
            state, 0, choice["choice_id"], [selected["id"]],
        )
        self.assertEqual(1, state["players"][0]["x_tokens"])

    def test_okapi_stable_spends_stored_token_to_play_sponsor_for_money(self):
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(253), instance_id="okapi",
        )
        source = next(card for card in state["players"][0]["played_cards"] if card["id"] == "okapi")
        self.assertEqual(3, source["stored_tokens"])
        self.assertIsNotNone(state["turn"]["bonus_sponsor_play"])
        target = self.sponsor(223)
        state["players"][0]["hand"] = [{"id": "institute", "entry_id": target.id}]
        actions = legal_bonus_sponsor_actions(
            self.engine, state, 0,
            {entry.id: entry for entry in self.pack.collections["sponsors"]},
        )
        play = next(item["action"] for item in actions if item["action"]["type"] == "play_bonus_sponsor_card")
        before = state["players"][0]["money"]
        state, _ = apply_bonus_sponsor_action(
            self.engine, state, 0,
            {entry.id: entry for entry in self.pack.collections["sponsors"]}, play,
        )
        source = next(card for card in state["players"][0]["played_cards"] if card["id"] == "okapi")
        self.assertEqual(2, source["stored_tokens"])
        self.assertEqual(before - int(target.facts["level"]), state["players"][0]["money"])
        self.assertTrue(any(card["id"] == "institute" for card in state["players"][0]["played_cards"]))

    def test_australia_expert_tucks_under_the_triggering_physical_card(self):
        self.state["players"][0]["hand"] = [{"id": "tuck-me"}]
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(212), instance_id="expert-australia-a",
        )
        choice = state["resolution"]["pending_choice"]
        state, _ = self.engine.submit_choice(
            state, 0, choice["choice_id"], ["tuck-me"],
        )
        expert = next(
            card for card in state["players"][0]["played_cards"]
            if card["id"] == "expert-australia-a"
        )
        self.assertEqual(["tuck-me"], [card["id"] for card in expert["tucked_cards"]])
        # The card's own Australia icon counts for its printed immediate reward.
        self.assertEqual(3, state["players"][0]["tracks"]["appeal"])

    def test_release_of_patents_uses_science_count_for_both_sides(self):
        self.state["players"][0]["icons"]["science"] = 3
        opponent_money = self.state["players"][1]["money"]
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(222), instance_id="patents",
        )
        state = self.settle_effect_order(state)
        self.assertEqual(3, state["players"][0]["tracks"]["conservation"])
        self.assertEqual(opponent_money + 6, state["players"][1]["money"])

    def test_release_of_patents_caps_conservation_and_opponent_money_at_three(self):
        self.state["players"][0]["icons"]["science"] = 6
        opponent_money = self.state["players"][1]["money"]
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(222), instance_id="patents",
        )
        state = self.settle_effect_order(state)
        self.assertEqual(3, state["players"][0]["tracks"]["conservation"])
        self.assertEqual(opponent_money + 6, state["players"][1]["money"])

    def test_audited_track_thresholds_use_printed_maximum_and_minimum(self):
        basic = self.sponsor(207)
        assignment = self.sponsor(227)
        self.state["players"][0]["action_cards"][4]["upgraded"] = True
        self.state["players"][0]["tracks"].update({"appeal": 25, "reputation": 5})
        from agentbga.ark_nova_official.cards import entry_is_eligible

        self.assertTrue(entry_is_eligible(self.engine, self.state, 0, basic))
        self.assertFalse(entry_is_eligible(self.engine, self.state, 0, assignment))
        self.state["players"][0]["tracks"].update({"appeal": 26, "reputation": 6})
        self.assertFalse(entry_is_eligible(self.engine, self.state, 0, basic))
        self.assertTrue(entry_is_eligible(self.engine, self.state, 0, assignment))

    def test_triggered_perception_two_draws_two_and_keeps_one(self):
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.sponsor(249), instance_id="owl-hut",
        )
        state["zoo_deck"] = [
            {"id": "deck-a", "kind": "sponsor"},
            {"id": "deck-b", "kind": "animal"},
        ]
        state, _ = play_entry_semantics(
            self.engine, state, 0, icon_card("bird-animal", "bird"),
            instance_id="bird-animal-1",
        )
        choice = state["resolution"]["pending_choice"]
        self.assertEqual(2, len(choice["options"]))
        state, _ = self.engine.submit_choice(
            state, 0, choice["choice_id"], [choice["options"][0]["id"]],
        )
        self.assertEqual(1, len(state["players"][0]["hand"]))
        self.assertEqual(1, len(state["zoo_discard"]))


if __name__ == "__main__":
    unittest.main()
