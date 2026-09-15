import unittest

from agentbga.ark_nova_map import (
    building_shape_variants,
    unique_sponsor_building_spec,
    unique_sponsor_shape_variants,
    valid_building_shape,
)
from agentbga.ark_nova_official.build_action import legal_unique_building_placements
from agentbga.ark_nova_official.sponsor_reference import unique_building_rules
from agentbga.ark_nova_official.state import new_semantic_state


class ArkNovaMapUniqueSponsorTests(unittest.TestCase):
    @staticmethod
    def _normalise(cells):
        minimum_q = min(q for q, _ in cells)
        minimum_r = min(r for _, r in cells)
        return frozenset((q - minimum_q, r - minimum_r) for q, r in cells)

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

    def test_rhesus_monkey_park_uses_printed_bent_chain_shape(self):
        printed = {(0, 0), (1, -1), (2, -1), (3, -1)}
        old_compact = {(0, 0), (-1, 0), (0, -1), (1, -1)}
        self.assertEqual(
            printed,
            set(unique_sponsor_building_spec(248)["canonical_cells"]),
        )
        generated = {
            frozenset(variant["cells"])
            for variant in building_shape_variants("unique_sponsor_248", 4)
        }
        self.assertIn(frozenset(printed), generated)
        self.assertNotIn(frozenset(old_compact), generated)
        self.assertTrue(valid_building_shape({
            "type": "unique_sponsor_248", "size": 4,
            "cells": [{"q": q, "r": r} for q, r in old_compact],
        }))

    def test_ten_supplied_unique_building_silhouettes_match_up_to_rotation(self):
        supplied = {
            252: {(0, 0), (-1, 0), (1, -1), (2, -2)},  # Spotted Hyena Compound
            253: {(0, 0), (1, 0), (2, -1), (3, -1)},   # Okapi Stable
            244: {(0, 0), (-1, 0), (1, -1), (1, 0)},   # Penguin Pool
            249: {(0, 0), (1, 0), (2, 0)},             # Barred Owl Hut
            250: {(0, 0), (-1, 0), (1, -1), (0, 1)},   # Sea Turtle Tank
            254: {(0, 0), (-1, 0), (1, -1)},           # Zoo School
            243: {(0, 0), (-1, 1), (1, 0)},            # Meerkat Den
            246: {(0, 0), (1, 0), (2, 0), (3, 0)},     # Aerial Cableway
            247: {(0, 0), (-1, 0), (-1, 1), (1, 0)},   # Baboon Rock
            251: {(0, 0), (1, -1), (2, -1), (3, -2)},  # Polar Bear Exhibit
        }
        for card_id, expected in supplied.items():
            with self.subTest(card_id=card_id):
                signatures = {
                    self._normalise(variant["cells"])
                    for variant in unique_sponsor_shape_variants(card_id)
                }
                self.assertIn(self._normalise(expected), signatures)

    def test_corrected_unique_building_legacy_shapes_remain_loadable_only(self):
        legacy = {
            247: {(0, 0), (-1, 0), (1, -1), (0, 1)},
            250: {(0, 0), (-1, 0), (0, -1), (0, 1)},
            251: {(0, 0), (-1, 1), (1, -1), (2, -1)},
            253: {(0, 0), (-1, 0), (0, 1), (1, 1)},
        }
        for card_id, old_cells in legacy.items():
            with self.subTest(card_id=card_id):
                self.assertTrue(valid_building_shape({
                    "type": f"unique_sponsor_{card_id}", "size": 4,
                    "cells": [{"q": q, "r": r} for q, r in old_cells],
                }))
                generated = {
                    self._normalise(variant["cells"])
                    for variant in unique_sponsor_shape_variants(card_id)
                }
                self.assertNotIn(self._normalise(old_cells), generated)

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
