"""Import the user-supplied 255-card reference into the semantic authoring pack.

The importer deliberately separates transcription from executable semantics.
Structured printed facts and concise effect records are imported first; the
requirements/effects arrays stay empty until a reviewed compiler maps each
record to the closed operation vocabulary in :mod:`semantics`.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .abilities import (
    compile_animal_ability, compile_animal_effects, solo_animal_replacement,
)
from .sponsor_effects import compile_sponsor_effects
from .project_effects import compile_project_facts, compiled_project_tier_count
from .final_scoring_effects import (
    compile_final_scoring_facts,
    compiled_final_scoring_tier_count,
)
from .sponsor_reference import (
    compile_sponsor_requirement,
    corrected_direct_rewards,
    corrected_printed_icons,
    unresolved_sponsor_requirements,
    unique_building_rules,
)


REFERENCE_COUNTS = {
    "animals": 128,
    "sponsors": 64,
    "base_conservation_projects": 12,
    "conservation_projects": 20,
    "final_scoring_cards": 11,
    "action_cards": 5,
    "ability_keywords": 47,
    "physical_255": 255,
}
CARD_RANGES = {
    "animals": range(401, 529),
    "sponsors": range(201, 265),
    "base_conservation_projects": range(101, 113),
    "conservation_projects": range(113, 133),
    "final_scoring_cards": range(1, 12),
}
COLLECTION_OUTPUTS = {
    "animals": "animals.json",
    "sponsors": "sponsors.json",
    "base_conservation_projects": "base_conservation_projects.json",
    "conservation_projects": "zoo_conservation_projects.json",
    "final_scoring_cards": "final_scoring.json",
}
SOURCE_ID = "user-structured-base-255"
_SLUG = re.compile(r"[^a-z0-9]+")
_COUNTED_REQUIREMENT = re.compile(r"^(.*?)(?:×([0-9]+))?$")

_ABILITY_PARAMETER_GAPS = {
}


class ReferenceImportError(ValueError):
    """A deterministic validation failure in the supplied reference dataset."""


def _fail(location: str, message: str) -> None:
    raise ReferenceImportError(f"{location}: {message}")


def _objects(value: Any, location: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        _fail(location, "must be an array of objects")
    return value


def _stable_id(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(location, "must be a non-empty string")
    return value


def _slug(value: str) -> str:
    result = _SLUG.sub("_", value.strip().lower()).strip("_")
    if not result:
        raise ReferenceImportError(f"cannot normalize identifier: {value!r}")
    return result


def _counted_icons(values: Any, location: str) -> tuple[list[str], dict[str, int]]:
    """Normalize printed icon labels while preserving doubled icons."""
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        _fail(location, "must be an array of strings")
    tags: list[str] = []
    icons: dict[str, int] = {}
    for value in values:
        match = _COUNTED_REQUIREMENT.fullmatch(value.strip())
        if match is None:
            _fail(location, f"unsupported counted icon: {value}")
        icon = _slug(match.group(1).strip())
        count = int(match.group(2) or 1)
        if icon not in tags:
            tags.append(icon)
        icons[icon] = icons.get(icon, 0) + count
    return tags, icons


def load_reference_dataset(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReferenceImportError(f"cannot read reference JSON: {error}") from error
    if not isinstance(data, dict):
        _fail("root", "must be an object")
    expected = {"metadata", *REFERENCE_COUNTS}
    if set(data) != expected:
        missing = expected - data.keys()
        extra = data.keys() - expected
        _fail("root", f"unexpected keys; missing={sorted(missing)}, extra={sorted(extra)}")

    for collection, expected_count in REFERENCE_COUNTS.items():
        rows = _objects(data[collection], collection)
        if len(rows) != expected_count:
            _fail(collection, f"expected {expected_count} rows, found {len(rows)}")
        ids = [_stable_id(row.get("id", row.get("key", row.get("physical_no"))), collection)
               if collection != "physical_255" else row.get("physical_no") for row in rows]
        if len(ids) != len(set(ids)):
            _fail(collection, "contains duplicate primary identifiers")

    for collection, expected_range in CARD_RANGES.items():
        actual = {int(row["id"]) for row in data[collection]}
        expected_ids = set(expected_range)
        if actual != expected_ids:
            _fail(collection, f"card-number coverage mismatch: {sorted(expected_ids ^ actual)}")

    physical = data["physical_255"]
    if [row.get("physical_no") for row in physical] != list(range(1, 256)):
        _fail("physical_255", "physical numbers must be exactly 1 through 255")
    by_unique_id = Counter(str(row.get("unique_id")) for row in physical)
    expected_copies = {
        **{
            (f"{number:03d}" if collection == "final_scoring_cards" else str(number)): 1
            for collection, values in CARD_RANGES.items() for number in values
        },
        **{row["id"]: row["copies"] for row in data["action_cards"]},
    }
    if by_unique_id != Counter(expected_copies):
        missing = Counter(expected_copies) - by_unique_id
        extra = by_unique_id - Counter(expected_copies)
        _fail("physical_255", f"copy expansion mismatch; missing={dict(missing)}, extra={dict(extra)}")
    for row in data["action_cards"]:
        if row.get("copies") != 4:
            _fail(f"action_cards.{row.get('id')}", "base game requires four physical copies")
    return data


def _display_summary(row: Mapping[str, Any], collection: str) -> str:
    if collection == "animals":
        keywords = ", ".join(
            str(ability.get("keyword") or ability.get("key"))
            for ability in row.get("abilities", [])
        ) or "no keyword ability"
        return (
            f"Cost {row.get('cost')}; enclosure {row.get('enclosure_size')}; "
            f"appeal {row.get('appeal')}; abilities: {keywords}."
        )[:280]
    if collection == "sponsors":
        timings = ", ".join(str(effect.get("timing")) for effect in row.get("effects", []))
        return f"Level {row.get('level')} sponsor; timings: {timings or 'none'}."[:280]
    if collection in {"base_conservation_projects", "conservation_projects"}:
        return f"Conservation project with {len(row.get('tiers', []))} structured reward tiers."
    return f"Endgame scoring card with {len(row.get('tiers', []))} structured thresholds."


def _facts(row: Mapping[str, Any], collection: str) -> dict[str, Any]:
    omitted = {"id", "card_type", "name_en", "name_cn", "cn_name_note", "source"}
    facts = {key: deepcopy(value) for key, value in row.items() if key not in omitted}
    facts["reference_import_status"] = "structured_transcription"
    facts["semantic_compile_status"] = "pending"
    if collection == "animals":
        tags, icons = _counted_icons(row.get("tags", []), f"animals.{row.get('id')}.tags")
        facts["tags"] = tags
        facts["icons"] = icons
        facts["continents"] = [_slug(str(value)) for value in row.get("continents", [])]
        facts["animal_categories"] = [
            _slug(str(value)) for value in row.get("animal_categories", [])
        ]
        _, unresolved = compile_animal_effects(row)
        facts["compiled_ability_keys"] = [
            str(ability["key"]) for ability in row.get("abilities", [])
            if str(ability.get("key")) not in unresolved
        ]
        facts["unresolved_ability_keys"] = unresolved
        facts["semantic_compile_status"] = "compiled" if not unresolved else "partial"
        solo = solo_animal_replacement(row.get("id"))
        if solo is not None:
            facts["solo_replaces_ops"] = solo["replaces_ops"]
            facts["solo_effects"] = solo["effects"]
            facts["solo_source"] = "base-card-blue-stripe"
    elif collection == "sponsors":
        tags, icons = _counted_icons(row.get("tags", []), f"sponsors.{row.get('id')}.tags")
        icons = corrected_printed_icons(str(row.get("id", "")), icons)
        for icon in icons:
            if icon not in tags:
                tags.append(icon)
        facts["tags"] = tags
        facts["icons"] = icons
        _, unresolved = compile_sponsor_effects(row)
        facts["compiled_effect_records"] = len(row.get("effects", [])) - len(unresolved)
        facts["unresolved_effect_records"] = unresolved
        facts["direct_rewards"] = corrected_direct_rewards(row)
        facts["unique_building"] = unique_building_rules(str(row.get("id", "")))
        unresolved_requirements = unresolved_sponsor_requirements(row)
        facts["unresolved_requirements"] = unresolved_requirements
        facts["semantic_compile_status"] = (
            "compiled" if not unresolved and not unresolved_requirements else "partial"
        )
    elif collection in {"base_conservation_projects", "conservation_projects"}:
        facts.update(compile_project_facts(row))
    elif collection == "final_scoring_cards":
        facts.update(compile_final_scoring_facts(row))
    return facts


def compile_requirement(value: str, *, animal_context: bool = False) -> dict[str, Any]:
    """Compile the closed set of animal/icon requirements in the reference."""
    match = _COUNTED_REQUIREMENT.fullmatch(value.strip())
    if match is None:
        raise ReferenceImportError(f"unsupported requirement: {value}")
    label = match.group(1).strip()
    count = int(match.group(2) or 1)
    if label in {"Animals II", "Sponsors II"}:
        action = "animals" if label == "Animals II" else "sponsors"
        return {
            "op": "compare",
            "args": {
                "left": {"ref": f"actor.action_cards.{action}.upgraded"},
                "operator": "==",
                "right": True,
            },
        }
    if label == "Partner Zoo":
        if animal_context:
            if count != 1:
                raise ReferenceImportError("animal Partner Zoo requirement must have count 1")
            return {"op": "matching_partner_zoo", "args": {}}
        return {
            "op": "compare",
            "args": {
                "left": {"ref": "actor.partner_zoo_count"},
                "operator": ">=",
                "right": count,
            },
        }
    if label in {
        "Africa", "Americas", "Asia", "Australia", "Europe", "Bear", "Bird",
        "Herbivore", "Predator", "Primate", "Reptile", "Science",
    }:
        return {"op": "has_icon", "args": {"icon": _slug(label), "count": count}}
    raise ReferenceImportError(f"unsupported requirement: {value}")


def _compiled_requirements(row: Mapping[str, Any], collection: str) -> list[dict[str, Any]]:
    raw = row.get("requirements", [])
    if not isinstance(raw, list) or any(not isinstance(value, str) for value in raw):
        _fail(f"{collection}.{row.get('id')}.requirements", "must be an array of strings")
    if collection == "animals":
        return [compile_requirement(value, animal_context=True) for value in raw]
    if collection == "sponsors":
        component_id = str(row.get("id", ""))
        result = []
        for value in raw:
            audited = compile_sponsor_requirement(component_id, value)
            if audited is not None:
                result.append(audited)
            elif value not in {"Appeal threshold", "Reputation threshold"}:
                result.append(compile_requirement(value))
        return result
    return []


def semantic_entry(row: Mapping[str, Any], collection: str) -> dict[str, Any]:
    kinds = {
        "animals": "animal",
        "sponsors": "sponsor",
        "base_conservation_projects": "base_conservation_project",
        "conservation_projects": "zoo_conservation_project",
        "final_scoring_cards": "final_scoring",
    }
    prefixes = {
        "animals": "animal",
        "sponsors": "sponsor",
        "base_conservation_projects": "base-project",
        "conservation_projects": "project",
        "final_scoring_cards": "final",
    }
    status = "transcribed"
    effects: list[dict[str, Any]] = []
    if collection == "animals":
        effects, _ = compile_animal_effects(row)
    elif collection == "sponsors":
        effects, _ = compile_sponsor_effects(row)
    return {
        "schema_version": "agentbga.ark_nova.card.v1",
        "id": f"ark-nova:{prefixes[collection]}-{str(row['id']).lower()}",
        "official_ref": {"component_id": str(row["id"]), "source_ids": [SOURCE_ID]},
        "kind": kinds[collection],
        "display": {
            "title": str(row["name_en"]),
            "summary": _display_summary(row, collection),
        },
        "facts": _facts(row, collection),
        "requirements": _compiled_requirements(row, collection),
        "effects": effects,
        "references": [],
        "review": {"status": status, "scenario_tests": []},
    }


def build_semantic_collections(data: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        collection: [semantic_entry(row, collection) for row in data[collection]]
        for collection in COLLECTION_OUTPUTS
    }


def audit_reference_gaps(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a stable backlog separating missing source parameters from compiler work."""
    missing_parameters = []
    compiler_backlog = []
    for row in data["animals"]:
        for ability in row.get("abilities", []):
            if compile_animal_ability(ability) is not None:
                continue
            key = str(ability.get("key", "unknown"))
            missing = [
                field for field in _ABILITY_PARAMETER_GAPS.get(key, ())
                if ability.get(field) in (None, "", [], {})
            ]
            item = {
                "card_id": str(row["id"]),
                "card_name": str(row["name_en"]),
                "ability_key": key,
            }
            if missing:
                missing_parameters.append({**item, "missing_fields": missing})
            else:
                compiler_backlog.append({**item, "dependency": _ability_dependency(key)})

    sponsor_backlog = []
    sponsor_requirement_backlog = []
    sponsor_compiled_records = 0
    for row in data["sponsors"]:
        _, unresolved = compile_sponsor_effects(row)
        sponsor_compiled_records += len(row.get("effects", [])) - len(unresolved)
        for index in unresolved:
            effect = row.get("effects", [])[index]
            sponsor_backlog.append({
                "card_id": str(row["id"]),
                "card_name": str(row["name_en"]),
                "effect_index": index,
                "timing": str(effect.get("timing", "unknown")),
            })
        for requirement in unresolved_sponsor_requirements(row):
            if requirement in {"Appeal threshold", "Reputation threshold"}:
                sponsor_requirement_backlog.append({
                    "card_id": str(row["id"]),
                    "card_name": str(row["name_en"]),
                    "requirement": requirement,
                    "missing_fields": ["numeric_threshold"],
                })
    sponsor_effects = len(sponsor_backlog)
    project_tiers = sum(
        len(row.get("tiers", []))
        for collection in ("base_conservation_projects", "conservation_projects")
        for row in data[collection]
    )
    compiled_project_tiers = sum(
        compiled_project_tier_count(row)
        for collection in ("base_conservation_projects", "conservation_projects")
        for row in data[collection]
    )
    final_scoring_tiers = sum(
        len(row.get("tiers", [])) for row in data["final_scoring_cards"]
    )
    compiled_final_scoring_tiers = sum(
        compiled_final_scoring_tier_count(row) for row in data["final_scoring_cards"]
    )
    return {
        "schema_version": "agentbga.ark_nova.reference_gaps.v1",
        "summary": {
            "blocking_parameter_records": len(missing_parameters),
            "animal_compiler_records": len(compiler_backlog),
            "uncompiled_sponsor_effect_records": sponsor_effects,
            "uncompiled_sponsor_requirement_records": len(sponsor_requirement_backlog),
            "uncompiled_project_tiers": project_tiers - compiled_project_tiers,
            "uncompiled_final_scoring_tiers": (
                final_scoring_tiers - compiled_final_scoring_tiers
            ),
        },
        "missing_printed_parameters": missing_parameters,
        "animal_compiler_backlog": compiler_backlog,
        "collection_backlog": {
            "sponsors": {
                "cards": len(data["sponsors"]),
                "effect_records": sponsor_effects,
                "compiled_effect_records": sponsor_compiled_records,
                "backlog": sponsor_backlog,
                "requirement_records": len(sponsor_requirement_backlog),
                "requirement_backlog": sponsor_requirement_backlog,
            },
            "conservation_projects": {
                "cards": len(data["base_conservation_projects"]) + len(data["conservation_projects"]),
                "tiers": project_tiers,
                "compiled_tiers": compiled_project_tiers,
                "backlog_tiers": project_tiers - compiled_project_tiers,
            },
            "final_scoring": {
                "cards": len(data["final_scoring_cards"]),
                "tiers": final_scoring_tiers,
                "compiled_tiers": compiled_final_scoring_tiers,
                "backlog_tiers": final_scoring_tiers - compiled_final_scoring_tiers,
            },
            "action_cards": {"unique_faces": len(data["action_cards"])},
        },
    }


