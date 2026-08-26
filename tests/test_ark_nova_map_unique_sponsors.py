import unittest

from agentbga.ark_nova_map import (
    unique_sponsor_building_spec,
    unique_sponsor_shape_variants,
)
from agentbga.ark_nova_official.build_action import legal_unique_building_placements
from agentbga.ark_nova_official.sponsor_reference import unique_building_rules
from agentbga.ark_nova_official.state import new_semantic_state


class ArkNovaMapUniqueSponsorTests(unittest.TestCase):
    def test_all_fifteen_specs_are_self_contained_and_rotatable(self):
        for card_id in range(243, 258):
            spec = unique_sponsor_building_spec(card_id)
            self.assertIsNotNone(spec, card_id)
            self.assertEqual(card_id, spec["card_id"])
            self.assertEqual(spec["size"], len(spec["canonical_cells"]))
            self.assertTrue(unique_sponsor_shape_variants(card_id), card_id)

        self.assertIsNone(unique_sponsor_building_spec(242))
        self.assertEqual([], unique_sponsor_shape_variants(258))

    def test_specs_are_defensive_copies_and_polar_bear_requires_water(self):
        first = unique_sponsor_building_spec(251)
        first["placement"].clear()
        second = unique_sponsor_building_spec(251)
        self.assertEqual(1, second["placement"]["min_adjacent_water_spaces"])
        self.assertEqual("water", unique_building_rules("251")["adjacent_terrain"])
        self.assertEqual(1, unique_building_rules("251")["adjacent_count"])

    def test_side_entrance_is_the_only_connectivity_override(self):
        for card_id in range(243, 257):
            placement = unique_sponsor_building_spec(card_id)["placement"]
            self.assertIsNot(False, placement.get("requires_adjacency_to_existing_building"))
        self.assertFalse(
            unique_sponsor_building_spec(257)["placement"]
            ["requires_adjacency_to_existing_building"]
        )

    def test_unique_buildings_respect_build_two_restricted_cells(self):
        state = new_semantic_state(2)
        player = state["players"][0]
        rules = unique_building_rules("248")
        restricted = {
            (cell["q"], cell["r"]) for cell in player["map"]["cells"]
            if cell.get("requires_build_upgrade")
        }
        level_one = legal_unique_building_placements(player, rules)
        self.assertFalse(any(
            {(cell["q"], cell["r"]) for cell in action["cells"]} & restricted
            for action in level_one
        ))

        next(card for card in player["action_cards"] if card["action"] == "build")["upgraded"] = True
        level_two = legal_unique_building_placements(player, rules)
        self.assertTrue(any(
            {(cell["q"], cell["r"]) for cell in action["cells"]} & restricted
            for action in level_two
        ))


if __name__ == "__main__":
    unittest.main()
