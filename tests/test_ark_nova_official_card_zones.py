import unittest

from agentbga.ark_nova_official import ArkNovaOfficialPlugin


class ArkNovaOfficialCardZoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = ArkNovaOfficialPlugin()

    def test_tucked_cards_remain_part_of_the_212_physical_zoo_cards(self):
        state = self.plugin.setup(2, 81)
        source = state["players"][0]["initial_draw"].pop()
        tucked = state["players"][0]["initial_draw"].pop()
        source["tucked_cards"] = [tucked]
        state["players"][0]["played_cards"].append(source)

        self.plugin.validate_state(state)

    def test_pending_draw_keep_cards_remain_in_the_physical_inventory(self):
        state = self.plugin.setup(2, 81)
        drawn = state["zoo_deck"].pop()
        state["resolution"]["pending_choice"] = self._pending(
            "draw_keep_cards", [drawn],
        )

        self.plugin.validate_state(state)

    def test_pending_scavenged_cards_remain_in_the_physical_inventory(self):
        state = self.plugin.setup(2, 81)
        drawn = [state["zoo_deck"].pop()]
        state["resolution"]["pending_choice"] = self._pending(
            "scavenge_discard", drawn,
        )

        self.plugin.validate_state(state)

    def test_effect_context_snapshots_are_not_counted_as_physical_zones(self):
        state = self.plugin.setup(2, 81)
        snapshot = dict(state["zoo_deck"][-1])
        state["resolution"]["queue"] = [{
            "operation": {"op": "gain_money", "args": {"amount": 1}},
            "actor_seat": 0, "source_id": "test", "card": snapshot,
        }]

        self.plugin.validate_state(state)

    @staticmethod
    def _pending(kind: str, drawn: list[dict]) -> dict:
        return {
            "choice_id": "zone-test", "seat": 0, "prompt": "Choose",
            "minimum": 0, "maximum": len(drawn),
            "options": [{"id": card["id"], "label": card["id"]} for card in drawn],
            "continuation": {"type": kind, "seat": 0, "drawn": drawn},
        }


if __name__ == "__main__":
    unittest.main()
