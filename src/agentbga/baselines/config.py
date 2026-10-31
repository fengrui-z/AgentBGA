"""Versioned, dependency-free baseline configuration."""
from __future__ import annotations

import math

BASELINE_BACKENDS = frozenset({'greedy', 'heuristic', 'ismcts'})
BASELINE_VERSION = '1'
COMMON = {'seed': 0, 'max_candidates': 32, 'time_limit_ms': 0}
DEFAULTS = {
    'greedy': {**COMMON},
    'heuristic': {**COMMON, 'position_weight': 1.0, 'opponent_weight': 0.25},
    'ismcts': {**COMMON, 'time_limit_ms': 1000, 'iterations': 128,
               'max_steps': 24, 'exploration': 1.4, 'position_weight': 1.0,
               'opponent_weight': 0.25},
}


def normalize_params(backend: str, value: object = None) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError('algorithm_params must be an object')
    defaults = DEFAULTS[backend]
    unknown = set(value) - set(defaults)
    if unknown:
        raise ValueError(f'{backend} has unknown algorithm_params: {sorted(unknown)}')
    result = {**defaults, **value}
    for key, number in result.items():
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise ValueError(f'algorithm_params.{key} must be a finite number')
        if key in {'seed', 'max_candidates', 'time_limit_ms', 'iterations', 'max_steps'}:
            if not isinstance(number, int):
                raise ValueError(f'algorithm_params.{key} must be an integer')
        if key != 'seed' and number < 0:
            raise ValueError(f'algorithm_params.{key} cannot be negative')
        if key in {'iterations', 'max_steps'} and number < 1:
            raise ValueError(f'algorithm_params.{key} must be positive')
    return result