def _ability_dependency(key: str) -> str:
    if key in {"flock_animal"}:
        return "enclosure_occupancy"
    if key in {"posturing", "peacocking"}:
        return "map_building_placement"
    if key in {"assertion", "dominance"}:
        return "conservation_project_supply"
    return "semantic_dispatcher"


def require_no_blocking_reference_gaps(report: Mapping[str, Any]) -> None:
    """Fail a release/import gate while printed parameters are still missing."""
    count = report.get("summary", {}).get("blocking_parameter_records")
    if not isinstance(count, int) or isinstance(count, bool):
        _fail("data_gaps", "blocking gap count is malformed")
    if count:
        _fail("data_gaps", f"{count} ability records still lack printed parameters")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def import_reference_pack(source: str | Path, target: str | Path) -> dict[str, Any]:
    data = load_reference_dataset(source)
    root = Path(target)
    if not root.is_dir() or not (root / "manifest.json").is_file():
        _fail("target", "must be an existing Ark Nova authoring pack")
    collections = build_semantic_collections(data)
    for collection, filename in COLLECTION_OUTPUTS.items():
        _write_json(root / filename, collections[collection])

    _write_json(root / "action_cards.reference.json", data["action_cards"])
    _write_json(root / "ability_keywords.reference.json", data["ability_keywords"])
    _write_json(root / "physical_255.reference.json", data["physical_255"])
    gaps = audit_reference_gaps(data)
    _write_json(root / "data_gaps.reference.json", gaps)

    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Importing fresh transcription deliberately demotes a copied release pack:
    # review metadata and the digest are invalid until both release passes run.
    manifest["status"] = "draft"
    manifest["pack_id"] = "ark-nova-base-map0-authoring"
    manifest.pop("content_sha256", None)
    manifest["content_version"] = "m4-reference-import.17"
    manifest["sources"] = [source for source in manifest["sources"] if source["id"] != SOURCE_ID]
    manifest["sources"].append({
        "id": SOURCE_ID,
        "kind": "physical_component",
        "title": "User-supplied structured base-game card reference",
        "revision": str(data["metadata"].get("schema_version", "1.0")),
        "verified_on": "2026-08-25",
    })
    _write_json(manifest_path, manifest)
    compiled_ability_keys = {
        str(ability["key"])
        for animal in data["animals"] for ability in animal.get("abilities", [])
        if compile_animal_ability(ability) is not None
    }
    fully_compiled_animals = sum(
        not compile_animal_effects(animal)[1] for animal in data["animals"]
    )
    return {
        "physical_cards": len(data["physical_255"]),
        "unique_card_faces": sum(len(data[key]) for key in (
            "animals", "sponsors", "base_conservation_projects",
            "conservation_projects", "final_scoring_cards", "action_cards",
        )),
        "authoring_entries_imported": sum(len(value) for value in collections.values()),
        "ability_keywords": len(data["ability_keywords"]),
        "compiled_ability_keywords": len(compiled_ability_keys),
        "fully_compiled_animals": fully_compiled_animals,
        **gaps["summary"],
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import the Ark Nova 255-card reference")
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--require-no-blocking-gaps", action="store_true",
        help="fail after auditing when printed card parameters are still missing",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = import_reference_pack(args.source, args.target)
    if args.require_no_blocking_gaps:
        gaps = json.loads((args.target / "data_gaps.reference.json").read_text(encoding="utf-8"))
        require_no_blocking_reference_gaps(gaps)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
