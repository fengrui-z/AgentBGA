from pathlib import Path
import unittest

from agentbga.ark_nova_official import (
    SemanticEngine,
    apply_official_action,
    legal_official_actions,
    load_content_pack,
    new_semantic_state,
)


class ArkNovaOfficialActionDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.pack = load_content_pack(root / "content-packs" / "ark-nova" / "base-en-draft")

    def setUp(self):
        self.engine = SemanticEngine()
        self.state = new_semantic_state(2, seed=43)
        self.state["phase"] = "active"

    def test_turn_starts_are_intersected_with_real_domain_choices(self):
        actions = legal_official_actions(self.engine, self.state, 0, self.pack)
        starts = {
            item["action"].get("action_card_id")
            for item in actions if item["action"]["type"] == "start_action"
        }
        self.assertNotIn("animals", starts)
        self.assertNotIn("cards", starts)
        self.assertIn("build", starts)
        self.assertIn("association", starts)
        self.assertIn("sponsors", starts)

    def test_unplayable_hand_does_not_trap_turn_and_sponsors_break_remains_available(self):
        self.state["players"][0]["hand"] = [{
            "id": "goat-a", "entry_id": "ark-nova:animal-519",
        }]
        # A Petting Zoo animal cannot use an ordinary enclosure, so Animals is
        # still excluded at the turn boundary.
        self.state["players"][0]["map"]["buildings"].append({
            "id": "standard-a", "type": "standard_enclosure", "size": 1,
            "shape_id": "standard_enclosure-1", "rotation": 0,
            "occupied": False, "cells": [{"q": 4, "r": -4}],
        })
        starts = legal_official_actions(self.engine, self.state, 0, self.pack)
        self.assertFalse(any(
            item["action"].get("action_card_id") == "animals"
            and item["action"]["type"] == "start_action"
            for item in starts
        ))
        sponsor_start = next(
            item["action"] for item in starts
            if item["action"].get("action_card_id") == "sponsors"
            and item["action"]["type"] == "start_action"
        )
        state, _ = apply_official_action(
            self.engine, self.state, 0, self.pack, sponsor_start,
        )
        self.assertIn("sponsors:advance-break", [
            item["id"] for item in legal_official_actions(self.engine, state, 0, self.pack)
        ])
        state, _ = apply_official_action(
            self.engine, state, 0, self.pack, {"type": "advance_sponsors_break"},
        )
        self.assertEqual(1, state["active_seat"])


if __name__ == "__main__":
    unittest.main()
