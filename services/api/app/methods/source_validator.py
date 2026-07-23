from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Mapping

import yaml
from jsonschema import Draft202012Validator

from .models import ValidatedMethodSource

EXPECTED_METHOD_ID = "hardtech-market-direction"
EXPECTED_METHOD_VERSION = "1.1.0"
EXPECTED_MANIFEST_SCHEMA_VERSION = "1.0.0"
EXPECTED_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
EXPECTED_SCHEMA_FILES = {
    "challenge.schema.json",
    "critic-packet.schema.json",
    "cynefin-gate-result.schema.json",
    "deep-analysis-result.schema.json",
    "dissent-record.schema.json",
    "draft-recommendation.schema.json",
    "focused-result.schema.json",
    "judgment-set.schema.json",
    "quality-gate-result.schema.json",
    "research-packet.schema.json",
    "safety-anchor.schema.json",
    "simulation-seeds.schema.json",
    "source-span.schema.json",
    "strategic-lens-output.schema.json",
    "structured-report.schema.json",
    "validator-aggregate.schema.json",
    "validator-result.schema.json",
}
EXPECTED_PROMPT_FILES = {
    "critic.md",
    "research.md",
    "safety-anchor.md",
    "synthesis.md",
    "validation.md",
    "lenses/counterparty-response-matrix.md",
    "lenses/meadows-leverage-points.md",
    "lenses/porter-five-forces.md",
    "lenses/pre-mortem.md",
    "lenses/scenario-planning.md",
}
EXPECTED_LENS_IDS = [
    "porter_five_forces",
    "pre_mortem",
    "counterparty_response_matrix",
    "scenario_planning",
    "meadows_leverage_points",
]
EXPECTED_VALIDATORS = [
    "V1_scope_charter",
    "V2_source_traceability",
    "V3_evidence_quality",
    "V4_claim_evidence_entailment",
    "V5_contradiction_alignment",
    "V6_unknown_assumption",
    "V7_adversarial_dissent",
    "V8_causal_simulation",
    "V9_publication_authority",
]
EXPECTED_SKILL_DISPOSITION_COUNTS = {
    "P0 直接编译": 13,
    "能力已被其他合同吸收": 7,
    "延后到下一方法包": 8,
    "仅参考": 1,
    "禁用": 2,
}
KNOWN_WORKERS = {"research", "critic", "synthesis", "validation"}
KNOWN_TOOLS = {
    "search_web",
    "fetch_url",
    "crawl_site",
    "extract_document",
    "get_source_status",
}
FORBIDDEN_TOOLS = {
    "external_write",
    "arbitrary_browser_action",
    "arbitrary_mcp",
    "provider_credentials",
    "secret_access",
    "sign_decision",
    "transition_to_decided",
    "update_decision_record",
    "create_report_without_run",
}
EXPECTED_APPLICABILITY_RULES = [
    {
        "rule_id": "subject_is_hardtech",
        "field": "subject.class",
        "operator": "in",
        "value": [
            "hardtech",
            "robotics",
            "industrial_device",
            "scientific_instrument",
            "regulated_device",
        ],
    },
    {
        "rule_id": "decision_is_market_direction",
        "field": "decision.type",
        "operator": "in",
        "value": [
            "market_direction",
            "segment_selection",
            "use_case_selection",
            "product_market_path",
        ],
    },
    {
        "rule_id": "comparable_options",
        "field": "options.count",
        "operator": "gte",
        "value": 2,
    },
    {
        "rule_id": "switching_cost_material",
        "field": "switching_cost.material",
        "operator": "eq",
        "value": True,
    },
    {
        "rule_id": "decision_contract_confirmed",
        "field": "confirmation.route_inputs_confirmed",
        "operator": "eq",
        "value": True,
    },
]
EXPECTED_EXCLUSION_ROUTES = {
    "no_real_choice": ("fewer_than_two_comparable_options", "partial"),
    "pure_marketing_optimization": (
        "no_material_r_and_d_delivery_or_switching_constraint",
        "unsupported",
    ),
    "single_option_certification": (
        "question_is_only_engineering_certification_or_compliance_signoff",
        "unsupported",
    ),
    "investment_selection": (
        "primary_question_is_security_or_portfolio_investment",
        "unsupported",
    ),
    "unsafe_or_unconfirmed_materials": (
        "analysis_requires_prohibited_or_unconfirmed_materials",
        "partial",
    ),
}
EXPECTED_REQUIRED_INPUTS = [
    {
        "id": "decision_subject",
        "type": "confirmed_snapshot",
        "required_for": ["focused", "full"],
        "fields": ["subject.id", "subject.class", "subject.stage", "subject.owner"],
    },
    {
        "id": "decision_question_and_deadline",
        "type": "confirmed_case_fields",
        "required_for": ["focused", "full"],
        "fields": ["decision.question", "decision.deadline"],
    },
    {
        "id": "goals_and_hard_constraints",
        "type": "confirmed_case_fields",
        "required_for": ["focused", "full"],
        "fields": ["goals", "constraints"],
    },
    {
        "id": "comparable_options",
        "type": "confirmed_case_fields",
        "required_for": ["focused", "full"],
        "minimum_items": 2,
        "fields": ["options"],
    },
    {
        "id": "evidence_policy",
        "type": "confirmed_charter_fields",
        "required_for": ["focused", "full"],
        "fields": ["allowed_materials", "prohibited_materials", "allowed_connectors"],
    },
    {
        "id": "knowns_assumptions_unknowns",
        "type": "confirmed_case_fields",
        "required_for": ["focused", "full"],
        "fields": ["known_facts", "assumptions", "unknown_items"],
    },
    {
        "id": "reproducibility",
        "type": "immutable_references",
        "required_for": ["focused", "full"],
        "fields": [
            "workspace_id",
            "case_version",
            "case_snapshot_hash",
            "dossier_snapshot_hash",
        ],
    },
]
EXPECTED_CYNEFIN_CONTRACT = {
    "required_before_formal_run": True,
    "output_schema": "urn:ludus:method:hardtech-market-direction:cynefin-gate-result:1.1.0",
    "domains": ["clear", "complicated", "complex", "chaotic", "disorder"],
    "default_routes": {
        "clear": "quick",
        "complicated": "focused",
        "complex": "full",
        "chaotic": "stabilize_first",
        "disorder": "clarify_scope",
    },
    "formal_block_domains": ["chaotic", "disorder"],
    "human_override_required_for": ["clear", "chaotic", "disorder"],
    "freeze_into": ["analysis_charter", "run_manifest"],
}


