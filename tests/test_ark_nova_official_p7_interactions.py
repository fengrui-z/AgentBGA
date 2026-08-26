import unittest
from pathlib import Path

from agentbga.ark_nova_official.actions import (
    complete_action_execution,
    defer_after_finishing,
    legal_action_starts,
    start_action,
)
from agentbga.ark_nova_official.semantics import SemanticEngine, SemanticRuleError
from agentbga.ark_nova_official.state import new_semantic_state
from agentbga.ark_nova_official.content import load_content_pack
from agentbga.ark_nova_official.interaction_audit import audit_interactions


def effect(op, args, timing="immediate"):
    return {"op": op, "args": args, "timing": timing}


def card_for(state, seat, action):
    return next(
        card for card in state["players"][seat]["action_cards"]
        if card["action"] == action
    )


class ArkNovaOfficialP7InteractionTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticEngine()

    def test_all_compiled_modifiers_have_trigger_producers_or_static_consumers(self):
        root = Path(__file__).resolve().parents[1]
        report = audit_interactions(load_content_pack(
            root / "content-packs" / "ark-nova" / "base-en-draft",
        ))
        self.assertEqual(51, report.modifier_count)
        self.assertEqual(40, report.dynamic_modifier_count)
        self.assertEqual(11, report.static_modifier_count)
        self.assertEqual((), report.unresolved)
        self.assertIn("income", report.triggers)
        self.assertIn("release_project_supported", report.triggers)
        self.assertIn("animal_cost_discount", report.static_kinds)
        self.assertIn("diversity_researcher", report.static_kinds)

    def _two_order_sensitive_modifiers(self):
        state = new_semantic_state(2)
        effects = [
            effect("add_modifier", {
                "id": "first-reputation", "trigger": "audit-trigger",
                "effects": [effect(
                    "move_track", {"track": "reputation", "amount": 1}, "on_trigger",
                )],
            }, "ongoing"),
            effect("add_modifier", {
                "id": "then-money", "trigger": "audit-trigger",
                "effects": [effect("gain_tiered_reward", {
                    "count": {"ref": "actor.tracks.reputation"},
                    "reward": "money", "thresholds": [1], "rewards": [5],
                }, "on_trigger")],
            }, "ongoing"),
        ]
        state, _ = self.engine.start_effects(state, 0, effects, source_id="p7-order")
        return state

    def test_simultaneous_cross_card_triggers_offer_real_order_choice(self):
        first = self._two_order_sensitive_modifiers()
        first, _ = self.engine.trigger_modifiers(
            first, "audit-trigger", actor_seat=0, owner_seats=[0],
        )
        choice = first["resolution"]["pending_choice"]
        self.assertEqual("choose_effect_order", choice["continuation"]["type"])
        self.assertEqual(["effect-0", "effect-1"], [item["id"] for item in choice["options"]])
        first, events = self.engine.submit_choice(
            first, 0, choice["choice_id"], ["effect-0"],
        )
        self.assertEqual(30, first["players"][0]["money"])
        self.assertEqual(1, first["players"][0]["tracks"]["reputation"])
        self.assertTrue(any(
            event["type"] == "simultaneous_effect_order_selected" for event in events
        ))

        second = self._two_order_sensitive_modifiers()
        second, _ = self.engine.trigger_modifiers(
            second, "audit-trigger", actor_seat=0, owner_seats=[0],
        )
        choice = second["resolution"]["pending_choice"]
        second, _ = self.engine.submit_choice(
            second, 0, choice["choice_id"], ["effect-1"],
        )
        self.assertEqual(25, second["players"][0]["money"])
        self.assertEqual(1, second["players"][0]["tracks"]["reputation"])

    def test_trigger_order_preserves_each_modifier_owner(self):
        state = new_semantic_state(2)
        for owner, amount in ((0, 2), (1, 3)):
            state, _ = self.engine.start_effects(state, owner, [
                effect("add_modifier", {
                    "id": f"owner-{owner}", "trigger": "any-owner",
                    "effects": [effect("gain_money", {"amount": amount}, "on_trigger")],
                }, "ongoing"),
            ], source_id=f"owner-source-{owner}")
        state, _ = self.engine.trigger_modifiers(
            state, "any-owner", actor_seat=0, owner_seats=[0, 1],
        )
        while state["resolution"]["pending_choice"] is not None:
            choice = state["resolution"]["pending_choice"]
            state, _ = self.engine.submit_choice(
                state, choice["seat"], choice["choice_id"], ["effect-0"],
            )
        self.assertEqual([27, 28], [player["money"] for player in state["players"]])

    def test_unaffordable_nonvenom_actions_are_not_offered(self):
        state = new_semantic_state(2)
        state["phase"] = "active"
        state["players"][0]["money"] = 1
        card_for(state, 0, "animals")["tokens"] = ["venom"]
        starts = legal_action_starts(state, 0)
        offered = {
            item["action"].get("action_card_id") for item in starts
            if item["action"]["type"] in {"start_action", "take_x_token_action"}
        }
        self.assertEqual({"animals"}, offered)
        with self.assertRaisesRegex(SemanticRuleError, "Venom payment"):
            start_action(state, 0, "cards")

    def test_venom_payment_is_reserved_until_after_extra_action_and_refunded(self):
        state = new_semantic_state(2)
        state["phase"] = "active"
        state["players"][0]["money"] = 5
        card_for(state, 0, "sponsors")["tokens"] = ["venom"]

        state, _ = start_action(state, 0, "build")
        self.assertEqual(3, state["players"][0]["money"])
        self.assertEqual(2, state["turn"]["venom_reserved_money"])
        state = defer_after_finishing(state, 0, [
            effect("grant_extra_action", {"action": "sponsors"}, "after_finishing"),
        ])
        state, _ = complete_action_execution(
            self.engine, state, 0, {"performed": True, "buildings": ["pavilion"]},
        )
        self.assertEqual(0, state["active_seat"])
        self.assertEqual(2, state["turn"]["venom_reserved_money"])

        state, _ = start_action(state, 0, "sponsors")
        state, events = complete_action_execution(
            self.engine, state, 0, {"performed": True, "mode": "advance_break"},
        )
        self.assertEqual(5, state["players"][0]["money"])
        self.assertEqual(0, state["turn"]["venom_reserved_money"])
        self.assertFalse(state["turn"]["venom_removed_this_turn"])
        self.assertEqual(2, events[-1]["venom"]["refunded"])

    def test_duplicate_string_interaction_token_is_returned_without_crashing(self):
        state = new_semantic_state(2)
        state["players"][1]["tracks"]["appeal"] = 10
        card_for(state, 1, "animals")["tokens"] = ["venom"]
        state, events = self.engine.start_effects(state, 0, [
            effect("apply_interaction_tokens", {
                "token": "venom", "amount": 1, "track_mode": "appeal",
            }, "interaction"),
        ], source_id="duplicate-venom")
        placement = next(event for event in events if event["type"] == "interaction_tokens_placed")
        self.assertEqual(0, placement["placed"])
        self.assertEqual(["venom"], card_for(state, 1, "animals")["tokens"])


if __name__ == "__main__":
    unittest.main()
