import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from agentbga import splendor
from agentbga.agents import (
    AgentError,
    AnthropicAgent,
    GeminiAgent,
    OpenAICompatibleAgent,
    PlayerConfig,
    load_players_config,
)
from agentbga.runner import run_match
from agentbga.store import Store


class _BackendHandler(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        if "system" in body and "messages" in body:
            backend = "anthropic"
            prompt = json.loads(body["messages"][0]["content"])
        elif "contents" in body:
            backend = "gemini"
            prompt = json.loads(body["contents"][0]["parts"][0]["text"])
        else:
            backend = "openai"
            prompt = json.loads(body["messages"][1]["content"])
        action_id = prompt["LEGAL_ACTIONS"][0]["id"]
        type(self).requests.append({
            "backend": backend, "path": self.path, "headers": dict(self.headers), "body": body,
        })
        if backend == "anthropic":
            payload = {
                "model": body["model"],
                "content": [{"type": "text", "text": json.dumps({"action_id": action_id})}],
                "usage": {"input_tokens": 11, "output_tokens": 4},
            }
        elif backend == "gemini":
            payload = {
                "candidates": [{"content": {"parts": [{"text": json.dumps({"action_id": action_id})}]}}],
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 4},
            }
        else:
            payload = {
                "model": body["model"],
                "choices": [{"message": {"content": json.dumps({"action_id": action_id})}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format, *args):
        pass


class _ErrorHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        raw = b'{"error":"credential leaked-key is invalid"}'
        self.send_response(401)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format, *args):
        pass


class _Server:
    def __enter__(self):
        _BackendHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _BackendHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()


LEGAL = [{"id": "a-test", "action": {"type": "take_tokens", "take": {"blue": 2}, "return": {}}}]


class AgentTests(unittest.TestCase):
    def test_openai_compatible_request_and_response(self):
        with _Server() as server:
            agent = OpenAICompatibleAgent(model="open-model", base_url=server.url + "/v1", api_key="open-key")
            action_id, metadata = agent.choose({"status": "active"}, LEGAL)
        request = _BackendHandler.requests[-1]
        self.assertEqual("a-test", action_id)
        self.assertEqual("openai", metadata["backend"])
        self.assertEqual("/v1/chat/completions", request["path"])
        self.assertEqual("Bearer open-key", request["headers"]["Authorization"])
        self.assertEqual("open-model", request["body"]["model"])

    def test_anthropic_request_and_response(self):
        with mock.patch.dict(os.environ, {"CLAUDE_KEY": "claude-key"}):
            with _Server() as server:
                agent = AnthropicAgent(
                    model="claude-model", base_url=server.url, api_key_env="CLAUDE_KEY"
                )
                action_id, metadata = agent.choose({"status": "active"}, LEGAL)
        request = _BackendHandler.requests[-1]
        self.assertEqual("a-test", action_id)
        self.assertEqual("anthropic", metadata["backend"])
        self.assertEqual("/v1/messages", request["path"])
        self.assertEqual("claude-key", request["headers"]["X-Api-Key"])
        self.assertEqual("2023-06-01", request["headers"]["Anthropic-Version"])
        self.assertEqual(128, request["body"]["max_tokens"])

    def test_gemini_request_and_response(self):
        with mock.patch.dict(os.environ, {"GOOGLE_KEY": "google-key"}):
            with _Server() as server:
                agent = GeminiAgent(
                    model="gemini-model", base_url=server.url + "/v1beta", api_key_env="GOOGLE_KEY"
                )
                action_id, metadata = agent.choose({"status": "active"}, LEGAL)
        request = _BackendHandler.requests[-1]
        self.assertEqual("a-test", action_id)
        self.assertEqual("gemini", metadata["backend"])
        self.assertEqual("/v1beta/models/gemini-model:generateContent", request["path"])
        self.assertEqual("google-key", request["headers"]["X-Goog-Api-Key"])
        self.assertIn("system_instruction", request["body"])

    def test_missing_key_names_the_required_environment_variable(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(AgentError, "MISSING_PLAYER_KEY"):
                AnthropicAgent(model="m", base_url="http://invalid", api_key_env="MISSING_PLAYER_KEY")

    def test_http_error_redacts_api_key(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ErrorHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            agent = OpenAICompatibleAgent(
                model="m", base_url=f"http://127.0.0.1:{server.server_port}/v1", api_key="leaked-key"
            )
            with self.assertRaises(AgentError) as raised:
                agent.choose({"status": "active"}, LEGAL)
            self.assertNotIn("leaked-key", str(raised.exception))
            self.assertIn("[REDACTED]", str(raised.exception))
        finally:
            server.shutdown()
            server.server_close()

    def test_load_named_players_config_and_reject_secret_field(self):
        config = {
            "schema_version": "agentbga.players.v1",
            "players": [
                {"name": "Alpha", "backend": "openai", "model": "a", "api_key_env": "ALPHA_KEY"},
                {"name": "Beta", "backend": "random"},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "players.json"
            path.write_text(json.dumps(config))
            players = load_players_config(str(path))
            self.assertEqual(["Alpha", "Beta"], [player.name for player in players])
            config["players"][0]["api_key"] = "must-not-be-accepted"
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "unknown fields: api_key"):
                load_players_config(str(path))

    def test_config_rejects_secrets_embedded_in_endpoint(self):
        with self.assertRaisesRegex(ValueError, "cannot contain credentials"):
            PlayerConfig.from_dict({
                "name": "Unsafe", "backend": "openai", "model": "m",
                "base_url": "https://user:secret@example.test/v1",
            }, 0)
        with self.assertRaisesRegex(ValueError, "query"):
            PlayerConfig.from_dict({
                "name": "Unsafe", "backend": "gemini", "model": "m",
                "base_url": "https://example.test/v1?key=secret",
            }, 0)

    def test_two_named_backends_with_distinct_endpoints_and_keys_complete_match(self):
        with _Server() as first, _Server() as second:
            players = [
                PlayerConfig.from_dict({
                    "name": "Alpha API", "backend": "openai", "model": "alpha-model",
                    "base_url": first.url + "/v1", "api_key_env": "ALPHA_KEY",
                }, 0),
                PlayerConfig.from_dict({
                    "name": "Beta API", "backend": "anthropic", "model": "beta-model",
                    "base_url": second.url, "api_key_env": "BETA_KEY",
                }, 1),
            ]
            with tempfile.TemporaryDirectory() as directory:
                store = Store(Path(directory) / "test.sqlite3")
                match_id, _, _ = store.create(2, 91)
                with mock.patch.dict(os.environ, {"ALPHA_KEY": "alpha-secret", "BETA_KEY": "beta-secret"}):
                    result = run_match(store, match_id, players, max_turns=250)
                self.assertEqual({"Alpha API", "Beta API"}, {row["player"] for row in result["rankings"]})
                persisted = store.players(match_id)
                self.assertEqual(["Alpha API", "Beta API"], [row["name"] for row in persisted])
                serialized = json.dumps(persisted)
                self.assertNotIn("alpha-secret", serialized)
                self.assertNotIn("beta-secret", serialized)
                self.assertTrue(any(
                    request["headers"].get("Authorization") == "Bearer alpha-secret"
                    for request in _BackendHandler.requests
                ))
                self.assertTrue(any(
                    request["headers"].get("X-Api-Key") == "beta-secret"
                    for request in _BackendHandler.requests
                ))
                calls = store.connection.execute(
                    "SELECT COUNT(*) FROM model_calls WHERE match_id=?", (match_id,)
                ).fetchone()[0]
                self.assertGreater(calls, 0)
                _, state, _ = store.load(match_id)
                splendor.validate_state(state)
                store.close()


if __name__ == "__main__":
    unittest.main()
