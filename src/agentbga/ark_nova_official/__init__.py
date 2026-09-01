"""Released high-fidelity Ark Nova base-game Map 0 rules package.

The legacy ``agentbga.ark_nova`` module remains registered under its immutable
controlled-core rules version for replaying matches created with that engine.
"""

from .content import (
    COLLECTION_KINDS,
    ContentEntry,
    ContentManifest,
    ContentPack,
    ContentValidationError,
    load_content_pack,
)
from .audit import SemanticAuditReport, audit_content_pack
from .actions import (
    ACTION_TOKEN_TYPES,
    action_execution_spec,
    complete_action_execution,
    current_action_execution,
    defer_after_finishing,
    legal_action_starts,
    start_action,
    take_x_token_action,
)
from .cards import entry_is_eligible, play_entry_semantics
from .cards_action import (
    apply_cards_execution_action,
    legal_cards_execution_actions,
    reputation_display_limit,
)
from .build_action import apply_build_execution_action, legal_build_execution_actions
from .animals_action import apply_animals_execution_action, legal_animals_execution_actions
from .association_action import (
    apply_association_execution_action,
    legal_association_execution_actions,
)
from .sponsors_action import apply_sponsors_execution_action, legal_sponsors_execution_actions
from .action_domains import apply_official_action, content_entry_indexes, legal_official_actions
from .abilities import compile_animal_ability, compile_animal_effects
from .presentation import (
    explain_effect, explain_predicate, present_entry, resolve_mechanics,
    resolved_effect_timing,
)
from .projects import (
    add_project_to_state,
    legal_new_project_levels,
    legal_new_project_support_options,
    legal_project_levels,
    legal_project_support_options,
    legal_project_token_choices,
    install_base_projects,
    support_project,
)
from .milestones import (
    OFFICIAL_CONSERVATION_MILESTONE_IDS,
    install_official_conservation_milestones,
    official_conservation_milestones,
    queue_endgame_final_scoring_discard,
)
from .rounds import queue_break
from .scoring import check_endgame_trigger, counters_crossed, score_game
from .final_scoring_effects import (
    compile_final_scoring_facts,
    compiled_final_scoring_tier_count,
    score_final_card,
)
from .interaction_audit import InteractionAuditReport, audit_interactions
from .plugin import ArkNovaOfficialPlugin
from .setup import (
    card_instance,
    choose_initial_hand,
    legal_initial_hand_actions,
    load_official_base_pack,
    setup_official_game,
)
from .semantics import (
    CONTENT_EFFECT_OPS,
    EFFECT_OPS,
    PREDICATE_OPS,
    SYSTEM_EFFECT_OPS,
    EvaluationContext,
    SemanticEngine,
    SemanticRuleError,
    simultaneous_effects,
    settle_turn_venom,
)
from .state import (
    SEMANTIC_RULES_VERSION,
    STATE_SCHEMA_VERSION,
    new_semantic_state,
    validate_semantic_state,
)

__all__ = [
    "COLLECTION_KINDS",
    "ACTION_TOKEN_TYPES",
    "ContentEntry",
    "ContentManifest",
    "ContentPack",
    "ContentValidationError",
    "InteractionAuditReport",
    "ArkNovaOfficialPlugin",
    "load_content_pack",
    "EFFECT_OPS",
    "CONTENT_EFFECT_OPS",
    "PREDICATE_OPS",
    "EvaluationContext",
    "SemanticAuditReport",
    "SemanticEngine",
    "SemanticRuleError",
    "simultaneous_effects",
    "settle_turn_venom",
    "SEMANTIC_RULES_VERSION",
    "STATE_SCHEMA_VERSION",
    "SYSTEM_EFFECT_OPS",
    "OFFICIAL_CONSERVATION_MILESTONE_IDS",
    "action_execution_spec",
    "apply_cards_execution_action",
    "apply_build_execution_action",
    "apply_animals_execution_action",
    "apply_association_execution_action",
    "apply_sponsors_execution_action",
    "apply_official_action",
    "audit_content_pack",
    "audit_interactions",
    "add_project_to_state",
    "check_endgame_trigger",
    "counters_crossed",
    "complete_action_execution",
    "compile_animal_ability",
    "compile_animal_effects",
    "compile_final_scoring_facts",
    "compiled_final_scoring_tier_count",
    "current_action_execution",
    "defer_after_finishing",
    "explain_effect",
    "resolve_mechanics",
    "resolved_effect_timing",
    "explain_predicate",
    "entry_is_eligible",
    "new_semantic_state",
    "install_official_conservation_milestones",
    "legal_action_starts",
    "legal_cards_execution_actions",
    "legal_build_execution_actions",
    "legal_animals_execution_actions",
    "legal_association_execution_actions",
    "legal_sponsors_execution_actions",
    "legal_official_actions",
    "content_entry_indexes",
    "legal_project_levels",
    "legal_new_project_levels",
    "legal_new_project_support_options",
    "legal_project_support_options",
    "legal_project_token_choices",
    "install_base_projects",
    "present_entry",
    "play_entry_semantics",
    "queue_break",
    "queue_endgame_final_scoring_discard",
    "reputation_display_limit",
    "score_game",
    "score_final_card",
    "start_action",
    "support_project",
    "take_x_token_action",
    "official_conservation_milestones",
    "validate_semantic_state",
    "card_instance",
    "choose_initial_hand",
    "legal_initial_hand_actions",
    "load_official_base_pack",
    "setup_official_game",
]
