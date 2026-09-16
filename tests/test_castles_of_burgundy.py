import random
from pathlib import Path
import tempfile
import unittest
from collections import Counter, deque

from agentbga import castles_of_burgundy as burgundy
from agentbga.agent_context import prepare_seat_context
from agentbga.seat_tool import call_tool


class CastlesOfBurgundyTests(unittest.TestCase):
    def _action(self, state, action_type, **matches):
        for item in burgundy.legal_actions(state, state["active_seat"]):
            action = item["action"]
            if action["type"] == action_type and all(action.get(key) == value for key, value in matches.items()):
                return action
        self.fail(f"no {action_type} action matching {matches}")

    def _put_in_storage(self, state, tile_id, seat=None):
        seat = state["active_seat"] if seat is None else seat
        for pile in state["tile_supply"].values():
            if tile_id in pile:
                pile.remove(tile_id)
                break
        else:
            if tile_id in state["black_supply"]:
                state["black_supply"].remove(tile_id)
            elif tile_id in state["black_depot"]:
                state["black_depot"].remove(tile_id)
            else:
                for depot in state["depots"]:
                    if tile_id in depot["tiles"]:
                        depot["tiles"].remove(tile_id)
                        break
                else:
                    state["discarded_tiles"].remove(tile_id)
        state["players"][seat]["storage"].append(tile_id)

    def _make_placeable(self, state, tile_id, color):
        player = state["players"][state["active_seat"]]
        self._put_in_storage(state, tile_id)
        candidates = [
            cell for cell in player["duchy"]
            if cell["tile_id"] is None and cell["color"] == color
            and burgundy._occupied_neighbors(player, cell)
        ]
        if not candidates:
            targets = [cell for cell in player["duchy"]
                       if cell["tile_id"] is None and cell["color"] == color]
            target = min(targets, key=lambda cell: burgundy.axial_hex_distance(
                (cell["q"], cell["r"]), (0, 0),
            ))
            cells = {(cell["q"], cell["r"]): cell for cell in player["duchy"]}
            frontier = deque([(0, 0)])
            previous = {(0, 0): None}
            goal = (target["q"], target["r"])
            while frontier and goal not in previous:
                current = frontier.popleft()
                for neighbor in burgundy.axial_hex_neighbors(current) & cells.keys():
                    if neighbor not in previous:
                        previous[neighbor] = current
                        frontier.append(neighbor)
            path = []
            cursor = goal
            while previous[cursor] is not None:
                path.append(cursor)
                cursor = previous[cursor]
            for coordinate in reversed(path[1:]):
                cell = cells[coordinate]
                if cell["tile_id"] is not None:
                    continue
                filler = next(
                    candidate for candidate, tile in burgundy.TILES.items()
                    if tile["color"] == cell["color"] and candidate not in self._all_used_tiles(state)
                )
                self._put_in_storage(state, filler)
                player["storage"].remove(filler)
                cell["tile_id"] = filler
        else:
            target = candidates[0]
        state["remaining_dice"][0]["value"] = target["number"]
        return target

    def test_setup_is_seeded_and_matches_physical_catalog(self):
        first = burgundy.new_game(4, 42)
        second = burgundy.new_game(4, 42)
        self.assertEqual(first, second)
        self.assertEqual(164, len(burgundy.TILES))
        self.assertEqual(42, len(burgundy.GOODS))
        self.assertEqual(37, len(first["players"][0]["duchy"]))
        self.assertEqual(8, len(first["black_depot"]))
        self.assertEqual(24, sum(len(depot["tiles"]) for depot in first["depots"]))
        self.assertEqual([4] * 6, [len(depot["tiles"]) for depot in first["depots"]])
        colors = [cell["color"] for cell in first["players"][0]["duchy"]]
        self.assertEqual(
            {"building": 12, "livestock": 6, "monastery": 6,
             "castle": 4, "mine": 3, "ship": 6},
            dict(sorted(Counter(colors).items())),
        )
        self.assertEqual(6, burgundy.CELL_TEMPLATE["+0,+0"]["number"])
        self.assertEqual("watchtower", burgundy.MONASTERY_BUILDINGS[17])
        self.assertEqual("bank", burgundy.MONASTERY_BUILDINGS[22])
        burgundy.validate_state(first)

    def test_worker_changes_die_and_take_moves_tile_to_storage(self):
        state = burgundy.new_game(2, 7)
        seat = state["active_seat"]
        state["players"][seat]["workers"] = 4
        die = state["remaining_dice"][0]
        target_depot = 1 if die["value"] not in (1, 6) else 3
        tile_id = state["depots"][target_depot - 1]["tiles"][0]
        action = self._action(
            state, "take_tile", die_index=die["index"], depot=target_depot, tile_id=tile_id,
        )
        next_state, events = burgundy.apply_action(state, seat, action)
        self.assertIn(tile_id, next_state["players"][seat]["storage"])
        self.assertEqual("tile_taken", events[1]["type"])
        self.assertLessEqual(next_state["players"][seat]["workers"], 4)

    def test_castle_grants_an_immediate_free_die_action(self):
        state = burgundy.new_game(2, 9)
        seat = state["active_seat"]
        target = self._make_placeable(state, "castle-14", "castle")
        burgundy.validate_state(state)
        action = self._action(state, "place_tile", tile_id="castle-14", cell_id=target["id"])
        next_state, _ = burgundy.apply_action(state, seat, action)
        self.assertEqual(1, next_state["free_actions"])
        bonus = [item["action"] for item in burgundy.legal_actions(next_state, seat)]
        self.assertTrue(any(action["type"] == "take_workers" and action["source"] == "bonus"
                            for action in bonus))

    def test_livestock_scores_matching_animals_in_same_pasture(self):
        state = burgundy.new_game(2, 11)
        seat = state["active_seat"]
        player = state["players"][seat]
        target = self._make_placeable(state, "livestock-sheep-01", "livestock")
        region = target["region"]
        second = next(
            burgundy._cell(player, cell_id) for cell_id in burgundy.REGIONS[region]
            if cell_id != target["id"]
        )
        second["tile_id"] = "livestock-sheep-02"
        self._put_in_storage(state, "livestock-sheep-02")
        player["storage"].remove("livestock-sheep-02")
        burgundy.validate_state(state)
        before = player["score"]
        action = self._action(state, "place_tile", tile_id="livestock-sheep-01", cell_id=target["id"])
        next_state, events = burgundy.apply_action(state, seat, action)
        scored = next(event for event in events if event["type"] == "livestock_scored")
        self.assertEqual(5, scored["points"])
        self.assertGreater(next_state["players"][seat]["score"], before)

    def test_ship_advances_bridge_and_resolves_goods_choice(self):
        state = burgundy.new_game(2, 13)
        seat = state["active_seat"]
        target = self._make_placeable(state, "ship-20", "ship")
        burgundy.validate_state(state)
        action = self._action(state, "place_tile", tile_id="ship-20", cell_id=target["id"])
        next_state, _ = burgundy.apply_action(state, seat, action)
        self.assertEqual(1, next_state["players"][seat]["bridge"])
        self.assertEqual("choose_goods", next_state["pending_effect"]["kind"])
        self.assertTrue(burgundy.legal_actions(next_state, seat))

    def test_black_depot_purchase_costs_two_silver_and_no_die(self):
        state = burgundy.new_game(2, 17)
        seat = state["active_seat"]
        state["players"][seat]["silver"] = 2
        tile_id = state["black_depot"][0]
        dice_before = list(state["remaining_dice"])
        action = self._action(state, "buy_tile", tile_id=tile_id, silver=2, workers=0)
        next_state, _ = burgundy.apply_action(state, seat, action)
        self.assertEqual(0, next_state["players"][seat]["silver"])
        self.assertEqual(dice_before, next_state["remaining_dice"])
        self.assertTrue(next_state["bought_this_turn"])

    def test_region_completion_scores_size_and_phase(self):
        state = burgundy.new_game(2, 19)
        seat = state["active_seat"]
        player = state["players"][seat]
        target = self._make_placeable(state, "building-bank-05", "building")
        region = target["region"]
        for cell_id in burgundy.REGIONS[region]:
            if cell_id == target["id"]:
                continue
            cell = burgundy._cell(player, cell_id)
            tile_id = next(
                candidate for candidate, tile in burgundy.TILES.items()
                if tile["color"] == "building" and candidate not in self._all_used_tiles(state)
            )
            self._put_in_storage(state, tile_id)
            player["storage"].remove(tile_id)
            cell["tile_id"] = tile_id
        burgundy.validate_state(state)
        action = self._action(state, "place_tile", tile_id="building-bank-05", cell_id=target["id"])
        _next_state, events = burgundy.apply_action(state, seat, action)
        completed = next(event for event in events if event["type"] == "area_completed")
        size = len(burgundy.REGIONS[region])
        self.assertEqual(burgundy.AREA_POINTS[size] + 10, completed["points"])

    @staticmethod
    def _all_used_tiles(state):
        used = set(state["black_depot"])
        used.update(tile for depot in state["depots"] for tile in depot["tiles"])
        for player in state["players"]:
            used.update(player["storage"])
            used.update(cell["tile_id"] for cell in player["duchy"] if cell["tile_id"])
        return used

    def test_random_legal_agents_complete_seeded_match(self):
        state = burgundy.new_game(2, 23)
        rng = random.Random(23)
        decisions = 0
        while state["status"] == "active" and decisions < 5000:
            legal = burgundy.legal_actions(state, state["active_seat"])
            self.assertTrue(legal)
            state, _ = burgundy.apply_action(
                state, state["active_seat"], rng.choice(legal)["action"],
            )
            decisions += 1
        self.assertEqual("finished", state["status"])
        self.assertEqual(50, state["turn_count"])
        burgundy.validate_state(state)

    def test_agent_observation_is_grouped_without_losing_board_information(self):
        state = burgundy.new_game(2, 29)
        seat = state["active_seat"]
        observation = burgundy.observe(state, seat)
        observation["state_version"] = 7
        legal = burgundy.legal_actions(state, seat)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "turn-context.json"
            prepare_seat_context(
                path, match_id="burgundy-test", seat=seat, version=7,
                observation=observation, legal=legal,
            )
            view = call_tool(path, "observe")

        self.assertEqual("castles_of_burgundy", view["game"])
        self.assertEqual(7, view["state_version"])
        self.assertEqual(observation["remaining_dice"], view["dice"]["remaining_dice"])
        self.assertEqual(observation["depots"], view["market"]["depots"])
        self.assertEqual(
            observation["players"][seat]["duchy"],
            view["players"][seat]["tiles"]["duchy"],
        )
        self.assertNotIn("depots", view)
        self.assertNotIn("round_dice", view)
        self.assertEqual(
            Counter(item["action"]["type"] for item in legal),
            Counter({item["group"]: item["count"] for item in view["legal_action_groups"]}),
        )

    def test_agent_legal_actions_support_groups_filters_and_original_ids(self):
        state = burgundy.new_game(2, 31)
        seat = state["active_seat"]
        state["players"][seat]["workers"] = 6
        observation = burgundy.observe(state, seat)
        observation["state_version"] = 9
        legal = burgundy.legal_actions(state, seat)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "turn-context.json"
            context = prepare_seat_context(
                path, match_id="burgundy-test", seat=seat, version=9,
                observation=observation, legal=legal,
            )
            target = next(
                item for item in context["legal_actions"]
                if item["type"] == "take_tile" and item["source"] == "die"
            )
            tile_color = burgundy.TILES[target["tile_id"]]["color"]
            result = call_tool(path, "legal_actions", {"filters": {
                "type": "take_tile",
                "source": "die",
                "die_index": target["die_index"],
                "depot": target["depot"],
                "tile_color": tile_color,
                "max_workers": target["workers"],
            }})
            grouped = call_tool(path, "legal_actions", {"group": "take_tile"})
            accepted = call_tool(path, "submit_action", {"action_id": target["id"]})

        self.assertIn(target["id"], {item["id"] for item in result["actions"]})
        self.assertTrue(all(item["type"] == "take_tile" for item in grouped["actions"]))
        self.assertEqual(
            {item["id"] for item in context["legal_actions"] if item["type"] == "take_tile"},
            {item["id"] for item in grouped["actions"]},
        )
        self.assertTrue(accepted["accepted"])


if __name__ == "__main__":
    unittest.main()
