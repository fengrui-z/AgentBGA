import json
from pathlib import Path
import tempfile
import unittest

from agentbga.ark_nova_official import (
    SemanticEngine,
    apply_build_execution_action,
    legal_build_execution_actions,
    new_semantic_state,
    start_action,
)
from agentbga.public_projection import public_game_event
from agentbga.store import Store


class MapRewardPrivacyTests(unittest.TestCase):
    def reward_events(self, producer: str, source: str, recycled: bool = False):
        engine = SemanticEngine()
        state = new_semantic_state(2, seed=23)
        state["phase"] = "active"
        state["card_display"] = [{"id": "public-card"}]
        state["zoo_discard" if recycled else "zoo_deck"] = [{"id": "hidden-draw"}]
        if producer == "semantic":
            state, _ = engine.start_effects(state, 0, [{
                "op": "take_map_reward_card", "args": {}, "timing": "immediate",
            }], source_id="map-bonus")
            pending = state["resolution"]["pending_choice"]
            option = "deck" if source == "deck" else "display-public-card"
            state, events = engine.submit_choice(state, 0, pending["choice_id"], [option])
        else:
            next(card for card in state["players"][0]["action_cards"]
                 if card["action"] == "build")["upgraded"] = True
            state, _ = start_action(state, 0, "build")
            for building_type, coordinate in (
                ("standard_enclosure", (-4, 2)), ("pavilion", (-3, 1)), ("kiosk", (-3, 0)),
            ):
                placement = next(
                    item["action"] for item in legal_build_execution_actions(state, 0)
                    if item["action"].get("building_type") == building_type
                    and {(cell["q"], cell["r"]) for cell in item["action"]["cells"]}
                    == {coordinate}
                )
                state, _ = apply_build_execution_action(engine, state, 0, placement)
            action = {"type": "take_build_reward_card", "source": source}
            if source == "display":
                action["card_id"] = "public-card"
            state, events = apply_build_execution_action(engine, state, 0, action)
        return state, events

    def test_deck_rewards_hide_identity_in_public_stream_and_stored_events(self):
        for producer in ("semantic", "build"):
            for recycled in (False, True):
                with self.subTest(producer=producer, recycled=recycled):
                    state, events = self.reward_events(producer, "deck", recycled)
                    reward = next(event for event in events if event["type"] == "map_card_reward_taken")
                    self.assertEqual("hidden-draw", reward["card_id"])
                    self.assertEqual(recycled, reward["deck_recycled"])
                    self.assertIn({"id": "hidden-draw"}, state["players"][0]["hand"])
                    # The runner uses this same projection for live decision events.
                    projected = [public_game_event(event) for event in events]
                    self.assertNotIn("hidden-draw", json.dumps(projected))
                    with tempfile.TemporaryDirectory() as directory:
                        store = Store(Path(directory) / "events.sqlite3")
                        self.addCleanup(store.close)
                        match_id, _, _ = store.create(2, 23, "ark_nova")
                        with store.connection:
                            store.connection.execute(
                                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (match_id, 1, 1, 0, json.dumps(reward), "test-hash", 0),
                            )
                        self.assertEqual(public_game_event(reward), store.events(match_id)[-1]["event"])
                        store.close()
                    # Redaction must not mutate the authoritative event.
                    self.assertEqual("hidden-draw", reward["card_id"])

    def test_public_display_rewards_keep_the_known_card_identity(self):
        for producer in ("semantic", "build"):
            with self.subTest(producer=producer):
                _, events = self.reward_events(producer, "display")
                reward = next(event for event in events if event["type"] == "map_card_reward_taken")
                self.assertEqual("public-card", public_game_event(reward)["card_id"])
