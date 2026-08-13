"""Stable structured-action and canonical-serialization helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Iterable


JsonObject = dict[str, Any]


def canonical_json(value: Any) -> str:
    """Serialize protocol data in the canonical form used by IDs and hashes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def state_digest(state: JsonObject) -> str:
    """Return a portable digest for a JSON-serializable rules state."""
    return hashlib.sha256(canonical_json(state).encode()).hexdigest()


@dataclass(frozen=True)
class ActionSpace:
    """A version-scoped set of legal structured actions.

    ``version`` is intentionally supplied by the game.  It can be a turn
    number, decision counter, state version, or another deterministic marker.
    ActionSpace does not prescribe a game's turn model.
    """

    phase: str
    version: int | str
    actions: tuple[JsonObject, ...]
    prefix: str = "a"

    @classmethod
    def from_actions(
        cls, phase: str, version: int | str, actions: Iterable[JsonObject], *, prefix: str = "a",
    ) -> "ActionSpace":
        return cls(phase=phase, version=version, actions=tuple(actions), prefix=prefix)

    def action_id(self, action: JsonObject) -> str:
        material = f"{self.version}:{self.phase}:{canonical_json(action)}"
        return f"{self.prefix}-{hashlib.sha256(material.encode()).hexdigest()[:12]}"

    def wrapped(self) -> list[JsonObject]:
        return [{"id": self.action_id(action), "action": action} for action in self.actions]

    def require(
        self,
        submitted: JsonObject,
        *,
        error_factory: Callable[[str], Exception] = ValueError,
        message: str = "action is not legal in the current state",
    ) -> JsonObject:
        """Return the canonical legal object equal to ``submitted`` or reject it."""
        legal = {canonical_json(action): action for action in self.actions}
        try:
            return legal[canonical_json(submitted)]
        except KeyError as error:
            raise error_factory(message) from error
