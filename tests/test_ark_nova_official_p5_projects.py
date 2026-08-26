from pathlib import Path
import unittest

from agentbga.ark_nova_map import building_shape_variants
from agentbga.ark_nova_presentation import map_display
from agentbga.ark_nova_official import (
    SemanticEngine,
    add_project_to_state,
    install_base_projects,
    legal_project_levels,
    legal_project_support_options,
    load_content_pack,
    new_semantic_state,
    support_project,
)
from agentbga.ark_nova_official.build_action import legal_free_building_placements


class ArkNovaOfficialP5ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.pack = load_content_pack(root / "content-packs" / "ark-nova" / "base-en-draft")
        cls.engine = SemanticEngine()

    def state_with_project(self, entry_id: str, *, base: bool) -> tuple[dict, object]:
        state = new_semantic_state(2, seed=53)
        state["phase"] = "active"
        entry = self.pack.entry(entry_id)
        return add_project_to_state(state, entry, base=base), entry

    def test_all_32_faces_compile_all_96_tiers(self):
        projects = [
            *self.pack.collections["base_conservation_projects"],
            *self.pack.collections["zoo_conservation_projects"],
        ]
        self.assertEqual(32, len(projects))
        self.assertEqual(96, sum(len(entry.facts["levels"]) for entry in projects))
        self.assertTrue(all(
            entry.facts["semantic_compile_status"] == "compiled"
            and entry.facts["unresolved_tiers"] == []
            for entry in projects
        ))

    def test_every_base_and_normal_project_face_reaches_its_high_tier(self):
        base_icons = {
            103: "africa", 104: "americas", 105: "australia", 106: "asia",
            107: "europe", 108: "primate", 109: "reptile", 110: "predator",
            111: "herbivore", 112: "bird",
        }
        for component in range(101, 113):
            state, entry = self.state_with_project(
                f"ark-nova:base-project-{component}", base=True,
            )
            player = state["players"][0]
            if component == 101:
                player["icons"].update({
                    icon: 1 for icon in (
                        "bear", "bird", "herbivore", "predator", "primate",
                    )
                })
            elif component == 102:
                player["icons"].update({
                    icon: 1 for icon in (
                        "africa", "americas", "asia", "australia", "europe",
                    )
                })
            else:
                player["icons"][base_icons[component]] = 5
            self.assertIn("high", {
                level["id"] for level in legal_project_levels(
                    self.engine, state, 0, entry,
                )
            }, component)

        for component in range(128, 133):
            state, entry = self.state_with_project(f"ark-nova:project-{component}", base=False)
            player = state["players"][0]
            if component in {128, 129}:
                player["icons"]["water" if component == 128 else "rock"] = 5
            elif component == 130:
                player["played_cards"] = [
                    {"id": f"small-{index}", "kind": "animal", "facts": {"enclosure_size": 2}}
                    for index in range(8)
                ]
            elif component == 131:
                player["played_cards"] = [
                    {"id": f"large-{index}", "kind": "animal", "facts": {"enclosure_size": 4}}
                    for index in range(4)
                ]
            else:
                player["icons"]["science"] = 5
            self.assertIn("high", {
                level["id"] for level in legal_project_levels(
                    self.engine, state, 0, entry,
                )
            }, component)

    def test_every_release_and_breeding_face_has_executable_support_choices(self):
        animals = list(self.pack.collections["animals"])
        for component in range(113, 123):
            state, entry = self.state_with_project(f"ark-nova:project-{component}", base=False)
            icon = entry.facts["release_icon"]
            animal = next(
                candidate for candidate in animals
                if int(candidate.facts.get("icons", {}).get(icon, 0)) > 0
                and int(candidate.facts.get("enclosure_size", 0)) >= 4
            )
            size = int(animal.facts["enclosure_size"])
            cells, shape_id, rotation = self._valid_standard_footprint(state, size)
            player = state["players"][0]
            player["played_cards"] = [{
                "id": f"release-{component}", "entry_id": animal.id,
                "kind": "animal", "facts": dict(animal.facts),
            }]
            player["map"]["buildings"] = [{
                "id": "release-enclosure", "type": "standard_enclosure", "size": size,
                "shape_id": shape_id, "rotation": rotation, "occupied": True,
                "used_capacity": size, "animal_ids": [f"release-{component}"],
                "cells": cells,
            }]
            self.assertIn("high", {
                option["id"] for option in legal_project_support_options(
                    self.engine, state, 0, entry,
                )
            }, component)

        for component in range(123, 128):
            state, entry = self.state_with_project(f"ark-nova:project-{component}", base=False)
            icon = entry.facts["breeding_icon"]
            animal = next(
                candidate for candidate in animals
                if int(candidate.facts.get("icons", {}).get(icon, 0)) > 0
                and candidate.facts.get("continents")
            )
            state["players"][0]["played_cards"] = [{
                "id": f"breeding-{component}", "entry_id": animal.id,
                "kind": "animal", "facts": dict(animal.facts),
            }]
            state["players"][0]["partner_zoos"] = [animal.facts["continents"][0]]
            self.assertEqual(3, len(legal_project_levels(self.engine, state, 0, entry)))

    @staticmethod
    def _valid_standard_footprint(
        state: dict, size: int,
    ) -> tuple[list[dict[str, int]], str, int]:
        buildable = {
            (cell["q"], cell["r"]) for cell in state["players"][0]["map"]["cells"]
            if cell["terrain"] == "buildable"
        }
        for anchor in sorted(buildable):
            for variant in building_shape_variants("standard_enclosure", size):
                cells = {
                    (anchor[0] + q, anchor[1] + r) for q, r in variant["cells"]
                }
                if cells <= buildable:
                    return (
                        [{"q": q, "r": r} for q, r in sorted(cells)],
                        variant["shape_id"], variant["rotation"],
                    )
        raise AssertionError(f"no valid size-{size} fixture")

    def test_two_player_base_row_blocks_one_different_level_on_each_card(self):
        state = new_semantic_state(2)
        entries = list(self.pack.collections["base_conservation_projects"][:3])
        state = install_base_projects(state, entries)
        self.assertEqual(
            [["high"], ["middle"], ["low"]],
            [project["blocked_levels"] for project in state["conservation_projects"]],
        )
        state["players"][0]["icons"].update({
            icon: 5 for icon in (
                "bear", "bird", "herbivore", "predator", "primate",
                "africa", "americas", "asia", "australia", "europe",
            )
        })
        self.assertNotIn("high", {
            level["id"] for level in legal_project_levels(
                self.engine, state, 0, entries[0],
            )
        })

    def test_base_diversity_and_icon_projects_use_exact_printed_thresholds(self):
        state, species = self.state_with_project("ark-nova:base-project-101", base=True)
        state["players"][0]["icons"].update({
            icon: 1 for icon in ("bear", "bird", "herbivore", "predator", "primate")
        })
        self.assertEqual(
            ["high", "middle", "low"],
            [level["id"] for level in legal_project_levels(self.engine, state, 0, species)],
        )

        state, habitat = self.state_with_project("ark-nova:base-project-102", base=True)
        state["players"][0]["icons"].update({
            icon: 1 for icon in ("africa", "americas", "asia", "australia")
        })
        self.assertEqual(
            ["middle", "low"],
            [level["id"] for level in legal_project_levels(self.engine, state, 0, habitat)],
        )

        for component, icon in ((103, "africa"), (108, "primate"), (112, "bird")):
            state, entry = self.state_with_project(
                f"ark-nova:base-project-{component}", base=True,
            )
            state["players"][0]["icons"][icon] = 4
            self.assertEqual(
                ["middle", "low"],
                [level["id"] for level in legal_project_levels(
                    self.engine, state, 0, entry,
                )],
            )

    def test_aquatic_counts_printed_icons_and_water_requirements(self):
        state, aquatic = self.state_with_project("ark-nova:project-128", base=False)
        player = state["players"][0]
        player["icons"]["water"] = 1
        player["played_cards"] = [{
            "id": "water-requirement-animal", "kind": "animal",
            "facts": {"water_requirement": 1},
        }]
        self.assertEqual(
            ["low"],
            [level["id"] for level in legal_project_levels(self.engine, state, 0, aquatic)],
        )

    def test_breeding_program_requires_matching_animal_and_partner_zoo(self):
        state, breeding = self.state_with_project("ark-nova:project-123", base=False)
        bird = self.pack.entry("ark-nova:animal-495")
        state["players"][0]["played_cards"] = [{
            "id": "secretary-a", "entry_id": bird.id, "kind": "animal",
            "facts": dict(bird.facts),
        }]
        self.assertEqual([], legal_project_levels(self.engine, state, 0, breeding))
        state["players"][0]["partner_zoos"] = ["africa"]
        levels = legal_project_levels(self.engine, state, 0, breeding)
        self.assertEqual(["slot-1", "slot-2", "slot-3"], [level["id"] for level in levels])
        self.assertEqual([(2, 2), (1, 2), (2, 0)], [
            (level["conservation"], level["reputation"]) for level in levels
        ])

    def test_release_project_selects_exact_size_animal_and_empties_smallest_enclosure(self):
        state, release = self.state_with_project("ark-nova:project-121", base=False)
        animal = self.pack.entry("ark-nova:animal-470")
        player = state["players"][0]
        player["tracks"]["appeal"] = 10
        player["icons"] = dict(animal.facts["icons"])
        player["tags"] = {tag: 1 for tag in animal.facts["tags"]}
        player["played_cards"] = [{
            "id": "mamba-a", "entry_id": animal.id, "kind": "animal",
            "display_title": animal.display_title, "facts": dict(animal.facts),
            "effects": list(animal.effects), "enclosure_id": "standard-a",
            "enclosure_space": 2,
        }]
        player["map"]["buildings"] = [{
            "id": "standard-a", "type": "standard_enclosure", "size": 2,
            "shape_id": "standard_enclosure-2", "rotation": 2,
            "occupied": True, "used_capacity": 2, "animal_ids": ["mamba-a"],
            "cells": [{"q": -4, "r": 2}, {"q": -3, "r": 1}],
        }]
        player["map"]["next_building_id"] = 2
        options = legal_project_support_options(self.engine, state, 0, release)
        self.assertEqual(["low"], sorted({option["id"] for option in options}))
        option = options[0]
        state, events = support_project(
            self.engine, state, 0, release, option["id"],
            release_animal_id=option["release_animal_id"],
            release_enclosure_id=option["release_enclosure_id"],
        )
        self.assertEqual([], state["players"][0]["played_cards"])
        self.assertEqual({}, state["players"][0]["icons"])
        self.assertEqual(
            10 - int(animal.facts["appeal"]),
            state["players"][0]["tracks"]["appeal"],
        )
        self.assertEqual(3, state["players"][0]["tracks"]["conservation"])
        self.assertFalse(state["players"][0]["map"]["buildings"][0]["occupied"])
        self.assertEqual("mamba-a", state["zoo_discard"][-1]["id"])
        released = next(event for event in events if event["type"] == "animal_released")
        self.assertEqual(int(animal.facts["appeal"]), released["appeal_lost"])

    def test_release_introduction_effect_is_separate_from_later_support(self):
        state, release = self.state_with_project("ark-nova:project-121", base=False)
        animal = self.pack.entry("ark-nova:animal-470")
        player = state["players"][0]
        player["played_cards"] = [{
            "id": "mamba-a", "entry_id": animal.id, "kind": "animal",
            "facts": dict(animal.facts),
        }]
        player["map"]["buildings"] = [{
            "id": "standard-a", "type": "standard_enclosure", "size": 2,
            "shape_id": "standard_enclosure-2", "rotation": 2,
            "occupied": True, "used_capacity": 2, "animal_ids": ["mamba-a"],
            "cells": [{"q": -4, "r": 2}, {"q": -3, "r": 1}],
        }]
        option = legal_project_support_options(self.engine, state, 0, release)[0]
        state, _ = support_project(
            self.engine, state, 0, release, option["id"],
            release_animal_id=option["release_animal_id"],
            release_enclosure_id=option["release_enclosure_id"],
            introduction_effects=release.facts["introduction_effects"],
        )
        self.assertEqual(1, state["players"][0]["tracks"]["reputation"])

    def test_player_board_project_token_grants_immediate_and_recurring_reward(self):
        state, species = self.state_with_project("ark-nova:base-project-101", base=True)
        state["players"][0]["icons"].update({
            icon: 1 for icon in ("bear", "bird", "herbivore", "predator", "primate")
        })
        state, _ = support_project(
            self.engine, state, 0, species, "high",
            token_slot_id="money-5", token_bonus_timing="before",
        )
        player = state["players"][0]
        self.assertEqual(30, player["money"])
        self.assertEqual(6, player["project_tokens_available"])
        slot = next(slot for slot in player["project_token_slots"] if slot["id"] == "money-5")
        self.assertTrue(slot["claimed"])
        self.assertTrue(any(
            modifier.get("id") == "project-token:money-5"
            for modifier in player["modifiers"]
        ))
        programs = map_display({
            **player,
            "appeal": player["tracks"]["appeal"],
            "conservation": player["tracks"]["conservation"],
            "reputation": player["tracks"]["reputation"],
            "upgrade_rewards_claimed": [],
            "conservation_rewards_claimed": [],
            "final_card_choice_resolved": False,
            "conservation_tokens_on_map": player["project_tokens_available"],
        })["player_board"]["conservation_programs"]
        money_slot = next(
            slot for program in programs for slot in program["slots"]
            if slot["id"] == "money-5"
        )
        self.assertEqual("claimed", money_slot["status"])
        state, events = self.engine.start_effects(state, 0, [{
            "op": "take_income", "timing": "system", "args": {},
        }], source_id="test:income")
        self.assertEqual(35, state["players"][0]["money"])
        self.assertTrue(any(event["type"] == "money_changed" for event in events))

    def test_immediate_project_token_reward_does_not_install_income(self):
        state, species = self.state_with_project("ark-nova:base-project-101", base=True)
        state["players"][0]["icons"].update({
            icon: 1 for icon in ("bear", "bird", "herbivore", "predator", "primate")
        })
        state, _ = support_project(
            self.engine, state, 0, species, "high",
            token_slot_id="x-3", token_bonus_timing="after",
        )
        self.assertEqual(3, state["players"][0]["x_tokens"])
        self.assertFalse(any(
            modifier.get("id") == "project-token:x-3"
            for modifier in state["players"][0]["modifiers"]
        ))

    def test_two_space_enclosure_token_opens_and_resolves_real_map_placement(self):
        state, species = self.state_with_project("ark-nova:base-project-101", base=True)
        state["players"][0]["icons"].update({
            icon: 1 for icon in ("bear", "bird", "herbivore", "predator", "primate")
        })
        state, _ = support_project(
            self.engine, state, 0, species, "high",
            token_slot_id="enclosure-2", token_bonus_timing="before",
        )
        choices = self.engine.legal_choice_actions(state, 0)
        self.assertTrue(choices)
        placements = [
            choice for choice in choices
            if choice["action"]["option_ids"][0].startswith("place-")
        ]
        self.assertTrue(placements)
        action = placements[0]["action"]
        state, _ = self.engine.submit_choice(
            state, 0, action["choice_id"], action["option_ids"],
        )
        building = state["players"][0]["map"]["buildings"][0]
        self.assertEqual(("standard_enclosure", 2), (building["type"], building["size"]))

    def test_release_uses_special_enclosure_tokens_before_any_standard_enclosure(self):
        state, release = self.state_with_project("ark-nova:project-121", base=False)
        animal = self.pack.entry("ark-nova:animal-470")
        player = state["players"][0]
        player["action_cards"][2]["upgraded"] = True
        player["map"]["buildings"] = [{
            "id": "standard-a", "type": "standard_enclosure", "size": 2,
            "shape_id": "standard_enclosure-2", "rotation": 0,
            "occupied": True, "used_capacity": 2, "animal_ids": [],
            "cells": [{"q": 2, "r": 0}, {"q": 3, "r": 0}],
        }]
        placement = legal_free_building_placements(player, ["reptile_house"])[0]
        special = {
            "id": "reptile-house", "type": "reptile_house", "size": 5,
            "shape_id": placement["shape_id"], "rotation": placement["rotation"],
            "occupied": False, "used_capacity": 1, "animal_ids": ["mamba-a"],
            "cells": placement["cells"],
        }
        player["map"]["buildings"].append(special)
        player["played_cards"] = [{
            "id": "mamba-a", "entry_id": animal.id, "kind": "animal",
            "facts": dict(animal.facts), "enclosure_id": special["id"],
        }]
        options = legal_project_support_options(self.engine, state, 0, release)
        self.assertEqual({"reptile-house"}, {
            option["release_enclosure_id"] for option in options
        })


if __name__ == "__main__":
    unittest.main()
