import json
from pathlib import Path
import tempfile
import unittest

from agentbga.agent_context import CONTEXT_V2, prepare_seat_context
from agentbga.agent_context import compact_card
from agentbga.ark_nova_official import ArkNovaOfficialPlugin
from agentbga.seat_tool import call_tool


class AgentContextTests(unittest.TestCase):
    def setUp(self):
        self.plugin = ArkNovaOfficialPlugin()
        self.state = self.plugin.setup(2, 42)
        self.observation = self.plugin.observe(self.state, 0)
        self.observation["state_version"] = 0
        self.legal = self.plugin.legal_actions(self.state, 0)

    def test_ark_nova_observe_is_compact_and_private_details_are_indexed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "turn-context.json"
            context = prepare_seat_context(
                path, match_id="match", seat=0, version=0,
                observation=self.observation, legal=self.legal,
            )

            self.assertEqual(CONTEXT_V2, context["schema_version"])
            full_size = len(json.dumps(self.observation, ensure_ascii=False).encode())
            compact = call_tool(path, "observe")
            compact_size = len(json.dumps(compact, ensure_ascii=False).encode())
            self.assertLess(compact_size, full_size // 2)
            self.assertLessEqual(compact_size, 16 * 1024)
            self.assertEqual("initial_draw", next(iter(compact["self"])))
            self.assertEqual(8, len(compact["self"]["initial_draw"]))
            self.assertIn("All cards in self.initial_draw are visible", compact["setup_instruction"])
            self.assertEqual(self.state["content_pack_id"], compact["content_pack_id"])
            self.assertEqual(self.state["content_hash"], compact["content_hash"])
            self.assertNotIn("map_display", compact["self"])
            self.assertIn("detail_ref", compact["self"]["map"])
            core_rules = call_tool(path, "inspect_rules", {"topic": "core"})
            self.assertTrue(any(
                "Action card moves to slot 1" in rule
                for rule in core_rules["rules"]
            ))

            own_cards = compact["self"].get("initial_draw", [])
            self.assertTrue(own_cards)
            details = call_tool(path, "inspect_card", {
                "card_ref": own_cards[0]["detail_ref"],
            })
            self.assertEqual(own_cards[0]["id"], details["id"])
            bare_details = call_tool(path, "inspect_card", {
                "card_ref": own_cards[0]["id"],
            })
            self.assertEqual(details["id"], bare_details["id"])
            rules_index = call_tool(path, "inspect_rules")
            self.assertIn("cards", {item["id"] for item in rules_index["topics"]})
            cards_rules = call_tool(path, "inspect_rules", {"topic": "cards"})
            self.assertEqual("Cards Action I / II", cards_rules["title"])
            self.assertIn("costs no money", cards_rules["shared"][1])
            self.assertIn("capped at 9", cards_rules["reputation_limit"])
            self.assertEqual(9, compact["self"]["track_constraints"]["reputation_limit"])
            self.assertIn("cannot exceed 9", compact["self"]["track_constraints"]["reputation_rule"])
            association_rules = call_tool(path, "inspect_rules", {"topic": "association"})
            self.assertIn("never money prices", association_rules["money_cost"])
            self.assertIn("2nd: upgrade one Action card", association_rules["asset_ladders"]["universities"])
            self.assertIn(
                "do not need that project card in hand",
                association_rules["project_sources"]["displayed_projects"],
            )
            self.assertIn(
                "another player's worker never increases your cost",
                association_rules["workers"],
            )
            self.assertTrue(all(
                card.get("effect_at_current_strength")
                for card in compact["self"]["action_cards"]
            ))

            opponent_ids = {
                card["id"] for card in self.state["players"][1]["initial_draw"]
            }
            indexed_refs = set(context["resources"]["cards"])
            self.assertTrue(all(f"card:{card_id}" not in indexed_refs for card_id in opponent_ids))
            with self.assertRaisesRegex(ValueError, "unavailable"):
                call_tool(path, "inspect_card", {
                    "card_ref": f"card:{next(iter(opponent_ids))}",
                })

    def test_animal_housing_options_make_standard_and_special_alternatives_explicit(self):
        card = compact_card({
            "id": "zoo-491", "kind": "animal", "card_type": "animal",
            "display_title": "Frilled Lizard",
            "facts": {
                "enclosure_size": 2,
                "can_use_standard_enclosure": True,
                "special_enclosure": "Reptile House 1",
            },
        })
        self.assertEqual([
            ("standard_enclosure", 2), ("reptile_house", 1),
        ], [
            (option["building_type"], option["capacity_used"])
            for option in card["housing_options"]
        ])

    def test_action_execution_contract_survives_legal_action_projection(self):
        legal = [{
            "id": "start:cards:m0:x0",
            "label": "cards · [5]",
            "action": {
                "type": "start_action", "action_card_id": "cards",
                "x_by_execution": [0], "multiplier_tokens": 0,
            },
            "execution_spec": {
                "action": "cards", "side": "I", "strength": 5,
                "draw_count": 3, "discard_count": 1, "break_steps": 2,
                "modes": ["draw", "snap"], "snap_cost": 0,
            },
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "turn-context.json"
            prepare_seat_context(
                path, match_id="match", seat=0, version=0,
                observation=self.observation, legal=legal,
            )
            action = call_tool(path, "legal_actions")["actions"][0]
            self.assertEqual(0, action["execution_spec"]["snap_cost"])
            self.assertIn("draw 3", action["rule_summary"])
            self.assertEqual("cards", action["rules_topic"])

    def test_displayed_project_tiers_and_immediate_association_opportunity_are_explicit(self):
        state = self.state
        for seat in range(2):
            choice = self.plugin.legal_actions(state, seat)[0]["action"]
            state, _ = self.plugin.apply_action(state, seat, choice)
        state["conservation_projects"][0] = {
            "id": "ark-nova:base-project-109",
            "base": True,
            "claims": [],
            "blocked_levels": ["low"],
        }
        player = state["players"][0]
        player["icons"]["reptile"] = 5
        player["association_workers"]["active"] = 1
        association = next(
            card for card in player["action_cards"]
            if card["action"] == "association"
        )
        strongest = next(
            card for card in player["action_cards"] if card["position"] == 5
        )
        association["position"], strongest["position"] = (
            strongest["position"], association["position"],
        )
        state["active_seat"] = 0
        observation = self.plugin.observe(state, 0)
        observation["state_version"] = 2
        legal = self.plugin.legal_actions(state, 0)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "turn-context.json"
            prepare_seat_context(
                path, match_id="match", seat=0, version=2,
                observation=observation, legal=legal,
            )
            compact = call_tool(path, "observe")
            reptiles = next(
                project for project in compact["global"]["base_conservation_projects"]
                if project["id"] == "ark-nova:base-project-109"
            )
            self.assertEqual("Reptile icons", reptiles["requirement"])
            self.assertEqual(5, reptiles["current_value"])
            high = next(tier for tier in reptiles["tiers"] if tier["id"] == "high")
            self.assertEqual((5, 5), (high["requirement"], high["conservation"]))
            self.assertEqual("high", reptiles["best_eligible_level"]["id"])

            opportunity = next(
                item for item in compact["decision_focus"][
                    "eligible_conservation_projects"
                ]
                if item["project_id"] == "ark-nova:base-project-109"
            )
            self.assertTrue(opportunity["legal_now"])
            self.assertFalse(opportunity["displayed_project_requires_card"])
            self.assertIn("other players never increase", opportunity["workers_rule"])

            association_actions = [
                action for action in call_tool(
                    path, "legal_actions", {"group": "start_action", "limit": 50},
                )["actions"]
                if action["id"].startswith("start:association")
            ]
            self.assertTrue(association_actions)
            self.assertTrue(any(
                "Reptiles" in action.get("opportunity_summary", "")
                and "no project card required" in action["opportunity_summary"]
                for action in association_actions
            ))

    def test_endgame_final_action_is_prominent_in_compact_observation(self):
        observation = dict(self.observation)
        observation["active_seat"] = 0
        observation["endgame"] = {
            "triggered": True,
            "triggered_by": 1,
            "remaining_final_turn_seats": [0],
            "is_my_final_action": True,
            "scoring_after_this_action": True,
            "instruction_cn": "这是你的最后一个行动；本行动结束后立即进行终局计分。",
            "instruction_en": "This is your final action; final scoring begins immediately after it ends.",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "turn-context.json"
            prepare_seat_context(
                path, match_id="match", seat=0, version=0,
                observation=observation, legal=self.legal,
            )
            compact = call_tool(path, "observe")
            self.assertTrue(compact["endgame"]["is_my_final_action"])
            focus = compact["decision_focus"]["endgame"]
            self.assertEqual([0], focus["remaining_final_turn_seats"])
            self.assertTrue(focus["scoring_after_this_action"])
            self.assertIn("final scoring begins immediately", focus["instruction"])

    def test_private_hand_precedes_public_board_after_setup_and_remains_inspectable(self):
        state = self.state
        for seat in range(2):
            choice = self.plugin.legal_actions(state, seat)[0]["action"]
            state, _ = self.plugin.apply_action(state, seat, choice)
        observation = self.plugin.observe(state, 0)
        observation["state_version"] = 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "turn-context.json"
            prepare_seat_context(
                path, match_id="match", seat=0, version=2,
                observation=observation,
                legal=self.plugin.legal_actions(state, 0),
            )
            compact = call_tool(path, "observe")
            self.assertEqual("hand", next(iter(compact["self"])))
            self.assertEqual(4, len(compact["self"]["hand"]))
            for card in compact["self"]["hand"]:
                details = call_tool(path, "inspect_card", {"card_ref": card["id"]})
                self.assertEqual(card["id"], details["id"])

    def test_large_legal_action_space_is_grouped_paged_and_complete(self):
        legal = []
        for rotation in range(3):
            for index in range(25):
                legal.append({
                    "id": f"build:{rotation}:{index}",
                    "label": f"Build rotation {rotation} at {index}",
                    "action": {
                        "type": "place_building", "building_type": "standard_enclosure",
                        "size": 3, "rotation": rotation,
                        "anchor": {"q": index, "r": -index},
                    },
                })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "turn-context.json"
            prepare_seat_context(
                path, match_id="match", seat=0, version=0,
                observation=self.observation, legal=legal,
            )
            grouped = call_tool(path, "legal_actions")
            self.assertEqual("groups", grouped["mode"])
            self.assertEqual(75, grouped["total"])
            seen = set()
            for group in grouped["groups"]:
                cursor = 0
                while cursor is not None:
                    page = call_tool(path, "legal_actions", {
                        "group": group["group"], "cursor": cursor, "limit": 11,
                    })
                    seen.update(item["id"] for item in page["actions"])
                    cursor = page["next_cursor"]
            self.assertEqual({item["id"] for item in legal}, seen)
            accepted = call_tool(path, "submit_action", {"action_id": next(iter(seen))})
            self.assertTrue(accepted["accepted"])

    def test_map_sections_and_observation_history_are_on_demand(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "turn-context.json"
            prepare_seat_context(
                path, match_id="match", seat=0, version=0,
                observation=self.observation, legal=self.legal,
            )
            buildings = call_tool(path, "inspect_map", {
                "seat": 0, "sections": ["buildings"],
            })
            self.assertIn("buildings", buildings)
            self.assertNotIn("terrain", buildings)

            changed = json.loads(json.dumps(self.observation))
            changed["state_version"] = 1
            changed["players"][0]["money"] += 3
            prepare_seat_context(
                path, match_id="match", seat=0, version=1,
                observation=changed, legal=self.legal,
            )
            observed = call_tool(path, "observe")
            delta = observed["changes_since_last_observation"]
            self.assertFalse(delta["baseline"])
            self.assertTrue(any(
                event.get("seat") == 0
                and "money" in event.get("changes", {})
                for event in delta["events"]
            ))
            history = call_tool(path, "inspect_history", {"since_version": 0})
            self.assertEqual("observed_state_changes", history["history_scope"])
            self.assertEqual(1, history["total"])


if __name__ == "__main__":
    unittest.main()
