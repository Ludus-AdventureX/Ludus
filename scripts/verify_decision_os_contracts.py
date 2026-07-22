"""Static, secret-safe contract checks for Ludus Decision OS.

Reads only planning documents, the fixed Look core bundle, method-pack
metadata/schemas/evals, and research Skill directory names. Credential files
such as .env and auth.json are never opened.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "decision-lab-product-plan"
REPO = ROOT / "decision-lab"
LOOK = ROOT / "look"
WAYS = REPO / "ways" / "hardtech-market-direction"
CURRENT_WAY = WAYS / "1.1.0"
LEGACY_WAY = WAYS / "1.0.0"
RESEARCH = ROOT / "探讨" / "skills" / "research"
LOOK_FILES = ("VERSION", "README.md", "index.html", "themes.css", "styles.css", "app.js")
LOOK_HASH = "c5d5d65bf62efdd14e4e3e13d1c70b92f9d6b4cdd4dbd2f652107d84d1a55e98"
THEMES = ("ink", "ledger", "vermilion", "red", "orange", "yellow", "green", "cyan", "blue", "purple")
VALIDATORS = (
    "V1_scope_charter", "V2_source_traceability", "V3_evidence_quality",
    "V4_claim_evidence_entailment", "V5_contradiction_alignment",
    "V6_unknown_assumption", "V7_adversarial_dissent",
    "V8_causal_simulation", "V9_publication_authority",
)
SCHEMA_FILES = {
    "challenge.schema.json", "critic-packet.schema.json", "cynefin-gate-result.schema.json",
    "deep-analysis-result.schema.json", "dissent-record.schema.json", "draft-recommendation.schema.json",
    "focused-result.schema.json", "judgment-set.schema.json", "quality-gate-result.schema.json",
    "research-packet.schema.json", "safety-anchor.schema.json", "simulation-seeds.schema.json",
    "source-span.schema.json", "strategic-lens-output.schema.json", "structured-report.schema.json",
    "validator-aggregate.schema.json", "validator-result.schema.json",
}
OWNERS = {"contract_lead", "ways_agent_pipeline", "case_api_data", "web_ux", "simulation_graph", "qa_release"}
TASK_IDS = {
    "task-01", "task-01w", "task-02", "task-03", "task-04", "task-05", "task-06", "task-07",
    "task-08", "task-09", "task-10", "task-11", "task-12", "task-13", "task-14", "task-14w",
    "task-15", "task-16", "task-17", "task-18a", "task-18", "task-19a", "task-19b", "task-19c",
    "task-19d", "task-19",
}
METRICS: dict[str, str] = {}


class ContractFailure(AssertionError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractFailure(message)


def read_text(path: Path) -> str:
    require(path.is_file(), f"missing file: {path}")
    require(path.name.lower() not in {".env", "auth.json"}, f"refusing secret-like file: {path}")
    return path.read_text(encoding="utf-8")


def require_text(path: Path, *needles: str) -> str:
    text = read_text(path)
    for needle in needles:
        require(needle in text, f"{path}: missing {needle!r}")
    return text


def yaml_load(path: Path) -> Any:
    require(yaml is not None, "PyYAML is required; install it or add it to PYTHONPATH")
    return yaml.safe_load(read_text(path))


def look_digest() -> str:
    digest = hashlib.sha256()
    for name in LOOK_FILES:
        path = LOOK / name
        require(path.is_file(), f"missing Look core file: {path}")
        digest.update(name.encode("utf-8"))
        digest.update(b"\n")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return digest.hexdigest()


def check_look() -> None:
    actual = look_digest()
    require(actual == LOOK_HASH, f"Look bundle drift: expected {LOOK_HASH}, got {actual}")
    frontend = require_text(
        PLAN / "11-frontend-spec.md", "最终视觉与关键交互设计源", "不得被生产 Web 直接加载",
        "只把 `app.js` 当行为规格", f"sha256:{LOOK_HASH}",
    )
    visual = require_text(
        PLAN / "24-frontend-visual-theme.md", "Review 是 dialog/drawer", "Case 选择是 Project Drawer",
        "`empty` view", "默认主题是 `ink`", "不是公开 theme ID",
    )
    require_text(
        PLAN / "18-detailed-development-plan.md", "Task 1W: Web/UX bootstrap 与 Look V7 设计快照",
        "design/look-source-manifest.json", "scripts/snapshot_look.py",
    )
    for view in ("workspace", "analysis", "report", "sandbox", "decision"):
        require(f"`{view}`" in frontend, f"missing canonical view: {view}")
    rows = re.findall(r"^\|\s*\d+\s*\|\s*`([^`]+)`\s*\|", visual, flags=re.MULTILINE)
    require(tuple(rows) == THEMES, f"theme ID/order drift: {rows}")
    METRICS["look"] = f"sha256:{actual}"


def interface_body(text: str, name: str) -> str:
    match = re.search(rf"(?:export\s+)?interface\s+{re.escape(name)}(?:\s+extends\s+[^{{]+)?\s*\{{", text)
    require(match is not None, f"missing interface {name}")
    start = match.end() - 1
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index]
    raise ContractFailure(f"unterminated interface {name}")


def interface_fields(text: str, name: str) -> tuple[tuple[str, bool, str], ...]:
    fields: list[tuple[str, bool, str]] = []
    for raw in interface_body(text, name).splitlines():
        line = raw.split("//", 1)[0].strip()
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(\?)?:\s*(.+);", line)
        if match:
            fields.append((match.group(1), bool(match.group(2)), re.sub(r"\s+", " ", match.group(3).strip())))
    require(fields, f"could not parse interface {name}")
    return tuple(fields)


def exact_interface(text: str, name: str, expected: Iterable[tuple[str, bool, str]]) -> None:
    actual = interface_fields(text, name)
    expected_tuple = tuple(expected)
    require(actual == expected_tuple, f"{name} drift:\nexpected={expected_tuple}\nactual={actual}")

def check_canonical_data() -> None:
    require_text(
        PLAN / "docs" / "contract-changes" / "CCR-20260721-003.md",
        "- Status: accepted", "- Date accepted: 2026-07-21",
        "72 小时只承诺 Hackathon Prototype Slice",
    )
    dm = read_text(PLAN / "06-data-model.md")
    inv = read_text(PLAN / "26-decision-os-invariants-and-agent-engine-contract.md")
    method_ref = (("id", False, "string"), ("version", False, "string"), ("contentHash", False, "string"))
    deep_request = (
        ("workspaceId", False, "string"), ("decisionCaseId", False, "string"),
        ("analysisRunId", False, "string"), ("charterId", False, "string"),
        ("charterVersion", False, "number"), ("caseSnapshotHash", False, "string"),
        ("dossierSnapshotHash", False, "string"), ("materialSnapshotHash", False, "string"),
        ("analysisDepth", False, "FormalAnalysisLevel"), ("method", False, "MethodVersionRef"),
        ("budget", False, "Record<string, number>"), ("allowedTools", False, "string[]"),
        ("allowedConnectorIds", False, "string[]"), ("idempotencyKey", False, "string"),
    )
    deep_result = (
        ("analysisRunId", False, "string"), ("runManifestId", False, "string"),
        ("runManifestHash", False, "string"), ("judgmentSetId", False, "string"),
        ("dissentRecordId", False, "string"), ("draftRecommendationId", False, "string"),
        ("unresolvedUnknownIds", False, "string[]"), ("validatorResults", False, "ValidatorResult[]"),
        ("qualityGateResultId", False, "string"), ("provenanceHash", False, "string"),
    )
    for name, expected in (("MethodVersionRef", method_ref), ("DeepAnalysisRequest", deep_request), ("DeepAnalysisResult", deep_result)):
        exact_interface(dm, name, expected)
        exact_interface(inv, name, expected)
        require(interface_fields(dm, name) == interface_fields(inv, name), f"06/26 {name} mismatch")
    require('export type FormalAnalysisLevel = "focused" | "full";' in dm, "06 FormalAnalysisLevel drift")
    require('type FormalAnalysisLevel = "focused" | "full";' in inv, "26 FormalAnalysisLevel drift")

    require('export type SourceScope = "pre_run" | "run_frozen";' in dm, "SourceScope missing")
    require("rawArtifactId?: string" in interface_body(dm, "SourceRecordBase"), "rawArtifactId must be optional")
    pre_source = interface_fields(dm, "PreRunSourceRecord")
    frozen_source = interface_fields(dm, "RunFrozenSourceRecord")
    require(("sourceScope", False, '"pre_run"') in pre_source, "pre-run source discriminator drift")
    require(("analysisRunId", True, "never") in pre_source, "pre-run source must forbid analysisRunId")
    for field in (
        ("sourceScope", False, '"run_frozen"'), ("analysisRunId", False, "string"),
        ("frozenFromSourceRecordId", False, "string"), ("frozenAt", False, "string"),
    ):
        require(field in frozen_source, f"RunFrozenSourceRecord missing {field}")
    require("export type SourceRecord = PreRunSourceRecord | RunFrozenSourceRecord;" in dm, "SourceRecord union drift")
    require("export type SourceSpan = PreRunSourceSpan | RunFrozenSourceSpan;" in dm, "SourceSpan union drift")

    require('export type WorkspaceRole = "owner" | "member";' in dm, "WorkspaceRole drift")
    require('export type WorkspaceCapability = "contribute" | "review" | "sign" | "manage_connectors";' in dm, "WorkspaceCapability drift")
    for name in ("User", "WorkspaceMembership", "UserSession"):
        interface_body(dm, name)
    require(("capabilities", False, "WorkspaceCapability[]") in interface_fields(dm, "WorkspaceMembership"), "membership capabilities missing")
    require(("revokedAt", True, "string") in interface_fields(dm, "UserSession"), "revocable session missing")

    signoff = (
        ("caseVersion", False, "number"), ("sourceAnalysisRunId", False, "string"),
        ("sourceReportArtifactId", False, "string"), ("sourceJudgmentSetId", False, "string"),
        ("sourceDissentRecordId", False, "string"), ("sourceCausalGraphId", True, "string"),
        ("sourceCausalGraphVersionId", True, "string"), ("sourceSimulationRunId", True, "string"),
        ("systemRecommendation", False, "SystemRecommendation"), ("selectedOptionId", False, "string"),
        ("decisionDraft", False, "string"), ("conditions", False, "string[]"),
        ("thresholds", False, "Threshold[]"), ("exitCriteria", False, "string[]"),
        ("actionItems", False, "ActionItem[]"), ("leadingIndicators", False, "LeadingIndicator[]"),
        ("acceptedUnknownIds", False, "string[]"), ("reviewDate", False, "string"),
    )
    exact_interface(dm, "SignoffPayload", signoff)
    request_fields = interface_fields(dm, "SignoffRequest")
    require(("payload", False, "SignoffPayload") in request_fields, "SignoffRequest payload missing")
    require(("payloadHash", False, "string") in request_fields, "SignoffRequest payloadHash missing")
    record_fields = interface_fields(dm, "DecisionRecord")
    for field in (
        ("payload", False, "SignoffPayload"), ("payloadHash", False, "string"),
        ("sourceJudgmentSetId", False, "string"), ("sourceDissentRecordId", False, "string"),
        ("systemRecommendation", False, "SystemRecommendation"),
    ):
        require(field in record_fields, f"DecisionRecord missing signed projection {field}")

    union_match = re.search(
        r"export type SystemRecommendation\s*=\s*(.*?)\n\s*;?\n\s*export interface Recommendation",
        dm, flags=re.DOTALL,
    )
    require(union_match is not None, "SystemRecommendation union missing")
    union_text = union_match.group(1)
    require('{ kind: "option"; optionId: string }' in union_text, "option branch missing")
    require('{ kind: "abstain"; reasonCodes: string[]; rationale: string }' in union_text, "abstain branch missing")
    require(("outcome", False, "SystemRecommendation") in interface_fields(dm, "Recommendation"), "Recommendation outcome missing")
    require(("outcome", False, "SystemRecommendation") in interface_fields(dm, "DraftRecommendation"), "DraftRecommendation outcome missing")

    api = require_text(
        PLAN / "10-api-and-events.md", "/signoff-requests/{signoffRequestId}/sign", "活动 session",
        "`sign` capability", "payloadHash", "原 SignoffPayload 与 payloadHash 原样复制",
    )
    require("/cases/{caseId}/decisions`" not in api, "direct create-decision endpoint remains")
    METRICS["deep_analysis"] = "06/26 exact"
    METRICS["signoff_fields"] = str(len(signoff))


def check_report_example() -> None:
    dm = read_text(PLAN / "06-data-model.md")
    pipeline = read_text(PLAN / "08-deep-research-pipeline.md")
    expected = tuple(field[0] for field in interface_fields(dm, "StructuredReport"))
    candidates: list[dict[str, Any]] = []
    for match in re.finditer(r"```json\s*\n(.*?)\n```", pipeline, flags=re.DOTALL):
        value = json.loads(match.group(1))
        if isinstance(value, dict) and "schemaVersion" in value and "recommendation" in value:
            candidates.append(value)
    require(len(candidates) == 1, f"expected one StructuredReport example, got {len(candidates)}")
    example = candidates[0]
    require(set(example) == set(expected), f"08 StructuredReport field drift: {sorted(set(example) ^ set(expected))}")
    recommendation = example.get("recommendation")
    require(isinstance(recommendation, dict), "report recommendation missing")
    outcome = recommendation.get("outcome")
    require(isinstance(outcome, dict) and outcome.get("kind") in {"option", "abstain"}, "report outcome invalid")
    METRICS["structured_report_fields"] = str(len(expected))

def active_documents() -> list[Path]:
    paths: list[Path] = []
    for path in sorted(PLAN.glob("[0-9][0-9]-*.md")):
        number = int(path.name[:2])
        if 1 <= number <= 24 or number == 26:
            paths.append(path)
    paths.extend((PLAN / "README.md", PLAN / "agent-work-manifest.yaml", REPO / "AGENTS.md"))
    return paths


def check_active_docs() -> None:
    legacy_ids = re.compile(r"\b(caseId|runId)\b")
    violations: list[str] = []
    for path in active_documents():
        for line_number, line in enumerate(read_text(path).splitlines(), 1):
            if legacy_ids.search(line):
                violations.append(f"{path}:{line_number}: {line.strip()}")
    require(not violations, "legacy wire IDs in active contracts:\n" + "\n".join(violations))

    workflow = read_text(PLAN / "07-agent-workflow.md")
    for fragment in ("$OutputEncoding", "Get-Content", "Set-Content", "Get-ChildItem", "'@ | py"):
        require(fragment not in workflow, f"07 contains PowerShell residue: {fragment}")
    require_text(
        PLAN / "09-simulation-engine.md", "relationshipQualityScore` 不得乘入上式",
        "delta_i(t) * p_ij * s_ij * m_ij * lambda", "`L < 1`", "`maxSteps`", "`epsilon`",
        "`inputHash`", "不得改变正式系统建议",
    )
    require_text(
        PLAN / "22-contract-generation-and-security-plan.md", "AES-256-GCM", "DNS rebinding",
        "pinned IP", "Postgres-backed 限流",
    )
    require_text(
        PLAN / "12-72-hour-execution-plan.md", "72 小时只承诺 **Hackathon Prototype Slice**",
        "Gate 0 未通过", "4 Agent/108 小时", "3 Agent/144 小时",
    )
    require_text(
        PLAN / "23-multi-agent-capacity-execution-plan.md", "6 Agent / 72h", "4 Agent / 108h", "3 Agent / 144h",
    )
    require_text(
        PLAN / "13-testing-and-acceptance.md", "test_no_run_no_report",
        "test_pre_run_source_freezes_into_run_scoped_source", "test_system_recommendation_abstains_on_fatal_path",
        "test_revoked_session_and_missing_sign_capability_rejected", "test_simulation_input_hash_and_replay_determinism",
    )
    METRICS["legacy_wire_ids"] = "0"


def norm_scope(pattern: str) -> str:
    return pattern.replace("\\", "/").strip("./")


def has_wildcard(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def prefix_before_wildcard(pattern: str) -> str:
    value = norm_scope(pattern)
    positions = [value.find(char) for char in "*?[" if char in value]
    end = min(positions) if positions else len(value)
    return value[:end].rstrip("/")


def covers(container: str, candidate: str) -> bool:
    container = norm_scope(container)
    candidate = norm_scope(candidate)
    if container == candidate:
        return True
    if container.endswith("/**"):
        prefix = container[:-3].rstrip("/")
        return candidate == prefix or candidate.startswith(prefix + "/")
    return not has_wildcard(candidate) and fnmatch.fnmatchcase(candidate, container)


def overlaps(left: str, right: str) -> bool:
    left = norm_scope(left)
    right = norm_scope(right)
    if covers(left, right) or covers(right, left):
        return True
    lp = prefix_before_wildcard(left)
    rp = prefix_before_wildcard(right)
    return bool(lp and rp and (lp == rp or lp.startswith(rp + "/") or rp.startswith(lp + "/")))


def github_slug(heading: str) -> str:
    value = re.sub(r"<[^>]+>", "", heading.strip().lower())
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"\s+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


def check_plan_anchor(plan_section: str) -> None:
    require("#" in plan_section, f"plan_section lacks anchor: {plan_section}")
    file_name, anchor = plan_section.split("#", 1)
    text = read_text(PLAN / file_name)
    slugs = {github_slug(match.group(1)) for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, flags=re.MULTILINE)}
    require(anchor in slugs, f"missing plan anchor: {plan_section}")


def check_manifest() -> None:
    data = yaml_load(PLAN / "agent-work-manifest.yaml")
    require(isinstance(data, dict), "agent manifest must be a mapping")
    owners = data.get("owners")
    tasks = data.get("tasks")
    require(isinstance(owners, dict) and set(owners) == OWNERS, f"owner set drift: {set(owners or {})}")
    require(isinstance(tasks, list), "manifest tasks missing")
    ids = [task.get("id") for task in tasks if isinstance(task, dict)]
    require(len(ids) == len(tasks), "every task needs an id")
    require(len(ids) == len(set(ids)), "duplicate task IDs")
    require(set(ids) == TASK_IDS, f"task set drift: {set(ids) ^ TASK_IDS}")
    by_id = {task["id"]: task for task in tasks}

    for task in tasks:
        owner = task.get("owner")
        require(owner in owners, f"{task['id']}: unknown owner {owner}")
        dependencies = task.get("depends_on", [])
        require(isinstance(dependencies, list), f"{task['id']}: depends_on must be a list")
        require(not (set(dependencies) - set(ids)), f"{task['id']}: missing dependency")
        require(task["id"] not in dependencies, f"{task['id']}: self dependency")
        check_plan_anchor(task.get("plan_section", ""))

        primary = task.get("write_scope", [])
        require(isinstance(primary, list) and primary, f"{task['id']}: empty write_scope")
        owner_scopes = owners[owner].get("write_scope", [])
        exclusions = owners[owner].get("exclusions", [])
        for scope in primary:
            require(any(covers(parent, scope) for parent in owner_scopes), f"{task['id']}: {scope} outside {owner}")
            require(not any(covers(item, scope) for item in exclusions), f"{task['id']}: {scope} excluded for {owner}")

        secondary = task.get("secondary_owner")
        secondary_scopes = task.get("secondary_write_scope", [])
        if secondary is None:
            require(not secondary_scopes, f"{task['id']}: secondary scope without owner")
        else:
            require(secondary in owners and secondary != owner, f"{task['id']}: invalid secondary owner")
            require(isinstance(secondary_scopes, list) and secondary_scopes, f"{task['id']}: empty secondary scope")
            allowed = owners[secondary].get("write_scope", [])
            denied = owners[secondary].get("exclusions", [])
            for scope in secondary_scopes:
                require(any(covers(parent, scope) for parent in allowed), f"{task['id']}: {scope} outside secondary {secondary}")
                require(not any(covers(item, scope) for item in denied), f"{task['id']}: {scope} excluded for secondary {secondary}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str, chain: tuple[str, ...] = ()) -> None:
        if task_id in visited:
            return
        require(task_id not in visiting, f"dependency cycle: {' -> '.join(chain + (task_id,))}")
        visiting.add(task_id)
        for dependency in by_id[task_id].get("depends_on", []):
            visit(dependency, chain + (task_id,))
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in ids:
        visit(task_id)
    require(len(visited) == len(ids), "DAG did not visit all tasks")

    require("task-19" in by_id["task-17"]["depends_on"], "Task 17 must depend on Task 19")
    require({"task-18a", "task-17", "task-19"}.issubset(by_id["task-18"]["depends_on"]), "Task 18 dependencies drift")
    require(set(by_id["task-19"]["depends_on"]) == {"task-19a", "task-19b", "task-19c", "task-19d"}, "Task 19 dependencies drift")

    slices = {
        "task-01w": ("web_ux", {"apps/web/**", "design/**", "scripts/snapshot_look.py"}),
        "task-14w": ("web_ux", {"apps/web/components/decisions/**", "apps/web/components/reviews/**", "apps/web/components/shell/CaseViewRouter.tsx"}),
        "task-18a": ("contract_lead", {"compose.yaml", "apps/web/Dockerfile", "services/api/Dockerfile", ".github/workflows/**", "THIRD_PARTY_NOTICES.md"}),
    }
    for task_id, (owner, scopes) in slices.items():
        task = by_id[task_id]
        require(task["owner"] == owner, f"{task_id} owner drift")
        require(scopes.issubset(set(task["write_scope"])), f"{task_id} scope drift")
    require(not any(scope.startswith("apps/web") or scope.startswith("design/") for scope in by_id["task-01"]["write_scope"]), "Task 1 owns Web/Look")
    require(not any("components/decisions" in scope or "components/reviews" in scope for scope in by_id["task-11"]["write_scope"]), "Task 11 owns Decision/Review")
    for task_id in ("task-19a", "task-19b", "task-19c", "task-19d", "task-19"):
        require("secondary_owner" not in by_id[task_id], f"{task_id} must not use secondary_owner")
    require("services/api/app/reports/publisher.py" in owners["case_api_data"].get("exclusions", []), "Case/API must exclude publisher")
    require("services/api/app/reports/**" in by_id["task-19c"]["write_scope"], "Task 19C must own reports")
    require(not any("reports" in scope for scope in by_id["task-19b"]["write_scope"]), "Task 19B must not own reports")

    model = data.get("ownership_model", {})
    require(model.get("task_scope_inherits_owner_exclusions") is True, "task exclusions must be inherited")
    reserved = model.get("reserved_scopes", [])
    require(isinstance(reserved, list) and reserved, "reserved scopes missing")
    for item in reserved:
        reserved_owner = item.get("owner")
        require(reserved_owner in owners, f"unknown reserved owner {reserved_owner}")
        for scope in item.get("paths", []):
            require(any(covers(parent, scope) for parent in owners[reserved_owner].get("write_scope", [])), f"reserved scope outside owner: {scope}")

    claims: list[tuple[str, str, str]] = []
    for task in tasks:
        claims.extend((task["id"], task["owner"], scope) for scope in task.get("write_scope", []))
        if task.get("secondary_owner"):
            claims.extend((task["id"], task["secondary_owner"], scope) for scope in task.get("secondary_write_scope", []))
    for index, (left_task, left_owner, left_scope) in enumerate(claims):
        for right_task, right_owner, right_scope in claims[index + 1:]:
            if left_owner == right_owner or not overlaps(left_scope, right_scope):
                continue
            left_denied = owners[left_owner].get("exclusions", [])
            right_denied = owners[right_owner].get("exclusions", [])
            carved = any(covers(item, right_scope) for item in left_denied) or any(covers(item, left_scope) for item in right_denied)
            require(carved, f"cross-owner overlap: {left_task}/{left_owner}:{left_scope} <-> {right_task}/{right_owner}:{right_scope}")

    gate = data.get("start_gates", {}).get("gate-0")
    require(isinstance(gate, dict), "gate-0 missing")
    require(set(gate.get("depends_on", [])) == {"task-01", "task-01w"}, "gate-0 dependencies drift")
    require(gate.get("required_before_capacity_clock") is True, "gate-0 must block capacity clock")
    profiles = data.get("capacity_profiles", {})
    expected_profiles = {
        "six_agent_72h": (6, 72, "hackathon_prototype"),
        "four_agent_108h": (4, 108, "full_mvp"),
        "three_agent_144h": (3, 144, "full_mvp"),
    }
    for name, expected in expected_profiles.items():
        profile = profiles.get(name, {})
        actual = (profile.get("slots"), profile.get("elapsed_hours"), profile.get("deliverable_scope"))
        require(actual == expected, f"capacity profile drift: {name}: {actual}")
    METRICS["owners"] = str(len(owners))
    METRICS["tasks"] = str(len(tasks))
    METRICS["dag"] = "acyclic"


def walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def resolve_pointer(document: Any, pointer: str, context: str) -> Any:
    if pointer in ("", "/"):
        return document
    require(pointer.startswith("/"), f"invalid JSON pointer in {context}: {pointer}")
    current = document
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            require(token.isdigit() and int(token) < len(current), f"unresolved pointer in {context}: {pointer}")
            current = current[int(token)]
        else:
            require(isinstance(current, dict) and token in current, f"unresolved pointer in {context}: {pointer}")
            current = current[token]
    return current


def outcome_kinds(schema: dict[str, Any], context: str) -> set[str]:
    branches = schema.get("oneOf")
    require(isinstance(branches, list) and len(branches) == 2, f"{context}: expected two outcome branches")
    kinds: set[str] = set()
    for branch in branches:
        kind = branch.get("properties", {}).get("kind", {}).get("const")
        require(isinstance(kind, str), f"{context}: branch lacks kind const")
        kinds.add(kind)
    return kinds


def prompt_metadata(path: Path) -> dict[str, Any]:
    match = re.match(r"^---\n(.*?)\n---\n", read_text(path), flags=re.DOTALL)
    require(match is not None, f"prompt frontmatter missing: {path}")
    value = yaml.safe_load(match.group(1))
    require(isinstance(value, dict), f"prompt frontmatter invalid: {path}")
    return value

def check_ways() -> None:
    require(LEGACY_WAY.is_dir(), "Ways 1.0.0 history missing")
    require(CURRENT_WAY.is_dir(), "Ways 1.1.0 package missing")
    manifest = yaml_load(CURRENT_WAY / "manifest.yaml")
    require(manifest.get("manifest_schema_version") == "1.0.0", "manifest schema version drift")
    require(manifest.get("version") == "1.1.0", "active method version drift")
    model_contract = manifest.get("model_contract", {})
    require(model_contract.get("formal_interface") == "DeepAnalysisRequest", "formal input drift")
    require(model_contract.get("formal_output") == "DeepAnalysisResult", "formal output drift")
    require(model_contract.get("chat_messages_primary_interface") is False, "chat became primary interface")
    exact_validators = tuple(manifest.get("quality_gates", {}).get("validator_contracts_exact", []))
    require(exact_validators == VALIDATORS, f"validator set/order drift: {exact_validators}")

    schemas_dir = CURRENT_WAY / "schemas"
    schema_paths = sorted(schemas_dir.glob("*.json"))
    require({path.name for path in schema_paths} == SCHEMA_FILES, "schema file set drift")
    by_path: dict[Path, dict[str, Any]] = {}
    by_id: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in schema_paths:
        document = json.loads(read_text(path))
        require(isinstance(document, dict), f"schema must be object: {path}")
        require(document.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"schema draft drift: {path}")
        schema_id = document.get("$id")
        require(isinstance(schema_id, str) and schema_id.endswith(":1.1.0"), f"schema ID drift: {path}: {schema_id}")
        require(schema_id not in by_id, f"duplicate schema ID: {schema_id}")
        by_path[path.resolve()] = document
        by_id[schema_id] = (path.resolve(), document)

    registry = manifest.get("schemas", {})
    require(isinstance(registry, dict) and len(registry) == len(schema_paths), "manifest schema registry drift")
    for descriptor in registry.values():
        require(isinstance(descriptor, dict), "schema descriptor invalid")
        path = (CURRENT_WAY / descriptor.get("path", "")).resolve()
        require(path in by_path, f"manifest schema path missing: {path}")
        require(descriptor.get("id") == by_path[path].get("$id"), f"schema id/path mismatch: {path}")

    for path, document in by_path.items():
        for value in walk(document):
            if not isinstance(value, dict) or "$ref" not in value:
                continue
            ref = value["$ref"]
            require(isinstance(ref, str), f"non-string $ref: {path}")
            require(":1.0.0" not in ref, f"stale schema ref: {path}: {ref}")
            fragment = ""
            if ref.startswith("#"):
                target = document
                fragment = ref[1:]
            elif ref.startswith("urn:"):
                base, separator, tail = ref.partition("#")
                require(base in by_id, f"unresolved schema URN: {path}: {base}")
                target = by_id[base][1]
                fragment = tail if separator else ""
            elif ref.startswith(("http://", "https://")):
                raise ContractFailure(f"network schema ref forbidden: {path}: {ref}")
            else:
                file_part, separator, tail = ref.partition("#")
                target_path = (path.parent / file_part).resolve()
                require(target_path in by_path, f"unresolved relative ref: {path}: {ref}")
                target = by_path[target_path]
                fragment = tail if separator else ""
            if fragment:
                resolve_pointer(target, fragment, f"{path}: {ref}")

    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        METRICS["jsonschema"] = "not-installed; structural+ref validation used"
    else:
        for path, document in by_path.items():
            try:
                Draft202012Validator.check_schema(document)
            except Exception as exc:
                raise ContractFailure(f"metaschema validation failed: {path}: {exc}") from exc
        METRICS["jsonschema"] = "Draft202012Validator.check_schema"

    deep_schema = by_path[(schemas_dir / "deep-analysis-result.schema.json").resolve()]
    deep_fields = [field[0] for field in interface_fields(read_text(PLAN / "06-data-model.md"), "DeepAnalysisResult")]
    require(deep_schema.get("required") == deep_fields, "DeepAnalysisResult required fields drift")
    require(set(deep_schema.get("properties", {})) == set(deep_fields), "DeepAnalysisResult properties drift")
    require(deep_schema.get("additionalProperties") is False, "DeepAnalysisResult must be closed")
    validator_items = deep_schema["properties"]["validatorResults"]
    require((validator_items.get("minItems"), validator_items.get("maxItems")) == (9, 9), "DeepAnalysisResult validator count drift")

    draft = by_path[(schemas_dir / "draft-recommendation.schema.json").resolve()]
    focused = by_path[(schemas_dir / "focused-result.schema.json").resolve()]
    require(outcome_kinds(draft["properties"]["outcome"], "DraftRecommendation") == {"option", "abstain"}, "Draft outcome drift")
    focused_outcome = focused["$defs"]["recommendation"]["properties"]["outcome"]
    require(outcome_kinds(focused_outcome, "Focused Recommendation") == {"option", "abstain"}, "Focused outcome drift")
    require("recommendedOptionId" not in json.dumps(draft), "DraftRecommendation still has recommendedOptionId")
    require("primaryOptionId" not in json.dumps(focused), "Focused Recommendation still has primaryOptionId")
    structured = by_path[(schemas_dir / "structured-report.schema.json").resolve()]
    expected_ref = "urn:ludus:method:hardtech-market-direction:focused-result:1.1.0#/$defs/recommendation"
    require(structured.get("properties", {}).get("recommendation", {}).get("$ref") == expected_ref, "StructuredReport recommendation ref drift")

    aggregate = by_path[(schemas_dir / "validator-aggregate.schema.json").resolve()]
    aggregate_results = aggregate.get("properties", {}).get("results", {})
    require(tuple(aggregate_results.get("required", [])) == VALIDATORS, "validator aggregate required drift")
    require(set(aggregate_results.get("properties", {})) == set(VALIDATORS), "validator aggregate properties drift")

    diagnostic = yaml_load(CURRENT_WAY / "diagnostic-questions.yaml")
    quality = yaml_load(CURRENT_WAY / "quality-gates.yaml")
    require(diagnostic.get("method_version") == "1.1.0", "diagnostic method_version drift")
    require(quality.get("method_version") == "1.1.0", "quality-gates method_version drift")
    require("abstain" in read_text(CURRENT_WAY / "quality-gates.yaml"), "quality gates lack abstain")

    prompt_paths = sorted((CURRENT_WAY / "prompts").rglob("*.md"))
    require(len(prompt_paths) == 10, f"expected 10 prompts, got {len(prompt_paths)}")
    for path in prompt_paths:
        metadata = prompt_metadata(path)
        require(metadata.get("version") == "1.1.0", f"prompt version drift: {path}")
        for value in walk(metadata):
            if isinstance(value, str) and value.startswith("urn:ludus:method:"):
                require(value.endswith(":1.1.0"), f"prompt schema ref drift: {path}: {value}")
    synthesis = read_text(CURRENT_WAY / "prompts" / "synthesis.md")
    require("outcome.kind=abstain" in synthesis and "不得使用空 option ID" in synthesis, "synthesis abstain contract missing")

    for path in sorted((CURRENT_WAY / "evals").glob("*.json")):
        json.loads(read_text(path))
    skill_dirs = sorted(path for path in RESEARCH.iterdir() if path.is_dir() and (path / "SKILL.md").is_file())
    require(len(skill_dirs) == 31, f"expected 31 research Skills, got {len(skill_dirs)}")
    capability = read_text(CURRENT_WAY / "CAPABILITY-MAP.md")
    section = re.search(r"## 31 个 Skill 全量映射\s*(.*?)(?:\n固定计数：)", capability, flags=re.DOTALL)
    require(section is not None, "31-Skill section missing")
    rows = re.findall(r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|", section.group(1), flags=re.MULTILINE)
    require(len(rows) == 31, f"expected 31 capability rows, got {len(rows)}")
    mapped = {item.rsplit("@", 1)[0] for item, _ in rows}
    actual = {path.name for path in skill_dirs}
    require(mapped == actual, f"Skill map drift: missing={sorted(actual - mapped)} extra={sorted(mapped - actual)}")
    counts = Counter(status.strip() for _, status in rows)
    expected_counts = {"P0 直接编译": 13, "能力已被其他合同吸收": 7, "延后到下一方法包": 8, "仅参考": 1, "禁用": 2}
    require({key: counts.get(key, 0) for key in expected_counts} == expected_counts, f"Skill disposition drift: {counts}")

    METRICS["ways"] = "1.1.0 active / 1.0.0 historical"
    METRICS["validators"] = str(len(VALIDATORS))
    METRICS["schemas"] = str(len(schema_paths))
    METRICS["skills"] = "31/31 dispositions=13/7/8/1/2"


def link_targets(path: Path, text: str) -> Iterable[tuple[str, Path]]:
    for match in re.finditer(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", text):
        raw = match.group(1).strip()
        if raw.startswith("<") and ">" in raw:
            raw = raw[1:raw.index(">")]
        else:
            raw = raw.split()[0]
        if not raw or raw.startswith(("#", "http://", "https://", "mailto:", "data:", "app://")):
            continue
        target = unquote(raw.split("#", 1)[0].split("?", 1)[0])
        if not target or re.match(r"^[A-Za-z]:[\\/]", target):
            continue
        yield raw, (path.parent / target).resolve()


def check_integrity() -> None:
    markdown: list[Path] = []
    for root in (PLAN, CURRENT_WAY):
        markdown.extend(sorted(root.rglob("*.md")))
    for path in markdown:
        text = read_text(path)
        open_fence: tuple[str, int] | None = None
        for line_number, line in enumerate(text.splitlines(), 1):
            match = re.match(r"^\s*(```+|~~~+)(.*)$", line)
            if not match:
                continue
            marker = match.group(1)[0]
            if open_fence is None:
                open_fence = (marker, line_number)
            elif marker == open_fence[0]:
                open_fence = None
        require(open_fence is None, f"unclosed Markdown fence: {path}:{open_fence[1] if open_fence else '?'}")
        for number, match in enumerate(re.finditer(r"```json\s*\n(.*?)\n```", text, flags=re.DOTALL), 1):
            try:
                json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                raise ContractFailure(f"invalid JSON fence: {path} block {number}: {exc}") from exc
        for raw, target in link_targets(path, text):
            require(target.exists(), f"broken local link: {path}: {raw} -> {target}")

    yaml_paths = sorted(PLAN.rglob("*.yaml")) + sorted(PLAN.rglob("*.yml"))
    yaml_paths += sorted(CURRENT_WAY.rglob("*.yaml")) + sorted(CURRENT_WAY.rglob("*.yml"))
    for path in yaml_paths:
        yaml_load(path)
    json_paths = sorted(CURRENT_WAY.rglob("*.json"))
    for path in json_paths:
        json.loads(read_text(path))
    METRICS["markdown"] = str(len(markdown))
    METRICS["yaml"] = str(len(yaml_paths))
    METRICS["json"] = str(len(json_paths))


def run_check(name: str, function: Any, failures: list[str]) -> None:
    try:
        function()
    except Exception as exc:
        failures.append(f"[{name}] {exc}")
        print(f"FAIL {name}: {exc}", file=sys.stderr)
    else:
        print(f"PASS {name}")


def main() -> int:
    checks = (
        ("look-v7", check_look),
        ("canonical-data", check_canonical_data),
        ("structured-report-example", check_report_example),
        ("active-docs-and-high-risk", check_active_docs),
        ("agent-manifest", check_manifest),
        ("ways-package", check_ways),
        ("document-integrity", check_integrity),
    )
    failures: list[str] = []
    for name, function in checks:
        run_check(name, function, failures)
    if failures:
        print(f"decision-os-contracts: FAIL ({len(failures)} check groups)", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("decision-os-contracts: PASS")
    for key in sorted(METRICS):
        print(f"{key}={METRICS[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
