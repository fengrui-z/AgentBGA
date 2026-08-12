"""SQLite persistence for matches and append-only action/event history."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import time
import uuid
from typing import Any

from . import splendor


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
                PRIMARY KEY(match_id, seat)
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def create(self, players: int, seed: int) -> tuple[str, int, dict[str, Any]]:
        state = splendor.new_game(players, seed)
        match_id = uuid.uuid4().hex[:16]
        now = time.time()
        digest = splendor.state_hash(state)
        with self.connection:
            self.connection.execute(
                "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (match_id, "splendor", splendor.RULES_VERSION, 0, seed,
                 json.dumps(state, separators=(",", ":")), digest, now, now),
            )
            event = {"type": "match_created", "players": players, "seed": seed}
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

    def act(self, match_id: str, seat: int, expected_version: int, action: dict[str, Any]) -> tuple[int, dict[str, Any], list[dict[str, Any]]]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            version, state, _ = self.load(match_id)
            if version != expected_version:
                raise ConflictError(f"expected version {expected_version}, current version is {version}")
            next_state, events = splendor.apply_action(state, seat, action)
            next_version = version + 1
            digest = splendor.state_hash(next_state)
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

    def set_players(self, match_id: str, players: list[dict[str, Any]]) -> None:
        self.load(match_id)
        with self.connection:
            self.connection.execute("DELETE FROM match_players WHERE match_id=?", (match_id,))
            for seat, player in enumerate(players):
                self.connection.execute(
                    "INSERT INTO match_players VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (match_id, seat, player["name"], player["backend"], player.get("model"),
                     player.get("base_url"), player.get("api_key_env")),
                )

    def players(self, match_id: str) -> list[dict[str, Any]]:
        self.load(match_id)
        rows = self.connection.execute(
            "SELECT seat,name,backend,model,base_url,api_key_env FROM match_players WHERE match_id=? ORDER BY seat",
            (match_id,),
        ).fetchall()
        return [{key: row[key] for key in row.keys() if row[key] is not None} for row in rows]

    def replay(self, match_id: str) -> list[dict[str, Any]]:
        """Rebuild a match only from its seed and accepted actions."""
        _, stored_state, stored_digest = self.load(match_id)
        state = splendor.new_game(stored_state["player_count"], stored_state["seed"])
        frames = [{"version": 0, "state_hash": splendor.state_hash(state), "action": None}]
        accepted = self.connection.execute(
            "SELECT version, seat, event_json, state_hash FROM events "
            "WHERE match_id=? ORDER BY seq", (match_id,)
        ).fetchall()
        for row in accepted:
            event = json.loads(row["event_json"])
            if event.get("type") != "action_accepted":
                continue
            state, _ = splendor.apply_action(state, row["seat"], event["action"])
            digest = splendor.state_hash(state)
            if digest != row["state_hash"]:
                raise AssertionError(f"replay hash mismatch at version {row['version']}")
            frames.append({
                "version": row["version"], "seat": row["seat"],
                "action": event["action"], "state_hash": digest,
            })
        if splendor.state_hash(state) != stored_digest:
            raise AssertionError("replayed final state does not match stored state")
        return frames
