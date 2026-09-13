"""Game-specific observation adapters backed by a shared bounded resource service."""
from copy import deepcopy
from .brass import compact_observation, resource_aliases
from .resources import build_resources
from ..legal_action_query import MAX_REPLY_BYTES, reply_bytes

ADAPTERS = {"brass_birmingham": (compact_observation, resource_aliases)}


def prepare_view(observation, *, version, match_id, seat):
    adapter = ADAPTERS.get(observation.get("game"))
    if adapter is None:
        return None
    project, aliases = adapter
    compact, deferred_board = project(observation, version)
    resources = build_resources(observation, version, [match_id, seat], aliases=aliases(observation))
    if deferred_board is not None:
        extra = build_resources(deferred_board, version, [match_id, seat, "overview"],
                                root_ref="overview/board")
        resources["documents"].update(extra["documents"])
    if reply_bytes(compact) > MAX_REPLY_BYTES:
        raise ValueError("Brass observation summary exceeds its response budget")
    return deepcopy(compact), resources
