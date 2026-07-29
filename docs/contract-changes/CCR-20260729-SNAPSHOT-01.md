# CCR-20260729-SNAPSHOT-01 — Charter snapshot fields become server-authoritative

- Status: proposed (implemented on `codex/alpha-remaining-fixes`)
- Date: 2026-07-29 (Asia/Shanghai)
- Owner: backend/runtime lane
- Affected surface: `POST /api/workspaces/{workspaceId}/cases/{decisionCaseId}/analysis-charters`
  and `POST /api/workspaces/{workspaceId}/analysis-charters/{charterId}/replacements`

## Problem

`AnalysisCharter` is supposed to freeze WHAT was analysed, so a report can later
be proven to rest on exactly that input (AGENTS.md section 5: "Charter 必须冻结
问题、期限、主体与档案快照…"; section 16 requires the change to be demonstrable
without claiming more than it does).

In practice all four snapshot fields were whatever the caller sent, and the
shipped web client sent `sha256:` + 32 random bytes for each:

```ts
caseSnapshotHash: `sha256:${randomHex(32)}`,
dossierSnapshotHash: `sha256:${randomHex(32)}`,
```

So the audit chain was shape-correct and meaning-free:

- two runs over identical case content carried unrelated hashes, so nothing
  downstream could recognise "same input";
- two runs over genuinely different content were equally unrelated, so nothing
  could detect "the input changed under me";
- `caseVersion` / `dossierSnapshotVersion` were hard-coded `1` regardless of the
  case's real version.

A traceability claim that cannot fail is not a traceability claim.

## Change

The server freezes these four fields from the database; the request values are
ignored (older callers may still send them).

| Field | Before | After |
|---|---|---|
| `caseVersion` | caller | `decision_cases.current_version` |
| `caseSnapshotHash` | caller | SHA-256 over canonical JSON of the case's decision-defining fields |
| `dossierSnapshotVersion` | caller | highest `version` among CONFIRMED dossier entries in scope (1 when empty) |
| `dossierSnapshotHash` | caller | SHA-256 over canonical JSON of those entries |

Determinism rules (`services/api/app/analyses/snapshots.py`):

- only `CONFIRMED` entries participate — a candidate must not change what a
  frozen charter claims to have analysed;
- subject-scoped AND this-case-scoped entries participate, because the analysis
  genuinely reads both; a sibling case's case-scoped entries never do;
- entries are ordered by id and JSON is emitted with sorted keys and no
  whitespace, so identical content always hashes identically.

A replacement (amendment) draft re-freezes rather than inheriting the superseded
charter's snapshot: an amendment exists *because* the frozen input changed, so
inheriting would make the new run claim to have analysed the old content.

## Compatibility

- **Request shape**: the four fields move from required to ignored. This is a
  relaxation — every previously valid request stays valid.
- **Response shape**: unchanged; the same field names now carry real values.
- **OpenAPI**: unchanged. These handlers take a free-form JSON body, so the
  generated document has no schema for them; verified by exporting both trees'
  OpenAPI and diffing — 69 operations both sides, zero schema delta
  (`CONTRACT_NEUTRAL`).
- **Errors/events/enums**: unchanged. No migration.
- **Not covered here**: `methodContentHash` is still caller-supplied. Making it
  authoritative requires reading the published method pack through the shipped
  loader and belongs to the Ways/Router lane; it is recorded as an open item
  rather than half-done here.

## Test impact (disclosed)

`app/analyses/tests/test_analysis_http_handlers.py::test_create_charter_missing_fields`
asserted that omitting `caseSnapshotHash` produced a `missingFields` entry. That
assertion is false by construction after this change, so it was revised to omit
`decisionSubjectId` instead, keeping the multi-field shape of the assertion.

New battery: `app/analyses/tests/test_traceability_and_recovery.py` pins
determinism, content binding, confirmed-only participation, caller values being
ignored, the fields being optional, and two charters over unchanged content
sharing one hash.

## Verification

- owner suite `app/analyses/tests`: 226 passed
- canonical suite `services/api/tests`: 574 passed (= baseline)
- `ruff` + `compileall` clean; OpenAPI `CONTRACT_NEUTRAL` vs `main`
