import json
from pathlib import Path
import tempfile
import unittest

from agentbga.ark_nova_official import (
    COLLECTION_KINDS,
    ContentValidationError,
    SemanticEngine,
    audit_content_pack,
    load_content_pack,
)
from agentbga.ark_nova_official.catalog import build_content_catalog
from agentbga.ark_nova_official.content import OFFICIAL_BASE_COUNTS


class ArkNovaOfficialContentTests(unittest.TestCase):
    def _write_pack(self, root: Path) -> dict[str, list[dict]]:
        source_id = "physical-base-en"
        collections: dict[str, list[dict]] = {}
        files = {}
        for collection, kind in COLLECTION_KINDS.items():
            filename = f"{collection}.json"
            files[collection] = filename
            collections[collection] = [
                {
                    "schema_version": "agentbga.ark_nova.card.v1",
                    "id": f"ark-nova:{kind}-{index + 1:03d}",
                    "official_ref": {
                        "component_id": f"{kind}-{index + 1:03d}",
                        "source_ids": [source_id],
                    },
                    "kind": kind,
                    "display": {
                        "title": f"Semantic {kind} {index + 1}",
                        "summary": "Project-authored mechanics summary.",
                    },
                    "facts": ({
                        "ordinal": index + 1,
                        "levels": [{
                            "id": "level-1",
                            "requirements": [],
                            "conservation": 1,
                            "reputation": 0,
                        }],
                    } if kind in {"zoo_conservation_project", "base_conservation_project"}
                        else {"ordinal": index + 1}),
                    "requirements": [],
                    "effects": [],
                    "references": [],
                    "review": {"status": "schema_valid", "scenario_tests": []},
                }
                for index in range(OFFICIAL_BASE_COUNTS[collection])
            ]
            (root / filename).write_text(json.dumps(collections[collection]), encoding="utf-8")

        manifest = {
            "schema_version": "agentbga.ark_nova.content_manifest.v1",
            "pack_id": "ark-nova-base-en-semantic-test",
            "game_id": "ark_nova",
            "rules_version": "base-1.2-faq-v2-semantic.1",
            "content_version": "test.1",
            "status": "draft",
            "distribution": {
                "mode": "repository_safe",
                "license": "Project-authored test fixture",
                "contains_publisher_art": False,
                "contains_verbatim_card_text": False,
            },
            "sources": [{
                "id": source_id,
                "kind": "physical_component",
                "title": "Test source reference",
                "revision": "base-en",
                "verified_on": "2026-08-24",
            }],
            "expected_counts": dict(OFFICIAL_BASE_COUNTS),
            "files": files,
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return collections

    def test_loads_complete_mechanics_only_pack_and_computes_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_pack(root)
            pack = load_content_pack(root)

            self.assertEqual("ark-nova-base-en-semantic-test", pack.manifest.pack_id)
            self.assertEqual(128, len(pack.collections["animals"]))
            self.assertEqual(64, len(pack.content_sha256))
            self.assertEqual(
                "animal",
                pack.entry("ark-nova:animal-001").kind,
            )

    def test_rejects_executable_fields_in_semantic_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collections = self._write_pack(root)
            collections["animals"][0]["facts"] = {"script": "do_not_run()"}
            (root / "animals.json").write_text(
                json.dumps(collections["animals"]), encoding="utf-8",
            )

            with self.assertRaisesRegex(ContentValidationError, "executable content is forbidden"):
                load_content_pack(root)

    def test_rejects_path_escape_and_unresolved_content_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collections = self._write_pack(root)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            manifest["files"]["animals"] = "../animals.json"
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ContentValidationError, "path escapes"):
                load_content_pack(root)

            manifest["files"]["animals"] = "animals.json"
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            collections["animals"][0]["references"] = ["ark-nova:missing-card"]
            (root / "animals.json").write_text(
                json.dumps(collections["animals"]), encoding="utf-8",
            )
            with self.assertRaisesRegex(ContentValidationError, "unresolved content references"):
                load_content_pack(root)

    def test_released_mode_requires_released_entries_and_scenario_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_pack(root)
            with self.assertRaisesRegex(ContentValidationError, "released content pack is required"):
                load_content_pack(root, require_released=True)

    def test_unentered_slot_may_defer_component_id_and_project_levels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collections = self._write_pack(root)
            entry = collections["base_conservation_projects"][0]
            entry["official_ref"]["component_id"] = None
            entry["facts"] = {"slot": 1}
            entry["review"]["status"] = "unentered"
            (root / "base_conservation_projects.json").write_text(
                json.dumps(collections["base_conservation_projects"]), encoding="utf-8",
            )

            pack = load_content_pack(root)
            self.assertIsNone(pack.collections["base_conservation_projects"][0].official_component_id)
            report = audit_content_pack(pack, SemanticEngine())
            self.assertEqual(1, report.unentered_entry_count)

            entry["review"]["status"] = "schema_valid"
            (root / "base_conservation_projects.json").write_text(
                json.dumps(collections["base_conservation_projects"]), encoding="utf-8",
            )
            with self.assertRaisesRegex(ContentValidationError, "may be null only"):
                load_content_pack(root)

    def test_repository_draft_pack_has_exact_roster_and_ui_projection(self):
        root = Path(__file__).resolve().parents[1]
        pack = load_content_pack(root / "content-packs" / "ark-nova" / "base-en-draft")
        catalog = build_content_catalog(pack)

        self.assertEqual(254, catalog["coverage"]["total"])
        self.assertEqual(235, catalog["coverage"]["roster_indexed"])
        self.assertEqual(234, catalog["coverage"]["semantic_entries"])
        self.assertEqual("401", catalog["entries"][0]["official_component_id"])
        self.assertEqual("Cheetah", catalog["entries"][0]["title"])
        self.assertEqual(
            pack.content_sha256,
            catalog["pack"]["content_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
