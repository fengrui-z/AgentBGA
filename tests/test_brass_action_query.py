import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from agentbga import brass_birmingham as brass
from agentbga.agent_context import prepare_seat_context
from agentbga.legal_action_query import query_actions, query_schema, reply_bytes, MAX_REPLY_BYTES
from agentbga.seat_tool import call_tool


class BrassActionQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "turn-context.json"
        self.state = brass.new_game(2, 43)

    def context(self, seat=None):
        seat = self.state["active_seat"] if seat is None else seat
        return prepare_seat_context(self.path, match_id="brass", seat=seat, version=9,
                                    observation=brass.observe(self.state, seat),
                                    legal=brass.legal_actions(self.state, seat))

    def step(self, **fields):
        seat = self.state["active_seat"]
        action = next(item["action"] for item in brass.legal_actions(self.state, seat)
                      if all(item["action"].get(k) == v for k, v in fields.items()))
        self.state, _ = brass.apply_action(self.state, seat, action)

    def begin(self, kind):
        self.step(type="select_action", action=kind)
        self.step(type="discard_card")

    def test_main_action_and_private_discard_queries(self):
        context = self.context()
        self.assertEqual(call_tool(self.path, "legal_actions"), context["legal_actions"])
        page = call_tool(self.path, "legal_actions", {"filters": {"action": "build"}})
        self.assertEqual(page["total"], 1)
        self.step(type="select_action", action="build")
        context = self.context()
        target = context["legal_actions"][0]["card_id"]
        self.assertEqual(query_actions(context, {"filters": {"card_id": target}})["total"], 1)
        opponent = 1 - self.state["active_seat"]
        private = self.state["players"][opponent]["hand"][0]["id"]
        self.assertEqual(query_actions(context, {"filters": {"card_id": private}})["total"], 0)
        inactive = self.context(opponent)
        self.assertEqual(query_actions(inactive, {"filters": {}})["actions"], [])

    def test_build_filters_and_original_submission(self):
        self.begin("build")
        brass.validate_state(self.state)
        context = self.context()
        target = context["legal_actions"][0]
        filters = {key: target[key] for key in ("type", "industry", "location_id", "tile_id", "slot_id")}
        filters["max_cost"] = target["cost"]
        page = call_tool(self.path, "legal_actions", {"filters": filters})
        self.assertEqual(page["actions"], [target])
        self.assertEqual(query_actions(context, {"filters": {**filters, "max_cost": 0}})["total"], 0)
        self.assertTrue(call_tool(self.path, "submit_action", {"action_id": target["id"]})["accepted"])
        with self.assertRaisesRegex(ValueError, "unsupported"):
            query_actions(context, {"filters": {"max_payment": 10}})

    def test_develop_membership_keeps_single_double_and_mixed_choices(self):
        self.begin("develop")
        context = self.context()
        expected = [x for x in context["legal_actions"] if "coal_mine" in x["industries"]]
        page = query_actions(context, {"filters": {"industry": "coal_mine"}})
        self.assertEqual(page["actions"], expected)
        self.assertIn(["coal_mine"], [x["industries"] for x in expected])
        self.assertIn(["coal_mine", "coal_mine"], [x["industries"] for x in expected])
        self.assertTrue(any(len(set(x["industries"])) == 2 for x in expected))
        bound = expected[0]["estimated_market_cost"]
        page = query_actions(context, {"filters": {"industry": "coal_mine", "max_estimated_market_cost": bound}})
        self.assertEqual(page["actions"], [x for x in expected if x["estimated_market_cost"] <= bound])
        # Development quotes have a separate field: never invent a full-turn cost.
        self.assertEqual(query_actions(context, {"filters": {"max_cost": 100}})["total"], 0)

    def test_scout_membership_preserves_every_matching_pair(self):
        self.begin("scout")
        context = self.context()
        target = context["legal_actions"][0]["card_ids"][0]
        expected = [x for x in context["legal_actions"] if target in x["card_ids"]]
        page = query_actions(context, {"filters": {"card_id": target}})
        self.assertEqual(page["actions"], expected)
        self.assertGreater(len(expected), 1)
        self.assertTrue(all(len(x["card_ids"]) == 2 for x in expected))

    def test_resource_sources_and_network_connections(self):
        self.begin("develop")
        self.step(type="develop_tiles", industries=["coal_mine"])
        context = self.context()
        market = query_actions(context, {"filters": {"resource": "iron", "source": "market"}})
        self.assertEqual(market["total"], 1)
        target = market["actions"][0]
        self.assertEqual(query_actions(context, {"filters": {"source_id": target["source_id"],
                                                             "max_cost": target["cost"]}})["actions"], [target])
        self.assertEqual(query_actions(context, {"filters": {"source": "industry"}})["total"], 0)
        self.state = brass.new_game(2, 43)
        self.begin("network")
        context = self.context()
        target = context["legal_actions"][0]
        self.assertEqual(query_actions(context, {"filters": {"connection_id": target["connection_id"]}})["actions"], [target])

    def test_lossless_bounded_pages_across_real_decisions(self):
        rng = random.Random(43)
        phases = set()
        for _ in range(250):
            if self.state["status"] != "active":
                break
            phases.add(self.state["phase"])
            context = self.context()
            self.assertLessEqual(reply_bytes(query_actions(context, {})), MAX_REPLY_BYTES)
            recovered, cursor = [], 0
            while cursor is not None:
                page = query_actions(context, {"filters": {}, "cursor": cursor, "limit": 7})
                self.assertLessEqual(reply_bytes(page), MAX_REPLY_BYTES)
                recovered.extend(page["actions"])
                cursor = page["next_cursor"]
            self.assertEqual(recovered, context["legal_actions"])
            seat = self.state["active_seat"]
            action = rng.choice(brass.legal_actions(self.state, seat))["action"]
            self.state, _ = brass.apply_action(self.state, seat, action)
        self.assertTrue({"choose_action", "develop_choose_tiles", "build_choose_placement",
                         "network_choose_link", "scout_choose_extra_cards"} <= phases)

    @unittest.skipUnless(shutil.which("node"), "Node is required for Pi parity")
    def test_pi_agrees_on_membership_and_cost_queries(self):
        from agentbga import legal_action_query
        script = Path(legal_action_query.__file__).with_suffix(".js").read_text().replace("__LEGAL_QUERY_SCHEMA__", json.dumps(query_schema()))
        script += '\nconst d=JSON.parse(require("fs").readFileSync(0,"utf8")); console.log(JSON.stringify(d.map(([c,q])=>filteredLegal(c,q))));'
        self.begin("develop")
        context = self.context()
        pairs = [[context, {"filters": {"industry": "coal_mine"}, "limit": 2}],
                 [context, {"filters": {"max_estimated_market_cost": 3}}]]
        self.state = brass.new_game(2, 43)
        self.begin("scout")
        context = self.context()
        pairs.append([context, {"filters": {"card_id": context["legal_actions"][0]["card_ids"][0]}}])
        result = subprocess.run(["node", "-e", script], input=json.dumps(pairs),
                                capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(json.loads(result.stdout), [query_actions(c, q) for c, q in pairs])
