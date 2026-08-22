import json
from pathlib import Path
import random
import tempfile
import threading
import unittest
from unittest import mock

from agentbga import seven_wonders as seven
from agentbga.agents import PlayerConfig
from agentbga.runner import run_match
from agentbga.store import Store


class SevenWondersTests(unittest.TestCase):
    def _action(self, state, action_type, **matches):
        for item in seven.legal_actions(state, state["active_seat"]):
            action = item["action"]
            if action["type"] == action_type and all(action.get(key) == value for key, value in matches.items()):
                return action
        self.fail(f"no {action_type} action matching {matches}")

    def _remove_card(self, state, card_id):
        for deck in state["age_decks"].values():
            if card_id in deck:
                deck.remove(card_id)
                return
        for hand in state["hands"]:
            if card_id in hand:
                hand.remove(card_id)
                return
        if card_id in state["discard"]:
            state["discard"].remove(card_id)
            return
        for player in state["players"]:
            for zone in ("city", "wonder_stages"):
                if card_id in player[zone]:
                    player[zone].remove(card_id)
                    return
        self.fail(f"card not found: {card_id}")

    def _move_to_hand(self, state, card_id, seat=0):
        self._remove_card(state, card_id)
        state["hands"][seat].append(card_id)

    def _move_to_city(self, state, card_id, seat=0):
        self._remove_card(state, card_id)
        state["players"][seat]["city"].append(card_id)

    def test_catalog_and_setup_match_second_edition_base_game(self):
        self.assertEqual(148, len(seven.CARDS))
        self.assertEqual({1: 49, 2: 49, 3: 50}, {
            age: sum(card["age"] == age for card in seven.CARDS.values()) for age in (1, 2, 3)
        })
        for players in range(3, 8):
            first = seven.new_game(players, 42)
            second = seven.new_game(players, 42)
            self.assertEqual(first, second)
            self.assertEqual([7] * players, [len(hand) for hand in first["hands"]])
            self.assertEqual(players * 7, len(first["age_decks"]["2"]))
            self.assertEqual(players * 7, len(first["age_decks"]["3"]))
            self.assertEqual(players, len({player["wonder"] for player in first["players"]}))
            self.assertTrue(all(player["wonder_side"] == "day" for player in first["players"]))

    def test_player_range_and_config_are_strict(self):
        with self.assertRaisesRegex(seven.RuleError, "3 to 7"):
            seven.new_game(2, 1)
        with self.assertRaisesRegex(seven.RuleError, "distinct"):
            seven.new_game(3, 1, {"wonders": ["giza", "giza", "rhodos"]})
        state = seven.new_game(3, 1, {
            "wonders": ["giza", "babylon", "rhodos"],
            "wonder_sides": ["night", "day", "night"],
        })
        self.assertEqual(["night", "day", "night"], [p["wonder_side"] for p in state["players"]])

    def test_choices_stay_sealed_until_every_player_submits(self):
        state = seven.new_game(3, 7)
        self.assertEqual([0, 1, 2], seven.decision_seats(state))
        self.assertTrue(all(seven.legal_actions(state, seat) for seat in range(3)))
        self.assertTrue(all(
            seven.observe(state, seat)["pending_choice_seats"] == []
            for seat in range(3)
        ))
        chosen = state["hands"][0][0]
        action = self._action(state, "sell_card", card_id=chosen)
        state, events = seven.apply_action(state, 0, action)
        self.assertEqual(["action_accepted"], [event["type"] for event in events])
        self.assertEqual("draft", state["phase"])
        self.assertEqual(1, state["active_seat"])
        other_view = seven.observe(state, 1)
        self.assertNotIn(chosen, json.dumps(other_view, sort_keys=True))
        self.assertTrue(other_view["players"][0]["choice_submitted"])

        for seat in (1, 2):
            action = self._action(state, "sell_card", card_id=state["hands"][seat][0])
            state, events = seven.apply_action(state, seat, action)
        self.assertEqual(2, state["pick"])
        self.assertEqual(0, state["active_seat"])
        self.assertEqual(6, len(state["hands"][0]))
        self.assertIn("card_sold", [event["type"] for event in events])

    def test_neighbor_trade_transfers_coins_on_reveal(self):
        state = seven.new_game(3, 3, {
            "wonders": ["olympia", "alexandria", "giza"], "wonder_sides": "day",
        })
        baths = "age1-baths-3"
        self._move_to_hand(state, baths, 0)
        seven.validate_state(state)
        build = next(
            item["action"] for item in seven.legal_actions(state, 0)
            if item["action"]["type"] == "build_card"
            and item["action"]["card_id"] == baths
            and item["action"]["payment"] == {"bank": 0, "left": 2, "right": 0}
        )
        self.assertEqual([{
            "direction": "left", "seat": 2, "coins": 2,
            "resources": {"stone": 1},
        }], build["purchases"])
        state, _ = seven.apply_action(state, 0, build)
        for seat in (1, 2):
            state, _ = seven.apply_action(
                state, seat, self._action(state, "sell_card", card_id=state["hands"][seat][0]),
            )
        self.assertIn(baths, state["players"][0]["city"])
        self.assertEqual(1, state["players"][0]["coins"])
        # Two trade Coins plus the three Coins from that neighbor's simultaneous sale.
        self.assertEqual(8, state["players"][2]["coins"])

    def test_trade_plans_keep_left_and_right_neighbor_choices_distinct(self):
        state = seven.new_game(3, 19, {
            "wonders": ["olympia", "alexandria", "giza"], "wonder_sides": "day",
        })
        self._move_to_city(state, "age1-stone-pit-3", 1)
        self._move_to_hand(state, "age1-baths-3", 0)
        seven.validate_state(state)

        builds = [
            item["action"] for item in seven.legal_actions(state, 0)
            if item["action"]["type"] == "build_card"
            and item["action"]["card_id"] == "age1-baths-3"
        ]
        purchases = {
            (action["purchases"][0]["direction"], action["purchases"][0]["seat"])
            for action in builds if action["purchases"]
        }
        self.assertEqual({("left", 2), ("right", 1)}, purchases)

    def test_trade_plans_hide_strictly_more_expensive_alternatives(self):
        state = seven.new_game(3, 31, {
            "wonders": ["olympia", "alexandria", "giza"], "wonder_sides": "day",
        })
        self._move_to_city(state, "age1-east-trading-post-3", 0)
        self._move_to_city(state, "age1-stone-pit-3", 1)
        self._move_to_hand(state, "age1-baths-3", 0)
        seven.validate_state(state)

        builds = [
            item["action"] for item in seven.legal_actions(state, 0)
            if item["action"]["type"] == "build_card"
            and item["action"]["card_id"] == "age1-baths-3"
        ]
        self.assertEqual(1, len(builds))
        self.assertEqual({"bank": 0, "left": 0, "right": 1}, builds[0]["payment"])
        self.assertEqual("right", builds[0]["purchases"][0]["direction"])

    def test_self_sufficient_builds_hide_unnecessary_neighbor_purchases(self):
        state = seven.new_game(3, 23, {
            "wonders": ["giza", "babylon", "alexandria"], "wonder_sides": "day",
        })
        self._move_to_city(state, "age1-stone-pit-3", 1)
        self._move_to_city(state, "age2-sawmill-3", 0)
        self._move_to_hand(state, "age1-baths-3", 0)
        seven.validate_state(state)

        legal = [item["action"] for item in seven.legal_actions(state, 0)]
        baths_builds = [
            action for action in legal
            if action["type"] == "build_card" and action["card_id"] == "age1-baths-3"
        ]
        wonder_builds = [action for action in legal if action["type"] == "build_wonder"]
        self.assertEqual(1, len(baths_builds))
        self.assertFalse(baths_builds[0]["purchases"])
        self.assertTrue(wonder_builds)
        self.assertTrue(all(not action["purchases"] for action in wonder_builds))

    def test_free_chain_build_hides_paid_neighbor_purchase_plans(self):
        state = seven.new_game(3, 29, {
            "wonders": ["alexandria", "giza", "babylon"], "wonder_sides": "day",
        })
        self._move_to_city(state, "age1-marketplace-3", 0)
        self._move_to_city(state, "age2-sawmill-3", 2)
        self._move_to_hand(state, "age2-caravansery-3", 0)
        state["players"][0]["coins"] = 10
        seven.validate_state(state)

        builds = [
            item["action"] for item in seven.legal_actions(state, 0)
            if item["action"]["type"] == "build_card"
            and item["action"]["card_id"] == "age2-caravansery-3"
        ]
        self.assertEqual(1, len(builds))
        self.assertEqual("chain", builds[0]["free_source"])
        self.assertEqual({"bank": 0, "left": 0, "right": 0}, builds[0]["payment"])
        self.assertEqual([], builds[0]["purchases"])

    def test_observation_describes_cards_wonder_stages_and_resource_sources(self):
        state = seven.new_game(3, 13, {
            "wonders": ["alexandria", "giza", "babylon"], "wonder_sides": "day",
        })
        self._move_to_city(state, "age1-clay-pit-3", 0)
        self._move_to_city(state, "age1-east-trading-post-3", 0)
        self._move_to_hand(state, "age1-baths-3", 0)
        seven.validate_state(state)

        player = seven.observe(state, 0)["players"][0]
        self.assertEqual("glass", player["starting_resource"])
        self.assertIn({
            "source_type": "wonder_start", "source_id": "alexandria",
            "source_name": "Alexandria", "options": ["glass"], "tradeable": True,
        }, player["resource_units"])
        clay_pit = next(
            unit for unit in player["resource_units"]
            if unit["source_id"] == "age1-clay-pit-3"
        )
        self.assertEqual(["ore", "clay"], clay_pit["options"])
        self.assertEqual("brown", clay_pit["source_color"])
        self.assertTrue(clay_pit["tradeable"])
        trading_post = next(
            unit for unit in player["resource_units"]
            if unit["source_id"] == "age1-east-trading-post-3"
        )
        self.assertEqual("trade_discount", trading_post["kind"])
        self.assertEqual("yellow", trading_post["source_color"])
        self.assertEqual(["right"], trading_post["directions"])
        self.assertEqual(list(seven.COMMON), trading_post["options"])

        stage_two = player["wonder_stages"][1]
        self.assertEqual([{
            "type": "production", "resources": list(seven.COMMON),
        }], stage_two["benefits"])
        baths = next(card for card in player["hand"] if card.get("name") == "Baths")
        self.assertIn({"type": "points", "amount": 3}, baths["benefits"])
        self.assertIn("Aqueduct", baths["chain_to"])

    def test_science_scores_squares_and_complete_sets(self):
        state = seven.new_game(3, 5)
        for card_id in ("age1-apothecary-3", "age1-workshop-3", "age1-scriptorium-3"):
            self._move_to_city(state, card_id)
        seven.validate_state(state)
        self.assertEqual(10, seven.score_breakdown(state, 0)["science"])

    def test_military_tokens_keep_their_age_when_conflicts_tie(self):
        state = seven.new_game(3, 43, {
            "wonders": ["alexandria", "giza", "babylon"], "wonder_sides": "day",
        })
        self._move_to_city(state, "age1-stockade-3", 0)
        self._move_to_city(state, "age1-guard-tower-3", 1)
        for hand in state["hands"]:
            state["discard"].extend(hand)
            hand.clear()

        events = []
        seven._end_age(state, events)
        self.assertEqual([[1], [], []], state["players"][0]["military_tokens_by_age"])
        self.assertEqual([[1], [], []], state["players"][1]["military_tokens_by_age"])
        self.assertEqual([[-1, -1], [], []], state["players"][2]["military_tokens_by_age"])

        self._move_to_city(state, "age1-barracks-3", 2)
        for hand in state["hands"]:
            state["discard"].extend(hand)
            hand.clear()
        seven._end_age(state, events)
        observed = seven.observe(state, 0)["players"]
        self.assertEqual([[1], [], []], observed[0]["military_tokens_by_age"])
        self.assertEqual([[1], [], []], observed[1]["military_tokens_by_age"])
        self.assertEqual([[-1, -1], [], []], observed[2]["military_tokens_by_age"])
        seven.validate_state(state)

    def test_observation_reports_each_guild_cards_current_points(self):
        state = seven.new_game(3, 37, {
            "wonders": ["alexandria", "giza", "babylon"], "wonder_sides": "day",
        })
        self._move_to_city(state, "age3-magistrates-guild-3", 0)
        self._move_to_city(state, "age1-altar-3", 1)
        self._move_to_city(state, "age1-baths-3", 2)
        seven.validate_state(state)

        guild = next(
            card for card in seven.observe(state, 0)["players"][0]["city"]
            if card["id"] == "age3-magistrates-guild-3"
        )
        self.assertEqual(2, guild["current_points"])
        self.assertEqual(2, seven.score_breakdown(state, 0)["guilds"])

        science_state = seven.new_game(3, 41, {
            "wonders": ["alexandria", "giza", "babylon"], "wonder_sides": "day",
        })
        self._move_to_city(science_state, "age3-scientists-guild-3", 0)
        self._move_to_city(science_state, "age1-apothecary-3", 0)
        seven.validate_state(science_state)
        scientists = next(
            card for card in seven.observe(science_state, 0)["players"][0]["city"]
            if card["id"] == "age3-scientists-guild-3"
        )
        self.assertEqual(3, scientists["current_points"])
        self.assertEqual(4, seven.score_breakdown(science_state, 0)["science"])

    def test_halikarnassos_stage_enters_free_discard_build_phase(self):
        state = seven.new_game(3, 11, {
            "wonders": ["halikarnassos", "giza", "alexandria"], "wonder_sides": "day",
        })
        stage_one = "age1-altar-3"
        clay = "age1-clay-pool-3"
        glass = "age1-glassworks-3"
        target = "age1-workshop-3"
        for card_id in (stage_one, clay, glass, target):
            self._remove_card(state, card_id)
        state["players"][0]["wonder_stages"].append(stage_one)
        state["players"][0]["city"].extend((clay, glass))
        state["discard"].append(target)
        seven.validate_state(state)

        material = state["hands"][0][0]
        action = self._action(state, "build_wonder", card_id=material, stage=2)
        state, _ = seven.apply_action(state, 0, action)
        for seat in (1, 2):
            state, _ = seven.apply_action(
                state, seat, self._action(state, "sell_card", card_id=state["hands"][seat][0]),
            )
        self.assertEqual("build_from_discard", state["phase"])
        action = self._action(state, "build_discard", card_id=target)
        state, events = seven.apply_action(state, 0, action)
        self.assertIn(target, state["players"][0]["city"])
        self.assertIn("discard_building_constructed", [event["type"] for event in events])

    def test_random_legal_agents_finish_all_supported_player_counts(self):
        for players in range(3, 8):
            with self.subTest(players=players):
                state = seven.new_game(players, players, {
                    "wonder_sides": ["day" if seat % 2 else "night" for seat in range(players)],
                })
                rng = random.Random(players)
                while state["status"] == "active" and state["decision_count"] < 300:
                    legal = seven.legal_actions(state, state["active_seat"])
                    self.assertTrue(legal)
                    state, _ = seven.apply_action(state, state["active_seat"], rng.choice(legal)["action"])
                self.assertEqual("finished", state["status"])
                seven.validate_state(state)

    def test_runner_decides_draft_choices_concurrently_from_one_snapshot(self):
        barrier = threading.Barrier(3)
        lock = threading.Lock()
        first_calls: list[tuple[int, int, tuple[int, ...], tuple[int, ...]]] = []

        class ConcurrentAgent:
            def __init__(self, seat):
                self.seat = seat
                self.called = False

            def choose(self, observation, legal, on_stream=None):
                if not self.called:
                    self.called = True
                    with lock:
                        first_calls.append((
                            self.seat,
                            observation["state_version"],
                            tuple(observation["pending_choice_seats"]),
                            tuple(observation["decision_seats"]),
                        ))
                    barrier.wait(timeout=3)
                return legal[0]["id"], {"test": "concurrent"}

        agents = [ConcurrentAgent(seat) for seat in range(3)]
        players = [
            PlayerConfig.from_dict({
                "name": f"Agent {seat}", "backend": "openai",
                "model": "fake", "api_key_env": "FAKE_KEY",
            }, seat)
            for seat in range(3)
        ]
        streamed: list[dict] = []
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            match_id, _, _ = store.create(3, 17, "seven_wonders")
            with mock.patch("agentbga.runner.build_model_agent", side_effect=agents):
                result = run_match(
                    store, match_id, players, max_turns=30, sink=streamed.append,
                )
            self.assertEqual("seven_wonders", result["game"])
            self.assertEqual("finished", store.load(match_id)[1]["status"])
            store.close()

        self.assertEqual({0, 1, 2}, {row[0] for row in first_calls})
        self.assertEqual({0}, {row[1] for row in first_calls})
        self.assertEqual({()}, {row[2] for row in first_calls})
        self.assertEqual({(0, 1, 2)}, {row[3] for row in first_calls})
        first_batch = [
            event for event in streamed
            if event["type"] == "decision" and event["snapshot_version"] == 0
        ]
        self.assertEqual(3, len(first_batch))
        self.assertTrue(all(event["simultaneous_seats"] == [0, 1, 2] for event in first_batch))


if __name__ == "__main__":
    unittest.main()
