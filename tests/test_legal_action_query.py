import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from agentbga import splendor
from agentbga.agent_context import prepare_seat_context, project_legal_actions
from agentbga.legal_action_query import MAX_REPLY_BYTES, query_actions, query_schema, reply_bytes
from agentbga.seat_tool import call_tool


class SplendorActionQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "turn-context.json"
        self.state = splendor.new_game(2, 43)
        # Legal ten-token holding: expands every take/reserve into return combinations.
        held = {"white": 2, "blue": 2, "green": 2, "red": 2, "black": 1, "gold": 1}
        self.state["players"][0]["tokens"] = held
        for color, count in held.items():
            self.state["bank"][color] -= count
        splendor.validate_state(self.state)
        self.legal = splendor.legal_actions(self.state, 0)
        self.context = prepare_seat_context(
            self.path, match_id="test", seat=0, version=12,
            observation=splendor.observe(self.state, 0), legal=self.legal,
        )

    def test_large_default_is_bounded_and_all_groups_round_trip(self):
        self.assertGreater(len(self.legal), 150)
        self.assertGreater(reply_bytes(self.context["legal_actions"]), MAX_REPLY_BYTES)
        response = call_tool(self.path, "legal_actions")
        self.assertEqual(response["mode"], "groups")
        self.assertLessEqual(reply_bytes(response), MAX_REPLY_BYTES)
        seen = {}
        for group in response["groups"]:
            cursor = 0
            while cursor is not None:
                page = call_tool(self.path, "legal_actions", {"group": group["group"], "cursor": cursor, "limit": 50})
                self.assertLessEqual(reply_bytes(page), MAX_REPLY_BYTES)
                self.assertTrue(page["actions"])
                for item in page["actions"]:
                    self.assertNotIn(item["id"], seen)
                    seen[item["id"]] = item
                cursor = page["next_cursor"]
        self.assertEqual(seen, {item["id"]: item for item in self.context["legal_actions"]})
        buy = next(item for item in seen.values() if item["type"].startswith("buy"))
        accepted = call_tool(self.path, "submit_action", {"action_id": buy["id"]})
        self.assertTrue(accepted["accepted"])
        with self.assertRaisesRegex(ValueError, "already"):
            call_tool(self.path, "submit_action", {"action_id": buy["id"]})
        self.assertEqual(json.loads(self.path.read_text()), self.context)

    def test_buy_filters_preserve_every_payment_and_original_id(self):
        original = [x for x in self.context["legal_actions"] if x["type"] == "buy_visible"]
        target = original[0]["card_id"]
        card = splendor.CARDS[target]
        result = call_tool(self.path, "legal_actions", {"filters": {
            "type": "buy_visible", "card_id": target, "tier": card["tier"], "bonus": card["bonus"],
        }, "limit": 50})
        self.assertEqual(result["actions"], [x for x in original if x["card_id"] == target])
        free = call_tool(self.path, "legal_actions", {"filters": {"max_payment": 0}})
        self.assertEqual(free["actions"], [])
        absent = call_tool(self.path, "legal_actions", {"filters": {"card_id": "not-visible"}})
        self.assertEqual(absent["total"], 0)
        self.assertIsNone(absent["next_cursor"])
        with self.assertRaisesRegex(ValueError, "unknown or stale"):
            call_tool(self.path, "submit_action", {"action_id": "not-visible"})

    def test_legacy_context_and_small_lists_remain_usable(self):
        self.context.pop("legal_action_query")
        self.assertEqual(project_legal_actions(self.context)["mode"], "groups")
        self.context["legal_actions"] = self.context["legal_actions"][:2]
        self.assertEqual(project_legal_actions(self.context), self.context["legal_actions"])

    def test_reserved_card_metadata_and_noble_choice(self):
        target = "t1-green-6"
        self.state["market"]["1"].remove(target)
        self.state["players"][0]["reserved"].append(target)
        prepare_seat_context(self.path, match_id="test", seat=0, version=13,
                             observation=splendor.observe(self.state, 0),
                             legal=splendor.legal_actions(self.state, 0))
        page = call_tool(self.path, "legal_actions", {"filters": {
            "type": "buy_reserved", "tier": 1, "bonus": "green", "card_id": target,
        }})
        self.assertTrue(page["actions"])
        self.assertTrue(all(x["type"] == "buy_reserved" for x in page["actions"]))
        self.state["phase"] = "choose_noble"
        self.state["pending_nobles"] = self.state["available_nobles"][:2]
        prepare_seat_context(self.path, match_id="test", seat=0, version=14,
                             observation=splendor.observe(self.state, 0),
                             legal=splendor.legal_actions(self.state, 0))
        noble = self.state["pending_nobles"][0]
        page = call_tool(self.path, "legal_actions", {"filters": {"noble_id": noble}})
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["actions"][0]["noble_id"], noble)

    def test_strict_validation_and_empty_tail(self):
        for args in ({"filters": {"location_id": "x"}}, {"filters": {"tier": True}},
                     {"filters": {"bonus": "gold"}}, {"filters": []}, {"filters": None},
                     {"cursor": -1}, {"cursor": True}, {"limit": 0}, {"limit": 51},
                     {"group": "missing"}, {"cursor": 100000}, {"extra": 1},
                     {"group": "take_tokens", "filters": {"type": "buy_visible"}}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                call_tool(self.path, "legal_actions", args)
        result = call_tool(self.path, "legal_actions", {"cursor": len(self.legal)})
        self.assertEqual(result["actions"], [])
        self.assertIsNone(result["next_cursor"])

    def test_byte_limit_applies_even_below_row_limit(self):
        # Long labels/Unicode can exhaust the byte budget with fewer than 20 rows.
        for item in self.context["legal_actions"]:
            item["label"] = "宝石" * 80
        page = query_actions(self.context, {"group": "take_tokens", "limit": 50})
        self.assertLess(len(page["actions"]), 20)
        self.assertGreater(len(page["actions"]), 0)
        self.assertLessEqual(reply_bytes(page), MAX_REPLY_BYTES)

    def test_mcp_and_minimal_expose_identical_query_schema(self):
        from agentbga.seat_mcp import TOOLS
        from agentbga.minimal_harness import MINIMAL_TOOLS, DirectGameAgent
        tool = next(x for x in TOOLS if x["name"] == "legal_actions")
        minimal = next(x["function"] for x in MINIMAL_TOOLS if x["function"]["name"] == "legal_actions")
        self.assertEqual(tool["inputSchema"], minimal["parameters"])
        agent = object.__new__(DirectGameAgent)
        agent.runtime = self.path.parent
        agent.workspace = self.path.parent
        agent.profile = object()
        args = {"filters": {"type": "buy_visible"}}
        self.assertEqual(agent._execute_tool("legal_actions", args, self.context["observation"], self.legal),
                         call_tool(self.path, "legal_actions", args))

    def test_stdio_mcp_and_cli_return_filtered_ids(self):
        args = {"filters": {"type": "buy_visible"}}
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "legal_actions", "arguments": args}}
        proc = subprocess.run([sys.executable, "-m", "agentbga.seat_mcp", "--context", str(self.path),
                               "--notes-root", str(self.path.parent)], input=json.dumps(request) + "\n",
                              text=True, capture_output=True, check=True, timeout=10)
        result = json.loads(proc.stdout)["result"]
        self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"]["data"])
        cli = subprocess.run([sys.executable, "-m", "agentbga.seat_tool", "--context", str(self.path),
                              "legal-actions", "--filters", json.dumps(args["filters"])],
                             text=True, capture_output=True, check=True, timeout=10)
        self.assertEqual(json.loads(cli.stdout)["data"], result["structuredContent"]["data"])

    @unittest.skipUnless(shutil.which("node"), "Node is required for Pi query parity")
    def test_pi_query_matches_python_results_and_errors(self):
        from agentbga import legal_action_query
        script = Path(legal_action_query.__file__).with_suffix(".js").read_text()
        script = script.replace("__LEGAL_QUERY_SCHEMA__", json.dumps(query_schema()))
        script += '\nconst input = JSON.parse(require("fs").readFileSync(0, "utf8"));\n'
        script += 'console.log(JSON.stringify(input.queries.map(args => {try {return filteredLegal(input.context, args);} catch(e) {return {error: true};}})));'
        queries = [{}, {"filters": {"type": "buy_visible"}}, {"group": "take_tokens", "limit": 50},
                   {"cursor": 10}, {"filters": {"max_payment": 4}}, {"cursor": -1},
                   {"filters": {"tier": True}}, {"filters": {"bonus": "gold"}}, {"filters": None}]
        expected = []
        for args in queries:
            try:
                expected.append(query_actions(self.context, args))
            except ValueError:
                expected.append({"error": True})
        proc = subprocess.run(["node", "-e", script], input=json.dumps({"context": self.context, "queries": queries}),
                              text=True, capture_output=True, check=True, timeout=10)
        self.assertEqual(json.loads(proc.stdout), expected)