class MethodSourceValidationError(ValueError):
    """Raised when a source or runtime method pack violates its contract."""


class MethodPathError(MethodSourceValidationError):
    """Raised when a manifest path is absolute or escapes the package root."""


def _is_link_like(path: Path) -> bool:
    """Return true for POSIX symlinks and Windows directory junctions."""

    return path.is_symlink() or path.is_junction()


def _fail(message: str) -> None:
    raise MethodSourceValidationError(message)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise MethodSourceValidationError(f"non-UTF-8 method-pack file: {path}") from exc
    except OSError as exc:
        raise MethodSourceValidationError(f"cannot read method-pack file: {path}") from exc


def _load_yaml(path: Path) -> Any:
    try:
        value = yaml.safe_load(_read_text(path))
    except yaml.YAMLError as exc:
        raise MethodSourceValidationError(f"invalid YAML: {path}: {exc}") from exc
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise MethodSourceValidationError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        _fail(f"JSON document must be an object: {path}")
    return value


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _safe_relative_path(root: Path, value: Any, context: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise MethodPathError(f"{context}: path must be a non-empty string")
    raw = value.replace("\\", "/")
    if PureWindowsPath(raw).drive:
        raise MethodPathError(f"{context}: path escapes package boundary: {value}")
    posix = PurePosixPath(raw)
    if posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
        raise MethodPathError(f"{context}: path escapes package boundary: {value}")
    lexical_candidate = root.joinpath(*posix.parts)
    current = root
    for part in posix.parts:
        current /= part
        if _is_link_like(current):
            raise MethodPathError(f"{context}: linked path is forbidden: {value}")
    candidate = lexical_candidate.resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise MethodPathError(f"{context}: path escapes package boundary: {value}")
    return candidate


def _require_file(root: Path, value: Any, context: str) -> Path:
    path = _safe_relative_path(root, value, context)
    if not path.is_file() or path.is_symlink():
        raise MethodSourceValidationError(f"{context}: referenced file is missing or symlinked: {value}")
    return path


def _require_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{context} must be a mapping")
    return value


def _require_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{context} must be a list")
    return value


def _resolve_pointer(document: Any, fragment: str, context: str) -> Any:
    current = document
    if not fragment:
        return current
    if not fragment.startswith("/"):
        _fail(f"invalid JSON pointer in {context}: {fragment}")
    for raw_token in fragment[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list) and token.isdigit():
            index = int(token)
            if index >= len(current):
                _fail(f"unresolved JSON pointer in {context}: {fragment}")
            current = current[index]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            _fail(f"unresolved JSON pointer in {context}: {fragment}")
    return current


def _prompt_metadata(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, flags=re.DOTALL)
    if match is None:
        _fail(f"prompt frontmatter missing: {path}")
    metadata = yaml.safe_load(match.group(1))
    if not isinstance(metadata, dict):
        _fail(f"prompt frontmatter invalid: {path}")
    return metadata


def _manifest_path(root: Path, manifest: Mapping[str, Any], key: str) -> Path:
    documentation = _require_mapping(manifest.get("documentation"), "manifest.documentation")
    return _require_file(root, documentation.get(key), f"manifest.documentation.{key}")


def _check_json_schemas(root: Path, manifest: Mapping[str, Any]) -> tuple[tuple[str, ...], dict[str, dict[str, Any]]]:
    schemas_dir = root / "schemas"
    if not schemas_dir.is_dir():
        _fail("schemas directory missing")
    schema_paths = sorted(schemas_dir.glob("*.json"))
    actual_names = {path.name for path in schema_paths}
    if actual_names != EXPECTED_SCHEMA_FILES:
        _fail(f"schema file set drift: missing={sorted(EXPECTED_SCHEMA_FILES - actual_names)} extra={sorted(actual_names - EXPECTED_SCHEMA_FILES)}")

    by_id: dict[str, dict[str, Any]] = {}
    path_by_id: dict[str, Path] = {}
    document_by_path: dict[Path, dict[str, Any]] = {}
    for path in schema_paths:
        document = _load_json(path)
        if document.get("$schema") != EXPECTED_SCHEMA_DRAFT:
            _fail(f"schema draft drift: {path}")
        schema_id = document.get("$id")
        if not isinstance(schema_id, str) or not schema_id.endswith(f":{EXPECTED_METHOD_VERSION}"):
            _fail(f"schema ID drift: {path}: {schema_id}")
        if schema_id in by_id:
            _fail(f"duplicate schema ID: {schema_id}")
        try:
            Draft202012Validator.check_schema(document)
        except Exception as exc:
            raise MethodSourceValidationError(f"schema metaschema failure: {path}: {exc}") from exc
        by_id[schema_id] = document
        path_by_id[schema_id] = path.resolve()
        document_by_path[path.resolve()] = document

    registry = _require_mapping(manifest.get("schemas"), "manifest.schemas")
    if len(registry) != len(schema_paths):
        _fail("manifest schema registry size drift")
    for name, descriptor_value in registry.items():
        descriptor = _require_mapping(descriptor_value, f"manifest.schemas.{name}")
        path = _require_file(root, descriptor.get("path"), f"manifest.schemas.{name}.path")
        document = document_by_path.get(path.resolve())
        if document is None:
            _fail(f"manifest schema path is not in schemas directory: {path}")
        if descriptor.get("id") != document.get("$id"):
            _fail(f"schema id/path mismatch: {name}")

    for path, document in document_by_path.items():
        for value in _walk(document):
            if not isinstance(value, dict) or "$ref" not in value:
                continue
            reference = value["$ref"]
            if not isinstance(reference, str):
                _fail(f"non-string schema ref: {path}")
            if ":1.0.0" in reference:
                _fail(f"stale schema reference: {path}: {reference}")
            if reference.startswith("#"):
                _resolve_pointer(document, reference[1:], f"{path}: {reference}")
            elif reference.startswith("urn:"):
                base, separator, fragment = reference.partition("#")
                if base not in by_id:
                    _fail(f"unresolved schema URN: {path}: {reference}")
                if separator:
                    _resolve_pointer(by_id[base], fragment, f"{path}: {reference}")
            elif reference.startswith(("http://", "https://")):
                _fail(f"network schema ref forbidden: {path}: {reference}")
            else:
                file_part, separator, fragment = reference.partition("#")
                target_path = _safe_relative_path(path.parent, file_part, f"{path}: $ref")
                target = document_by_path.get(target_path.resolve())
                if target is None:
                    _fail(f"unresolved relative schema ref: {path}: {reference}")
                if separator:
                    _resolve_pointer(target, fragment, f"{path}: {reference}")

    return tuple(sorted(by_id)), by_id


def _check_prompts(root: Path, manifest: Mapping[str, Any]) -> tuple[Path, ...]:
    prompts_dir = root / "prompts"
    paths = sorted(path for path in prompts_dir.rglob("*.md") if path.is_file()) if prompts_dir.is_dir() else []
    actual = {path.relative_to(root).as_posix() for path in paths}
    if actual != {f"prompts/{item}" for item in EXPECTED_PROMPT_FILES}:
        expected = {f"prompts/{item}" for item in EXPECTED_PROMPT_FILES}
        _fail(f"prompt file set drift: missing={sorted(expected - actual)} extra={sorted(actual - expected)}")
    for path in paths:
        metadata = _prompt_metadata(path)
        if metadata.get("version") != EXPECTED_METHOD_VERSION:
            _fail(f"prompt version drift: {path}")
        for value in _walk(metadata):
            if isinstance(value, str) and value.startswith("urn:ludus:method:") and not value.endswith(f":{EXPECTED_METHOD_VERSION}"):
                _fail(f"prompt schema reference drift: {path}: {value}")
    synthesis = _read_text(root / "prompts" / "synthesis.md")
    if "outcome.kind=abstain" not in synthesis or "不得使用空 option ID" not in synthesis:
        _fail("synthesis abstain contract missing")
    return tuple(paths)


def _check_capability_map(root: Path, manifest: Mapping[str, Any]) -> dict[str, int]:
    path = _require_file(root, "CAPABILITY-MAP.md", "capability map")
    text = _read_text(path)
    section_match = re.search(
        r"## 31 个 Skill 全量映射\s*(.*?)(?:\n固定计数：)",
        text,
        flags=re.DOTALL,
    )
    if section_match is None:
        _fail("31-Skill capability map section missing")
    rows = re.findall(
        r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|",
        section_match.group(1),
        flags=re.MULTILINE,
    )
    if len(rows) != 31:
        _fail(f"expected 31 capability rows, got {len(rows)}")

    semver = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
    capability_versions: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for reference, status in rows:
        name, separator, version = reference.rpartition("@")
        if (
            not separator
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name)
            or not semver.fullmatch(version)
            or name in capability_versions
        ):
            _fail(f"invalid or duplicate capability Skill reference: {reference}")
        capability_versions[name] = version
        counts[status.strip()] += 1

    actual_counts = {key: counts.get(key, 0) for key in EXPECTED_SKILL_DISPOSITION_COUNTS}
    if actual_counts != EXPECTED_SKILL_DISPOSITION_COUNTS:
        _fail(f"Skill disposition drift: {actual_counts}")

    sources_text = _read_text(_require_file(root, "SOURCES.md", "source provenance"))
    source_rows = re.findall(
        r"^\|\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*\|\s*"
        r"(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\s*\|\s*`([^`]+)`\s*\|",
        sources_text,
        flags=re.MULTILINE,
    )
    source_table: dict[str, tuple[str, str]] = {}
    for name, version, source_path in source_rows:
        if name in source_table:
            _fail(f"duplicate source provenance row: {name}")
        source_table[name] = (version, source_path.replace("\\", "/"))

    manifest_sources: dict[str, tuple[str, str]] = {}
    source_skills = _require_list(manifest.get("source_skills"), "manifest.source_skills")
    for item in source_skills:
        source = _require_mapping(item, "manifest.source_skills item")
        name = source.get("name")
        version = source.get("version")
        source_path = source.get("path")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name)
            or not isinstance(version, str)
            or not semver.fullmatch(version)
            or not isinstance(source_path, str)
            or name in manifest_sources
        ):
            _fail(f"invalid or duplicate manifest source Skill: {name}")
        normalized_path = source_path.replace("\\", "/")
        expected_path = f"探讨/skills/research/{name}/SKILL.md"
        if normalized_path != expected_path:
            _fail(f"source Skill path drift: {name}: {source_path}")
        manifest_sources[name] = (version, normalized_path)

    if set(manifest_sources) != set(source_table):
        _fail(
            "manifest/SOURCES source Skill set drift: "
            f"missing={sorted(set(source_table) - set(manifest_sources))} "
            f"extra={sorted(set(manifest_sources) - set(source_table))}"
        )
    for name, (version, source_path) in manifest_sources.items():
        if capability_versions.get(name) != version:
            _fail(f"manifest/CAPABILITY-MAP source Skill version drift: {name}")
        if source_table.get(name) != (version, source_path):
            _fail(f"manifest/SOURCES source Skill version or path drift: {name}")

    default_research_root = root.parents[3] / "探讨" / "skills" / "research"
    if default_research_root.is_dir():
        skill_dirs = {
            skill_dir.name
            for skill_dir in default_research_root.iterdir()
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file()
        }
        mapped_names = set(capability_versions)
        if len(skill_dirs) != 31:
            _fail(f"expected 31 research Skills, got {len(skill_dirs)}")
        if skill_dirs != mapped_names:
            _fail(
                f"Skill map drift: missing={sorted(skill_dirs - mapped_names)} "
                f"extra={sorted(mapped_names - skill_dirs)}"
            )
        for name, (version, _) in manifest_sources.items():
            skill_path = default_research_root / name / "SKILL.md"
            if skill_path.is_symlink():
                _fail(f"source Skill symlink is forbidden: {skill_path}")
            metadata = _prompt_metadata(skill_path)
            if metadata.get("name") != name or str(metadata.get("version")) != version:
                _fail(f"source Skill frontmatter drift: {name}")
    return actual_counts


