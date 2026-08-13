"""Built-in game discovery and plugin lookup."""

from __future__ import annotations

from typing import Any

from . import ark_nova, splendor
from .game import GamePlugin


class _ModulePlugin:
    def __init__(self, module: Any, game_id: str):
        self.module = module
        self.game_id = game_id
        self.rules_version = module.RULES_VERSION

    def describe(self) -> dict[str, Any]:
        return self.module.describe()

    def setup(
        self, players: int, seed: int, config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.module.new_game(players, seed, config=config)

    def observe(self, state: dict[str, Any], seat: int) -> dict[str, Any]:
        return self.module.observe(state, seat)

    def legal_actions(self, state: dict[str, Any], seat: int) -> list[dict[str, Any]]:
        return self.module.legal_actions(state, seat)

    def apply_action(
        self, state: dict[str, Any], seat: int, action: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return self.module.apply_action(state, seat, action)

    def rankings(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return self.module.rankings(state)

    def validate_state(self, state: dict[str, Any]) -> None:
        self.module.validate_state(state)

    def state_hash(self, state: dict[str, Any]) -> str:
        return self.module.state_hash(state)


_PLUGINS: dict[str, GamePlugin] = {
    "splendor": _ModulePlugin(splendor, "splendor"),
    "ark_nova": _ModulePlugin(ark_nova, "ark_nova"),
}


def game_ids() -> tuple[str, ...]:
    return tuple(_PLUGINS)


def get_game(game_id: str) -> GamePlugin:
    try:
        return _PLUGINS[game_id]
    except KeyError as error:
        raise ValueError(f"unknown game: {game_id}") from error


def list_games() -> list[dict[str, Any]]:
    return [plugin.describe() for plugin in _PLUGINS.values()]
