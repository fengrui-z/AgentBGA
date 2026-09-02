import unittest

from agentbga.ark_nova_official import (
    SemanticEngine,
    SemanticRuleError,
    action_execution_spec,
    complete_action_execution,
    current_action_execution,
    defer_after_finishing,
    install_official_conservation_milestones,
    legal_action_starts,
    new_semantic_state,
    queue_endgame_final_scoring_discard,
    start_action,
    take_x_token_action,
)
from agentbga.ark_nova_official.actions import skip_repeated_action_execution
from agentbga.ark_nova_official.action_domains import legal_official_actions


def effect(op: str, args: dict, timing: str = "immediate") -> dict:
    return {"op": op, "args": args, "timing": timing}


def card_for(state: dict, seat: int, action: str) -> dict:
    return next(
        card for card in state["players"][seat]["action_cards"]
        if card["action"] == action
    )


class ArkNovaOfficialActionTests(unittest.TestCase):
    def test_optional_repeated_multiplier_execution_can_be_skipped(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["phase"] = "active"
        card_for(state, 0, "association")["tokens"] = ["multiplier"]
        state, _ = start_action(
            state, 0, "association", x_by_execution=(0, 0), multiplier_tokens=1,
        )
        state, _ = complete_action_execution(
            engine, state, 0, {"performed": True, "tasks": ["test"]},
        )
        legal = legal_official_actions(engine, state, 0, {})
        self.assertIn(
            "multiplier:skip-repeated-execution",
            [choice["id"] for choice in legal],
        )
        started_second = {**state, "turn": {**state["turn"]}}
        started_second["turn"]["action_session"] = {
            **state["turn"]["action_session"],
            "association_resolution": {
                "remaining_strength": 1, "tasks": [], "task_ids": [],
                "pending_reward": None, "donation_made": False,
            },
        }
        self.assertNotIn(
            "multiplier:skip-repeated-execution",
            [choice["id"] for choice in legal_official_actions(
                engine, started_second, 0, {},
            )],
        )

        state, events = skip_repeated_action_execution(engine, state, 0)

        self.assertIsNone(state["turn"]["action_session"])
        self.assertEqual(1, state["active_seat"])
        self.assertEqual("repeated_action_execution_skipped", events[0]["type"])

    def test_unlocking_final_association_worker_gains_one_conservation(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["players"][0]["association_workers"].update({"active": 3, "reserve": 1})
        state, events = engine.start_effects(state, 0, [effect(
            "gain_association_worker", {"amount": 1},
        )], source_id="test:last-worker")
        self.assertEqual({"active": 4, "reserve": 0, "committed": []}, state["players"][0]["association_workers"])
        self.assertEqual(1, state["players"][0]["tracks"]["conservation"])
        self.assertTrue(any(
            event["type"] == "association_workers_activated"
            and event["last_worker_bonus"]
            for event in events
        ))

    def test_break_clears_interaction_markers_from_every_players_action_cards(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        card_for(state, 0, "animals")["tokens"] = [
            {"type": "constriction", "source_id": "boa"}, "multiplier",
        ]
        card_for(state, 1, "cards")["tokens"] = [
            {"type": "venom", "source_id": "snake"},
        ]
        state, events = engine.start_effects(state, 0, [effect(
            "for_each_player", {"effects": [effect("clear_action_tokens", {})]},
        )], source_id="break:test")
        self.assertEqual([], card_for(state, 0, "animals")["tokens"])
        self.assertEqual([], card_for(state, 1, "cards")["tokens"])
        self.assertEqual(
            [2, 1],
            [event["count"] for event in events if event["type"] == "break_action_tokens_cleared"],
        )

    def test_strength_is_locked_per_multiplier_execution_and_card_moves_after_both(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["phase"] = "active"
        state["players"][0]["x_tokens"] = 3
        build = card_for(state, 0, "build")
        self.assertEqual(3, build["position"])
        build["tokens"] = ["multiplier", "constriction", "venom"]

        state, events = start_action(
            state, 0, "build", x_by_execution=(1, 2), multiplier_tokens=1,
        )
        self.assertEqual([2, 3], events[0]["strengths"])
        self.assertEqual(0, state["players"][0]["x_tokens"])
        self.assertEqual(3, card_for(state, 0, "build")["position"])

        # An upgrade earned during an action does not change the locked side.
        card_for(state, 0, "build")["upgraded"] = True
        self.assertFalse(current_action_execution(state, 0)["upgraded"])
        state, _ = complete_action_execution(
            engine, state, 0, {"performed": True, "buildings": ["pavilion"]},
        )
        self.assertEqual(3, card_for(state, 0, "build")["position"])
        self.assertEqual(2, current_action_execution(state, 0)["number"])

        state, events = complete_action_execution(
            engine, state, 0, {"performed": True, "buildings": ["kiosk"]},
        )
        self.assertEqual(1, card_for(state, 0, "build")["position"])
        self.assertEqual([], card_for(state, 0, "build")["tokens"])
        self.assertEqual(1, state["active_seat"])
        self.assertEqual(1, state["turn"]["number"])
        self.assertEqual("turn_finished", events[-1]["type"])

    def test_after_finishing_effect_resolves_only_after_action_card_moves(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["phase"] = "active"
        state, _ = start_action(state, 0, "sponsors")
        state = defer_after_finishing(state, 0, [effect("gain_money", {"amount": 3})])
        self.assertEqual(5, card_for(state, 0, "sponsors")["position"])

        state, events = complete_action_execution(
            engine, state, 0, {"performed": True, "cards": ["test-sponsor"]},
        )
        self.assertEqual(1, card_for(state, 0, "sponsors")["position"])
        self.assertEqual(28, state["players"][0]["money"])
        self.assertEqual("active", state["phase"])
        self.assertEqual(1, state["active_seat"])
        self.assertEqual("action_finished", events[1]["type"])
        self.assertEqual("turn_finished", events[-1]["type"])

    def test_determination_opens_one_different_extra_action_without_new_turn(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["phase"] = "active"
        state["players"][0]["x_tokens"] = 1
        state, _ = start_action(state, 0, "animals", x_by_execution=(1,))
        state = defer_after_finishing(state, 0, [effect(
            "grant_extra_action", {"excluded_action": "animals"}, "after_finishing",
        )])
        state, events = complete_action_execution(
            engine, state, 0, {"performed": True, "cards": ["test-eagle"]},
        )
        self.assertEqual(0, state["active_seat"])
        self.assertEqual("active", state["phase"])
        self.assertEqual(1, state["turn"]["number"])
        self.assertTrue(any(event["type"] == "extra_action_window_opened" for event in events))
        starts = legal_action_starts(state, 0)
        self.assertNotIn("animals", {
            option["action"].get("action_card_id") for option in starts
        })

        state, _ = start_action(state, 0, "sponsors")
        self.assertTrue(state["turn"]["action_session"]["is_extra_action"])
        state, events = complete_action_execution(
            engine, state, 0, {"performed": True, "mode": "advance_break"},
        )
        self.assertEqual(1, state["active_seat"])
        self.assertEqual(1, state["turn"]["number"])
        self.assertEqual("turn_finished", events[-1]["type"])

    def test_alternative_x_action_moves_card_and_applies_remaining_venom_cost(self):
        state = new_semantic_state(2)
        state["phase"] = "active"
        card_for(state, 0, "animals")["tokens"] = ["venom"]
        state, events = take_x_token_action(state, 0, "cards")
        self.assertEqual(23, state["players"][0]["money"])
        self.assertEqual(1, state["players"][0]["x_tokens"])
        self.assertEqual(1, card_for(state, 0, "cards")["position"])
        self.assertEqual(["venom"], card_for(state, 0, "animals")["tokens"])
        self.assertEqual("x_token_action_completed", events[0]["type"])

        full = new_semantic_state(2)
        full["phase"] = "active"
        full["players"][0]["x_tokens"] = 5
        with self.assertRaisesRegex(SemanticRuleError, "five X-tokens"):
            take_x_token_action(full, 0, "cards")

    def test_legal_start_candidates_respect_constriction_and_separate_x_allocations(self):
        state = new_semantic_state(2)
        state["phase"] = "active"
        animals = card_for(state, 0, "animals")
        animals["position"] = 2
        card_for(state, 0, "cards")["position"] = 1
        animals["tokens"] = ["constriction", "multiplier"]
        starts = legal_action_starts(state, 0)
        self.assertFalse(any(item["id"].startswith("start:animals") for item in starts))
        self.assertTrue(any(item["id"] == "take-x:animals" for item in starts))

        state["players"][0]["x_tokens"] = 4
        starts = legal_action_starts(state, 0)
        twice = next(
            item for item in starts
            if item["action"]["action_card_id"] == "animals"
            and item["action"].get("multiplier_tokens") == 1
            and item["action"].get("x_by_execution") == [2, 2]
        )
        self.assertEqual(2, twice["execution_spec"]["strength"])

    def test_official_conservation_milestones_pause_in_order_and_share_bonus_tiles(self):
        engine = SemanticEngine()
        state = new_semantic_state(3)
        for seat in (0, 1, 2):
            state["players"][seat]["final_scoring_cards"] = [
                {"id": f"final-{seat}-a"}, {"id": f"final-{seat}-b"},
            ]
        state = install_official_conservation_milestones(
            state,
            bonuses_at_5=[{
                "id": "reputation-two",
                "label": "Gain 2 reputation",
                "effects": [effect("move_track", {"track": "reputation", "amount": 2})],
            }],
        )
        state, _ = engine.start_effects(
            state,
            0,
            [effect("move_track", {"track": "conservation", "amount": 10})],
            source_id="test:project",
        )
        self.assertIn("Upgrade", state["resolution"]["pending_choice"]["prompt"])

        upgrade = next(
            item["action"] for item in engine.legal_choice_actions(state, 0)
            if item["action"]["option_ids"] == ["upgrade-cards"]
        )
        state, _ = engine.submit_choice(
            state, 0, upgrade["choice_id"], upgrade["option_ids"],
        )
        self.assertTrue(card_for(state, 0, "cards")["upgraded"])
        self.assertIn("at 5", state["resolution"]["pending_choice"]["prompt"])

        bonus = next(
            item["action"] for item in engine.legal_choice_actions(state, 0)
            if item["action"]["option_ids"] == ["bonus-reputation-two"]
        )
        state, events = engine.submit_choice(
            state, 0, bonus["choice_id"], bonus["option_ids"],
        )
        self.assertEqual(2, state["players"][0]["tracks"]["reputation"])
        self.assertFalse(state["conservation_bonus_slots"]["5"][0]["available"])
        self.assertTrue(any(item["type"] == "conservation_bonus_taken" for item in events))
        self.assertIn("at 8", state["resolution"]["pending_choice"]["prompt"])

        money = engine.legal_choice_actions(state, 0)[0]["action"]
        state, _ = engine.submit_choice(
            state, 0, money["choice_id"], money["option_ids"],
        )
        self.assertEqual(30, state["players"][0]["money"])
        self.assertEqual(0, state["resolution"]["pending_choice"]["seat"])

        discard_0 = engine.legal_choice_actions(state, 0)[0]["action"]
        state, _ = engine.submit_choice(
            state, 0, discard_0["choice_id"], discard_0["option_ids"],
        )
        self.assertEqual(1, state["resolution"]["pending_choice"]["seat"])
        discard_1 = engine.legal_choice_actions(state, 1)[0]["action"]
        state, _ = engine.submit_choice(
            state, 1, discard_1["choice_id"], discard_1["option_ids"],
        )
        discard_2 = engine.legal_choice_actions(state, 2)[0]["action"]
        state, _ = engine.submit_choice(
            state, 2, discard_2["choice_id"], discard_2["option_ids"],
        )
        self.assertEqual([1, 1, 1], [
            len(player["final_scoring_cards"]) for player in state["players"]
        ])
        self.assertEqual(3, len(state["final_scoring_discard"]))
        self.assertTrue(state["endgame"]["final_scoring_discard_completed"])
        self.assertIsNone(state["resolution"]["pending_choice"])

    def test_reputation_five_opens_action_card_upgrade_choice(self):
        engine = SemanticEngine()
        state = install_official_conservation_milestones(new_semantic_state(2))
        state, _ = engine.start_effects(
            state, 0,
            [effect("move_track", {"track": "reputation", "amount": 5})],
            source_id="test:reputation",
        )
        choice = state["resolution"]["pending_choice"]
        self.assertEqual("action_upgrade_reward", choice["continuation"]["type"])
        self.assertEqual(
            {"upgrade-animals", "upgrade-cards", "upgrade-build", "upgrade-association", "upgrade-sponsors"},
            {option["id"] for option in choice["options"]},
        )

    def test_conservation_bonus_choices_follow_player_count_and_shared_supply(self):
        engine = SemanticEngine()
        tiles = [{
            "id": "tile-a", "label": "Tile A",
            "effects": [effect("gain_money", {"amount": 10})],
        }, {
            "id": "tile-b", "label": "Tile B",
            "effects": [effect("gain_x_token", {"amount": 3})],
        }]

        two_player = install_official_conservation_milestones(
            new_semantic_state(2), bonuses_at_5=tiles,
        )
        two_player, _ = engine.start_effects(
            two_player, 0,
            [effect("choose_conservation_reward", {"at": 5}, "system")],
            source_id="test:two-player-c5",
        )
        self.assertEqual(
            {"bonus-tile-a", "bonus-tile-b"},
            {option["id"] for option in two_player["resolution"]["pending_choice"]["options"]},
        )
        first = engine.legal_choice_actions(two_player, 0)[0]["action"]
        two_player, _ = engine.submit_choice(
            two_player, 0, first["choice_id"], first["option_ids"],
        )
        two_player, _ = engine.start_effects(
            two_player, 1,
            [effect("choose_conservation_reward", {"at": 5}, "system")],
            source_id="test:second-two-player-c5",
        )
        self.assertEqual(1, len(two_player["resolution"]["pending_choice"]["options"]))
        self.assertNotEqual(
            first["option_ids"][0],
            two_player["resolution"]["pending_choice"]["options"][0]["id"],
        )

        three_player = install_official_conservation_milestones(
            new_semantic_state(3), bonuses_at_5=tiles,
        )
        for seat in (0, 1):
            three_player, _ = engine.start_effects(
                three_player, seat,
                [effect("choose_conservation_reward", {"at": 5}, "system")],
                source_id=f"test:three-player-c5:{seat}",
            )
            bonus = next(
                item["action"] for item in engine.legal_choice_actions(three_player, seat)
                if item["action"]["option_ids"][0].startswith("bonus-")
            )
            three_player, _ = engine.submit_choice(
                three_player, seat, bonus["choice_id"], bonus["option_ids"],
            )
        three_player, _ = engine.start_effects(
            three_player, 2,
            [effect("choose_conservation_reward", {"at": 5}, "system")],
            source_id="test:third-three-player-c5",
        )
        self.assertEqual(
            ["money-5"],
            [option["id"] for option in three_player["resolution"]["pending_choice"]["options"]],
        )

    def test_unusable_optional_rewards_resolve_without_an_empty_choice(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["players"][0]["universities"] = [
            "research-2", "research-reputation", "research-hand-limit",
        ]
        state["conservation_bonus_slots"]["5"] = [{
            "id": "university", "label": "Take a university", "available": True,
            "effects": [{
                "op": "choose_bonus_association_asset",
                "args": {"asset": "university"}, "timing": "system",
            }],
        }]
        state, _ = engine.start_effects(
            state, 0,
            [effect("choose_conservation_reward", {"at": 5}, "system")],
            source_id="test:no-usable-conservation-reward",
        )
        self.assertIsNone(state["resolution"]["pending_choice"])
        self.assertEqual([], state["resolution"]["queue"])

        for card in state["players"][0]["action_cards"]:
            card["upgraded"] = True
        state["players"][0]["association_workers"]["reserve"] = 0
        for operation in (
            effect("choose_action_upgrade", {}, "system"),
            effect("choose_action_upgrade_or_worker", {}, "system"),
            effect("choose_bonus_association_asset", {"asset": "university"}, "system"),
        ):
            state, _ = engine.start_effects(
                state, 0, [operation], source_id=f"test:no-option:{operation['op']}",
            )
            self.assertIsNone(state["resolution"]["pending_choice"])
            self.assertEqual([], state["resolution"]["queue"])
    def test_endgame_fallback_discards_final_scoring_cards_when_ten_was_not_reached(self):
        engine = SemanticEngine()
        state = new_semantic_state(2)
        state["phase"] = "endgame"
        for seat in (0, 1):
            state["players"][seat]["final_scoring_cards"] = [
                {"id": f"fallback-{seat}-a"}, {"id": f"fallback-{seat}-b"},
            ]
        state, _ = queue_endgame_final_scoring_discard(engine, state, starting_seat=1)
        self.assertEqual(1, state["resolution"]["pending_choice"]["seat"])
        for seat in (1, 0):
            choice = engine.legal_choice_actions(state, seat)[0]["action"]
            state, _ = engine.submit_choice(
                state, seat, choice["choice_id"], choice["option_ids"],
            )
        self.assertEqual("endgame", state["phase"])
        self.assertTrue(state["endgame"]["final_scoring_discard_completed"])
        self.assertEqual([1, 1], [
            len(player["final_scoring_cards"]) for player in state["players"]
        ])

    def test_five_action_specs_are_human_readable_and_side_aware(self):
        specs = {
            action: action_execution_spec(action, action == "association", 5)
            for action in ("cards", "build", "animals", "association", "sponsors")
        }
        self.assertEqual(["draw", "snap"], specs["cards"]["modes"])
        self.assertEqual((3, 1), (
            specs["cards"]["draw_count"], specs["cards"]["discard_count"],
        ))
        self.assertEqual(5, specs["build"]["maximum_total_size"])
        self.assertEqual("hand_only", specs["animals"]["display_sources"])
        self.assertIsNone(specs["animals"]["display_surcharge"])
        self.assertEqual(2, specs["animals"]["maximum_cards"])
        self.assertTrue(specs["association"]["donation_allowed"])
        self.assertEqual(5, specs["sponsors"]["break_money"])

        cards_ii = action_execution_spec("cards", True, 5)
        self.assertEqual((4, 1), (cards_ii["draw_count"], cards_ii["discard_count"]))

        animals_ii = action_execution_spec("animals", True, 5)
        self.assertEqual("folder_number", animals_ii["display_surcharge"])
        self.assertEqual(1, animals_ii["reputation_before_play"])
        association_ii = action_execution_spec("association", True, 5)
        self.assertEqual(
            "hand_or_within_reputation",
            association_ii["new_project_card_sources"],
        )
        self.assertFalse(association_ii["displayed_projects_require_card"])
        self.assertNotIn("new_project_sources", association_ii)
        self.assertEqual("folder_number", association_ii["display_project_surcharge"])
        sponsors_ii = action_execution_spec("sponsors", True, 5)
        self.assertEqual("folder_number", sponsors_ii["display_surcharge"])
        self.assertTrue(action_execution_spec("build", True, 5)[
            "may_move_animals_into_new_special_enclosure"
        ])

    def test_official_strength_tables_cover_both_sides_at_strengths_one_to_five(self):
        self.assertEqual(
            [(1, 1), (1, 0), (2, 1), (2, 0), (3, 1)],
            [
                (action_execution_spec("cards", False, strength)["draw_count"],
                 action_execution_spec("cards", False, strength)["discard_count"])
                for strength in range(1, 6)
            ],
        )
        self.assertEqual(
            [(1, 0), (2, 1), (2, 0), (3, 1), (4, 1)],
            [
                (action_execution_spec("cards", True, strength)["draw_count"],
                 action_execution_spec("cards", True, strength)["discard_count"])
                for strength in range(1, 6)
            ],
        )
        self.assertEqual(
            [0, 1, 1, 1, 2],
            [action_execution_spec("animals", False, value)["maximum_cards"]
             for value in range(1, 6)],
        )
        self.assertEqual(
            [1, 1, 2, 2, 2],
            [action_execution_spec("animals", True, value)["maximum_cards"]
             for value in range(1, 6)],
        )


if __name__ == "__main__":
    unittest.main()
