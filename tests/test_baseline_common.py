import random
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from agentbga.agents import PlayerConfig
from agentbga.baselines.config import normalize_params
from agentbga.baselines.sampling import sample_state, SUPPORTED_RULES
from agentbga.registry import get_game, list_games
from agentbga.store import Store


class BaselineCommonTests(unittest.TestCase):
    def test_configuration_and_persistence(self):
        for backend in ("greedy", "heuristic", "ismcts"):
            config = PlayerConfig.from_dict(
                {
                    "name": backend,
                    "backend": backend,
                    "algorithm_params": {"seed": 17, "max_candidates": 8},
                },
                0,
            )
            with tempfile.TemporaryDirectory() as directory:
                store = Store(Path(directory) / "test.sqlite3")
                match, _, _ = store.create(2, 42)
                store.set_players(match, [config.public_dict()])
                self.assertEqual(
                    config.algorithm_params, store.players(match)[0]["algorithm_params"]
                )
                store.close()
        for bad in (
            {"unknown": 1},
            {"max_steps": 0},
            {"iterations": True},
            {"time_limit_ms": -1},
            {"max_steps": 1.5},
            {"exploration": float("nan")},
        ):
            with self.assertRaises(ValueError):
                normalize_params("ismcts", bad)
        with self.assertRaises(ValueError):
            normalize_params("greedy", {"iterations": 1})

    def test_every_default_game_has_a_sampler(self):
        self.assertEqual(set(SUPPORTED_RULES), {d["id"] for d in list_games()})
        for description in list_games():
            game = get_game(description["id"])
            state = game.setup(max(2, description["players"]["minimum"]), 42)
            for _ in range(30):
                if state["status"] != "active":
                    break
                seats = game.decision_seats(state)
                choices = {}
                for seat in seats:
                    with self.subTest(
                        game=game.game_id, phase=state["phase"], seat=seat
                    ):
                        before = deepcopy(state)
                        sample = sample_state(game, state, seat, random.Random(123))
                        game.validate_state(sample)
                        self.assertEqual(before, state)
                        self.assertEqual(
                            game.observe(state, seat), game.observe(sample, seat)
                        )
                        self.assertEqual(
                            game.legal_actions(state, seat),
                            game.legal_actions(sample, seat),
                        )
                        choices[seat] = random.Random(
                            43 + state.get("decision_count", state["turn_count"])
                        ).choice(game.legal_actions(state, seat))["action"]
                for seat in seats:
                    state, _ = game.apply_action(state, seat, choices[seat])

    def test_hidden_order_and_real_seed_do_not_change_samples(self):
        for name in SUPPORTED_RULES:
            game = get_game(name)
            description = game.describe()
            state = game.setup(max(2, description["players"]["minimum"]), 42)
            seat = game.decision_seats(state)[0]
            changed = deepcopy(state)
            changed["seed"] = 99999
            for key in (
                "deck",
                "bag",
                "zoo_deck",
                "draw_deck",
                "merchant_deck",
                "point_deck",
            ):
                if key in changed:
                    changed[key].reverse()
            if "decks" in changed:
                for deck in changed["decks"].values():
                    deck.reverse()
            with self.subTest(game=name):
                self.assertEqual(
                    sample_state(game, state, seat, random.Random(9)),
                    sample_state(game, changed, seat, random.Random(9)),
                )

    def test_player_counts_and_optional_setups(self):
        for description in list_games():
            game = get_game(description["id"])
            for count in {
                description["players"]["minimum"],
                description["players"]["maximum"],
            }:
                for seed in (17, 73):
                    state = game.setup(count, seed)
                    for seat in game.decision_seats(state):
                        with self.subTest(
                            game=game.game_id, players=count, seed=seed, seat=seat
                        ):
                            sampled = sample_state(game, state, seat, random.Random(8))
                            game.validate_state(sampled)
                            self.assertEqual(
                                game.observe(state, seat), game.observe(sampled, seat)
                            )
        for name, config in [
            ("harmonies", {"nature_spirits": True, "board_side": "B"}),
            ("wingspan", {"goal_board": "blue"}),
            ("ark_nova", {"map": "map-a"}),
        ]:
            game = get_game(name)
            state = game.setup(2, 17, config)
            for seat in game.decision_seats(state):
                sampled = sample_state(game, state, seat, random.Random(8))
                game.validate_state(sampled)
                self.assertEqual(game.observe(state, seat), game.observe(sampled, seat))

    def test_hidden_hand_assignment_does_not_influence_policy_world(self):
        for name in ("ark_nova", "wingspan", "brass_birmingham", "seven_wonders"):
            game = get_game(name)
            n = max(2, game.describe()["players"]["minimum"])
            state = game.setup(n, 42)
            seat = game.decision_seats(state)[0]
            other = (seat + 1) % n
            changed = deepcopy(state)
            if name == "ark_nova":
                a, b = changed["players"][other]["initial_draw"], changed["zoo_deck"]
            elif name == "wingspan":
                a, b = changed["players"][other]["hand"], changed["deck"]
            elif name == "brass_birmingham":
                a, b = changed["players"][other]["hand"], changed["draw_deck"]
            else:
                a, b = changed["hands"][other], changed["hands"][(other + 1) % n]
            a[0], b[0] = b[0], a[0]
            self.assertEqual(game.observe(state, seat), game.observe(changed, seat))
            self.assertEqual(
                sample_state(game, state, seat, random.Random(9)),
                sample_state(game, changed, seat, random.Random(9)),
            )

    def test_resume_with_sealed_seven_wonders_choice(self):
        game = get_game("seven_wonders")
        state = game.setup(3, 42)
        state, _ = game.apply_action(
            state, 0, game.legal_actions(state, 0)[0]["action"]
        )
        sampled = sample_state(game, state, 1, random.Random(8))
        game.validate_state(sampled)
        self.assertEqual(game.observe(state, 1), game.observe(sampled, 1))
        self.assertEqual(game.legal_actions(state, 1), game.legal_actions(sampled, 1))
