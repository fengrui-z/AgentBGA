"""Game-agnostic metadata profiles for the universal harness.

Each game plugin provides a GameProfile that tells the harness how to
interpret game-specific state/actions in a unified semantic framework.
The harness uses the profile to structure observations, group actions,
detect phases, and compress history — without knowing any game rules.

This abstraction is what makes the harness "long-horizon adversarial
decision-making" (LHAD) compatible: Euro board games are clean LHAD
instances, and the profile is the bridge between game-specific rules
and game-agnostic cognitive scaffolding.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GameProfile:
    """Declarative metadata: how the harness should interpret a game.

    The harness never reads game rules — it reads this profile to know
    which observation fields are "self state" vs "market", which actions
    are "build" vs "block", and when the game transitions to endgame.
    """

    # ── Identity ──
    game_id: str
    game_name: str

    # ── Phase detection ──
    total_expected_turns: int
    endgame_score_threshold: int

    # ── Semantic categories ──
    resource_categories: dict[str, str]  # game resource → universal type
    engine_component_name: str            # what "engine" means in this game
    scoring_dimensions: list[str]         # what you score

    # ── Action meta-types ──
    # Maps game-specific action.type → universal meta-type
    # Universal types: acquire | build | score | block | setup | convert
    action_meta_types: dict[str, str]

    # ── Observation schema ──
    # Maps observation keys → universal semantic category
    # Universal categories: self_state | shared_resources | market |
    #   opponents | scoring_opportunities | spatial | hidden_self | meta
    observation_schema: dict[str, str]

    # ── Turn structure ──
    turn_structure: str  # single_action | multi_step | action_phase

    # ── Hidden information ──
    hidden_info_types: list[str]

    # ── Spatial ──
    has_spatial: bool
    spatial_summary_method: str  # none | network | grid | track

    # ── Special abilities ──
    has_card_abilities: bool
    ability_summary_depth: str  # none | keyword | full

    # ── Strategy hints (injected into prompts) ──
    early_strategy: str
    mid_strategy: str
    late_strategy: str

    # ── Sub-capability emphasis (★1-3) ──
    # Which LHAD sub-capabilities this game tests most
    capability_weights: dict[str, int] = field(default_factory=dict)


# ── Universal action meta-types ──
META_ACQUIRE = "acquire"   # gain resources
META_BUILD = "build"       # invest in engine/capability
META_SCORE = "score"       # direct scoring
META_BLOCK = "block"       # deny/block opponent
META_SETUP = "setup"       # prepare future actions
META_CONVERT = "convert"   # transform resources


# ── Sub-capability keys (match the LHAD taxonomy) ──
CAP_ENGINE = "engine_investment"
CAP_RESOURCE = "resource_allocation"
CAP_OPPONENT = "opponent_adaptation"
CAP_PHASE = "phase_transition"
CAP_PLANNING = "long_range_planning"
CAP_PERCEPTION = "active_perception"
CAP_ENDGAME = "endgame_calculation"
CAP_COMBO = "combo_recognition"


# ── Splendor profile ──
SPLENDOR_PROFILE = GameProfile(
    game_id="splendor",
    game_name="Splendor",
    total_expected_turns=50,
    endgame_score_threshold=12,
    resource_categories={"gems": "currency", "gold": "wildcard"},
    engine_component_name="development cards (bonuses discount future purchases)",
    scoring_dimensions=["prestige", "nobles"],
    action_meta_types={
        "take_tokens": META_ACQUIRE,
        "buy_visible": META_BUILD,
        "buy_reserved": META_BUILD,
        "reserve_visible": META_BLOCK,
        "reserve_deck": META_BLOCK,
        "choose_noble": META_SCORE,
        "pass": META_SETUP,
    },
    observation_schema={
        "bank": "shared_resources",
        "market": "market",
        "players": "self_state",
        "available_nobles": "scoring_opportunities",
        "reserved": "hidden_self",
        "rankings": "meta",
        "deck_counts": "meta",
    },
    turn_structure="single_action",
    hidden_info_types=["reserved_cards"],
    has_spatial=False,
    spatial_summary_method="none",
    has_card_abilities=False,
    ability_summary_depth="none",
    early_strategy=(
        "Buy tier-1 cards to build bonuses early. Focus on 2 colors that "
        "align with available nobles. Take 3 different-color tokens when "
        "you can't buy yet."
    ),
    mid_strategy=(
        "Chain purchases using bonuses for discounts. Monitor opponent "
        "noble progress — reserve cards they need. Start buying tier-2 "
        "for higher points."
    ),
    late_strategy=(
        "Race to 15. Prioritize high-point purchases and noble claims. "
        "Every turn counts — avoid taking tokens if a purchase is available."
    ),
    capability_weights={
        CAP_ENGINE: 3,
        CAP_RESOURCE: 2,
        CAP_OPPONENT: 2,
        CAP_PHASE: 2,
        CAP_PLANNING: 1,
        CAP_PERCEPTION: 1,
        CAP_ENDGAME: 3,
        CAP_COMBO: 1,
    },
)


# ── Azul profile ──
AZUL_PROFILE = GameProfile(
    game_id="azul",
    game_name="Azul",
    total_expected_turns=90,
    endgame_score_threshold=60,
    resource_categories={"tiles": "shared_draft", "floor": "penalty"},
    engine_component_name="pattern lines feeding permanent wall placements",
    scoring_dimensions=["wall adjacency", "completed rows", "completed columns", "completed colors"],
    action_meta_types={"draft_tiles": META_BUILD},
    observation_schema={
        "factories": "shared_resources",
        "center": "shared_resources",
        "players": "self_state",
        "wall_pattern": "spatial",
        "bag_count": "meta",
        "lid_count": "meta",
        "rankings": "meta",
    },
    turn_structure="single_action",
    hidden_info_types=[],
    has_spatial=True,
    spatial_summary_method="grid",
    has_card_abilities=False,
    ability_summary_depth="none",
    early_strategy=(
        "Fill short pattern lines efficiently while watching which colors opponents need. "
        "Avoid taking unnecessary floor penalties just to complete a weak placement."
    ),
    mid_strategy=(
        "Build intersecting horizontal and vertical groups for adjacency points. Track the "
        "remaining supply and use factory remainders to shape the center offer."
    ),
    late_strategy=(
        "Control when a horizontal row completes and calculate endgame bonuses. Prefer moves "
        "that preserve the score lead after floor penalties and row-count tiebreaking."
    ),
    capability_weights={
        CAP_ENGINE: 1,
        CAP_RESOURCE: 3,
        CAP_OPPONENT: 3,
        CAP_PHASE: 2,
        CAP_PLANNING: 2,
        CAP_PERCEPTION: 2,
        CAP_ENDGAME: 3,
        CAP_COMBO: 2,
    },
)


# ── Ark Nova profile ──
ARK_NOVA_PROFILE = GameProfile(
    game_id="ark_nova",
    game_name="Ark Nova",
    total_expected_turns=200,
    endgame_score_threshold=150,
    resource_categories={
        "money": "currency",
        "x_tokens": "special",
        "action_strength": "tempo",
    },
    engine_component_name="played animal cards (abilities and discounts)",
    scoring_dimensions=["appeal", "conservation"],
    action_meta_types={
        "play_cards": META_BUILD,
        "action_upgrade": META_BUILD,
        "take_money": META_ACQUIRE,
        "advance_break": META_SCORE,
        "association_task": META_BUILD,
        "donate": META_SCORE,
        "animal_released": META_CONVERT,
        "cards_drawn": META_ACQUIRE,
        "break_discard": META_SETUP,
    },
    observation_schema={
        "card_display": "market",
        "players": "self_state",
        "association_board": "shared_resources",
        "break_track": "scoring_opportunities",
        "base_conservation_projects": "scoring_opportunities",
        "hand": "hidden_self",
        "final_scoring_cards": "hidden_self",
        "map": "spatial",
        "deck_count": "meta",
        "discard_count": "meta",
    },
    turn_structure="action_phase",
    hidden_info_types=["hand_cards", "final_objectives"],
    has_spatial=True,
    spatial_summary_method="grid",
    has_card_abilities=True,
    ability_summary_depth="full",
    early_strategy=(
        "Upgrade action card strengths for tempo. Buy cheap animals to "
        "build your zoo. Claim partner zoos and universities early for "
        "discounts. Don't neglect the association board."
    ),
    mid_strategy=(
        "Execute your engine: chain card abilities for efficiency. "
        "Monitor the break track — time your Break resolution. Start "
        "working toward conservation projects. Keep appeal and "
        "consensation balanced."
    ),
    late_strategy=(
        "Maximize appeal + conservation. Complete final objectives. "
        "Time your last Break for maximum scoring. Don't get caught "
        "with unspent money or unplayed cards."
    ),
    capability_weights={
        CAP_ENGINE: 3,
        CAP_RESOURCE: 3,
        CAP_OPPONENT: 2,
        CAP_PHASE: 3,
        CAP_PLANNING: 3,
        CAP_PERCEPTION: 2,
        CAP_ENDGAME: 1,
        CAP_COMBO: 3,
    },
)


# ── Brass Birmingham profile ──
BRASS_PROFILE = GameProfile(
    game_id="brass_birmingham",
    game_name="Brass: Birmingham",
    total_expected_turns=100,
    endgame_score_threshold=80,
    resource_categories={
        "money": "currency",
        "coal": "resource",
        "iron": "resource",
        "beer": "resource",
    },
    engine_component_name="built industries (passive resource generation and links)",
    scoring_dimensions=["VP", "income track position"],
    action_meta_types={
        "build_industry": META_BUILD,
        "build_link": META_BUILD,
        "sell": META_CONVERT,
        "develop": META_SETUP,
        "scout": META_ACQUIRE,
        "take_loan": META_ACQUIRE,
        "finish_sell": META_CONVERT,
    },
    observation_schema={
        "board": "spatial",
        "markets": "shared_resources",
        "players": "self_state",
        "industries": "shared_resources",
        "links": "spatial",
        "hand": "hidden_self",
    },
    turn_structure="multi_step",
    hidden_info_types=["hand_cards", "wild_cards"],
    has_spatial=True,
    spatial_summary_method="network",
    has_card_abilities=False,
    ability_summary_depth="none",
    early_strategy=(
        "Build coal and iron industries in the canal era. Establish "
        "your network early. Take loans if needed for tempo — debt "
        "is a tool, not a liability. Scout for location cards."
    ),
    mid_strategy=(
        "Sell goods for income and VP. Build links to connect your "
        "industries. Monitor the coal/iron markets — empty markets "
        "mean opportunity. Transition to rail era planning."
    ),
    late_strategy=(
        "Maximize VP per action in the rail era. Build high-level "
        "industries. Use beer to sell remaining goods. Every link "
        "and industry placement counts. Income track compounds."
    ),
    capability_weights={
        CAP_ENGINE: 2,
        CAP_RESOURCE: 3,
        CAP_OPPONENT: 3,
        CAP_PHASE: 3,
        CAP_PLANNING: 2,
        CAP_PERCEPTION: 2,
        CAP_ENDGAME: 2,
        CAP_COMBO: 1,
    },
)


# ── 7 Wonders profile ──
SEVEN_WONDERS_PROFILE = GameProfile(
    game_id="seven_wonders",
    game_name="7 Wonders",
    total_expected_turns=18,
    endgame_score_threshold=45,
    resource_categories={
        "common_resources": "production",
        "rare_resources": "production",
        "coins": "currency",
        "military": "competition",
    },
    engine_component_name="city tableau and constructed Wonder stages",
    scoring_dimensions=[
        "wonder", "treasure", "military", "civil", "commercial", "science", "guilds",
    ],
    action_meta_types={
        "build_card": META_BUILD,
        "build_wonder": META_BUILD,
        "sell_card": META_ACQUIRE,
        "build_discard": META_BUILD,
        "skip_discard": META_SETUP,
    },
    observation_schema={
        "players": "opponents",
        "hand": "hidden_self",
        "discard_count": "meta",
        "rankings": "meta",
        "pass_direction": "meta",
    },
    turn_structure="multi_step",
    hidden_info_types=["draft_hands", "sealed_choices", "discarded_cards"],
    has_spatial=False,
    spatial_summary_method="none",
    has_card_abilities=True,
    ability_summary_depth="full",
    early_strategy=(
        "Establish flexible production and watch both neighbors' resources before committing "
        "to expensive Wonder stages or a narrow science plan."
    ),
    mid_strategy=(
        "Exploit chains and trade discounts while tracking the passing direction. Balance "
        "engine growth against military breakpoints and cards your next neighbor needs."
    ),
    late_strategy=(
        "Calculate direct points, guild exposure, science sets, military outcomes, and coin "
        "tiebreaks. Deny high-value cards when selling or burying them is efficient."
    ),
    capability_weights={
        CAP_ENGINE: 3,
        CAP_RESOURCE: 3,
        CAP_OPPONENT: 3,
        CAP_PHASE: 3,
        CAP_PLANNING: 3,
        CAP_PERCEPTION: 2,
        CAP_ENDGAME: 3,
        CAP_COMBO: 3,
    },
)


# ── The Castles of Burgundy profile ──

CASTLES_OF_BURGUNDY_PROFILE = GameProfile(
    game_id="castles_of_burgundy",
    game_name="The Castles of Burgundy",
    total_expected_turns=100,
    endgame_score_threshold=180,
    resource_categories={
        "silver": "currency", "workers": "die_adjustment", "goods": "sets",
        "hex_storage": "spatial_inventory",
    },
    engine_component_name="placed duchy tiles and monastery abilities",
    scoring_dimensions=[
        "completed_areas", "color_bonuses", "livestock", "sold_goods",
        "watchtowers", "monasteries", "leftover_resources",
    ],
    action_meta_types={
        "take_tile": META_ACQUIRE, "place_tile": META_BUILD,
        "sell_goods": META_SCORE, "take_workers": META_ACQUIRE,
        "buy_tile": META_ACQUIRE, "choose_tile": META_ACQUIRE,
        "choose_goods": META_ACQUIRE, "sell_goods_effect": META_SCORE,
        "place_tile_effect": META_BUILD, "skip_effect": META_SETUP,
        "end_turn": META_SETUP,
    },
    observation_schema={
        "players": "self_state", "depots": "market", "black_depot": "market",
        "color_bonus_claims": "scoring_opportunities", "round_dice": "shared_resources",
        "remaining_dice": "self_state", "turn_order": "meta",
    },
    turn_structure="multi_step",
    hidden_info_types=[],
    has_spatial=True,
    spatial_summary_method="grid",
    has_card_abilities=True,
    ability_summary_depth="keyword",
    early_strategy=(
        "Use early-phase area bonuses aggressively, keep hex storage flexible, and value "
        "ships and workers that make later dice reliable."
    ),
    mid_strategy=(
        "Chain building effects, protect access to scarce colors, and balance region "
        "completion with color-majority bonuses."
    ),
    late_strategy=(
        "Finish high-value areas, convert goods and spare dice into points, and account "
        "for monastery and leftover-resource scoring."
    ),
    capability_weights={
        CAP_ENGINE: 3, CAP_RESOURCE: 3, CAP_OPPONENT: 2, CAP_PHASE: 3,
        CAP_PLANNING: 3, CAP_PERCEPTION: 2, CAP_ENDGAME: 3, CAP_COMBO: 3,
    },
)


# ── Registry ──

HARMONIES_PROFILE = GameProfile(
    game_id="harmonies", game_name="Harmonies", total_expected_turns=300,
    endgame_score_threshold=100,
    resource_categories={"pending_tokens": "landscape", "token_groups": "shared_draft"},
    engine_component_name="landscapes and overlapping animal habitats",
    scoring_dimensions=["trees", "mountains", "fields", "buildings", "water", "animals", "spirits"],
    action_meta_types={"choose_spirit": META_SETUP, "take_tokens": META_ACQUIRE,
                       "place_token": META_BUILD, "take_animal": META_ACQUIRE,
                       "place_animal": META_SCORE, "end_turn": META_SETUP},
    observation_schema={"players": "self_state", "market": "market", "token_groups": "shared_resources",
                        "pending_tokens": "self_state", "rules": "meta", "rankings": "meta"},
    turn_structure="multi_step", hidden_info_types=["spirit_choices", "bag_order", "deck_order"],
    has_spatial=True, spatial_summary_method="grid", has_card_abilities=True, ability_summary_depth="full",
    early_strategy="Choose compatible habitats. Build trees and connected mountains; preserve room for water and fields.",
    mid_strategy="Settle animals between token placements before changing support heights. Reuse support cells and complete cards to free slots.",
    late_strategy="Calculate landscape and habitat points. Two empty spaces trigger the final equal-turn round. Explicitly end your turn after optional settlements.",
    capability_weights={CAP_RESOURCE: 3, CAP_PLANNING: 3, CAP_COMBO: 3, CAP_ENDGAME: 3, CAP_PERCEPTION: 3},
)


WINGSPAN_PROFILE = GameProfile(
    game_id="wingspan", game_name="Wingspan", total_expected_turns=700,
    endgame_score_threshold=90, resource_categories={"food": "food", "eggs": "eggs"},
    engine_component_name="three habitat rows and chained bird powers",
    scoring_dimensions=["birds", "eggs", "cached_food", "tucked_cards", "round_goals", "bonus_cards"],
    action_meta_types={"play_bird": META_BUILD, "gain_food": META_ACQUIRE, "lay_eggs": META_SCORE,
                       "draw_cards": META_ACQUIRE, "activate_power": META_CONVERT,
                       "take_food": META_ACQUIRE, "draw_card": META_ACQUIRE, "tuck_card": META_SCORE,
                       "keep_birds": META_SETUP, "choose_bonus": META_SETUP},
    observation_schema={"players": "self_state", "tray": "market", "feeder": "shared_resources",
                        "pending": "self_state", "goals": "scoring_opportunities", "rules": "meta"},
    turn_structure="multi_step", hidden_info_types=["hand", "bonuses", "deck_order", "rng"],
    has_spatial=True, spatial_summary_method="grid", has_card_abilities=True, ability_summary_depth="full",
    early_strategy="Keep affordable birds and matching food. Build forest and wetland engines early.",
    mid_strategy="Resolve optional brown powers right to left. Weigh round goals against engine growth. Pink effects may require decisions during opponents' turns.",
    late_strategy="Only 26 full actions per player. Compare bird, egg, tuck, cache and bonus points. Preserve eggs needed for bird placement.",
    capability_weights={CAP_RESOURCE: 3, CAP_PLANNING: 3, CAP_COMBO: 3, CAP_ENDGAME: 3},
)

CARCASSONNE_PROFILE = GameProfile(
    game_id="carcassonne", game_name="Carcassonne", total_expected_turns=142,
    endgame_score_threshold=80, resource_categories={"meeples_available": "followers"},
    engine_component_name="connected cities, roads, monasteries, and fields",
    scoring_dimensions=["city", "road", "monastery", "field"],
    action_meta_types={"place_tile": META_BUILD, "place_meeple": META_SCORE, "skip_meeple": META_SETUP},
    observation_schema={"board": "spatial", "features": "scoring_opportunities",
                        "current_tile": "shared_resources", "players": "self_state",
                        "meeples": "spatial", "deck_count": "meta", "rules": "meta"},
    turn_structure="multi_step", hidden_info_types=["deck_order"], has_spatial=True,
    spatial_summary_method="grid", has_card_abilities=False, ability_summary_depth="none",
    early_strategy="Complete small features to recycle followers. Keep several followers available; farmers remain committed until game end.",
    mid_strategy="Use feature connectivity and majority counts to merge into valuable features. Each new tile must match every neighboring edge.",
    late_strategy="Count distinct completed cities per field. Unfinished cities score half; followers placed on the last tile still score. Ties share full points.",
    capability_weights={CAP_RESOURCE: 3, CAP_OPPONENT: 3, CAP_PLANNING: 3, CAP_ENDGAME: 3, CAP_PERCEPTION: 3},
)

_PROFILES: dict[str, GameProfile] = {
    "splendor": SPLENDOR_PROFILE,
    "azul": AZUL_PROFILE,
    "ark_nova": ARK_NOVA_PROFILE,
    "brass_birmingham": BRASS_PROFILE,
    "castles_of_burgundy": CASTLES_OF_BURGUNDY_PROFILE,
    "seven_wonders": SEVEN_WONDERS_PROFILE,
    "harmonies": HARMONIES_PROFILE,
    "wingspan": WINGSPAN_PROFILE,
    "carcassonne": CARCASSONNE_PROFILE,
}


def get_profile(game_id: str) -> GameProfile:
    """Return the GameProfile for a registered game."""
    try:
        return _PROFILES[game_id]
    except KeyError:
        raise ValueError(f"no GameProfile registered for: {game_id}")


def all_profiles() -> dict[str, GameProfile]:
    return dict(_PROFILES)


# ── Phase detection ──

def detect_phase(turn: int, score: int, profile: GameProfile) -> str:
    """Game-agnostic phase detection based on progress relative to profile thresholds."""
    turn_progress = turn / profile.total_expected_turns if profile.total_expected_turns else 0
    score_progress = score / profile.endgame_score_threshold if profile.endgame_score_threshold else 0
    if turn_progress < 0.3 and score_progress < 0.4:
        return "early"
    if turn_progress < 0.7 and score_progress < 0.7:
        return "mid"
    return "late"


# ── Action grouping ──

def group_actions(legal_actions: list[dict], profile: GameProfile) -> dict[str, list[dict]]:
    """Group legal actions by universal meta-type."""
    groups: dict[str, list[dict]] = {}
    for item in legal_actions:
        action = item.get("action", item)
        action_type = action.get("type", "unknown")
        meta = profile.action_meta_types.get(action_type, "other")
        groups.setdefault(meta, []).append(item)
    return groups


# ── Observation categorization ──

def categorize_observation(observation: dict, profile: GameProfile) -> dict[str, dict]:
    """Split raw observation into universal semantic categories."""
    categories: dict[str, dict] = {}
    for key, value in observation.items():
        category = profile.observation_schema.get(key, "other")
        categories.setdefault(category, {})[key] = value
    return categories
