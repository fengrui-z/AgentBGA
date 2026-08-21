"""Stable memory ownership and filesystem layout for harness participants."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .agents import PlayerConfig


def _digest(value: str, length: int = 20) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


@dataclass(frozen=True)
class MemoryIdentity:
    scope: str
    scope_id: str
    participant_id: str
    owner_key: str
    workspace: Path


def memory_identity(
    root: Path, config: PlayerConfig, match_id: str, seat: int,
) -> MemoryIdentity:
    """Resolve memory ownership separately from the participant's current seat."""
    scope = "series" if config.series_id else "match"
    scope_id = config.series_id or match_id
    participant_id = config.participant_id or f"seat-{seat}"
    scope_digest = _digest(f"{scope}\0{scope_id}")
    participant_digest = _digest(participant_id, 12)
    if scope == "series":
        workspace = (
            root / "_series" / f"series-{scope_digest}" /
            f"participant-{participant_digest}-{config.backend}"
        )
    else:
        workspace = root / match_id / f"seat-{seat}-{config.backend}"
    owner_key = json.dumps({
        "scope": scope,
        "id": scope_id,
        "participant_id": participant_id,
        "backend": config.backend,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return MemoryIdentity(scope, scope_id, participant_id, owner_key, workspace)


def stable_session_id(identity: MemoryIdentity) -> str:
    digest = _digest(identity.owner_key)
    return f"session-agentbga-{identity.scope}-{digest}"
