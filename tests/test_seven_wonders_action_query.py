import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from agentbga import seven_wonders as seven
from agentbga.agent_context import prepare_seat_context
from agentbga.legal_action_query import query_actions, query_schema, reply_bytes, MAX_REPLY_BYTES
from agentbga.seat_tool import call_tool


class SevenWondersQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "turn-context.json"
        self.state = seven.new_game(3, 19, {
            "wonders": ["olympia", "alexandria", "giza"], "wonder_sides": "day",
        })

    def move(self, card, destination):
        for zone in [*self.state["hands"], *self.state["age_decks"].values(), self.state["discard"],
                     *[p["city"] for p in self.state["players"]]]:
            if card in zone:
                zone.remove(card)
        destination.append(card)

    def context(self, seat=0):
        return prepare_seat_context(self.path, match_id="seven", seat=seat, version=7,
                                    observation=seven.observe(self.state, seat),
                                    legal=seven.legal_actions(self.state, seat))

    def test_trade_filters_preserve_distinct_neighbor_plans(self):
        self.move("age1-stone-pit-3", self.state["players"][1]["city"])
        self.move("age1-baths-3", self.state["hands"][0])
        seven.validate_state(self.state)
        context = self.context()
        filters = {"type": "build_card", "card_id": "age1-baths-3", "card_color": "blue",
                   "card_age": 1, "max_payment": 2}
        page = call_tool(self.path, "legal_actions", {"filters": filters})
        expected = [x for x in context["legal_actions"]
                    if x["type"] == "build_card" and x["card_id"] == "age1-baths-3"]
        self.assertEqual(page["actions"], expected)
        self.assertEqual({(x["payment"]["left"], x["payment"]["right"]) for x in expected}, {(2, 0), (0, 2)})
        right = call_tool(self.path, "legal_actions", {"filters": {**filters, "max_left_payment": 0}})
        self.assertEqual(len(right["actions"]), 1)
        self.assertEqual(right["actions"][0]["payment"]["right"], 2)
        self.assertTrue(call_tool(self.path, "submit_action", {"action_id": right["actions"][0]["id"]})["accepted"])

    def test_chains_and_wonder_material_card_filters(self):
        self.move("age1-marketplace-3", self.state["players"][0]["city"])
        self.move("age2-caravansery-3", self.state["hands"][0])
        self.context()
        page = call_tool(self.path, "legal_actions", {"filters": {
            "type": "build_card", "free_source": "chain", "max_payment": 0,
        }})
        self.assertTrue(any(x["card_id"] == "age2-caravansery-3" for x in page["actions"]))
        self.state["players"][0]["coins"] = 30
        self.move("age2-quarry-3", self.state["players"][0]["city"])
        context = self.context()
        expected = [x for x in context["legal_actions"] if x["type"] == "build_wonder"]
        self.assertTrue(expected)
        card = expected[0]["card_id"]
        page = call_tool(self.path, "legal_actions", {"filters": {"type": "build_wonder", "stage": 1, "card_id": card}})
        self.assertEqual(page["actions"], [x for x in expected if x["card_id"] == card])

    def test_sealed_opponent_choice_is_not_queryable(self):
        target = self.state["hands"][0][0]
        sell = next(x["action"] for x in seven.legal_actions(self.state, 0)
                    if x["action"]["type"] == "sell_card" and x["action"]["card_id"] == target)
        self.state, _ = seven.apply_action(self.state, 0, sell)
        self.context(1)
        page = call_tool(self.path, "legal_actions", {"filters": {"card_id": target}})
        self.assertEqual(page["actions"], [])
        self.assertEqual(page["total"], 0)
        with self.assertRaisesRegex(ValueError, "unknown or stale"):
            call_tool(self.path, "submit_action", {"action_id": "opponent-action"})

    def test_discard_and_seventh_card_phases(self):
        target = self.state["hands"][1][0]
        self.move(target, self.state["discard"])
        self.state["phase"] = "build_from_discard"
        self.state["active_seat"] = 0
        self.context()
        page = call_tool(self.path, "legal_actions", {"filters": {"type": "build_discard", "card_id": target}})
        self.assertEqual(page["total"], 1)
        self.state["discard"] = []
        self.context()
        self.assertEqual(call_tool(self.path, "legal_actions", {"filters": {"type": "skip_discard"}})["total"], 1)
        self.state["phase"] = "seventh_card"
        context = self.context()
        self.assertTrue(context["legal_actions"])
        for kind in {x["type"] for x in context["legal_actions"]}:
            page = call_tool(self.path, "legal_actions", {"filters": {"type": kind}})
            self.assertEqual(page["actions"], [x for x in context["legal_actions"] if x["type"] == kind])

    @unittest.skipUnless(shutil.which("node"), "Node is required for Pi parity")
    def test_pi_agrees_on_color_age_and_payment_queries(self):
        from agentbga import legal_action_query
        self.move("age1-stone-pit-3", self.state["players"][1]["city"])
        self.move("age1-baths-3", self.state["hands"][0])
        context = self.context()
        queries = [{"filters": {"card_color": "blue", "card_age": 1}},
                   {"filters": {"max_right_payment": 0}}, {"filters": {"stage": 1}}]
        script = Path(legal_action_query.__file__).with_suffix(".js").read_text().replace("__LEGAL_QUERY_SCHEMA__", json.dumps(query_schema()))
        script += '\nconst d=JSON.parse(require("fs").readFileSync(0,"utf8")); console.log(JSON.stringify(d.queries.map(q=>filteredLegal(d.context,q))));'
        result = subprocess.run(["node", "-e", script], input=json.dumps({"context": context, "queries": queries}),
                                capture_output=True, text=True, check=True, timeout=10)
        expected = [query_actions(context, q) for q in queries]
        self.assertEqual(json.loads(result.stdout), expected)
        self.assertTrue(all(reply_bytes(x) <= MAX_REPLY_BYTES for x in expected))
