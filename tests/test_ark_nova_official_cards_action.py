import unittest
from copy import deepcopy

from agentbga.ark_nova_official import (
    SemanticEngine,
    SemanticRuleError,
    apply_cards_execution_action,
    legal_cards_execution_actions,
    new_semantic_state,
    reputation_display_limit,
    start_action,
)


def card(card_id: str, kind: str = "animal") -> dict:
    return {"id": card_id, "kind": kind}


def action_card(state: dict, seat: int, action: str) -> dict:
    return next(item for item in state["players"][seat]["action_cards"] if item["action"] == action)


class ArkNovaOfficialCardsActionTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticEngine()
        self.state = new_semantic_state(2, seed=17)
        self.state["phase"] = "active"

    def apply(self, state: dict, action: dict) -> tuple[dict, list[dict]]:
        return apply_cards_execution_action(self.engine, state, 0, action)

    def test_reputation_ranges_match_the_six_display_positions(self):
        expected = {
            0: 1, 1: 1, 2: 2, 3: 2, 4: 3, 6: 3, 7: 4, 9: 4,
            10: 5, 12: 5, 13: 6, 15: 6, 99: 6,
        }
        self.assertEqual(expected, {value: reputation_display_limit(value) for value in expected})

    def test_cards_one_draws_one_at_a_time_then_requires_discard(self):
        state = self.state
        state["players"][0]["x_tokens"] = 1
        state["players"][0]["hand"] = [card("held")]
        state["zoo_deck"] = [card("deck-a"), card("deck-b"), card("deck-c")]
        state, _ = start_action(state, 0, "cards", x_by_execution=(1,))

        choices = legal_cards_execution_actions(state, 0)
        self.assertEqual(["cards:draw"], [choice["id"] for choice in choices])
        state, _ = self.apply(state, {"type": "begin_cards_draw"})
        self.assertEqual(2, state["break"]["position"])

        state, _ = self.apply(state, {"type": "draw_cards_action_card", "source": "deck"})
        self.assertEqual(["cards:draw:deck"], [
            choice["id"] for choice in legal_cards_execution_actions(state, 0)
        ])
        state, _ = self.apply(state, {"type": "draw_cards_action_card", "source": "deck"})
        self.assertEqual(3, len(legal_cards_execution_actions(state, 0)))
        self.assertEqual("action", state["phase"])

        state, events = self.apply(
            state, {"type": "discard_cards_action_card", "card_id": "held"},
        )
        self.assertEqual(["held"], [item["id"] for item in state["zoo_discard"]])
        self.assertEqual(1, action_card(state, 0, "cards")["position"])
        self.assertEqual(1, state["active_seat"])
        self.assertEqual("turn_finished", events[-1]["type"])

    def test_cards_two_can_take_only_within_reputation_and_refills_after_finishing(self):
        state = self.state
        state["players"][0]["x_tokens"] = 1
        state["players"][0]["tracks"]["reputation"] = 4
        action_card(state, 0, "cards")["upgraded"] = True
        state["card_display"] = [card(f"display-{index}") for index in range(1, 7)]
        state["zoo_deck"] = [card("refill"), card("deck-draw")]
        state, _ = start_action(state, 0, "cards", x_by_execution=(1,))
        state, _ = self.apply(state, {"type": "begin_cards_draw"})

        choices = legal_cards_execution_actions(state, 0)
        self.assertEqual(
            ["cards:draw:deck", "cards:draw:display:display-1",
             "cards:draw:display:display-2", "cards:draw:display:display-3"],
            [choice["id"] for choice in choices],
        )
        state, _ = self.apply(state, {
            "type": "draw_cards_action_card", "source": "display", "card_id": "display-3",
        })
        self.assertEqual(5, len(state["card_display"]))
        self.assertEqual("action", state["phase"])
        self.assertNotIn("display-4", {
            choice["action"].get("card_id")
            for choice in legal_cards_execution_actions(state, 0)
            if choice["action"].get("source") == "display"
        })

        state, events = self.apply(state, {"type": "draw_cards_action_card", "source": "deck"})
        self.assertEqual(6, len(state["card_display"]))
        self.assertIn("display-3", [item["id"] for item in state["players"][0]["hand"]])
        self.assertTrue(any(event["type"] == "card_display_refilled" for event in events))

    def test_snap_ignores_reputation_but_still_defers_refill(self):
        state = self.state
        state["players"][0]["x_tokens"] = 1
        action_card(state, 0, "cards")["upgraded"] = True
        state["card_display"] = [card(f"display-{index}") for index in range(1, 7)]
        state["zoo_deck"] = [card("replacement")]
        state, _ = start_action(state, 0, "cards", x_by_execution=(1,))
        choices = legal_cards_execution_actions(state, 0)
        self.assertIn("cards:snap:display-6", [choice["id"] for choice in choices])

        state, events = self.apply(
            state, {"type": "snap_cards_action_card", "card_id": "display-6"},
        )
        self.assertIn("display-6", [item["id"] for item in state["players"][0]["hand"]])
        self.assertEqual(6, len(state["card_display"]))
        self.assertEqual(2, state["break"]["position"])
        self.assertTrue(any(event["type"] == "cards_action_card_snapped" for event in events))

    def test_stale_or_out_of_range_display_choice_is_rejected_without_mutation(self):
        state = self.state
        action_card(state, 0, "cards")["upgraded"] = True
        state["card_display"] = [card(f"display-{index}") for index in range(1, 7)]
        state["zoo_deck"] = [card("deck-a"), card("deck-b")]
        state, _ = start_action(state, 0, "cards")
        state, _ = self.apply(state, {"type": "begin_cards_draw"})
        before = deepcopy(state)
        with self.assertRaisesRegex(SemanticRuleError, "not currently legal"):
            self.apply(state, {
                "type": "draw_cards_action_card", "source": "display", "card_id": "display-2",
            })
        self.assertEqual(before, state)

    def test_multiplier_executions_preserve_physical_display_gaps_until_action_finishes(self):
        state = self.state
        state["players"][0]["x_tokens"] = 2
        state["players"][0]["tracks"]["reputation"] = 4
        cards = action_card(state, 0, "cards")
        cards["upgraded"] = True
        cards["tokens"] = ["multiplier"]
        state["card_display"] = [card(f"display-{index}") for index in range(1, 7)]
        state["zoo_deck"] = [card("refill-a"), card("refill-b"), card("deck-a"), card("deck-b")]
        state, _ = start_action(
            state, 0, "cards", x_by_execution=(1, 1), multiplier_tokens=1,
        )
        state, _ = self.apply(state, {"type": "begin_cards_draw"})
        state, _ = self.apply(state, {
            "type": "draw_cards_action_card", "source": "display", "card_id": "display-3",
        })
        state, _ = self.apply(state, {"type": "draw_cards_action_card", "source": "deck"})
        self.assertEqual(2, state["turn"]["action_session"]["current_execution"] + 1)

        state, _ = self.apply(state, {"type": "begin_cards_draw"})
        display_choices = {
            choice["action"].get("card_id")
            for choice in legal_cards_execution_actions(state, 0)
            if choice["action"].get("source") == "display"
        }
        self.assertEqual({"display-1", "display-2"}, display_choices)


if __name__ == "__main__":
    unittest.main()
