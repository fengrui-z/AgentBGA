"""Reproducible dual-review evidence and promotion for the Map 0 base pack.

This deliberately records reviewer *processes*, not invented human identities.
The first independent pass cross-checks the structured JSON against the XLSX
and both human-readable DOCX exports.  The second pass executes one registered
runtime scenario per released face.  The resulting ledger contains hashes and
outcomes only; it does not copy publisher prose or artwork into the repository.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from ..ark_nova_map import map_zero
from .content import ContentEntry, load_content_pack
from .reference_import import (
    COLLECTION_OUTPUTS,
    build_semantic_collections,
    load_reference_dataset,
)
from .release_scenarios import release_scenario_id, run_release_scenario


SOURCE_REVIEWER = "source-crosswalk-pass-v1"
SEMANTIC_REVIEWER = "runtime-scenario-pass-v1"
LEDGER_SCHEMA_VERSION = "agentbga.ark_nova.release_review.v1"
RELEASE_RULES_VERSION = "base-1.2-faq-v2-map0.1"
RELEASE_CONTENT_VERSION = "map0-release.1"
RELEASE_PACK_ID = "ark-nova-base-map0-released"

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_CELL_COLUMN = re.compile(r"^([A-Z]+)")

_SOURCE_COLLECTIONS = {
    "animals": ("Animals", 2),
    "sponsors": ("Sponsors", 3),
    "base_conservation_projects": ("Base Projects", 4),
    "conservation_projects": ("Projects 113-132", 5),
    "final_scoring_cards": ("Final Scoring", 6),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _column_index(reference: str) -> int:
    match = _CELL_COLUMN.match(reference)
    if match is None:
        raise ValueError(f"invalid spreadsheet cell reference: {reference}")
    value = 0
    for letter in match.group(1):
        value = value * 26 + ord(letter) - ord("A") + 1
    return value - 1


def _xlsx_tables(path: Path) -> dict[str, list[list[str]]]:
    """Read tabular values from an XLSX package using only OPC XML."""
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target_by_id = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship")
        }
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t"))
                for item in shared_root.findall(f"{{{_MAIN_NS}}}si")
            ]
        result: dict[str, list[list[str]]] = {}
        sheets = workbook.find(f"{{{_MAIN_NS}}}sheets")
        if sheets is None:
            raise ValueError("workbook has no sheets")
        for sheet in sheets:
            name = sheet.attrib["name"]
            relationship_id = sheet.attrib[f"{{{_REL_NS}}}id"]
            target = target_by_id[relationship_id].lstrip("/")
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            root = ET.fromstring(archive.read(target))
            rows: list[list[str]] = []
            for row in root.findall(f".//{{{_MAIN_NS}}}sheetData/{{{_MAIN_NS}}}row"):
                values: dict[int, str] = {}
                for cell in row.findall(f"{{{_MAIN_NS}}}c"):
                    index = _column_index(cell.attrib["r"])
                    value_node = cell.find(f"{{{_MAIN_NS}}}v")
                    value = "" if value_node is None else value_node.text or ""
                    if cell.attrib.get("t") == "s" and value:
                        value = shared[int(value)]
                    values[index] = value
                width = max(values, default=-1) + 1
                rows.append([values.get(index, "") for index in range(width)])
            result[name] = rows
        return result


def _docx_tables(path: Path) -> list[list[list[str]]]:
    """Read Word table cells without importing formatting or embedded media."""
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    return [[
        [
            "".join(node.text or "" for node in cell.iter(f"{{{_WORD_NS}}}t")).strip()
            for cell in row.findall(f"{{{_WORD_NS}}}tc")
        ]
        for row in table.findall(f"{{{_WORD_NS}}}tr")
    ] for table in root.iter(f"{{{_WORD_NS}}}tbl")]


def _row_index(rows: list[list[str]], id_header: str, name_header: str) -> dict[str, str]:
    header = rows[0]
    id_column = header.index(id_header)
    name_column = header.index(name_header)
    result = {}
    for row in rows[1:]:
        if id_column >= len(row) or not row[id_column]:
            continue
        component = row[id_column].strip()
        name = row[name_column].strip() if name_column < len(row) else ""
        if component in result:
            raise AssertionError(f"duplicate component in review table: {component}")
        result[component] = name
    return result


def _word_row_index(rows: list[list[str]]) -> dict[str, str]:
    if not rows:
        return {}
    return _row_index(rows, rows[0][0], rows[0][1])


def verify_source_crosswalk(reference_root: Path, pack_root: Path) -> dict[str, Any]:
    """Cross-check all 235 card faces across JSON, XLSX, EN DOCX, and CN DOCX."""
    files = {
        "json": reference_root / "ark_nova_base_cards.json",
        "xlsx": reference_root / "Ark_Nova_Base_Cards.xlsx",
        "docx_en": reference_root / "Ark_Nova_Base_255_Cards_EN.docx",
        "docx_cn": reference_root / "Ark_Nova_Base_255_Cards_CN.docx",
    }
    missing = [str(path) for path in files.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"release review inputs are missing: {missing}")
    source = load_reference_dataset(files["json"])
    generated = build_semantic_collections(source)
    pack = load_content_pack(pack_root)

    # The authoring pack must still be the deterministic compiler output. Review
    # metadata is intentionally excluded because promotion writes it afterward.
    for source_collection, output in COLLECTION_OUTPUTS.items():
        actual = list(pack.collections[
            "zoo_conservation_projects"
            if source_collection == "conservation_projects" else source_collection
            if source_collection != "final_scoring_cards" else "final_scoring"
        ])
        expected = generated[source_collection]
        if len(actual) != len(expected):
            raise AssertionError(f"compiled collection count mismatch: {source_collection}")
        raw_actual = json.loads((pack_root / output).read_text(encoding="utf-8"))
        for compiled, authored in zip(expected, raw_actual):
            left = {key: value for key, value in compiled.items() if key != "review"}
            right = {key: value for key, value in authored.items() if key != "review"}
            if left != right:
                raise AssertionError(f"compiled/source mismatch: {authored.get('id')}")

    workbook = _xlsx_tables(files["xlsx"])
    english_tables = _docx_tables(files["docx_en"])
    chinese_tables = _docx_tables(files["docx_cn"])
    entries = []
    for source_collection, (sheet, word_table_index) in _SOURCE_COLLECTIONS.items():
        rows = source[source_collection]
        expected_names = {str(row["id"]): str(row["name_en"]) for row in rows}
        xlsx_names = _row_index(workbook[sheet], "ID", "English Name")
        en_names = _word_row_index(english_tables[word_table_index])
        cn_names = _word_row_index(chinese_tables[word_table_index])
        for label, values in (("xlsx", xlsx_names), ("docx_en", en_names)):
            if values != expected_names:
                difference = sorted(set(values) ^ set(expected_names))[:10]
                mismatched = [
                    component for component in expected_names.keys() & values.keys()
                    if expected_names[component] != values[component]
                ][:10]
                raise AssertionError(
                    f"{source_collection} {label} crosswalk mismatch: ids={difference}, names={mismatched}"
                )
        if set(cn_names) != set(expected_names) or any(
            not cn_names[component].endswith(name)
            for component, name in expected_names.items()
        ):
            difference = sorted(set(cn_names) ^ set(expected_names))[:10]
            mismatched = [
                component for component in expected_names.keys() & cn_names.keys()
                if not cn_names[component].endswith(expected_names[component])
            ][:10]
            raise AssertionError(
                f"{source_collection} docx_cn crosswalk mismatch: "
                f"ids={difference}, names={mismatched}"
            )
        entries.extend({
            "component_id": component,
            "source_collection": source_collection,
            "xlsx_sheet": sheet,
            "docx_table": word_table_index,
        } for component in expected_names)

    if len(entries) != 235:
        raise AssertionError(f"source crosswalk must cover 235 card faces, found {len(entries)}")
    return {
        "reviewer": SOURCE_REVIEWER,
        "card_faces": len(entries),
        "artifacts": [
            {"role": role, "file": path.name, "sha256": _sha256(path)}
            for role, path in files.items()
        ],
        "entries": entries,
    }


def _map_zero_entry() -> dict[str, Any]:
    map_state = map_zero()
    terrain = {
        terrain: sum(cell["terrain"] == terrain for cell in map_state["cells"])
        for terrain in ("buildable", "water", "rock")
    }
    return {
        "schema_version": "agentbga.ark_nova.card.v1",
        "id": "ark-nova:map-0",
        "official_ref": {
            "component_id": "0",
            "source_ids": ["capstone-rulebook-base-en", "user-structured-base-255"],
        },
        "kind": "map",
        "display": {
            "title": "Zoo Map 0",
            "summary": "Beginner Map 0 axial footprint; no free setup buildings.",
        },
        "facts": {
            "map_id": "0",
            "geometry_version": map_state["schema_version"],
            "coordinate_system": map_state["coordinate_system"],
            "cell_count": len(map_state["cells"]),
            "terrain_counts": terrain,
            "placement_bonus_count": len(map_state["placement_bonus_slots"]),
            "build_ii_cells": [
                [cell["q"], cell["r"]] for cell in map_state["cells"]
                if cell.get("requires_build_upgrade")
            ],
            "setup_buildings": [],
            "completion_reward": deepcopy(map_state["completion_reward"]),
        },
        "requirements": [],
        "effects": [],
        "references": [],
        "review": {
            "status": "released",
            "scenario_tests": ["ark-nova-map0-release:map:0"],
            "reviewer": SOURCE_REVIEWER,
            "second_reviewer": SEMANTIC_REVIEWER,
        },
    }


def _content_digest(manifest: Mapping[str, Any], collections: Mapping[str, Any]) -> str:
    digest_manifest = {key: value for key, value in manifest.items() if key != "content_sha256"}
    canonical = json.dumps(
        {"manifest": digest_manifest, "collections": collections},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_release_review_ledger(pack: Any) -> dict[str, Any]:
    """Validate the committed evidence ledger against a loaded released pack."""
    path = pack.root / "release-review-ledger.json"
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read Ark Nova release-review ledger: {error}") from error
    if ledger.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise ValueError("Ark Nova release-review ledger schema is unsupported")
    if (
        ledger.get("pack_id") != pack.manifest.pack_id
        or ledger.get("rules_version") != pack.manifest.rules_version
    ):
        raise ValueError("Ark Nova release-review ledger does not match the content pack")
    records = ledger.get("entries")
    if not isinstance(records, list):
        raise ValueError("Ark Nova release-review ledger entries are malformed")
    by_id = {
        entry.id: entry
        for collection in pack.collections.values()
        for entry in collection
    }
    if {record.get("entry_id") for record in records} != set(by_id):
        raise ValueError("Ark Nova release-review ledger coverage is incomplete")
    if len(records) != len(by_id):
        raise ValueError("Ark Nova release-review ledger contains duplicate entries")
    for record in records:
        entry = by_id[record["entry_id"]]
        if (
            record.get("result") != "pass"
            or record.get("source_reviewer") != SOURCE_REVIEWER
            or record.get("semantic_reviewer") != SEMANTIC_REVIEWER
            or record.get("scenario_id") not in entry.scenario_tests
            or entry.reviewer != SOURCE_REVIEWER
            or entry.second_reviewer != SEMANTIC_REVIEWER
        ):
            raise ValueError(f"Ark Nova release evidence mismatch: {entry.id}")
    semantic = ledger.get("semantic_review", {})
    if (
        semantic.get("scenario_count") != len(by_id)
        or semantic.get("card_face_count") != 235
        or semantic.get("bonus_tile_count") != 9
        or semantic.get("map_count") != 1
    ):
        raise ValueError("Ark Nova release-review summary is inconsistent")
    return ledger


def promote_map_zero_pack(reference_root: Path, pack_root: Path) -> dict[str, Any]:
    """Run both review passes and mechanically promote a verified Map 0 pack."""
    source_review = verify_source_crosswalk(reference_root, pack_root)
    draft = load_content_pack(pack_root)
    scenario_results = []
    for collection, entries in draft.collections.items():
        if collection == "maps":
            continue
        scenario_results.extend(run_release_scenario(draft, entry) for entry in entries)

    map_document = _map_zero_entry()
    map_entry = ContentEntry(
        id=map_document["id"], kind="map", official_component_id="0",
        source_ids=tuple(map_document["official_ref"]["source_ids"]),
        display_title=map_document["display"]["title"],
        display_summary=map_document["display"]["summary"],
        facts=map_document["facts"], requirements=(), effects=(), references=(),
        review_status="released",
        scenario_tests=tuple(map_document["review"]["scenario_tests"]),
        reviewer=SOURCE_REVIEWER, second_reviewer=SEMANTIC_REVIEWER,
    )
    scenario_results.append(run_release_scenario(draft, map_entry))
    scenario_by_entry = {result["entry_id"]: result for result in scenario_results}

    manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
    collections: dict[str, Any] = {}
    for collection, filename in manifest["files"].items():
        if collection == "maps":
            values = [map_document]
        else:
            values = json.loads((pack_root / filename).read_text(encoding="utf-8"))
            for value in values:
                scenario = scenario_by_entry[value["id"]]
                value["review"] = {
                    "status": "released",
                    "scenario_tests": [scenario["scenario_id"]],
                    "reviewer": SOURCE_REVIEWER,
                    "second_reviewer": SEMANTIC_REVIEWER,
                }
        collections[collection] = values

    manifest.update({
        "pack_id": RELEASE_PACK_ID,
        "rules_version": RELEASE_RULES_VERSION,
        "content_version": RELEASE_CONTENT_VERSION,
        "status": "released",
    })
    sources = {source["id"]: source for source in manifest["sources"]}
    sources["capstone-rulebook-base-en"]["verified_on"] = "2026-08-28"
    sources["capstone-rulebook-base-en"]["revision"] = (
        "publisher download checked 2026-08-28"
    )
    sources["capstone-glossary-base-en"] = {
        "id": "capstone-glossary-base-en",
        "kind": "rulebook",
        "title": "Ark Nova base-game English glossary",
        "revision": "publisher download checked 2026-08-28",
        "url": "https://cdn.shopify.com/s/files/1/0947/3907/1278/files/Ark-Nova-Glossary.pdf",
        "verified_on": "2026-08-28",
    }
    sources["capstone-faq-v2-base-en"] = {
        "id": "capstone-faq-v2-base-en",
        "kind": "faq_errata",
        "title": "Ark Nova FAQ v2",
        "revision": "publisher download checked 2026-08-28",
        "url": "https://cdn.shopify.com/s/files/1/0947/3907/1278/files/Ark-Nova-FAQ-v2.pdf",
        "verified_on": "2026-08-28",
    }
    manifest["sources"] = list(sources.values())
    manifest["expected_counts"]["maps"] = 1
    manifest.pop("content_sha256", None)
    manifest["content_sha256"] = _content_digest(manifest, collections)

    ledger = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "scope": "Ark Nova base game, Map 0 mode",
        "reviewed_on": "2026-08-28",
        "pack_id": RELEASE_PACK_ID,
        "rules_version": RELEASE_RULES_VERSION,
        "source_review": source_review,
        "semantic_review": {
            "reviewer": SEMANTIC_REVIEWER,
            "scenario_count": len(scenario_results),
            "card_face_count": 235,
            "bonus_tile_count": 9,
            "map_count": 1,
            "results_sha256": hashlib.sha256(json.dumps(
                scenario_results, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")).hexdigest(),
        },
        "entries": [{
            "entry_id": result["entry_id"],
            "scenario_id": result["scenario_id"],
            "source_reviewer": SOURCE_REVIEWER,
            "semantic_reviewer": SEMANTIC_REVIEWER,
            "result": "pass",
        } for result in scenario_results],
    }

    for collection, filename in manifest["files"].items():
        _write_json(pack_root / filename, collections[collection])
    _write_json(pack_root / "release-review-ledger.json", ledger)
    _write_json(pack_root / "manifest.json", manifest)
    return {
        "content_sha256": manifest["content_sha256"],
        "source_card_faces": source_review["card_faces"],
        "scenario_count": len(scenario_results),
        "ledger": str(pack_root / "release-review-ledger.json"),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review and promote the Ark Nova Map 0 pack")
    parser.add_argument("reference_root", type=Path)
    parser.add_argument("pack_root", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    print(json.dumps(
        promote_map_zero_pack(args.reference_root.resolve(), args.pack_root.resolve()),
        indent=2, sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
