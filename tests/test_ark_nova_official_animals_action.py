from pathlib import Path
import unittest

from agentbga.ark_nova_map import building_shape_variants
from agentbga.mechanics import axial_hex_neighbors
from agentbga.ark_nova_official import (
    SemanticEngine,
    SemanticRuleError,
    apply_animals_execution_action,
    legal_animals_execution_actions,
    load_content_pack,
    new_semantic_state,
    start_action,
)
from agentbga.ark_nova_official.build_action import legal_free_building_placements


def action_card(state: dict, action: str) -> dict:
    return next(card for card in state["players"][0]["action_cards"] if card["action"] == action)


def add_building(
    state: dict, building_id: str, building_type: str, size: int,
    cells: set[tuple[int, int]], shape_id: str | None = None, rotation: int = 0,
) -> None:
    zoo_map = state["players"][0]["map"]
    zoo_map["buildings"].append({
        "id": building_id, "type": building_type, "size": size,
        "shape_id": shape_id or f"{building_type}-{size}", "rotation": rotation,
        "occupied": False,
        "cells": [{"q": q, "r": r} for q, r in sorted(cells)],
    })
    zoo_map["next_building_id"] += 1


class ArkNovaOfficialAnimalsActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        pack = load_content_pack(root / "content-packs" / "ark-nova" / "base-en-draft")
        cls.entries = {entry.id: entry for entry in pack.collections["animals"]}
        cls.secretary = cls.entries["ark-nova:animal-495"]
        cls.goat = cls.entries["ark-nova:animal-519"]
        cls.cougar = cls.entries["ark-nova:animal-413"]
        cls.reindeer = cls.entries["ark-nova:animal-438"]
        cls.small_a = cls.entries["ark-nova:animal-404"]
        cls.small_b = cls.entries["ark-nova:animal-405"]
        cls.small_display = cls.entries["ark-nova:animal-410"]
        cls.barbary_macaque = cls.entries["ark-nova:animal-456"]
        cls.australian_sea_lion = cls.entries["ark-nova:animal-422"]
        cls.frilled_lizard = cls.entries["ark-nova:animal-491"]

    def setUp(self):
        self.engine = SemanticEngine()
        self.state = new_semantic_state(2, seed=31)
        self.state["phase"] = "active"

    def choices(self, state: dict) -> list[dict]:
        return legal_animals_execution_actions(self.engine, state, 0, self.entries)

    def apply(self, state: dict, action: dict) -> tuple[dict, list[dict]]:
        state, events = apply_animals_execution_action(
            self.engine, state, 0, self.entries, action,
        )
        while (
            state["resolution"]["pending_choice"] is not None
            and state["resolution"]["pending_choice"].get("continuation", {}).get("type")
            == "choose_effect_order"
        ):
            choice = state["resolution"]["pending_choice"]
            state, resolved = self.engine.submit_choice(
                state, choice["seat"], choice["choice_id"], ["effect-0"],
            )
            events.extend(resolved)
        return state, events

    def test_animals_one_selects_card_before_enclosure_and_records_physical_instance(self):
        state = self.state
        state["players"][0]["x_tokens"] = 1
        state["players"][0]["partner_zoos"] = ["africa"]
        state["players"][0]["hand"] = [{
            "id": "secretary-copy-a", "entry_id": self.secretary.id,
        }]
        add_building(
            state, "enclosure-a", "standard_enclosure", 4,
            {(-4, 2), (-3, 1), (-4, 3), (-3, 2)},
        )
        state, _ = start_action(state, 0, "animals", x_by_execution=(1,))
        self.assertEqual(["animals:begin"], [choice["id"] for choice in self.choices(state)])
        state, _ = self.apply(state, {"type": "begin_animals_action"})
        selection = self.choices(state)[0]
        self.assertEqual("select_animal_card", selection["action"]["type"])
        self.assertIn("11 money", selection["label"])

        state, _ = self.apply(state, selection["action"])
        self.assertEqual(["animals:enclosure:enclosure-a"], [
            choice["id"] for choice in self.choices(state)
        ])
        state, events = self.apply(state, {
            "type": "play_selected_animal", "building_id": "enclosure-a",
        })
        self.assertEqual(14, state["players"][0]["money"])
        self.assertEqual(4, state["players"][0]["tracks"]["appeal"])
        self.assertEqual(1, state["players"][0]["tracks"]["conservation"])
        played = state["players"][0]["played_cards"][0]
        self.assertEqual("secretary-copy-a", played["id"])
        self.assertEqual(self.secretary.id, played["entry_id"])
        self.assertEqual("enclosure-a", played["enclosure_id"])
        self.assertTrue(state["players"][0]["map"]["buildings"][0]["occupied"])
        self.assertTrue(any(event["type"] == "animal_played" for event in events))
        self.assertIn("animals:finish", [choice["id"] for choice in self.choices(state)])

    def test_animal_partner_zoo_requirement_must_match_the_animals_continent(self):
        state = self.state
        player = state["players"][0]
        player["money"] = 100
        player["x_tokens"] = 1
        player["hand"] = [{"id": "macaque-a", "entry_id": self.barbary_macaque.id}]
        add_building(state, "enclosure-a", "standard_enclosure", 2, {(-4, 2), (-3, 1)})
        player["partner_zoos"] = ["europe"]
        state, _ = start_action(state, 0, "animals", x_by_execution=(1,))
        self.assertEqual([], self.choices(state))

        state["players"][0]["partner_zoos"] = ["africa"]
        self.assertEqual(["animals:begin"], [choice["id"] for choice in self.choices(state)])

    def test_two_physical_copies_of_one_card_face_can_both_be_played(self):
        state = self.state
        state["players"][0]["money"] = 100
        state["players"][0]["x_tokens"] = 4
        state["players"][0]["hand"] = [
            {"id": "secretary-copy-a", "entry_id": self.secretary.id},
            {"id": "secretary-copy-b", "entry_id": self.secretary.id},
        ]
        add_building(
            state, "enclosure-a", "standard_enclosure", 4,
            {(-4, 2), (-3, 1), (-4, 3), (-3, 2)},
        )
        add_building(
            state, "enclosure-b", "standard_enclosure", 4,
            {(-1, 2), (-2, 3), (-1, 3), (-2, 4)},
        )
        state, _ = start_action(state, 0, "animals", x_by_execution=(4,))
        state, _ = self.apply(state, {"type": "begin_animals_action"})
        for instance_id, enclosure_id in (
            ("secretary-copy-a", "enclosure-a"),
            ("secretary-copy-b", "enclosure-b"),
        ):
            state, _ = self.apply(state, {
                "type": "select_animal_card", "instance_id": instance_id, "source": "hand",
            })
            state, _ = self.apply(state, {
                "type": "play_selected_animal", "building_id": enclosure_id,
            })
        self.assertEqual(
            {"secretary-copy-a", "secretary-copy-b"},
            {card["id"] for card in state["players"][0]["played_cards"]},
        )
        self.assertEqual(["animals:finish"], [choice["id"] for choice in self.choices(state)])

    def test_animals_two_strength_one_is_legal_and_special_enclosure_tracks_capacity(self):
        state = self.state
        action_card(state, "animals")["upgraded"] = True
        state["players"][0]["hand"] = [{"id": "goat-a", "entry_id": self.goat.id}]
        add_building(
            state, "petting-zoo", "petting_zoo", 3,
            {(-1, 1), (-1, 2), (0, 2)},
        )
        state, _ = start_action(state, 0, "animals")
        self.assertEqual(1, state["turn"]["action_session"]["strengths"][0])
        state, _ = self.apply(state, {"type": "begin_animals_action"})
        state, _ = self.apply(state, {
            "type": "select_animal_card", "instance_id": "goat-a", "source": "hand",
        })
        self.assertEqual(["animals:enclosure:petting-zoo"], [
            choice["id"] for choice in self.choices(state)
        ])
        state, _ = self.apply(state, {
            "type": "play_selected_animal", "building_id": "petting-zoo",
        })
        building = state["players"][0]["map"]["buildings"][0]
        self.assertEqual(1, building["used_capacity"])
        self.assertFalse(building["occupied"])

    def test_frilled_lizard_offers_standard_or_reptile_house_with_explicit_capacity(self):
        state = self.state
        player = state["players"][0]
        player["money"] = 100
        player["x_tokens"] = 1
        player["hand"] = [{"id": "frilled-a", "entry_id": self.frilled_lizard.id}]
        player["modifiers"].append({"kind": "diversity_researcher"})
        action_card(state, "build")["upgraded"] = True
        standard_placement = legal_free_building_placements(
            player, ["standard_enclosure_2"],
        )[0]
        add_building(
            state, "standard-2", "standard_enclosure", 2,
            {(cell["q"], cell["r"]) for cell in standard_placement["cells"]},
            shape_id=standard_placement["shape_id"],
            rotation=standard_placement["rotation"],
        )
        reptile_placement = legal_free_building_placements(
            player, ["reptile_house"],
        )[0]
        add_building(
            state, "reptile-house", "reptile_house", 5,
            {(cell["q"], cell["r"]) for cell in reptile_placement["cells"]},
            shape_id=reptile_placement["shape_id"],
            rotation=reptile_placement["rotation"],
        )
        state, _ = start_action(state, 0, "animals", x_by_execution=(1,))
        state, _ = self.apply(state, {"type": "begin_animals_action"})
        state, _ = self.apply(state, {
            "type": "select_animal_card", "instance_id": "frilled-a", "source": "hand",
        })
        choices = self.choices(state)
        self.assertEqual({
            "animals:enclosure:standard-2", "animals:enclosure:reptile-house",
        }, {choice["id"] for choice in choices})
        standard = next(choice for choice in choices if choice["id"].endswith("standard-2"))
        special = next(choice for choice in choices if choice["id"].endswith("reptile-house"))
        self.assertIn("printed requirement 2", standard["label"])
        self.assertIn("uses 1 capacity", special["label"])
        self.assertEqual(4, special["presentation"]["capacity_after"])

    def test_waza_small_program_adds_one_paid_play_then_optional_display_take(self):
        state = self.state
        player = state["players"][0]
        player["money"] = 100
        player["x_tokens"] = 2
        player["modifiers"].append({
            "id": "waza-small", "source_id": "ark-nova:sponsor-228",
            "trigger": "static", "condition": None, "effects": [],
            "kind": "waza_small_animal_program", "amount": 1,
        })
        player["hand"] = [
            {"id": "small-a", "entry_id": self.small_a.id},
            {"id": "small-b", "entry_id": self.small_b.id},
        ]
        state["card_display"] = [{
            "id": "small-display", "entry_id": self.small_display.id,
        }]
        state["zoo_deck"] = [{"id": "replacement", "entry_id": self.small_display.id}]
        add_building(
            state, "small-enclosure-a", "standard_enclosure", 2,
            {(-4, 2), (-3, 1)},
        )
        add_building(
            state, "small-enclosure-b", "standard_enclosure", 1,
            {(3, -3)},
        )
        state, _ = start_action(state, 0, "animals", x_by_execution=(2,))
        state, _ = self.apply(state, {"type": "begin_animals_action"})
        state, _ = self.apply(state, {
            "type": "select_animal_card", "instance_id": "small-a", "source": "hand",
        })
        state, _ = self.apply(state, {
            "type": "play_selected_animal", "building_id": "small-enclosure-a",
        })
        state, events = self.apply(state, {"type": "finish_animals_action"})
        self.assertTrue(any(event["type"] == "waza_small_animal_window_opened" for event in events))
        state, _ = self.apply(state, {
            "type": "select_animal_card", "instance_id": "small-b", "source": "hand",
        })
        state, _ = self.apply(state, {
            "type": "play_selected_animal", "building_id": "small-enclosure-b",
        })
        take = next(
            choice["action"] for choice in self.choices(state)
            if choice["action"]["type"] == "take_waza_small_animal"
        )
        state, events = self.apply(state, take)
        self.assertIn("small-display", [card["id"] for card in state["players"][0]["hand"]])
        self.assertEqual(2, len([
            card for card in state["players"][0]["played_cards"]
            if card["kind"] == "animal"
        ]))
        self.assertIsNone(state["turn"]["action_session"])
        self.assertTrue(any(event["type"] == "waza_small_animal_taken" for event in events))

    def test_strength_five_reputation_precedes_display_range_and_refill_waits_for_finish(self):
        state = self.state
        animals = action_card(state, "animals")
        sponsors = action_card(state, "sponsors")
        animals["position"], sponsors["position"] = sponsors["position"], animals["position"]
        animals["upgraded"] = True
        state["players"][0]["tracks"]["reputation"] = 3
        state["players"][0]["money"] = 100
        state["card_display"] = [
            {"id": f"secretary-display-{index}", "entry_id": self.secretary.id}
            for index in range(1, 7)
        ]
        state["zoo_deck"] = [{"id": "replacement", "entry_id": self.secretary.id}]
        add_building(
            state, "enclosure-a", "standard_enclosure", 4,
            {(-4, 2), (-3, 1), (-4, 3), (-3, 2)},
        )
        state, _ = start_action(state, 0, "animals")
        state, _ = self.apply(state, {"type": "begin_animals_action"})
        self.assertEqual(4, state["players"][0]["tracks"]["reputation"])
        display_choices = {
            choice["action"]["instance_id"] for choice in self.choices(state)
            if choice["action"]["type"] == "select_animal_card"
        }
        self.assertEqual({
            "secretary-display-1", "secretary-display-2", "secretary-display-3",
        }, display_choices)
        state, _ = self.apply(state, {
            "type": "select_animal_card", "instance_id": "secretary-display-3",
            "source": "display",
        })
        state, _ = self.apply(state, {
            "type": "play_selected_animal", "building_id": "enclosure-a",
        })
        self.assertEqual(83, state["players"][0]["money"])
        played_record = state["turn"]["action_session"]["animals_resolution"]["played"][0]
        self.assertEqual(3, played_record["folder_cost"])
        self.assertEqual(5, len(state["card_display"]))
        state, events = self.apply(state, {"type": "finish_animals_action"})
        self.assertEqual(6, len(state["card_display"]))
        self.assertTrue(any(event["type"] == "card_display_refilled" for event in events))

    def test_animals_two_display_position_four_costs_four_money(self):
        state = self.state
        animals = action_card(state, "animals")
        sponsors = action_card(state, "sponsors")
        animals["position"], sponsors["position"] = sponsors["position"], animals["position"]
        animals["upgraded"] = True
        state["players"][0]["tracks"]["reputation"] = 6
        state["players"][0]["money"] = 100
        state["card_display"] = [
            {"id": f"secretary-display-{index}", "entry_id": self.secretary.id}
            for index in range(1, 7)
        ]
        add_building(
            state, "enclosure-a", "standard_enclosure", 4,
            {(-4, 2), (-3, 1), (-4, 3), (-3, 2)},
        )

        state, _ = start_action(state, 0, "animals")
        state, _ = self.apply(state, {"type": "begin_animals_action"})
        self.assertEqual(7, state["players"][0]["tracks"]["reputation"])
        state, _ = self.apply(state, {
            "type": "select_animal_card", "instance_id": "secretary-display-4",
            "source": "display",
        })
        state, _ = self.apply(state, {
            "type": "play_selected_animal", "building_id": "enclosure-a",
        })
        self.assertEqual(82, state["players"][0]["money"])
        self.assertEqual(
            4,
            state["turn"]["action_session"]["animals_resolution"]["played"][0]["folder_cost"],
        )

    def test_illegal_standard_enclosure_for_pettting_zoo_animal_is_never_offered(self):
        state = self.state
        state["players"][0]["x_tokens"] = 1
        state["players"][0]["hand"] = [{"id": "goat-a", "entry_id": self.goat.id}]
        add_building(state, "standard-a", "standard_enclosure", 1, {(4, -4)})
        state, _ = start_action(state, 0, "animals", x_by_execution=(1,))
        self.assertEqual([], self.choices(state))
        with self.assertRaisesRegex(SemanticRuleError, "not currently legal"):
            self.apply(state, {"type": "begin_animals_action"})

    def test_rock_requirement_filters_enclosures_by_distinct_adjacent_terrain(self):
        state = self.state
        player = state["players"][0]
        player["x_tokens"] = 2
        player["hand"] = [{"id": "cougar-a", "entry_id": self.cougar.id}]
        buildable = {
            (cell["q"], cell["r"]) for cell in player["map"]["cells"]
            if cell["terrain"] == "buildable"
        }
        rocks = {
            (cell["q"], cell["r"]) for cell in player["map"]["cells"]
            if cell["terrain"] == "rock"
        }
        candidates = []
        for anchor in buildable:
            for variant in building_shape_variants("standard_enclosure", 3):
                cells = {
                    (anchor[0] + q, anchor[1] + r) for q, r in variant["cells"]
                }
                if cells <= buildable:
                    adjacent = set().union(*(axial_hex_neighbors(cell) for cell in cells))
                    candidates.append((cells, bool(adjacent & rocks)))
        good = next(cells for cells, touches in candidates if touches)
        bad = next(
            cells for cells, touches in candidates
            if not touches and not cells & good
        )
        add_building(state, "rock-good", "standard_enclosure", 3, good)
        add_building(state, "rock-bad", "standard_enclosure", 3, bad)
        state, _ = start_action(state, 0, "animals", x_by_execution=(2,))
        state, _ = self.apply(state, {"type": "begin_animals_action"})
        state, _ = self.apply(state, {
            "type": "select_animal_card", "instance_id": "cougar-a", "source": "hand",
        })
        self.assertEqual(["animals:enclosure:rock-good"], [
            choice["id"] for choice in self.choices(state)
        ])

    def test_australian_sea_lion_requires_a_water_adjacent_enclosure(self):
        state = self.state
        player = state["players"][0]
        player["money"] = 100
        player["x_tokens"] = 3
        player["partner_zoos"] = ["australia"]
        player["hand"] = [{
            "id": "sea-lion-a", "entry_id": self.australian_sea_lion.id,
        }]
        buildable = {
            (cell["q"], cell["r"]) for cell in player["map"]["cells"]
            if cell["terrain"] == "buildable"
        }
        water = {
            (cell["q"], cell["r"]) for cell in player["map"]["cells"]
            if cell["terrain"] == "water"
        }
        candidates = []
        for anchor in buildable:
            for variant in building_shape_variants("standard_enclosure", 4):
                cells = {
                    (anchor[0] + q, anchor[1] + r) for q, r in variant["cells"]
                }
                if cells <= buildable:
                    adjacent = set().union(*(axial_hex_neighbors(cell) for cell in cells))
                    candidates.append((cells, bool(adjacent & water)))
        good = next(cells for cells, touches in candidates if touches)
        bad = next(
            cells for cells, touches in candidates
            if not touches and not cells & good
        )
        add_building(state, "water-good", "standard_enclosure", 4, good)
        add_building(state, "water-bad", "standard_enclosure", 4, bad)
        state, _ = start_action(state, 0, "animals", x_by_execution=(3,))
        state, _ = self.apply(state, {"type": "begin_animals_action"})
        state, _ = self.apply(state, {
            "type": "select_animal_card", "instance_id": "sea-lion-a",
            "source": "hand",
        })
        self.assertEqual(["animals:enclosure:water-good"], [
            choice["id"] for choice in self.choices(state)
        ])

    def test_flock_animal_may_share_only_an_occupied_herbivore_enclosure(self):
        state = self.state
        player = state["players"][0]
        player["x_tokens"] = 2
        player["hand"] = [{"id": "reindeer-a", "entry_id": self.reindeer.id}]
        player["played_cards"] = [
            {"id": "resident-herbivore", "facts": {"icons": ["herbivore"]}},
            {"id": "resident-predator", "facts": {"icons": ["predator"]}},
        ]
        add_building(
            state, "herbivore-home", "standard_enclosure", 3,
            {(-4, 2), (-3, 1), (-3, 2)},
        )
        add_building(
            state, "predator-home", "standard_enclosure", 3,
            {(1, -3), (1, -2), (0, -2)},
        )
        buildings = player["map"]["buildings"]
        buildings[0].update({
            "occupied": True, "used_capacity": 3,
            "animal_ids": ["resident-herbivore"],
        })
        buildings[1].update({
            "occupied": True, "used_capacity": 3,
            "animal_ids": ["resident-predator"],
        })
        state, _ = start_action(state, 0, "animals", x_by_execution=(2,))
        state, _ = self.apply(state, {"type": "begin_animals_action"})
        state, _ = self.apply(state, {
            "type": "select_animal_card", "instance_id": "reindeer-a", "source": "hand",
        })
        self.assertEqual(["animals:enclosure:herbivore-home"], [
            choice["id"] for choice in self.choices(state)
        ])
        state, events = self.apply(state, {
            "type": "play_selected_animal", "building_id": "herbivore-home",
        })
        shared = state["players"][0]["map"]["buildings"][0]
        self.assertEqual(
            ["resident-herbivore", "reindeer-a"], shared["animal_ids"],
        )
        animal_event = next(event for event in events if event["type"] == "animal_played")
        self.assertEqual(0, animal_event["space"])


if __name__ == "__main__":
    unittest.main()
