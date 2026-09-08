"""Validated loader for mechanics-only Ark Nova semantic content packs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping


MANIFEST_SCHEMA_VERSION = "agentbga.ark_nova.content_manifest.v1"
ENTRY_SCHEMA_VERSION = "agentbga.ark_nova.card.v1"
CONTENT_ID = re.compile(r"^ark-nova:[a-z0-9][a-z0-9._-]*$")
PACK_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
OPERATION_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
CUSTOM_ID = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")
SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

COLLECTION_KINDS: dict[str, str] = {
    "animals": "animal",
    "sponsors": "sponsor",
    "zoo_conservation_projects": "zoo_conservation_project",
    "base_conservation_projects": "base_conservation_project",
    "final_scoring": "final_scoring",
    "bonus_tiles": "bonus_tile",
    "maps": "map",
}

OFFICIAL_BASE_COUNTS: dict[str, int] = {
    "animals": 128,
    "sponsors": 64,
    "zoo_conservation_projects": 20,
    "base_conservation_projects": 12,
    "final_scoring": 11,
    "bonus_tiles": 9,
    # This released rules package deliberately supports the base game's
    # beginner Map 0 mode only. Other base maps require separate geometry and
    # player-board ability implementations and are not claimed by this pack.
    "maps": 1,
}

_FORBIDDEN_EXECUTABLE_KEYS = {"code", "eval", "exec", "import", "module", "python", "script"}
_REVIEW_STATES = {
    "unentered", "transcribed", "schema_valid", "rules_reviewed",
    "scenario_tested", "double_checked", "released",
}
_EFFECT_TIMINGS = {
    "on_play", "immediate", "ongoing", "income", "on_trigger", "interaction",
    "end_of_game", "on_support", "on_release", "after_finishing",
}


class ContentValidationError(ValueError):
    """A stable validation error that includes the failing JSON location."""


@dataclass(frozen=True)
class ContentManifest:
    pack_id: str
    rules_version: str
    content_version: str
    status: str
    distribution_mode: str
    sources: tuple[str, ...]
    expected_counts: Mapping[str, int]
    files: Mapping[str, str]
    declared_sha256: str | None


@dataclass(frozen=True)
class ContentEntry:
    id: str
    kind: str
    official_component_id: str | None
    source_ids: tuple[str, ...]
    display_title: str
    display_summary: str
    facts: Mapping[str, Any]
    requirements: tuple[Mapping[str, Any], ...]
    effects: tuple[Mapping[str, Any], ...]
    references: tuple[str, ...]
    review_status: str
    scenario_tests: tuple[str, ...]
    reviewer: str | None
    second_reviewer: str | None


@dataclass(frozen=True)
class ContentPack:
    root: Path
    manifest: ContentManifest
    collections: Mapping[str, tuple[ContentEntry, ...]]
    content_sha256: str

    def entry(self, content_id: str) -> ContentEntry:
        for entries in self.collections.values():
            for item in entries:
                if item.id == content_id:
                    return item
        raise KeyError(content_id)


def _fail(location: str, message: str) -> None:
    raise ContentValidationError(f"{location}: {message}")


def _object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(location, "must be a JSON object")
    return value


def _string(value: Any, location: str, *, maximum: int | None = None) -> str:
    if not isinstance(value, str) or not value:
        _fail(location, "must be a non-empty string")
    if maximum is not None and len(value) > maximum:
        _fail(location, f"must be at most {maximum} characters")
    return value


def _exact_keys(
    value: Mapping[str, Any], location: str, required: set[str], optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing:
        _fail(location, f"missing keys: {', '.join(sorted(missing))}")
    if extra:
        _fail(location, f"unknown keys: {', '.join(sorted(extra))}")


def _read_json(path: Path, location: str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ContentValidationError(f"{location}: duplicate JSON key: {key}")
            value[key] = item
        return value

    def reject_constant(value: str) -> Any:
        raise ContentValidationError(f"{location}: non-finite number is forbidden: {value}")

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except ContentValidationError:
        raise
    except FileNotFoundError as error:
        raise ContentValidationError(f"{location}: file does not exist: {path.name}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContentValidationError(f"{location}: cannot read valid UTF-8 JSON: {error}") from error


def _safe_content_path(root: Path, relative: Any, location: str) -> Path:
    text = _string(relative, location, maximum=256)
    candidate_path = Path(text)
    if candidate_path.is_absolute() or candidate_path.suffix != ".json":
        _fail(location, "must be a relative .json path")
    resolved = (root / candidate_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ContentValidationError(f"{location}: path escapes the content-pack root") from error
    return resolved


def _validate_data_tree(value: Any, location: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        _fail(location, "non-finite numbers are forbidden")
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_data_tree(item, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail(location, "object keys must be strings")
            if key.lower() in _FORBIDDEN_EXECUTABLE_KEYS:
                _fail(f"{location}.{key}", "executable content is forbidden")
            _validate_data_tree(item, f"{location}.{key}")
        return
    _fail(location, f"unsupported value type: {type(value).__name__}")


def _validate_operation(value: Any, location: str, *, effect: bool = False) -> dict[str, Any]:
    operation = _object(value, location)
    required = {"op", "args", "timing"} if effect else {"op", "args"}
    optional = {"when", "custom_id"} if effect else {"when", "custom_id"}
    _exact_keys(operation, location, required, optional)
    op = _string(operation["op"], f"{location}.op", maximum=64)
    if OPERATION_ID.fullmatch(op) is None:
        _fail(f"{location}.op", "must be a lowercase operation identifier")
    args = _object(operation["args"], f"{location}.args")
    _validate_data_tree(args, f"{location}.args")
    if "when" in operation:
        _validate_operation(operation["when"], f"{location}.when")
    if "custom_id" in operation:
        custom_id = _string(operation["custom_id"], f"{location}.custom_id", maximum=128)
        if CUSTOM_ID.fullmatch(custom_id) is None:
            _fail(f"{location}.custom_id", "must be a stable lowercase identifier")
    if effect and operation["timing"] not in _EFFECT_TIMINGS:
        _fail(f"{location}.timing", "is not a supported effect timing")
    return operation


def _validate_project_facts(facts: Mapping[str, Any], location: str) -> None:
    levels = facts.get("levels")
    if not isinstance(levels, list) or not levels:
        _fail(f"{location}.levels", "conservation projects require a non-empty level array")
    seen: set[str] = set()
    for index, raw in enumerate(levels):
        level_location = f"{location}.levels[{index}]"
        level = _object(raw, level_location)
        _exact_keys(level, level_location, {"id", "requirements", "conservation"}, {"reputation"})
        level_id = _string(level["id"], f"{level_location}.id", maximum=64)
        if level_id in seen:
            _fail(f"{location}.levels", "project level IDs must be unique")
        seen.add(level_id)
        requirements = level["requirements"]
        if not isinstance(requirements, list):
            _fail(f"{level_location}.requirements", "must be an array")
        for position, requirement in enumerate(requirements):
            _validate_operation(requirement, f"{level_location}.requirements[{position}]")
        for reward in ("conservation", "reputation"):
            value = level.get(reward, 0)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                _fail(f"{level_location}.{reward}", "must be a non-negative integer")


def _load_entry(raw: Any, collection: str, index: int, source_ids: set[str]) -> ContentEntry:
    location = f"files.{collection}[{index}]"
    item = _object(raw, location)
    _exact_keys(
        item,
        location,
        {
            "schema_version", "id", "official_ref", "kind", "display", "facts",
            "requirements", "effects", "references", "review",
        },
    )
    if item["schema_version"] != ENTRY_SCHEMA_VERSION:
        _fail(f"{location}.schema_version", f"must equal {ENTRY_SCHEMA_VERSION}")
    content_id = _string(item["id"], f"{location}.id", maximum=160)
    if CONTENT_ID.fullmatch(content_id) is None:
        _fail(f"{location}.id", "must be a stable ark-nova content ID")
    expected_kind = COLLECTION_KINDS[collection]
    if item["kind"] != expected_kind:
        _fail(f"{location}.kind", f"must equal {expected_kind}")

    review = _object(item["review"], f"{location}.review")
    _exact_keys(review, f"{location}.review", {"status", "scenario_tests"}, {"reviewer", "second_reviewer"})
    review_status = _string(review["status"], f"{location}.review.status")
    if review_status not in _REVIEW_STATES:
        _fail(f"{location}.review.status", "is not a supported review state")

    official_ref = _object(item["official_ref"], f"{location}.official_ref")
    _exact_keys(official_ref, f"{location}.official_ref", {"component_id", "source_ids"}, {"faq_refs"})
    component_id = official_ref["component_id"]
    if component_id is not None:
        component_id = _string(component_id, f"{location}.official_ref.component_id", maximum=64)
    elif review_status != "unentered":
        _fail(
            f"{location}.official_ref.component_id",
            "may be null only while the entry is unentered",
        )
    raw_source_ids = official_ref["source_ids"]
    if not isinstance(raw_source_ids, list) or not raw_source_ids:
        _fail(f"{location}.official_ref.source_ids", "must be a non-empty array")
    entry_sources = tuple(_string(value, f"{location}.official_ref.source_ids") for value in raw_source_ids)
    if any(SOURCE_ID.fullmatch(value) is None for value in entry_sources):
        _fail(f"{location}.official_ref.source_ids", "must contain stable lowercase source IDs")
    unknown_sources = set(entry_sources) - source_ids
    if unknown_sources:
        _fail(f"{location}.official_ref.source_ids", f"unknown source IDs: {', '.join(sorted(unknown_sources))}")
    raw_faq_refs = official_ref.get("faq_refs", [])
    if not isinstance(raw_faq_refs, list) or any(
        not isinstance(value, str) or not value or len(value) > 128 for value in raw_faq_refs
    ):
        _fail(f"{location}.official_ref.faq_refs", "must be an array of short non-empty strings")
    if len(set(raw_faq_refs)) != len(raw_faq_refs):
        _fail(f"{location}.official_ref.faq_refs", "must not contain duplicates")

    display = _object(item["display"], f"{location}.display")
    _exact_keys(display, f"{location}.display", {"title", "summary"})
    title = _string(display["title"], f"{location}.display.title", maximum=96)
    summary = _string(display["summary"], f"{location}.display.summary", maximum=280)

    facts = _object(item["facts"], f"{location}.facts")
    _validate_data_tree(facts, f"{location}.facts")
    if (
        expected_kind in {"zoo_conservation_project", "base_conservation_project"}
        and review_status != "unentered"
    ):
        _validate_project_facts(facts, f"{location}.facts")
    raw_requirements = item["requirements"]
    raw_effects = item["effects"]
    if not isinstance(raw_requirements, list):
        _fail(f"{location}.requirements", "must be an array")
    if not isinstance(raw_effects, list):
        _fail(f"{location}.effects", "must be an array")
    requirements = tuple(
        _validate_operation(value, f"{location}.requirements[{position}]")
        for position, value in enumerate(raw_requirements)
    )
    effects = tuple(
        _validate_operation(value, f"{location}.effects[{position}]", effect=True)
        for position, value in enumerate(raw_effects)
    )

    raw_references = item["references"]
    if not isinstance(raw_references, list):
        _fail(f"{location}.references", "must be an array")
    references = tuple(_string(value, f"{location}.references") for value in raw_references)
    invalid_refs = [value for value in references if CONTENT_ID.fullmatch(value) is None]
    if invalid_refs:
        _fail(f"{location}.references", f"invalid content IDs: {', '.join(invalid_refs)}")

    raw_tests = review["scenario_tests"]
    if not isinstance(raw_tests, list):
        _fail(f"{location}.review.scenario_tests", "must be an array")
    scenario_tests = tuple(_string(value, f"{location}.review.scenario_tests") for value in raw_tests)
    reviewer = review.get("reviewer")
    second_reviewer = review.get("second_reviewer")
    if reviewer is not None:
        reviewer = _string(reviewer, f"{location}.review.reviewer", maximum=128)
    if second_reviewer is not None:
        second_reviewer = _string(second_reviewer, f"{location}.review.second_reviewer", maximum=128)
    if len(set(entry_sources)) != len(entry_sources) or len(set(references)) != len(references) or len(set(scenario_tests)) != len(scenario_tests):
        _fail(location, "source IDs, references, and scenario tests must not contain duplicates")

    return ContentEntry(
        id=content_id,
        kind=expected_kind,
        official_component_id=component_id,
        source_ids=entry_sources,
        display_title=title,
        display_summary=summary,
        facts=facts,
        requirements=requirements,
        effects=effects,
        references=references,
        review_status=review_status,
        scenario_tests=scenario_tests,
        reviewer=reviewer,
        second_reviewer=second_reviewer,
    )


def _parse_manifest(raw: Any, root: Path) -> tuple[ContentManifest, dict[str, Any]]:
    manifest = _object(raw, "manifest")
    required = {
        "schema_version", "pack_id", "game_id", "rules_version", "content_version",
        "status", "distribution", "sources", "expected_counts", "files",
    }
    _exact_keys(manifest, "manifest", required, {"content_sha256"})
    if manifest["schema_version"] != MANIFEST_SCHEMA_VERSION:
        _fail("manifest.schema_version", f"must equal {MANIFEST_SCHEMA_VERSION}")
    if manifest["game_id"] != "ark_nova":
        _fail("manifest.game_id", "must equal ark_nova")
    pack_id = _string(manifest["pack_id"], "manifest.pack_id", maximum=128)
    if PACK_ID.fullmatch(pack_id) is None:
        _fail("manifest.pack_id", "must be a stable lowercase pack ID")
    rules_version = _string(manifest["rules_version"], "manifest.rules_version", maximum=128)
    content_version = _string(manifest["content_version"], "manifest.content_version", maximum=128)
    status = manifest["status"]
    if status not in {"draft", "review", "released"}:
        _fail("manifest.status", "must be draft, review, or released")

    distribution = _object(manifest["distribution"], "manifest.distribution")
    _exact_keys(
        distribution,
        "manifest.distribution",
        {"mode", "license", "contains_publisher_art", "contains_verbatim_card_text"},
    )
    if distribution["mode"] not in {"repository_safe", "local_only"}:
        _fail("manifest.distribution.mode", "must be repository_safe or local_only")
    _string(distribution["license"], "manifest.distribution.license", maximum=256)
    if distribution["contains_publisher_art"] is not False or distribution["contains_verbatim_card_text"] is not False:
        _fail("manifest.distribution", "semantic packs must not include publisher art or verbatim card text")

    raw_sources = manifest["sources"]
    if not isinstance(raw_sources, list) or not raw_sources:
        _fail("manifest.sources", "must be a non-empty array")
    source_ids: list[str] = []
    for index, value in enumerate(raw_sources):
        source = _object(value, f"manifest.sources[{index}]")
        _exact_keys(source, f"manifest.sources[{index}]", {"id", "kind", "title", "revision", "verified_on"}, {"url"})
        source_id = _string(source["id"], f"manifest.sources[{index}].id")
        if SOURCE_ID.fullmatch(source_id) is None:
            _fail(f"manifest.sources[{index}].id", "must be a stable lowercase source ID")
        source_ids.append(source_id)
        if source["kind"] not in {
            "rulebook", "faq_errata", "physical_component", "publisher_listing",
            "community_catalog",
        }:
            _fail(f"manifest.sources[{index}].kind", "is not a supported source kind")
        _string(source["title"], f"manifest.sources[{index}].title", maximum=256)
        _string(source["revision"], f"manifest.sources[{index}].revision", maximum=128)
        verified_on = _string(source["verified_on"], f"manifest.sources[{index}].verified_on", maximum=10)
        try:
            date.fromisoformat(verified_on)
        except ValueError as error:
            raise ContentValidationError(
                f"manifest.sources[{index}].verified_on: must be an ISO date",
            ) from error
        if "url" in source:
            _string(source["url"], f"manifest.sources[{index}].url", maximum=2048)
    if len(set(source_ids)) != len(source_ids):
        _fail("manifest.sources", "source IDs must be unique")

    expected_counts = _object(manifest["expected_counts"], "manifest.expected_counts")
    _exact_keys(expected_counts, "manifest.expected_counts", set(COLLECTION_KINDS))
    for collection, official_count in OFFICIAL_BASE_COUNTS.items():
        count = expected_counts[collection]
        if not isinstance(count, int) or isinstance(count, bool) or count != official_count:
            _fail(f"manifest.expected_counts.{collection}", f"must equal {official_count}")

    files = _object(manifest["files"], "manifest.files")
    _exact_keys(files, "manifest.files", set(COLLECTION_KINDS))
    for collection, relative in files.items():
        _safe_content_path(root, relative, f"manifest.files.{collection}")

    declared_hash = manifest.get("content_sha256")
    if declared_hash is not None and (not isinstance(declared_hash, str) or re.fullmatch(r"[a-f0-9]{64}", declared_hash) is None):
        _fail("manifest.content_sha256", "must be a lowercase SHA-256 digest")
    if status == "released" and declared_hash is None:
        _fail("manifest.content_sha256", "is required for a released pack")

    return ContentManifest(
        pack_id=pack_id,
        rules_version=rules_version,
        content_version=content_version,
        status=status,
        distribution_mode=distribution["mode"],
        sources=tuple(source_ids),
        expected_counts=dict(expected_counts),
        files=dict(files),
        declared_sha256=declared_hash,
    ), manifest


def load_content_pack(root: str | Path, *, require_released: bool = False) -> ContentPack:
    """Load and fully validate a semantic content pack without executing data.

    ``root`` must contain ``manifest.json``. Counts, source references, content
    references, review state, path containment, and the optional declared digest
    are verified before a pack is returned.
    """
    pack_root = Path(root).resolve()
    manifest_raw = _read_json(pack_root / "manifest.json", "manifest")
    manifest, manifest_document = _parse_manifest(manifest_raw, pack_root)
    if require_released and manifest.status != "released":
        _fail("manifest.status", "a released content pack is required")

    collections: dict[str, tuple[ContentEntry, ...]] = {}
    raw_collections: dict[str, list[Any]] = {}
    all_ids: set[str] = set()
    all_entries: list[ContentEntry] = []
    for collection in COLLECTION_KINDS:
        path = _safe_content_path(pack_root, manifest.files[collection], f"manifest.files.{collection}")
        raw_entries = _read_json(path, f"files.{collection}")
        if not isinstance(raw_entries, list):
            _fail(f"files.{collection}", "must contain a JSON array")
        raw_collections[collection] = raw_entries
        if len(raw_entries) != manifest.expected_counts[collection]:
            _fail(
                f"files.{collection}",
                f"expected {manifest.expected_counts[collection]} entries, found {len(raw_entries)}",
            )
        entries = tuple(
            _load_entry(value, collection, index, set(manifest.sources))
            for index, value in enumerate(raw_entries)
        )
        for entry in entries:
            if entry.id in all_ids:
                _fail(f"files.{collection}", f"duplicate content ID: {entry.id}")
            all_ids.add(entry.id)
            all_entries.append(entry)
        collections[collection] = entries

    for entry in all_entries:
        unresolved = set(entry.references) - all_ids
        if unresolved:
            _fail(entry.id, f"unresolved content references: {', '.join(sorted(unresolved))}")
        if manifest.status == "released":
            if entry.review_status != "released":
                _fail(entry.id, "every entry in a released pack must have released review status")
            if not entry.scenario_tests:
                _fail(entry.id, "every released entry must have scenario-test coverage")
            if not entry.reviewer or not entry.second_reviewer:
                _fail(entry.id, "every released entry must record two reviewers")
            if entry.reviewer == entry.second_reviewer:
                _fail(entry.id, "released entry reviewers must be independent")

    digest_manifest = {key: value for key, value in manifest_document.items() if key != "content_sha256"}
    digest_input = {
        "manifest": digest_manifest,
        "collections": raw_collections,
    }
    canonical = json.dumps(digest_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    if manifest.declared_sha256 is not None and manifest.declared_sha256 != digest:
        _fail("manifest.content_sha256", f"digest mismatch; computed {digest}")

    return ContentPack(
        root=pack_root,
        manifest=manifest,
        collections=collections,
        content_sha256=digest,
    )
