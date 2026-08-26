"""Closed, deterministic interpreter for Ark Nova semantic card operations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
import random
import re
from typing import Any, Callable, Mapping

from ..ark_nova_tracks import appeal_income
from ..mechanics import axial_hex_neighbors
from .state import clone_state, reputation_track_limit, validate_semantic_state


PREDICATE_OPS = frozenset({
    "all", "any", "not", "compare", "has_tag", "has_icon", "flag_set",
    "player_count", "in", "custom",
})
EFFECT_OPS = frozenset({
    "noop", "gain_money", "lose_money", "pay_money", "gain_x_token",
    "add_source_card_tokens",
    "gain_association_worker", "add_action_token",
    "sell_hand_cards", "tuck_hand_cards", "draw_keep_cards",
    "reveal_keep_animal", "take_display_card",
    "reveal_first_animal_size", "take_any_map_placement_bonus",
    "scavenge_discard", "dig_cards",
    "apply_interaction_tokens", "pilfer", "grant_hypnosis_action",
    "gain_icon_reward", "gain_tiered_icon_reward", "gain_tiered_reward",
    "reposition_action_card",
    "grant_extra_action",
    "draw_keep_final_scoring", "take_display_sponsors", "refill_card_display",
    "take_base_project", "introduce_base_project",
    "place_free_building", "take_map_reward_card",
    "choose_bonus_association_asset",
    "move_track", "advance_break", "draw_cards", "set_flag", "add_modifier",
    "trigger_icon_entered", "trigger_animal_played", "trigger_building_placed",
    "trigger_project_supported", "open_bonus_sponsor_play",
    "choose_one", "choose_effect_order", "choose_opponent", "for_each_opponent", "for_each_player",
    "discard_to_hand_limit", "clear_action_tokens", "recall_association_workers",
    "replenish_association", "refresh_display", "take_income", "reset_break",
    "add_score_entry", "custom",
    "choose_action_upgrade_or_worker", "choose_action_upgrade", "choose_conservation_reward",
    "discard_final_scoring_card", "take_conservation_bonus",
    "mark_final_scoring_discard_complete",
})
SYSTEM_EFFECT_OPS = frozenset({
    "discard_to_hand_limit", "clear_action_tokens", "recall_association_workers",
    "replenish_association", "refresh_display", "take_income", "reset_break",
    "choose_action_upgrade_or_worker", "choose_action_upgrade", "choose_conservation_reward",
    "discard_final_scoring_card", "take_conservation_bonus",
    "mark_final_scoring_discard_complete",
})
CONTENT_EFFECT_OPS = EFFECT_OPS - SYSTEM_EFFECT_OPS
EFFECT_TIMINGS = frozenset({
    "on_play", "immediate", "ongoing", "income", "on_trigger", "interaction",
    "end_of_game", "on_support", "on_release", "after_finishing", "system",
})
STATIC_MODIFIER_KINDS = frozenset({
    "animal_cost_discount", "association_project_strength",
    "engineer_extra_building", "repeat_release_projects",
    "base_project_wildcard", "large_animal_ignore_prerequisite",
    "waza_small_animal_program", "diversity_researcher",
    "archeologist_bonus",
})
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")


class SemanticRuleError(ValueError):
    """A deterministic rejection from the semantic rules interpreter."""


def simultaneous_effects(
    effects: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...], *,
    label: str = "Resolve simultaneous effects",
    timing: str = "immediate",
) -> list[dict[str, Any]]:
    """Wrap two or more same-time effects in the official player-order choice."""
    copied = [deepcopy(dict(effect)) for effect in effects]
    if len(copied) <= 1:
        return copied
    return [{
        "op": "choose_effect_order", "timing": timing,
        "args": {"label": label, "effects": copied},
    }]


def _official_kiosk_income(player: Mapping[str, Any]) -> int:
    """Return printed Break income from the current zoo-map topology.

    Each kiosk scores every adjacent qualifying building once, regardless of
    how many cells of the same polyhex touch it. Empty standard enclosures do
    not qualify; empty special enclosures do.
    """
    buildings = player.get("map", {}).get("buildings", [])
    kiosks = [building for building in buildings if building.get("type") == "kiosk"]
    qualifying = []
    for building in buildings:
        building_type = building.get("type")
        if (
            building_type == "pavilion"
            or building_type in {"petting_zoo", "reptile_house", "large_bird_aviary"}
            or (building_type == "standard_enclosure" and bool(building.get("occupied")))
            or (isinstance(building_type, str) and building_type.startswith("unique_sponsor_"))
        ):
            qualifying.append(building)

    income = 0
    for kiosk in kiosks:
        kiosk_cells = {
            (int(cell["q"]), int(cell["r"])) for cell in kiosk.get("cells", [])
        }
        adjacent = set().union(
            *(axial_hex_neighbors(cell) for cell in kiosk_cells),
        ) if kiosk_cells else set()
        for building in qualifying:
            building_cells = {
                (int(cell["q"]), int(cell["r"])) for cell in building.get("cells", [])
            }
            income += bool(adjacent & building_cells)
    return income


def settle_turn_venom(state: dict[str, Any], seat: int) -> dict[str, Any]:
    """Settle the one official Venom payment after all extra actions finish."""
    turn = state["turn"]
    reserved = int(turn.get("venom_reserved_money", 0))
    removed = bool(turn.get("venom_removed_this_turn", False))
    refunded = reserved if removed else 0
    if refunded:
        state["players"][seat]["money"] += refunded
    turn["venom_reserved_money"] = 0
    turn["venom_removed_this_turn"] = False
    return {"reserved": reserved, "refunded": refunded, "paid": reserved - refunded}


@dataclass(frozen=True)
class EvaluationContext:
    state: Mapping[str, Any]
    actor_seat: int
    target_seat: int | None = None
    card: Mapping[str, Any] | None = None
    bindings: Mapping[str, Any] | None = None


PredicateHandler = Callable[[Mapping[str, Any], EvaluationContext, "SemanticEngine"], bool]
EffectHandler = Callable[[dict[str, Any], Mapping[str, Any], "SemanticEngine"], list[dict[str, Any]]]


def _operation(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticRuleError(f"{label} must be an operation object")
    op = value.get("op")
    args = value.get("args")
    if not isinstance(op, str) or not _IDENTIFIER.fullmatch(op):
        raise SemanticRuleError(f"{label}.op must be a stable lowercase identifier")
    if not isinstance(args, Mapping):
        raise SemanticRuleError(f"{label}.args must be an object")
    return value


class SemanticEngine:
    """Execute only registered semantic operations; content is never evaluated as code."""

    def __init__(self) -> None:
        self._predicate_handlers: dict[str, PredicateHandler] = {}
        self._effect_handlers: dict[str, EffectHandler] = {}

    def register_predicate(self, custom_id: str, handler: PredicateHandler) -> None:
        self._register(self._predicate_handlers, custom_id, handler)

    def register_effect(self, custom_id: str, handler: EffectHandler) -> None:
        self._register(self._effect_handlers, custom_id, handler)

    @staticmethod
    def _register(registry: dict[str, Any], custom_id: str, handler: Any) -> None:
        if not isinstance(custom_id, str) or _IDENTIFIER.fullmatch(custom_id) is None:
            raise ValueError("custom semantic handler ID must be stable and lowercase")
        if custom_id in registry:
            raise ValueError(f"custom semantic handler is already registered: {custom_id}")
        if not callable(handler):
            raise TypeError("custom semantic handler must be callable")
        registry[custom_id] = handler

    def evaluate(self, predicate: Mapping[str, Any], context: EvaluationContext) -> bool:
        operation = _operation(predicate, "predicate")
        op = operation["op"]
        args = operation["args"]
        if op not in PREDICATE_OPS:
            raise SemanticRuleError(f"unknown predicate operation: {op}")
        if op == "all":
            return all(self.evaluate(item, context) for item in self._conditions(args))
        if op == "any":
            return any(self.evaluate(item, context) for item in self._conditions(args))
        if op == "not":
            condition = args.get("condition")
            return not self.evaluate(_operation(condition, "predicate.args.condition"), context)
        if op == "compare":
            left = self.value(args.get("left"), context)
            right = self.value(args.get("right"), context)
            operator = args.get("operator")
            comparisons = {
                "==": lambda: left == right,
                "!=": lambda: left != right,
                ">=": lambda: left >= right,
                ">": lambda: left > right,
                "<=": lambda: left <= right,
                "<": lambda: left < right,
            }
            if operator not in comparisons:
                raise SemanticRuleError("compare.operator must be ==, !=, >=, >, <=, or <")
            try:
                return bool(comparisons[operator]())
            except TypeError as error:
                raise SemanticRuleError("compared semantic values are incompatible") from error
        if op in {"has_tag", "has_icon"}:
            kind = "tags" if op == "has_tag" else "icons"
            key = args.get("tag" if op == "has_tag" else "icon")
            if not isinstance(key, str) or not key:
                raise SemanticRuleError(f"{op} requires a stable {kind[:-1]} ID")
            seat = self._selected_seat(args.get("seat", "actor"), context)
            count = self._integer(args.get("count", 1), context, minimum=0)
            return int(context.state["players"][seat][kind].get(key, 0)) >= count
        if op == "flag_set":
            flag = args.get("flag")
            if not isinstance(flag, str) or not flag:
                raise SemanticRuleError("flag_set requires a flag ID")
            seat = self._selected_seat(args.get("seat", "actor"), context)
            return bool(context.state["players"][seat]["flags"].get(flag, False)) is bool(
                args.get("value", True)
            )
        if op == "player_count":
            expected = self._integer(args.get("count"), context, minimum=1, maximum=4)
            return int(context.state["player_count"]) == expected
        if op == "in":
            values = args.get("values")
            if not isinstance(values, list):
                raise SemanticRuleError("in.values must be an array")
            return self.value(args.get("value"), context) in [self.value(item, context) for item in values]
        custom_id = operation.get("custom_id")
        if not isinstance(custom_id, str) or custom_id not in self._predicate_handlers:
            raise SemanticRuleError(f"unregistered custom predicate: {custom_id}")
        return bool(self._predicate_handlers[custom_id](args, context, self))

    @staticmethod
    def _conditions(args: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        values = args.get("conditions")
        if not isinstance(values, list):
            raise SemanticRuleError("conditions must be an array")
        return [_operation(value, "condition") for value in values]

    def value(self, expression: Any, context: EvaluationContext) -> Any:
        if expression is None or isinstance(expression, (str, int, bool)):
            return expression
        if not isinstance(expression, Mapping):
            raise SemanticRuleError("semantic value must be a literal, reference, or calculation")
        if set(expression) == {"ref"}:
            return self._reference(expression["ref"], context)
        if set(expression) != {"calc", "values"}:
            raise SemanticRuleError("semantic value object must contain ref or calc/values")
        operation = expression["calc"]
        values = expression["values"]
        if not isinstance(values, list) or not values:
            raise SemanticRuleError("calculation values must be a non-empty array")
        resolved = [self._integer(value, context) for value in values]
        if operation == "add":
            return sum(resolved)
        if operation == "multiply":
            result = 1
            for value in resolved:
                result *= value
            return result
        if operation == "minimum":
            return min(resolved)
        if operation == "maximum":
            return max(resolved)
        if operation == "floor_divide" and len(resolved) == 2:
            if resolved[1] == 0:
                raise SemanticRuleError("cannot divide a semantic value by zero")
            return resolved[0] // resolved[1]
        raise SemanticRuleError(f"unsupported semantic calculation: {operation}")

    def _reference(self, reference: Any, context: EvaluationContext) -> Any:
        if not isinstance(reference, str) or not reference:
            raise SemanticRuleError("semantic reference must be a non-empty string")
        root, separator, path = reference.partition(".")
        if not separator:
            raise SemanticRuleError(f"semantic reference requires a root and path: {reference}")
        if root in {"actor", "target"}:
            seat = context.actor_seat if root == "actor" else context.target_seat
            if seat is None:
                raise SemanticRuleError("target reference used outside a targeted effect")
            return self._player_reference(context.state["players"][seat], path)
        if root == "card":
            if context.card is None or not path.startswith("facts."):
                raise SemanticRuleError("card references are limited to card.facts")
            return self._mapping_path(context.card, path)
        if root == "state":
            if path == "player_count":
                return context.state["player_count"]
            if path in {"break.position", "break.limit", "break.count"}:
                return self._mapping_path(context.state, path)
            raise SemanticRuleError(f"state reference is not public to card semantics: {path}")
        if root == "binding":
            if context.bindings is None:
                raise SemanticRuleError("binding reference used without choice bindings")
            return self._mapping_path(context.bindings, path)
        raise SemanticRuleError(f"unknown semantic reference root: {root}")

    @staticmethod
    def _mapping_path(value: Mapping[str, Any], path: str) -> Any:
        current: Any = value
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                raise SemanticRuleError(f"semantic reference does not resolve: {path}")
            current = current[part]
        return current

    @staticmethod
    def _player_reference(player: Mapping[str, Any], path: str) -> Any:
        direct = {"money", "x_tokens", "hand_limit"}
        if path in direct:
            return player[path]
        if path == "hand_count":
            return len(player["hand"])
        if path == "played_card_count":
            return len(player["played_cards"])
        if path == "supported_project_count":
            return len(player["supported_projects"])
        if path == "partner_zoo_count":
            return len(player["partner_zoos"])
        if path == "university_count":
            return len(player["universities"])
        if path == "kiosk_count":
            return sum(
                building.get("type") == "kiosk"
                for building in player["map"]["buildings"]
            )
        if path == "side_entrance_income_building_count":
            buildings = player["map"]["buildings"]
            entrance = next(
                (building for building in buildings
                 if building.get("type") == "unique_sponsor_257"),
                None,
            )
            if entrance is None:
                return 0
            adjacent = set().union(*(
                axial_hex_neighbors((cell["q"], cell["r"]))
                for cell in entrance["cells"]
            ))
            return sum(
                building is not entrance
                and not (
                    building.get("type") == "standard_enclosure"
                    and not building.get("occupied")
                )
                and any(
                    (cell["q"], cell["r"]) in adjacent
                    for cell in building["cells"]
                )
                for building in buildings
            )
        if path in {"small_animal_count", "large_animal_count"}:
            small = path == "small_animal_count"
            result = 0
            for card in player["played_cards"]:
                if card.get("kind") != "animal":
                    continue
                facts = card.get("facts", {})
                size = facts.get("enclosure_size") if isinstance(facts, Mapping) else None
                special = facts.get("special_enclosure", "") if isinstance(facts, Mapping) else ""
                is_small = (
                    isinstance(size, int) and not isinstance(size, bool) and size <= 2
                ) or (
                    isinstance(special, str) and special.startswith("Petting Zoo")
                )
                is_large = (
                    isinstance(size, int) and not isinstance(size, bool) and size >= 4
                    and not is_small
                )
                result += is_small if small else is_large
            return result
        if path in {"rock_requirement_total", "water_requirement_total"}:
            requirement = path.removesuffix("_total")
            return sum(
                int(card.get("facts", {}).get(requirement, 0) or 0)
                for card in player["played_cards"]
                if isinstance(card.get("facts"), Mapping)
            )
        if path in {"rock_icon_total", "water_icon_total"}:
            icon = path.removesuffix("_icon_total")
            # The authoritative counter is updated when a card enters/leaves
            # play and includes its printed terrain-adjacency symbols.
            return int(player["icons"].get(icon, 0))
        if path in {
            "distinct_animal_category_count",
            "distinct_continent_count",
            "distinct_continent_animal_category_count",
        }:
            category_icons = {
                "bear", "bird", "herbivore", "pet", "predator", "primate", "reptile",
            }
            continents = {"africa", "americas", "asia", "australia", "europe"}
            if path == "distinct_continent_count":
                category_icons = continents
            elif path == "distinct_continent_animal_category_count":
                category_icons |= continents
            return sum(int(player["icons"].get(icon, 0)) > 0 for icon in category_icons)
        if path in {"map_complete", "all_border_buildable_spaces_covered"}:
            zoo_map = player["map"]
            occupied = {
                (cell["q"], cell["r"])
                for building in zoo_map["buildings"] for cell in building["cells"]
            }
            buildable = {
                (cell["q"], cell["r"])
                for cell in zoo_map["cells"] if cell["terrain"] == "buildable"
            }
            if path == "map_complete":
                return buildable <= occupied
            coordinates = {
                (cell["q"], cell["r"]) for cell in zoo_map["cells"]
            }
            border = {
                coordinate for coordinate in buildable
                if any(neighbor not in coordinates for neighbor in axial_hex_neighbors(coordinate))
            }
            return border <= occupied
        if path in {"water_spaces_connected", "rock_spaces_connected"}:
            terrain_kind = path.removesuffix("_spaces_connected")
            zoo_map = player["map"]
            occupied = {
                (cell["q"], cell["r"])
                for building in zoo_map["buildings"] for cell in building["cells"]
            }
            terrain_cells = {
                (cell["q"], cell["r"])
                for cell in zoo_map["cells"]
                if cell["terrain"] == terrain_kind
                and (cell["q"], cell["r"]) not in occupied
            }
            return all(axial_hex_neighbors(cell) & occupied for cell in terrain_cells)
        if path in {
            "connected_water_space_count", "unconnected_water_space_count",
            "connected_rock_space_count", "unconnected_rock_space_count",
            "connected_uncovered_border_space_count",
            "connected_placement_bonus_space_count",
            "unconnected_placement_bonus_space_count",
            "empty_buildable_group_of_six_count",
        }:
            zoo_map = player["map"]
            occupied = {
                (cell["q"], cell["r"])
                for building in zoo_map["buildings"] for cell in building["cells"]
            }
            cells_by_coordinate = {
                (cell["q"], cell["r"]): cell for cell in zoo_map["cells"]
            }
            if path.endswith("water_space_count") or path.endswith("rock_space_count"):
                terrain = "water" if "water" in path else "rock"
                candidates = {
                    coordinate for coordinate, cell in cells_by_coordinate.items()
                    if cell["terrain"] == terrain and coordinate not in occupied
                }
                connected = {
                    coordinate for coordinate in candidates
                    if axial_hex_neighbors(coordinate) & occupied
                }
                return len(candidates - connected) if path.startswith("unconnected") else len(connected)
            if "placement_bonus" in path:
                candidates = {
                    coordinate for coordinate, cell in cells_by_coordinate.items()
                    if cell.get("placement_bonus") is not None
                }
                connected = {
                    coordinate for coordinate in candidates
                    if axial_hex_neighbors(coordinate) & occupied
                }
                return len(candidates - connected) if path.startswith("unconnected") else len(connected)
            buildable = {
                coordinate for coordinate, cell in cells_by_coordinate.items()
                if cell["terrain"] == "buildable"
            }
            empty = buildable - occupied
            if path == "connected_uncovered_border_space_count":
                map_coordinates = set(cells_by_coordinate)
                border = {
                    coordinate for coordinate in empty
                    if any(
                        neighbor not in map_coordinates
                        for neighbor in axial_hex_neighbors(coordinate)
                    )
                }
                return sum(bool(axial_hex_neighbors(cell) & occupied) for cell in border)
            groups = 0
            unseen = set(empty)
            while unseen:
                frontier = {unseen.pop()}
                component_size = 0
                while frontier:
                    current = frontier.pop()
                    component_size += 1
                    neighbors = axial_hex_neighbors(current) & unseen
                    unseen -= neighbors
                    frontier |= neighbors
                groups += component_size // 6
            return groups
        if path == "occupied_standard_enclosure_size_1_count":
            return sum(
                building.get("type") == "standard_enclosure"
                and building.get("size") == 1
                and bool(building.get("occupied"))
                for building in player["map"]["buildings"]
            )
        action_prefix = "action_cards."
        if path.startswith(action_prefix) and path.endswith(".upgraded"):
            action = path[len(action_prefix):-len(".upgraded")]
            for card in player["action_cards"]:
                if card["action"] == action:
                    return bool(card["upgraded"])
            raise SemanticRuleError(f"unknown action-card reference: {action}")
        prefix, separator, key = path.partition(".")
        if separator and prefix in {"tracks", "tags", "icons", "flags", "income"}:
            default: Any = False if prefix == "flags" else 0
            return player[prefix].get(key, default)
        if separator and prefix == "association_workers" and key in {"active", "reserve"}:
            return player[prefix][key]
        raise SemanticRuleError(f"player reference is not public to card semantics: {path}")

    def _integer(
        self, expression: Any, context: EvaluationContext, *,
        minimum: int | None = None, maximum: int | None = None,
    ) -> int:
        value = self.value(expression, context)
        if not isinstance(value, int) or isinstance(value, bool):
            raise SemanticRuleError("semantic amount must resolve to an integer")
        if minimum is not None and value < minimum:
            raise SemanticRuleError(f"semantic amount must be at least {minimum}")
        if maximum is not None and value > maximum:
            raise SemanticRuleError(f"semantic amount must be at most {maximum}")
        return value

    @staticmethod
    def _selected_seat(selector: Any, context: EvaluationContext) -> int:
        if selector == "actor":
            return context.actor_seat
        if selector == "target" and context.target_seat is not None:
            return context.target_seat
        if isinstance(selector, int) and not isinstance(selector, bool) and 0 <= selector < context.state["player_count"]:
            return selector
        raise SemanticRuleError("seat selector must be actor, target, or a valid seat")

    def start_effects(
        self,
        state: dict[str, Any],
        actor_seat: int,
        effects: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
        *,
        source_id: str,
        card: Mapping[str, Any] | None = None,
        timing: str | None = None,
        completion: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        next_state = clone_state(state)
        self._require_idle(next_state)
        self._require_seat(next_state, actor_seat)
        selected = [effect for effect in effects if timing is None or effect.get("timing") == timing]
        frames = self._frames(selected, actor_seat, None, source_id, card, {})
        next_state["resolution"]["queue"] = frames
        next_state["resolution"]["completion"] = deepcopy(completion)
        events: list[dict[str, Any]] = []
        self._drain(next_state, events)
        validate_semantic_state(next_state)
        return next_state, events

    def trigger_modifiers(
        self,
        state: dict[str, Any],
        trigger: str,
        *,
        actor_seat: int,
        owner_seats: list[int] | tuple[int, ...] | None = None,
        bindings: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Resolve registered ongoing effects for a named game event.

        ``actor_seat`` is the player who caused the event; modifier effects
        target their owner by default. Callers control owner order explicitly,
        which preserves official player-order resolution when effects interact.
        """
        if not isinstance(trigger, str) or not trigger:
            raise SemanticRuleError("modifier trigger must be a non-empty string")
        next_state = clone_state(state)
        self._require_idle(next_state)
        self._require_seat(next_state, actor_seat)
        owners = list(owner_seats) if owner_seats is not None else self._clockwise_seats(
            next_state, actor_seat, include_actor=True,
        )
        for owner in owners:
            self._require_seat(next_state, owner)
        frames = self._matching_modifier_frames(
            next_state, trigger, actor_seat, owners, bindings or {},
        )
        frames = self._ordered_frames(
            frames, actor_seat=actor_seat, label=f"Order {trigger} effects",
        )
        next_state["resolution"]["queue"] = frames
        events = [{
            "type": "semantic_trigger_started",
            "trigger": trigger,
            "actor_seat": actor_seat,
            "modifier_count": len(frames),
        }]
        self._drain(next_state, events)
        validate_semantic_state(next_state)
        return next_state, events

    @staticmethod
    def _require_idle(state: Mapping[str, Any]) -> None:
        resolution = state["resolution"]
        if resolution["queue"] or resolution["pending_choice"] is not None:
            raise SemanticRuleError("another semantic resolution is already in progress")

    @staticmethod
    def _require_seat(state: Mapping[str, Any], seat: int) -> None:
        if not isinstance(seat, int) or isinstance(seat, bool) or not 0 <= seat < state["player_count"]:
            raise SemanticRuleError("semantic actor seat is out of range")

    @staticmethod
    def _frames(
        effects: Any,
        actor_seat: int,
        target_seat: int | None,
        source_id: str,
        card: Mapping[str, Any] | None,
        bindings: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        if not isinstance(effects, (list, tuple)):
            raise SemanticRuleError("effects must be an array")
        frames = []
        for effect in effects:
            operation = _operation(effect, "effect")
            timing = operation.get("timing")
            if timing is not None and timing not in EFFECT_TIMINGS:
                raise SemanticRuleError(f"unknown effect timing: {timing}")
            frames.append({
                "operation": deepcopy(dict(operation)),
                "actor_seat": actor_seat,
                "target_seat": operation.get("_semantic_target_seat", target_seat),
                "source_id": operation.get("_semantic_source_id", source_id),
                "card": deepcopy(dict(operation.get("_semantic_card", card)))
                if operation.get("_semantic_card", card) is not None else None,
                "bindings": deepcopy(dict(operation.get("_semantic_bindings", bindings))),
            })
        return frames

    def _context(self, state: Mapping[str, Any], frame: Mapping[str, Any]) -> EvaluationContext:
        return EvaluationContext(
            state=state,
            actor_seat=frame["actor_seat"],
            target_seat=frame.get("target_seat"),
            card=frame.get("card"),
            bindings=frame.get("bindings"),
        )

    def _drain(self, state: dict[str, Any], events: list[dict[str, Any]]) -> None:
        resolution = state["resolution"]
        while resolution["queue"] and resolution["pending_choice"] is None:
            frame = resolution["queue"].pop(0)
            operation = frame["operation"]
            condition = operation.get("when")
            if condition is not None and not self.evaluate(condition, self._context(state, frame)):
                events.append({
                    "type": "semantic_effect_skipped",
                    "source_id": frame["source_id"],
                    "op": operation["op"],
                })
                continue
            self._execute_frame(state, frame, events)
        if not resolution["queue"] and resolution["pending_choice"] is None:
            self._complete(state, events)

    def _execute_frame(
        self, state: dict[str, Any], frame: dict[str, Any], events: list[dict[str, Any]],
    ) -> None:
        operation = frame["operation"]
        op = operation["op"]
        if op not in EFFECT_OPS:
            raise SemanticRuleError(f"unknown effect operation: {op}")
        if op == "choose_one":
            self._choose_one(state, frame)
            return
        if op == "choose_effect_order":
            self._choose_effect_order(state, frame)
            return
        if op == "choose_opponent":
            self._choose_opponent(state, frame)
            return
        if op in {"for_each_opponent", "for_each_player"}:
            self._expand_seats(state, frame, opponents_only=op == "for_each_opponent")
            return
        if op == "discard_to_hand_limit":
            self._discard_to_limit(state, frame, events)
            return
        if op == "choose_action_upgrade_or_worker":
            self._choose_action_upgrade_or_worker(state, frame)
            return
        if op == "choose_action_upgrade":
            self._choose_action_upgrade(state, frame)
            return
        if op == "choose_conservation_reward":
            self._choose_conservation_reward(state, frame)
            return
        if op == "discard_final_scoring_card":
            self._discard_final_scoring_card(state, frame)
            return
        if op in {"sell_hand_cards", "tuck_hand_cards"}:
            self._select_hand_cards(state, frame, tuck=op == "tuck_hand_cards")
            return
        if op in {"draw_keep_cards", "reveal_keep_animal"}:
            self._draw_keep_cards(state, frame, animals_only=op == "reveal_keep_animal")
            return
        if op == "take_any_map_placement_bonus":
            self._take_any_map_placement_bonus(state, frame)
            return
        if op == "take_display_card":
            self._take_display_card(state, frame)
            return
        if op == "scavenge_discard":
            self._scavenge_discard(state, frame)
            return
        if op == "dig_cards":
            self._dig_cards(state, frame)
            return
        if op == "apply_interaction_tokens":
            self._apply_interaction_tokens(state, frame, events)
            return
        if op == "pilfer":
            self._pilfer(state, frame, events)
            return
        if op == "grant_hypnosis_action":
            self._hypnosis(state, frame, events)
            return
        if op == "reposition_action_card":
            self._reposition_action_card(state, frame)
            return
        if op == "draw_keep_final_scoring":
            self._draw_keep_final_scoring(state, frame)
            return
        if op == "take_base_project":
            self._take_base_project(state, frame)
            return
        if op == "place_free_building":
            self._place_free_building(state, frame)
            return
        if op == "take_map_reward_card":
            self._take_map_reward_card(state, frame)
            return
        if op == "choose_bonus_association_asset":
            self._choose_bonus_association_asset(state, frame)
            return
        events.extend(self._apply_effect(state, frame))

    def _open_choice(
        self, state: dict[str, Any], frame: Mapping[str, Any], *, seat: int,
        prompt: str, options: list[dict[str, Any]], minimum: int = 1, maximum: int = 1,
        continuation: Mapping[str, Any] | None = None,
    ) -> None:
        if not options and minimum:
            raise SemanticRuleError("semantic choice has no legal options")
        resolution = state["resolution"]
        choice_id = f"semantic-choice-{resolution['next_choice_id']}"
        resolution["next_choice_id"] += 1
        resolution["pending_choice"] = {
            "choice_id": choice_id,
            "seat": seat,
            "prompt": prompt,
            "minimum": minimum,
            "maximum": maximum,
            "options": options,
            "continuation": deepcopy(dict(continuation)) if continuation is not None else None,
            "frame": {
                key: deepcopy(frame.get(key))
                for key in ("actor_seat", "target_seat", "source_id", "card", "bindings")
            },
        }

    def _choose_one(self, state: dict[str, Any], frame: Mapping[str, Any]) -> None:
        args = frame["operation"]["args"]
        raw_options = args.get("options")
        if not isinstance(raw_options, list):
            raise SemanticRuleError("choose_one.options must be an array")
        options = []
        seen = set()
        for raw in raw_options:
            if not isinstance(raw, Mapping):
                raise SemanticRuleError("choose_one option must be an object")
            option_id = raw.get("id")
            if not isinstance(option_id, str) or not _IDENTIFIER.fullmatch(option_id) or option_id in seen:
                raise SemanticRuleError("choose_one option IDs must be stable and unique")
            seen.add(option_id)
            condition = raw.get("when")
            if condition is not None and not self.evaluate(condition, self._context(state, frame)):
                continue
            effects = raw.get("effects")
            if not isinstance(effects, list):
                raise SemanticRuleError("choose_one option effects must be an array")
            options.append({
                "id": option_id,
                "label": str(raw.get("label", option_id)),
                "effects": deepcopy(effects),
                "target_seat": frame.get("target_seat"),
                "bindings": deepcopy(frame.get("bindings", {})),
            })
        self._open_choice(
            state,
            frame,
            seat=frame["actor_seat"],
            prompt=str(args.get("prompt", "Choose one effect")),
            options=options,
        )

    def _choose_effect_order(self, state: dict[str, Any], frame: Mapping[str, Any]) -> None:
        args = frame["operation"]["args"]
        effects = args.get("effects")
        if not isinstance(effects, list) or not effects:
            raise SemanticRuleError("choose_effect_order.effects must be a non-empty array")
        if len(effects) == 1:
            state["resolution"]["queue"][0:0] = self._frames(
                effects, frame["actor_seat"], frame.get("target_seat"),
                frame["source_id"], frame.get("card"), frame.get("bindings", {}),
            )
            return
        options = []
        for index, effect in enumerate(effects):
            operation = _operation(effect, "ordered effect")
            options.append({
                "id": f"effect-{index}",
                "label": str(operation.get("label", operation["op"])),
                "value": {"index": index},
            })
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        self._open_choice(
            state, frame, seat=seat,
            prompt=str(args.get("label", "Resolve simultaneous effects")),
            options=options,
            continuation={
                "type": "choose_effect_order", "seat": seat,
                "effects": deepcopy(effects),
                "actor_seat": frame["actor_seat"],
                "target_seat": frame.get("target_seat"),
                "source_id": frame["source_id"],
                "card": deepcopy(frame.get("card")),
                "bindings": deepcopy(frame.get("bindings", {})),
            },
        )

    def _choose_opponent(self, state: dict[str, Any], frame: Mapping[str, Any]) -> None:
        args = frame["operation"]["args"]
        effects = args.get("effects")
        if not isinstance(effects, list):
            raise SemanticRuleError("choose_opponent.effects must be an array")
        actor = frame["actor_seat"]
        options = []
        for target in self._clockwise_seats(state, actor, include_actor=False):
            targeted = {**frame, "target_seat": target}
            condition = args.get("condition")
            if condition is not None and not self.evaluate(condition, self._context(state, targeted)):
                continue
            options.append({
                "id": f"seat-{target}",
                "label": f"Seat {target}",
                "effects": deepcopy(effects),
                "target_seat": target,
                "bindings": {**frame.get("bindings", {}), "target_seat": target},
            })
        self._open_choice(
            state,
            frame,
            seat=actor,
            prompt=str(args.get("prompt", "Choose an opponent")),
            options=options,
        )

    @staticmethod
    def _clockwise_seats(
        state: Mapping[str, Any], actor: int, *, include_actor: bool,
    ) -> list[int]:
        count = state["player_count"]
        start = 0 if include_actor else 1
        end = count if include_actor else count
        return [((actor + offset) % count) for offset in range(start, end)]

    def _expand_seats(
        self, state: dict[str, Any], frame: Mapping[str, Any], *, opponents_only: bool,
    ) -> None:
        effects = frame["operation"]["args"].get("effects")
        if not isinstance(effects, list):
            raise SemanticRuleError("for_each effect requires an effects array")
        targets = self._clockwise_seats(
            state, frame["actor_seat"], include_actor=not opponents_only,
        )
        expanded = []
        for target in targets:
            expanded.extend(self._frames(
                effects,
                frame["actor_seat"],
                target,
                frame["source_id"],
                frame.get("card"),
                {**frame.get("bindings", {}), "target_seat": target},
            ))
        state["resolution"]["queue"][0:0] = expanded

    def _discard_to_limit(
        self, state: dict[str, Any], frame: Mapping[str, Any], events: list[dict[str, Any]],
    ) -> None:
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        player = state["players"][seat]
        surplus = max(0, len(player["hand"]) - player["hand_limit"])
        if not surplus:
            events.append({"type": "break_hand_limit_checked", "seat": seat, "discarded": 0})
            return
        options = []
        for index, card in enumerate(player["hand"]):
            card_id = card.get("id")
            if not isinstance(card_id, str):
                raise SemanticRuleError("cards selected by semantics require stable IDs")
            options.append({"id": card_id, "label": str(card.get("display_title", card_id)), "value": index})
        self._open_choice(
            state,
            frame,
            seat=seat,
            prompt="Discard down to the hand limit",
            options=options,
            minimum=surplus,
            maximum=surplus,
            continuation={"type": "discard_selected_cards", "seat": seat},
        )

    def _choose_action_upgrade_or_worker(
        self, state: dict[str, Any], frame: Mapping[str, Any],
    ) -> None:
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        player = state["players"][seat]
        options = [
            {
                "id": f"upgrade-{card['action']}",
                "label": f"Upgrade {card['action']}",
                "value": {"kind": "upgrade", "action": card["action"]},
            }
            for card in sorted(player["action_cards"], key=lambda item: item["position"])
            if not card["upgraded"]
        ]
        if player["association_workers"]["reserve"] > 0:
            options.append({
                "id": "activate-association-worker",
                "label": "Activate an association worker",
                "value": {"kind": "worker"},
            })
        self._open_choice(
            state,
            frame,
            seat=seat,
            prompt="Upgrade an Action card or activate an association worker",
            options=options,
            continuation={"type": "conservation_2_reward", "seat": seat},
        )

    def _choose_action_upgrade(
        self, state: dict[str, Any], frame: Mapping[str, Any],
    ) -> None:
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        options = [{
            "id": f"upgrade-{card['action']}",
            "label": f"Upgrade {card['action']}",
            "value": {"action": card["action"]},
        } for card in sorted(
            state["players"][seat]["action_cards"], key=lambda item: item["position"],
        ) if not card["upgraded"]]
        self._open_choice(
            state, frame, seat=seat, prompt="Upgrade one Action card",
            options=options,
            continuation={"type": "action_upgrade_reward", "seat": seat},
        )

    def _choose_conservation_reward(
        self, state: dict[str, Any], frame: Mapping[str, Any],
    ) -> None:
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        at = frame["operation"]["args"].get("at")
        if at not in (5, 8):
            raise SemanticRuleError("conservation reward must be for space 5 or 8")
        options = []
        if state["player_count"] >= 3:
            options.append({
                "id": "money-5",
                "label": "Take 5 money",
                "effects": [{
                    "op": "gain_money", "args": {"amount": 5}, "timing": "system",
                }],
                "target_seat": seat,
            })
        for tile in state.get("conservation_bonus_slots", {}).get(str(at), []):
            if not tile.get("available", True):
                continue
            tile_id = tile.get("id")
            if not isinstance(tile_id, str) or _IDENTIFIER.fullmatch(tile_id) is None:
                raise SemanticRuleError("conservation bonus tile requires a stable ID")
            if not self._bonus_tile_usable(state, seat, tile):
                continue
            options.append({
                "id": f"bonus-{tile_id}",
                "label": str(tile.get("label", tile_id)),
                "effects": [{
                    "op": "take_conservation_bonus",
                    "args": {"at": at, "bonus_id": tile_id},
                    "timing": "system",
                }],
                "target_seat": seat,
            })
        self._open_choice(
            state,
            frame,
            seat=seat,
            prompt=f"Choose the conservation reward at {at}",
            options=options,
        )

    def _bonus_tile_usable(
        self, state: Mapping[str, Any], seat: int, tile: Mapping[str, Any],
    ) -> bool:
        for effect in tile.get("effects", []):
            if isinstance(effect, Mapping) and effect.get("op") == "choose_bonus_association_asset":
                asset = effect.get("args", {}).get("asset")
                return bool(self._bonus_association_asset_options(state, seat, asset))
        return True

    @staticmethod
    def _bonus_association_asset_options(
        state: Mapping[str, Any], seat: int, asset: Any,
    ) -> list[dict[str, Any]]:
        player = state["players"][seat]
        if asset == "university":
            owned = set(player["universities"])
            supply = state["association_board"]["universities"]
            maximum = 3
        elif asset == "partner_zoo":
            association_upgraded = next(
                card["upgraded"] for card in player["action_cards"]
                if card["action"] == "association"
            )
            if len(player["partner_zoos"]) >= 2 and not association_upgraded:
                return []
            owned = set(player["partner_zoos"])
            supply = state["association_board"]["partner_zoos"]
            maximum = 4
        else:
            raise SemanticRuleError("unknown bonus association asset")
        if len(owned) >= maximum:
            return []
        return [{
            "id": asset_id,
            "label": asset_id.replace("-", " ").title(),
            "value": asset_id,
        } for asset_id, stock in supply.items()
            if asset_id not in owned
            and int(stock.get("available", 0) if isinstance(stock, Mapping) else stock) > 0]

    def _choose_bonus_association_asset(
        self, state: dict[str, Any], frame: Mapping[str, Any],
    ) -> None:
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        asset = frame["operation"]["args"].get("asset")
        options = self._bonus_association_asset_options(state, seat, asset)
        self._open_choice(
            state, frame, seat=seat,
            prompt=("Choose an available university" if asset == "university"
                    else "Choose an available partner zoo"),
            options=options,
            continuation={
                "type": "bonus_association_asset", "seat": seat, "asset": asset,
                "actor_seat": frame["actor_seat"], "source_id": frame["source_id"],
            },
        )

    def _discard_final_scoring_card(
        self, state: dict[str, Any], frame: Mapping[str, Any],
    ) -> None:
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        options = []
        seen = set()
        for card in state["players"][seat]["final_scoring_cards"]:
            card_id = card.get("id")
            if not isinstance(card_id, str) or card_id in seen:
                raise SemanticRuleError("Final Scoring cards require stable unique IDs")
            seen.add(card_id)
            options.append({
                "id": card_id,
                "label": str(card.get("display_title", card_id)),
            })
        self._open_choice(
            state,
            frame,
            seat=seat,
            prompt="Discard one Final Scoring card",
            options=options,
            continuation={"type": "discard_final_scoring_card", "seat": seat},
        )

    @staticmethod
    def _card_kind(card: Mapping[str, Any]) -> str | None:
        value = card.get("kind", card.get("card_type"))
        return value if isinstance(value, str) else None

    @staticmethod
    def _card_animal_size_class(card: Mapping[str, Any]) -> str | None:
        if SemanticEngine._card_kind(card) != "animal":
            return None
        facts = card.get("facts")
        source = facts if isinstance(facts, Mapping) else card
        size = source.get("enclosure_size")
        if not isinstance(size, int) or isinstance(size, bool):
            explicit = card.get("animal_size_class")
            return explicit if explicit in {"small", "medium", "large"} else None
        if size <= 2:
            return "small"
        if size >= 4:
            return "large"
        return "medium"

    def _select_hand_cards(
        self, state: dict[str, Any], frame: Mapping[str, Any], *, tuck: bool,
    ) -> None:
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        maximum = self._integer(
            frame["operation"]["args"].get("maximum"), self._context(state, frame), minimum=0,
        )
        options = []
        for card in state["players"][seat]["hand"]:
            card_id = card.get("id")
            if not isinstance(card_id, str):
                raise SemanticRuleError("hand-card choices require stable IDs")
            options.append({"id": card_id, "label": str(card.get("display_title", card_id))})
        self._open_choice(
            state,
            frame,
            seat=seat,
            prompt=("Tuck cards under this animal" if tuck else "Sell cards for 4 money each"),
            options=options,
            minimum=0,
            maximum=min(maximum, len(options)),
            continuation={
                "type": "tuck_hand_cards" if tuck else "sell_hand_cards",
                "seat": seat,
                "actor_seat": frame["actor_seat"],
                "source_id": frame["source_id"],
                "source_instance_id": (
                    frame.get("card", {}).get("id")
                    if isinstance(frame.get("card"), Mapping) else None
                ),
            },
        )

    def _draw_keep_cards(
        self, state: dict[str, Any], frame: Mapping[str, Any], *, animals_only: bool,
    ) -> None:
        args = frame["operation"]["args"]
        context = self._context(state, frame)
        draw_count = self._integer(args.get("draw"), context, minimum=0)
        keep_count = self._integer(args.get("keep", 1), context, minimum=0)
        drawn = [state["zoo_deck"].pop() for _ in range(min(draw_count, len(state["zoo_deck"])))]
        eligible = [card for card in drawn if not animals_only or self._card_kind(card) == "animal"]
        required = min(keep_count, len(eligible))
        if not eligible:
            state["zoo_discard"].extend(drawn)
            return
        options = []
        for card in eligible:
            card_id = card.get("id")
            if not isinstance(card_id, str):
                raise SemanticRuleError("revealed cards require stable IDs")
            options.append({
                "id": card_id, "label": str(card.get("display_title", card_id)),
            })
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        self._open_choice(
            state,
            frame,
            seat=seat,
            prompt="Keep revealed card(s)",
            options=options,
            minimum=required,
            maximum=required,
            continuation={
                "type": "draw_keep_cards",
                "seat": seat,
                "drawn": deepcopy(drawn),
            },
        )

    def _draw_keep_final_scoring(
        self, state: dict[str, Any], frame: Mapping[str, Any],
    ) -> None:
        args = frame["operation"]["args"]
        context = self._context(state, frame)
        draw_count = self._integer(args.get("draw"), context, minimum=0)
        keep_count = self._integer(args.get("keep"), context, minimum=0)
        deck = state["final_scoring_deck"]
        drawn = []
        solo_discarded = []
        while len(drawn) < draw_count and deck:
            card = deck.pop()
            scoring = card.get("facts", {}).get("scoring", {})
            if (
                state["player_count"] == 1
                and isinstance(scoring, Mapping)
                and scoring.get("solo_policy") == "discard_and_redraw"
            ):
                solo_discarded.append(card)
                continue
            drawn.append(card)
        state["final_scoring_discard"].extend(solo_discarded)
        if not drawn:
            return
        required = min(keep_count, len(drawn))
        options = []
        for card in drawn:
            card_id = card.get("id")
            if not isinstance(card_id, str):
                raise SemanticRuleError("Final Scoring card choices require stable IDs")
            options.append({
                "id": card_id,
                "label": str(card.get("display_title", card_id)),
            })
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        self._open_choice(
            state, frame, seat=seat,
            prompt="Keep one Final Scoring card", options=options,
            minimum=required, maximum=required,
            continuation={
                "type": "draw_keep_final_scoring", "seat": seat, "drawn": drawn,
                "solo_discarded": len(solo_discarded),
            },
        )

    def _take_display_card(self, state: dict[str, Any], frame: Mapping[str, Any]) -> None:
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        options = []
        for card in state["card_display"]:
            card_id = card.get("id")
            if not isinstance(card_id, str):
                raise SemanticRuleError("display-card choices require stable IDs")
            options.append({"id": card_id, "label": str(card.get("display_title", card_id))})
        if not options:
            return
        self._open_choice(
            state,
            frame,
            seat=seat,
            prompt="Take one card from the display",
            options=options,
            continuation={"type": "take_display_card", "seat": seat},
        )

    def _take_base_project(self, state: dict[str, Any], frame: Mapping[str, Any]) -> None:
        supply = state["base_project_supply"]
        if not supply:
            return
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        options = []
        seen = set()
        for card in supply:
            card_id = card.get("id")
            if not isinstance(card_id, str) or not card_id or card_id in seen:
                raise SemanticRuleError("base-project supply requires unique physical IDs")
            seen.add(card_id)
            options.append({
                "id": card_id,
                "label": str(card.get("display_title", card.get("entry_id", card_id))),
            })
        self._open_choice(
            state, frame, seat=seat, prompt="Take one unused base Conservation Project",
            options=options, continuation={"type": "take_base_project", "seat": seat},
        )

    def _place_free_building(self, state: dict[str, Any], frame: Mapping[str, Any]) -> None:
        from .build_action import legal_free_building_placements

        args = frame["operation"]["args"]
        building_types = args.get("building_types")
        maximum = args.get("maximum")
        if (
            not isinstance(building_types, list) or not building_types
            or any(not isinstance(value, str) for value in building_types)
            or not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1
        ):
            raise SemanticRuleError("place_free_building requires building types and a maximum")
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        placements = legal_free_building_placements(state["players"][seat], building_types)
        options = [{
            "id": f"place-{index}",
            "label": (
                f"{action['building_type']} at "
                f"({action['anchor']['q']},{action['anchor']['r']})"
            ),
            "value": deepcopy(action),
        } for index, action in enumerate(placements)]
        options.append({"id": "stop", "label": "Do not place another building", "value": None})
        self._open_choice(
            state, frame, seat=seat,
            prompt="Place a free building", options=options,
            continuation={
                "type": "place_free_building", "seat": seat,
                "building_types": building_types, "remaining": maximum,
                "source_id": frame["source_id"],
            },
        )

    def _take_map_reward_card(self, state: dict[str, Any], frame: Mapping[str, Any]) -> None:
        from .cards_action import reputation_display_limit

        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        options = []
        if state["zoo_deck"] or state["zoo_discard"]:
            options.append({"id": "deck", "label": "Draw from the deck", "value": {"source": "deck"}})
        limit = reputation_display_limit(state["players"][seat]["tracks"]["reputation"])
        session = state["turn"].get("action_session") or {}
        positions = None
        for key in ("animals_resolution", "sponsors_resolution", "cards_resolution"):
            resolution = session.get(key)
            if isinstance(resolution, Mapping):
                positions = resolution.get("display_position_by_id")
                if positions is None and key == "cards_resolution":
                    positions = session.get("cards_display_position_by_id")
                break
        seen = set()
        for index, card in enumerate(state["card_display"]):
            card_id = card.get("id")
            if not isinstance(card_id, str) or not card_id or card_id in seen:
                raise SemanticRuleError("display cards require unique physical IDs")
            seen.add(card_id)
            position = index if positions is None else positions.get(card_id, 99)
            if position < limit:
                options.append({
                    "id": f"display-{card_id}",
                    "label": f"Take display card {position + 1}",
                    "value": {"source": "display", "card_id": card_id},
                })
        if not options:
            return
        self._open_choice(
            state, frame, seat=seat, prompt="Take a Map reward card",
            options=options, continuation={"type": "take_map_reward_card", "seat": seat},
        )

    def _take_any_map_placement_bonus(
        self, state: dict[str, Any], frame: Mapping[str, Any],
    ) -> None:
        """Open Archeologist's choice without covering/removing the printed bonus."""
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        options = []
        for cell in state["players"][seat]["map"]["cells"]:
            reward = cell.get("placement_bonus")
            if not isinstance(reward, Mapping):
                continue
            q, r = cell.get("q"), cell.get("r")
            if not isinstance(q, int) or not isinstance(r, int):
                raise SemanticRuleError("Map placement bonus requires axial coordinates")
            options.append({
                "id": f"bonus-q{q}-r{r}",
                "label": f"{reward.get('type', 'bonus')} at ({q},{r})",
                "value": {"coordinate": [q, r], "reward": deepcopy(dict(reward))},
            })
        if not options:
            return
        self._open_choice(
            state, frame, seat=seat, prompt="Choose an uncovered placement bonus",
            options=options,
            continuation={
                "type": "take_any_map_placement_bonus", "seat": seat,
                "actor_seat": frame["actor_seat"], "source_id": frame["source_id"],
            },
        )

    def _scavenge_discard(self, state: dict[str, Any], frame: Mapping[str, Any]) -> None:
        args = frame["operation"]["args"]
        context = self._context(state, frame)
        draw_count = self._integer(args.get("draw"), context, minimum=0)
        keep_count = self._integer(args.get("keep", 1), context, minimum=0)
        discard = list(state["zoo_discard"])
        if not discard or draw_count == 0:
            return
        seed = f"{state['seed']}:{state['resolution']['next_choice_id']}:{frame['source_id']}"
        random.Random(seed).shuffle(discard)
        drawn = discard[:draw_count]
        drawn_ids = {card.get("id") for card in drawn}
        if None in drawn_ids or len(drawn_ids) != len(drawn):
            raise SemanticRuleError("Scavenging cards require unique stable IDs")
        state["zoo_discard"] = [card for card in state["zoo_discard"] if card.get("id") not in drawn_ids]
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        required = min(keep_count, len(drawn))
        self._open_choice(
            state, frame, seat=seat, prompt="Keep card(s) from the shuffled discard pile",
            options=[{
                "id": card["id"], "label": str(card.get("display_title", card["id"])),
            } for card in drawn],
            minimum=required, maximum=required,
            continuation={"type": "scavenge_discard", "seat": seat, "drawn": drawn},
        )

    def _dig_cards(self, state: dict[str, Any], frame: Mapping[str, Any]) -> None:
        remaining = self._integer(
            frame["operation"]["args"].get("maximum"), self._context(state, frame), minimum=0,
        )
        if remaining == 0:
            return
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        options = [{"id": "stop", "label": "Stop digging", "value": {"zone": "stop"}}]
        for card in state["card_display"]:
            card_id = card.get("id")
            if not isinstance(card_id, str):
                raise SemanticRuleError("display-card choices require stable IDs")
            options.append({
                "id": f"display:{card_id}",
                "label": f"Cycle display: {card.get('display_title', card_id)}",
                "value": {"zone": "display", "card_id": card_id},
            })
        for card in state["players"][seat]["hand"]:
            card_id = card.get("id")
            if not isinstance(card_id, str):
                raise SemanticRuleError("hand-card choices require stable IDs")
            options.append({
                "id": f"hand:{card_id}",
                "label": f"Cycle hand: {card.get('display_title', card_id)}",
                "value": {"zone": "hand", "card_id": card_id},
            })
        self._open_choice(
            state, frame, seat=seat, prompt=f"Dig cards ({remaining} remaining)",
            options=options,
            continuation={
                "type": "dig_cards", "seat": seat, "remaining": remaining,
                "actor_seat": frame["actor_seat"], "source_id": frame["source_id"],
            },
        )

    @staticmethod
    def _interaction_immune(player: Mapping[str, Any]) -> bool:
        return bool(player["flags"].get("interaction_immunity")) or any(
            card.get("entry_id", card.get("id")) == "ark-nova:sponsor-225"
            for card in player["played_cards"]
        )

    @classmethod
    def _interaction_allocations(
        cls, state: Mapping[str, Any], actor_seat: int, *, token: str,
        amount: int, actor_appeal: int,
    ) -> list[dict[str, Any]]:
        actor = state["players"][actor_seat]
        allocations = []
        for target in state["players"]:
            if target["seat"] == actor_seat or cls._interaction_immune(target):
                continue
            target_appeal = int(target["tracks"]["appeal"])
            if target_appeal < 5:
                continue
            if token == "venom":
                count = amount if target_appeal > actor_appeal else 0
            else:
                count = int(target_appeal > actor_appeal)
                count += int(target["tracks"]["conservation"] > actor["tracks"]["conservation"])
            if count:
                allocations.append({"seat": target["seat"], "count": count})
        return allocations

    @staticmethod
    def _place_interaction_tokens(
        state: dict[str, Any], allocations: list[Mapping[str, Any]], *,
        token: str, source_id: str, events: list[dict[str, Any]],
    ) -> None:
        descending = token == "constriction"
        for allocation in allocations:
            seat = allocation["seat"]
            cards = sorted(
                state["players"][seat]["action_cards"],
                key=lambda card: card["position"], reverse=descending,
            )[:allocation["count"]]
            placed = 0
            for card in cards:
                if any(
                    (marker if isinstance(marker, str) else marker.get("type")) == token
                    for marker in card["tokens"]
                ):
                    continue
                card["tokens"].append({"type": token, "source_id": source_id})
                placed += 1
            events.append({
                "type": "interaction_tokens_placed", "seat": seat, "token": token,
                "requested": allocation["count"], "placed": placed,
            })

    def _apply_interaction_tokens(
        self, state: dict[str, Any], frame: Mapping[str, Any], events: list[dict[str, Any]],
    ) -> None:
        args = frame["operation"]["args"]
        token = args.get("token")
        if token not in {"venom", "constriction"}:
            raise SemanticRuleError("interaction token must be venom or constriction")
        expected_mode = "appeal" if token == "venom" else "appeal_and_conservation"
        if args.get("track_mode") != expected_mode:
            raise SemanticRuleError("interaction token has an invalid track mode")
        amount = self._integer(args.get("amount", 1), self._context(state, frame), minimum=1)
        actor_seat = frame["actor_seat"]
        after_appeal = int(state["players"][actor_seat]["tracks"]["appeal"])
        printed_appeal = 0
        card = frame.get("card")
        if isinstance(card, Mapping):
            printed_appeal = int(card.get("facts", {}).get("appeal", 0))
        pre_play_tracks = (
            card.get("semantic_context", {}).get("pre_play_tracks", {})
            if isinstance(card, Mapping) else {}
        )
        before_appeal = pre_play_tracks.get("appeal")
        if not isinstance(before_appeal, int) or isinstance(before_appeal, bool):
            before_appeal = max(0, after_appeal - printed_appeal)
        before = self._interaction_allocations(
            state, actor_seat, token=token, amount=amount, actor_appeal=before_appeal,
        )
        after = self._interaction_allocations(
            state, actor_seat, token=token, amount=amount, actor_appeal=after_appeal,
        )
        if before != after:
            self._open_choice(
                state, frame, seat=actor_seat,
                prompt="Resolve the animal interaction before or after its appeal",
                options=[
                    {"id": "before_appeal", "label": "Before appeal", "value": before},
                    {"id": "after_appeal", "label": "After appeal", "value": after},
                ],
                continuation={
                    "type": "apply_interaction_tokens", "seat": actor_seat,
                    "token": token, "source_id": frame["source_id"],
                },
            )
            return
        self._place_interaction_tokens(
            state, after, token=token, source_id=frame["source_id"], events=events,
        )

    @classmethod
    def _pilfer_leaders(
        cls, state: Mapping[str, Any], actor_seat: int, *, leader_track: str,
        actor_appeal: int,
    ) -> list[int]:
        eligible = []
        for player in state["players"]:
            appeal = actor_appeal if player["seat"] == actor_seat else int(
                player["tracks"]["appeal"]
            )
            if appeal < 5:
                continue
            score = appeal if leader_track == "appeal" else int(
                player["tracks"]["conservation"]
            )
            if leader_track == "conservation" and score < 1:
                continue
            eligible.append((player["seat"], score))
        if not eligible:
            return []
        maximum = max(score for _, score in eligible)
        return [
            seat for seat, score in eligible
            if score == maximum and seat != actor_seat
            and not cls._interaction_immune(state["players"][seat])
        ]

    def _open_pilfer_target(
        self, state: dict[str, Any], frame: Mapping[str, Any], *,
        leader_track: str, target_seats: list[int], events: list[dict[str, Any]],
    ) -> None:
        actor = frame["actor_seat"]
        if not target_seats:
            events.append({
                "type": "pilfering_no_target", "seat": actor,
                "leader_track": leader_track,
            })
            return
        if len(target_seats) == 1:
            self._open_pilfer_payment(
                state, frame, leader_track=leader_track, target_seat=target_seats[0],
            )
            return
        self._open_choice(
            state, frame, seat=actor,
            prompt=f"Choose a tied {leader_track} leader to pilfer",
            options=[{
                "id": f"seat-{seat}", "label": f"Seat {seat}", "value": seat,
            } for seat in target_seats],
            continuation={
                "type": "pilfer_target", "seat": actor,
                "actor_seat": actor, "leader_track": leader_track,
                "source_id": frame["source_id"],
            },
        )

    def _open_pilfer_payment(
        self, state: dict[str, Any], frame: Mapping[str, Any], *,
        leader_track: str, target_seat: int,
    ) -> None:
        target = state["players"][target_seat]
        can_give_card = bool(target["hand"])
        can_give_five = target["money"] >= 5
        options = []
        if can_give_card:
            options.append({
                "id": "give_card", "label": "Give 1 random hand card",
                "value": "card",
            })
        if can_give_five or not can_give_card:
            amount = min(5, target["money"])
            options.append({
                "id": "give_money", "label": f"Give {amount} money",
                "value": "money",
            })
        nonce = state["resolution"]["next_choice_id"]
        self._open_choice(
            state, frame, seat=target_seat,
            prompt=f"Resolve pilfering led by {leader_track}", options=options,
            continuation={
                "type": "pilfer_payment", "seat": target_seat,
                "actor_seat": frame["actor_seat"], "target_seat": target_seat,
                "leader_track": leader_track, "source_id": frame["source_id"],
                "nonce": nonce,
            },
        )

    def _pilfer(
        self, state: dict[str, Any], frame: Mapping[str, Any], events: list[dict[str, Any]],
    ) -> None:
        leader_track = frame["operation"]["args"].get("leader_track")
        if leader_track not in {"appeal", "conservation"}:
            raise SemanticRuleError("pilfer.leader_track must be appeal or conservation")
        actor = frame["actor_seat"]
        after_appeal = int(state["players"][actor]["tracks"]["appeal"])
        card = frame.get("card")
        before_appeal = None
        if isinstance(card, Mapping):
            before_appeal = card.get("semantic_context", {}).get(
                "pre_play_tracks", {},
            ).get("appeal")
        if not isinstance(before_appeal, int) or isinstance(before_appeal, bool):
            before_appeal = after_appeal
        before = self._pilfer_leaders(
            state, actor, leader_track=leader_track, actor_appeal=before_appeal,
        )
        after = self._pilfer_leaders(
            state, actor, leader_track=leader_track, actor_appeal=after_appeal,
        )
        if before != after:
            self._open_choice(
                state, frame, seat=actor,
                prompt="Resolve pilfering before or after this animal's appeal",
                options=[
                    {"id": "before_appeal", "label": "Before appeal", "value": before},
                    {"id": "after_appeal", "label": "After appeal", "value": after},
                ],
                continuation={
                    "type": "pilfer_timing", "seat": actor,
                    "actor_seat": actor, "leader_track": leader_track,
                    "source_id": frame["source_id"],
                },
            )
            return
        self._open_pilfer_target(
            state, frame, leader_track=leader_track, target_seats=after, events=events,
        )

    @classmethod
    def _hypnosis_leaders(
        cls, state: Mapping[str, Any], actor_seat: int, *, actor_appeal: int,
    ) -> list[int]:
        scores = [
            (
                player["seat"],
                actor_appeal if player["seat"] == actor_seat
                else int(player["tracks"]["appeal"]),
            )
            for player in state["players"]
        ]
        maximum = max(score for _, score in scores)
        if maximum < 5:
            return []
        return [
            seat for seat, score in scores
            if score == maximum and seat != actor_seat
            and not cls._interaction_immune(state["players"][seat])
        ]

    def _open_hypnosis_target(
        self, state: dict[str, Any], frame: Mapping[str, Any], *,
        maximum_target_slot: int, target_seats: list[int], events: list[dict[str, Any]],
    ) -> None:
        actor = frame["actor_seat"]
        if not target_seats:
            events.append({"type": "hypnosis_no_target", "seat": actor})
            return
        if len(target_seats) == 1:
            self._open_hypnosis_card(
                state, frame, maximum_target_slot=maximum_target_slot,
                target_seat=target_seats[0],
            )
            return
        self._open_choice(
            state, frame, seat=actor,
            prompt="Choose a tied appeal leader for Hypnosis",
            options=[{
                "id": f"seat-{target}", "label": f"Seat {target}", "value": target,
            } for target in target_seats],
            continuation={
                "type": "hypnosis_target", "seat": actor, "actor_seat": actor,
                "maximum_target_slot": maximum_target_slot,
                "source_id": frame["source_id"],
            },
        )

    def _open_hypnosis_card(
        self, state: dict[str, Any], frame: Mapping[str, Any], *,
        maximum_target_slot: int, target_seat: int,
    ) -> None:
        options = []
        for card in sorted(
            state["players"][target_seat]["action_cards"],
            key=lambda item: item["position"],
        ):
            if card["position"] > maximum_target_slot:
                continue
            options.append({
                "id": f"action-{card['id']}",
                "label": f"{card['action']} · slot {card['position']}",
                "value": {
                    "target_seat": target_seat,
                    "target_action_card_id": card["id"],
                },
            })
        self._open_choice(
            state, frame, seat=frame["actor_seat"],
            prompt="Choose an opponent Action card for Hypnosis", options=options,
            continuation={
                "type": "hypnosis_card", "seat": frame["actor_seat"],
                "actor_seat": frame["actor_seat"],
                "maximum_target_slot": maximum_target_slot,
                "source_id": frame["source_id"],
            },
        )

    def _hypnosis(
        self, state: dict[str, Any], frame: Mapping[str, Any], events: list[dict[str, Any]],
    ) -> None:
        maximum_target_slot = self._integer(
            frame["operation"]["args"].get("maximum_target_slot"),
            self._context(state, frame), minimum=1, maximum=5,
        )
        actor = frame["actor_seat"]
        after_appeal = int(state["players"][actor]["tracks"]["appeal"])
        card = frame.get("card")
        before_appeal = None
        if isinstance(card, Mapping):
            before_appeal = card.get("semantic_context", {}).get(
                "pre_play_tracks", {},
            ).get("appeal")
        if not isinstance(before_appeal, int) or isinstance(before_appeal, bool):
            before_appeal = after_appeal
        before = self._hypnosis_leaders(
            state, actor, actor_appeal=before_appeal,
        )
        after = self._hypnosis_leaders(
            state, actor, actor_appeal=after_appeal,
        )
        if before != after:
            self._open_choice(
                state, frame, seat=actor,
                prompt="Resolve Hypnosis before or after this animal's appeal",
                options=[
                    {"id": "before_appeal", "label": "Before appeal", "value": before},
                    {"id": "after_appeal", "label": "After appeal", "value": after},
                ],
                continuation={
                    "type": "hypnosis_timing", "seat": actor, "actor_seat": actor,
                    "maximum_target_slot": maximum_target_slot,
                    "source_id": frame["source_id"],
                },
            )
            return
        self._open_hypnosis_target(
            state, frame, maximum_target_slot=maximum_target_slot,
            target_seats=after, events=events,
        )

    def _reposition_action_card(
        self, state: dict[str, Any], frame: Mapping[str, Any],
    ) -> None:
        args = frame["operation"]["args"]
        raw_slots = args.get("target_slots")
        if raw_slots is None:
            target_slots = [self._integer(
                args.get("target_slot"), self._context(state, frame), minimum=1, maximum=5,
            )]
        else:
            if (
                not isinstance(raw_slots, list) or not raw_slots
                or any(
                    not isinstance(value, int) or isinstance(value, bool)
                    or not 1 <= value <= 5 for value in raw_slots
                )
                or len(raw_slots) != len(set(raw_slots))
            ):
                raise SemanticRuleError("reposition_action_card.target_slots is invalid")
            target_slots = list(raw_slots)
        optional = args.get("optional", False)
        if not isinstance(optional, bool):
            raise SemanticRuleError("reposition_action_card.optional must be boolean")
        fixed_action = args.get("action")
        if fixed_action is not None and fixed_action not in {
            "animals", "cards", "build", "association", "sponsors",
        }:
            raise SemanticRuleError("reposition_action_card.action is invalid")
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        selectable = [
            card for card in state["players"][seat]["action_cards"]
            if fixed_action is None or card["action"] == fixed_action
        ]
        options = [{
            "id": (
                card["id"] if len(target_slots) == 1
                else f"{card['id']}-to-{target_slot}"
            ),
            "label": f"{card['action']} ({card['position']} -> {target_slot})",
            "value": {"action_card_id": card["id"], "target_slot": target_slot},
        } for card in sorted(selectable, key=lambda card: card["position"])
          for target_slot in target_slots]
        self._open_choice(
            state, frame, seat=seat,
            prompt="Move an Action card", options=options,
            minimum=0 if optional else 1, maximum=1,
            continuation={"type": "reposition_action_card", "seat": seat},
        )

    @staticmethod
    def _move_action_card_to_slot(
        state: dict[str, Any], seat: int, action_card_id: str, target_slot: int,
    ) -> tuple[int, int]:
        cards = state["players"][seat]["action_cards"]
        selected = next((card for card in cards if card["id"] == action_card_id), None)
        if selected is None:
            raise SemanticRuleError("selected Action card is no longer available")
        old_slot = int(selected["position"])
        if old_slot < target_slot:
            for card in cards:
                if old_slot < card["position"] <= target_slot:
                    card["position"] -= 1
        elif old_slot > target_slot:
            for card in cards:
                if target_slot <= card["position"] < old_slot:
                    card["position"] += 1
        selected["position"] = target_slot
        return old_slot, target_slot

    def legal_choice_actions(self, state: Mapping[str, Any], seat: int) -> list[dict[str, Any]]:
        pending = state["resolution"].get("pending_choice")
        if pending is None or pending["seat"] != seat:
            return []
        options = pending["options"]
        actions = []
        for size in range(pending["minimum"], pending["maximum"] + 1):
            for selected in combinations(options, size):
                option_ids = [option["id"] for option in selected]
                suffix = "+".join(option_ids) if option_ids else "none"
                actions.append({
                    "id": f"{pending['choice_id']}:{suffix}",
                    "label": ", ".join(option["label"] for option in selected),
                    "action": {
                        "type": "resolve_semantic_choice",
                        "choice_id": pending["choice_id"],
                        "option_ids": option_ids,
                    },
                })
        return actions

    def submit_choice(
        self, state: dict[str, Any], seat: int, choice_id: str, option_ids: list[str],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        next_state = clone_state(state)
        pending = next_state["resolution"].get("pending_choice")
        if pending is None:
            raise SemanticRuleError("there is no pending semantic choice")
        if pending["seat"] != seat:
            raise SemanticRuleError("semantic choice belongs to another seat")
        if pending["choice_id"] != choice_id:
            raise SemanticRuleError("semantic choice ID is stale")
        if not isinstance(option_ids, list) or any(not isinstance(value, str) for value in option_ids):
            raise SemanticRuleError("semantic choice option_ids must be a string array")
        if len(option_ids) != len(set(option_ids)) or not pending["minimum"] <= len(option_ids) <= pending["maximum"]:
            raise SemanticRuleError("semantic choice has an invalid selection count")
        by_id = {option["id"]: option for option in pending["options"]}
        if any(option_id not in by_id for option_id in option_ids):
            raise SemanticRuleError("semantic choice contains an unknown option")
        selected = [by_id[option_id] for option_id in option_ids]
        next_state["resolution"]["pending_choice"] = None
        events = [{
            "type": "semantic_choice_resolved",
            "choice_id": choice_id,
            "seat": seat,
            "option_ids": option_ids,
        }]
        continuation = pending.get("continuation")
        if continuation is not None:
            self._apply_choice_continuation(next_state, continuation, selected, events)
        else:
            base = pending["frame"]
            frames = []
            for option in selected:
                frames.extend(self._frames(
                    option.get("effects", []),
                    base["actor_seat"],
                    option.get("target_seat", base.get("target_seat")),
                    base["source_id"],
                    base.get("card"),
                    option.get("bindings", base.get("bindings", {})),
                ))
            next_state["resolution"]["queue"][0:0] = frames
        self._drain(next_state, events)
        validate_semantic_state(next_state)
        return next_state, events

    def _apply_choice_continuation(
        self, state: dict[str, Any], continuation: Mapping[str, Any],
        selected: list[Mapping[str, Any]], events: list[dict[str, Any]],
    ) -> None:
        continuation_type = continuation.get("type")
        seat = continuation.get("seat")
        player = state["players"][seat]
        if continuation_type == "choose_effect_order":
            if (
                len(selected) != 1
                or not isinstance(selected[0].get("value"), Mapping)
                or not isinstance(selected[0]["value"].get("index"), int)
            ):
                raise SemanticRuleError("effect ordering requires exactly one effect")
            effects = continuation.get("effects")
            index = selected[0]["value"]["index"]
            if not isinstance(effects, list) or not 0 <= index < len(effects):
                raise SemanticRuleError("effect ordering continuation is malformed")
            selected_effect = effects[index]
            remaining = effects[:index] + effects[index + 1:]
            ordered = [selected_effect]
            ordered.extend(simultaneous_effects(
                remaining,
                label="Resolve remaining simultaneous effects",
                timing="immediate",
            ))
            state["resolution"]["queue"][0:0] = self._frames(
                ordered,
                int(continuation["actor_seat"]),
                continuation.get("target_seat"),
                str(continuation["source_id"]),
                continuation.get("card"),
                continuation.get("bindings", {}),
            )
            events.append({
                "type": "simultaneous_effect_order_selected",
                "seat": seat, "selected_op": selected_effect.get("op"),
                "remaining": len(remaining),
            })
            return
        if continuation_type == "pilfer_timing":
            if len(selected) != 1 or not isinstance(selected[0].get("value"), list):
                raise SemanticRuleError("pilfering timing requires one valid selection")
            frame = {
                "actor_seat": continuation.get("actor_seat"),
                "target_seat": None,
                "source_id": continuation.get("source_id"),
                "card": None,
                "bindings": {},
            }
            self._open_pilfer_target(
                state, frame, leader_track=str(continuation.get("leader_track")),
                target_seats=list(selected[0]["value"]), events=events,
            )
            return
        if continuation_type == "pilfer_target":
            if len(selected) != 1 or not isinstance(selected[0].get("value"), int):
                raise SemanticRuleError("pilfering target requires one valid seat")
            frame = {
                "actor_seat": continuation.get("actor_seat"),
                "target_seat": selected[0]["value"],
                "source_id": continuation.get("source_id"),
                "card": None,
                "bindings": {},
            }
            self._open_pilfer_payment(
                state, frame, leader_track=str(continuation.get("leader_track")),
                target_seat=selected[0]["value"],
            )
            return
        if continuation_type == "pilfer_payment":
            if len(selected) != 1 or selected[0].get("value") not in {"card", "money"}:
                raise SemanticRuleError("pilfering payment requires one valid option")
            actor_seat = continuation.get("actor_seat")
            target_seat = continuation.get("target_seat")
            if not isinstance(actor_seat, int) or not isinstance(target_seat, int):
                raise SemanticRuleError("pilfering payment seats are malformed")
            actor = state["players"][actor_seat]
            target = state["players"][target_seat]
            if selected[0]["value"] == "money":
                amount = min(5, target["money"])
                target["money"] -= amount
                actor["money"] += amount
                events.append({
                    "type": "pilfering_money_transferred", "seat": actor_seat,
                    "target_seat": target_seat, "amount": amount,
                    "leader_track": continuation.get("leader_track"),
                })
                return
            if not target["hand"]:
                raise SemanticRuleError("pilfering target no longer has a hand card")
            nonce = continuation.get("nonce")
            index = random.Random(
                f"{state['seed']}:pilfer:{nonce}:{actor_seat}:{target_seat}"
            ).randrange(len(target["hand"]))
            card = target["hand"].pop(index)
            actor["hand"].append(card)
            events.append({
                "type": "pilfering_card_transferred", "seat": actor_seat,
                "target_seat": target_seat, "card_id": card.get("id"),
                "leader_track": continuation.get("leader_track"),
            })
            return
        if continuation_type == "hypnosis_timing":
            if len(selected) != 1 or not isinstance(selected[0].get("value"), list):
                raise SemanticRuleError("Hypnosis timing requires one valid selection")
            frame = {
                "actor_seat": continuation.get("actor_seat"), "target_seat": None,
                "source_id": continuation.get("source_id"), "card": None,
                "bindings": {},
            }
            self._open_hypnosis_target(
                state, frame,
                maximum_target_slot=int(continuation.get("maximum_target_slot")),
                target_seats=list(selected[0]["value"]), events=events,
            )
            return
        if continuation_type == "hypnosis_target":
            if len(selected) != 1 or not isinstance(selected[0].get("value"), int):
                raise SemanticRuleError("Hypnosis target requires one valid seat")
            frame = {
                "actor_seat": continuation.get("actor_seat"),
                "target_seat": selected[0]["value"],
                "source_id": continuation.get("source_id"), "card": None,
                "bindings": {},
            }
            self._open_hypnosis_card(
                state, frame,
                maximum_target_slot=int(continuation.get("maximum_target_slot")),
                target_seat=selected[0]["value"],
            )
            return
        if continuation_type == "hypnosis_card":
            if len(selected) != 1 or not isinstance(selected[0].get("value"), Mapping):
                raise SemanticRuleError("Hypnosis requires one valid Action card")
            value = selected[0]["value"]
            actor_seat = continuation.get("actor_seat")
            target_seat = value.get("target_seat")
            target_card_id = value.get("target_action_card_id")
            if not isinstance(actor_seat, int) or not isinstance(target_seat, int):
                raise SemanticRuleError("Hypnosis seats are malformed")
            target_card = next((
                card for card in state["players"][target_seat]["action_cards"]
                if card.get("id") == target_card_id
            ), None)
            maximum = continuation.get("maximum_target_slot")
            if (
                target_card is None or not isinstance(maximum, int)
                or target_card["position"] > maximum
            ):
                raise SemanticRuleError("Hypnosis Action card is no longer legal")
            state["turn"]["hypnosis_action"] = {
                "seat": actor_seat,
                "target_seat": target_seat,
                "target_action_card_id": target_card["id"],
                "action": target_card["action"],
                "position": target_card["position"],
                "upgraded": bool(target_card["upgraded"]),
                "constricted": any(
                    (token if isinstance(token, str) else token.get("type")) == "constriction"
                    for token in target_card["tokens"]
                ),
                "venom": any(
                    (token if isinstance(token, str) else token.get("type")) == "venom"
                    for token in target_card["tokens"]
                ),
                "source_id": continuation.get("source_id"),
            }
            events.append({
                "type": "hypnosis_action_granted", "seat": actor_seat,
                "target_seat": target_seat, "action": target_card["action"],
                "position": target_card["position"],
                "upgraded": bool(target_card["upgraded"]),
            })
            return
        if continuation_type in {"sell_hand_cards", "tuck_hand_cards"}:
            selected_ids = {option["id"] for option in selected}
            moved = [card for card in player["hand"] if card.get("id") in selected_ids]
            if len(moved) != len(selected_ids):
                raise SemanticRuleError("selected hand cards are no longer available")
            player["hand"] = [card for card in player["hand"] if card.get("id") not in selected_ids]
            source_id = continuation.get("source_id")
            if continuation_type == "sell_hand_cards":
                state["zoo_discard"].extend(moved)
                op, args = "gain_money", {"amount": 4 * len(moved)}
                event_type = "sun_bathing_cards_sold"
            else:
                source_instance_id = continuation.get("source_instance_id")
                source = next(
                    (
                        card for card in player["played_cards"]
                        if (
                            card.get("id") == source_instance_id
                            or (
                                source_instance_id is None
                                and (card.get("id") == source_id or card.get("entry_id") == source_id)
                            )
                        )
                    ),
                    None,
                )
                if source is None:
                    raise SemanticRuleError("Pouch source animal is no longer in play")
                source.setdefault("tucked_cards", []).extend(moved)
                op, args = "move_track", {"track": "appeal", "amount": 2 * len(moved)}
                event_type = "pouch_cards_tucked"
            events.append({"type": event_type, "seat": seat, "count": len(moved)})
            if moved:
                state["resolution"]["queue"].insert(0, {
                    "operation": {"op": op, "args": args, "timing": "on_play"},
                    "actor_seat": continuation.get("actor_seat", seat),
                    "target_seat": seat,
                    "source_id": source_id,
                    "card": None,
                    "bindings": {},
                })
            return
        if continuation_type == "draw_keep_cards":
            selected_ids = {option["id"] for option in selected}
            drawn = continuation.get("drawn")
            if not isinstance(drawn, list):
                raise SemanticRuleError("revealed-card continuation is malformed")
            kept = [card for card in drawn if card.get("id") in selected_ids]
            if len(kept) != len(selected_ids):
                raise SemanticRuleError("selected revealed cards are unavailable")
            player["hand"].extend(kept)
            state["zoo_discard"].extend(
                card for card in drawn if card.get("id") not in selected_ids
            )
            events.append({
                "type": "revealed_cards_resolved", "seat": seat,
                "drawn": len(drawn), "kept": len(kept),
            })
            return
        if continuation_type == "draw_keep_final_scoring":
            selected_ids = {option["id"] for option in selected}
            drawn = continuation.get("drawn")
            if not isinstance(drawn, list):
                raise SemanticRuleError("Final Scoring draw continuation is malformed")
            kept = [card for card in drawn if card.get("id") in selected_ids]
            if len(kept) != len(selected_ids):
                raise SemanticRuleError("selected Final Scoring cards are unavailable")
            player["final_scoring_cards"].extend(kept)
            state["final_scoring_discard"].extend(
                card for card in drawn if card.get("id") not in selected_ids
            )
            events.append({
                "type": "final_scoring_cards_drawn", "seat": seat,
                "drawn": len(drawn), "kept": len(kept),
                "solo_discarded": int(continuation.get("solo_discarded", 0)),
            })
            return
        if continuation_type == "take_display_card":
            if len(selected) != 1:
                raise SemanticRuleError("exactly one display card must be selected")
            selected_id = selected[0]["id"]
            taken = [card for card in state["card_display"] if card.get("id") == selected_id]
            if len(taken) != 1:
                raise SemanticRuleError("selected display card is no longer available")
            state["card_display"] = [
                card for card in state["card_display"] if card.get("id") != selected_id
            ]
            player["hand"].extend(taken)
            if state["zoo_deck"]:
                state["card_display"].append(state["zoo_deck"].pop())
            events.append({"type": "display_card_taken", "seat": seat, "card_id": selected_id})
            return
        if continuation_type == "take_base_project":
            if len(selected) != 1:
                raise SemanticRuleError("exactly one unused base project must be selected")
            selected_id = selected[0]["id"]
            taken = [
                card for card in state["base_project_supply"]
                if card.get("id") == selected_id
            ]
            if len(taken) != 1:
                raise SemanticRuleError("selected base project is no longer available")
            state["base_project_supply"].remove(taken[0])
            player["hand"].append(taken[0])
            events.append({
                "type": "base_project_taken", "seat": seat,
                "physical_id": selected_id,
                "project_id": taken[0].get("entry_id", taken[0].get("id")),
            })
            return
        if continuation_type == "place_free_building":
            if len(selected) != 1:
                raise SemanticRuleError("free building placement requires one selection")
            value = selected[0].get("value")
            if value is None:
                events.append({"type": "free_building_placement_stopped", "seat": seat})
                return
            if not isinstance(value, Mapping):
                raise SemanticRuleError("free building placement is malformed")
            from .build_action import legal_free_building_placements, place_free_building

            building_types = continuation.get("building_types")
            if not isinstance(building_types, list):
                raise SemanticRuleError("free building continuation has invalid building types")
            legal = legal_free_building_placements(state["players"][seat], building_types)
            if dict(value) not in legal:
                raise SemanticRuleError("selected free building placement is stale")
            building, effects, rewards = place_free_building(state, seat, value)
            events.append({
                "type": "free_building_placed", "seat": seat,
                "building": deepcopy(building), "source_id": continuation.get("source_id"),
            })
            queued = list(effects)
            for reward in rewards:
                if reward.get("type") == "take_card":
                    queued.append({
                        "op": "take_map_reward_card", "timing": "immediate", "args": {},
                    })
                elif reward.get("type") == "clever":
                    session = state["turn"].get("action_session")
                    operation = {
                        "op": "reposition_action_card", "timing": "after_finishing",
                        "args": {
                            "target_slot": reward["target_strength"], "optional": False,
                        },
                    }
                    if session is not None and session.get("seat") == seat:
                        session["after_finishing_effects"].append(operation)
                    else:
                        queued.append({**operation, "timing": "immediate"})
                else:
                    raise SemanticRuleError("free building produced an unknown map reward")
            remaining = continuation.get("remaining")
            if not isinstance(remaining, int) or isinstance(remaining, bool) or remaining < 1:
                raise SemanticRuleError("free building continuation has invalid remaining count")
            if remaining > 1:
                queued.append({
                    "op": "place_free_building", "timing": "immediate",
                    "args": {"building_types": building_types, "maximum": remaining - 1},
                })
            state["resolution"]["queue"][0:0] = SemanticEngine._frames(
                queued, continuation.get("actor_seat", seat), seat,
                str(continuation.get("source_id", "free-building")), None, {},
            )
            return
        if continuation_type == "take_any_map_placement_bonus":
            if len(selected) != 1 or not isinstance(selected[0].get("value"), Mapping):
                raise SemanticRuleError("Archeologist requires one valid placement bonus")
            value = selected[0]["value"]
            reward = value.get("reward")
            coordinate = value.get("coordinate")
            if not isinstance(reward, Mapping) or not isinstance(coordinate, list):
                raise SemanticRuleError("Archeologist placement bonus is malformed")
            reward_type = reward.get("type")
            queued: list[dict[str, Any]] = []
            if reward_type == "take_card":
                queued.append({
                    "op": "take_map_reward_card", "timing": "immediate", "args": {},
                })
            elif reward_type == "clever":
                operation = {
                    "op": "reposition_action_card", "timing": "after_finishing",
                    "args": {
                        "target_slot": int(reward.get("target_strength", 1)),
                        "optional": False,
                    },
                }
                session = state["turn"].get("action_session")
                if session is not None and session.get("seat") == seat:
                    session["after_finishing_effects"].append(operation)
                else:
                    queued.append({**operation, "timing": "immediate"})
            else:
                operations = {
                    "gain_money": ("gain_money", {"amount": reward.get("amount", 0)}),
                    "gain_x_token": ("gain_x_token", {"amount": reward.get("amount", 0)}),
                    "gain_reputation": (
                        "move_track",
                        {"track": "reputation", "amount": reward.get("amount", 0)},
                    ),
                }
                if reward_type not in operations:
                    raise SemanticRuleError("Archeologist selected an unsupported placement bonus")
                op, args = operations[reward_type]
                queued.append({"op": op, "timing": "immediate", "args": args})
            events.append({
                "type": "archeologist_bonus_chosen", "seat": seat,
                "coordinate": coordinate, "reward": deepcopy(dict(reward)),
            })
            state["resolution"]["queue"][0:0] = SemanticEngine._frames(
                queued,
                int(continuation.get("actor_seat", seat)), seat,
                str(continuation.get("source_id", "sponsor:archeologist")),
                None, {},
            )
            return
        if continuation_type == "take_map_reward_card":
            if len(selected) != 1 or not isinstance(selected[0].get("value"), Mapping):
                raise SemanticRuleError("Map card reward requires one valid selection")
            value = selected[0]["value"]
            source = value.get("source")
            recycled = False
            if source == "deck":
                if not state["zoo_deck"]:
                    if not state["zoo_discard"]:
                        raise SemanticRuleError("Zoo deck and discard are empty")
                    random.Random(
                        f"{state['seed']}:map-card:{state['resolution']['next_choice_id']}"
                    ).shuffle(state["zoo_discard"])
                    state["zoo_deck"] = state["zoo_discard"]
                    state["zoo_discard"] = []
                    recycled = True
                card = state["zoo_deck"].pop()
            elif source == "display":
                card_id = value.get("card_id")
                matches = [card for card in state["card_display"] if card.get("id") == card_id]
                if len(matches) != 1:
                    raise SemanticRuleError("selected Map reward card is no longer displayed")
                card = matches[0]
                state["card_display"].remove(card)
                if state["zoo_deck"]:
                    state["card_display"].append(state["zoo_deck"].pop())
            else:
                raise SemanticRuleError("Map card reward source is malformed")
            player["hand"].append(card)
            events.append({
                "type": "map_card_reward_taken", "seat": seat,
                "card_id": card.get("id"), "source": source, "deck_recycled": recycled,
            })
            return
        if continuation_type == "scavenge_discard":
            selected_ids = {option["id"] for option in selected}
            drawn = continuation.get("drawn")
            if not isinstance(drawn, list):
                raise SemanticRuleError("Scavenging continuation is malformed")
            kept = [card for card in drawn if card.get("id") in selected_ids]
            if len(kept) != len(selected_ids):
                raise SemanticRuleError("selected Scavenging cards are unavailable")
            player["hand"].extend(kept)
            state["zoo_discard"].extend(
                card for card in drawn if card.get("id") not in selected_ids
            )
            events.append({
                "type": "scavenging_resolved", "seat": seat,
                "drawn": len(drawn), "kept": len(kept),
            })
            return
        if continuation_type == "dig_cards":
            if len(selected) != 1 or not isinstance(selected[0].get("value"), Mapping):
                raise SemanticRuleError("Digging requires exactly one valid selection")
            value = selected[0]["value"]
            zone = value.get("zone")
            if zone == "stop":
                events.append({"type": "digging_stopped", "seat": seat})
                return
            card_id = value.get("card_id")
            if not isinstance(card_id, str) or zone not in {"display", "hand"}:
                raise SemanticRuleError("Digging selection is malformed")
            cards = state["card_display"] if zone == "display" else player["hand"]
            cycled = [card for card in cards if card.get("id") == card_id]
            if len(cycled) != 1:
                raise SemanticRuleError("selected Digging card is no longer available")
            if zone == "display":
                state["card_display"] = [card for card in cards if card.get("id") != card_id]
                if state["zoo_deck"]:
                    state["card_display"].append(state["zoo_deck"].pop())
            else:
                player["hand"] = [card for card in cards if card.get("id") != card_id]
                if state["zoo_deck"]:
                    player["hand"].append(state["zoo_deck"].pop())
            state["zoo_discard"].extend(cycled)
            events.append({"type": "digging_card_cycled", "seat": seat, "zone": zone, "card_id": card_id})
            remaining = continuation.get("remaining")
            if not isinstance(remaining, int) or isinstance(remaining, bool) or remaining < 1:
                raise SemanticRuleError("Digging continuation has invalid remaining count")
            if remaining > 1:
                state["resolution"]["queue"].insert(0, {
                    "operation": {"op": "dig_cards", "args": {"maximum": remaining - 1}, "timing": "on_play"},
                    "actor_seat": continuation.get("actor_seat", seat), "target_seat": seat,
                    "source_id": continuation.get("source_id"), "card": None, "bindings": {},
                })
            return
        if continuation_type == "apply_interaction_tokens":
            if len(selected) != 1 or not isinstance(selected[0].get("value"), list):
                raise SemanticRuleError("interaction timing requires exactly one selection")
            token = continuation.get("token")
            if token not in {"venom", "constriction"}:
                raise SemanticRuleError("interaction timing token is malformed")
            SemanticEngine._place_interaction_tokens(
                state, selected[0]["value"], token=token,
                source_id=str(continuation.get("source_id")), events=events,
            )
            return
        if continuation_type == "reposition_action_card":
            if not selected:
                events.append({"type": "action_card_reposition_declined", "seat": seat})
                return
            if len(selected) != 1 or not isinstance(selected[0].get("value"), Mapping):
                raise SemanticRuleError("Action-card reposition requires one valid selection")
            value = selected[0]["value"]
            card_id = value.get("action_card_id")
            target_slot = value.get("target_slot")
            if not isinstance(card_id, str) or not isinstance(target_slot, int):
                raise SemanticRuleError("Action-card reposition selection is malformed")
            old_slot, new_slot = SemanticEngine._move_action_card_to_slot(
                state, seat, card_id, target_slot,
            )
            events.append({
                "type": "action_card_repositioned", "seat": seat,
                "action_card_id": card_id, "from": old_slot, "to": new_slot,
            })
            return
        if continuation_type == "conservation_2_reward":
            if len(selected) != 1:
                raise SemanticRuleError("the conservation-2 reward requires one selection")
            value = selected[0].get("value")
            if not isinstance(value, Mapping):
                raise SemanticRuleError("the conservation-2 reward is malformed")
            if value.get("kind") == "upgrade":
                action = value.get("action")
                card = next(
                    (item for item in player["action_cards"] if item["action"] == action), None,
                )
                if card is None or card["upgraded"]:
                    raise SemanticRuleError("the selected Action card cannot be upgraded")
                card["upgraded"] = True
                events.append({"type": "action_card_upgraded", "seat": seat, "action": action})
                return
            if value.get("kind") == "worker":
                workers = player["association_workers"]
                if workers["reserve"] < 1:
                    raise SemanticRuleError("no association worker is available to activate")
                workers["reserve"] -= 1
                workers["active"] += 1
                events.append({"type": "association_worker_activated", "seat": seat})
                return
            raise SemanticRuleError("unknown conservation-2 reward")
        if continuation_type == "action_upgrade_reward":
            if len(selected) != 1 or not isinstance(selected[0].get("value"), Mapping):
                raise SemanticRuleError("the Action-card upgrade requires one selection")
            action = selected[0]["value"].get("action")
            card = next(
                (item for item in player["action_cards"] if item["action"] == action), None,
            )
            if card is None or card["upgraded"]:
                raise SemanticRuleError("the selected Action card cannot be upgraded")
            card["upgraded"] = True
            events.append({"type": "action_card_upgraded", "seat": seat, "action": action})
            return
        if continuation_type == "bonus_association_asset":
            if len(selected) != 1 or not isinstance(selected[0].get("value"), str):
                raise SemanticRuleError("the association reward requires one asset")
            asset = continuation.get("asset")
            asset_id = selected[0]["value"]
            legal_ids = {
                option["value"] for option in self._bonus_association_asset_options(
                    state, seat, asset,
                )
            }
            if asset_id not in legal_ids:
                raise SemanticRuleError("the selected association asset is no longer available")
            board_key = "universities" if asset == "university" else "partner_zoos"
            supply = state["association_board"][board_key][asset_id]
            if isinstance(supply, Mapping):
                supply["available"] = 0
                if seat not in supply["owners"]:
                    supply["owners"].append(seat)
            else:
                state["association_board"][board_key][asset_id] = 0
            queued: list[dict[str, Any]] = []
            if asset == "university":
                player["universities"].append(asset_id)
                icon_count = 2 if asset_id == "research-2" else 1
                player["icons"]["research"] = player["icons"].get("research", 0) + icon_count
                player["icons"]["science"] = player["icons"].get("science", 0) + icon_count
                queued.append({
                    "op": "trigger_icon_entered", "timing": "immediate",
                    "args": {"icon": "science", "count": icon_count},
                })
                if asset_id == "research-reputation":
                    queued.append({
                        "op": "move_track", "timing": "immediate",
                        "args": {"track": "reputation", "amount": 2},
                    })
                elif asset_id == "research-hand-limit":
                    player["hand_limit"] += 2
                count = len(player["universities"])
                if count == 2:
                    queued.append({"op": "choose_action_upgrade", "timing": "system", "args": {}})
                elif count == 3:
                    queued.append({
                        "op": "move_track", "timing": "immediate",
                        "args": {"track": "conservation", "amount": 2},
                    })
            else:
                player["partner_zoos"].append(asset_id)
                count = len(player["partner_zoos"])
                if count == 2:
                    queued.append({"op": "choose_action_upgrade", "timing": "system", "args": {}})
                elif count == 3:
                    queued.append({
                        "op": "gain_association_worker", "timing": "immediate",
                        "args": {"amount": 1},
                    })
                elif count == 4:
                    queued.append({
                        "op": "move_track", "timing": "immediate",
                        "args": {"track": "conservation", "amount": 2},
                    })
            state["resolution"]["queue"][0:0] = self._frames(
                queued, int(continuation.get("actor_seat", seat)), seat,
                str(continuation.get("source_id", "bonus-association-asset")), None, {},
            )
            events.append({
                "type": "bonus_association_asset_taken", "seat": seat,
                "asset": asset, "asset_id": asset_id,
            })
            return
        if continuation_type == "discard_final_scoring_card":
            if len(selected) != 1:
                raise SemanticRuleError("exactly one Final Scoring card must be discarded")
            selected_id = selected[0]["id"]
            discarded = [
                card for card in player["final_scoring_cards"] if card["id"] == selected_id
            ]
            if len(discarded) != 1:
                raise SemanticRuleError("selected Final Scoring card is no longer held")
            player["final_scoring_cards"] = [
                card for card in player["final_scoring_cards"] if card["id"] != selected_id
            ]
            state["final_scoring_discard"].extend(discarded)
            events.append({
                "type": "final_scoring_card_discarded", "seat": seat, "card_id": selected_id,
            })
            return
        if continuation_type != "discard_selected_cards":
            raise SemanticRuleError(f"unknown semantic choice continuation: {continuation_type}")
        selected_ids = {option["id"] for option in selected}
        discarded = [card for card in player["hand"] if card["id"] in selected_ids]
        if len(discarded) != len(selected_ids):
            raise SemanticRuleError("selected cards are no longer in hand")
        player["hand"] = [card for card in player["hand"] if card["id"] not in selected_ids]
        state["zoo_discard"].extend(discarded)
        events.append({"type": "break_cards_discarded", "seat": seat, "count": len(discarded)})

    def _apply_effect(
        self, state: dict[str, Any], frame: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        operation = frame["operation"]
        op = operation["op"]
        args = operation["args"]
        context = self._context(state, frame)
        seat = frame.get("target_seat")
        if seat is None:
            seat = frame["actor_seat"]
        player = state["players"][seat]
        base_event = {"seat": seat, "source_id": frame["source_id"], "op": op}
        if op == "noop":
            return [{"type": "semantic_noop", **base_event}]
        if op in {"gain_money", "lose_money", "pay_money"}:
            amount = self._integer(args.get("amount"), context, minimum=0)
            if op == "gain_money":
                player["money"] += amount
                delta = amount
            elif op == "pay_money":
                if player["money"] < amount:
                    raise SemanticRuleError("player cannot pay the semantic money cost")
                player["money"] -= amount
                delta = -amount
            else:
                actual = min(player["money"], amount)
                player["money"] -= actual
                delta = -actual
            return [{"type": "money_changed", **base_event, "delta": delta, "value": player["money"]}]
        if op == "gain_x_token":
            amount = self._integer(args.get("amount"), context, minimum=0)
            old = player["x_tokens"]
            player["x_tokens"] = min(5, old + amount)
            return [{
                "type": "x_tokens_changed", **base_event,
                "delta": player["x_tokens"] - old, "value": player["x_tokens"],
            }]
        if op == "add_source_card_tokens":
            amount = self._integer(args.get("amount"), context, minimum=0)
            card = frame.get("card")
            instance_id = card.get("id") if isinstance(card, Mapping) else None
            matches = [
                played for played in player["played_cards"]
                if played.get("id") == instance_id
            ]
            if len(matches) != 1:
                raise SemanticRuleError("source-card token effect cannot resolve its instance")
            matches[0]["stored_tokens"] = int(matches[0].get("stored_tokens", 0)) + amount
            return [{
                "type": "source_card_tokens_added", **base_event,
                "instance_id": instance_id, "amount": amount,
                "value": matches[0]["stored_tokens"],
            }]
        if op == "reveal_first_animal_size":
            size_class = args.get("size_class")
            if size_class not in {"small", "large"}:
                raise SemanticRuleError("revealed Animal size must be small or large")
            revealed: list[dict[str, Any]] = []
            found: dict[str, Any] | None = None
            # A single search may inspect every card that was in the two Zoo-card
            # piles when the effect started, but never recycles cards it just
            # revealed and discarded.
            pools: list[list[dict[str, Any]]] = [state["zoo_deck"]]
            recycled: list[dict[str, Any]] = []
            if state["zoo_discard"]:
                recycled = list(state["zoo_discard"])
                state["zoo_discard"] = []
                random.Random(
                    f"{state['seed']}:waza:{state['resolution']['next_choice_id']}:"
                    f"{frame['source_id']}:{size_class}"
                ).shuffle(recycled)
                pools.append(recycled)
            found_pool_index: int | None = None
            for pool_index, pool in enumerate(pools):
                while pool:
                    card = pool.pop()
                    if self._card_animal_size_class(card) == size_class:
                        found = card
                        found_pool_index = pool_index
                        break
                    revealed.append(card)
                if found is not None:
                    break
            if found_pool_index == 0 and recycled:
                # The original discard pile was not searched.
                state["zoo_discard"].extend(recycled)
            elif found_pool_index == 1 and recycled:
                # Unsearched recycled cards become the new draw pile.
                state["zoo_deck"][0:0] = recycled
            state["zoo_discard"].extend(revealed)
            if found is not None:
                player["hand"].append(found)
            return [{
                "type": "waza_animal_search_resolved", **base_event,
                "size_class": size_class, "revealed": len(revealed) + (found is not None),
                "discarded": len(revealed),
                "card_id": None if found is None else found.get("id"),
            }]
        if op in {"gain_icon_reward", "gain_tiered_icon_reward", "gain_tiered_reward"}:
            icon = args.get("icon")
            scope = args.get("scope")
            reward = args.get("reward")
            if reward not in {
                "appeal", "x_token", "money", "conservation", "reputation",
            }:
                raise SemanticRuleError("icon reward resource is invalid")
            if op == "gain_tiered_reward":
                count = self._integer(args.get("count"), context, minimum=0)
            else:
                if not isinstance(icon, str) or not icon:
                    raise SemanticRuleError("icon reward requires an icon")
                if scope not in {"actor", "all_players"}:
                    raise SemanticRuleError("icon reward scope is invalid")
                owners = [player] if scope == "actor" else state["players"]
                count = sum(int(owner["icons"].get(icon, 0)) for owner in owners)
            if op == "gain_icon_reward":
                per_icon = self._integer(args.get("per_icon"), context, minimum=0)
                maximum = self._integer(args.get("maximum"), context, minimum=0)
                amount = min(maximum, count * per_icon)
            else:
                thresholds = args.get("thresholds")
                rewards = args.get("rewards")
                if (
                    not isinstance(thresholds, list) or not isinstance(rewards, list)
                    or len(thresholds) != len(rewards) or not thresholds
                    or any(
                        not isinstance(item, int) or isinstance(item, bool) or item < 0
                        for item in [*thresholds, *rewards]
                    )
                    or thresholds != sorted(set(thresholds))
                ):
                    raise SemanticRuleError("tiered icon reward table is invalid")
                amount = max(
                    (tier_reward for threshold, tier_reward in zip(thresholds, rewards)
                     if count >= threshold),
                    default=0,
                )
            if reward == "x_token":
                old = player["x_tokens"]
                player["x_tokens"] = min(5, old + amount)
                delta = player["x_tokens"] - old
                value = player["x_tokens"]
            elif reward == "money":
                old = player["money"]
                player["money"] += amount
                delta = amount
                value = player["money"]
            else:
                track = reward
                old = player["tracks"][track]
                player["tracks"][track] = min(
                    state["track_limits"][track], old + amount,
                )
                delta = player["tracks"][track] - old
                value = player["tracks"][track]
                self._queue_crossed_milestones(
                    state, frame, track, old, player["tracks"][track],
                )
            return [{
                "type": (
                    "tiered_reward_gained" if op == "gain_tiered_reward"
                    else "icon_reward_gained"
                ), **base_event,
                "icon": icon, "scope": scope, "reward": reward,
                "count": count, "icon_count": count, "amount": delta, "value": value,
            }]
        if op == "gain_association_worker":
            amount = self._integer(args.get("amount", 1), context, minimum=0)
            workers = player["association_workers"]
            activated = min(amount, workers["reserve"])
            workers["reserve"] -= activated
            workers["active"] += activated
            return [{
                "type": "association_workers_activated", **base_event,
                "delta": activated, "active": workers["active"], "reserve": workers["reserve"],
            }]
        if op == "add_action_token":
            action = args.get("action")
            token_type = args.get("token")
            if action not in {"animals", "cards", "build", "association", "sponsors"}:
                raise SemanticRuleError("add_action_token.action is invalid")
            if token_type not in {"multiplier", "venom", "constriction"}:
                raise SemanticRuleError("add_action_token.token is invalid")
            action_card = next(card for card in player["action_cards"] if card["action"] == action)
            action_card["tokens"].append({"type": token_type, "source_id": frame["source_id"]})
            return [{
                "type": "action_token_added", **base_event,
                "action": action, "token": token_type,
            }]
        if op == "grant_extra_action":
            excluded = args.get("excluded_action")
            fixed_action = args.get("action")
            valid_actions = {"animals", "cards", "build", "association", "sponsors"}
            if (
                (excluded not in valid_actions and fixed_action not in valid_actions)
                or (excluded in valid_actions and fixed_action in valid_actions)
            ):
                raise SemanticRuleError(
                    "grant_extra_action requires exactly one fixed or excluded action"
                )
            if state["turn"].get("extra_action") is not None:
                raise SemanticRuleError("an extra action is already pending")
            state["turn"]["extra_action"] = {
                "seat": seat,
                "excluded_action": excluded,
                "action": fixed_action,
                "source_id": frame["source_id"],
            }
            return [{
                "type": "extra_action_granted", **base_event,
                "excluded_action": excluded,
                "action": fixed_action,
            }]
        if op == "move_track":
            track = args.get("track")
            if track not in state["track_limits"]:
                raise SemanticRuleError(f"unknown Ark Nova track: {track}")
            amount = self._integer(args.get("amount"), context)
            old = player["tracks"][track]
            limit = (
                reputation_track_limit(player)
                if track == "reputation" else state["track_limits"][track]
            )
            player["tracks"][track] = max(0, min(limit, old + amount))
            self._queue_crossed_milestones(state, frame, track, old, player["tracks"][track])
            return [{
                "type": "track_moved", **base_event, "track": track,
                "delta": player["tracks"][track] - old, "value": player["tracks"][track],
            }]
        if op == "advance_break":
            track = state["break"]
            amount = self._integer(args.get("amount"), context, minimum=0)
            if track["mode"] == "solo_round":
                return [{
                    "type": "break_track_advance_skipped_in_solo",
                    **base_event, "amount": amount,
                }]
            if track["mode"] != "shared_track" or track["limit"] is None:
                raise SemanticRuleError("shared break-track advancement is unavailable")
            old = track["position"]
            track["position"] = min(track["limit"], old + amount)
            triggered = not track["pending"] and track["position"] == track["limit"]
            result = [{
                "type": "break_track_advanced", **base_event,
                "delta": track["position"] - old, "value": track["position"],
            }]
            if triggered:
                track["pending"] = True
                track["initiator"] = frame["actor_seat"]
                old_x = state["players"][frame["actor_seat"]]["x_tokens"]
                state["players"][frame["actor_seat"]]["x_tokens"] = min(5, old_x + 1)
                result.append({
                    "type": "break_triggered", "seat": frame["actor_seat"],
                    "x_token_delta": state["players"][frame["actor_seat"]]["x_tokens"] - old_x,
                })
            return result
        if op == "draw_cards":
            amount = self._integer(args.get("amount"), context, minimum=0)
            drawn = []
            for _ in range(min(amount, len(state["zoo_deck"]))):
                drawn.append(state["zoo_deck"].pop())
            player["hand"].extend(drawn)
            return [{"type": "cards_drawn", **base_event, "count": len(drawn)}]
        if op == "take_display_sponsors":
            sponsors = [
                card for card in state["card_display"]
                if self._card_kind(card) == "sponsor"
            ]
            sponsor_ids = {card.get("id") for card in sponsors}
            if None in sponsor_ids or len(sponsor_ids) != len(sponsors):
                raise SemanticRuleError("display Sponsors require unique stable IDs")
            state["card_display"] = [
                card for card in state["card_display"] if card.get("id") not in sponsor_ids
            ]
            player["hand"].extend(sponsors)
            return [{
                "type": "display_sponsors_taken", **base_event,
                "count": len(sponsors), "card_ids": sorted(sponsor_ids),
            }]
        if op == "refill_card_display":
            target_size = self._integer(args.get("target_size"), context, minimum=0)
            added = 0
            while len(state["card_display"]) < target_size and state["zoo_deck"]:
                state["card_display"].append(state["zoo_deck"].pop())
                added += 1
            return [{
                "type": "card_display_refilled", **base_event,
                "added": added, "size": len(state["card_display"]),
            }]
        if op == "introduce_base_project":
            project_id = args.get("project_id")
            if not isinstance(project_id, str) or not project_id:
                raise SemanticRuleError("introduce_base_project requires a project ID")
            if any(project.get("id") == project_id for project in state["conservation_projects"]):
                return [{
                    "type": "base_project_already_in_play", **base_event,
                    "project_id": project_id,
                }]
            matches = [
                card for card in state["base_project_supply"]
                if card.get("entry_id", card.get("id")) == project_id
            ]
            if not matches:
                return [{
                    "type": "base_project_unavailable", **base_event,
                    "project_id": project_id,
                }]
            card = matches[0]
            state["base_project_supply"].remove(card)
            state["conservation_projects"].append({
                "id": project_id, "base": True, "claims": [],
            })
            return [{
                "type": "base_project_introduced", **base_event,
                "project_id": project_id, "physical_id": card.get("id"),
            }]
        if op == "set_flag":
            flag = args.get("flag")
            if not isinstance(flag, str) or _IDENTIFIER.fullmatch(flag) is None:
                raise SemanticRuleError("set_flag.flag must be a stable identifier")
            value = args.get("value", True)
            if not isinstance(value, bool):
                raise SemanticRuleError("set_flag.value must be boolean")
            player["flags"][flag] = value
            return [{"type": "flag_changed", **base_event, "flag": flag, "value": value}]
        if op == "add_modifier":
            modifier_id = args.get("id")
            trigger = args.get("trigger")
            effects = args.get("effects")
            if not isinstance(modifier_id, str) or _IDENTIFIER.fullmatch(modifier_id) is None:
                raise SemanticRuleError("modifier requires a stable ID")
            if not isinstance(trigger, str) or not trigger:
                raise SemanticRuleError("modifier requires a trigger")
            if not isinstance(effects, list):
                raise SemanticRuleError("modifier effects must be an array")
            if any(item["id"] == modifier_id and item["source_id"] == frame["source_id"] for item in player["modifiers"]):
                raise SemanticRuleError("modifier is already active")
            modifier = {
                "id": modifier_id,
                "source_id": frame["source_id"],
                "trigger": trigger,
                "condition": deepcopy(args.get("condition")),
                "effects": deepcopy(effects),
            }
            if isinstance(frame.get("card"), Mapping):
                modifier["source_instance_id"] = frame["card"].get("id")
            kind = args.get("kind")
            if kind is not None:
                if kind not in STATIC_MODIFIER_KINDS:
                    raise SemanticRuleError("modifier kind is not a supported static rule")
                amount = args.get("amount")
                if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
                    raise SemanticRuleError("static modifier amount must be non-negative")
                modifier["kind"] = kind
                modifier["amount"] = amount
                if kind == "animal_cost_discount":
                    animal_size = args.get("animal_size")
                    if animal_size not in {"small", "large"}:
                        raise SemanticRuleError("animal discount requires a size class")
                    modifier["animal_size"] = animal_size
            player["modifiers"].append(modifier)
            return [{"type": "modifier_added", **base_event, "modifier_id": modifier_id}]
        if op == "trigger_icon_entered":
            icon = args.get("icon")
            count = args.get("count", 1)
            if (
                not isinstance(icon, str) or not icon
                or not isinstance(count, int) or isinstance(count, bool) or count < 1
            ):
                raise SemanticRuleError("icon-entered trigger requires an icon and positive count")
            actor = frame["actor_seat"]
            owners = self._clockwise_seats(state, actor, include_actor=True)
            queued: list[dict[str, Any]] = []
            for _ in range(count):
                queued.extend(self._matching_modifier_frames(
                    state, f"icon_entered:self:{icon}", actor, [actor],
                    {"icon": icon},
                ))
                queued.extend(self._matching_modifier_frames(
                    state, f"icon_entered:any:{icon}", actor, owners,
                    {"icon": icon},
                ))
            distinct_icons = {
                "africa", "americas", "asia", "australia", "europe",
                "bear", "bird", "herbivore", "pet", "predator", "primate", "reptile",
            }
            if icon in distinct_icons and int(player["icons"].get(icon, 0)) == count:
                queued.extend(self._matching_modifier_frames(
                    state, "distinct_icon_entered", actor, [actor], {"icon": icon},
                ))
            queued = self._ordered_frames(
                queued, actor_seat=actor, label=f"Order {icon} icon effects",
            )
            state["resolution"]["queue"][0:0] = queued
            return [{
                "type": "zoo_icon_entered", **base_event,
                "icon": icon, "count": count, "modifier_count": len(queued),
            }]
        if op == "trigger_animal_played":
            size_class = args.get("size_class")
            if size_class not in {"small", "medium", "large"}:
                raise SemanticRuleError("animal-played trigger requires a size class")
            actor = frame["actor_seat"]
            bindings = {
                "size_class": size_class,
                "entry_id": args.get("entry_id"),
                "instance_id": args.get("instance_id"),
            }
            queued = self._matching_modifier_frames(
                state, "animal_played", actor, [actor], bindings,
            )
            queued.extend(self._matching_modifier_frames(
                state, f"{size_class}_animal_played", actor, [actor], bindings,
            ))
            queued = self._ordered_frames(
                queued, actor_seat=actor, label="Order Animal-played effects",
            )
            state["resolution"]["queue"][0:0] = queued
            return [{
                "type": "semantic_animal_played", **base_event,
                **bindings, "modifier_count": len(queued),
            }]
        if op == "open_bonus_sponsor_play":
            source = frame.get("card")
            source_instance_id = source.get("id") if isinstance(source, Mapping) else None
            source_card = next((
                card for card in player["played_cards"]
                if card.get("id") == source_instance_id
            ), None)
            if source_card is None:
                raise SemanticRuleError("bonus Sponsor source card is unavailable")
            if int(source_card.get("stored_tokens", 0)) < 1:
                return [{
                    "type": "bonus_sponsor_window_skipped", **base_event,
                    "reason": "no_source_tokens", "source_instance_id": source_instance_id,
                }]
            existing = state["turn"].get("bonus_sponsor_play")
            if existing is not None:
                if (
                    existing.get("seat") != seat
                    or existing.get("source_instance_id") != source_instance_id
                ):
                    raise SemanticRuleError("another bonus Sponsor window is already pending")
                existing["remaining_triggers"] = int(existing.get("remaining_triggers", 1)) + 1
            else:
                state["turn"]["bonus_sponsor_play"] = {
                    "seat": seat, "source_instance_id": source_instance_id,
                    "source_id": frame["source_id"], "remaining_triggers": 1,
                    "selected": None,
                }
            return [{
                "type": "bonus_sponsor_window_opened", **base_event,
                "source_instance_id": source_instance_id,
                "remaining_triggers": state["turn"]["bonus_sponsor_play"]["remaining_triggers"],
            }]
        if op == "trigger_building_placed":
            raw_cells = args.get("cells")
            if (
                not isinstance(raw_cells, list) or not raw_cells
                or any(
                    not isinstance(cell, Mapping)
                    or not isinstance(cell.get("q"), int)
                    or not isinstance(cell.get("r"), int)
                    for cell in raw_cells
                )
            ):
                raise SemanticRuleError("building-placed trigger requires axial cells")
            actor = frame["actor_seat"]
            footprint = {(cell["q"], cell["r"]) for cell in raw_cells}
            zoo_map = state["players"][actor]["map"]
            bindings: dict[str, Any] = {"covered_cells": len(footprint)}
            for terrain in ("water", "rock"):
                terrain_cells = {
                    (cell["q"], cell["r"]) for cell in zoo_map["cells"]
                    if cell["terrain"] == terrain and (cell["q"], cell["r"]) not in footprint
                }
                bindings[f"adjacent_{terrain}_cells"] = sum(
                    bool(axial_hex_neighbors(cell) & terrain_cells)
                    for cell in footprint
                )
            queued = self._matching_modifier_frames(
                state, "building_placed", actor, [actor], bindings,
            )
            queued = self._ordered_frames(
                queued, actor_seat=actor, label="Order building-placement effects",
            )
            state["resolution"]["queue"][0:0] = queued
            return [{
                "type": "semantic_building_placed", **base_event,
                **bindings, "modifier_count": len(queued),
            }]
        if op == "trigger_project_supported":
            release = args.get("release", False)
            if not isinstance(release, bool):
                raise SemanticRuleError("project-supported release binding must be boolean")
            actor = frame["actor_seat"]
            bindings = {"release": release}
            queued = self._matching_modifier_frames(
                state, "project_supported", actor, [actor], bindings,
            )
            if release:
                queued.extend(self._matching_modifier_frames(
                    state, "release_project_supported", actor, [actor], bindings,
                ))
            queued = self._ordered_frames(
                queued, actor_seat=actor, label="Order project-support effects",
            )
            state["resolution"]["queue"][0:0] = queued
            return [{
                "type": "semantic_project_supported", **base_event,
                "release": release, "modifier_count": len(queued),
            }]
        if op == "clear_action_tokens":
            removed = 0
            clearable = {"multiplier", "venom", "constriction"}
            for action_card in player["action_cards"]:
                kept = []
                for token in action_card["tokens"]:
                    token_type = token if isinstance(token, str) else token.get("type")
                    if token_type in clearable:
                        removed += 1
                    else:
                        kept.append(token)
                action_card["tokens"] = kept
            return [{"type": "break_action_tokens_cleared", **base_event, "count": removed}]
        if op == "recall_association_workers":
            workers = player["association_workers"]
            count = len(workers["committed"])
            workers["active"] += count
            workers["committed"] = []
            return [{"type": "break_workers_recalled", **base_event, "count": count}]
        if op == "replenish_association":
            for supply in state["association_board"].values():
                if not isinstance(supply, dict):
                    continue
                for key, value in supply.items():
                    if isinstance(value, int) and not isinstance(value, bool):
                        supply[key] = max(value, 1)
                    elif isinstance(value, dict) and "available" in value:
                        owners = value.get("owners", [])
                        value["available"] = 0 if len(owners) >= state["player_count"] else 1
            return [{"type": "break_association_replenished", **base_event}]
        if op == "refresh_display":
            discard_count = min(2, len(state["card_display"]))
            discarded = state["card_display"][:discard_count]
            state["card_display"] = state["card_display"][discard_count:]
            state["zoo_discard"].extend(discarded)
            while len(state["card_display"]) < 6 and state["zoo_deck"]:
                state["card_display"].append(state["zoo_deck"].pop())
            return [{"type": "break_display_refreshed", **base_event, "discarded": discard_count}]
        if op == "take_income":
            kiosk_income = (
                _official_kiosk_income(player)
                if state.get("official_track_income")
                else int(player["income"].get("kiosks", 0))
            )
            amount = (
                (
                    appeal_income(int(player["tracks"]["appeal"]))
                    if state.get("official_track_income")
                    else int(player["income"].get("appeal", 0))
                )
                + kiosk_income
                + int(player["income"].get("other", 0))
            )
            player["money"] += amount
            triggered = self._matching_modifier_frames(state, "income", seat, [seat], {})
            triggered = self._ordered_frames(
                triggered, actor_seat=seat, label="Order income effects",
            )
            state["resolution"]["queue"][0:0] = triggered
            return [{
                "type": "break_income_collected", **base_event,
                "amount": amount, "kiosk_income": kiosk_income,
            }]
        if op == "reset_break":
            track = state["break"]
            track["position"] = 0
            track["pending"] = False
            track["count"] += 1
            return [{"type": "break_track_reset", **base_event, "break_count": track["count"]}]
        if op == "add_score_entry":
            points = self._integer(args.get("points"), context)
            category = args.get("category", "card")
            if not isinstance(category, str) or not category:
                raise SemanticRuleError("score entry category must be a string")
            player["score_entries"].append({
                "source_id": frame["source_id"], "category": category, "points": points,
            })
            return [{"type": "score_entry_added", **base_event, "category": category, "points": points}]
        if op == "take_conservation_bonus":
            at = args.get("at")
            bonus_id = args.get("bonus_id")
            if at not in (5, 8) or not isinstance(bonus_id, str):
                raise SemanticRuleError("invalid conservation bonus selection")
            tiles = state.get("conservation_bonus_slots", {}).get(str(at), [])
            tile = next((item for item in tiles if item.get("id") == bonus_id), None)
            if tile is None or not tile.get("available", True):
                raise SemanticRuleError("conservation bonus is no longer available")
            effects = tile.get("effects")
            if not isinstance(effects, list):
                raise SemanticRuleError("conservation bonus effects must be an array")
            tile["available"] = False
            state["resolution"]["queue"][0:0] = self._frames(
                effects,
                frame["actor_seat"],
                seat,
                f"bonus:{bonus_id}",
                None,
                {**frame.get("bindings", {}), "bonus_id": bonus_id},
            )
            return [{
                "type": "conservation_bonus_taken", **base_event,
                "at": at, "bonus_id": bonus_id,
            }]
        if op == "mark_final_scoring_discard_complete":
            state["endgame"]["final_scoring_discard_completed"] = True
            return [{"type": "final_scoring_discard_completed", **base_event}]
        custom_id = operation.get("custom_id")
        if not isinstance(custom_id, str) or custom_id not in self._effect_handlers:
            raise SemanticRuleError(f"unregistered custom effect: {custom_id}")
        return self._effect_handlers[custom_id](state, frame, self)

    def _matching_modifier_frames(
        self,
        state: Mapping[str, Any],
        trigger: str,
        actor_seat: int,
        owner_seats: list[int],
        bindings: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        frames: list[dict[str, Any]] = []
        for owner in owner_seats:
            for modifier in state["players"][owner]["modifiers"]:
                if modifier["trigger"] != trigger:
                    continue
                source_card = next(
                    (
                        card for card in state["players"][owner]["played_cards"]
                        if card.get("id") == modifier.get("source_instance_id")
                    ),
                    None,
                )
                probe = {
                    "actor_seat": actor_seat,
                    "target_seat": owner,
                    "source_id": modifier["source_id"],
                    "card": source_card,
                    "bindings": dict(bindings),
                }
                condition = modifier.get("condition")
                if condition is not None and not self.evaluate(condition, self._context(state, probe)):
                    continue
                frames.extend(self._frames(
                    modifier["effects"], actor_seat, owner,
                    modifier["source_id"], source_card, bindings,
                ))
        return frames

    def _ordered_frames(
        self, frames: list[dict[str, Any]], *, actor_seat: int, label: str,
    ) -> list[dict[str, Any]]:
        """Turn simultaneous frames into one ordering window without losing owners."""
        if len(frames) <= 1:
            return frames
        effects = []
        for frame in frames:
            operation = deepcopy(dict(frame["operation"]))
            operation["_semantic_source_id"] = frame["source_id"]
            operation["_semantic_target_seat"] = frame.get("target_seat")
            operation["_semantic_bindings"] = deepcopy(frame.get("bindings", {}))
            if frame.get("card") is not None:
                operation["_semantic_card"] = deepcopy(frame["card"])
            effects.append(operation)
        return self._frames(
            simultaneous_effects(effects, label=label),
            actor_seat, actor_seat, f"trigger:{label}", None, {},
        )

    def _queue_crossed_milestones(
        self, state: dict[str, Any], frame: Mapping[str, Any], track: str, old: int, new: int,
    ) -> None:
        if new <= old:
            return
        crossed = []
        player = state["players"][frame.get("target_seat") if frame.get("target_seat") is not None else frame["actor_seat"]]
        for milestone in sorted(state.get("milestones", []), key=lambda item: item["at"]):
            if milestone.get("track") != track or not old < milestone.get("at", -1) <= new:
                continue
            milestone_id = milestone.get("id")
            if not isinstance(milestone_id, str):
                raise SemanticRuleError("track milestone requires a stable ID")
            scope = milestone.get("scope", "player")
            claimed = (state["claimed_global_milestones"] if scope == "global"
                       else player["claimed_milestones"])
            if milestone_id in claimed:
                continue
            claimed.append(milestone_id)
            crossed.extend(self._frames(
                milestone.get("effects", []),
                frame["actor_seat"],
                player["seat"],
                f"milestone:{milestone_id}",
                None,
                {"milestone": milestone_id},
            ))
        state["resolution"]["queue"][0:0] = crossed

    def _complete(self, state: dict[str, Any], events: list[dict[str, Any]]) -> None:
        completion = state["resolution"].get("completion")
        state["resolution"]["completion"] = None
        if completion is None:
            return
        if completion.get("type") == "finish_break":
            initiator = completion.get("initiator")
            state["phase"] = "active"
            state["active_seat"] = (initiator + 1) % state["player_count"]
            events.append({
                "type": "break_finished",
                "initiator": initiator,
                "next_seat": state["active_seat"],
            })
            return
        if completion.get("type") == "finish_turn":
            seat = completion.get("seat")
            if not isinstance(seat, int) or isinstance(seat, bool) or not 0 <= seat < state["player_count"]:
                raise SemanticRuleError("finish-turn completion requires a valid seat")
            hypnosis_action = state["turn"].get("hypnosis_action")
            if hypnosis_action is not None:
                if hypnosis_action.get("seat") != seat:
                    raise SemanticRuleError("Hypnosis action belongs to a different seat")
                state["phase"] = "active"
                state["active_seat"] = seat
                events.append({
                    "type": "hypnosis_action_window_opened", "seat": seat,
                    "target_seat": hypnosis_action.get("target_seat"),
                    "action": hypnosis_action.get("action"),
                })
                return
            extra_action = state["turn"].get("extra_action")
            if extra_action is not None:
                if extra_action.get("seat") != seat:
                    raise SemanticRuleError("extra action belongs to a different seat")
                state["phase"] = "active"
                state["active_seat"] = seat
                events.append({
                    "type": "extra_action_window_opened",
                    "seat": seat,
                    "excluded_action": extra_action.get("excluded_action"),
                    "action": extra_action.get("action"),
                })
                return
            venom = settle_turn_venom(state, seat)
            if state["break"]["pending"]:
                state["phase"] = "break_pending"
                state["active_seat"] = seat
            else:
                state["phase"] = "active"
                state["active_seat"] = (seat + 1) % state["player_count"]
            events.append({
                "type": "turn_finished",
                "seat": seat,
                "turn": state["turn"]["number"],
                "next_seat": state["active_seat"],
                "break_pending": bool(state["break"]["pending"]),
                "venom": venom,
            })
            return
        if completion.get("type") == "finish_final_scoring_discard":
            resume_phase = completion.get("resume_phase")
            if not isinstance(resume_phase, str) or not resume_phase:
                raise SemanticRuleError("Final Scoring discard completion requires a resume phase")
            state["phase"] = resume_phase
            events.append({"type": "final_scoring_discard_window_finished"})
            return
        raise SemanticRuleError(f"unknown semantic completion: {completion.get('type')}")

    def validate_predicate_vocabulary(self, predicate: Mapping[str, Any]) -> set[str]:
        operation = _operation(predicate, "predicate")
        op = operation["op"]
        if op not in PREDICATE_OPS:
            raise SemanticRuleError(f"unknown predicate operation: {op}")
        if op == "custom":
            custom_id = operation.get("custom_id")
            if custom_id not in self._predicate_handlers:
                raise SemanticRuleError(f"unregistered custom predicate: {custom_id}")
        operations = {op}
        if op in {"all", "any"}:
            for child in self._conditions(operation["args"]):
                operations |= self.validate_predicate_vocabulary(child)
        elif op == "not":
            operations |= self.validate_predicate_vocabulary(operation["args"].get("condition"))
        elif op == "compare":
            if operation["args"].get("operator") not in {"==", "!=", ">=", ">", "<=", "<"}:
                raise SemanticRuleError("compare.operator must be ==, !=, >=, >, <=, or <")
            self._validate_value_vocabulary(operation["args"].get("left"))
            self._validate_value_vocabulary(operation["args"].get("right"))
        elif op in {"has_tag", "has_icon"}:
            key = operation["args"].get("tag" if op == "has_tag" else "icon")
            if not isinstance(key, str) or not key:
                raise SemanticRuleError(f"{op} requires a stable ID")
            self._validate_value_vocabulary(operation["args"].get("count", 1))
        elif op == "flag_set":
            if not isinstance(operation["args"].get("flag"), str):
                raise SemanticRuleError("flag_set requires a flag ID")
        elif op == "player_count":
            count = operation["args"].get("count")
            if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 4:
                raise SemanticRuleError("player_count requires an integer from one to four")
        elif op == "in":
            values = operation["args"].get("values")
            if not isinstance(values, list):
                raise SemanticRuleError("in.values must be an array")
            self._validate_value_vocabulary(operation["args"].get("value"))
            for value in values:
                self._validate_value_vocabulary(value)
        return operations

    def _validate_value_vocabulary(self, expression: Any) -> None:
        if expression is None or isinstance(expression, (str, int, bool)):
            return
        if not isinstance(expression, Mapping):
            raise SemanticRuleError("semantic value must be a literal, reference, or calculation")
        if set(expression) == {"ref"}:
            reference = expression["ref"]
            if not isinstance(reference, str) or "." not in reference:
                raise SemanticRuleError("semantic reference must contain a root and path")
            root, path = reference.split(".", 1)
            if root not in {"actor", "target", "card", "state", "binding"}:
                raise SemanticRuleError(f"unknown semantic reference root: {root}")
            if root == "card" and not path.startswith("facts."):
                raise SemanticRuleError("card references are limited to card.facts")
            return
        if set(expression) != {"calc", "values"}:
            raise SemanticRuleError("semantic value object must contain ref or calc/values")
        if expression["calc"] not in {"add", "multiply", "minimum", "maximum", "floor_divide"}:
            raise SemanticRuleError(f"unsupported semantic calculation: {expression['calc']}")
        values = expression["values"]
        if not isinstance(values, list) or not values:
            raise SemanticRuleError("calculation values must be a non-empty array")
        if expression["calc"] == "floor_divide" and len(values) != 2:
            raise SemanticRuleError("floor_divide requires exactly two values")
        for value in values:
            self._validate_value_vocabulary(value)

    def validate_effect_vocabulary(
        self, effect: Mapping[str, Any], *, allow_system: bool = False,
    ) -> tuple[set[str], set[str]]:
        operation = _operation(effect, "effect")
        op = operation["op"]
        if op not in EFFECT_OPS:
            raise SemanticRuleError(f"unknown effect operation: {op}")
        if op in SYSTEM_EFFECT_OPS and not allow_system:
            raise SemanticRuleError(f"system-only effect is forbidden in content: {op}")
        timing = operation.get("timing")
        if timing not in EFFECT_TIMINGS:
            raise SemanticRuleError(f"effect requires a supported timing: {timing}")
        predicate_ops: set[str] = set()
        effect_ops = {op}
        if operation.get("when") is not None:
            predicate_ops |= self.validate_predicate_vocabulary(operation["when"])
        if op == "custom":
            custom_id = operation.get("custom_id")
            if custom_id not in self._effect_handlers:
                raise SemanticRuleError(f"unregistered custom effect: {custom_id}")
        args = operation["args"]
        nested: list[Mapping[str, Any]] = []
        if op in {
            "gain_money", "lose_money", "pay_money", "gain_x_token", "advance_break",
            "draw_cards", "add_source_card_tokens",
        }:
            self._validate_value_vocabulary(args.get("amount"))
        elif op == "move_track":
            if args.get("track") not in {"appeal", "conservation", "reputation"}:
                raise SemanticRuleError("move_track requires appeal, conservation, or reputation")
            self._validate_value_vocabulary(args.get("amount"))
        elif op == "pilfer":
            if args.get("leader_track") not in {"appeal", "conservation"}:
                raise SemanticRuleError("pilfer requires an appeal or conservation leader track")
        elif op == "grant_hypnosis_action":
            maximum = args.get("maximum_target_slot")
            if (
                not isinstance(maximum, int) or isinstance(maximum, bool)
                or not 1 <= maximum <= 5
            ):
                raise SemanticRuleError("Hypnosis requires a maximum target slot from 1 to 5")
        elif op == "gain_icon_reward":
            if (
                not isinstance(args.get("icon"), str)
                or args.get("scope") not in {"actor", "all_players"}
                or args.get("reward") not in {
                    "appeal", "x_token", "money", "conservation", "reputation",
                }
            ):
                raise SemanticRuleError("gain_icon_reward has invalid identifiers")
            self._validate_value_vocabulary(args.get("per_icon"))
            self._validate_value_vocabulary(args.get("maximum"))
        elif op == "gain_tiered_icon_reward":
            thresholds = args.get("thresholds")
            rewards = args.get("rewards")
            if (
                not isinstance(args.get("icon"), str)
                or args.get("scope") not in {"actor", "all_players"}
                or args.get("reward") not in {
                    "appeal", "x_token", "money", "conservation", "reputation",
                }
                or not isinstance(thresholds, list) or not isinstance(rewards, list)
                or len(thresholds) != len(rewards) or not thresholds
                or any(
                    not isinstance(item, int) or isinstance(item, bool) or item < 0
                    for item in [*thresholds, *rewards]
                )
                or thresholds != sorted(set(thresholds))
            ):
                raise SemanticRuleError("gain_tiered_icon_reward has an invalid table")
        elif op == "gain_tiered_reward":
            thresholds = args.get("thresholds")
            rewards = args.get("rewards")
            if (
                args.get("reward") not in {
                    "appeal", "x_token", "money", "conservation", "reputation",
                }
                or not isinstance(thresholds, list) or not isinstance(rewards, list)
                or len(thresholds) != len(rewards) or not thresholds
                or any(
                    not isinstance(item, int) or isinstance(item, bool) or item < 0
                    for item in [*thresholds, *rewards]
                )
                or thresholds != sorted(set(thresholds))
            ):
                raise SemanticRuleError("gain_tiered_reward has an invalid table")
            self._validate_value_vocabulary(args.get("count"))
        elif op == "set_flag":
            if not isinstance(args.get("flag"), str) or not isinstance(args.get("value", True), bool):
                raise SemanticRuleError("set_flag requires a flag ID and boolean value")
        elif op == "trigger_icon_entered":
            count = args.get("count", 1)
            if (
                not isinstance(args.get("icon"), str)
                or not isinstance(count, int) or isinstance(count, bool) or count < 1
            ):
                raise SemanticRuleError("trigger_icon_entered requires an icon and positive count")
        elif op == "reveal_first_animal_size":
            if args.get("size_class") not in {"small", "large"}:
                raise SemanticRuleError("reveal_first_animal_size requires small or large")
        elif op == "trigger_animal_played":
            if args.get("size_class") not in {"small", "medium", "large"}:
                raise SemanticRuleError("trigger_animal_played requires an Animal size class")
        elif op == "trigger_building_placed":
            cells = args.get("cells")
            if (
                not isinstance(cells, list) or not cells
                or any(
                    not isinstance(cell, Mapping)
                    or set(cell) != {"q", "r"}
                    or not isinstance(cell["q"], int) or isinstance(cell["q"], bool)
                    or not isinstance(cell["r"], int) or isinstance(cell["r"], bool)
                    for cell in cells
                )
            ):
                raise SemanticRuleError("trigger_building_placed requires axial cells")
        elif op == "trigger_project_supported":
            if not isinstance(args.get("release", False), bool):
                raise SemanticRuleError("trigger_project_supported requires a boolean release flag")
        elif op == "introduce_base_project":
            if not isinstance(args.get("project_id"), str) or not args["project_id"]:
                raise SemanticRuleError("introduce_base_project requires a project ID")
        elif op == "place_free_building":
            building_types = args.get("building_types")
            maximum = args.get("maximum")
            if (
                not isinstance(building_types, list) or not building_types
                or any(not isinstance(value, str) for value in building_types)
                or not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1
            ):
                raise SemanticRuleError("place_free_building requires types and maximum")
        elif op == "add_score_entry":
            self._validate_value_vocabulary(args.get("points"))
        if op == "choose_effect_order":
            child_effects = args.get("effects")
            if not isinstance(child_effects, list) or not child_effects:
                raise SemanticRuleError("choose_effect_order.effects must be non-empty")
            if not isinstance(args.get("label", "Resolve simultaneous effects"), str):
                raise SemanticRuleError("choose_effect_order.label must be a string")
            nested.extend(child_effects)
        elif op == "choose_one":
            options = args.get("options", [])
            if not isinstance(options, list):
                raise SemanticRuleError("choose_one.options must be an array")
            seen_options = set()
            for option in options:
                if not isinstance(option, Mapping):
                    raise SemanticRuleError("choose_one option must be an object")
                option_id = option.get("id")
                if not isinstance(option_id, str) or option_id in seen_options:
                    raise SemanticRuleError("choose_one option IDs must be strings and unique")
                seen_options.add(option_id)
                if option.get("when") is not None:
                    predicate_ops |= self.validate_predicate_vocabulary(option["when"])
                option_effects = option.get("effects")
                if not isinstance(option_effects, list):
                    raise SemanticRuleError("choose_one option effects must be an array")
                nested.extend(option_effects)
        elif op in {"choose_opponent", "for_each_opponent", "for_each_player", "add_modifier"}:
            if args.get("condition") is not None:
                predicate_ops |= self.validate_predicate_vocabulary(args["condition"])
            child_effects = args.get("effects")
            if not isinstance(child_effects, list):
                raise SemanticRuleError(f"{op}.effects must be an array")
            nested.extend(child_effects)
            if op == "add_modifier":
                if not isinstance(args.get("id"), str) or not isinstance(args.get("trigger"), str):
                    raise SemanticRuleError("add_modifier requires stable id and trigger strings")
                kind = args.get("kind")
                if kind is not None:
                    if kind not in STATIC_MODIFIER_KINDS:
                        raise SemanticRuleError("add_modifier static kind is invalid")
                    amount = args.get("amount")
                    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
                        raise SemanticRuleError("add_modifier static amount is invalid")
                    if (
                        kind == "animal_cost_discount"
                        and args.get("animal_size") not in {"small", "large"}
                    ):
                        raise SemanticRuleError("animal discount size class is invalid")
        elif op == "choose_conservation_reward":
            if args.get("at") not in (5, 8):
                raise SemanticRuleError("choose_conservation_reward requires space 5 or 8")
        elif op == "choose_bonus_association_asset":
            if args.get("asset") not in {"university", "partner_zoo"}:
                raise SemanticRuleError(
                    "choose_bonus_association_asset requires university or partner_zoo"
                )
        elif op == "take_conservation_bonus":
            if args.get("at") not in (5, 8) or not isinstance(args.get("bonus_id"), str):
                raise SemanticRuleError("take_conservation_bonus requires space and bonus ID")
        for child in nested:
            child_predicates, child_effects = self.validate_effect_vocabulary(
                child, allow_system=allow_system,
            )
            predicate_ops |= child_predicates
            effect_ops |= child_effects
        return predicate_ops, effect_ops
