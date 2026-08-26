"""Semantic vocabulary audit connecting reviewed content to the rules engine."""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from typing import Mapping

from .content import ContentPack
from .semantics import SemanticEngine


@dataclass(frozen=True)
class SemanticAuditReport:
    pack_id: str
    content_sha256: str
    entry_count: int
    predicate_operations: tuple[str, ...]
    effect_operations: tuple[str, ...]
    scenario_test_count: int
    collection_counts: tuple[tuple[str, int], ...]
    review_counts: tuple[tuple[str, int], ...]
    roster_entry_count: int
    semantic_entry_count: int
    scenario_covered_entry_count: int
    unentered_entry_count: int


def audit_content_pack(pack: ContentPack, engine: SemanticEngine) -> SemanticAuditReport:
    """Reject any content operation that the selected engine cannot execute."""
    predicate_operations: set[str] = set()
    effect_operations: set[str] = set()
    scenario_tests: set[str] = set()
    collection_counts: Counter[str] = Counter()
    review_counts: Counter[str] = Counter()
    roster_entry_count = 0
    semantic_entry_count = 0
    scenario_covered_entry_count = 0
    entry_count = 0
    for collection, entries in pack.collections.items():
        for entry in entries:
            entry_count += 1
            collection_counts[collection] += 1
            review_counts[entry.review_status] += 1
            roster_entry_count += entry.official_component_id is not None
            scenario_covered_entry_count += bool(entry.scenario_tests)
            scenario_tests.update(entry.scenario_tests)
            has_semantics = bool(entry.requirements or entry.effects)
            for requirement in entry.requirements:
                predicate_operations |= engine.validate_predicate_vocabulary(requirement)
            if entry.kind in {"base_conservation_project", "zoo_conservation_project"}:
                levels = entry.facts.get("levels")
                if entry.review_status == "unentered" and levels is None:
                    continue
                if not isinstance(levels, list) or not levels:
                    raise ValueError(f"conservation project has no semantic levels: {entry.id}")
                has_semantics = True
                for level in levels:
                    if not isinstance(level, Mapping) or not isinstance(level.get("requirements"), list):
                        raise ValueError(f"conservation project has malformed semantic levels: {entry.id}")
                    for requirement in level["requirements"]:
                        predicate_operations |= engine.validate_predicate_vocabulary(requirement)
            if entry.kind == "final_scoring":
                scoring = entry.facts.get("scoring")
                if entry.review_status == "unentered" and scoring is None:
                    continue
                if scoring is None and entry.facts.get("semantic_compile_status") != "compiled":
                    continue
                if not isinstance(scoring, Mapping) or not isinstance(scoring.get("mode"), str):
                    raise ValueError(f"Final Scoring card has no compiled scoring rule: {entry.id}")
                has_semantics = True
            for effect in entry.effects:
                predicates, effects = engine.validate_effect_vocabulary(effect)
                predicate_operations |= predicates
                effect_operations |= effects
            solo_effects = entry.facts.get("solo_effects")
            solo_replaces = entry.facts.get("solo_replaces_ops")
            if solo_effects is not None or solo_replaces is not None:
                if (
                    entry.kind != "animal"
                    or not isinstance(solo_effects, list) or not solo_effects
                    or not isinstance(solo_replaces, list) or not solo_replaces
                    or any(not isinstance(value, str) for value in solo_replaces)
                    or not any(effect.get("op") in set(solo_replaces) for effect in entry.effects)
                ):
                    raise ValueError(f"Animal card has malformed solo replacement: {entry.id}")
                for effect in solo_effects:
                    predicates, effects = engine.validate_effect_vocabulary(effect)
                    predicate_operations |= predicates
                    effect_operations |= effects
            semantic_entry_count += has_semantics
    return SemanticAuditReport(
        pack_id=pack.manifest.pack_id,
        content_sha256=pack.content_sha256,
        entry_count=entry_count,
        predicate_operations=tuple(sorted(predicate_operations)),
        effect_operations=tuple(sorted(effect_operations)),
        scenario_test_count=len(scenario_tests),
        collection_counts=tuple(sorted(collection_counts.items())),
        review_counts=tuple(sorted(review_counts.items())),
        roster_entry_count=roster_entry_count,
        semantic_entry_count=semantic_entry_count,
        scenario_covered_entry_count=scenario_covered_entry_count,
        unentered_entry_count=review_counts["unentered"],
    )
