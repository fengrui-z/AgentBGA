import unittest
from pathlib import Path

from agentbga.ark_nova_map import building_shape_variants, valid_building_shape
from agentbga.ark_nova_official import (
    SemanticEngine,
    SemanticRuleError,
    apply_build_execution_action,
    legal_build_execution_actions,
    load_content_pack,
    new_semantic_state,
    play_entry_semantics,
    start_action,
)


def action_card(state: dict, action: str) -> dict:
    return next(card for card in state["players"][0]["action_cards"] if card["action"] == action)


def footprint(action: dict) -> frozenset[tuple[int, int]]:
    return frozenset((cell["q"], cell["r"]) for cell in action["cells"])


class ArkNovaOfficialBuildActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.pack = load_content_pack(root / "content-packs" / "ark-nova" / "base-en-draft")

    def setUp(self):
        self.engine = SemanticEngine()
        self.state = new_semantic_state(2, seed=23)
        self.state["phase"] = "active"

    def choices(self, state: dict) -> list[dict]:
        return legal_build_execution_actions(state, 0)

    def apply(self, state: dict, action: dict) -> tuple[dict, list[dict]]:
        return apply_build_execution_action(self.engine, state, 0, action)

    def test_map_zero_and_anchor_preserving_rotations_include_reported_border_placements(self):
        state = self.state
        state["players"][0]["x_tokens"] = 1
        state, _ = start_action(state, 0, "build", x_by_execution=(1,))
        placements = [item["action"] for item in self.choices(state)]
        expected = [
            (3, {(-4, 2), (-3, 1), (-3, 2)}),
            (3, {(1, -3), (1, -2), (0, -2)}),
            (4, {(-4, 2), (-3, 1), (-4, 3), (-3, 2)}),
            (4, {(-1, 2), (-2, 3), (-1, 3), (-2, 4)}),
        ]
        for size, cells in expected:
            self.assertTrue(any(
                action["building_type"] == "standard_enclosure"
                and action["size"] == size and footprint(action) == cells
                for action in placements
            ), (size, cells))

        size_five = building_shape_variants("standard_enclosure", 5)[0]["cells"]
        self.assertEqual(5, len(size_five))
        self.assertEqual({0, 1}, {q for q, _ in size_five})

    def test_branched_size_four_legacy_shape_is_not_offered(self):
        state = self.state
        state["players"][0]["x_tokens"] = 2
        state, _ = start_action(state, 0, "build", x_by_execution=(2,))
        placements = [item["action"] for item in self.choices(state)]
        branched = {(-1, 2), (-2, 3), (-2, 4), (0, 2)}

        self.assertFalse(any(
            action.get("building_type") == "standard_enclosure"
            and action.get("size") == 4 and footprint(action) == branched
            for action in placements
        ))
        self.assertFalse(any(
            "variant" in variant["shape_id"]
            for variant in building_shape_variants("standard_enclosure", 4)
        ))
        # Compatibility: a match saved by an older build remains loadable even
        # though this footprint is no longer generated as a legal action.
        self.assertTrue(valid_building_shape({
            "type": "standard_enclosure", "size": 4,
            "cells": [{"q": q, "r": r} for q, r in branched],
        }))

    def test_build_one_places_exactly_one_building_then_requires_finish(self):
        state, _ = start_action(self.state, 0, "build")
        placement = next(
            item["action"] for item in self.choices(state)
            if item["action"].get("building_type") == "pavilion"
            and not any(
                cell.get("placement_bonus")
                for cell in state["players"][0]["map"]["cells"]
                if (cell["q"], cell["r"]) in footprint(item["action"])
            )
        )
        state, _ = self.apply(state, placement)
        self.assertEqual(23, state["players"][0]["money"])
        self.assertEqual(1, state["players"][0]["tracks"]["appeal"])
        self.assertEqual(["build:finish"], [item["id"] for item in self.choices(state)])

        state, events = self.apply(state, {"type": "finish_build_action"})
        self.assertEqual(1, action_card(state, "build")["position"])
        self.assertEqual(1, state["active_seat"])
        self.assertEqual("turn_finished", events[-1]["type"])

    def test_build_two_can_build_different_sizes_with_one_strength_budget(self):
        state = self.state
        state["players"][0]["x_tokens"] = 2
        action_card(state, "build")["upgraded"] = True
        state, _ = start_action(state, 0, "build", x_by_execution=(2,))
        first = next(
            item["action"] for item in self.choices(state)
            if item["action"].get("building_type") == "standard_enclosure"
            and item["action"].get("size") == 1
            and not any(cell.get("placement_bonus") for cell in state["players"][0]["map"]["cells"]
                        if (cell["q"], cell["r"]) in footprint(item["action"]))
        )
        state, _ = self.apply(state, first)
        second = next(
            item["action"] for item in self.choices(state)
            if item["action"].get("building_type") == "standard_enclosure"
            and item["action"].get("size") == 2
        )
        state, _ = self.apply(state, second)
        self.assertIn("build:finish", [item["id"] for item in self.choices(state)])
        self.assertFalse(any(
            item["action"].get("building_type") == "standard_enclosure"
            and item["action"].get("size") in {1, 2}
            for item in self.choices(state)
        ))
        state, _ = self.apply(state, {"type": "finish_build_action"})
        self.assertEqual([1, 2], sorted(
            building["size"] for building in state["players"][0]["map"]["buildings"]
        ))

    def test_engineer_adds_one_same_kind_building_without_spending_strength(self):
        state, _ = play_entry_semantics(
            self.engine, self.state, 0, self.pack.entry("ark-nova:sponsor-217"),
            instance_id="engineer-a",
        )
        state, _ = start_action(state, 0, "build")
        first = next(
            item["action"] for item in self.choices(state)
            if item["action"].get("building_type") == "standard_enclosure"
            and item["action"].get("size") == 2
        )
        state, _ = self.apply(state, first)
        extras = [
            item["action"] for item in self.choices(state)
            if item["action"].get("type") == "place_engineer_building"
        ]
        self.assertTrue(extras)
        self.assertTrue(all(
            action["building_type"] == "standard_enclosure" and action["size"] == 2
            for action in extras
        ))
        remaining = state["turn"]["action_session"]["build_resolution"]["remaining_strength"]
        state, events = self.apply(state, extras[0])
        self.assertEqual(
            remaining,
            state["turn"]["action_session"]["build_resolution"]["remaining_strength"],
        )
        self.assertEqual(17, state["players"][0]["money"])
        self.assertTrue(any(event.get("engineer_extra") for event in events))
        self.assertFalse(any(
            item["action"].get("type") == "place_engineer_building"
            for item in self.choices(state)
        ))

    def test_diversity_researcher_permits_building_on_water_or_rock(self):
        state = self.state
        action_card(state, "sponsors")["upgraded"] = True
        state, _ = play_entry_semantics(
            self.engine, state, 0, self.pack.entry("ark-nova:sponsor-219"),
            instance_id="diversity-researcher",
        )
        state, _ = start_action(state, 0, "build")
        terrain = {
            (cell["q"], cell["r"]): cell["terrain"]
            for cell in state["players"][0]["map"]["cells"]
        }
        placement = next(
            item["action"] for item in self.choices(state)
            if any(terrain[coordinate] in {"water", "rock"} for coordinate in footprint(item["action"]))
        )
        state, events = self.apply(state, placement)
        self.assertTrue(any(
            terrain[(cell["q"], cell["r"])] in {"water", "rock"}
            for cell in state["players"][0]["map"]["buildings"][-1]["cells"]
        ))
        self.assertTrue(any(event["type"] == "building_placed" for event in events))

    def test_build_two_cells_and_special_enclosures_are_gated_by_upgraded_side(self):
        state, _ = start_action(self.state, 0, "build")
        side_one = [item["action"] for item in self.choices(state)]
        gated = {(3, -2), (2, -1)}
        self.assertFalse(any(footprint(action) & gated for action in side_one))
        self.assertFalse(any(action["building_type"] in {
            "reptile_house", "large_bird_aviary",
        } for action in side_one))

        upgraded = new_semantic_state(2)
        upgraded["phase"] = "active"
        upgraded["players"][0]["x_tokens"] = 2
        action_card(upgraded, "build")["upgraded"] = True
        upgraded, _ = start_action(upgraded, 0, "build", x_by_execution=(2,))
        side_two = [item["action"] for item in self.choices(upgraded)]
        self.assertTrue(any(footprint(action) & gated for action in side_two))
        self.assertTrue(any(action["building_type"] == "reptile_house" for action in side_two))
        self.assertTrue(any(action["building_type"] == "large_bird_aviary" for action in side_two))

    def test_build_two_may_move_standard_enclosure_animal_into_new_reptile_house(self):
        state = self.state
        player = state["players"][0]
        player["x_tokens"] = 2
        action_card(state, "build")["upgraded"] = True
        animal = self.pack.entry("ark-nova:animal-470")
        player["played_cards"] = [{
            "id": "mamba-a", "entry_id": animal.id, "kind": "animal",
            "display_title": animal.display_title, "facts": dict(animal.facts),
            "effects": list(animal.effects), "enclosure_id": "standard-a",
            "enclosure_space": 2,
        }]
        player["map"]["buildings"] = [{
            "id": "standard-a", "type": "standard_enclosure", "size": 2,
            "shape_id": "standard_enclosure-2", "rotation": 0,
            "occupied": True, "used_capacity": 2, "animal_ids": ["mamba-a"],
            "cells": [{"q": 2, "r": 0}, {"q": 3, "r": 0}],
        }]
        player["map"]["next_building_id"] = 2
        state, _ = start_action(state, 0, "build", x_by_execution=(2,))
        reptile = next(
            choice["action"] for choice in self.choices(state)
            if choice["action"].get("building_type") == "reptile_house"
        )
        state, _ = self.apply(state, reptile)
        migrations = self.choices(state)
        move = next(
            choice["action"] for choice in migrations
            if choice["action"]["type"] == "move_animal_to_special_enclosure"
        )
        self.assertEqual("mamba-a", move["instance_id"])
        self.assertEqual(1, move["space"])
        state, events = self.apply(state, move)
        standard = next(
            building for building in state["players"][0]["map"]["buildings"]
            if building["id"] == "standard-a"
        )
        special = next(
            building for building in state["players"][0]["map"]["buildings"]
            if building["type"] == "reptile_house"
        )
        self.assertFalse(standard["occupied"])
        self.assertEqual([], standard["animal_ids"])
        self.assertEqual(["mamba-a"], special["animal_ids"])
        self.assertEqual(1, special["used_capacity"])
        self.assertEqual(special["id"], state["players"][0]["played_cards"][0]["enclosure_id"])
        self.assertTrue(any(
            event["type"] == "animal_moved_to_special_enclosure" for event in events
        ))
        state, _ = self.apply(state, {"type": "finish_special_enclosure_migration"})
        self.assertIn("build:finish", [choice["id"] for choice in self.choices(state)])

    def test_money_placement_bonus_is_at_three_minus_three_and_is_consumed(self):
        state = self.state
        action_card(state, "build")["upgraded"] = True
        state, _ = start_action(state, 0, "build")
        border = next(
            item["action"] for item in self.choices(state)
            if item["action"].get("building_type") == "standard_enclosure"
            and item["action"].get("size") == 1
            and footprint(item["action"]) == {(4, -3)}
        )
        state, _ = self.apply(state, border)
        placement = next(
            item["action"] for item in self.choices(state)
            if item["action"].get("building_type") == "pavilion"
            and footprint(item["action"]) == {(3, -3)}
        )
        state, events = self.apply(state, placement)
        self.assertEqual(26, state["players"][0]["money"])
        cell = next(
            cell for cell in state["players"][0]["map"]["cells"]
            if (cell["q"], cell["r"]) == (3, -3)
        )
        self.assertNotIn("placement_bonus", cell)
        self.assertTrue(any(
            event["type"] == "money_changed" and event["delta"] == 5 for event in events
        ))

    def test_stale_or_malformed_placement_is_rejected_without_partial_payment(self):
        state, _ = start_action(self.state, 0, "build")
        before_money = state["players"][0]["money"]
        with self.assertRaisesRegex(SemanticRuleError, "not currently legal"):
            self.apply(state, {
                "type": "place_building", "building_type": "pavilion", "size": 1,
                "shape_id": "pavilion-1", "rotation": 0,
                "anchor": {"q": 0, "r": 0}, "cost": 0,
                "cells": [{"q": 0, "r": 0}],
            })
        self.assertEqual(before_money, state["players"][0]["money"])
        self.assertEqual([], state["players"][0]["map"]["buildings"])

    def test_take_card_map_reward_uses_reputation_range_and_refills_immediately(self):
        state = self.state
        action_card(state, "build")["upgraded"] = True
        state["card_display"] = [{"id": f"display-{index}"} for index in range(1, 7)]
        state["zoo_deck"] = [{"id": "replacement"}]
        state, _ = start_action(state, 0, "build")
        route = [
            ("standard_enclosure", {(-4, 2)}),
            ("pavilion", {(-3, 1)}),
            ("kiosk", {(-3, 0)}),
        ]
        for building_type, cells in route:
            placement = next(
                item["action"] for item in self.choices(state)
                if item["action"].get("building_type") == building_type
                and footprint(item["action"]) == cells
            )
            state, _ = self.apply(state, placement)

        choices = self.choices(state)
        self.assertEqual(
            {"build:reward:card:deck", "build:reward:card:display:display-1"},
            {item["id"] for item in choices},
        )
        state, _ = self.apply(state, {
            "type": "take_build_reward_card", "source": "display", "card_id": "display-1",
        })
        self.assertIn("display-1", [card["id"] for card in state["players"][0]["hand"]])
        self.assertEqual(6, len(state["card_display"]))
        self.assertIn("replacement", [card["id"] for card in state["card_display"]])
        self.assertEqual(["build:finish"], [item["id"] for item in self.choices(state)])

    def test_clever_reward_resolves_after_build_card_moves_to_slot_one(self):
        state = self.state
        zoo_map = state["players"][0]["map"]
        zoo_map["buildings"].append({
            "id": "fixture-enclosure", "type": "standard_enclosure", "size": 1,
            "shape_id": "standard_enclosure-1", "rotation": 0, "occupied": False,
            "cells": [{"q": 2, "r": 0}],
        })
        zoo_map["next_building_id"] = 2
        state, _ = start_action(state, 0, "build")
        clever = next(
            item["action"] for item in self.choices(state)
            if item["action"].get("building_type") == "pavilion"
            and footprint(item["action"]) == {(1, 0)}
        )
        state, _ = self.apply(state, clever)
        self.assertEqual(["build:finish"], [item["id"] for item in self.choices(state)])
        state, _ = self.apply(state, {"type": "finish_build_action"})
        self.assertEqual(1, action_card(state, "build")["position"])
        self.assertEqual("after_finishing", state["phase"])
        self.assertIsNotNone(state["resolution"]["pending_choice"])

        sponsors = next(
            item["action"] for item in self.engine.legal_choice_actions(state, 0)
            if item["action"]["option_ids"] == ["sponsors"]
        )
        state, events = self.engine.submit_choice(
            state, 0, sponsors["choice_id"], sponsors["option_ids"],
        )
        self.assertEqual(1, action_card(state, "sponsors")["position"])
        self.assertEqual(2, action_card(state, "build")["position"])
        self.assertEqual(1, state["active_seat"])
        self.assertEqual("turn_finished", events[-1]["type"])


if __name__ == "__main__":
    unittest.main()
