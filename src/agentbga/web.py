"""Local-only HTTP API and static host for the AgentBGA match table."""

from __future__ import annotations

from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlsplit

from . import splendor
from .agents import PlayerConfig
from .runner import run_match
from .store import Store


class MatchHub:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path
        self.matches: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)

    def _snapshot(self, match_id: str) -> dict[str, Any]:
        store = Store(self.db_path)
        try:
            version, state, _ = store.load(match_id)
            players = store.players(match_id)
            return {
                "match_id": match_id,
                "version": version,
                "status": state["status"],
                "turn_count": state["turn_count"],
                "active_seat": state["active_seat"],
                "phase": state["phase"],
                "players": players,
                "views": [splendor.observe(state, seat) for seat in range(state["player_count"])],
            }
        finally:
            store.close()

    @staticmethod
    def _with_runtime(snapshot: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        return {
            **snapshot,
            "paused": bool(record["paused"]),
            "pause_pending": bool(
                record["paused"] and record["running"] and not record["at_pause_gate"]
            ),
            "human_turn": record.get("human_pending"),
        }

    def _append_locked(
        self, record: dict[str, Any], event: dict[str, Any], snapshot: dict[str, Any] | None,
    ) -> None:
        item = {"seq": len(record["events"]), "event": event}
        if snapshot is not None:
            decorated = self._with_runtime(snapshot, record)
            item["snapshot"] = decorated
            record["snapshot"] = decorated
        record["events"].append(item)

    def _publish(self, match_id: str, event: dict[str, Any]) -> None:
        # Token deltas are deliberately lightweight: copying every full board snapshot
        # for a long reasoning stream would create hundreds of megabytes of traffic.
        lightweight = {
            "agent_stream", "harness_output", "harness_tool_call", "harness_tool_result",
        }
        snapshot = None if event.get("type") in lightweight else self._snapshot(match_id)
        with self.condition:
            record = self.matches[match_id]
            if event.get("type") in {"match_finished", "match_failed"}:
                record["running"] = False
                record["paused"] = False
                record["at_pause_gate"] = False
                record["human_pending"] = None
                record["human_submission"] = None
            self._append_locked(record, event, snapshot)
            self.condition.notify_all()

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_players = payload.get("players")
        if not isinstance(raw_players, list) or len(raw_players) not in (2, 3, 4):
            raise ValueError("players must contain 2, 3, or 4 entries")
        configs: list[PlayerConfig] = []
        for seat, raw in enumerate(raw_players):
            if not isinstance(raw, dict):
                raise ValueError(f"player {seat} must be an object")
            api_key = raw.get("api_key")
            public = {key: value for key, value in raw.items() if key != "api_key"}
            config = PlayerConfig.from_dict(public, seat)
            if config.backend not in {"random", "human"} and (
                not isinstance(api_key, str) or not api_key.strip()
            ):
                raise ValueError(f"player {seat} requires api_key")
            configs.append(replace(config, api_key=api_key or None))
        if len({config.name for config in configs}) != len(configs):
            raise ValueError("player names must be unique")
        seed = payload.get("seed")
        if seed in (None, ""):
            seed = secrets.randbits(63)
        if not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        speed_ms = payload.get("speed_ms", 650)
        if not isinstance(speed_ms, int) or not 0 <= speed_ms <= 10_000:
            raise ValueError("speed_ms must be an integer from 0 to 10000")
        store = Store(self.db_path)
        try:
            match_id, _, _ = store.create(len(configs), seed)
            store.set_players(match_id, [config.public_dict() for config in configs])
        finally:
            store.close()
        snapshot = self._snapshot(match_id)
        with self.condition:
            record = {
                "events": [], "snapshot": snapshot, "running": True,
                "paused": False, "at_pause_gate": False,
                "human_pending": None, "human_submission": None,
            }
            record["snapshot"] = self._with_runtime(snapshot, record)
            self.matches[match_id] = record
            created_snapshot = dict(record["snapshot"])
        thread = threading.Thread(
            target=self._run, args=(match_id, configs, speed_ms), daemon=True,
            name=f"agentbga-{match_id}",
        )
        thread.start()
        return created_snapshot

    def set_paused(self, match_id: str, paused: bool) -> dict[str, Any]:
        with self.condition:
            if match_id not in self.matches:
                raise KeyError(match_id)
            record = self.matches[match_id]
            if not record["running"]:
                raise ValueError("match is no longer running")
            if record["paused"] == paused:
                return dict(record["snapshot"])
            record["paused"] = paused
            if not paused:
                record["at_pause_gate"] = False
            snapshot = self._with_runtime(record["snapshot"], record)
            event_type = "pause_requested" if paused else "match_resumed"
            self._append_locked(record, {"type": event_type, "match_id": match_id}, snapshot)
            self.condition.notify_all()
            return dict(record["snapshot"])

    def _wait_for_turn(self, match_id: str) -> None:
        with self.condition:
            record = self.matches[match_id]
            if record["paused"] and record["running"]:
                record["at_pause_gate"] = True
                snapshot = self._with_runtime(record["snapshot"], record)
                self._append_locked(
                    record, {"type": "match_paused", "match_id": match_id}, snapshot,
                )
                self.condition.notify_all()
            while record["paused"] and record["running"]:
                self.condition.wait()
            record["at_pause_gate"] = False

    def _wait_for_human_action(
        self, match_id: str, configs: list[PlayerConfig], seat: int, version: int,
        _observation: dict[str, Any], legal: list[dict[str, Any]],
    ) -> str:
        with self.condition:
            record = self.matches[match_id]
            pending = {
                "seat": seat,
                "player": configs[seat].name,
                "version": version,
                "legal_actions": legal,
            }
            record["human_pending"] = pending
            record["human_submission"] = None
            snapshot = self._with_runtime(record["snapshot"], record)
            self._append_locked(record, {
                "type": "human_turn_started", "match_id": match_id,
                "seat": seat, "player": configs[seat].name, "version": version,
                "legal_action_count": len(legal),
            }, snapshot)
            self.condition.notify_all()
            while record["running"] and record["human_submission"] is None:
                self.condition.wait()
            action_id = record["human_submission"]
            record["human_submission"] = None
            if not isinstance(action_id, str):
                raise RuntimeError("match stopped before the human submitted an action")
            return action_id

    def submit_human_action(
        self, match_id: str, seat: int, expected_version: int, action_id: str,
    ) -> dict[str, Any]:
        with self.condition:
            if match_id not in self.matches:
                raise KeyError(match_id)
            record = self.matches[match_id]
            if not record["running"]:
                raise ValueError("match is no longer running")
            pending = record.get("human_pending")
            if not pending:
                raise ValueError("match is not waiting for a human action")
            if pending["seat"] != seat or pending["version"] != expected_version:
                raise ValueError("human turn is stale or belongs to another seat")
            legal_ids = {item["id"] for item in pending["legal_actions"]}
            if action_id not in legal_ids:
                raise ValueError("action_id is not legal for the current human turn")
            record["human_submission"] = action_id
            record["human_pending"] = None
            snapshot = self._with_runtime(record["snapshot"], record)
            self._append_locked(record, {
                "type": "human_action_submitted", "match_id": match_id,
                "seat": seat, "version": expected_version, "action_id": action_id,
            }, snapshot)
            self.condition.notify_all()
            return dict(record["snapshot"])

    def _run(self, match_id: str, configs: list[PlayerConfig], speed_ms: int) -> None:
        store = Store(self.db_path)
        try:
            def sink(event: dict[str, Any]) -> None:
                self._publish(match_id, event)
                if event.get("type") == "turn" and speed_ms:
                    time.sleep(speed_ms / 1000)

            options: dict[str, Any] = {
                "sink": sink,
                "turn_gate": lambda: self._wait_for_turn(match_id),
            }
            if any(config.backend == "human" for config in configs):
                options["human_choice"] = lambda seat, version, observation, legal: self._wait_for_human_action(
                    match_id, configs, seat, version, observation, legal,
                )
            run_match(store, match_id, configs, **options)
        except Exception as error:
            self._publish(match_id, {"type": "match_failed", "error": str(error)})
        finally:
            store.close()

    def get(self, match_id: str) -> dict[str, Any]:
        with self.lock:
            if match_id not in self.matches:
                raise KeyError(match_id)
            return dict(self.matches[match_id]["snapshot"])

    def events_after(self, match_id: str, after: int, wait: float = 15) -> tuple[list[dict[str, Any]], bool]:
        deadline = time.monotonic() + wait
        with self.condition:
            if match_id not in self.matches:
                raise KeyError(match_id)
            while len(self.matches[match_id]["events"]) <= after + 1 and self.matches[match_id]["running"]:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.condition.wait(remaining)
            record = self.matches[match_id]
            return list(record["events"][after + 1:]), bool(record["running"])


class WebHandler(BaseHTTPRequestHandler):
    hub: MatchHub
    static_dir: Path

    def log_message(self, format: str, *args: Any) -> None:
        # Deliberately avoid request logging: match creation bodies contain keys.
        if self.command != "POST":
            super().log_message(format, *args)

    def _headers(self, status: int, content_type: str, length: int | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:3000")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def _json(self, status: int, value: Any) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode()
        self._headers(status, "application/json; charset=utf-8", len(raw))
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:
        self._headers(HTTPStatus.NO_CONTENT, "text/plain", 0)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        human_action = re_match(r"^/api/matches/([a-f0-9]+)/(action)$", path)
        if human_action:
            match_id, _ = human_action
            try:
                payload = self._read_json()
                seat = payload.get("seat")
                expected_version = payload.get("expected_version")
                action_id = payload.get("action_id")
                if not isinstance(seat, int) or not isinstance(expected_version, int) or not isinstance(action_id, str):
                    raise ValueError("seat, expected_version, and action_id are required")
                self._json(
                    HTTPStatus.OK,
                    self.hub.submit_human_action(match_id, seat, expected_version, action_id),
                )
            except KeyError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "match_not_found"})
            except (ValueError, json.JSONDecodeError) as error:
                self._json(HTTPStatus.CONFLICT, {"error": "invalid_human_action", "message": str(error)})
            return
        control = re_match(r"^/api/matches/([a-f0-9]+)/(pause|resume)$", path)
        if control:
            match_id, action = control
            try:
                self._json(HTTPStatus.OK, self.hub.set_paused(match_id, action == "pause"))
            except KeyError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "match_not_found"})
            except ValueError as error:
                self._json(HTTPStatus.CONFLICT, {"error": "match_not_running", "message": str(error)})
            return
        if path != "/api/matches":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            payload = self._read_json()
            self._json(HTTPStatus.CREATED, self.hub.create(payload))
        except (ValueError, json.JSONDecodeError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request", "message": str(error)})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 64 * 1024:
            raise ValueError("request is too large")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("request must be a JSON object")
        return payload

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True, "service": "agentbga-web"})
            return
        match = re_match(r"^/api/matches/([a-f0-9]+)(/events)?$", path)
        if match:
            match_id, events_suffix = match
            try:
                if events_suffix:
                    self._event_stream(match_id)
                else:
                    self._json(HTTPStatus.OK, self.hub.get(match_id))
            except KeyError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "match_not_found"})
            return
        self._static(path)

    def _event_stream(self, match_id: str) -> None:
        after = int(self.headers.get("Last-Event-ID", "-1"))
        self._headers(HTTPStatus.OK, "text/event-stream; charset=utf-8")
        try:
            while True:
                items, running = self.hub.events_after(match_id, after)
                for item in items:
                    raw = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                    self.wfile.write(f"id: {item['seq']}\nevent: match\ndata: {raw}\n\n".encode())
                    self.wfile.flush()
                    after = item["seq"]
                if not running:
                    return
                if not items:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # Closing or navigating away from the page normally ends EventSource this way.
            return

    def _static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        target = (self.static_dir / relative).resolve()
        if self.static_dir.resolve() not in target.parents and target != self.static_dir.resolve():
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not target.is_file():
            if Path(relative).suffix:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            target = self.static_dir / "index.html"
        if not target.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "frontend_not_built"})
            return
        raw = target.read_bytes()
        self._headers(HTTPStatus.OK, mimetypes.guess_type(target.name)[0] or "application/octet-stream", len(raw))
        self.wfile.write(raw)


def re_match(pattern: str, value: str) -> tuple[str, str | None] | None:
    import re
    match = re.match(pattern, value)
    return (match.group(1), match.group(2)) if match else None


def serve(host: str = "127.0.0.1", port: int = 8765, db_path: str | Path | None = None,
          static_dir: str | Path | None = None) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("the key-accepting web server may only bind to localhost")
    root = Path(__file__).resolve().parents[2]
    assets = Path(static_dir) if static_dir else root / "web" / "dist" / "client"
    if not (assets / "index.html").is_file():
        raise FileNotFoundError(
            f"frontend build not found at {assets}; run: cd {root / 'web'} && npm install && npm run build"
        )
    handler = type("AgentBGAWebHandler", (WebHandler,), {"hub": MatchHub(db_path), "static_dir": assets})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"AgentBGA table: http://{host}:{port}")
    print("API keys remain in this process memory and are never persisted.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