def _check_manifest_contract(root: Path, manifest: Mapping[str, Any], schema_ids: set[str]) -> None:
    if manifest.get("manifest_schema_version") != EXPECTED_MANIFEST_SCHEMA_VERSION:
        _fail("manifest schema version drift")
    if manifest.get("id") != EXPECTED_METHOD_ID:
        _fail(f"method id drift: {manifest.get('id')}")
    if manifest.get("version") != EXPECTED_METHOD_VERSION:
        _fail(f"method version drift: {manifest.get('version')}")

    applicability = _require_mapping(manifest.get("applicability"), "manifest.applicability")
    applicability_rules = _require_list(applicability.get("all"), "manifest.applicability.all")
    if applicability_rules != EXPECTED_APPLICABILITY_RULES:
        _fail("applicability rule contract drift")

    exclusions = _require_mapping(manifest.get("exclusions"), "manifest.exclusions")
    exclusion_rules = _require_list(exclusions.get("any"), "manifest.exclusions.any")
    exclusion_by_id: dict[str, dict[str, Any]] = {}
    for item in exclusion_rules:
        rule = _require_mapping(item, "manifest exclusion")
        rule_id = rule.get("rule_id")
        if not isinstance(rule_id, str) or rule_id in exclusion_by_id:
            _fail(f"invalid or duplicate exclusion rule: {rule_id}")
        exclusion_by_id[rule_id] = rule
    if set(exclusion_by_id) != set(EXPECTED_EXCLUSION_ROUTES):
        _fail("exclusion rule set drift")
    for rule_id, (expected_when, expected_route) in EXPECTED_EXCLUSION_ROUTES.items():
        rule = exclusion_by_id[rule_id]
        if rule.get("when") != expected_when or rule.get("route") != expected_route:
            _fail(f"exclusion route contract drift: {rule_id}")

    decision_gate = _require_mapping(manifest.get("decision_gate"), "manifest.decision_gate")
    cynefin = _require_mapping(decision_gate.get("cynefin"), "manifest.decision_gate.cynefin")
    if cynefin != EXPECTED_CYNEFIN_CONTRACT:
        _fail("Cynefin decision-gate contract drift")
    if cynefin.get("output_schema") not in schema_ids:
        _fail("Cynefin decision-gate references an unknown schema")

    for key in ("overview", "changelog", "eval_guide", "source_provenance", "capability_map"):
        _manifest_path(root, manifest, key)
    required_inputs = _require_list(manifest.get("required_inputs"), "manifest.required_inputs")
    if required_inputs != EXPECTED_REQUIRED_INPUTS:
        _fail("required input contract drift")

    workers = _require_list(manifest.get("workers"), "manifest.workers")
    worker_by_id: dict[str, dict[str, Any]] = {}
    for item in workers:
        worker = _require_mapping(item, "manifest.worker")
        worker_id = worker.get("id")
        if worker_id not in KNOWN_WORKERS or worker_id in worker_by_id:
            _fail(f"unknown or duplicate worker: {worker_id}")
        worker_by_id[worker_id] = worker
        if "prompt" in worker:
            _require_file(root, worker["prompt"], f"worker {worker_id} prompt")
        for key in ("output_schema", "auxiliary_output_schema"):
            if key in worker:
                schema_id = worker[key]
                if schema_id not in schema_ids:
                    _fail(f"worker {worker_id} references unknown schema: {schema_id}")
        if "output_schemas" in worker:
            outputs = _require_mapping(worker["output_schemas"], f"worker {worker_id}.output_schemas")
            for schema_id in outputs.values():
                if schema_id not in schema_ids:
                    _fail(f"worker {worker_id} references unknown schema: {schema_id}")
    if set(worker_by_id) != KNOWN_WORKERS:
        _fail(f"worker set drift: {sorted(worker_by_id)}")

    critic_substeps = _require_list(worker_by_id["critic"].get("mandatory_substeps"), "critic mandatory_substeps")
    substep_by_id = {_require_mapping(item, "critic substep").get("id"): item for item in critic_substeps}
    if set(substep_by_id) != {"safety_anchor", "adversarial_review"}:
        _fail("critic mandatory substep set drift")
    safety = _require_mapping(substep_by_id["safety_anchor"], "safety_anchor")
    if safety.get("output_schema") not in schema_ids:
        _fail("safety anchor output schema is unknown")
    _require_file(root, safety.get("prompt"), "safety anchor prompt")

    quality = _require_mapping(manifest.get("quality_gates"), "manifest.quality_gates")
    if quality.get("validator_contracts_exact") != EXPECTED_VALIDATORS:
        _fail("validator contract set/order drift")
    _require_file(root, quality.get("definition"), "quality gate definition")

    levels = _require_mapping(manifest.get("analysis_levels"), "manifest.analysis_levels")
    if set(levels) != {"quick", "focused", "full"}:
        _fail("analysis level set drift")
    focused_lenses = _require_mapping(levels["focused"], "focused level").get("required_lens_artifacts")
    full_lenses = _require_mapping(levels["full"], "full level").get("required_lens_artifacts")
    if focused_lenses != [] or full_lenses != EXPECTED_LENS_IDS:
        _fail("required lens artifact contract drift")
    for level in ("focused", "full"):
        output_schema = _require_mapping(levels[level], f"{level} level").get("output_schema")
        if output_schema not in schema_ids:
            _fail(f"{level} level references unknown output schema")

    lens_protocols = _require_list(manifest.get("lens_protocols"), "manifest.lens_protocols")
    lens_ids = []
    for item in lens_protocols:
        lens = _require_mapping(item, "lens protocol")
        lens_id = lens.get("id")
        lens_ids.append(lens_id)
        if lens.get("output_schema") not in schema_ids:
            _fail(f"lens {lens_id} references unknown schema")
        _require_file(root, lens.get("prompt"), f"lens {lens_id} prompt")
        if lens_id not in EXPECTED_LENS_IDS:
            _fail(f"unknown strategic lens: {lens_id}")
    if len(lens_ids) != len(EXPECTED_LENS_IDS) or set(lens_ids) != set(EXPECTED_LENS_IDS):
        _fail("strategic lens set drift")

    permissions = _require_mapping(manifest.get("tool_permissions"), "manifest.tool_permissions")
    stable_catalog = _require_list(
        permissions.get("stable_read_only_catalog"), "stable_read_only_catalog"
    )
    if not all(isinstance(item, str) for item in stable_catalog) or set(stable_catalog) != KNOWN_TOOLS:
        _fail("stable read-only tool catalog drift or unknown tool")
    by_worker = _require_mapping(permissions.get("by_worker"), "tool permissions by_worker")
    if set(by_worker) != KNOWN_WORKERS:
        _fail("tool permission worker set drift")
    for worker_id, value in by_worker.items():
        permission = _require_mapping(value, f"tool permission {worker_id}")
        allowed = _require_list(permission.get("allow", []), f"tool permission {worker_id}.allow")
        if not all(isinstance(item, str) for item in allowed) or not set(allowed).issubset(KNOWN_TOOLS):
            _fail(f"unknown tool permission for {worker_id}")
    denied_values = _require_list(permissions.get("deny_for_all"), "deny_for_all")
    if not all(isinstance(item, str) for item in denied_values):
        _fail("deny_for_all contains a non-string tool")
    denied = set(denied_values)
    if not denied.issubset(KNOWN_TOOLS | FORBIDDEN_TOOLS):
        _fail("deny_for_all contains an unknown tool")
    if not FORBIDDEN_TOOLS.issubset(denied):
        _fail("forbidden tool deny list is incomplete")

    evals = _require_list(manifest.get("evals"), "manifest.evals")
    eval_paths: set[str] = set()
    for item in evals:
        evaluation = _require_mapping(item, "manifest.eval")
        eval_path = _require_file(root, evaluation.get("path"), "manifest.eval.path")
        eval_paths.add(eval_path.relative_to(root).as_posix())
        eval_document = _load_json(eval_path)
        if eval_document.get("schemaVersion") != "1.0.0":
            _fail(f"eval schema version drift: {eval_path}")
        required_route = evaluation.get("required_route")
        if required_route in {"exact", "partial", "unsupported"}:
            eval_input = _require_mapping(eval_document.get("input"), f"{eval_path} input")
            expected_route = _require_mapping(
                eval_document.get("expectedRoute"), f"{eval_path} expectedRoute"
            )
            if expected_route.get("matchStatus") != required_route:
                _fail(f"eval route declaration drift: {eval_path}")
            requested_level = eval_input.get("requestedAnalysisLevel")
            if requested_level != evaluation.get("required_level"):
                _fail(f"eval requested analysis level drift: {eval_path}")
            allowed_connectors = eval_input.get("allowedConnectors")
            if (
                not isinstance(allowed_connectors, list)
                or not allowed_connectors
                or not all(isinstance(value, str) for value in allowed_connectors)
                or not set(allowed_connectors).issubset(KNOWN_TOOLS)
            ):
                _fail(f"eval allowed connector contract drift: {eval_path}")
            if required_route == "exact":
                confirmation = _require_mapping(
                    eval_input.get("confirmation"), f"{eval_path} confirmation"
                )
                if any(
                    confirmation.get(field) is not True
                    for field in (
                        "routeInputsConfirmed",
                        "allowedMaterialsConfirmed",
                        "unknownItemsConfirmed",
                    )
                ):
                    _fail(f"exact eval confirmation contract drift: {eval_path}")
        elif required_route == "gate_contract":
            cases = _require_list(eval_document.get("cases"), f"{eval_path} cases")
            domains = [
                _require_mapping(case, f"{eval_path} case").get("domain") for case in cases
            ]
            if domains != EXPECTED_CYNEFIN_CONTRACT["domains"]:
                _fail(f"Cynefin eval domain contract drift: {eval_path}")
        else:
            _fail(f"unknown eval route contract: {eval_path}: {required_route}")
    actual_eval_paths = {path.relative_to(root).as_posix() for path in (root / "evals").glob("*.json")}
    if eval_paths != actual_eval_paths:
        _fail(f"eval file set drift: missing={sorted(actual_eval_paths - eval_paths)} extra={sorted(eval_paths - actual_eval_paths)}")

    diagnostic = _load_yaml(_require_file(root, "diagnostic-questions.yaml", "diagnostic questions"))
    quality_file = _load_yaml(_require_file(root, "quality-gates.yaml", "quality gates"))
    if not isinstance(diagnostic, dict) or diagnostic.get("method_version") != EXPECTED_METHOD_VERSION:
        _fail("diagnostic method version drift")
    if not isinstance(quality_file, dict) or quality_file.get("method_version") != EXPECTED_METHOD_VERSION:
        _fail("quality-gates method version drift")
    if "abstain" not in _read_text(root / "quality-gates.yaml"):
        _fail("quality gates lack abstain")


