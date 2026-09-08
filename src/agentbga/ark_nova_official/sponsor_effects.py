"""Reviewed compiler for base-game Sponsor card effect records.

The reference dataset intentionally stores human-readable transcriptions.  This
module is the card-number boundary that turns only audited records into the
closed semantic vocabulary.  A record not listed here remains explicit
backlog; it is never silently treated as a no-op by the Sponsors action.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .sponsor_reference import corrected_direct_rewards


ON_PLAY = "on_play"


def _effect(op: str, args: Mapping[str, Any], timing: str = ON_PLAY, **extra: Any) -> dict[str, Any]:
    return {"op": op, "args": deepcopy(dict(args)), "timing": timing, **extra}


def _track(track: str, amount: Any, timing: str = ON_PLAY, *, when: Mapping[str, Any] | None = None) -> dict[str, Any]:
    effect = _effect("move_track", {"track": track, "amount": amount}, timing)
    if when is not None:
        effect["when"] = deepcopy(dict(when))
    return effect


def _modifier(
    component_id: str,
    trigger: str,
    effects: list[dict[str, Any]],
    *,
    kind: str | None = None,
    amount: int | None = None,
    animal_size: str | None = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "id": f"sponsor-{component_id}",
        "trigger": trigger,
        "effects": effects,
    }
    if kind is not None:
        args["kind"] = kind
    if amount is not None:
        args["amount"] = amount
    if animal_size is not None:
        args["animal_size"] = animal_size
    return _effect("add_modifier", args)


def _icon_trigger(component_id: str, icon: str, scope: str, effects: list[dict[str, Any]]) -> dict[str, Any]:
    return _modifier(component_id, f"icon_entered:{scope}:{icon}", effects)


def _all_icons(icons: tuple[str, ...]) -> dict[str, Any]:
    return {
        "op": "all",
        "args": {
            "conditions": [
                {"op": "has_icon", "args": {"icon": icon, "count": 1}}
                for icon in icons
            ],
        },
    }


def _ref(path: str) -> dict[str, str]:
    return {"ref": f"actor.{path}"}


def _multiply(value: Any, multiplier: int) -> dict[str, Any]:
    return {"calc": "multiply", "values": [value, multiplier]}


def _at_least(path: str, count: int) -> dict[str, Any]:
    return {
        "op": "compare",
        "args": {"left": _ref(path), "operator": ">=", "right": count},
    }


def _tiered_value(
    count: Any, reward: str, thresholds: list[int], rewards: list[int],
    timing: str = ON_PLAY,
) -> dict[str, Any]:
    return _effect(
        "gain_tiered_reward",
        {
            "count": count, "reward": reward,
            "thresholds": thresholds, "rewards": rewards,
        },
        timing,
    )


def _tiered_income(component_id: str, icon: str) -> list[dict[str, Any]]:
    return [_modifier(component_id, "income", [_effect(
        "gain_tiered_icon_reward",
        {
            "icon": icon,
            "scope": "actor",
            "reward": "money",
            "thresholds": [1, 3, 5],
            "rewards": [3, 6, 9],
        },
        "income",
    )])]


def compile_sponsor_effects(
    row: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[int]]:
    """Return executable effects plus unresolved source-record indexes.

    Direct printed track rewards are compiled generically.  ``resolved`` below
    refers to complete source effect records, so a composite record remains in
    backlog until every clause is represented.
    """
    component_id = str(row.get("id", ""))
    effects: list[dict[str, Any]] = []
    source_records = row.get("effects", [])
    resolved: set[int] = set()

    direct_rewards = corrected_direct_rewards(row)
    for field, track in (
        ("appeal", "appeal"),
        ("reputation", "reputation"),
        ("conservation", "conservation"),
    ):
        amount = direct_rewards.get(field, 0)
        if isinstance(amount, int) and not isinstance(amount, bool) and amount > 0:
            effects.append(_track(track, amount))

    if component_id == "201":
        take_card = _effect("take_map_reward_card", {}, "income")
        effects.extend([
            _effect("take_map_reward_card", {}),
            _modifier(component_id, "income", [take_card]),
            _effect(
                "gain_tiered_icon_reward",
                {
                    "icon": "science", "scope": "actor", "reward": "conservation",
                    "thresholds": [3, 6], "rewards": [1, 2],
                },
                "end_of_game",
            ),
        ])
        resolved.update({0, 1})
    elif component_id == "202":
        effects.append(_icon_trigger(component_id, "science", "self", [
            _track("reputation", 1, "on_trigger"),
        ]))
        resolved.add(0)
    elif component_id == "203":
        effects.extend([
            _tiered_value(_ref("university_count"), "money", [1, 2, 3], [2, 5, 10]),
            _modifier(
                component_id, "static", [],
                kind="association_project_strength", amount=4,
            ),
            _track(
                "conservation", 1, "end_of_game",
                when=_at_least("university_count", 3),
            ),
        ])
        resolved.add(0)
    elif component_id == "204":
        effects.extend([
            _effect("gain_money", {"amount": _multiply(_ref("icons.science"), 2)}),
            _icon_trigger(component_id, "science", "self", [
                _track("conservation", 1, "on_trigger"),
            ]),
        ])
        resolved.add(0)
    elif component_id == "205":
        resolved.add(0)
    elif component_id == "206":
        effects.extend([
            _track("appeal", _multiply(_ref("supported_project_count"), 2)),
            _modifier(component_id, "income", [
                _track("conservation", 1, "income"),
            ]),
        ])
        resolved.add(0)
    elif component_id == "207":
        conservation = {
            "calc": "floor_divide",
            "values": [_ref("distinct_continent_animal_category_count"), 2],
        }
        effects.extend([
            _track("conservation", conservation),
            _effect("for_each_opponent", {
                "effects": [_effect("gain_money", {
                    "amount": _multiply(conservation, 2),
                })],
            }),
        ])
        resolved.add(0)
    elif component_id == "208":
        effects.extend([
            _track("appeal", _ref("icons.science")),
            _icon_trigger(component_id, "science", "any", [
                _effect("gain_money", {"amount": 2}, "on_trigger"),
            ]),
            _track(
                "conservation", 1, "end_of_game",
                when=_at_least("distinct_animal_category_count", 5),
            ),
        ])
        resolved.update({0, 1})
    elif component_id == "209":
        effects.extend([
            _effect("gain_x_token", {"amount": 1}),
            _modifier(component_id, "income", [
                _effect("gain_x_token", {"amount": 1}, "income"),
            ]),
            _track(
                "conservation", 1, "end_of_game",
                when=_at_least("university_count", 3),
            ),
        ])
        resolved.add(0)
    elif component_id == "210":
        effects.extend([
            _track("appeal", _ref("icons.americas")),
            _icon_trigger(component_id, "americas", "self", [
                _effect(
                    "place_free_building",
                    {"building_types": ["kiosk"], "maximum": 1},
                    "on_trigger",
                ),
            ]),
            _track(
                "conservation", 1, "end_of_game",
                when=_at_least("kiosk_count", 5),
            ),
        ])
        resolved.add(0)
    elif component_id == "211":
        effects.extend([
            _track("appeal", _ref("icons.europe")),
            _icon_trigger(component_id, "europe", "self", [
                _effect(
                    "place_free_building",
                    {"building_types": ["standard_enclosure_1"], "maximum": 1},
                    "on_trigger",
                ),
            ]),
            _track(
                "conservation", 1, "end_of_game",
                when={
                    "op": "compare",
                    "args": {
                        "left": {"ref": "actor.occupied_standard_enclosure_size_1_count"},
                        "operator": ">=", "right": 5,
                    },
                },
            ),
        ])
        resolved.update({0, 1})
    elif component_id == "212":
        effects.extend([
            _track("appeal", _ref("icons.australia")),
            _icon_trigger(component_id, "australia", "self", [
                _effect("tuck_hand_cards", {"maximum": 1}, "on_trigger"),
            ]),
        ])
        resolved.add(0)
    elif component_id == "213":
        effects.extend([
            _track("appeal", _ref("icons.asia")),
            _icon_trigger(component_id, "asia", "self", [
                _effect(
                    "place_free_building",
                    {"building_types": ["pavilion"], "maximum": 1},
                    "on_trigger",
                ),
            ]),
        ])
        resolved.add(0)
    elif component_id == "214":
        effects.extend([
            _track("appeal", _ref("icons.africa")),
            _track("appeal", _ref("x_tokens")),
            _icon_trigger(component_id, "africa", "self", [
                _effect(
                    "reposition_action_card",
                    {"target_slot": 1, "optional": True},
                    "on_trigger",
                ),
            ]),
            _track(
                "conservation", 1, "end_of_game",
                when={
                    "op": "compare",
                    "args": {
                        "left": _ref("all_border_buildable_spaces_covered"),
                        "operator": "==", "right": True,
                    },
                },
            ),
        ])
        resolved.add(0)
    elif component_id in {"215", "218"}:
        effects.extend([
            _effect("add_source_card_tokens", {"amount": 2}),
            _modifier(
                f"{component_id}-wildcard", "static", [],
                kind="base_project_wildcard", amount=1,
            ),
            _track(
                "conservation", 1, "end_of_game",
                when=_at_least("supported_project_count", 5),
            ),
        ])
        resolved.update(range(len(source_records)))
    elif component_id == "216":
        effects.append(_effect("gain_association_worker", {"amount": 1}))
        resolved.add(0)
    elif component_id == "217":
        effects.extend([
            _modifier(
                component_id, "static", [],
                kind="engineer_extra_building", amount=1,
            ),
            _track(
                "appeal", 5, "end_of_game",
                when={
                    "op": "compare",
                    "args": {
                        "left": _ref("map_complete"), "operator": "==", "right": True,
                    },
                },
            ),
        ])
        resolved.add(0)
    elif component_id == "219":
        rock = _ref("rock_requirement_total")
        water = _ref("water_requirement_total")
        matched = {"calc": "minimum", "values": [rock, water, 3]}
        effects.extend([
            _effect("gain_money", {
                "amount": _multiply({"calc": "add", "values": [rock, water]}, 2),
            }),
            _track("appeal", _multiply(matched, 2)),
            _modifier(
                component_id, "static", [], kind="diversity_researcher", amount=1,
            ),
        ])
        resolved.add(0)
    elif component_id == "220":
        effects.extend([
            _effect("gain_money", {"amount": 3}),
            _modifier(component_id, "income", [
                _effect("gain_money", {"amount": 3}, "income"),
            ]),
            _track(
                "conservation", 1, "end_of_game",
                when=_at_least("tracks.reputation", 9),
            ),
        ])
        resolved.add(0)
    elif component_id == "221":
        effects.extend([
            _modifier(
                component_id, "static", [], kind="archeologist_bonus", amount=1,
            ),
            _track(
                "conservation", 1, "end_of_game",
                when={
                    "op": "compare",
                    "args": {
                        "left": _ref("all_border_buildable_spaces_covered"),
                        "operator": "==", "right": True,
                    },
                },
            ),
        ])
        resolved.add(0)
    elif component_id == "222":
        science_count = {"calc": "minimum", "values": [_ref("icons.science"), 3]}
        effects.extend([
            _track("conservation", science_count),
            _effect("for_each_opponent", {
                "effects": [_effect("gain_money", {
                    "amount": {"calc": "multiply", "values": [science_count, 2]},
                })],
            }),
        ])
        resolved.add(0)
    elif component_id == "223":
        # The doubled printed icon is represented by facts.icons; there is no
        # separate instruction to dispatch.
        resolved.add(0)
    elif component_id == "224":
        effects.extend([
            _effect("gain_x_token", {"amount": 1}),
            _modifier(component_id, "release_project_supported", [
                _track("conservation", 1, "on_trigger"),
            ]),
            _modifier(
                f"{component_id}-repeat", "static", [],
                kind="repeat_release_projects", amount=1,
            ),
        ])
        resolved.add(0)
    elif component_id == "225":
        effects.extend([
            _effect("gain_x_token", {"amount": 1}),
            _effect("set_flag", {"flag": "interaction_immunity", "value": True}),
            _track(
                "conservation", 1, "end_of_game",
                when=_all_icons(("africa", "americas", "asia", "australia", "europe")),
            ),
        ])
        resolved.update({0, 1})
    elif component_id == "226":
        effects.append(_track(
            "conservation", 1, "end_of_game",
            when=_all_icons(("africa", "americas", "asia", "australia", "europe")),
        ))
        resolved.add(0)
    elif component_id == "227":
        effects.append(_effect("choose_one", {
            "prompt": "Choose the WAZA Special Assignment size class",
            "options": [
                {
                    "id": "small", "label": "Small Animals (size 1–2)",
                    "effects": [
                        _effect("set_flag", {"flag": "waza_small_only", "value": True}),
                        _effect("reveal_first_animal_size", {"size_class": "small"}),
                        _modifier(component_id, "small_animal_played", [
                            _track("appeal", 2, "on_trigger"),
                        ]),
                    ],
                },
                {
                    "id": "large", "label": "Large Animals (size 4–5)",
                    "effects": [
                        _effect("set_flag", {"flag": "waza_large_only", "value": True}),
                        _effect("reveal_first_animal_size", {"size_class": "large"}),
                        _modifier(component_id, "large_animal_played", [
                            _track("appeal", 4, "on_trigger"),
                        ]),
                    ],
                },
            ],
        }))
        resolved.add(0)
    elif component_id == "228":
        effects.extend([
            _effect("gain_money", {"amount": _multiply(_ref("small_animal_count"), 2)}),
            _modifier(
                component_id, "static", [], kind="waza_small_animal_program", amount=1,
            ),
        ])
        resolved.add(0)
    elif component_id == "229":
        effects.extend([
            _track("appeal", _ref("small_animal_count")),
            _modifier(
                component_id, "static", [],
                kind="animal_cost_discount", amount=3, animal_size="small",
            ),
        ])
        resolved.add(0)
    elif component_id == "230":
        effects.extend([
            _track("appeal", _multiply(_ref("large_animal_count"), 2)),
            _modifier(
                component_id, "static", [],
                kind="animal_cost_discount", amount=4, animal_size="large",
            ),
        ])
        resolved.add(0)
    elif component_id in {"231", "232", "233", "234", "235"}:
        icon = {
            "231": "primate", "232": "reptile", "233": "bird",
            "234": "predator", "235": "herbivore",
        }[component_id]
        effects.extend([
            _track("appeal", _ref(f"icons.{icon}")),
            *_tiered_income(component_id, icon),
        ])
        resolved.add(0)
    elif component_id in {"236", "237", "238", "239", "240"}:
        icon = {
            "236": "primate", "237": "reptile", "238": "bird",
            "239": "predator", "240": "herbivore",
        }[component_id]
        effects.append(_icon_trigger(component_id, icon, "any", [
            _effect("gain_money", {"amount": 3}, "on_trigger"),
        ]))
        resolved.add(0)
    elif component_id in {"241", "242"}:
        terrain = "water" if component_id == "241" else "rock"
        immediate_appeal: Any = _ref(f"icons.{terrain}")
        if terrain == "rock":
            immediate_appeal = _multiply({
                "calc": "floor_divide", "values": [immediate_appeal, 2],
            }, 3)
        effects.extend([
            _track("appeal", immediate_appeal),
            _modifier(component_id, "building_placed", [
                _effect("gain_money", {
                    "amount": {"ref": f"binding.adjacent_{terrain}_cells"},
                }, "on_trigger"),
            ]),
            _track(
                "conservation", 1, "end_of_game",
                when={
                    "op": "compare",
                    "args": {
                        "left": _ref(f"{terrain}_spaces_connected"),
                        "operator": "==", "right": True,
                    },
                },
            ),
        ])
        resolved.update({0, 1})
    elif component_id in {"243", "244", "245", "246", "247"}:
        icon = {
            "243": "herbivore", "244": "bird", "245": "water",
            "246": "rock", "247": "primate",
        }[component_id]
        effects.extend([
            _icon_trigger(component_id, icon, "self", [
                _track("appeal", 2, "on_trigger"),
            ]),
            _track(
                "conservation", 1, "end_of_game",
                when=_at_least(f"icons.{icon}", 6),
            ),
        ])
        resolved.add(0)
    elif component_id == "248":
        effects.append(_icon_trigger(component_id, "primate", "self", [
            _effect("gain_x_token", {"amount": 1}, "on_trigger"),
        ]))
        resolved.add(0)
    elif component_id == "249":
        effects.append(_icon_trigger(component_id, "bird", "self", [
            _effect("draw_keep_cards", {"draw": 2, "keep": 1}, "on_trigger"),
        ]))
        resolved.add(0)
    elif component_id == "250":
        effects.append(_icon_trigger(component_id, "reptile", "self", [
            _effect("sell_hand_cards", {"maximum": 2}, "on_trigger"),
        ]))
        resolved.add(0)
    elif component_id == "251":
        effects.extend([
            _icon_trigger(component_id, "bear", "any", [
                _track("appeal", 2, "on_trigger"),
            ]),
            _effect(
                "gain_tiered_icon_reward",
                {
                    "icon": "bear", "scope": "actor", "reward": "conservation",
                    "thresholds": [3, 6], "rewards": [1, 2],
                },
                "end_of_game",
            ),
        ])
        resolved.add(0)
    elif component_id == "252":
        effects.append(_icon_trigger(component_id, "predator", "self", [
            _effect(
                "reveal_keep_animal",
                {"draw": {"ref": "actor.icons.predator"}, "keep": 1},
                "on_trigger",
            ),
        ]))
        resolved.add(0)
    elif component_id == "253":
        effects.extend([
            _effect("add_source_card_tokens", {"amount": 3}),
            _modifier(component_id, "icon_entered:self:herbivore", [
                _effect("open_bonus_sponsor_play", {}, "on_trigger"),
            ]),
        ])
        resolved.update({0, 1})
    elif component_id == "254":
        effects.append(_effect("take_map_reward_card", {}))
        resolved.add(0)
    elif component_id in {"255", "256"}:
        # The fixed two-space placement is enforced by the Sponsors action;
        # corrected_direct_rewards supplies the printed four Appeal.
        resolved.add(0)
    elif component_id == "257":
        effects.extend([
            _modifier(component_id, "income", [
                _effect("gain_money", {
                    "amount": _multiply(_ref("side_entrance_income_building_count"), 2),
                }, "income"),
            ]),
            _track(
                "appeal", 5, "end_of_game",
                when={
                    "op": "compare",
                    "args": {
                        "left": _ref("map_complete"), "operator": "==", "right": True,
                    },
                },
            ),
        ])
        resolved.update({0, 1, 2})
    elif component_id in {"258", "259"}:
        terrain = "water" if component_id == "258" else "rock"
        effects.extend([
            _track("appeal", _ref(f"connected_{terrain}_space_count")),
            _track(
                "conservation",
                {
                    "calc": "floor_divide",
                    "values": [_ref(f"unconnected_{terrain}_space_count"), 2],
                },
                "end_of_game",
            ),
        ])
        resolved.add(0)
    elif component_id == "260":
        effects.extend([
            _track("appeal", _ref("connected_uncovered_border_space_count")),
            _track(
                "conservation", _ref("empty_buildable_group_of_six_count"),
                "end_of_game",
            ),
        ])
        resolved.add(0)
    elif component_id == "261":
        effects.append(_track(
            "conservation", 1, "end_of_game",
            when=_at_least("distinct_animal_category_count", 5),
        ))
        resolved.add(0)
    elif component_id == "262":
        effects.extend([
            _effect("gain_money", {
                "amount": _multiply(_ref("distinct_continent_animal_category_count"), 2),
            }),
            _modifier(component_id, "distinct_icon_entered", [
                _effect("gain_resources", {
                    "money": 2, "appeal": 1,
                }, "on_trigger"),
            ]),
        ])
        resolved.update({0, 1})
    elif component_id == "263":
        effects.extend([
            _modifier(
                component_id, "static", [],
                kind="large_animal_ignore_prerequisite", amount=1,
            ),
            _effect(
                "place_free_building",
                {"building_types": ["standard_enclosure_5"], "maximum": 1},
            ),
        ])
        resolved.update({0, 1})
    elif component_id == "264":
        effects.extend([
            _track("appeal", _ref("connected_placement_bonus_space_count")),
            _track(
                "conservation",
                {
                    "calc": "floor_divide",
                    "values": [_ref("unconnected_placement_bonus_space_count"), 2],
                },
                "end_of_game",
            ),
        ])
        resolved.add(0)

    unresolved = [index for index in range(len(source_records)) if index not in resolved]
    return effects, unresolved
