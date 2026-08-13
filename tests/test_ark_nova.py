import copy
import random
import unittest

from agentbga import ark_nova


def apply_kind(state, kind, **matches):
    seat = state["active_seat"]
    item = next(
        item for item in ark_nova.legal_actions(state, seat)
        if item["action"]["type"] == kind
        and all(item["action"].get(key) == value for key, value in matches.items())
    )
    return ark_nova.apply_action(state, seat, item["action"])[0]


def finish_initial_hands(state):
    while state["phase"] == "initial_hand_selection":
        state = ark_nova.apply_action(
            state, state["active_seat"], ark_nova.legal_actions(state, state["active_seat"])[0]["action"],
        )[0]
    return state


class ArkNovaControlledCoreTests(unittest.TestCase):
    def test_setup_is_deterministic_and_matches_beginner_setup_shape(self):
        first = ark_nova.new_game(2, 42)
        second = ark_nova.new_game(2, 42)
        self.assertEqual(first, second)
        self.assertEqual("active", first["status"])
        self.assertEqual("initial_hand_selection", first["phase"])
        self.assertEqual(6, len(first["card_display"]))
        self.assertEqual(3, len(first["base_conservation_projects"]))
        self.assertEqual(12, len(first["base_conservation_projects"]) + len(first["base_conservation_deck"]))
        self.assertEqual(4, len(first["game_board_bonus_tiles"]))
        self.assertEqual(
            212, len(first["card_display"]) + len(first["zoo_deck"])
            + sum(len(player["initial_draw"]) for player in first["players"]),
        )
        for seat, player in enumerate(first["players"]):
            self.assertEqual(25, player["money"])
            self.assertEqual(seat, player["appeal"])
            self.assertEqual(8, len(player["initial_draw"]))
            self.assertEqual(2, len(player["final_scoring_cards"]))
            self.assertEqual("animals", player["action_cards"][0]["action"])
            self.assertEqual(3, player["map"]["buildings"][0]["size"])

    def test_observation_hides_private_cards_and_unrevealed_display(self):
        state = ark_nova.new_game(3, 7)
        view = ark_nova.observe(state, 0)
        self.assertEqual({"hidden": True}, view["card_display"][0])
        self.assertIn("id", view["players"][0]["initial_draw"][0])
        self.assertEqual({"hidden": True}, view["players"][1]["initial_draw"][0])
        self.assertIn("id", view["players"][0]["final_scoring_cards"][0])
        self.assertEqual({"hidden": True}, view["players"][2]["final_scoring_cards"][0])
        self.assertNotIn("zoo_deck", view)
        self.assertEqual(len(state["zoo_deck"]), view["deck_count"])

    def test_choose_initial_hand_is_a_real_decision_step(self):
        state = ark_nova.new_game(2, 1)
        legal = ark_nova.legal_actions(state, 0)
        self.assertEqual(70, len(legal))
        kept = set(legal[0]["action"]["card_ids"])
        state, events = ark_nova.apply_action(state, 0, legal[0]["action"])
        self.assertEqual(kept, {card["id"] for card in state["players"][0]["hand"]})
        self.assertEqual([], state["players"][0]["initial_draw"])
        self.assertEqual(1, state["active_seat"])
        self.assertEqual("initial_hand_selection", state["phase"])
        self.assertEqual("initial_hand_chosen", events[1]["type"])
        state = apply_kind(state, "choose_initial_hand")
        self.assertEqual("choose_action", state["phase"])
        self.assertEqual(0, state["active_seat"])
        self.assertNotIn("hidden", ark_nova.observe(state, 0)["card_display"][0])

    def test_action_card_moves_to_strength_one_and_x_action_works(self):
        state = finish_initial_hands(ark_nova.new_game(2, 3))
        player = state["players"][0]
        chosen = next(card for card in player["action_cards"] if card["strength"] == 5)
        state = apply_kind(state, "take_x_token", action_card=chosen["action"])
        player = state["players"][0]
        self.assertEqual(1, player["x_tokens"])
        self.assertEqual(1, next(card for card in player["action_cards"] if card["action"] == chosen["action"])["strength"])
        self.assertEqual(1, state["turn_count"])

    def test_cards_build_animals_association_and_sponsors_state_machines(self):
        state = finish_initial_hands(ark_nova.new_game(2, 17, {"turn_limit": 20}))

        # Cards: select the card, then snap a visible card.
        state = apply_kind(state, "select_action", action_card="cards", x_tokens=0)
        self.assertEqual("cards_choose", state["phase"])
        state = apply_kind(state, "snap_card") if any(
            item["action"]["type"] == "snap_card" for item in ark_nova.legal_actions(state, 0)
        ) else apply_kind(state, "draw_cards")
        if state["phase"] == "cards_discard":
            state = apply_kind(state, "discard_card")
        self.assertEqual(1, state["turn_count"])

        # Association is always available at sufficient strength; make strength 5 explicit.
        seat = state["active_seat"]
        assoc = next(card for card in state["players"][seat]["action_cards"] if card["action"] == "association")
        state["players"][seat]["x_tokens"] = max(0, 5 - assoc["strength"])
        state = apply_kind(state, "select_action", action_card="association", strength=5)
        state = apply_kind(state, "association_task", task="partner_zoo")
        self.assertEqual(2, state["turn_count"])

        # Build a pavilion using a controlled legal placement.
        seat = state["active_seat"]
        build = next(card for card in state["players"][seat]["action_cards"] if card["action"] == "build")
        state["players"][seat]["x_tokens"] = max(0, 3 - build["strength"])
        state = apply_kind(state, "select_action", action_card="build", strength=max(3, build["strength"]))
        state = apply_kind(state, "place_building", building_type="pavilion")
        self.assertEqual(3, state["turn_count"])

        # Sponsors always offers the official Break/money alternative.
        state = apply_kind(state, "select_action", action_card="sponsors", x_tokens=0)
        self.assertEqual("sponsors_choose", state["phase"])
        state = apply_kind(state, "advance_break")
        self.assertEqual(4, state["turn_count"])

        # Put a controlled animal in the empty starting enclosure.
        seat = state["active_seat"]
        player = state["players"][seat]
        animal = next((card for card in player["hand"] if card["card_type"] == "animal"
                       and card["enclosure_size"] <= 3 and card["cost"] <= player["money"]), None)
        if animal is None:
            animal = next(card for card in state["zoo_deck"] if card["card_type"] == "animal"
                          and card["enclosure_size"] <= 3)
            state["zoo_deck"].remove(animal)
            player["hand"].append(animal)
        state = apply_kind(state, "select_action", action_card="animals", x_tokens=0)
        state = apply_kind(state, "play_animal", card_id=animal["id"])
        player = state["players"][seat]
        self.assertTrue(player["map"]["buildings"][0]["occupied"])
        self.assertTrue(any(card["id"] == animal["id"] for card in player["played_cards"]))

    def test_break_discard_and_income_resolution(self):
        state = finish_initial_hands(ark_nova.new_game(2, 8, {"turn_limit": 20}))
        state["break_track"]["position"] = state["break_track"]["limit"] - 1
        starting_money = [player["money"] for player in state["players"]]
        state = apply_kind(state, "select_action", action_card="sponsors", x_tokens=0)
        state = apply_kind(state, "advance_break")
        while state["phase"] == "break_discard":
            state = apply_kind(state, "break_discard")
        self.assertEqual(0, state["break_track"]["position"])
        self.assertEqual("choose_action", state["phase"])
        self.assertTrue(all(len(player["hand"]) <= 3 for player in state["players"]))
        self.assertTrue(all(player["money"] > starting_money[player["seat"]] for player in state["players"]))

    def test_conservation_milestone_inserts_action_upgrade_before_next_turn(self):
        state = finish_initial_hands(ark_nova.new_game(2, 22, {"turn_limit": 20}))
        player = state["players"][0]
        project = state["base_conservation_projects"][0]
        project.update({"tag": "bird", "project_kind": "tag"})
        sources = [card for card in state["zoo_deck"] if card.get("card_type") == "animal"][:2]
        for card in sources:
            state["zoo_deck"].remove(card)
            card["tags"] = ["bird"]
            player["played_cards"].append(card)
        association = next(card for card in player["action_cards"] if card["action"] == "association")
        player["x_tokens"] = max(0, 5 - association["strength"])
        state = apply_kind(state, "select_action", action_card="association", strength=5)
        state = apply_kind(state, "association_task", task="conservation_project", level=2)
        self.assertEqual("choose_action_upgrade", state["phase"])
        self.assertEqual(0, state["active_seat"])
        state, events = ark_nova.apply_action(
            state, 0, next(item["action"] for item in ark_nova.legal_actions(state, 0)
                           if item["action"]["type"] == "upgrade_action_card"),
        )
        self.assertEqual("action_card_upgraded", events[1]["type"])
        self.assertEqual(1, state["active_seat"])
        self.assertEqual("choose_action", state["phase"])

    def test_partner_zoo_discount_and_controlled_effect_primitives(self):
        state = finish_initial_hands(ark_nova.new_game(2, 24, {"turn_limit": 20}))
        player = state["players"][0]
        animal = next(card for card in state["zoo_deck"] if card["card_type"] == "animal"
                      and 2 <= card["enclosure_size"] <= 3)
        state["zoo_deck"].remove(animal)
        animal["effects"] = [{"type": "gain_money", "amount": 3}]
        player["hand"].append(animal)
        player["partner_zoos"].append(animal["continent"])
        starting_money = player["money"]
        state = apply_kind(state, "select_action", action_card="animals", x_tokens=0)
        action = next(item["action"] for item in ark_nova.legal_actions(state, 0)
                      if item["action"]["type"] == "play_animal" and item["action"]["card_id"] == animal["id"])
        self.assertEqual(max(0, animal["cost"] - 3), action["cost"])
        state, events = ark_nova.apply_action(state, 0, action)
        self.assertEqual(starting_money - action["cost"] + 3, state["players"][0]["money"])
        self.assertTrue(any(event["type"] == "effects_resolved" for event in events))

    def test_upgraded_association_can_make_a_donation(self):
        state = finish_initial_hands(ark_nova.new_game(2, 26, {"turn_limit": 20}))
        player = state["players"][0]
        next(card for card in player["action_cards"] if card["action"] == "association")["upgraded"] = True
        association = next(card for card in player["action_cards"] if card["action"] == "association")
        player["x_tokens"] = max(0, 2 - association["strength"])
        state = apply_kind(state, "select_action", action_card="association", strength=max(2, association["strength"]))
        state = apply_kind(state, "association_task", task="reputation")
        self.assertEqual("association_donation", state["phase"])
        money = state["players"][0]["money"]
        state = apply_kind(state, "make_donation")
        self.assertEqual(money - 2, state["players"][0]["money"])
        self.assertEqual(1, state["players"][0]["conservation"])
        self.assertEqual(1, len(state["association_board"]["donations"]))

    def test_release_project_returns_enclosure_and_removes_appeal(self):
        state = finish_initial_hands(ark_nova.new_game(2, 28, {"turn_limit": 20}))
        player = state["players"][0]
        animal = next(card for card in state["zoo_deck"] if card["card_type"] == "animal"
                      and card["enclosure_size"] <= 3)
        state["zoo_deck"].remove(animal)
        animal["enclosure_id"] = "starting-enclosure-3"
        player["played_cards"].append(animal)
        player["map"]["buildings"][0]["occupied"] = True
        player["appeal"] += animal["appeal"]
        project = next(card for card in state["zoo_deck"] if card["card_type"] == "conservation_project")
        state["zoo_deck"].remove(project)
        project.update({"project_kind": "release_animal", "levels": [2, 4, 5]})
        player["hand"].append(project)
        association = next(card for card in player["action_cards"] if card["action"] == "association")
        player["x_tokens"] = max(0, 5 - association["strength"])
        starting_appeal = player["appeal"]
        state = apply_kind(state, "select_action", action_card="association", strength=5)
        state = apply_kind(state, "association_task", task="release_animal", card_id=animal["id"])
        player = state["players"][0]
        self.assertFalse(player["map"]["buildings"][0]["occupied"])
        self.assertEqual(starting_appeal - animal["appeal"], player["appeal"])
        self.assertIn(project["id"], player["supported_projects"])
        self.assertTrue(any(card["id"] == animal["id"] for card in state["zoo_discard"]))

    def test_controlled_final_card_scoring_counts_only_one_unresolved_card(self):
        state = ark_nova.new_game(2, 30)
        player = state["players"][0]
        player["final_scoring_cards"] = [
            {"id": "f-a", "objective": "buildings", "per": 1, "points_per_step": 2,
             "maximum": 8, "implementation": "controlled_final_scoring"},
            {"id": "f-b", "objective": "animals", "per": 1, "points_per_step": 2,
             "maximum": 8, "implementation": "controlled_final_scoring"},
        ]
        player["final_card_choice_resolved"] = False
        row = next(row for row in ark_nova.rankings(state) if row["seat"] == 0)
        self.assertEqual(2, row["final_card_points"])

    def test_upgraded_animals_can_play_from_reputation_range(self):
        state = finish_initial_hands(ark_nova.new_game(2, 32, {"turn_limit": 20}))
        player = state["players"][0]
        next(card for card in player["action_cards"] if card["action"] == "animals")["upgraded"] = True
        player["reputation"] = 4
        animal = next(card for card in state["zoo_deck"] if card["card_type"] == "animal"
                      and card["enclosure_size"] <= 3)
        state["zoo_deck"].remove(animal)
        displaced = state["card_display"][0]
        state["card_display"][0] = animal
        state["zoo_deck"].append(displaced)
        state = apply_kind(state, "select_action", action_card="animals", x_tokens=0)
        action = next(item["action"] for item in ark_nova.legal_actions(state, 0)
                      if item["action"].get("source") == "display" and item["action"]["card_id"] == animal["id"])
        state, _ = ark_nova.apply_action(state, 0, action)
        self.assertTrue(any(card["id"] == animal["id"] for card in state["players"][0]["played_cards"]))

    def test_upgraded_build_offers_special_enclosures(self):
        state = finish_initial_hands(ark_nova.new_game(2, 34, {"turn_limit": 20}))
        player = state["players"][0]
        next(card for card in player["action_cards"] if card["action"] == "build")["upgraded"] = True
        build = next(card for card in player["action_cards"] if card["action"] == "build")
        player["x_tokens"] = max(0, 5 - build["strength"])
        state = apply_kind(state, "select_action", action_card="build", strength=max(5, build["strength"]))
        kinds = {item["action"].get("building_type") for item in ark_nova.legal_actions(state, 0)}
        self.assertTrue({"petting_zoo", "reptile_house", "large_bird_aviary"} <= kinds)

    def test_upgraded_sponsors_can_play_from_reputation_range(self):
        state = finish_initial_hands(ark_nova.new_game(2, 36, {"turn_limit": 20}))
        player = state["players"][0]
        next(card for card in player["action_cards"] if card["action"] == "sponsors")["upgraded"] = True
        player["reputation"] = 4
        sponsor = next(card for card in state["zoo_deck"] if card["card_type"] == "sponsor"
                       and card["level"] <= 5)
        state["zoo_deck"].remove(sponsor)
        displaced = state["card_display"][0]
        state["card_display"][0] = sponsor
        state["zoo_deck"].append(displaced)
        sponsors = next(card for card in player["action_cards"] if card["action"] == "sponsors")
        player["x_tokens"] = max(0, sponsor["level"] - sponsors["strength"])
        state = apply_kind(state, "select_action", action_card="sponsors",
                           strength=max(sponsor["level"], sponsors["strength"]))
        state = apply_kind(state, "play_sponsor", source="display", card_id=sponsor["id"])
        self.assertTrue(any(card["id"] == sponsor["id"] for card in state["players"][0]["played_cards"]))

    def test_conservation_five_offers_money_or_bonus_tile(self):
        state = finish_initial_hands(ark_nova.new_game(2, 38, {"turn_limit": 20}))
        player = state["players"][0]
        player["conservation"] = 4
        player["conservation_tokens_on_map"] = 7
        next(card for card in player["action_cards"] if card["action"] == "association")["upgraded"] = True
        association = next(card for card in player["action_cards"] if card["action"] == "association")
        player["x_tokens"] = max(0, 2 - association["strength"])
        state = apply_kind(state, "select_action", action_card="association",
                           strength=max(2, association["strength"]))
        state = apply_kind(state, "association_task", task="reputation")
        state = apply_kind(state, "make_donation")
        self.assertEqual("choose_conservation_bonus", state["phase"])
        actions = [item["action"] for item in ark_nova.legal_actions(state, 0)]
        self.assertTrue(any(action["choice"] == "money" for action in actions))
        self.assertTrue(any(action["choice"] == "bonus_tile" for action in actions))

    def test_upgraded_association_supports_multiple_distinct_tasks(self):
        state = finish_initial_hands(ark_nova.new_game(2, 40, {"turn_limit": 20}))
        player = state["players"][0]
        card = next(card for card in player["action_cards"] if card["action"] == "association")
        card["upgraded"] = True
        player["association_workers"]["active"] = 2
        player["association_workers"]["reserve"] = 2
        player["x_tokens"] = max(0, 5 - card["strength"])
        state = apply_kind(state, "select_action", action_card="association", strength=5)
        state = apply_kind(state, "association_task", task="reputation")
        self.assertEqual("association_task", state["phase"])
        tasks = {item["action"].get("task") for item in ark_nova.legal_actions(state, 0)}
        self.assertIn("partner_zoo", tasks)
        self.assertNotIn("reputation", tasks)

    def test_upgraded_sponsors_can_play_multiple_cards_by_level_budget(self):
        state = finish_initial_hands(ark_nova.new_game(2, 42, {"turn_limit": 20}))
        player = state["players"][0]
        action_card = next(card for card in player["action_cards"] if card["action"] == "sponsors")
        action_card["upgraded"] = True
        sponsors = [card for card in state["zoo_deck"] if card["card_type"] == "sponsor"
                    and card["level"] <= 2][:2]
        for card in sponsors:
            state["zoo_deck"].remove(card)
            player["hand"].append(card)
        player["x_tokens"] = max(0, 4 - action_card["strength"])
        state = apply_kind(state, "select_action", action_card="sponsors",
                           strength=max(4, action_card["strength"]))
        state = apply_kind(state, "play_sponsor", card_id=sponsors[0]["id"])
        self.assertEqual("sponsors_choose", state["phase"])
        self.assertTrue(any(item["action"].get("card_id") == sponsors[1]["id"]
                            for item in ark_nova.legal_actions(state, 0)))

    def test_random_legal_agents_finish_many_seeded_matches(self):
        for seed in range(40):
            state = ark_nova.new_game(2 + seed % 3, seed, {"turn_limit": 18 + seed % 5})
            rng = random.Random(seed)
            decisions = 0
            while state["status"] == "active":
                legal = ark_nova.legal_actions(state, state["active_seat"])
                self.assertTrue(legal, (seed, state["phase"], state["turn_count"]))
                state, _ = ark_nova.apply_action(state, state["active_seat"], rng.choice(legal)["action"])
                decisions += 1
                self.assertLess(decisions, 1000)
            ark_nova.validate_state(state)
            self.assertTrue(ark_nova.rankings(state)[0]["rank"] == 1)

    def test_card_and_map_invariants_detect_corruption(self):
        state = ark_nova.new_game(4, 9)
        broken = copy.deepcopy(state)
        broken["card_display"][0] = broken["players"][0]["initial_draw"][0]
        with self.assertRaisesRegex(AssertionError, "212 unique zoo cards"):
            ark_nova.validate_state(broken)
        broken = copy.deepcopy(state)
        broken["players"][0]["map"]["buildings"].append(copy.deepcopy(
            broken["players"][0]["map"]["buildings"][0]
        ))
        with self.assertRaisesRegex(AssertionError, "overlap"):
            ark_nova.validate_state(broken)


if __name__ == "__main__":
    unittest.main()