def _validate(root: Path, *, runtime: bool) -> ValidatedMethodSource:
    requested_root = root.expanduser().absolute()
    if _is_link_like(requested_root):
        raise MethodSourceValidationError(f"linked method package root is forbidden: {requested_root}")
    root = requested_root.resolve()
    if not root.is_dir():
        raise MethodSourceValidationError(f"method package directory missing: {root}")
    for path in root.rglob("*"):
        if _is_link_like(path):
            _fail(f"linked path is forbidden in method package: {path}")
    manifest_path = root / "manifest.yaml"
    manifest = _load_yaml(manifest_path)
    if not isinstance(manifest, dict):
        _fail("manifest.yaml must contain a mapping")
    expected_status = "published" if runtime else "release_candidate"
    expected_runtime_status = "published" if runtime else "unpublished"
    if manifest.get("status") != expected_status:
        _fail(f"method status must be {expected_status}")
    release = _require_mapping(manifest.get("release"), "manifest.release")
    if release.get("runtime_status") != expected_runtime_status:
        _fail(f"runtime status must be {expected_runtime_status}")
    if release.get("content_hash_algorithm") != "sha256":
        _fail("method content hash algorithm must be sha256")
    if release.get("hash_scope") != "all_package_files_except_manifest_release_content_hash":
        _fail("method content hash scope drift")
    if release.get("immutable_after_publish") is not True:
        _fail("method pack must be immutable after publish")
    if runtime and not isinstance(release.get("content_hash"), str):
        _fail("published method pack content hash is missing")
    if not runtime and release.get("content_hash") is not None:
        _fail("source method pack must not contain a published content hash")

    schema_ids, _ = _check_json_schemas(root, manifest)
    _check_manifest_contract(root, manifest, set(schema_ids))
    prompt_paths = _check_prompts(root, manifest)
    skill_counts = _check_capability_map(root, manifest)
    eval_paths = tuple(sorted((root / "evals").glob("*.json")))
    files = tuple(sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: path.relative_to(root).as_posix()))
    return ValidatedMethodSource(
        root=root,
        method_id=str(manifest["id"]),
        version=str(manifest["version"]),
        manifest=copy.deepcopy(manifest),
        files=files,
        schema_ids=tuple(schema_ids),
        prompt_paths=prompt_paths,
        eval_paths=eval_paths,
        skill_disposition_counts=skill_counts,
    )


