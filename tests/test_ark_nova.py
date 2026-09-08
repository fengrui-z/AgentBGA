import copy
import random
import unittest

from agentbga import ark_nova
from agentbga.ark_nova_map import building_shape_variants, valid_building_shape
from agentbga.ark_nova_tracks import (
    appeal_income,
    conservation_score_offset,
    conservation_target_appeal,
    reputation_display_slot,
    scoring_tracks_crossed,
)


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


def add_enclosure(player, size=3):
    """Add one legal controlled fixture enclosure to an otherwise empty Map 0."""

    player["money"] = max(player["money"], size * 2)
    action = next(
        action for action in ark_nova._build_actions(player, size, False)
        if action["building_type"] == "standard_enclosure" and action["size"] == size
    )
    building = {
        "id": f"fixture-enclosure-{len(player['map']['buildings']) + 1}",
        "type": "standard_enclosure", "size": size, "shape_id": action["shape_id"],
        "rotation": action["rotation"], "occupied": False, "cells": action["cells"],
    }
    player["map"]["buildings"].append(building)
    return building


class ArkNovaControlledCoreTests(unittest.TestCase):
    def test_map_zero_transcription_matches_reference_landmarks(self):
        map_data = ark_nova._map_zero()
        terrain = {(cell["q"], cell["r"]): cell["terrain"] for cell in map_data["cells"]}
        effects = {(slot["q"], slot["r"]): slot["effect"] for slot in map_data["placement_bonus_slots"]}
        expected_rows = {
            -4: (3, 4), -3: (1, 4), -2: (-1, 4), -1: (-3, 4), 0: (-4, 4),
            1: (-4, 4), 2: (-4, 3), 3: (-4, 1), 4: (-4, -1), 5: (-4, -3),
        }
        self.assertEqual({
            (q, r) for r, (minimum, maximum) in expected_rows.items()
            for q in range(minimum, maximum + 1)
        }, set(terrain))
        self.assertEqual(58, len(terrain))
        self.assertEqual({
            (-3, -1), (-4, 0), (-4, 1), (-1, -2), (1, -1),
            (-2, 2), (-3, 4), (4, 0), (4, 1), (3, 2),
        }, {coordinate for coordinate, value in terrain.items() if value == "water"})
        self.assertEqual({
            (-2, -1), (-1, -1), (2, -2), (1, 1), (2, 1),
            (2, 2), (1, 3), (-4, 5), (-3, 5),
        }, {coordinate for coordinate, value in terrain.items() if value == "rock"})
        self.assertEqual(39, sum(value == "buildable" for value in terrain.values()))
        self.assertEqual({"type": "gain_money", "amount": 10}, effects[(0, 0)])
        self.assertEqual({"type": "gain_money", "amount": 5}, effects[(3, -3)])
        self.assertNotIn((3, -2), effects)
        self.assertEqual({"type": "clever", "target_strength": 1}, effects[(1, 0)])
        self.assertEqual({(-3, 0), (-2, 1), (-1, 4)}, {
            coordinate for coordinate, effect in effects.items() if effect["type"] == "take_card"
        })
        self.assertEqual({(3, -2), (2, -1)}, {
            (cell["q"], cell["r"]) for cell in map_data["cells"]
            if cell.get("requires_build_upgrade", False)
        })

    def test_build_ii_cells_require_upgraded_build_action(self):
        state = finish_initial_hands(ark_nova.new_game(2, 100, {"turn_limit": 20}))
        player = state["players"][0]
        player["money"] = 100
        restricted = {(3, -2), (2, -1)}
        regular = ark_nova._build_actions(player, 5, False)
        upgraded = ark_nova._build_actions(player, 5, True)
        self.assertFalse(any(
            restricted & {(cell["q"], cell["r"]) for cell in action["cells"]}
            for action in regular
        ))
        self.assertTrue(any(
            restricted & {(cell["q"], cell["r"]) for cell in action["cells"]}
            for action in upgraded
        ))

    def test_map_take_card_and_clever_are_explicit_decisions(self):
        state = finish_initial_hands(ark_nova.new_game(2, 102, {"turn_limit": 20}))
        player = state["players"][0]
        events = []
        ark_nova._resolve_map_bonuses(state, player, [{"q": -3, "r": 0}], events)
        state["pending_rewards"][0]["resume_seat"] = 1
        ark_nova._begin_pending_reward(state)
        self.assertEqual("choose_map_card", state["phase"])
        actions = ark_nova.legal_actions(state, 0)
        self.assertEqual(2, len(actions))  # deck plus display slot 1 at starting reputation one
        before = len(state["players"][0]["hand"])
        state, events = ark_nova.apply_action(state, 0, actions[0]["action"])
        self.assertEqual(before + 1, len(state["players"][0]["hand"]))
        self.assertTrue(any(event["type"] == "map_card_taken" for event in events))

        state = finish_initial_hands(ark_nova.new_game(2, 103, {"turn_limit": 20}))
        player = state["players"][0]
        events = []
        ark_nova._resolve_map_bonuses(state, player, [{"q": 1, "r": 0}], events)
        state["pending_rewards"][0]["resume_seat"] = 1
        ark_nova._begin_pending_reward(state)
        self.assertEqual("choose_clever_action", state["phase"])
        strongest = next(card for card in player["action_cards"] if card["strength"] == 5)["action"]
        state = apply_kind(state, "clever_action_card", action_card=strongest)
        self.assertEqual(1, next(
            card["strength"] for card in state["players"][0]["action_cards"]
            if card["action"] == strongest
        ))

    def test_first_building_touches_map_border_then_later_buildings_touch_a_building(self):
        state = finish_initial_hands(ark_nova.new_game(2, 104, {"turn_limit": 20}))
        player = state["players"][0]
        player["money"] = 100
        coordinates = {(cell["q"], cell["r"]) for cell in player["map"]["cells"]}
        border = {
            coordinate for coordinate in coordinates
            if any(neighbor not in coordinates for neighbor in ark_nova._neighbors(coordinate))
        }
        actions = ark_nova._build_actions(player, 5, False)
        self.assertTrue(actions)
        self.assertTrue(all(
            border & {(cell["q"], cell["r"]) for cell in action["cells"]}
            for action in actions
        ))
        chosen = next(action for action in actions if action["building_type"] == "standard_enclosure")
        player["map"]["buildings"].append({
            "id": "fixture-first", "type": chosen["building_type"], "size": chosen["size"],
            "shape_id": chosen["shape_id"], "rotation": chosen["rotation"],
            "occupied": False, "cells": chosen["cells"],
        })
        occupied = {(cell["q"], cell["r"]) for cell in chosen["cells"]}
        later = ark_nova._build_actions(player, 5, False)
        self.assertTrue(later)
        self.assertTrue(all(any(
            ark_nova._neighbors((cell["q"], cell["r"])) & occupied for cell in action["cells"]
        ) for action in later))

    def test_build_actions_use_fixed_polyhexes_with_explicit_rotations_and_anchors(self):
        state = finish_initial_hands(ark_nova.new_game(2, 101, {"turn_limit": 20}))
        player = state["players"][0]
        player["money"] = 100
        actions = ark_nova._build_actions(player, 5, True)
        self.assertTrue(actions)
        self.assertGreaterEqual(len(building_shape_variants("standard_enclosure", 5)), 3)
        self.assertGreaterEqual(len({
            action["rotation"] for action in actions
            if action["building_type"] == "standard_enclosure" and action["size"] == 5
        }), 3)
        for action in actions:
            self.assertIn("anchor", action)
            self.assertIn(action["anchor"], action["cells"])
            self.assertTrue(valid_building_shape({
                "type": action["building_type"], "size": action["size"],
                "cells": action["cells"],
            }))

    def test_special_enclosure_shapes_match_the_physical_tiles(self):
        reptile = set(building_shape_variants("reptile_house", 5)[0]["cells"])
        aviary = set(building_shape_variants("large_bird_aviary", 5)[0]["cells"])

        self.assertEqual({
            (0, 0), (-1, 0), (-1, 1), (1, -1), (1, 0),
        }, reptile)
        self.assertEqual({
            (0, 0), (-1, 0), (-1, 1), (1, -1), (0, 1),
        }, aviary)
        self.assertNotEqual(reptile, aviary)

        # Each physical tile has one central cell touching four other cells.
        # The reptile house is symmetric; the aviary extends one branch and
        # therefore has six distinct rotations rather than three.
        centre = (0, 0)
        self.assertEqual(4, len(ark_nova._neighbors(centre) & reptile))
        self.assertEqual(4, len(ark_nova._neighbors(centre) & aviary))
        self.assertEqual(3, len(building_shape_variants("reptile_house", 5)))
        self.assertEqual(6, len(building_shape_variants("large_bird_aviary", 5)))

    def test_old_special_enclosure_shapes_are_loadable_but_not_generated(self):
        legacy_shapes = {
            "reptile_house": {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1)},
            "large_bird_aviary": {(0, 0), (1, 0), (1, 1), (2, 1), (2, 2)},
        }
        for building_type, cells in legacy_shapes.items():
            self.assertTrue(valid_building_shape({
                "type": building_type,
                "size": 5,
                "cells": [{"q": q, "r": r} for q, r in cells],
            }))
            generated = {
                frozenset(variant["cells"])
                for variant in building_shape_variants(building_type, 5)
            }
            self.assertNotIn(frozenset(cells), generated)

    def test_anchor_preserving_rotations_include_reference_border_placements(self):
        state = ark_nova.new_game(2, 105)
        player = state["players"][0]
        player["money"] = 100
        actions = ark_nova._build_actions(player, 5, False)
        expected = (
            (3, {(-4, 2), (-3, 1), (-3, 2)}),
            (3, {(1, -3), (1, -2), (0, -2)}),
            (4, {(-4, 2), (-3, 1), (-4, 3), (-3, 2)}),
            (4, {(-1, 2), (-2, 3), (-1, 3), (-2, 4)}),
        )
        for size, footprint in expected:
            self.assertTrue(any(
                action["building_type"] == "standard_enclosure" and action["size"] == size
                and {(cell["q"], cell["r"]) for cell in action["cells"]} == footprint
                for action in actions
            ), (size, footprint))
        size_five = building_shape_variants("standard_enclosure", 5)[0]["cells"]
        self.assertEqual({(0, 0), (0, 1), (1, -1), (1, 0), (1, 1)}, set(size_five))

    def test_setup_is_deterministic_and_matches_map_zero_setup(self):
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
            self.assertEqual("map-0", player["map"]["id"])
            self.assertEqual([], player["map"]["buildings"])

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

        spectator = ark_nova.observe_spectator(state)
        self.assertEqual("spectator", spectator["viewer_mode"])
        for player in spectator["players"]:
            self.assertTrue(all("hidden" not in card for card in player["initial_draw"]))
            self.assertTrue(all("hidden" not in card for card in player["final_scoring_cards"]))
        # Creating the observer projection must not weaken the normal seat view.
        self.assertEqual(
            {"hidden": True}, ark_nova.observe(state, 0)["players"][1]["initial_draw"][0],
        )

    def test_third_partner_zoo_requires_upgraded_association_card(self):
        state = ark_nova.new_game(2, 71)
        player = state["players"][0]
        player["partner_zoos"] = ["africa", "europe"]
        actions = ark_nova._association_actions(state, player, 3)
        self.assertFalse(any(action["task"] == "partner_zoo" for action in actions))

        next(
            card for card in player["action_cards"] if card["action"] == "association"
        )["upgraded"] = True
        actions = ark_nova._association_actions(state, player, 3)
        self.assertTrue(any(action["task"] == "partner_zoo" for action in actions))

    def test_public_view_normalizes_tracks_assets_counters_and_map_rewards(self):
        state = ark_nova.new_game(2, 8)
        player = state["players"][0]
        self.assertEqual("agentbga.ark_nova.map.v3", player["map"]["schema_version"])
        self.assertEqual(58, len(player["map"]["cells"]))
        self.assertEqual("reference_transcribed_map_zero_geometry", player["map"]["geometry_status"])
        self.assertEqual([], player["map"]["buildings"])
        player["universities"].append("research-2")
        state["association_board"]["universities"]["research-2"] = 0
        reward_cell = next(cell for cell in player["map"]["cells"] if "placement_bonus" in cell)

        view = ark_nova.observe(state, 0)
        summary = view["players"][0]["public_summary"]
        self.assertEqual(
            view["players"][0]["appeal"] + conservation_score_offset(view["players"][0]["conservation"]),
            summary["tracks"]["current_score"],
        )
        self.assertEqual(2, summary["counters"]["animals"]["research"])
        self.assertEqual(113, view["public_tracks"]["appeal"]["maximum"])
        self.assertEqual(41, view["public_tracks"]["conservation"]["maximum"])
        shared = view["public_tracks"]["appeal_conservation"]
        self.assertEqual(114, shared["maximum"])
        self.assertEqual(113, shared["conservation_spaces"][0]["axis"])
        university = next(item for item in view["association_display"]["universities"] if item["id"] == "research-2")
        self.assertEqual([0], university["owners"])
        self.assertEqual([2, 5, 7, 10, 12], [
            slot["cost"] for slot in view["association_display"]["donation_slots"]
        ])
        self.assertTrue(all(
            slot["status"] == "available" for slot in view["association_display"]["donation_slots"]
        ))
        self.assertEqual("available", view["players"][0]["map_display"]["placement_rewards"][0]["status"])
        board = view["players"][0]["map_display"]["player_board"]
        self.assertEqual([4, 3, 2, 1], [slot["level"] for slot in board["partner_zoo_ladder"]])
        self.assertEqual([3, 2, 1], [slot["level"] for slot in board["university_ladder"]])
        self.assertEqual([1, 2, 3, 4, 5], [
            card["strength"] for card in summary["action_cards"]
        ])
        self.assertEqual(2, view["public_tracks"]["conservation"]["rewards"][0]["position"])
        reputation_track = view["public_tracks"]["reputation"]
        self.assertEqual(1, reputation_track["minimum"])
        self.assertEqual(13, reputation_track["display_access"][-1]["minimum_reputation"])
        self.assertEqual(15, reputation_track["display_access"][-1]["maximum_reputation"])
        self.assertTrue(reputation_track["display_access"][-1]["requires_cards_upgrade"])

        reward_cell.pop("placement_bonus")
        claimed_view = ark_nova.observe(state, 0)
        reward = next(
            item for item in claimed_view["players"][0]["map_display"]["placement_rewards"]
            if item["q"] == reward_cell["q"] and item["r"] == reward_cell["r"]
        )
        self.assertEqual("claimed", reward["status"])

    def test_completing_all_buildable_map_cells_claims_reward_once(self):
        state = ark_nova.new_game(2, 9)
        player = state["players"][0]
        occupied = {
            (cell["q"], cell["r"])
            for building in player["map"]["buildings"] for cell in building["cells"]
        }
        remaining = [
            cell for cell in player["map"]["cells"]
            if cell["terrain"] == "buildable" and (cell["q"], cell["r"]) not in occupied
        ]
        for index, cell in enumerate(remaining):
            player["map"]["buildings"].append({
                "id": f"coverage-{index}", "type": "standard_enclosure", "size": 1,
                "occupied": False, "cells": [{"q": cell["q"], "r": cell["r"]}],
            })
        before = player["appeal"]
        events = []
        ark_nova._resolve_map_bonuses(state, player, [], events)
        self.assertEqual(before + 7, player["appeal"])
        self.assertTrue(player["map"]["completion_reward_claimed"])
        self.assertTrue(any(event["type"] == "zoo_map_completed" for event in events))
        ark_nova._resolve_map_bonuses(state, player, [], events)
        self.assertEqual(before + 7, player["appeal"])
        coverage = ark_nova.observe(state, 0)["players"][0]["map_display"]["coverage"]
        self.assertTrue(coverage["complete"])
        self.assertEqual("claimed", coverage["status"])

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

    def test_unresolved_selected_action_can_be_cancelled_and_reselected(self):
        state = finish_initial_hands(ark_nova.new_game(2, 106, {"turn_limit": 20}))
        player = state["players"][0]
        player["x_tokens"] = 2
        state = apply_kind(state, "select_action", action_card="sponsors", x_tokens=1)
        self.assertEqual("sponsors_choose", state["phase"])
        self.assertEqual(1, state["players"][0]["x_tokens"])
        state = apply_kind(state, "cancel_action", action_card="sponsors")
        self.assertEqual("choose_action", state["phase"])
        self.assertEqual(2, state["players"][0]["x_tokens"])
        self.assertEqual(0, state["turn_count"])

        state = apply_kind(state, "select_action", action_card="cards", x_tokens=0)
        self.assertEqual(2, state["break_track"]["position"])
        state = apply_kind(state, "cancel_action", action_card="cards")
        self.assertEqual(0, state["break_track"]["position"])
        self.assertFalse(state["break_track"]["triggered"])

    def test_universities_apply_reputation_research_and_hand_limit_benefits(self):
        state = finish_initial_hands(ark_nova.new_game(2, 107, {"turn_limit": 20}))
        player = state["players"][0]
        association = next(card for card in player["action_cards"] if card["action"] == "association")
        player["x_tokens"] = max(0, 4 - association["strength"])
        state = apply_kind(state, "select_action", action_card="association",
                           strength=max(4, association["strength"]))
        state = apply_kind(state, "association_task", task="university",
                           university="research-reputation")
        player = state["players"][0]
        self.assertEqual(3, player["reputation"])
        self.assertEqual(1, ark_nova.observe(state, 0)["players"][0]["public_summary"]["counters"]["animals"]["research"])

        player["universities"].append("hand-limit-5")
        summary = ark_nova.observe(state, 0)["players"][0]["public_summary"]
        self.assertEqual(2, summary["counters"]["animals"]["research"])
        self.assertEqual(5, summary["resources"]["hand_limit"])

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
        enclosure = add_enclosure(player, 3)
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
        self.assertTrue(next(item for item in player["map"]["buildings"] if item["id"] == enclosure["id"])["occupied"])
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

    def test_shared_track_income_and_opposing_conservation_coordinates(self):
        self.assertEqual(5, appeal_income(0))
        self.assertEqual(11, appeal_income(7))
        self.assertEqual(21, appeal_income(34))
        self.assertEqual(21, appeal_income(35))
        self.assertEqual(22, appeal_income(36))
        self.assertEqual(25, appeal_income(51))
        self.assertEqual(26, appeal_income(52))
        self.assertEqual(26, appeal_income(55))
        self.assertEqual(27, appeal_income(59))
        self.assertEqual(27, appeal_income(60))
        self.assertEqual(28, appeal_income(61))
        self.assertEqual(35, appeal_income(100))
        self.assertEqual(36, appeal_income(101))
        self.assertEqual(37, appeal_income(108))
        self.assertEqual(38, appeal_income(111))
        self.assertEqual(-13, conservation_score_offset(0))
        self.assertEqual(-12, conservation_score_offset(1))
        self.assertEqual(-10, conservation_score_offset(2))
        self.assertEqual(6, conservation_score_offset(10))
        self.assertEqual(9, conservation_score_offset(11))
        self.assertEqual(99, conservation_score_offset(41))
        self.assertEqual(113, conservation_target_appeal(0))
        self.assertEqual(94, conservation_target_appeal(10))
        self.assertEqual(1, conservation_target_appeal(41))
        self.assertFalse(scoring_tracks_crossed(93, 10))
        self.assertTrue(scoring_tracks_crossed(94, 10))

    def test_reputation_ranges_gate_rewards_and_overflow(self):
        self.assertEqual([1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6], [
            reputation_display_slot(reputation) for reputation in range(1, 16)
        ])
        state = ark_nova.new_game(2, 109)
        player = state["players"][0]
        self.assertEqual(1, player["reputation"])

        player["reputation"] = 4
        workers_before = dict(player["association_workers"])
        events = []
        ark_nova._gain_reputation(state, player, 4, events, "test:early")
        self.assertEqual(8, player["reputation"])
        self.assertEqual(workers_before["active"] + 1, player["association_workers"]["active"])
        self.assertEqual(workers_before["reserve"] - 1, player["association_workers"]["reserve"])
        self.assertEqual(["action_upgrade"], [reward["type"] for reward in state["pending_rewards"]])

        state["pending_rewards"] = []
        player["reputation"] = 9
        ark_nova._gain_reputation(state, player, 2, events, "test:gate")
        self.assertEqual(9, player["reputation"])
        self.assertTrue(events[-1]["cards_ii_gate_blocked"])

        next(card for card in player["action_cards"] if card["action"] == "cards")["upgraded"] = True
        conservation_before = player["conservation"]
        ark_nova._gain_reputation(state, player, 6, events, "test:upper")
        self.assertEqual(15, player["reputation"])
        self.assertEqual(conservation_before + 2, player["conservation"])
        self.assertEqual(2, player["x_tokens"])
        self.assertEqual(["reputation:10", "reputation:13"], [
            reward["source_id"] for reward in state["pending_rewards"]
            if reward["type"] == "map_take_card"
        ])
        appeal_before = player["appeal"]
        ark_nova._gain_reputation(state, player, 2, events, "test:overflow")
        self.assertEqual(15, player["reputation"])
        self.assertEqual(appeal_before + 2, player["appeal"])

    def test_break_recalls_workers_and_refills_assets_for_other_players(self):
        state = finish_initial_hands(ark_nova.new_game(2, 108, {"turn_limit": 20}))
        first, second = state["players"]
        first["association_workers"] = {
            "active": 0, "reserve": 2,
            "committed": [{"task": "reputation", "workers": 2}],
        }
        first["partner_zoos"] = ["africa"]
        second["partner_zoos"] = ["europe"]
        first["universities"] = ["research-2", "hand-limit-5"]
        second["universities"] = ["research-reputation", "hand-limit-5"]
        state["association_board"]["partner_zoos"]["africa"] = 0
        state["association_board"]["partner_zoos"]["europe"] = 0
        state["association_board"]["universities"] = {
            "research-2": 0, "research-reputation": 0, "hand-limit-5": 0,
        }
        state["break_track"]["next_seat"] = 0

        events = []
        ark_nova._resolve_break(state, events)

        self.assertEqual(2, first["association_workers"]["active"])
        self.assertEqual([], first["association_workers"]["committed"])
        self.assertEqual(1, state["association_board"]["partner_zoos"]["africa"])
        self.assertEqual(1, state["association_board"]["partner_zoos"]["europe"])
        self.assertEqual(1, state["association_board"]["universities"]["research-2"])
        self.assertEqual(1, state["association_board"]["universities"]["research-reputation"])
        self.assertEqual(0, state["association_board"]["universities"]["hand-limit-5"])
        tasks = ark_nova._association_actions(state, first, 4)
        self.assertTrue(any(item.get("university") == "research-reputation" for item in tasks))
        self.assertTrue(any(item.get("continent") == "europe" for item in tasks))
        university = next(
            item for item in ark_nova.observe(state, 0)["association_display"]["universities"]
            if item["id"] == "research-reputation"
        )
        self.assertEqual(1, university["remaining"])
        self.assertEqual([1], university["owners"])

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
        add_enclosure(player, 3)
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
        enclosure = add_enclosure(player, 3)
        animal = next(card for card in state["zoo_deck"] if card["card_type"] == "animal"
                      and card["enclosure_size"] <= 3)
        state["zoo_deck"].remove(animal)
        animal["enclosure_id"] = enclosure["id"]
        player["played_cards"].append(animal)
        enclosure["occupied"] = True
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
        self.assertFalse(next(item for item in player["map"]["buildings"] if item["id"] == enclosure["id"])["occupied"])
        self.assertEqual(starting_appeal - animal["appeal"], player["appeal"])
        self.assertIn(project["id"], player["supported_projects"])
        self.assertTrue(any(card["id"] == animal["id"] for card in state["zoo_discard"]))

    def test_controlled_final_card_scoring_counts_only_one_unresolved_card(self):
        state = ark_nova.new_game(2, 30)
        player = state["players"][0]
        add_enclosure(player, 1)
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
        player["money"] = 100
        add_enclosure(player, 3)
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
        self.assertEqual(1, action["folder_cost"])
        self.assertEqual(ark_nova._animal_cost(player, animal) + 1, action["cost"])
        state, _ = ark_nova.apply_action(state, 0, action)
        self.assertEqual(100 - action["cost"], state["players"][0]["money"])
        self.assertTrue(any(card["id"] == animal["id"] for card in state["players"][0]["played_cards"]))

    def test_upgraded_animals_strength_five_plays_at_most_two_and_gains_one_reputation(self):
        state = finish_initial_hands(ark_nova.new_game(2, 33, {"turn_limit": 20}))
        player = state["players"][0]
        player["money"] = 100
        animals = next(
            card for card in player["action_cards"] if card["action"] == "animals"
        )
        animals["upgraded"] = True
        player["x_tokens"] = 5 - animals["strength"]
        cards = [
            card for card in state["zoo_deck"]
            if card["card_type"] == "animal" and card["enclosure_size"] <= 3
        ][:3]
        self.assertEqual(3, len(cards))
        for card in cards:
            state["zoo_deck"].remove(card)
            player["hand"].append(card)
            add_enclosure(player, card["enclosure_size"])

        start = next(
            item["action"] for item in ark_nova.legal_actions(state, 0)
            if item["action"]["type"] == "select_action"
            and item["action"]["action_card"] == "animals"
            and item["action"]["strength"] == 5
        )
        state, events = ark_nova.apply_action(state, 0, start)
        self.assertEqual(2, state["players"][0]["reputation"])
        self.assertEqual(1, sum(
            event["type"] == "reputation_advanced"
            and event.get("source_id") == "action:animals:reputation"
            for event in events
        ))

        for card in cards[:2]:
            play = next(
                item["action"] for item in ark_nova.legal_actions(state, 0)
                if item["action"].get("type") == "play_animal"
                and item["action"].get("card_id") == card["id"]
            )
            state, _ = ark_nova.apply_action(state, 0, play)

        played_ids = {card["id"] for card in state["players"][0]["played_cards"]}
        self.assertTrue({card["id"] for card in cards[:2]} <= played_ids)
        self.assertIn(cards[2]["id"], {
            card["id"] for card in state["players"][0]["hand"]
        })
        self.assertEqual(2, state["players"][0]["reputation"])
        self.assertEqual("choose_action", state["phase"])

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
        player["money"] = 25
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
        action = next(
            item["action"] for item in ark_nova.legal_actions(state, 0)
            if item["action"].get("source") == "display"
            and item["action"].get("card_id") == sponsor["id"]
        )
        self.assertEqual(1, action["folder_cost"])
        state, events = ark_nova.apply_action(state, 0, action)
        self.assertEqual(24, state["players"][0]["money"])
        self.assertTrue(any(
            event.get("type") == "sponsor_played" and event.get("folder_cost") == 1
            for event in events
        ))
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
        add_enclosure(broken["players"][0], 1)
        broken["players"][0]["map"]["buildings"].append(copy.deepcopy(
            broken["players"][0]["map"]["buildings"][0]
        ))
        with self.assertRaisesRegex(AssertionError, "overlap"):
            ark_nova.validate_state(broken)


if __name__ == "__main__":
    unittest.main()
