"""Common representation of one player-facing decision step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DecisionStep:
    active_seat: int
    decision: str
    phase: str
    action_card: str | None = None
    remaining_plays: int = 0

    def to_dict(self, *, include_phase: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "active_seat": self.active_seat,
            "decision": self.decision,
            "action_card": self.action_card,
            "remaining_plays": self.remaining_plays,
        }
        if include_phase:
            result["phase"] = self.phase
        return result
