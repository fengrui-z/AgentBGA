import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from agentbga import brass_birmingham as brass
from agentbga.agent_context import prepare_seat_context
from agentbga.agent_view import prepare_view
from agentbga.agent_view.resources import inspect, build_resources, INSPECT_SCHEMA
from agentbga.legal_action_query import MAX_REPLY_BYTES, reply_bytes
from agentbga.seat_tool import call_tool


class BrassObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'turn-context.json'
        self.state = brass.new_game(4, 43)

    def context(self, version=1, seat=None):
        seat = self.state['active_seat'] if seat is None else seat
        return prepare_seat_context(self.path, match_id='view-test', seat=seat, version=version,
                                    observation=brass.observe(self.state, seat),
                                    legal=brass.legal_actions(self.state, seat))

    def recover(self, context, ref='observation'):
        args = {'ref': ref}
        result = None
        while True:
            page = inspect(context, args)
            self.assertLessEqual(reply_bytes(page), MAX_REPLY_BYTES)
            if page['mode'] == 'value':
                return page['value']
            if result is None:
                result = {} if page['mode'] == 'object' else []
            for entry in page['entries']:
                value = self.recover(context, entry['inspect_ref']) if 'inspect_ref' in entry else entry['value']
                if isinstance(result, dict):
                    result[entry['key']] = value
                else:
                    self.assertEqual(entry['index'], len(result))
                    result.append(value)
            if page['next_cursor'] is None:
                return result
            args['cursor'] = page['next_cursor']

    def test_summary_and_lossless_details_for_all_player_counts(self):
        for count in (2, 3, 4):
            with self.subTest(players=count):
                self.state = brass.new_game(count, 43)
                context = self.context()
                original = brass.observe(self.state, context['seat'])
                shown = call_tool(self.path, 'observe')
                self.assertLessEqual(reply_bytes(shown), MAX_REPLY_BYTES)
                self.assertLess(reply_bytes(shown), reply_bytes(original) / 4)
                self.assertEqual(shown['markets'], original['markets'])
                self.assertEqual(shown['turn'], original['turn'])
                own = shown['players'][context['seat']]
                self.assertEqual(own['hand'], original['players'][context['seat']]['hand'])
                self.assertEqual(self.recover(context), original)
                for i, player in enumerate(shown['players']):
                    for kind, remaining, level in player['industry_stacks']['rows']:
                        tiles = original['players'][i]['industry_stacks'][kind]
                        self.assertEqual(remaining, len(tiles))
                        self.assertEqual(level, tiles[0]['level'] if tiles else None)

    def test_hidden_information_stays_hidden_in_all_resources(self):
        context = self.context(seat=0)
        serialized = json.dumps(context)
        for opponent in self.state['players'][1:]:
            for card in opponent['hand']:
                self.assertNotIn(card['id'], serialized)
        for player in self.state['players']:
            for card in player['discard']:
                if not card.get('face_up', True):
                    self.assertNotIn(card['id'], serialized)
        for ref in ('../../database.sqlite', 'observation/players/1/hand/0', '__proto__'):
            with self.assertRaises(ValueError):
                inspect(context, {'ref': ref})

    def test_paging_binds_decision_and_reference(self):
        source = {'items': [{'id': i, 'description': '中文' * 300} for i in range(45)]}
        resources = build_resources(source, 8, ['m', 0])
        context = {'version': 8, 'view_resources': resources}
        self.assertEqual(self.recover(context), source)
        ref = 'observation/items'
        first = inspect(context, {'ref': ref})
        self.assertIsNotNone(first['next_cursor'])
        cursor = first['next_cursor']
        with self.assertRaises(ValueError):
            inspect(context, {'cursor': cursor})
        next_context = {'version': 9, 'view_resources': build_resources(source, 9, ['m', 0])}
        with self.assertRaises(ValueError):
            inspect(next_context, {'ref': ref, 'cursor': cursor})
        for args in ({'state_version': 7}, {'state_version': True}, {'cursor': None},
                     {'cursor': ''}, {'ref': 3}, {'limit': 5}, [], {'state_version': -1}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                inspect(context, args)

    def test_dense_board_overflow_has_complete_inspectable_overview(self):
        original = brass.observe(self.state, 0)
        tile = self.state['players'][0]['industry_stacks']['cotton_mill'][0]
        # Deliberately exceed any ordinary board size to exercise the overflow contract.
        original['board']['industries'] = [dict(tile, id=f'industry-{i}', owner=i % 4,
            location='birmingham', slot_id=f'slot-{i}', resources=2, flipped=False) for i in range(150)]
        shown, resources = prepare_view(original, version=5, match_id='overflow', seat=0)
        self.assertLessEqual(reply_bytes(shown), MAX_REPLY_BYTES)
        self.assertTrue(shown['board']['deferred'])
        context = {'version': 5, 'view_resources': resources}
        overview = self.recover(context, shown['board']['inspect_ref'])
        self.assertEqual(len(overview['industries']['rows']), 150)
        self.assertEqual(self.recover(context), original)

    def test_real_decisions_keep_all_public_board_rows_and_submission_ids(self):
        for count in (2, 4):
            self.state = brass.new_game(count, 44)
            rng = random.Random(44)
            for decision in range(250):
                if self.state['status'] != 'active':
                    break
                seat = self.state['active_seat']
                legal = brass.legal_actions(self.state, seat)
                if decision % 7 == 0:
                    context = self.context(version=decision)
                    shown = context['observation']
                    self.assertLessEqual(reply_bytes(shown), MAX_REPLY_BYTES)
                    board = shown['board']
                    if board.get('deferred'):
                        board = self.recover(context, board['inspect_ref'])
                    self.assertEqual(len(board['industries']['rows']), len(self.state['board']['industries']))
                    self.assertEqual(len(board['links']['rows']), len(self.state['board']['links']))
                    self.assertEqual([x['id'] for x in context['legal_actions']], [x['id'] for x in legal])
                self.state, _ = brass.apply_action(self.state, seat, rng.choice(legal)['action'])
        context = self.context(version=251)
        chosen = context['legal_actions'][0]['id']
        self.assertTrue(call_tool(self.path, 'submit_action', {'action_id': chosen})['accepted'])

    def test_mcp_minimal_and_cli_share_inspection(self):
        from agentbga.seat_mcp import TOOLS
        from agentbga.minimal_harness import MINIMAL_TOOLS, DirectGameAgent
        context = self.context()
        args = {'ref': 'observation/board/connection_spaces'}
        expected = inspect(context, args)
        self.assertEqual(next(t for t in TOOLS if t['name'] == 'inspect')['inputSchema'], INSPECT_SCHEMA)
        self.assertEqual(next(t['function'] for t in MINIMAL_TOOLS if t['function']['name'] == 'inspect')['parameters'], INSPECT_SCHEMA)
        agent = object.__new__(DirectGameAgent)
        agent.runtime = self.path.parent
        agent.workspace = self.path.parent
        self.assertEqual(agent._execute_tool('inspect', args), expected)
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'inspect', 'arguments': args}}
        result = subprocess.run([sys.executable, '-m', 'agentbga.seat_mcp', '--context', str(self.path),
                                 '--notes-root', self.tmp.name], input=json.dumps(request)+'\n',
                                text=True, capture_output=True, check=True, timeout=10)
        payload = json.loads(result.stdout)['result']
        self.assertEqual(payload['structuredContent']['data'], expected)
        self.assertLessEqual(len(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()), MAX_REPLY_BYTES)
        result = subprocess.run([sys.executable, '-m', 'agentbga.seat_tool', '--context', str(self.path),
                                 'inspect', '--ref', args['ref']], text=True, capture_output=True, check=True, timeout=10)
        self.assertEqual(json.loads(result.stdout)['data'], expected)

    @unittest.skipUnless(shutil.which('node'), 'Node required for Pi parity')
    def test_pi_serves_identical_prepared_pages_and_rejects_invalid_queries(self):
        from agentbga.harness import PI_EXTENSION
        context = self.context()
        script = PI_EXTENSION.split('function inspectResource', 1)[1].split('export default function', 1)[0]
        script = 'function inspectResource' + script.replace(': any', '')
        script += '\nconst d=JSON.parse(require("fs").readFileSync(0,"utf8")); console.log(JSON.stringify(d.q.map(q=>{try{return inspectResource(d.c,q)}catch(e){return {error:true}}})));'
        queries = [{}, {'ref': 'observation/players/0/industry_stacks'}, {'cursor': 'stale'},
                   {'state_version': 99}, {'ref': '__proto__'}, {'cursor': None}, {'unknown': 1}]
        expected = []
        for query in queries:
            try:
                expected.append(inspect(context, query))
            except ValueError:
                expected.append({'error': True})
        result = subprocess.run(['node', '-e', script], input=json.dumps({'c': context, 'q': queries}),
                                text=True, capture_output=True, check=True, timeout=10)
        self.assertEqual(json.loads(result.stdout), expected)
