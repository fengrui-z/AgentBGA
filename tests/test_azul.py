import random
import unittest

from agentbga import azul


class AzulTests(unittest.TestCase):
    def test_setup_is_deterministic_and_uses_official_component_counts(self):
        for players, factories in azul.FACTORY_COUNTS.items():
            state = azul.new_game(players, 42)
            self.assertEqual(factories, len(state["factories"]))
            self.assertTrue(all(len(row["tiles"]) == 4 for row in state["factories"]))
            self.assertEqual(100 - factories * 4, len(state["bag"]))
            self.assertEqual(players, len(state["players"]))
            azul.validate_state(state)
        self.assertEqual(azul.new_game(2, 42), azul.new_game(2, 42))
        self.assertNotEqual(azul.new_game(2, 42)["factories"],
                            azul.new_game(2, 43)["factories"])
        with self.assertRaises(azul.RuleError):
            azul.new_game(1, 42)

    def test_observation_exposes_colors_and_counts_but_not_tile_ids_or_bag_order(self):
        state = azul.new_game(2, 7)
        view = azul.observe(state, 0)
        self.assertNotIn("bag", view)
        self.assertEqual(len(state["bag"]), view["bag_count"])
        self.assertEqual(set(azul.COLORS), set(view["factories"][0]["tiles"]))
        self.assertNotIn(state["factories"][0]["tiles"][0], str(view))

    def test_factory_draft_moves_remainder_to_center_and_places_selected_tiles(self):
        state = azul.new_game(2, 8)
        factory = state["factories"][0]
        color = azul.TILES[factory["tiles"][0]]
        selected = sum(azul.TILES[tile] == color for tile in factory["tiles"])
        action = {
            "type": "draft_tiles", "source": factory["id"], "color": color,
            "destination": "pattern-line-5",
        }
        state, events = azul.apply_action(state, 0, action)
        self.assertEqual([], state["factories"][0]["tiles"])
        self.assertEqual(4 - selected, len(state["center"]))
        self.assertEqual(selected, len(state["players"][0]["pattern_lines"][4]["tiles"]))
        self.assertIn("factory_remainder_moved", [event["type"] for event in events])

    def test_center_draft_claims_start_marker_and_floor_overflow_goes_to_lid(self):
        state = azul.new_game(2, 9)
        first = state["factories"][0]
        color = azul.TILES[first["tiles"][0]]
        state, _ = azul.apply_action(state, 0, {
            "type": "draft_tiles", "source": first["id"], "color": color,
            "destination": "floor",
        })
        center_color = azul.TILES[state["center"][0]]
        center_count = sum(azul.TILES[tile] == center_color for tile in state["center"])
        before_lid = len(state["lid"])
        state, events = azul.apply_action(state, 1, {
            "type": "draft_tiles", "source": "center", "color": center_color,
            "destination": "floor",
        })
        floor = state["players"][1]["floor"]
        self.assertIn(azul.START_MARKER, floor)
        self.assertFalse(state["center_has_start_marker"])
        expected_overflow = max(0, center_count + 1 - len(azul.FLOOR_PENALTIES))
        self.assertEqual(before_lid + expected_overflow, len(state["lid"]))
        self.assertIn("start_player_marker_taken", [event["type"] for event in events])

    def test_round_with_no_center_tiles_retains_the_round_start_player(self):
        state = azul.new_game(2, 10)
        state["round"] = 2
        state["active_seat"] = 1
        state["round_start_seat"] = 1
        all_tiles = list(azul.TILES)
        chosen = []
        drafts = []
        for factory, color in zip(state["factories"], azul.COLORS, strict=True):
            tiles = [tile for tile in all_tiles if azul.TILES[tile] == color][:4]
            factory["tiles"] = tiles
            chosen.extend(tiles)
            drafts.append((factory["id"], color))
        state["bag"] = [tile for tile in all_tiles if tile not in chosen]
        state["lid"] = []
        state["center"] = []
        azul.validate_state(state)

        events = []
        for source, color in drafts:
            state, events = azul.apply_action(state, state["active_seat"], {
                "type": "draft_tiles",
                "source": source,
                "color": color,
                "destination": "floor",
            })

        self.assertEqual(3, state["round"])
        self.assertEqual(1, state["active_seat"])
        self.assertEqual(1, state["round_start_seat"])
        self.assertTrue(state["center_has_start_marker"])
        self.assertIn("start_player_marker_retained", [event["type"] for event in events])
        azul.validate_state(state)

    def test_wall_placement_scoring_covers_isolated_and_crossing_connections(self):
        wall = [[None for _ in range(5)] for _ in range(5)]
        wall[2][2] = "placed"
        self.assertEqual(1, azul._wall_placement_score(wall, 2, 2))
        wall[2][1] = "left"
        self.assertEqual(2, azul._wall_placement_score(wall, 2, 2))
        wall[2][3] = "right"
        wall[1][2] = "up"
        wall[3][2] = "down"
        self.assertEqual(6, azul._wall_placement_score(wall, 2, 2))

    def test_rankings_use_completed_rows_as_the_only_score_tiebreak(self):
        state = azul.new_game(2, 11)
        state["players"][0]["score"] = 10
        state["players"][1]["score"] = 10
        for column, color in enumerate(azul.WALL_PATTERN[1]):
            tile = next(tile for tile in state["bag"] if azul.TILES[tile] == color)
            state["bag"].remove(tile)
            state["players"][1]["wall"][1][column] = tile
        azul.validate_state(state)
        ranking = azul.rankings(state)
        self.assertEqual(1, ranking[0]["seat"])
        self.assertEqual([1, 2], [row["rank"] for row in ranking])

    def test_endgame_bonus_counts_rows_columns_and_complete_color_sets(self):
        player = azul._player_board(0)
        player["wall"] = [["occupied" for _ in range(5)] for _ in range(5)]
        self.assertEqual({
            "completed_rows": 5,
            "completed_columns": 5,
            "completed_colors": 5,
            "row_points": 10,
            "column_points": 35,
            "color_points": 50,
            "total": 95,
        }, azul._endgame_bonus(player))

    def test_illegal_action_is_atomic(self):
        state = azul.new_game(2, 13)
        before = azul.state_hash(state)
        with self.assertRaises(azul.RuleError):
            azul.apply_action(state, 0, {
                "type": "draft_tiles", "source": "center", "color": "blue",
                "destination": "pattern-line-1",
            })
        self.assertEqual(before, azul.state_hash(state))

    def test_action_ids_are_stable_and_wrong_seat_has_no_actions(self):
        state = azul.new_game(2, 12)
        first = azul.legal_actions(state, 0)
        second = azul.legal_actions(state, 0)
        self.assertEqual(first, second)
        self.assertEqual(len(first), len({row["id"] for row in first}))
        self.assertEqual([], azul.legal_actions(state, 1))

    def test_random_games_finish_and_preserve_all_tiles(self):
        for seed in range(6):
            state = azul.new_game(2 + seed % 3, seed)
            rng = random.Random(seed)
            for _ in range(300):
                if state["status"] == "finished":
                    break
                actions = azul.legal_actions(state, state["active_seat"])
                self.assertTrue(actions)
                state, _ = azul.apply_action(
                    state, state["active_seat"], rng.choice(actions)["action"],
                )
                azul.validate_state(state)
            self.assertEqual("finished", state["status"])
            self.assertEqual(100, sum(
                len(zone) for zone in self._tile_zones(state)
            ))

    @staticmethod
    def _tile_zones(state):
        yield state["bag"]
        yield state["lid"]
        yield state["center"]
        for factory in state["factories"]:
            yield factory["tiles"]
        for player in state["players"]:
            for line in player["pattern_lines"]:
                yield line["tiles"]
            for row in player["wall"]:
                yield [tile for tile in row if tile is not None]
            yield [tile for tile in player["floor"] if tile != azul.START_MARKER]


if __name__ == "__main__":
    unittest.main()
