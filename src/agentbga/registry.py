"""Built-in game discovery and plugin lookup."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from . import ark_nova, azul, brass_birmingham, century_spice_road, seven_wonders, splendor
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

    def decision_seats(self, state: dict[str, Any]) -> list[int]:
        """Return the seats that may decide from the same state snapshot.

        Most games have exactly one active seat.  Games with sealed simultaneous
        choices can opt in by exposing ``decision_seats`` from their module.
        """
        handler = getattr(self.module, "decision_seats", None)
        if handler is None:
            return [state["active_seat"]] if state.get("status") == "active" else []
        return list(handler(state))

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


class GameRegistry:
    """Validated game-plugin collection, independent from global application state."""

    def __init__(self, plugins: Iterable[GamePlugin] = ()):
        self._plugins: dict[str, GamePlugin] = {}
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: GamePlugin, *, replace: bool = False) -> None:
        if not isinstance(plugin, GamePlugin):
            raise TypeError("game plugin does not implement the GamePlugin contract")
        game_id = plugin.game_id
        if not isinstance(game_id, str) or not game_id or game_id.strip() != game_id:
            raise ValueError("game plugin must declare a stable non-empty game_id")
        if game_id in self._plugins and not replace:
            raise ValueError(f"game is already registered: {game_id}")
        description = plugin.describe()
        if description.get("id") != game_id:
            raise ValueError(f"game description id does not match plugin id: {game_id}")
        if description.get("rules_version") != plugin.rules_version:
            raise ValueError(f"game description rules version does not match plugin: {game_id}")
        self._plugins[game_id] = plugin

    def game_ids(self) -> tuple[str, ...]:
        return tuple(self._plugins)

    def get(self, game_id: str) -> GamePlugin:
        try:
            return self._plugins[game_id]
        except KeyError as error:
            raise ValueError(f"unknown game: {game_id}") from error

    def list_games(self) -> list[dict[str, Any]]:
        return [plugin.describe() for plugin in self._plugins.values()]


_REGISTRY = GameRegistry((
    _ModulePlugin(splendor, "splendor"),
    _ModulePlugin(azul, "azul"),
    _ModulePlugin(ark_nova, "ark_nova"),
    _ModulePlugin(brass_birmingham, "brass_birmingham"),
    _ModulePlugin(century_spice_road, "century_spice_road"),
    _ModulePlugin(seven_wonders, "seven_wonders"),
))


def game_ids() -> tuple[str, ...]:
    return _REGISTRY.game_ids()


def get_game(game_id: str) -> GamePlugin:
    return _REGISTRY.get(game_id)


def list_games() -> list[dict[str, Any]]:
    return _REGISTRY.list_games()
