from copy import deepcopy
import unittest

from agentbga.ark_nova_official import (
    ArkNovaOfficialPlugin,
    ContentEntry,
    SemanticEngine,
    audit_content_pack,
    audit_interactions,
)
from agentbga.ark_nova_official.cards import play_entry_semantics
from agentbga.ark_nova_official.cards import _entry_effects_for_player_count
from agentbga.ark_nova_official.state import new_semantic_state
from agentbga.ark_nova_official.semantics import _official_kiosk_income


class ArkNovaOfficialP8ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = ArkNovaOfficialPlugin()

    def _finish_setup(self, state):
        for seat in range(state["player_count"]):
            action = self.plugin.legal_actions(state, seat)[0]["action"]
            state, _ = self.plugin.apply_action(state, seat, action)
        for _ in range(2):
            for seat in range(state["player_count"]):
                action = self.plugin.legal_actions(state, seat)[0]["action"]
                state, _ = self.plugin.apply_action(state, seat, action)
        return state

    def test_core_faces_bonus_tiles_and_all_255_four_player_physical_cards_are_executable(self):
        report = audit_content_pack(self.plugin.pack, SemanticEngine())
        interactions = audit_interactions(self.plugin.pack)
        self.assertEqual(244, report.roster_entry_count)
        self.assertEqual(243, report.semantic_entry_count)
        self.assertEqual((), interactions.unresolved)
        self.assertEqual(
            {"transcribed"},
            {
                entry.review_status
                for collection in (
                    "animals", "sponsors", "zoo_conservation_projects",
                    "base_conservation_projects", "final_scoring",
                )
                for entry in self.plugin.pack.collections[collection]
            },
        )
        state = self.plugin.setup(4, 9001)
        physical_card_faces = 128 + 64 + 32 + 11
        action_cards = sum(len(player["action_cards"]) for player in state["players"])
        self.assertEqual(255, physical_card_faces + action_cards)

    def test_setup_is_deterministic_private_and_includes_map_zero_starters(self):
        first = self.plugin.setup(2, 81)
        second = self.plugin.setup(2, 81)
        self.assertEqual(first, second)
        self.assertEqual(1, first["players"][0]["tracks"]["reputation"])
        self.assertEqual(70, len(self.plugin.legal_actions(first, 0)))
        private_id = first["players"][1]["initial_draw"][0]["id"]
        self.assertNotIn(private_id, str(self.plugin.observe(first, 0)))
        self.assertIn(private_id, str(self.plugin.observe_spectator(first)))

        state = self._finish_setup(first)
        self.assertEqual("active", state["phase"])
        for player in state["players"]:
            self.assertEqual(4, len(player["hand"]))
            self.assertEqual(
                [("standard_enclosure", 3), ("kiosk", 1)],
                [(item["type"], item["size"]) for item in player["map"]["buildings"]],
            )
            self.assertEqual(0, player["income"]["kiosks"])

    def test_web_projection_exposes_human_readable_card_facts_without_leaking_hidden_cards(self):
        state = self.plugin.setup(2, 81)
        view = self.plugin.observe(state, 0)
        private_cards = view["players"][0]["initial_draw"]
        animal = next(card for card in private_cards if card["card_type"] == "animal")
        sponsor = next(card for card in private_cards if card["card_type"] == "sponsor")
        final_card = view["players"][0]["final_scoring_cards"][0]
        project = view["base_conservation_projects"][0]

        self.assertTrue(animal["display_title"])
        self.assertIn("cost", animal)
        self.assertIn("enclosure_size", animal)
        self.assertIn("abilities", animal)
        self.assertIsInstance(animal["icons"], dict)
        self.assertTrue(sponsor["display_title"])
        self.assertIn("level", sponsor)
        self.assertTrue(sponsor["mechanism_notes"])
        self.assertTrue(sponsor["resolved_mechanics"])
        self.assertTrue(all(
            mechanic["source"] in {"compiled_semantics", "card_facts"}
            for mechanic in sponsor["resolved_mechanics"]
        ))
        self.assertTrue(project["display_title"])
        self.assertTrue(project["criterion_cn"])
        self.assertTrue(all(tier.get("requirement") is not None for tier in project["tiers"]))
        self.assertTrue(final_card["display_title"])
        self.assertTrue(final_card["criterion_cn"])
        self.assertTrue(final_card["tiers"])

        opponent = view["players"][1]
        self.assertEqual([{"hidden": True}] * 8, opponent["initial_draw"])
        self.assertNotIn(state["players"][1]["initial_draw"][0]["display_title"], str(opponent))

    def test_solo_setup_never_deals_the_relative_final_scoring_card(self):
        for seed in range(30):
            state = self.plugin.setup(1, seed)
            self.assertNotIn(
                "ark-nova:final-009",
                {card["entry_id"] for card in state["players"][0]["final_scoring_cards"]},
            )

    def test_invalid_action_is_rejected_without_mutating_the_snapshot(self):
        state = self.plugin.setup(2, 19)
        before = deepcopy(state)
        with self.assertRaisesRegex(ValueError, "initial hand"):
            self.plugin.apply_action(state, 0, {"type": "take_x_token_action"})
        self.assertEqual(before, state)

    def test_end_to_end_setup_final_turns_private_discard_and_scoring(self):
        state = self._finish_setup(self.plugin.setup(2, 27))
        state["players"][0]["tracks"].update({"appeal": 112, "conservation": 1})

        action = next(
            item["action"] for item in self.plugin.legal_actions(state, 0)
            if item["action"]["type"] == "take_x_token_action"
        )
        state, events = self.plugin.apply_action(state, 0, action)
        self.assertTrue(any(event["type"] == "endgame_triggered" for event in events))
        self.assertEqual([1], state["endgame"]["final_turn_seats"])

        action = next(
            item["action"] for item in self.plugin.legal_actions(state, 1)
            if item["action"]["type"] == "take_x_token_action"
        )
        state, _ = self.plugin.apply_action(state, 1, action)
        self.assertEqual("final_scoring_discard", state["phase"])
        while state["status"] != "finished":
            seat = self.plugin.decision_seats(state)[0]
            state, _ = self.plugin.apply_action(
                state, seat, self.plugin.legal_actions(state, seat)[0]["action"],
            )
        self.assertEqual(2, len(state["endgame"]["results"]))
        self.assertEqual([], self.plugin.decision_seats(state))
        self.assertEqual([], self.plugin.legal_actions(state, 0))

    def test_official_break_income_reads_appeal_and_live_kiosk_adjacency(self):
        state = self._finish_setup(self.plugin.setup(2, 44))
        state["players"][0]["tracks"]["appeal"] = 32
        state["players"][0]["money"] = 0
        state["break"].update({
            "pending": True, "initiator": 0,
            "position": state["break"]["limit"],
        })
        from agentbga.ark_nova_official.rounds import queue_break

        state, _ = queue_break(self.plugin.engine, state)
        while state["resolution"]["pending_choice"] is not None:
            choice = state["resolution"]["pending_choice"]
            state, _ = self.plugin.engine.submit_choice(
                state, choice["seat"], choice["choice_id"],
                [choice["options"][0]["id"]],
            )
        # The free size-3 enclosure is empty, so the adjacent starter kiosk
        # provides no income yet.
        self.assertEqual(21, state["players"][0]["money"])
        self.assertEqual(1, state["break"]["count"])

        player = {"map": {"buildings": [
            {"type": "kiosk", "cells": [{"q": 0, "r": 0}]},
            {"type": "standard_enclosure", "occupied": True,
             "cells": [{"q": 1, "r": 0}]},
            {"type": "standard_enclosure", "occupied": False,
             "cells": [{"q": 0, "r": 1}]},
            {"type": "pavilion", "cells": [{"q": -1, "r": 0}]},
            {"type": "petting_zoo", "occupied": False,
             "cells": [{"q": -1, "r": 1}, {"q": -1, "r": 2}, {"q": 0, "r": 2}]},
            # Both cells touch the kiosk, but one unique building scores once.
            {"type": "unique_sponsor_255",
             "cells": [{"q": 0, "r": -1}, {"q": 1, "r": -1}]},
        ]}}
        self.assertEqual(4, _official_kiosk_income(player))

    def test_solo_uses_rounds_of_7_6_5_4_3_2_then_scores(self):
        state = self._finish_setup(self.plugin.setup(1, 123))
        self.assertEqual(20, state["players"][0]["tracks"]["appeal"])
        break_turns = []
        for turn in range(1, 28):
            state["players"][0]["x_tokens"] = 0
            action = next(
                item["action"] for item in self.plugin.legal_actions(state, 0)
                if item["action"]["type"] == "take_x_token_action"
            )
            state, events = self.plugin.apply_action(state, 0, action)
            if any(event["type"] == "solo_break_started" for event in events):
                break_turns.append(turn)
            while state["phase"] == "break" and state["resolution"]["pending_choice"] is not None:
                choice = state["resolution"]["pending_choice"]
                state, _ = self.plugin.apply_action(
                    state, 0, self.plugin.legal_actions(state, 0)[0]["action"],
                )
        self.assertEqual([7, 13, 18, 22, 25], break_turns)
        self.assertEqual(27, state["turn"]["number"])
        self.assertEqual(5, state["break"]["count"])
        self.assertEqual([2, 5, 7, 10], [
            item["cost"] for item in state["donations_made"]
            if item.get("source") == "solo_tile"
        ])
        self.assertEqual("final_scoring_discard", state["phase"])
        while state["status"] != "finished":
            choice_seat = self.plugin.decision_seats(state)[0]
            state, _ = self.plugin.apply_action(
                state, choice_seat,
                self.plugin.legal_actions(state, choice_seat)[0]["action"],
            )
        self.assertIn("solo_won", state["endgame"]["results"][0])

    def test_break_trigger_gives_every_player_one_final_turn(self):
        state = self._finish_setup(self.plugin.setup(3, 321))
        state["active_seat"] = 2
        state["players"][0]["tracks"].update({"appeal": 112, "conservation": 1})
        state, events = self.plugin._trigger_or_consume_final_turn(state, 0, "break")
        self.assertTrue(events)
        self.assertEqual([2, 0, 1], state["endgame"]["final_turn_seats"])

    def test_same_card_order_can_change_pilfering_timing(self):
        entry = ContentEntry(
            id="ark-nova:test-order", kind="animal", official_component_id=None,
            source_ids=(), display_title="Order Test", display_summary="",
            facts={"tags": [], "icons": [], "enclosure_size": 1},
            requirements=(), effects=(
                {"op": "move_track", "timing": "on_play",
                 "args": {"track": "appeal", "amount": 6}},
                {"op": "pilfer", "timing": "interaction",
                 "args": {"leader_track": "appeal"}},
            ), references=(), review_status="scenario_tested", scenario_tests=(),
            reviewer=None, second_reviewer=None,
        )
        base = new_semantic_state(2)
        base["players"][0]["tracks"]["appeal"] = 7
        base["players"][1]["tracks"]["appeal"] = 8
        base["players"][1]["hand"] = [{"id": "target-card"}]
        engine = SemanticEngine()

        before, _ = play_entry_semantics(engine, base, 0, entry, instance_id="order-a")
        ordering = before["resolution"]["pending_choice"]
        self.assertEqual("choose_effect_order", ordering["continuation"]["type"])
        before, _ = engine.submit_choice(
            before, 0, ordering["choice_id"], ["effect-1"],
        )
        self.assertEqual(
            "pilfer_payment",
            before["resolution"]["pending_choice"]["continuation"]["type"],
        )

        after, _ = play_entry_semantics(engine, base, 0, entry, instance_id="order-b")
        ordering = after["resolution"]["pending_choice"]
        after, _ = engine.submit_choice(
            after, 0, ordering["choice_id"], ["effect-0"],
        )
        self.assertEqual(
            "pilfer_timing",
            after["resolution"]["pending_choice"]["continuation"]["type"],
        )

    def test_all_eleven_interactive_animals_use_blue_stripe_solo_replacements(self):
        expected = {
            449: ("apply_interaction_tokens", "gain_x_token"),
            456: ("pilfer", "draw_cards"),
            458: ("pilfer", "draw_cards"),
            463: ("pilfer", "draw_cards"),
            470: ("apply_interaction_tokens", "gain_x_token"),
            474: ("apply_interaction_tokens", "reposition_action_card"),
            475: ("grant_hypnosis_action", "grant_extra_action"),
            482: ("apply_interaction_tokens", "reposition_action_card"),
            483: ("apply_interaction_tokens", "reposition_action_card"),
            485: ("grant_hypnosis_action", "grant_extra_action"),
            492: ("apply_interaction_tokens", "gain_x_token"),
        }
        found = {}
        for component, (removed, replacement) in expected.items():
            entry = self.plugin.pack.entry(f"ark-nova:animal-{component}")
            multiplayer = _entry_effects_for_player_count(entry, 2)
            solo = _entry_effects_for_player_count(entry, 1)
            self.assertIn(removed, {effect["op"] for effect in multiplayer})
            self.assertNotIn(removed, {effect["op"] for effect in solo})
            self.assertIn(replacement, {effect["op"] for effect in solo})
            found[component] = entry.facts["solo_source"]
        self.assertEqual({"base-card-blue-stripe"}, set(found.values()))

        state = new_semantic_state(1)
        state["zoo_deck"] = [{"id": "draw-a"}, {"id": "draw-b"}]
        state, _ = play_entry_semantics(
            SemanticEngine(), state, 0,
            self.plugin.pack.entry("ark-nova:animal-458"), instance_id="solo-macaque",
            requirements_already_authorized=True,
        )
        self.assertEqual(2, len(state["players"][0]["hand"]))


if __name__ == "__main__":
    unittest.main()
