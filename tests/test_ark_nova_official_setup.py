from pathlib import Path
import unittest

from agentbga.ark_nova_official import ArkNovaOfficialPlugin, EvaluationContext, SemanticEngine, add_project_to_state, load_content_pack, new_semantic_state, present_entry, setup_official_game
from agentbga.ark_nova_official.setup import _bonus_tiles, card_instance


class ArkNovaOfficialSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.pack = load_content_pack(
            root / "content-packs" / "ark-nova" / "base-en-draft"
        )

    def test_multiplayer_setup_uses_printed_break_lengths_and_starting_appeal(self):
        expected = {2: 9, 3: 12, 4: 15}
        for player_count, break_limit in expected.items():
            with self.subTest(player_count=player_count):
                state = setup_official_game(player_count, 41, pack=self.pack)
                self.assertEqual(break_limit, state["break"]["limit"])
                self.assertEqual(
                    list(range(player_count)),
                    [player["tracks"]["appeal"] for player in state["players"]],
                )
                self.assertTrue(all(
                    player["tracks"]["conservation"] == 0
                    for player in state["players"]
                ))

    def test_match_runner_uses_ark_nova_specific_turn_limit(self):
        self.assertEqual(1000, ArkNovaOfficialPlugin().describe()["default_max_turns"])

    def test_multi_icon_cards_share_complete_engine_and_web_projection(self):
        expected = {
            "ark-nova:sponsor-246": {"rock": 2},
            "ark-nova:sponsor-245": {"water": 2},
            "ark-nova:animal-401": {"africa": 1, "predator": 2},
            "ark-nova:animal-407": {"asia": 1, "predator": 1, "water": 2},
            "ark-nova:animal-421": {
                "australia": 1, "predator": 1, "rock": 1, "water": 1,
            },
            "ark-nova:animal-441": {"europe": 2, "herbivore": 1},
            "ark-nova:animal-446": {
                "australia": 2, "herbivore": 1, "water": 2,
            },
        }
        for entry_id, icons in expected.items():
            with self.subTest(entry_id=entry_id):
                entry = self.pack.entry(entry_id)
                self.assertEqual(icons, present_entry(entry)["facts"]["icons"])

    def test_runtime_card_uses_executable_reputation_threshold(self):
        plugin = ArkNovaOfficialPlugin()
        entry = plugin.pack.entry("ark-nova:sponsor-228")
        state = plugin.setup(2, seed=47)
        state["players"][0]["hand"] = [card_instance(entry)]
        card = plugin.observe(state, 0)["players"][0]["hand"][0]
        self.assertEqual(
            [{"description_cn": "你的声望 >= 3", "description_en": "your reputation >= 3"}],
            card["resolved_requirements"],
        )
        state["players"][0]["tracks"]["reputation"] = 2
        self.assertFalse(plugin.engine.evaluate(
            entry.requirements[0],
            EvaluationContext(state=state, actor_seat=0),
        ))

    def test_two_player_base_projects_block_left_high_middle_and_right_low(self):
        state = setup_official_game(2, 42, pack=self.pack)
        base_projects = [
            project for project in state["conservation_projects"]
            if project["base"]
        ]
        self.assertEqual(
            [["high"], ["middle"], ["low"]],
            [project["blocked_levels"] for project in base_projects],
        )

    def test_two_player_project_view_marks_the_exact_covered_tier(self):
        plugin = ArkNovaOfficialPlugin()
        view = plugin.observe(plugin.setup(2, seed=42), 0)
        projects = view["base_conservation_projects"]

        self.assertEqual(
            ["high", "middle", "low"],
            [next(tier["id"] for tier in project["tiers"] if tier["blocked"])
             for project in projects],
        )
        self.assertTrue(all(
            sum(bool(tier["blocked"]) for tier in project["tiers"]) == 1
            for project in projects
        ))

    def test_zoo_project_and_player_claim_are_projected_for_web(self):
        plugin = ArkNovaOfficialPlugin()
        state = plugin.setup(2, seed=43)
        entry = plugin.pack.entry("ark-nova:project-113")
        state = add_project_to_state(
            state, entry, base=False, instance_id="zoo-project-card-a",
        )
        project = next(item for item in state["conservation_projects"] if item["id"] == entry.id)
        level_id = entry.facts["levels"][0]["id"]
        project["claims"].append({"seat": 0, "level_id": level_id})
        state["players"][0]["supported_projects"].append(entry.id)

        view = plugin.observe(state, 0)
        self.assertEqual(1, len(view["zoo_conservation_projects"]))
        presented = view["zoo_conservation_projects"][0]
        self.assertEqual("zoo-project-card-a", presented["instance_id"])
        self.assertEqual(entry.display_title, presented["display_title"])
        self.assertEqual(level_id, presented["claims"][0]["level_id"])
        self.assertEqual(
            entry.display_title,
            view["players"][0]["supported_project_details"][0]["display_title"],
        )

    def test_played_card_view_normalises_runtime_kind_for_web_grouping(self):
        plugin = ArkNovaOfficialPlugin()
        state = plugin.setup(2, seed=44)
        state["players"][0]["played_cards"] = [
            {"id": "animal-a", "kind": "animal", "facts": {}, "effects": []},
            {"id": "sponsor-a", "kind": "sponsor", "facts": {}, "effects": []},
        ]

        view = plugin.observe(state, 0)
        self.assertEqual(
            ["animal", "sponsor"],
            [card["card_type"] for card in view["players"][0]["played_cards"]],
        )

    def test_public_icon_counters_follow_semantic_icons_and_terrain_requirements(self):
        plugin = ArkNovaOfficialPlugin()
        state = plugin.setup(2, seed=45)
        player = state["players"][0]
        player["icons"].update({
            "asia": 2, "bear": 1, "pet": 1, "science": 2, "predator": 2,
        })
        player["played_cards"] = [{
            "id": "animal-a", "kind": "animal",
            "facts": {"rock_requirement": 1, "water_requirement": 2},
            "effects": [],
        }]

        counters = plugin.observe(state, 0)["players"][0]["public_summary"]["counters"]
        self.assertEqual(2, counters["continents"]["asia"])
        self.assertEqual(1, counters["animals"]["bear"])
        self.assertEqual(1, counters["animals"]["petting_zoo"])
        self.assertEqual(2, counters["animals"]["research"])
        self.assertEqual(2, counters["animals"]["predator"])
        self.assertEqual(1, counters["animals"]["rock"])
        presented = plugin.observe(state, 0)["players"][0]["played_cards"][0]
        self.assertEqual({"rock": 1, "water": 2}, presented["icons"])
        self.assertEqual(2, counters["animals"]["water"])

    def test_private_final_cards_include_live_scoring_projection(self):
        plugin = ArkNovaOfficialPlugin()
        state = plugin.setup(2, seed=46)
        entry = plugin.pack.entry("ark-nova:final-001")
        final_card = {
            "id": "final-live-a", "entry_id": entry.id, "kind": entry.kind,
            "facts": dict(entry.facts), "effects": list(entry.effects),
        }
        state["players"][0]["final_scoring_cards"] = [final_card]
        state["players"][0]["played_cards"] = [
            {"id": f"large-{index}", "kind": "animal", "facts": {"enclosure_size": 4}}
            for index in range(4)
        ]

        own = plugin.observe(state, 0)["players"][0]["final_scoring_cards"][0]
        hidden = plugin.observe(state, 1)["players"][0]["final_scoring_cards"][0]
        self.assertEqual(4, own["live_scoring"]["metric_value"])
        self.assertGreater(own["live_scoring"]["conservation"], 0)
        self.assertEqual({"hidden": True}, hidden)

    def test_setup_draws_four_of_the_nine_exact_bonus_tile_faces(self):
        tiles = _bonus_tiles(self.pack.collections["bonus_tiles"])
        self.assertEqual(9, len(tiles))
        self.assertEqual({
            "bonus-reputation-2", "bonus-x-3", "bonus-enclosure-3",
            "bonus-cards-3", "bonus-money-5", "bonus-money-10",
            "bonus-multiplier", "bonus-university", "bonus-partner-zoo",
        }, {tile["id"] for tile in tiles})
        state = setup_official_game(3, 43, pack=self.pack)
        installed = [
            tile for at in ("5", "8")
            for tile in state["conservation_bonus_slots"][at]
        ]
        self.assertEqual(4, len(installed))
        self.assertEqual(4, len({tile["id"] for tile in installed}))
        self.assertEqual(5, len(state["unused_conservation_bonus_tiles"]))
        self.assertTrue(all(tile["available"] for tile in installed))

    def test_choice_bonus_tiles_execute_build_multiplier_and_association_assets(self):
        engine = SemanticEngine()
        tiles = {tile["id"]: tile for tile in _bonus_tiles()}

        building_state = new_semantic_state(2)
        building_state, _ = engine.start_effects(
            building_state, 0, tiles["bonus-enclosure-3"]["effects"],
            source_id="test:bonus-enclosure-3",
        )
        placement = engine.legal_choice_actions(building_state, 0)[0]["action"]
        building_state, _ = engine.submit_choice(
            building_state, 0, placement["choice_id"], placement["option_ids"],
        )
        self.assertEqual(3, building_state["players"][0]["map"]["buildings"][0]["size"])
        self.assertEqual(
            "standard_enclosure",
            building_state["players"][0]["map"]["buildings"][0]["type"],
        )

        multiplier_state = new_semantic_state(2)
        multiplier_state, _ = engine.start_effects(
            multiplier_state, 0, tiles["bonus-multiplier"]["effects"],
            source_id="test:bonus-multiplier",
        )
        multiplier = next(
            item["action"] for item in engine.legal_choice_actions(multiplier_state, 0)
            if item["action"]["option_ids"] == ["association"]
        )
        multiplier_state, _ = engine.submit_choice(
            multiplier_state, 0, multiplier["choice_id"], multiplier["option_ids"],
        )
        association = next(
            card for card in multiplier_state["players"][0]["action_cards"]
            if card["action"] == "association"
        )
        self.assertEqual("multiplier", association["tokens"][0]["type"])

        university_state = new_semantic_state(2)
        university_state, _ = engine.start_effects(
            university_state, 0, tiles["bonus-university"]["effects"],
            source_id="test:bonus-university",
        )
        university = next(
            item["action"] for item in engine.legal_choice_actions(university_state, 0)
            if item["action"]["option_ids"] == ["research-2"]
        )
        university_state, _ = engine.submit_choice(
            university_state, 0, university["choice_id"], university["option_ids"],
        )
        self.assertEqual(["research-2"], university_state["players"][0]["universities"])
        self.assertEqual(2, university_state["players"][0]["icons"]["research"])
        self.assertEqual(
            0, university_state["association_board"]["universities"]["research-2"]["available"],
        )

    def test_partner_zoo_bonus_respects_association_two_upgrade_gate(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["players"][0]["partner_zoos"] = ["africa", "europe"]
        state["conservation_bonus_slots"]["5"] = [{
            **next(tile for tile in _bonus_tiles() if tile["id"] == "bonus-partner-zoo"),
            "available": True,
        }, {
            "id": "bonus-x-3", "label": "Gain 3 X-tokens", "available": True,
            "effects": [{
                "op": "gain_x_token", "timing": "immediate", "args": {"amount": 3},
            }],
        }]
        state, _ = engine.start_effects(
            state, 0, [{
                "op": "choose_conservation_reward", "timing": "system", "args": {"at": 5},
            }], source_id="test:partner-zoo-gate",
        )
        self.assertEqual(
            ["bonus-bonus-x-3"],
            [option["id"] for option in state["resolution"]["pending_choice"]["options"]],
        )

        state["resolution"]["pending_choice"] = None
        state["resolution"]["queue"] = []
        next(
            card for card in state["players"][0]["action_cards"]
            if card["action"] == "association"
        )["upgraded"] = True
        state, _ = engine.start_effects(
            state, 0, [{
                "op": "choose_conservation_reward", "timing": "system", "args": {"at": 5},
            }], source_id="test:partner-zoo-gate-upgraded",
        )
        self.assertIn(
            "bonus-bonus-partner-zoo",
            [option["id"] for option in state["resolution"]["pending_choice"]["options"]],
        )


if __name__ == "__main__":
    unittest.main()
