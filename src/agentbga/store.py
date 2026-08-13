"""SQLite persistence for matches and append-only action/event history."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import time
import uuid
from typing import Any

from .registry import get_game


class ConflictError(RuntimeError):
    pass


class MatchNotFound(KeyError):
    pass


def default_db_path() -> Path:
    return Path.cwd() / ".agentbga" / "agentbga.sqlite3"


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS matches (
                id TEXT PRIMARY KEY,
                game_id TEXT NOT NULL,
                rules_version TEXT NOT NULL,
                version INTEGER NOT NULL,
                seed INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                state_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                match_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                version INTEGER NOT NULL,
                seat INTEGER,
                event_json TEXT NOT NULL,
                state_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(match_id, seq)
            );
            CREATE TABLE IF NOT EXISTS model_calls (
                match_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                seat INTEGER NOT NULL,
                controller TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(match_id, version, seat)
            );
            CREATE TABLE IF NOT EXISTS match_players (
                match_id TEXT NOT NULL,
                seat INTEGER NOT NULL,
                name TEXT NOT NULL,
                backend TEXT NOT NULL,
                model TEXT,
                base_url TEXT,
                api_key_env TEXT,
                harness TEXT,
                wire_api TEXT,
                reasoning_effort TEXT,
                PRIMARY KEY(match_id, seat)
            );
            CREATE TABLE IF NOT EXISTS harness_events (
                match_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                seat INTEGER NOT NULL,
                seq INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(match_id, version, seat, seq)
            );
            """
        )
        columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(match_players)").fetchall()
        }
        if "harness" not in columns:
            self.connection.execute("ALTER TABLE match_players ADD COLUMN harness TEXT")
        if "wire_api" not in columns:
            self.connection.execute("ALTER TABLE match_players ADD COLUMN wire_api TEXT")
        if "reasoning_effort" not in columns:
            self.connection.execute("ALTER TABLE match_players ADD COLUMN reasoning_effort TEXT")
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def create(
        self, players: int, seed: int, game_id: str = "splendor",
        config: dict[str, Any] | None = None,
    ) -> tuple[str, int, dict[str, Any]]:
        game = get_game(game_id)
        state = game.setup(players, seed, config)
        match_id = uuid.uuid4().hex[:16]
        now = time.time()
        digest = game.state_hash(state)
        with self.connection:
            self.connection.execute(
                "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (match_id, game_id, game.rules_version, 0, seed,
                 json.dumps(state, separators=(",", ":")), digest, now, now),
            )
            event = {
                "type": "match_created", "game": game_id, "players": players,
                "seed": seed, "config": config or {},
            }
            self.connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (match_id, 0, 0, None, json.dumps(event, separators=(",", ":")), digest, now),
            )
        return match_id, 0, state

    def load(self, match_id: str) -> tuple[int, dict[str, Any], str]:
        row = self.connection.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        if row is None:
            raise MatchNotFound(match_id)
        return row["version"], json.loads(row["state_json"]), row["state_hash"]

    def game_id(self, match_id: str) -> str:
        row = self.connection.execute("SELECT game_id FROM matches WHERE id = ?", (match_id,)).fetchone()
        if row is None:
            raise MatchNotFound(match_id)
        return str(row["game_id"])

    def game(self, match_id: str):
        return get_game(self.game_id(match_id))

    def act(self, match_id: str, seat: int, expected_version: int, action: dict[str, Any]) -> tuple[int, dict[str, Any], list[dict[str, Any]]]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            version, state, _ = self.load(match_id)
            if version != expected_version:
                raise ConflictError(f"expected version {expected_version}, current version is {version}")
            game = self.game(match_id)
            next_state, events = game.apply_action(state, seat, action)
            next_version = version + 1
            digest = game.state_hash(next_state)
            now = time.time()
            updated = self.connection.execute(
                "UPDATE matches SET version=?, state_json=?, state_hash=?, updated_at=? WHERE id=? AND version=?",
                (next_version, json.dumps(next_state, separators=(",", ":")), digest, now, match_id, version),
            )
            if updated.rowcount != 1:
                raise ConflictError("match changed concurrently")
            next_seq = self.connection.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 FROM events WHERE match_id=?", (match_id,)
            ).fetchone()[0]
            for offset, event in enumerate(events):
                self.connection.execute(
                    "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (match_id, next_seq + offset, next_version, seat,
                     json.dumps(event, separators=(",", ":")), digest, now),
                )
            self.connection.commit()
            return next_version, next_state, events
        except Exception:
            self.connection.rollback()
            raise

    def events(self, match_id: str, after: int = -1) -> list[dict[str, Any]]:
        self.load(match_id)
        rows = self.connection.execute(
            "SELECT * FROM events WHERE match_id=? AND seq>? ORDER BY seq", (match_id, after)
        ).fetchall()
        return [
            {
                "seq": row["seq"], "version": row["version"], "seat": row["seat"],
                "event": json.loads(row["event_json"]), "state_hash": row["state_hash"],
            }
            for row in rows
        ]

    def record_controller_call(
        self, match_id: str, version: int, seat: int, controller: str, metadata: dict[str, Any]
    ) -> None:
        """Persist non-secret call metadata; prompts, responses, and keys are excluded."""
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO model_calls VALUES (?, ?, ?, ?, ?, ?)",
                (match_id, version, seat, controller,
                 json.dumps(metadata, separators=(",", ":")), time.time()),
            )

    def record_harness_event(
        self, match_id: str, version: int, seat: int, event: dict[str, Any],
    ) -> None:
        """Persist a redacted harness/tool event for audit and UI replay."""
        with self.connection:
            seq = self.connection.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 FROM harness_events "
                "WHERE match_id=? AND version=? AND seat=?", (match_id, version, seat),
            ).fetchone()[0]
            self.connection.execute(
                "INSERT INTO harness_events VALUES (?, ?, ?, ?, ?, ?)",
                (match_id, version, seat, seq,
                 json.dumps(event, separators=(",", ":")), time.time()),
            )

    def harness_events(self, match_id: str) -> list[dict[str, Any]]:
        self.load(match_id)
        rows = self.connection.execute(
            "SELECT version,seat,seq,event_json,created_at FROM harness_events "
            "WHERE match_id=? ORDER BY version,seat,seq", (match_id,),
        ).fetchall()
        return [{
            "version": row["version"], "seat": row["seat"], "seq": row["seq"],
            "event": json.loads(row["event_json"]), "created_at": row["created_at"],
        } for row in rows]

    def set_players(self, match_id: str, players: list[dict[str, Any]]) -> None:
        self.load(match_id)
        with self.connection:
            self.connection.execute("DELETE FROM match_players WHERE match_id=?", (match_id,))
            for seat, player in enumerate(players):
                self.connection.execute(
                    "INSERT INTO match_players "
                    "(match_id,seat,name,backend,model,base_url,api_key_env,harness,wire_api,reasoning_effort) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (match_id, seat, player["name"], player["backend"], player.get("model"),
                     player.get("base_url"), player.get("api_key_env"),
                     player["backend"] if player["backend"] in {"claude", "pi", "codex", "opencode"} else None,
                     player.get("wire_api"), player.get("reasoning_effort")),
                )

    def players(self, match_id: str) -> list[dict[str, Any]]:
        self.load(match_id)
        rows = self.connection.execute(
            "SELECT seat,name,backend,model,base_url,api_key_env,harness,wire_api,reasoning_effort "
            "FROM match_players WHERE match_id=? ORDER BY seat",
            (match_id,),
        ).fetchall()
        return [{key: row[key] for key in row.keys() if row[key] is not None} for row in rows]

    def replay(self, match_id: str) -> list[dict[str, Any]]:
        """Rebuild a match only from its seed and accepted actions."""
        _, stored_state, stored_digest = self.load(match_id)
        game = self.game(match_id)
        created = self.connection.execute(
            "SELECT event_json FROM events WHERE match_id=? AND seq=0", (match_id,)
        ).fetchone()
        created_event = json.loads(created["event_json"]) if created else {}
        state = game.setup(
            stored_state["player_count"], stored_state["seed"], created_event.get("config") or None,
        )
        frames = [{"version": 0, "state_hash": game.state_hash(state), "action": None}]
        accepted = self.connection.execute(
            "SELECT version, seat, event_json, state_hash FROM events "
            "WHERE match_id=? ORDER BY seq", (match_id,)
        ).fetchall()
        for row in accepted:
            event = json.loads(row["event_json"])
            if event.get("type") != "action_accepted":
                continue
            state, _ = game.apply_action(state, row["seat"], event["action"])
            digest = game.state_hash(state)
            if digest != row["state_hash"]:
                raise AssertionError(f"replay hash mismatch at version {row['version']}")
            frames.append({
                "version": row["version"], "seat": row["seat"],
                "action": event["action"], "state_hash": digest,
            })
        if game.state_hash(state) != stored_digest:
            raise AssertionError("replayed final state does not match stored state")
        return frames
