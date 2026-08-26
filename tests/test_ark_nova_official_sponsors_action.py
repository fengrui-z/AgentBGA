from pathlib import Path
import unittest

from agentbga.ark_nova_official import (
    SemanticEngine,
    SemanticRuleError,
    apply_sponsors_execution_action,
    legal_sponsors_execution_actions,
    load_content_pack,
    new_semantic_state,
    start_action,
)


def action_card(state: dict, action: str) -> dict:
    return next(card for card in state["players"][0]["action_cards"] if card["action"] == action)


class ArkNovaOfficialSponsorsActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        pack = load_content_pack(root / "content-packs" / "ark-nova" / "base-en-draft")
        cls.entries = {entry.id: entry for entry in pack.collections["sponsors"]}
        cls.simple = cls.entries["ark-nova:sponsor-223"]
        cls.sponsors_two = cls.entries["ark-nova:sponsor-201"]
        cls.placement = cls.entries["ark-nova:sponsor-243"]
        cls.unique_ready = cls.entries["ark-nova:sponsor-248"]

    def setUp(self):
        self.engine = SemanticEngine()
        self.state = new_semantic_state(2, seed=41)
        self.state["phase"] = "active"

    def choices(self, state: dict) -> list[dict]:
        return legal_sponsors_execution_actions(self.engine, state, 0, self.entries)

    def apply(self, state: dict, action: dict) -> tuple[dict, list[dict]]:
        return apply_sponsors_execution_action(
            self.engine, state, 0, self.entries, action,
        )

    def test_break_branch_advances_by_strength_and_pays_side_one_rate(self):
        state, _ = start_action(self.state, 0, "sponsors")
        state, events = self.apply(state, {"type": "advance_sponsors_break"})
        self.assertEqual(5, state["break"]["position"])
        self.assertEqual(30, state["players"][0]["money"])
        self.assertEqual(1, action_card(state, "sponsors")["position"])
        self.assertEqual(1, state["active_seat"])
        self.assertEqual("turn_finished", events[-1]["type"])

    def test_sponsors_one_plays_exactly_one_card_then_finishes(self):
        state = self.state
        state["players"][0]["hand"] = [
            {"id": "science-a", "entry_id": self.simple.id},
            {"id": "science-b", "entry_id": self.simple.id},
        ]
        state, _ = start_action(state, 0, "sponsors")
        state, events = self.apply(state, {
            "type": "play_sponsor_card", "instance_id": "science-a", "source": "hand",
        })
        self.assertEqual("science-a", state["players"][0]["played_cards"][0]["id"])
        self.assertEqual(self.simple.id, state["players"][0]["played_cards"][0]["entry_id"])
        self.assertEqual(["sponsors:finish"], [choice["id"] for choice in self.choices(state)])
        self.assertTrue(any(event["type"] == "sponsor_played" for event in events))

    def test_sponsors_two_plays_multiple_cards_with_shared_level_budget(self):
        state = self.state
        action_card(state, "sponsors")["upgraded"] = True
        state["players"][0]["hand"] = [
            {"id": "science-a", "entry_id": self.simple.id},
            {"id": "science-b", "entry_id": self.simple.id},
        ]
        state, _ = start_action(state, 0, "sponsors")
        for instance_id in ("science-a", "science-b"):
            state, _ = self.apply(state, {
                "type": "play_sponsor_card", "instance_id": instance_id, "source": "hand",
            })
        self.assertEqual(2, len(state["players"][0]["played_cards"]))
        self.assertEqual(["sponsors:finish"], [choice["id"] for choice in self.choices(state)])

    def test_display_range_keeps_physical_slots_and_refills_after_finish(self):
        state = self.state
        action_card(state, "sponsors")["upgraded"] = True
        state["players"][0]["tracks"]["reputation"] = 4
        state["card_display"] = [
            {"id": f"display-{index}", "entry_id": self.simple.id}
            for index in range(1, 7)
        ]
        state["zoo_deck"] = [{"id": "replacement", "entry_id": self.simple.id}]
        state, _ = start_action(state, 0, "sponsors")
        state, _ = self.apply(state, {
            "type": "play_sponsor_card", "instance_id": "display-3", "source": "display",
        })
        self.assertEqual(22, state["players"][0]["money"])
        played_record = state["turn"]["action_session"]["sponsors_resolution"]["played"][0]
        self.assertEqual(3, played_record["folder_cost"])
        self.assertEqual(5, len(state["card_display"]))
        remaining_display = {
            choice["action"].get("instance_id") for choice in self.choices(state)
            if choice["action"].get("source") == "display"
        }
        self.assertEqual({"display-1", "display-2"}, remaining_display)
        state, events = self.apply(state, {"type": "finish_sponsors_action"})
        self.assertEqual(6, len(state["card_display"]))
        self.assertTrue(any(event["type"] == "card_display_refilled" for event in events))

    def test_sponsors_two_requirement_uses_upgraded_action_card(self):
        state = self.state
        state["players"][0]["hand"] = [{
            "id": "lab-a", "entry_id": self.sponsors_two.id,
        }]
        state, _ = start_action(state, 0, "sponsors")
        self.assertNotIn("sponsors:play:lab-a", [choice["id"] for choice in self.choices(state)])

        upgraded = new_semantic_state(2)
        upgraded["phase"] = "active"
        action_card(upgraded, "sponsors")["upgraded"] = True
        upgraded["players"][0]["hand"] = [{
            "id": "lab-a", "entry_id": self.sponsors_two.id,
        }]
        upgraded, _ = start_action(upgraded, 0, "sponsors")
        self.assertIn("sponsors:play:lab-a", [choice["id"] for choice in self.choices(upgraded)])

    def test_unique_building_still_requires_its_printed_reputation(self):
        state = self.state
        state["players"][0]["hand"] = [{
            "id": "den-a", "entry_id": self.placement.id,
        }]
        state, _ = start_action(state, 0, "sponsors")
        self.assertEqual(["sponsors:advance-break"], [choice["id"] for choice in self.choices(state)])
        with self.assertRaisesRegex(SemanticRuleError, "not currently legal"):
            self.apply(state, {
                "type": "play_sponsor_card", "instance_id": "den-a", "source": "hand",
            })

        eligible = self.state
        eligible["players"][0]["tracks"]["reputation"] = 3
        eligible["players"][0]["hand"] = [{
            "id": "den-a", "entry_id": self.placement.id,
        }]
        eligible, _ = start_action(eligible, 0, "sponsors")
        self.assertIn("sponsors:play:den-a", [choice["id"] for choice in self.choices(eligible)])

    def test_compiled_unique_building_is_selected_then_placed_before_card_effects(self):
        state = self.state
        state["players"][0]["hand"] = [{
            "id": "monkey-park-a", "entry_id": self.unique_ready.id,
        }]
        state, _ = start_action(state, 0, "sponsors")
        self.assertIn(
            "sponsors:play:monkey-park-a",
            [choice["id"] for choice in self.choices(state)],
        )
        state, events = self.apply(state, {
            "type": "play_sponsor_card", "instance_id": "monkey-park-a", "source": "hand",
        })
        self.assertEqual("unique_sponsor_building_selected", events[0]["type"])
        self.assertEqual(1, len(state["players"][0]["hand"]))
        placements = self.choices(state)
        self.assertTrue(placements)
        self.assertTrue(all(
            choice["action"]["type"] == "place_unique_sponsor_building"
            for choice in placements
        ))

        state, events = self.apply(state, placements[0]["action"])
        self.assertEqual([], state["players"][0]["hand"])
        self.assertEqual("unique_sponsor_248", state["players"][0]["map"]["buildings"][0]["type"])
        self.assertEqual("monkey-park-a", state["players"][0]["played_cards"][0]["id"])
        # The newly installed modifier sees this card's own primate icon.
        self.assertEqual(1, state["players"][0]["x_tokens"])
        self.assertTrue(any(
            event["type"] == "unique_sponsor_building_placed" for event in events
        ))
        self.assertEqual(["sponsors:finish"], [choice["id"] for choice in self.choices(state)])


if __name__ == "__main__":
    unittest.main()
