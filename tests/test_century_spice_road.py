import random
import unittest

from agentbga import century_spice_road as century


class CenturySpiceRoadTests(unittest.TestCase):
    def _action(self, state, action_type, **matches):
        legal = century.legal_actions(state, state["active_seat"])
        for item in legal:
            action = item["action"]
            if action["type"] == action_type and all(action.get(key) == value for key, value in matches.items()):
                return action
        self.fail(f"no {action_type} action matching {matches}")

    def _move_merchant_to_hand(self, state, card_id, seat=0):
        if card_id in state["merchant_deck"]:
            state["merchant_deck"].remove(card_id)
        else:
            slot = next(slot for slot in state["merchant_market"] if slot["card_id"] == card_id)
            state["merchant_market"].remove(slot)
            if state["merchant_deck"]:
                state["merchant_market"].append({
                    "card_id": state["merchant_deck"].pop(), "spices": century._pool(),
                })
        state["players"][seat]["hand"].append(card_id)

    def _move_points_to_player(self, state, card_ids, seat=0):
        for card_id in card_ids:
            if card_id in state["point_deck"]:
                state["point_deck"].remove(card_id)
            else:
                state["point_market"].remove(card_id)
            state["players"][seat]["point_cards"].append(card_id)
        while len(state["point_market"]) < century.POINT_MARKET_SIZE and state["point_deck"]:
            state["point_market"].append(state["point_deck"].pop())

    def test_catalog_and_setup_match_base_game(self):
        self.assertEqual(45, len(century.MERCHANTS))
        self.assertEqual(43, len([card for card in century.MERCHANTS if card.startswith("merchant-")]))
        self.assertEqual(36, len(century.POINT_CARDS))
        first = century.new_game(5, 42)
        second = century.new_game(5, 42)
        self.assertEqual(first, second)
        self.assertEqual(6, len(first["merchant_market"]))
        self.assertEqual(5, len(first["point_market"]))
        self.assertEqual(10, first["coins"]["gold"])
        self.assertEqual(
            [(3, 0), (4, 0), (4, 0), (3, 1), (3, 1)],
            [(p["spices"]["turmeric"], p["spices"]["saffron"]) for p in first["players"]],
        )

    def test_acquire_places_payment_and_collects_card_spices(self):
        state = century.new_game(2, 3)
        selected = state["merchant_market"][2]["card_id"]
        state["merchant_market"][2]["spices"]["cardamom"] = 1
        action = self._action(
            state, "acquire_merchant", position=2,
            payment=["turmeric", "turmeric"], discard={},
        )
        next_state, events = century.apply_action(state, 0, action)
        self.assertIn(selected, next_state["players"][0]["hand"])
        self.assertEqual(1, next_state["merchant_market"][0]["spices"]["turmeric"])
        self.assertEqual(1, next_state["merchant_market"][1]["spices"]["turmeric"])
        self.assertEqual(1, next_state["players"][0]["spices"]["cardamom"])
        self.assertEqual("merchant_acquired", events[1]["type"])

    def test_gain_card_forces_exact_caravan_discard(self):
        state = century.new_game(2, 1)
        state["players"][0]["spices"] = century._pool((9, 0, 0, 0))
        action = self._action(
            state, "play_merchant", card_id="start-gain", discard={"turmeric": 1},
        )
        next_state, _ = century.apply_action(state, 0, action)
        self.assertEqual(10, sum(next_state["players"][0]["spices"].values()))
        self.assertEqual(10, next_state["players"][0]["spices"]["turmeric"])

    def test_upgrade_can_chain_the_same_cube(self):
        state = century.new_game(2, 1)
        action = self._action(
            state, "play_merchant", card_id="start-upgrade",
            upgrades=["turmeric", "saffron"],
        )
        next_state, _ = century.apply_action(state, 0, action)
        self.assertEqual(2, next_state["players"][0]["spices"]["turmeric"])
        self.assertEqual(1, next_state["players"][0]["spices"]["cardamom"])

    def test_exchange_card_can_repeat(self):
        state = century.new_game(2, 1)
        self._move_merchant_to_hand(state, "merchant-40")  # YY -> RR
        state["players"][0]["spices"] = century._pool((4, 0, 0, 0))
        century.validate_state(state)
        action = self._action(
            state, "play_merchant", card_id="merchant-40", repetitions=2, discard={},
        )
        next_state, _ = century.apply_action(state, 0, action)
        self.assertEqual(century._pool((0, 4, 0, 0)), next_state["players"][0]["spices"])

    def test_gold_exhaustion_moves_silver_to_first_slot(self):
        state = century.new_game(2, 8)
        state["coins"]["gold"] = 1
        point = century.POINT_CARDS[state["point_market"][0]]
        state["players"][0]["spices"] = dict(point["cost"])
        action = self._action(state, "claim_point", position=0, point_id=point["id"])
        next_state, _ = century.apply_action(state, 0, action)
        self.assertEqual(1, next_state["players"][0]["coins"]["gold"])
        self.assertEqual(0, next_state["coins"]["gold"])
        self.assertEqual(0, next_state["coins"]["silver_position"])
        next_point = century.POINT_CARDS[next_state["point_market"][0]]
        next_state["players"][1]["spices"] = dict(next_point["cost"])
        action = self._action(next_state, "claim_point", position=0, point_id=next_point["id"])
        final_state, _ = century.apply_action(next_state, 1, action)
        self.assertEqual(1, final_state["players"][1]["coins"]["silver"])

    def test_two_player_sixth_point_card_finishes_current_round(self):
        state = century.new_game(2, 11)
        owned = list(century.POINT_CARDS)[:5]
        target = next(card_id for card_id in state["point_market"] if card_id not in owned)
        self._move_points_to_player(state, owned, seat=0)
        if target not in state["point_market"]:
            state["point_deck"].remove(target)
            replaced = state["point_market"][0]
            state["point_deck"].append(replaced)
            state["point_market"][0] = target
        point = century.POINT_CARDS[target]
        state["players"][0]["spices"] = dict(point["cost"])
        century.validate_state(state)
        position = state["point_market"].index(target)
        action = self._action(state, "claim_point", position=position, point_id=target)
        next_state, _ = century.apply_action(state, 0, action)
        self.assertEqual("active", next_state["status"])
        self.assertEqual(2, next_state["end_after_turn"])
        action = self._action(next_state, "play_merchant", card_id="start-gain")
        final_state, _ = century.apply_action(next_state, 1, action)
        self.assertEqual("finished", final_state["status"])

    def test_tied_score_is_won_by_later_player(self):
        state = century.new_game(2, 1)
        state["players"][0]["spices"] = century._pool()
        state["players"][1]["spices"] = century._pool()
        self.assertEqual(1, century.rankings(state)[0]["seat"])

    def test_random_legal_agents_finish_seeded_match(self):
        state = century.new_game(2, 0)
        rng = random.Random(0)
        while state["status"] == "active" and state["turn_count"] < 2000:
            action = rng.choice(century.legal_actions(state, state["active_seat"]))["action"]
            state, _ = century.apply_action(state, state["active_seat"], action)
        self.assertEqual("finished", state["status"])
        century.validate_state(state)


if __name__ == "__main__":
    unittest.main()
