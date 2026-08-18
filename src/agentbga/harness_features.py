"""Feature flags for harness cognitive interventions.

Each flag controls a specific cognitive scaffolding mechanism that
targets one LHAD sub-capability. Flags are passed to DirectGameAgent
via the ``features`` dict and can be toggled per-experiment.

    from agentbga.harness_features import HarnessFeatures
    features = HarnessFeatures(state_diff=True, action_grouping=True)
    agent = DirectGameAgent(config, match_id, seat, features=features)

Default: all flags off (baseline minimal harness). Turn on individually
to measure each intervention's marginal effect.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HarnessFeatures:
    """Toggles for harness cognitive interventions.

    Each intervention targets a specific LHAD sub-capability and can
    be independently enabled for ablation studies.
    """

    # A: State diff — show what changed since last turn instead of full board
    state_diff: bool = False

    # B: Action grouping — group legal actions by meta-type with priority
    action_grouping: bool = False

    # C: Game journal — structured per-turn log instead of raw conversation
    game_journal: bool = False

    # D: Plan tracking — maintain short/medium/long-term plan across turns
    plan_tracking: bool = False

    # E: Opponent modeling — track and summarize opponent behavior
    opponent_modeling: bool = False

    # F: Phase-aware CoT — inject phase-specific reasoning scaffolding
    phase_cot: bool = False

    # G: Counterfactual prompt — ask agent to consider alternatives
    counterfactual: bool = False

    # H: Pre-commitment — force agent to state plan before acting
    pre_commitment: bool = False

    # I: Attention guidance — highlight actionable items in observation
    attention_guidance: bool = False

    # J: Semantic compaction — game-aware context compression
    semantic_compaction: bool = False

    # K: Post-game reflection — generate structured analysis after match
    post_game_reflection: bool = False

    # L: Cross-game playbook — carry lessons across matches
    cross_game_playbook: bool = False

    @classmethod
    def all_on(cls) -> "HarnessFeatures":
        """Enable every intervention (for the 'full harness' condition)."""
        return cls(**{k: True for k in cls.__dataclass_fields__})

    @classmethod
    def baseline(cls) -> "HarnessFeatures":
        """Disable all interventions (pure minimal harness baseline)."""
        return cls()

    def diff(self, other: "HarnessFeatures") -> list[str]:
        """Return list of feature names that differ between two configs."""
        diffs = []
        for field_name in self.__dataclass_fields__:
            if getattr(self, field_name) != getattr(other, field_name):
                diffs.append(field_name)
        return diffs

    def enabled_count(self) -> int:
        """Number of enabled interventions."""
        return sum(1 for v in self.__dict__.values() if v)


# ── Convenience presets ──

BASELINE = HarnessFeatures.baseline()
FULL = HarnessFeatures.all_on()

# Targeted presets (each tests one sub-capability cluster)
MEMORY_FOCUSED = HarnessFeatures(
    game_journal=True, semantic_compaction=True, plan_tracking=True,
)
ATTENTION_FOCUSED = HarnessFeatures(
    state_diff=True, action_grouping=True, attention_guidance=True,
)
REASONING_FOCUSED = HarnessFeatures(
    phase_cot=True, counterfactual=True, pre_commitment=True,
)
META_LEARNING = HarnessFeatures(
    post_game_reflection=True, cross_game_playbook=True,
)

# ── Feature → sub-capability mapping (for paper tables) ──

FEATURE_TO_CAPABILITY: dict[str, str] = {
    "state_diff": "active_perception",
    "action_grouping": "resource_allocation",
    "game_journal": "long_range_planning",
    "plan_tracking": "long_range_planning",
    "opponent_modeling": "opponent_adaptation",
    "phase_cot": "phase_transition",
    "counterfactual": "resource_allocation",
    "pre_commitment": "long_range_planning",
    "attention_guidance": "active_perception",
    "semantic_compaction": "long_range_planning",
    "post_game_reflection": "engine_investment",
    "cross_game_playbook": "engine_investment",
}


def feature_table() -> str:
    """Human-readable table of all features and their target capabilities."""
    lines = [
        f"{'Feature':>25}  {'Target capability':>25}  {'Default'}",
        "-" * 65,
    ]
    for name, cap in FEATURE_TO_CAPABILITY.items():
        lines.append(f"{name:>25}  {cap:>25}  off")
    return "\n".join(lines)
