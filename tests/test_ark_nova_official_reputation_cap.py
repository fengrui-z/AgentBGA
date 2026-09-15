import unittest

from agentbga.ark_nova_official import ArkNovaOfficialPlugin, SemanticEngine
from agentbga.ark_nova_official.state import new_semantic_state


class ArkNovaOfficialReputationCapTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticEngine()

    def move_reputation(self, state: dict, amount: int) -> dict:
        state, _ = self.engine.start_effects(state, 0, [{
            "op": "move_track", "timing": "immediate",
            "args": {"track": "reputation", "amount": amount},
        }], source_id="reputation-cap-test")
        return state

    def test_cards_one_caps_reputation_at_nine(self):
        state = self.move_reputation(new_semantic_state(2), 20)
        self.assertEqual(9, state["players"][0]["tracks"]["reputation"])

    def test_cards_two_allows_reputation_through_fifteen(self):
        state = new_semantic_state(2)
        cards = next(
            card for card in state["players"][0]["action_cards"]
            if card["action"] == "cards"
        )
        cards["upgraded"] = True
        state = self.move_reputation(state, 20)
        self.assertEqual(15, state["players"][0]["tracks"]["reputation"])

    def test_observe_and_next_action_repair_legacy_over_cap_state(self):
        plugin = ArkNovaOfficialPlugin()
        state = plugin.setup(2, 81)
        state["players"][1]["tracks"]["reputation"] = 12
        view = plugin.observe_spectator(state)
        self.assertEqual(9, view["players"][1]["reputation"])

        action = plugin.legal_actions(state, 0)[0]["action"]
        state, events = plugin.apply_action(state, 0, action)
        self.assertEqual(9, state["players"][1]["tracks"]["reputation"])
        correction = next(event for event in events if event["type"] == "reputation_cap_corrected")
        self.assertEqual({"old_value": 12, "value": 9}, {
            "old_value": correction["old_value"], "value": correction["value"],
        })


if __name__ == "__main__":
    unittest.main()
