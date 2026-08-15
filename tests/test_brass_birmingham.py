import json
import random
import unittest

from agentbga import brass_birmingham as brass


class BrassBirminghamFoundationTests(unittest.TestCase):
    def test_setup_is_deterministic_and_models_two_action_turns(self):
        first = brass.new_game(3, 42)
        second = brass.new_game(3, 42)
        self.assertEqual(first, second)
        self.assertEqual(brass.state_hash(first), brass.state_hash(second))
        self.assertEqual("canal", first["era"])
        self.assertEqual(1, first["turn"]["actions_total"])
        self.assertEqual(8, len(first["players"][0]["hand"]))
        self.assertEqual(1, len(first["players"][0]["discard"]))
        self.assertFalse(first["players"][0]["discard"][0]["face_up"])
        self.assertEqual(45, sum(len(stack) for stack in first["players"][0]["industry_stacks"].values()))
        self.assertEqual(4, len(first["board"]["merchant_locations"]))
        brass.validate_state(first)

    def test_observation_hides_opponent_hand_but_exposes_counts_and_economy(self):
        state = brass.new_game(2, 7)
        private_id = state["players"][1]["hand"][0]["id"]
        facedown_id = state["players"][0]["discard"][0]["id"]
        observation = brass.observe(state, 0)
        self.assertEqual(8, observation["players"][1]["hand_count"])
        self.assertEqual([{"hidden": True}] * 8, observation["players"][1]["hand"])
        self.assertNotIn(private_id, json.dumps(observation, sort_keys=True))
        self.assertNotIn(facedown_id, json.dumps(observation, sort_keys=True))
        self.assertEqual(state["players"][0]["hand"], observation["players"][0]["hand"])
        self.assertEqual(17, observation["players"][1]["money"])

    def test_pass_consumes_a_card_and_first_round_uses_stable_spending_order(self):
        state = brass.new_game(2, 11)
        first_seat, second_seat = state["turn_order"]
        state["players"][first_seat]["spent_this_round"] = 7
        state["players"][second_seat]["spent_this_round"] = 2

        select = next(item["action"] for item in brass.legal_actions(state, first_seat)
                      if item["action"] == {"type": "select_action", "action": "pass"})
        state, _ = brass.apply_action(state, first_seat, select)
        action = brass.legal_actions(state, first_seat)[0]["action"]
        state, events = brass.apply_action(state, first_seat, action)
        self.assertEqual("action_accepted", events[0]["type"])
        self.assertEqual(second_seat, state["active_seat"])
        self.assertEqual(8, len(state["players"][first_seat]["hand"]))
        self.assertTrue(state["players"][first_seat]["discard"][-1]["face_up"])

        select = next(item["action"] for item in brass.legal_actions(state, second_seat)
                      if item["action"] == {"type": "select_action", "action": "pass"})
        state, _ = brass.apply_action(state, second_seat, select)
        action = brass.legal_actions(state, second_seat)[0]["action"]
        state, events = brass.apply_action(state, second_seat, action)
        self.assertEqual([second_seat, first_seat], state["turn_order"])
        self.assertEqual(2, state["round"])
        self.assertEqual(2, state["turn"]["actions_total"])
        self.assertTrue(any(event["type"] == "round_order_determined" for event in events))
        self.assertEqual(17, state["players"][first_seat]["money"])
        brass.validate_state(state)

    def test_official_setup_counts_vary_by_player_count(self):
        expected = {2: (40, 3), 3: (54, 4), 4: (64, 5)}
        for players, (card_count, merchants) in expected.items():
            with self.subTest(players=players):
                state = brass.new_game(players, 3)
                zones = len(state["draw_deck"]) + sum(
                    len(player["hand"]) + len(player["discard"]) for player in state["players"]
                )
                self.assertEqual(card_count, zones)
                self.assertEqual(merchants, len(state["board"]["merchant_locations"]))
                self.assertEqual({2: 5, 3: 7, 4: 9}[players], sum(
                    len(merchant["slots"]) for merchant in state["board"]["merchant_locations"]
                ))
                self.assertEqual(13, sum(state["markets"]["coal"]["occupied"]))
                self.assertEqual(8, sum(state["markets"]["iron"]["occupied"]))

    def test_industry_tiles_and_city_slots_use_verified_board_data(self):
        state = brass.new_game(2, 5)
        tiles = state["players"][0]["industry_stacks"]
        self.assertEqual((1, 12, 5), (
            tiles["cotton_mill"][0]["level"],
            tiles["cotton_mill"][0]["money_cost"],
            tiles["cotton_mill"][0]["vp"],
        ))
        self.assertFalse(tiles["pottery"][0]["developable"])
        self.assertEqual(2, tiles["brewery"][-1]["production"]["rail"])
        self.assertEqual(14, len(state["markets"]["coal"]["prices"]))
        birmingham = next(location for location in state["board"]["locations"]
                          if location["id"] == "birmingham")
        self.assertEqual(4, len(birmingham["industry_slots"]))
        self.assertEqual(["iron_works"], birmingham["industry_slots"][2]["accepts"])
        self.assertEqual(["canal", "rail"], tiles["pottery"][0]["allowed_eras"])

    def test_industry_card_can_open_any_matching_location_when_player_has_no_board_tiles(self):
        state = brass.new_game(2, 101)
        seat = state["active_seat"]
        placements = brass._build_placements(
            state, seat, {"card_type": "industry", "industries": ["brewery"]},
        )
        self.assertTrue(placements)
        self.assertIn("farm_brewery_cannock", {
            action["location_id"] for action in placements
        })

    def test_build_prefers_an_empty_single_icon_slot_over_a_dual_icon_slot(self):
        state = brass.new_game(2, 103)
        seat = state["active_seat"]
        connection = next(
            space for space in state["board"]["connection_spaces"]
            if space["endpoints"] == ["stoke_on_trent", "warrington"]
        )
        state["board"]["links"].append({
            "id": "stoke-market-link", "connection_id": connection["id"],
            "owner": seat, "era": "canal",
        })
        placements = [
            action for action in brass._build_placements(
                state, seat,
                {"card_type": "location", "location": "stoke_on_trent"},
            )
            if action["industry"] == "manufacturer"
        ]
        self.assertEqual(["stoke_on_trent-slot-3"], [
            action["slot_id"] for action in placements
        ])

    def test_empty_player_count_merchant_space_still_connects_to_coal_market_and_scores(self):
        state = brass.new_game(2, 107)
        seat = state["active_seat"]
        self.assertNotIn("warrington", {
            merchant["id"] for merchant in state["board"]["merchant_locations"]
        })
        connection = next(
            space for space in state["board"]["connection_spaces"]
            if space["endpoints"] == ["stoke_on_trent", "warrington"]
        )
        state["board"]["links"].append({
            "id": "warrington-coal-link", "connection_id": connection["id"],
            "owner": seat, "era": "canal",
        })
        sources = brass._coal_source_actions_for_nodes(
            state, ["stoke_on_trent"], state["players"][seat]["money"],
        )
        self.assertEqual("market", sources[0]["source"])

        brass._score_era(state, [])
        self.assertEqual(2, state["players"][seat]["vp"])

    def test_double_rail_opponent_beer_must_connect_to_second_link(self):
        state = brass.new_game(2, 109)
        seat = state["active_seat"]
        opponent = 1 - seat
        tile = state["players"][opponent]["industry_stacks"]["brewery"].pop(0)
        brewery = dict(tile)
        brewery.update({
            "id": f"seat-{opponent}-{tile['id']}", "tile_id": tile["id"],
            "owner": opponent, "location": "stoke_on_trent",
            "slot_id": "stoke-on-trent-test-slot", "state": "board",
            "resources": 1, "flipped": False,
        })
        state["board"]["industries"].append(brewery)
        connections = {
            tuple(space["endpoints"]): space["id"]
            for space in state["board"]["connection_spaces"]
        }
        pending = {
            "links_total": 2,
            "links": [
                {"connection_id": connections[("stoke_on_trent", "warrington")]},
                {"connection_id": connections[("birmingham", "coventry")]},
            ],
            "total_cost": 15,
        }
        self.assertEqual([], brass._network_beer_source_actions(state, seat, pending))
        brewery["owner"] = seat
        self.assertEqual(brewery["id"], brass._network_beer_source_actions(
            state, seat, pending,
        )[0]["source_id"])

    def test_develop_cannot_remove_restricted_pottery_tile(self):
        state = brass.new_game(2, 6)
        seat = state["active_seat"]
        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "develop")
        state, _ = brass.apply_action(state, seat, select)
        state, _ = brass.apply_action(state, seat, brass.legal_actions(state, seat)[0]["action"])
        choices = brass.legal_actions(state, seat)
        self.assertFalse(any("pottery" in item["action"]["industries"] for item in choices))

    def test_develop_must_use_board_iron_and_flips_depleted_works(self):
        state = brass.new_game(2, 67)
        seat = state["active_seat"]
        owner = 1 - seat
        tile = state["players"][owner]["industry_stacks"]["iron_works"].pop(0)
        works = dict(tile)
        works.update({
            "id": f"seat-{owner}-{tile['id']}", "tile_id": tile["id"], "owner": owner,
            "location": "coalbrookdale", "slot_id": "coalbrookdale-slot-2",
            "state": "board", "resources": 1, "flipped": False,
        })
        state["board"]["industries"].append(works)
        location = next(row for row in state["board"]["locations"]
                        if row["id"] == "coalbrookdale")
        location["industry_slots"][1]["industry_id"] = works["id"]
        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "develop")
        state, _ = brass.apply_action(state, seat, select)
        state, _ = brass.apply_action(state, seat, brass.legal_actions(state, seat)[0]["action"])
        choice = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"]["industries"] == ["coal_mine"])
        state, _ = brass.apply_action(state, seat, choice)
        source = brass.legal_actions(state, seat)[0]["action"]
        self.assertEqual(("industry", works["id"]), (source["source"], source["source_id"]))
        state, _ = brass.apply_action(state, seat, source)
        depleted = next(row for row in state["board"]["industries"]
                        if row["id"] == works["id"])
        self.assertTrue(depleted["flipped"])
        self.assertEqual(13, state["players"][owner]["income_position"])
        self.assertEqual(17, state["players"][seat]["money"])

    def test_loan_is_a_two_decision_action_and_lowers_income(self):
        state = brass.new_game(2, 17)
        seat = state["active_seat"]
        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "loan")
        state, _ = brass.apply_action(state, seat, select)
        self.assertEqual("choose_discard_card", state["phase"])
        state, events = brass.apply_action(state, seat, brass.legal_actions(state, seat)[0]["action"])
        self.assertEqual(47, state["players"][seat]["money"])
        self.assertEqual(7, state["players"][seat]["income_position"])
        self.assertTrue(any(event["type"] == "loan_taken" for event in events))

    def test_scout_discards_three_cards_and_moves_both_wilds(self):
        state = brass.new_game(2, 19)
        seat = state["active_seat"]
        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "scout")
        state, _ = brass.apply_action(state, seat, select)
        state, _ = brass.apply_action(state, seat, brass.legal_actions(state, seat)[0]["action"])
        self.assertEqual("scout_choose_extra_cards", state["phase"])
        state, events = brass.apply_action(state, seat, brass.legal_actions(state, seat)[0]["action"])
        self.assertEqual({"location": 1, "industry": 1}, state["players"][seat]["wild_cards"])
        self.assertEqual({"location": 3, "industry": 3}, state["wild_cards"])
        self.assertEqual(4, len(state["players"][seat]["discard"]))
        self.assertTrue(any(event["type"] == "wild_cards_scouted" for event in events))

    def test_develop_removes_lowest_tiles_and_buys_iron_from_market(self):
        state = brass.new_game(2, 23)
        seat = state["active_seat"]
        first_tile = state["players"][seat]["industry_stacks"]["coal_mine"][0]["id"]
        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "develop")
        state, _ = brass.apply_action(state, seat, select)
        state, _ = brass.apply_action(state, seat, brass.legal_actions(state, seat)[0]["action"])
        choice = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"]["industries"] == ["coal_mine"])
        state, _ = brass.apply_action(state, seat, choice)
        self.assertEqual("develop_choose_iron_source", state["phase"])
        source = brass.legal_actions(state, seat)[0]["action"]
        self.assertEqual(("market", 2), (source["source"], source["cost"]))
        state, events = brass.apply_action(state, seat, source)
        self.assertNotEqual(
            first_tile, state["players"][seat]["industry_stacks"]["coal_mine"][0]["id"],
        )
        self.assertEqual(15, state["players"][seat]["money"])
        self.assertEqual(2, state["players"][seat]["spent_this_round"])
        self.assertTrue(any(event["type"] == "industries_developed" for event in events))

    def test_first_network_action_can_use_any_open_canal_then_costs_three(self):
        state = brass.new_game(2, 29)
        seat = state["active_seat"]
        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "network")
        state, _ = brass.apply_action(state, seat, select)
        state, _ = brass.apply_action(state, seat, brass.legal_actions(state, seat)[0]["action"])
        links = brass.legal_actions(state, seat)
        self.assertEqual(
            sum("canal" in eras for _endpoints, eras in brass.CONNECTION_DATA), len(links),
        )
        self.assertFalse(any(item["action"]["connection_id"] == "connection-02"
                             for item in links))
        state, events = brass.apply_action(state, seat, links[0]["action"])
        self.assertEqual(14, state["players"][seat]["money"])
        self.assertEqual(3, state["players"][seat]["spent_this_round"])
        self.assertEqual(13, state["players"][seat]["links_remaining"])
        self.assertEqual(seat, state["board"]["links"][0]["owner"])
        self.assertTrue(any(event["type"] == "network_link_built" for event in events))

    def test_build_uses_card_permission_city_slot_and_lowest_tile(self):
        state = brass.new_game(2, 37)
        seat = state["active_seat"]
        card = state["players"][seat]["hand"][0]
        card.clear()
        card.update({
            "id": "test-birmingham", "card_type": "location", "location": "birmingham",
        })
        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "build")
        state, _ = brass.apply_action(state, seat, select)
        discard = next(item["action"] for item in brass.legal_actions(state, seat)
                       if item["action"].get("card_id") == "test-birmingham")
        state, _ = brass.apply_action(state, seat, discard)
        placements = brass.legal_actions(state, seat)
        cotton = next(item["action"] for item in placements
                      if item["action"]["industry"] == "cotton_mill")
        state, events = brass.apply_action(state, seat, cotton)
        built = state["board"]["industries"][0]
        self.assertEqual(("cotton_mill-01", "birmingham", 0), (
            built["tile_id"], built["location"], built["resources"],
        ))
        self.assertEqual(5, state["players"][seat]["money"])
        self.assertEqual(12, state["players"][seat]["spent_this_round"])
        self.assertTrue(any(event["type"] == "industry_built" for event in events))

    def test_industry_card_is_available_for_the_no_tiles_opening_exception(self):
        state = brass.new_game(2, 41)
        seat = state["active_seat"]
        card = state["players"][seat]["hand"][0]
        card.clear()
        card.update({
            "id": "test-cotton", "card_type": "industry", "industry": "cotton_mill",
        })
        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "build")
        state, _ = brass.apply_action(state, seat, select)
        self.assertTrue(any(item["action"].get("card_id") == "test-cotton"
                            for item in brass.legal_actions(state, seat)))

    def test_build_can_overbuild_own_lower_level_matching_industry(self):
        state = brass.new_game(2, 73)
        seat = state["active_seat"]
        player = state["players"][seat]
        old_tile = player["industry_stacks"]["coal_mine"].pop(0)
        old = dict(old_tile)
        old.update({
            "id": f"seat-{seat}-{old_tile['id']}", "tile_id": old_tile["id"],
            "owner": seat, "location": "coventry", "slot_id": "coventry-slot-2",
            "state": "board", "resources": 2, "flipped": False,
        })
        state["board"]["industries"].append(old)
        location = next(row for row in state["board"]["locations"]
                        if row["id"] == "coventry")
        location["industry_slots"][1]["industry_id"] = old["id"]
        card = player["hand"][0]
        card.clear()
        card.update({"id": "overbuild-coventry", "card_type": "location", "location": "coventry"})
        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "build")
        state, _ = brass.apply_action(state, seat, select)
        discard = next(item["action"] for item in brass.legal_actions(state, seat)
                       if item["action"].get("card_id") == "overbuild-coventry")
        state, _ = brass.apply_action(state, seat, discard)
        placement = next(item["action"] for item in brass.legal_actions(state, seat)
                         if item["action"].get("overbuild_industry_id") == old["id"])
        state, events = brass.apply_action(state, seat, placement)
        replacement = next(row for row in state["board"]["industries"]
                           if row["location"] == "coventry")
        self.assertEqual((2, "coal_mine-02"), (replacement["level"], replacement["tile_id"]))
        self.assertTrue(any(row["id"] == old["id"]
                            for row in state["players"][seat]["removed_industries"]))
        self.assertTrue(any(event["type"] == "industry_overbuilt" for event in events))

    def test_build_resolves_iron_as_a_separate_market_source_decision(self):
        state = brass.new_game(2, 43)
        seat = state["active_seat"]
        card = state["players"][seat]["hand"][0]
        card.clear()
        card.update({"id": "test-derby", "card_type": "location", "location": "derby"})
        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "build")
        state, _ = brass.apply_action(state, seat, select)
        discard = next(item["action"] for item in brass.legal_actions(state, seat)
                       if item["action"].get("card_id") == "test-derby")
        state, _ = brass.apply_action(state, seat, discard)
        brewery = next(item["action"] for item in brass.legal_actions(state, seat)
                       if item["action"]["industry"] == "brewery")
        state, _ = brass.apply_action(state, seat, brewery)
        self.assertEqual("build_choose_iron_source", state["phase"])
        source = brass.legal_actions(state, seat)[0]["action"]
        self.assertEqual(("market", 2), (source["source"], source["cost"]))
        state, events = brass.apply_action(state, seat, source)
        self.assertEqual(10, state["players"][seat]["money"])
        self.assertEqual(7, state["players"][seat]["spent_this_round"])
        self.assertEqual(7, sum(state["markets"]["iron"]["occupied"]))
        self.assertEqual(1, state["board"]["industries"][0]["resources"])
        self.assertTrue(any(event["type"] == "build_resource_consumed" for event in events))

    def test_income_position_is_not_mistaken_for_income_level(self):
        self.assertEqual(0, brass._income_level(10))
        self.assertEqual(1, brass._income_level(11))
        self.assertEqual(1, brass._income_level(12))
        self.assertEqual(11, brass._income_level(31))

    def test_final_tie_break_uses_income_level_then_money_not_track_position(self):
        state = brass.new_game(2, 113)
        state["players"][0].update({"vp": 20, "income_position": 11, "money": 8})
        state["players"][1].update({"vp": 20, "income_position": 12, "money": 7})
        rows = brass.rankings(state)
        self.assertEqual((0, 1), (rows[0]["seat"], rows[0]["rank"]))
        self.assertEqual((1, 2), (rows[1]["seat"], rows[1]["rank"]))
        self.assertEqual((1, 1), (rows[0]["income_level"], rows[1]["income_level"]))

    def test_negative_income_pauses_for_explicit_industry_liquidation(self):
        state = brass.new_game(2, 83)
        seat = state["turn_order"][0]
        player = state["players"][seat]
        player["income_position"] = 5  # income level -5
        player["money"] = 3
        tile = player["industry_stacks"]["coal_mine"].pop(0)
        industry = dict(tile)
        industry.update({
            "id": f"seat-{seat}-{tile['id']}", "tile_id": tile["id"], "owner": seat,
            "location": "coventry", "slot_id": "coventry-slot-2",
            "state": "board", "resources": 2, "flipped": False,
        })
        state["board"]["industries"].append(industry)
        location = next(row for row in state["board"]["locations"]
                        if row["id"] == "coventry")
        location["industry_slots"][1]["industry_id"] = industry["id"]
        state["pending_round_transition"] = {
            "final_round": False, "income_seats": list(state["turn_order"]),
            "income_index": 0,
        }
        events = []
        brass._resume_income_resolution(state, events)
        self.assertEqual((seat, "income_choose_liquidation"),
                         (state["active_seat"], state["phase"]))
        action = brass.legal_actions(state, seat)[0]["action"]
        self.assertEqual(2, action["value"])
        state, events = brass.apply_action(state, seat, action)
        self.assertEqual(0, state["players"][seat]["money"])
        self.assertFalse(any(row["id"] == industry["id"]
                             for row in state["board"]["industries"]))
        self.assertEqual("choose_action", state["phase"])
        self.assertTrue(any(event["type"] == "industry_liquidated" for event in events))

    def test_build_can_buy_coal_only_when_connected_to_a_merchant(self):
        state = brass.new_game(2, 47)
        seat = state["active_seat"]
        birmingham_oxford = next(
            space for space in state["board"]["connection_spaces"]
            if space["endpoints"] == ["birmingham", "oxford"]
        )
        state["board"]["links"].append({
            "id": "setup-link", "connection_id": birmingham_oxford["id"],
            "owner": seat, "era": "canal",
        })
        state["players"][seat]["links_remaining"] -= 1
        card = state["players"][seat]["hand"][0]
        card.clear()
        card.update({
            "id": "test-birmingham-coal", "card_type": "location", "location": "birmingham",
        })
        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "build")
        state, _ = brass.apply_action(state, seat, select)
        discard = next(item["action"] for item in brass.legal_actions(state, seat)
                       if item["action"].get("card_id") == "test-birmingham-coal")
        state, _ = brass.apply_action(state, seat, discard)
        manufacturer = next(item["action"] for item in brass.legal_actions(state, seat)
                            if item["action"]["industry"] == "manufacturer")
        state, _ = brass.apply_action(state, seat, manufacturer)
        self.assertEqual("build_choose_coal_source", state["phase"])
        source = brass.legal_actions(state, seat)[0]["action"]
        self.assertEqual(("market", 1), (source["source"], source["cost"]))
        state, _ = brass.apply_action(state, seat, source)
        self.assertEqual(8, state["players"][seat]["money"])
        self.assertEqual(9, state["players"][seat]["spent_this_round"])
        self.assertEqual(12, sum(state["markets"]["coal"]["occupied"]))

    def test_official_deck_contains_dual_industry_cards_at_three_players(self):
        deck = brass._card_deck(3)
        dual = [card for card in deck if card.get("industries") == [
            "cotton_mill", "manufacturer",
        ]]
        self.assertEqual(6, len(dual))

    def test_sell_uses_connected_merchant_beer_applies_bonus_and_flips_tile(self):
        state = brass.new_game(2, 53)
        seat = state["active_seat"]
        tile = state["players"][seat]["industry_stacks"]["cotton_mill"].pop(0)
        industry = dict(tile)
        industry.update({
            "id": f"seat-{seat}-{tile['id']}", "tile_id": tile["id"], "owner": seat,
            "location": "birmingham", "slot_id": "birmingham-slot-1",
            "state": "board", "resources": 0, "flipped": False,
        })
        state["board"]["industries"].append(industry)
        birmingham = next(location for location in state["board"]["locations"]
                          if location["id"] == "birmingham")
        birmingham["industry_slots"][0]["industry_id"] = industry["id"]
        connection = next(space for space in state["board"]["connection_spaces"]
                          if space["endpoints"] == ["birmingham", "oxford"])
        state["board"]["links"].append({
            "id": "sell-link", "connection_id": connection["id"],
            "owner": seat, "era": "canal",
        })
        state["players"][seat]["links_remaining"] -= 1
        oxford = next(merchant for merchant in state["board"]["merchant_locations"]
                      if merchant["id"] == "oxford")
        target_slot = oxford["slots"][0]
        donor = next(
            slot for merchant in state["board"]["merchant_locations"] for slot in merchant["slots"]
            if slot["buys"] in {"cotton_mill", "any"}
        )
        target_slot["buys"], donor["buys"] = donor["buys"], target_slot["buys"]
        target_slot["beer"] = 0 if target_slot["buys"] == "blank" else 1
        donor["beer"] = 0 if donor["buys"] == "blank" else 1

        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "sell")
        state, _ = brass.apply_action(state, seat, select)
        state, _ = brass.apply_action(state, seat, brass.legal_actions(state, seat)[0]["action"])
        sale = next(item["action"] for item in brass.legal_actions(state, seat)
                    if item["action"]["merchant_slot_id"] == target_slot["id"])
        state, _ = brass.apply_action(state, seat, sale)
        beer = next(item["action"] for item in brass.legal_actions(state, seat)
                    if item["action"]["source"] == "merchant")
        state, events = brass.apply_action(state, seat, beer)
        self.assertEqual("sell_continue", state["phase"])
        self.assertTrue(state["board"]["industries"][0]["flipped"])
        self.assertEqual(17, state["players"][seat]["income_position"])
        self.assertEqual(0, next(
            slot for merchant in state["board"]["merchant_locations"]
            for slot in merchant["slots"] if slot["id"] == beer["source_id"]
        )["beer"])
        self.assertTrue(any(event["type"] == "industry_sold" for event in events))

    def test_rail_network_selects_link_then_consumes_coal_before_building(self):
        state = brass.new_game(2, 59)
        seat = state["active_seat"]
        state["era"] = "rail"
        state["round"] = 1
        state["players"][seat]["removed_industries"].append(
            state["players"][seat]["industry_stacks"]["coal_mine"].pop(0)
        )
        tile = state["players"][seat]["industry_stacks"]["coal_mine"].pop(0)
        mine = dict(tile)
        mine.update({
            "id": f"seat-{seat}-{tile['id']}", "tile_id": tile["id"], "owner": seat,
            "location": "coventry", "slot_id": "coventry-slot-2",
            "state": "board", "resources": 3, "flipped": False,
        })
        state["board"]["industries"].append(mine)
        coventry = next(location for location in state["board"]["locations"]
                        if location["id"] == "coventry")
        coventry["industry_slots"][1]["industry_id"] = mine["id"]

        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "network")
        state, _ = brass.apply_action(state, seat, select)
        state, _ = brass.apply_action(state, seat, brass.legal_actions(state, seat)[0]["action"])
        self.assertEqual("network_choose_mode", state["phase"])
        one = next(item["action"] for item in brass.legal_actions(state, seat)
                   if item["action"]["count"] == 1)
        state, _ = brass.apply_action(state, seat, one)
        target = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"]["connection_id"] == "connection-03")
        state, _ = brass.apply_action(state, seat, target)
        self.assertEqual("network_choose_coal_source", state["phase"])
        coal = next(item["action"] for item in brass.legal_actions(state, seat)
                    if item["action"]["source_id"] == mine["id"])
        state, events = brass.apply_action(state, seat, coal)
        self.assertEqual(2, next(industry for industry in state["board"]["industries"]
                                 if industry["id"] == mine["id"])["resources"])
        built = next(link for link in state["board"]["links"]
                     if link["connection_id"] == "connection-03")
        self.assertEqual((seat, "rail"), (built["owner"], built["era"]))
        self.assertEqual(12, state["players"][seat]["money"])
        self.assertTrue(any(event["type"] == "rail_coal_consumed" for event in events))

    def test_double_rail_costs_fifteen_two_coal_and_brewery_beer(self):
        state = brass.new_game(2, 61)
        seat = state["active_seat"]
        state["era"] = "rail"
        state["round"] = 1
        player = state["players"][seat]
        player["removed_industries"].append(player["industry_stacks"]["coal_mine"].pop(0))
        coal_tile = player["industry_stacks"]["coal_mine"].pop(0)
        mine = dict(coal_tile)
        mine.update({
            "id": f"seat-{seat}-{coal_tile['id']}", "tile_id": coal_tile["id"],
            "owner": seat, "location": "coventry", "slot_id": "coventry-slot-2",
            "state": "board", "resources": 3, "flipped": False,
        })
        for _ in range(2):
            player["removed_industries"].append(player["industry_stacks"]["brewery"].pop(0))
        beer_tile = player["industry_stacks"]["brewery"].pop(0)
        brewery = dict(beer_tile)
        brewery.update({
            "id": f"seat-{seat}-{beer_tile['id']}", "tile_id": beer_tile["id"],
            "owner": seat, "location": "derby", "slot_id": "derby-slot-1",
            "state": "board", "resources": 2, "flipped": False,
        })
        state["board"]["industries"].extend([mine, brewery])
        for location_id, slot_index, industry_id in (
            ("coventry", 1, mine["id"]), ("derby", 0, brewery["id"]),
        ):
            location = next(row for row in state["board"]["locations"]
                            if row["id"] == location_id)
            location["industry_slots"][slot_index]["industry_id"] = industry_id

        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"].get("action") == "network")
        state, _ = brass.apply_action(state, seat, select)
        state, _ = brass.apply_action(state, seat, brass.legal_actions(state, seat)[0]["action"])
        two = next(item["action"] for item in brass.legal_actions(state, seat)
                   if item["action"]["count"] == 2)
        state, _ = brass.apply_action(state, seat, two)
        for connection_id in ("connection-03", "connection-04"):
            link = next(item["action"] for item in brass.legal_actions(state, seat)
                        if item["action"]["connection_id"] == connection_id)
            state, _ = brass.apply_action(state, seat, link)
            coal = next(item["action"] for item in brass.legal_actions(state, seat)
                        if item["action"]["source_id"] == mine["id"])
            state, _ = brass.apply_action(state, seat, coal)
        self.assertEqual("network_choose_beer_source", state["phase"])
        beer = next(item["action"] for item in brass.legal_actions(state, seat)
                    if item["action"]["source_id"] == brewery["id"])
        state, _ = brass.apply_action(state, seat, beer)
        self.assertEqual(2, state["players"][seat]["money"])
        self.assertEqual(12, state["players"][seat]["links_remaining"])
        self.assertEqual(1, next(row for row in state["board"]["industries"]
                                 if row["id"] == mine["id"])["resources"])
        self.assertEqual(1, next(row for row in state["board"]["industries"]
                                 if row["id"] == brewery["id"])["resources"])

    def test_era_scoring_counts_flipped_industry_and_adjacent_link_icons(self):
        state = brass.new_game(2, 71)
        seat = state["active_seat"]
        tile = state["players"][seat]["industry_stacks"]["cotton_mill"].pop(0)
        industry = dict(tile)
        industry.update({
            "id": f"seat-{seat}-{tile['id']}", "tile_id": tile["id"], "owner": seat,
            "location": "birmingham", "slot_id": "birmingham-slot-1",
            "state": "board", "resources": 0, "flipped": True,
        })
        state["board"]["industries"].append(industry)
        location = next(row for row in state["board"]["locations"]
                        if row["id"] == "birmingham")
        location["industry_slots"][0]["industry_id"] = industry["id"]
        connection = next(space for space in state["board"]["connection_spaces"]
                          if space["endpoints"] == ["birmingham", "oxford"])
        state["board"]["links"].append({
            "id": "score-link", "connection_id": connection["id"],
            "owner": seat, "era": "canal",
        })
        events = []
        brass._score_era(state, events)
        self.assertEqual(8, state["players"][seat]["vp"])
        score = next(event for event in events
                     if event["type"] == "era_scored" and event["seat"] == seat)
        self.assertEqual((5, 3), (score["industry_points"], score["link_points"]))

    def test_pass_only_match_transitions_to_rail_and_finishes_deterministically(self):
        state = brass.new_game(2, 31)
        saw_rail = False
        decisions = 0
        while state["status"] == "active":
            seat = state["active_seat"]
            legal = brass.legal_actions(state, seat)
            if state["phase"] == "choose_action":
                action = next(item["action"] for item in legal
                              if item["action"].get("action") == "pass")
            else:
                action = legal[0]["action"]
            state, _ = brass.apply_action(state, seat, action)
            decisions += 1
            saw_rail = saw_rail or state["era"] == "rail"
            self.assertLess(decisions, 300)
        self.assertTrue(saw_rail)
        self.assertEqual("rail", state["era"])
        self.assertEqual("finished", state["phase"])
        self.assertEqual([], brass.legal_actions(state, state["active_seat"]))
        self.assertEqual(10, state["round"])
        brass.validate_state(state)

    def test_player_with_one_remaining_card_does_not_get_a_second_action(self):
        state = brass.new_game(2, 79)
        seat = state["active_seat"]
        next_seat = next(candidate for candidate in state["turn_order"] if candidate != seat)
        state["era"] = "rail"
        state["round"] = 2
        state["turn"].update({"actions_total": 2, "actions_remaining": 2})
        for card in state["draw_deck"]:
            card["face_up"] = True
            state["players"][seat]["discard"].append(card)
        state["draw_deck"] = []
        for player in state["players"]:
            keep = player["hand"][:1]
            for card in player["hand"][1:]:
                card["face_up"] = True
                player["discard"].append(card)
            player["hand"] = keep
        select = next(item["action"] for item in brass.legal_actions(state, seat)
                      if item["action"] == {"type": "select_action", "action": "pass"})
        state, _ = brass.apply_action(state, seat, select)
        state, _ = brass.apply_action(state, seat, brass.legal_actions(state, seat)[0]["action"])
        self.assertEqual(next_seat, state["active_seat"])
        self.assertEqual(1, state["turn"]["actions_total"])

    def test_plugin_is_exposed_as_a_playable_beta(self):
        description = brass.describe()
        self.assertTrue(description["runnable"])
        self.assertEqual("playable_beta", description["implementation_status"])
        self.assertEqual(
            ["build", "network", "develop", "sell", "loan", "scout", "pass"],
            description["action_types"],
        )

    def test_random_legal_strategies_finish_without_empty_decision_steps(self):
        for players in (2, 3, 4):
            for seed in range(3):
                with self.subTest(players=players, seed=seed):
                    state = brass.new_game(players, seed)
                    rng = random.Random(seed + players * 1000 + 2026)
                    for _decision in range(750):
                        if state["status"] == "finished":
                            break
                        seat = state["active_seat"]
                        legal = brass.legal_actions(state, seat)
                        self.assertTrue(legal, (state["era"], state["round"], state["phase"]))
                        state, _ = brass.apply_action(
                            state, seat, rng.choice(legal)["action"],
                        )
                    self.assertEqual("finished", state["status"])
                    brass.validate_state(state)


if __name__ == "__main__":
    unittest.main()
