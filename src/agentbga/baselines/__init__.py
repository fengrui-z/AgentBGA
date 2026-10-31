"""Local non-LLM controllers. Each implementation can ship independently."""

from importlib import import_module
from .config import BASELINE_BACKENDS, BASELINE_VERSION, normalize_params


def build_baseline(config, game, seat):
    from .sampling import SUPPORTED_RULES

    if SUPPORTED_RULES.get(game.game_id) != game.rules_version:
        raise ValueError(
            f"baseline does not support {game.game_id}@{game.rules_version}"
        )
    try:
        module = import_module(f".{config.backend}", __name__)
    except ModuleNotFoundError as error:
        if error.name != f"{__name__}.{config.backend}":
            raise
        raise ValueError(f"{config.backend} is not installed in this branch") from error
    return module.Agent(
        game, seat, normalize_params(config.backend, config.algorithm_params)
    )
