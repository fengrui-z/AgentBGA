"""Base-game CATAN rule regressions.

Rule references: CATAN base rules (2020) and https://www.catan.com/faq/basegame.
Scenarios deliberately isolate rules while preserving physical resource/card supply.
"""

from collections import Counter
from copy import deepcopy
import json
import random
import unittest
from unittest.mock import patch

from agentbga import catan
from agentbga.game import GameRuleError


class CatanTests(unittest.TestCase):
    def _actions(self, state, seat=None):
        seat = state["active_seat"] if seat is None else seat
        return [row["action"] for row in catan.legal_actions(state, seat)]

    def _action(self, state, kind, **matches):
        for action in self._actions(state):
            if action["type"] == kind and all(action.get(k) == v for k, v in matches.items()):
                return action
        self.fail(f"No legal {kind} action matching {matches}; phase={state['phase']}")

    def _play(self, state, kind, **matches):
        return catan.apply_action(state, state["active_seat"], self._action(state, kind, **matches))[0]

    def _setup(self, players=3, seed=17):
        state = catan.new_game(players, seed)
        while state["phase"].startswith("setup"):
            state, _ = catan.apply_action(state, state["active_seat"], self._actions(state)[0])
        return state

    def _main(self, players=3):
        state = self._setup(players)
        state["phase"] = "main"
        state["turn_count"] = 3
        return state

    def _empty_board(self, players=3):
        state = self._main(players)
        for vertex in state["board"]["vertices"]:
            vertex["building"] = None
        for edge in state["board"]["edges"]:
            edge["owner"] = None
        for player in state["players"]:
            for resource in catan.RESOURCES:
                state["bank"][resource] += player["resources"][resource]
                player["resources"][resource] = 0
        state["longest_road_seat"] = None
        return state

    def _give(self, state, seat=0, **resources):
        for resource, amount in resources.items():
            self.assertGreaterEqual(state["bank"][resource], amount)
            state["bank"][resource] -= amount
            state["players"][seat]["resources"][resource] += amount

    def _dev(self, state, kind, seat=0, bought_turn=0):
        card_id = next(card for card in state["development_deck"] if catan.DEVELOPMENT_CARDS[card] == kind)
        state["development_deck"].remove(card_id)
        state["players"][seat]["development_cards"].append({
            "id": card_id, "type": kind, "bought_turn": bought_turn,
        })
        return card_id

    def _path(self, state, length, excluded=(), start=None):
        board = state["board"]
        blocked = set(excluded)

        def visit(vertices, edges):
            if len(edges) == length:
                return vertices, edges
            for edge_id in board["vertices"][vertices[-1]]["edges"]:
                edge = board["edges"][edge_id]
                other = next(v for v in edge["vertices"] if v != vertices[-1])
                if other not in blocked and other not in vertices:
                    result = visit(vertices + [other], edges + [edge_id])
                    if result is not None:
                        return result
            return None

        starts = [start] if start is not None else range(len(board["vertices"]))
        for vertex in starts:
            if vertex not in blocked:
                result = visit([vertex], [])
                if result is not None:
                    return result
        self.fail(f"No path of {length} edges outside {blocked}")

    def _roads(self, state, edges, seat=0):
        for edge in edges:
            state["board"]["edges"][edge]["owner"] = seat

    def _building(self, state, vertex, seat=0, kind="settlement"):
        state["board"]["vertices"][vertex]["building"] = {"seat": seat, "type": kind}

    def _assert_resources(self, state):
        for resource in catan.RESOURCES:
            self.assertEqual(19, state["bank"][resource] + sum(
                player["resources"][resource] for player in state["players"]
            ))
            self.assertGreaterEqual(state["bank"][resource], 0)

    def _assert_rejected(self, state, action, seat=None):
        before = deepcopy(state)
        with self.assertRaises(GameRuleError):
            catan.apply_action(state, state["active_seat"] if seat is None else seat, action)
        self.assertEqual(before, state, "Rejected actions must not mutate authoritative state")

    def test_setup_inventory_topology_and_determinism(self):
        for players in (3, 4):
            with self.subTest(players=players):
                state = catan.new_game(players, 42)
                self.assertEqual(state, catan.new_game(players, 42))
                catan.validate_state(state)
                board = state["board"]
                self.assertEqual((19, 54, 72, 9), tuple(len(board[k]) for k in ("hexes", "vertices", "edges", "ports")))
                self.assertEqual(Counter(brick=3, lumber=4, wool=4, grain=4, ore=3, desert=1), Counter(h["terrain"] for h in board["hexes"]))
                self.assertEqual(Counter({2: 1, 3: 2, 4: 2, 5: 2, 6: 2, 8: 2, 9: 2, 10: 2, 11: 2, 12: 1}), Counter(h["number"] for h in board["hexes"] if h["number"] is not None))
                self.assertEqual(Counter(knight=14, victory_point=5, road_building=2, year_of_plenty=2, monopoly=2), Counter(catan.DEVELOPMENT_CARDS.values()))
                self.assertEqual(25, len(state["development_deck"]))
                self.assertEqual("desert", board["hexes"][state["robber_hex"]]["terrain"])
                self.assertEqual(18, len({v for port in board["ports"] for v in port["vertices"]}))
                for edge in board["edges"]:
                    self.assertEqual(2, len(edge["vertices"]))
                    for vertex in edge["vertices"]:
                        self.assertIn(edge["id"], board["vertices"][vertex]["edges"])
                for tile in board["hexes"]:
                    self.assertEqual(6, len(tile["vertices"]))
                    self.assertEqual(6, len(tile["edges"]))
                self._assert_resources(state)
        for invalid in (1, 2, 5):
            with self.assertRaises(GameRuleError):
                catan.new_game(invalid, 1)
        with self.assertRaises(GameRuleError):
            catan.new_game(3, 1, {"unknown": True})

    def test_snake_setup_second_settlement_resources_and_free_roads(self):
        for players in (3, 4):
            state = catan.new_game(players, 3)
            settlement_seats = []
            expected = [Counter() for _ in range(players)]
            while state["phase"].startswith("setup"):
                actor = state["active_seat"]
                action = self._actions(state)[0]
                if action["type"] == "place_settlement":
                    settlement_seats.append(actor)
                    vertex = action["vertex"]
                    if len(settlement_seats) > players:
                        for tile in state["board"]["hexes"]:
                            if vertex in tile["vertices"] and tile["terrain"] != "desert":
                                expected[actor][tile["terrain"]] += 1
                else:
                    self.assertEqual("place_road", action["type"])
                    self.assertIn(vertex, state["board"]["edges"][action["edge"]]["vertices"])
                before = deepcopy(state)
                state, events = catan.apply_action(state, actor, action)
                self.assertEqual("action_accepted", events[0]["type"])
                self.assertNotEqual(before, state)
                self._assert_resources(state)
            self.assertEqual(list(range(players)) + list(reversed(range(players))), settlement_seats)
            self.assertEqual("roll", state["phase"])
            self.assertEqual(0, state["active_seat"])
            for seat in range(players):
                self.assertEqual(expected[seat], +Counter(state["players"][seat]["resources"]))
                self.assertEqual(2, sum(v["building"] is not None and v["building"]["seat"] == seat for v in state["board"]["vertices"]))
                self.assertEqual(2, sum(e["owner"] == seat for e in state["board"]["edges"]))
            catan.validate_state(state)

    def test_legal_action_rejections_are_atomic_and_seat_private(self):
        state = catan.new_game(3, 4)
        action = self._actions(state)[0]
        self._assert_rejected(state, action, seat=1)
        self._assert_rejected(state, {"type": "place_settlement", "vertex": -1})
        self._assert_rejected(state, {"type": "end_turn"})
        self._assert_rejected(state, {**action, "unexpected": "field"})
        self.assertEqual([], self._actions(state, 1))
        self.assertEqual([], self._actions(state, 2))
        before = deepcopy(state)
        first, first_events = catan.apply_action(state, 0, action)
        second, second_events = catan.apply_action(state, 0, action)
        self.assertEqual(before, state)
        self.assertEqual(first, second)
        self.assertEqual(first_events, second_events)
        self.assertEqual(catan.state_hash(first), catan.state_hash(second))

    def test_building_costs_connection_and_distance(self):
        state = self._empty_board()
        vertices, edges = self._path(state, 3)
        self._building(state, vertices[0])
        self._roads(state, edges[:2])
        self._give(state, brick=2, lumber=2, wool=1, grain=3, ore=3)
        allowed = self._actions(state)
        self.assertNotIn({"type": "build_settlement", "vertex": vertices[1]}, allowed)
        self.assertIn({"type": "build_settlement", "vertex": vertices[2]}, allowed)
        far_vertex = next(v["id"] for v in state["board"]["vertices"] if v["id"] not in vertices)
        self._assert_rejected(state, {"type": "build_settlement", "vertex": far_vertex})
        self._assert_rejected(state, {"type": "build_city", "vertex": vertices[2]})
        initial = dict(state["players"][0]["resources"])
        state = self._play(state, "build_settlement", vertex=vertices[2])
        for resource in ("brick", "lumber", "wool", "grain"):
            self.assertEqual(initial[resource] - 1, state["players"][0]["resources"][resource])
        state = self._play(state, "build_city", vertex=vertices[2])
        self.assertEqual({"seat": 0, "type": "city"}, state["board"]["vertices"][vertices[2]]["building"])
        self.assertEqual(0, state["players"][0]["resources"]["ore"])
        self.assertEqual(0, state["players"][0]["resources"]["grain"])
        state = self._play(state, "build_road", edge=edges[2])
        self.assertEqual(0, state["players"][0]["resources"]["brick"])
        self.assertEqual(0, state["players"][0]["resources"]["lumber"])
        self._assert_resources(state)
        catan.validate_state(state)

    def test_enemy_building_blocks_extension_but_existing_far_side_can_extend(self):
        state = self._empty_board()
        vertices, edges = self._path(state, 3)
        self._roads(state, edges[:1])
        self._building(state, vertices[1], seat=1)
        self._give(state, brick=1, lumber=1)
        self._assert_rejected(state, {"type": "build_road", "edge": edges[1]})
        self._roads(state, edges[1:2])
        self.assertIn({"type": "build_road", "edge": edges[2]}, self._actions(state))

    def test_production_city_double_and_robber_blocks_only_its_hex(self):
        state = self._empty_board()
        tile = next(h for h in state["board"]["hexes"] if h["terrain"] != "desert")
        self._building(state, tile["vertices"][0], kind="city")
        # Keep just one producing number, so the scenario has no incidental income.
        for other in state["board"]["hexes"]:
            if other["id"] != tile["id"] and other["terrain"] != "desert":
                other["number"] = 3 if tile["number"] != 3 else 4
        catan._produce(state, tile["number"], [])
        self.assertEqual(2, state["players"][0]["resources"][tile["terrain"]])
        state["robber_hex"] = tile["id"]
        catan._produce(state, tile["number"], [])
        self.assertEqual(2, state["players"][0]["resources"][tile["terrain"]])
        self._assert_resources(state)

    def test_production_shortage_single_recipient_gets_bank_remainder(self):
        state = self._empty_board()
        tile = next(h for h in state["board"]["hexes"] if h["terrain"] != "desert")
        self._building(state, tile["vertices"][0], kind="city")
        resource = tile["terrain"]
        self._give(state, seat=2, **{resource: 18})
        catan._produce(state, tile["number"], [])
        self.assertEqual(1, state["players"][0]["resources"][resource])
        self.assertEqual(0, state["bank"][resource])
        self._assert_resources(state)

    def test_production_shortage_multiple_recipients_get_none(self):
        state = self._empty_board()
        tile = next(h for h in state["board"]["hexes"] if h["terrain"] != "desert")
        self._building(state, tile["vertices"][0])
        self._building(state, tile["vertices"][2], seat=1)
        resource = tile["terrain"]
        self._give(state, seat=2, **{resource: 18})
        catan._produce(state, tile["number"], [])
        self.assertEqual(0, state["players"][0]["resources"][resource])
        self.assertEqual(0, state["players"][1]["resources"][resource])
        self.assertEqual(1, state["bank"][resource])
        self._assert_resources(state)

    def test_longest_road_counts_cycle_and_stops_at_opponent(self):
        state = self._empty_board()
        tile = state["board"]["hexes"][0]
        self._roads(state, tile["edges"])
        self.assertEqual(6, catan.longest_road_length(state, 0))
        self._building(state, tile["vertices"][0])
        self.assertEqual(6, catan.longest_road_length(state, 0))
        self._building(state, tile["vertices"][0], seat=1)
        self.assertEqual(6, catan.longest_road_length(state, 0))
        self._building(state, tile["vertices"][3], seat=2)
        self.assertEqual(3, catan.longest_road_length(state, 0))

    def test_longest_road_branch_uses_two_arms_and_block_splits_chain(self):
        state = self._empty_board()
        center = next(v for v in state["board"]["vertices"] if len(v["edges"]) == 3)
        self._roads(state, center["edges"])
        self.assertEqual(2, catan.longest_road_length(state, 0))
        state = self._empty_board()
        vertices, edges = self._path(state, 6)
        self._roads(state, edges)
        self.assertEqual(6, catan.longest_road_length(state, 0))
        self._building(state, vertices[3], seat=1)
        self.assertEqual(3, catan.longest_road_length(state, 0))

    def test_longest_road_threshold_incumbent_tie_and_transfer(self):
        state = self._empty_board()
        vertices, first = self._path(state, 6)
        _, second = self._path(state, 6, excluded=vertices)
        self._roads(state, first[:4])
        catan._update_awards(state)
        self.assertIsNone(state["longest_road_seat"])
        self._roads(state, first[4:5])
        catan._update_awards(state)
        self.assertEqual(0, state["longest_road_seat"])
        self._roads(state, second[:5], seat=1)
        catan._update_awards(state)
        self.assertEqual(0, state["longest_road_seat"])
        self._roads(state, second[5:], seat=1)
        catan._update_awards(state)
        self.assertEqual(1, state["longest_road_seat"])
        state["board"]["edges"][second[-1]]["owner"] = None
        state["longest_road_seat"] = None
        catan._update_awards(state)
        self.assertIsNone(state["longest_road_seat"])

    def test_largest_army_threshold_tie_and_transfer(self):
        state = self._main()
        state["players"][0]["played_knights"] = 2
        catan._update_awards(state)
        self.assertIsNone(state["largest_army_seat"])
        state["players"][0]["played_knights"] = 3
        catan._update_awards(state)
        self.assertEqual(0, state["largest_army_seat"])
        state["players"][1]["played_knights"] = 3
        catan._update_awards(state)
        self.assertEqual(0, state["largest_army_seat"])
        state["players"][1]["played_knights"] = 4
        catan._update_awards(state)
        self.assertEqual(1, state["largest_army_seat"])

    def test_opponent_composition_and_victory_cards_do_not_leak(self):
        first = self._empty_board()
        self._give(first, seat=0, brick=2)
        self._give(first, seat=1, grain=2)
        self._give(first, seat=2, ore=2)
        self._dev(first, "victory_point", seat=1)
        self._dev(first, "knight", seat=2)
        second = deepcopy(first)
        for key in ("resources", "development_cards"):
            second["players"][1][key], second["players"][2][key] = second["players"][2][key], second["players"][1][key]
        self.assertNotEqual(catan.score(first, 1), catan.score(second, 1))
        self.assertEqual(catan.observe(first, 0), catan.observe(second, 0))
        self.assertEqual(catan.legal_actions(first, 0), catan.legal_actions(second, 0))
        self.assertNotEqual(catan.observe(first, 1), catan.observe(second, 1))
        observation = catan.observe(first, 0)
        for secret_key in ("seed", "rng_counter", "development_deck"):
            self.assertNotIn(secret_key, observation)
        self.assertNotIn("victory_point-", json.dumps(observation))
        # Composing an offer must not reveal which recipient can afford it.
        first = self._play(first, "propose_trade", partner=1)
        second = self._play(second, "propose_trade", partner=1)
        for _ in range(3):
            self.assertEqual(catan.observe(first, 0), catan.observe(second, 0))
            self.assertEqual(catan.legal_actions(first, 0), catan.legal_actions(second, 0))
            action = next(a for a in self._actions(first) if a["type"] == "trade_amount" and a["amount"] == (1 if a["resource"] == "brick" else 0))
            first, _ = catan.apply_action(first, 0, action)
            second, _ = catan.apply_action(second, 0, action)

    def test_seven_discards_half_once_then_moves_robber(self):
        state = self._empty_board()
        state["phase"] = "roll"
        self._give(state, seat=0, brick=9)
        self._give(state, seat=1, wool=8)
        self._give(state, seat=2, grain=7)
        with patch.object(catan, "_draw_random", side_effect=[2, 3]):
            state = self._play(state, "roll_dice")
        discards = Counter()
        while state["phase"] == "discard":
            actor = state["active_seat"]
            actions = self._actions(state)
            self.assertEqual({"discard"}, {a["type"] for a in actions})
            self._assert_rejected(state, {"type": "end_turn"})
            discards[actor] += 1
            state, _ = catan.apply_action(state, actor, actions[0])
        self.assertEqual(Counter({0: 4, 1: 4}), discards)
        self.assertEqual([5, 4, 7], [sum(p["resources"].values()) for p in state["players"]])
        self.assertEqual(0, state["active_seat"])
        self._assert_rejected(state, {"type": "move_robber", "hex": state["robber_hex"]})
        old_hex = state["robber_hex"]
        state = self._play(state, "move_robber")
        self.assertNotEqual(old_hex, state["robber_hex"])
        self.assertEqual("main", state["phase"])
        self._assert_resources(state)
        catan.validate_state(state)

    def test_robber_steals_deterministically_without_public_resource_identity(self):
        state = self._empty_board()
        state["phase"] = "roll"
        tile = next(h for h in state["board"]["hexes"] if h["id"] != state["robber_hex"])
        self._building(state, tile["vertices"][0], seat=1)
        self._give(state, seat=1, ore=2, wool=2)
        with patch.object(catan, "_draw_random", side_effect=[2, 3]):
            state = self._play(state, "roll_dice")
        state = self._play(state, "move_robber", hex=tile["id"])
        self._assert_rejected(state, {"type": "steal", "victim": 0})
        self._assert_rejected(state, {"type": "steal", "victim": 2})
        action = self._action(state, "steal", victim=1)
        first, events = catan.apply_action(state, 0, action)
        second, replay_events = catan.apply_action(state, 0, action)
        self.assertEqual(first, second)
        self.assertEqual(events, replay_events)
        self.assertEqual(1, sum(first["players"][0]["resources"].values()))
        self.assertEqual(3, sum(first["players"][1]["resources"].values()))
        self.assertEqual("main", first["phase"])
        event_text = json.dumps(events)
        self.assertNotIn('"ore"', event_text)
        self.assertNotIn('"wool"', event_text)
        self._assert_resources(first)

    def test_bought_development_card_waits_until_next_turn(self):
        state = self._empty_board()
        self._give(state, wool=1, grain=1, ore=1)
        # A fixed top card checks purchase timing independently of shuffle order.
        knight = next(card for card in state["development_deck"] if catan.DEVELOPMENT_CARDS[card] == "knight")
        state["development_deck"].remove(knight)
        state["development_deck"].append(knight)
        state = self._play(state, "buy_development_card")
        self.assertEqual(0, sum(state["players"][0]["resources"].values()))
        self.assertEqual(1, len(state["players"][0]["development_cards"]))
        self._assert_rejected(state, {"type": "play_knight"})
        state = self._play(state, "end_turn")
        for _ in range(2):
            with patch.object(catan, "_draw_random", side_effect=[0, 0]):
                state = self._play(state, "roll_dice")
            state = self._play(state, "end_turn")
        self.assertEqual(0, state["active_seat"])
        self.assertEqual("roll", state["phase"])
        self.assertIn({"type": "play_knight"}, self._actions(state))
        self._assert_resources(state)

    def test_preroll_knight_does_not_discard_and_consumes_whole_turn_dev_limit(self):
        state = self._empty_board()
        state["phase"] = "roll"
        self._give(state, brick=10)
        self._dev(state, "knight")
        self._dev(state, "monopoly")
        state = self._play(state, "play_knight")
        self.assertEqual(10, state["players"][0]["resources"]["brick"])
        self.assertNotEqual("discard", state["phase"])
        state = self._play(state, "move_robber")
        self.assertEqual("roll", state["phase"])
        self.assertEqual(1, state["players"][0]["played_knights"])
        self.assertFalse(any(a["type"] == "play_monopoly" for a in self._actions(state)))
        with patch.object(catan, "_draw_random", side_effect=[0, 0]):
            state = self._play(state, "roll_dice")
        self._assert_rejected(state, {"type": "play_monopoly", "resource": "grain"})
        self._assert_resources(state)

    def test_year_of_plenty_takes_two_resources_including_same_type(self):
        state = self._empty_board()
        card_id = self._dev(state, "year_of_plenty")
        state = self._play(state, "play_year_of_plenty")
        state = self._play(state, "take_resource", resource="ore")
        state = self._play(state, "take_resource", resource="ore")
        self.assertEqual("main", state["phase"])
        self.assertEqual(2, state["players"][0]["resources"]["ore"])
        self.assertIn(card_id, state["development_discard"])
        self._assert_resources(state)

    def test_monopoly_collects_all_named_resources_only_from_opponents(self):
        state = self._empty_board()
        self._dev(state, "monopoly")
        self._give(state, ore=1)
        self._give(state, seat=1, ore=3, wool=2)
        self._give(state, seat=2, ore=2, brick=1)
        bank = deepcopy(state["bank"])
        state = self._play(state, "play_monopoly", resource="ore")
        self.assertEqual([6, 0, 0], [p["resources"]["ore"] for p in state["players"]])
        self.assertEqual(2, state["players"][1]["resources"]["wool"])
        self.assertEqual(1, state["players"][2]["resources"]["brick"])
        self.assertEqual(bank, state["bank"])
        self._assert_resources(state)

    def test_road_building_places_two_connected_roads_without_payment(self):
        state = self._empty_board()
        vertices, edges = self._path(state, 2)
        self._building(state, vertices[0])
        self._dev(state, "road_building")
        state = self._play(state, "play_road_building")
        state = self._play(state, "free_road", edge=edges[0])
        state = self._play(state, "free_road", edge=edges[1])
        self.assertEqual("main", state["phase"])
        self.assertEqual(0, sum(state["players"][0]["resources"].values()))
        self.assertEqual(2, sum(e["owner"] == 0 for e in state["board"]["edges"]))
        self._assert_resources(state)

    def test_maritime_trade_cost_and_owned_port_rates(self):
        for port_resource, ratio in ((None, 4), ("any", 3), ("brick", 2)):
            with self.subTest(port=port_resource):
                state = self._empty_board()
                if port_resource is not None:
                    port = next(p for p in state["board"]["ports"] if p["resource"] == port_resource)
                    self._building(state, port["vertices"][0])
                self._give(state, brick=4)
                state = self._play(state, "maritime_trade", give="brick", receive="ore", ratio=ratio)
                self.assertEqual(4 - ratio, state["players"][0]["resources"]["brick"])
                self.assertEqual(1, state["players"][0]["resources"]["ore"])
                self._assert_resources(state)
        state = self._empty_board()
        port = next(p for p in state["board"]["ports"] if p["resource"] == "brick")
        self._building(state, port["vertices"][0], seat=1)
        self._give(state, brick=4)
        self._assert_rejected(state, {"type": "maritime_trade", "give": "brick", "receive": "ore", "ratio": 2})
        self._assert_rejected(state, {"type": "maritime_trade", "give": "brick", "receive": "brick", "ratio": 4})

    def _offer(self, state, give, receive, partner=1):
        state = self._play(state, "propose_trade", partner=partner)
        for amounts in (give, receive):
            for resource in catan.RESOURCES:
                state = self._play(state, "trade_amount", resource=resource, amount=amounts.get(resource, 0))
        return state

    def test_domestic_bundle_offer_requires_recipient_consent_and_is_atomic(self):
        state = self._empty_board()
        self._give(state, brick=2, lumber=1)
        self._give(state, seat=1, grain=2, ore=1)
        before = deepcopy(state["players"])
        state = self._offer(state, {"brick": 2, "lumber": 1}, {"grain": 2, "ore": 1})
        self.assertEqual(1, state["active_seat"])
        self.assertEqual(before, state["players"])
        self._assert_rejected(state, {"type": "respond_trade", "accept": True}, seat=0)
        accepted = self._play(state, "respond_trade", accept=True)
        self.assertEqual(0, accepted["active_seat"])
        self.assertEqual("main", accepted["phase"])
        self.assertEqual(Counter(grain=2, ore=1), +Counter(accepted["players"][0]["resources"]))
        self.assertEqual(Counter(brick=2, lumber=1), +Counter(accepted["players"][1]["resources"]))
        self._assert_resources(accepted)
        declined = self._play(state, "respond_trade", accept=False)
        self.assertEqual(before, declined["players"])
        self.assertEqual("main", declined["phase"])
        self.assertEqual(0, declined["active_seat"])

    def test_unaffordable_trade_can_be_offered_and_declined_but_not_accepted(self):
        state = self._empty_board()
        self._give(state, brick=1)
        self._give(state, seat=1, wool=2)
        state = self._offer(state, {"brick": 1}, {"ore": 2})
        self.assertEqual(1, state["active_seat"])
        self._assert_rejected(state, {"type": "respond_trade", "accept": True})
        self.assertIn({"type": "respond_trade", "accept": False}, self._actions(state))
        state = self._play(state, "respond_trade", accept=False)
        self.assertEqual(1, state["players"][0]["resources"]["brick"])
        self._assert_resources(state)

    def test_counteroffer_swaps_roles_and_requires_turn_owner_consent(self):
        state = self._empty_board()
        self._give(state, brick=2)
        self._give(state, seat=1, wool=2)
        before = deepcopy(state["players"])
        state = self._offer(state, {"brick": 2}, {"wool": 1})
        state = self._play(state, "counter_trade")
        self.assertEqual(0, state["turn_seat"])
        self.assertEqual(1, state["active_seat"])
        for bundle in ({"wool": 2}, {"brick": 1}):
            for resource in catan.RESOURCES:
                state = self._play(state, "trade_amount", resource=resource, amount=bundle.get(resource, 0))
        self.assertEqual(before, state["players"])
        self.assertEqual(0, state["active_seat"])
        state = self._play(state, "respond_trade", accept=True)
        self.assertEqual("main", state["phase"])
        self.assertEqual(0, state["active_seat"])
        self.assertEqual(1, state["players"][0]["resources"]["brick"])
        self.assertEqual(2, state["players"][0]["resources"]["wool"])
        self._assert_resources(state)
        catan.validate_state(state)

    def test_live_rankings_do_not_expose_secret_victory_points(self):
        state = self._main()
        before = catan.rankings(state)
        self._dev(state, "victory_point", seat=1)
        self.assertEqual(before, catan.rankings(state))

    def test_canceling_trade_returns_to_main_without_transfers(self):
        state = self._empty_board()
        self._give(state, brick=2)
        self._give(state, seat=1, wool=1)
        before = deepcopy(state["players"])
        state = self._play(state, "propose_trade", partner=1)
        state = self._play(state, "trade_amount", resource="brick", amount=2)
        state = self._play(state, "cancel_trade")
        self.assertEqual("main", state["phase"])
        self.assertEqual(before, state["players"])

    def test_ten_points_only_wins_on_owners_turn_and_needs_no_roll(self):
        state = self._empty_board()
        # Five available victory cards plus five legally separated settlements.
        chosen = []
        for vertex in state["board"]["vertices"]:
            neighbors = {v for edge in vertex["edges"] for v in state["board"]["edges"][edge]["vertices"]}
            if not neighbors.intersection(chosen):
                self._building(state, vertex["id"], seat=1)
                chosen.append(vertex["id"])
                if len(chosen) == 5:
                    break
        for _ in range(5):
            self._dev(state, "victory_point", seat=1)
        self.assertEqual(10, catan.score(state, 1))
        catan._check_winner(state, [])
        self.assertEqual("active", state["status"])
        state = self._play(state, "end_turn")
        self.assertEqual("finished", state["status"])
        self.assertEqual(1, catan.rankings(state)[0]["seat"])
        self.assertEqual([], catan.decision_seats(state))
        self.assertEqual([], self._actions(state, 1))

    def test_buying_victory_card_can_win_immediately(self):
        state = self._empty_board()
        chosen = []
        for vertex in state["board"]["vertices"]:
            neighbors = {v for edge in vertex["edges"] for v in state["board"]["edges"][edge]["vertices"]}
            if not neighbors.intersection(chosen):
                self._building(state, vertex["id"], kind="city" if len(chosen) < 4 else "settlement")
                chosen.append(vertex["id"])
                if len(chosen) == 5:
                    break
        self.assertEqual(9, catan.score(state, 0))
        self._give(state, wool=1, grain=1, ore=1)
        card = next(card for card in state["development_deck"] if catan.DEVELOPMENT_CARDS[card] == "victory_point")
        state["development_deck"].remove(card)
        state["development_deck"].append(card)
        state = self._play(state, "buy_development_card")
        self.assertEqual("finished", state["status"])
        self.assertEqual(0, catan.rankings(state)[0]["seat"])
        self.assertEqual(10, catan.score(state, 0))
        self._assert_resources(state)

    def test_seeded_three_and_four_player_rollouts_preserve_state_and_replay(self):
        for players in (3, 4):
            with self.subTest(players=players):
                state = catan.new_game(players, 102 + players)
                replay = deepcopy(state)
                rng = random.Random(players)
                phases = set()
                for _ in range(180):
                    if state["status"] == "finished":
                        break
                    phases.add(state["phase"])
                    actor = state["active_seat"]
                    legal = self._actions(state)
                    self.assertTrue(legal)
                    # Keep random play focused on board progress, without spending
                    # the bounded rollout repeatedly composing optional trades.
                    choices = [a for a in legal if a["type"] not in {"propose_trade", "cancel_trade"}] or legal
                    productive = [a for a in choices if a["type"] in {"build_city", "build_settlement", "buy_development_card"}]
                    action = rng.choice(productive or choices)
                    before = deepcopy(state)
                    state, events = catan.apply_action(state, actor, action)
                    replay, replay_events = catan.apply_action(replay, actor, action)
                    self.assertEqual(state, replay)
                    self.assertEqual(events, replay_events)
                    self.assertNotEqual(before, state)
                    catan.validate_state(state)
                    self._assert_resources(state)
                self.assertIn("main", phases)
                self.assertIn("roll", phases)
                self.assertIn("discard", phases)
                self.assertGreater(state["turn_count"], 10)


if __name__ == "__main__":
    unittest.main()
