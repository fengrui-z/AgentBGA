"""Common contracts for deterministic AgentBGA game plugins."""

from __future__ import annotations

from typing import Any, NotRequired, Protocol, TypedDict, runtime_checkable


JsonObject = dict[str, Any]


class LegalAction(TypedDict):
    id: str
    action: JsonObject


class DomainEvent(TypedDict):
    type: str
    seat: NotRequired[int]


class GameRuleError(ValueError):
    """A stable, user-correctable game-rule rejection."""


@runtime_checkable
class GamePlugin(Protocol):
    game_id: str
    rules_version: str

    def describe(self) -> JsonObject: ...
    def setup(self, players: int, seed: int, config: JsonObject | None = None) -> JsonObject: ...
    def observe(self, state: JsonObject, seat: int) -> JsonObject: ...
    def decision_seats(self, state: JsonObject) -> list[int]: ...
    def legal_actions(self, state: JsonObject, seat: int) -> list[LegalAction]: ...
    def apply_action(
        self, state: JsonObject, seat: int, action: JsonObject,
    ) -> tuple[JsonObject, list[DomainEvent]]: ...
    def rankings(self, state: JsonObject) -> list[JsonObject]: ...
    def validate_state(self, state: JsonObject) -> None: ...
    def state_hash(self, state: JsonObject) -> str: ...
