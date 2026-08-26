import json
from pathlib import Path
import unittest

from agentbga.ark_nova_official.final_scoring_effects import (
    compile_final_scoring_facts,
    compiled_final_scoring_tier_count,
    score_final_card,
)
from agentbga.ark_nova_official.scoring import score_game
from agentbga.ark_nova_official.semantics import SemanticEngine
from agentbga.ark_nova_official.state import new_semantic_state


class ArkNovaOfficialP6FinalScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        source = root / "reference-input" / "ark-nova-base" / "ark_nova_base_cards.json"
        cls.rows = json.loads(source.read_text(encoding="utf-8"))["final_scoring_cards"]
        cls.by_id = {row["id"]: row for row in cls.rows}

    def card(self, component_id):
        row = self.by_id[component_id]
        return {
            "id": f"ark-nova:final-{component_id}",
            "kind": "final_scoring",
            "facts": {**row, **compile_final_scoring_facts(row)},
            "effects": [],
        }

    def test_all_11_faces_and_40_records_compile_without_backlog(self):
        self.assertEqual(11, len(self.rows))
        self.assertEqual(40, sum(compiled_final_scoring_tier_count(row) for row in self.rows))
        for row in self.rows:
            facts = compile_final_scoring_facts(row)
            self.assertEqual("compiled", facts["semantic_compile_status"])
            self.assertEqual([], facts["unresolved_tiers"])

    def test_all_nine_threshold_cards_reach_each_printed_tier(self):
        setters = {
            "001": lambda p, n: p["played_cards"].extend(
                {"kind": "animal", "facts": {"enclosure_size": 4}} for _ in range(n)
            ),
            "002": lambda p, n: p["played_cards"].extend(
                {"kind": "animal", "facts": {"enclosure_size": 2}} for _ in range(n)
            ),
            "003": lambda p, n: p["icons"].update({"science": n}),
            "005": lambda p, n: p["supported_projects"].extend(
                f"project-{index}" for index in range(n)
            ),
            "006": lambda p, n: self._leave_empty_building_spaces(p, n),
            "007": lambda p, n: p["tracks"].update({"reputation": n}),
            "008": lambda p, n: p["played_cards"].extend(
                {"kind": "sponsor", "facts": {}} for _ in range(n)
            ),
            "010": lambda p, n: p["icons"].update({"rock": n}),
            "011": lambda p, n: p["icons"].update({"water": n}),
        }
        for component_id, setter in setters.items():
            row = self.by_id[component_id]
            for tier in row["tiers"]:
                with self.subTest(card=component_id, tier=tier):
                    state = new_semantic_state(2)
                    setter(state["players"][0], tier["requirement"])
                    result = score_final_card(state, 0, self.card(component_id))
                    self.assertEqual(tier["conservation"], result["conservation"])

    def test_recorded_terrain_requirements_are_terrain_icons(self):
        state = new_semantic_state(2)
        player = state["players"][0]
        player["icons"].update({"rock": 2, "water": 2})
        self.assertEqual(2, score_final_card(state, 0, self.card("010"))["metric_value"])
        self.assertEqual(2, score_final_card(state, 0, self.card("011"))["metric_value"])

    def test_architectural_zoo_scores_each_map_condition(self):
        state = new_semantic_state(2)
        player = state["players"][0]
        # Covering every building space also connects every terrain space on Map 0.
        buildable = [
            cell for cell in player["map"]["cells"] if cell["terrain"] == "buildable"
        ]
        player["map"]["buildings"] = [
            {
                "id": f"single-{index}", "type": "standard_enclosure", "size": 1,
                "shape_id": "standard_enclosure-1", "rotation": 0,
                "occupied": False, "cells": [{"q": cell["q"], "r": cell["r"]}],
            }
            for index, cell in enumerate(buildable)
        ]
        result = score_final_card(state, 0, self.card("004"))
        self.assertEqual(4, result["conservation"])
        self.assertTrue(all(result["conditions"].values()))

    def test_diverse_species_compares_right_neighbor_and_caps_at_four(self):
        state = new_semantic_state(3)
        state["players"][0]["icons"].update({
            "bear": 1, "bird": 2, "herbivore": 1,
            "pet": 1, "predator": 2, "primate": 1,
        })
        state["players"][1]["icons"].update({"bird": 2, "predator": 1})
        result = score_final_card(state, 0, self.card("009"))
        self.assertEqual(4, result["conservation"])
        self.assertEqual(1, result["right_neighbor_seat"])
        self.assertIn("bear", result["winning_categories"])
        self.assertNotIn("bird", result["winning_categories"])

    def test_solo_diverse_species_is_non_scoring_failsafe(self):
        state = new_semantic_state(1)
        result = score_final_card(state, 0, self.card("009"))
        self.assertEqual(0, result["conservation"])
        self.assertEqual("discard_and_redraw", result["solo_policy"])

    def test_solo_draw_discards_diverse_species_and_draws_replacement(self):
        state = new_semantic_state(1)
        replacement = self.card("001")
        diverse = self.card("009")
        state["final_scoring_deck"] = [replacement, diverse]
        effects = [{
            "op": "draw_keep_final_scoring", "timing": "immediate",
            "args": {"draw": 1, "keep": 1},
        }]
        engine = SemanticEngine()
        state, _ = engine.start_effects(state, 0, effects, source_id="solo-final-draw")
        choice = state["resolution"]["pending_choice"]
        self.assertEqual([replacement["id"]], [item["id"] for item in choice["options"]])
        self.assertEqual([diverse["id"]], [card["id"] for card in state["final_scoring_discard"]])
        state, events = engine.submit_choice(
            state, 0, choice["choice_id"], [replacement["id"]],
        )
        self.assertEqual(1, events[-1]["solo_discarded"])

    def test_score_game_applies_final_conservation_before_vp_distance(self):
        state = new_semantic_state(2)
        state["endgame"]["final_scoring_discard_completed"] = True
        player = state["players"][0]
        next(card for card in player["action_cards"] if card["action"] == "cards")["upgraded"] = True
        player["tracks"].update({"appeal": 20, "conservation": 0, "reputation": 15})
        player["final_scoring_cards"] = [self.card("007")]
        scored, events = score_game(SemanticEngine(), state, [10] * 42)
        row = next(item for item in scored["endgame"]["results"] if item["seat"] == 0)
        self.assertEqual(4, row["conservation"])
        self.assertEqual(10, row["victory_points"])
        self.assertEqual("final_scoring_card_scored", events[0]["type"])
        self.assertEqual(4, events[0]["awarded_conservation"])

    @staticmethod
    def _leave_empty_building_spaces(player, empty_count):
        buildable = [
            cell for cell in player["map"]["cells"] if cell["terrain"] == "buildable"
        ]
        covered = buildable[:max(0, len(buildable) - empty_count)]
        player["map"]["buildings"] = [
            {
                "id": f"single-{index}", "type": "standard_enclosure", "size": 1,
                "shape_id": "standard_enclosure-1", "rotation": 0,
                "occupied": False, "cells": [{"q": cell["q"], "r": cell["r"]}],
            }
            for index, cell in enumerate(covered)
        ]


if __name__ == "__main__":
    unittest.main()
