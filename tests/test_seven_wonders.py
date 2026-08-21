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
        state, _ = seven.apply_action(state, 0, build)
        for seat in (1, 2):
            state, _ = seven.apply_action(
                state, seat, self._action(state, "sell_card", card_id=state["hands"][seat][0]),
            )
        self.assertIn(baths, state["players"][0]["city"])
        self.assertEqual(1, state["players"][0]["coins"])
        # Two trade Coins plus the three Coins from that neighbor's simultaneous sale.
        self.assertEqual(8, state["players"][2]["coins"])

    def test_science_scores_squares_and_complete_sets(self):
        state = seven.new_game(3, 5)
        for card_id in ("age1-apothecary-3", "age1-workshop-3", "age1-scriptorium-3"):
            self._move_to_city(state, card_id)
        seven.validate_state(state)
        self.assertEqual(10, seven.score_breakdown(state, 0)["science"])

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
