"""Stable, UI-safe export for an Ark Nova semantic content pack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .audit import audit_content_pack
from .content import ContentPack, load_content_pack
from .presentation import present_entry
from .semantics import SemanticEngine


CATALOG_SCHEMA_VERSION = "agentbga.ark_nova.catalog.v1"


def build_content_catalog(pack: ContentPack, *, locale: str = "zh-CN") -> dict[str, Any]:
    """Build the one JSON projection shared by the API and browser UI."""
    audit = audit_content_pack(pack, SemanticEngine())
    entries: list[dict[str, Any]] = []
    for collection, collection_entries in pack.collections.items():
        for entry in collection_entries:
            entries.append({"collection": collection, **present_entry(entry, locale=locale)})
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "pack": {
            "id": pack.manifest.pack_id,
            "rules_version": pack.manifest.rules_version,
            "content_version": pack.manifest.content_version,
            "status": pack.manifest.status,
            "content_sha256": pack.content_sha256,
            "distribution_mode": pack.manifest.distribution_mode,
        },
        "coverage": {
            "total": audit.entry_count,
            "collections": dict(audit.collection_counts),
            "review": dict(audit.review_counts),
            "roster_indexed": audit.roster_entry_count,
            "semantic_entries": audit.semantic_entry_count,
            "scenario_covered_entries": audit.scenario_covered_entry_count,
            "unentered": audit.unentered_entry_count,
        },
        "vocabulary": {
            "predicates": list(audit.predicate_operations),
            "effects": list(audit.effect_operations),
        },
        "disclaimer": (
            "Project-authored mechanics data only. Short component names and identifiers are "
            "catalog references; publisher artwork and verbatim card prose are excluded. "
            "Only released entries are suitable for rules-accurate play."
        ),
        "entries": entries,
    }


def write_content_catalog(
    pack: ContentPack, destination: str | Path, *, locale: str = "zh-CN",
) -> Path:
    """Write a deterministic UTF-8 catalog export and return its resolved path."""
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            build_content_catalog(pack, locale=locale),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export an Ark Nova content pack for the Web UI")
    parser.add_argument("pack", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--locale", default="zh-CN")
    arguments = parser.parse_args(argv)
    pack = load_content_pack(arguments.pack)
    write_content_catalog(pack, arguments.destination, locale=arguments.locale)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
