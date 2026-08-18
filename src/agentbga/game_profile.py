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


# ── Registry ──

_PROFILES: dict[str, GameProfile] = {
    "splendor": SPLENDOR_PROFILE,
    "ark_nova": ARK_NOVA_PROFILE,
    "brass_birmingham": BRASS_PROFILE,
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