def validate_method_source(source_path: str | Path) -> ValidatedMethodSource:
    """Validate the editable ``ways`` source package without modifying it."""

    return _validate(Path(source_path), runtime=False)


def validate_runtime_package(package_path: str | Path) -> ValidatedMethodSource:
    """Validate the structural contract of a published runtime package."""

    return _validate(Path(package_path), runtime=True)


def _normalized_bytes(path: Path, *, manifest_content_hash_is_empty: bool = False, root: Path | None = None) -> bytes:
    data = path.read_bytes()
    if path.name == "manifest.yaml" and manifest_content_hash_is_empty:
        if root is None:
            raise ValueError("root is required when normalizing the manifest")
        manifest = yaml.safe_load(data.decode("utf-8"))
        if not isinstance(manifest, dict):
            raise MethodSourceValidationError("manifest is not a mapping while hashing")
        release = manifest.get("release")
        if isinstance(release, dict):
            release["content_hash"] = None
        data = (yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False).replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))
    else:
        try:
            data = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        except UnicodeDecodeError:
            pass
    return data


def compute_package_hash(package_root: str | Path, *, published_manifest: bool = False) -> str:
    """Compute the deterministic SHA-256 for a source or published package."""

    requested_root = Path(package_root).expanduser().absolute()
    if _is_link_like(requested_root):
        raise MethodSourceValidationError(f"linked package root is forbidden: {requested_root}")
    root = requested_root.resolve()
    if not root.is_dir():
        raise MethodSourceValidationError(f"package root is missing: {root}")
    hasher = hashlib.sha256()
    all_paths = tuple(root.rglob("*"))
    for path in all_paths:
        if _is_link_like(path):
            _fail(f"linked path is forbidden in method package: {path}")
    paths = sorted((path for path in all_paths if path.is_file()), key=lambda path: path.relative_to(root).as_posix())
    for path in paths:
        relative = path.relative_to(root).as_posix()
        content = _normalized_bytes(path, manifest_content_hash_is_empty=published_manifest, root=root)
        relative_bytes = relative.encode("utf-8")
        hasher.update(len(relative_bytes).to_bytes(8, "big"))
        hasher.update(relative_bytes)
        hasher.update(len(content).to_bytes(8, "big"))
        hasher.update(content)
    return hasher.hexdigest()
