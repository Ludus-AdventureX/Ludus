# CCR-20260725-ANALYSIS-01 — Addendum A1: Task 9/10 Contract Gap Reconciliation

- Date: 2026-07-25 (Asia/Shanghai)
- Adjudicator: Contract/Mainline Lead (contract_lead)
- Status: ACCEPTED (formal addendum to CCR-20260725-ANALYSIS-01)
- Baseline adjudicated against: remote main `4508b3059e1a71f62f90bdabcfb7a36cfc50cac4` (live-verified).
- Trigger: full-chain accumulated pending ruling items from Task 8 r1 handoff (§5), Task 9 r1 handoff (§5-6), r2 QA disclosure (ACCEPT, pending contract ratification), and r3 QA-hard-assertion-locked fixes — consolidated into this single addendum A1.

Input evidence:

- CCR body: `docs/product-plan/docs/contract-changes/CCR-20260725-ANALYSIS-01.md` (live on main @ 4508b30)
- Task 9 r1 handoff: `docs/handoffs/TASK_09_ANALYSIS_RUNTIME_R1_HANDOFF.md` §5-6 (branch `codex/task-09-analysis-runtime-r1`)
- Task 8 r1 handoff: `docs/handoffs/TASK_08_EVIDENCE_LEDGER_R1_HANDOFF.md` §5 (branch `codex/task-08-evidence-ledger-r1` @ c599030)
- QA r2 report + r3 closure: `docs/handoffs/QA_TASK_09_IDEMPOTENCY_WIRE_R2_REPORT.md` (branch `codex/qa-task-09-idempotency-wire-r2` @ 78c3ce6)
- 06-data-model.md / 10-api-and-events.md (live on main @ 4508b30)
- Format precedent: `CCR-20260724-SIM-01-ADDENDUM-A1.md`

Legend used below for every ruling:

- **REAFFIRM** — already canonical; no text change needed.
- **NEW** — adjudicated here; the named canonical subsection is amended in this same commit.
- **IMPLEMENTATION_FREE** — deliberately NOT frozen; implementers choose.
- **DEFERRED-to-A3** — belongs to a later integration/mounting wave; ruling preserves the gap with explicit A3 input.

---

## A1-1. Event/enum promotion to app.types — IMPLEMENTATION_FREE (DB-first, code follow-up in A3)

**Gap:** AnalysisEventCategory (5 values), AnalysisEventType (20 values), ResearchPacket.role, InterventionResult (`resolution`|`amendment`), RunResolution.kind (3 kinds), CharterFrozenField (11 field names), AnalysisCharter.status (4 values) — all have canonical literal sets in 06-data-model.md but no corresponding Python `app.types` enums. Task 9 r1 handoff §5 item 1 reports they are persisted "per the SIM-02A precedent (CHECK strings; PG enums for status/role columns without parallel Python StrEnums)".

**Evidence:**
- 06-data-model.md L465-476: `CharterFrozenField` type with exactly 11 string literal members.
- 06-data-model.md L28 (AnalysisCharter.status in the data-model table): `draft | awaiting_confirmation | confirmed | superseded`.
- 06-data-model.md L31-33 (AnalysisRunStatus): 10 enum values, `types.py` has `AnalysisRunStatus` enum — this one IS promoted.
- 06-data-model.md L149-157 (AnalysisEventCategory + AnalysisEventType): five categories + twenty types.
- 10-api-and-events.md L424: "事件只使用 `06-data-model.md` 的一套合同".
- Task 9 r1 handoff §5 item 1: "CCR requested to promote them."

**Ruling:** The DB-layer constraint (CHECK strings + PG enums for status columns) is already canonical and sufficient for runtime correctness. Promotion to `app.types` Python enums is a code-level change that requires coordinated updates across `app/analyses/`, `app/evidence/`, and `app/strategic_lenses/` — not a docs-only lane action. The DB-first posture is **canonically valid**: PG enums provide type safety and CHECK constraints enforce the literal sets at the persistence boundary exactly as the SIM-02A precedent established. Python enum promotion is **IMPLEMENTATION_FREE** for the DB layer but MUST be completed before the A3 integration wave publishes routes, as consumers of `app.types` enums (frontend contract generation, API serialization) require the promoted types. Execution owner: **A3 integration lane**.

---

## A1-2. RunManifest storage — REAFFIRM

**Gap:** 06-data-model.md defines the `RunManifest` interface but no dedicated storage decision. Task 9 r1 handoff §5 item 2 reports the owner reused the pre-existing `analysis_runs.run_manifest_id` and `analysis_runs.run_manifest_hash` columns; no new table was created.

**Evidence:**
- 06-data-model.md L2023-2026: `DeepAnalysisResult.runManifestId: string` + `runManifestHash: string` — both fields exist on the canonical result interface.
- Task 9 r1 handoff §1 (models.py): `analysis_runs` ORM consumed as-is from contract_lead, columns pre-existing.
- Task 9 r1 handoff §5 item 2: "recorded, fail-closed (no invented table)."

**Ruling:** **REAFFIRM.** The `run_manifest_id`/`run_manifest_hash` columns are the canonical storage surface; no separate manifest table is required. The RunManifest is a derived/computed artifact from the frozen Run state, not a separately versioned entity. If a future CCR requires a dedicated `run_manifests` table (e.g., cross-run manifest comparison), it must arrive as a new migration, never as an in-place rewrite.

---

## A1-3. Heartbeat timeout canonical value — IMPLEMENTATION_FREE

**Gap:** Heartbeat timeout has no canonical value in any contract document. Task 9 r1 handoff §5 item 4 reports default 120s, injectable per call.

**Evidence:**
- CCR-20260725-ANALYSIS-01 §1.5: "Heartbeat interval, claim primitive (advisory lock vs FOR UPDATE SKIP LOCKED), and progress-value granularity: **IMPLEMENTATION_FREE**".
- Task 9 r1 handoff §5 item 4: "Heartbeat timeout value is not specified canonically; default 120s (DEFAULT_HEARTBEAT_TIMEOUT), injectable per call."
- 06-data-model.md L451: `heartbeatAt?: string` — only the persisted timestamp is canonical, not the interval.

**Ruling:** **IMPLEMENTATION_FREE.** The timeout interval is an operational parameter, not a contract surface. The 120s default is a reasonable implementation choice and is injectable — no canonical text amendment needed. If production tuning reveals a need for a hard ceiling, that is a future ops-config CCR.

---

## A1-4. Charter/Run HTTP endpoint mounting — DEFERRED-to-A3

**Gap:** 10-api-and-events.md L65-75 freezes the full set of Charter/Run HTTP endpoints (create, PATCH, confirm, replacements, runs, SSE, resolutions, cancel), but no router is mounted in Task 9's delivery. Task 9 r1 handoff §5 item 3 + §6 both confirm: routers are "unmounted by design" and mounting rights "stay with the integration layer."

**Evidence:**
- 10-api-and-events.md L65-75: endpoint table with full path set.
- Task 9 r1 handoff §5 item 3: "Charter/Run creation HTTP endpoints … belong to the mounting/integration wave; this lane ships the domain/repository layer they will call. SSE/resolutions/cancel routers stay unmounted until that CCR."
- Task 9 r1 handoff §6: "Routers unmounted by design ⇒ no OpenAPI/TS change; ready_for_public_route = NO."

**Ruling:** **DEFERRED-to-A3.** All endpoint paths are already canonical in 10-api-and-events.md. The mounting act (router registration in `app/main.py`, OpenAPI generation, TS contract output) belongs to the A3 integration wave. The A3 lane receives: (a) the full endpoint path table from 10-api, (b) the domain/repository layer from Task 9, (c) the mounted `app/evidence/routes.py` from Task 8 (currently relative/unmounted). No contract text change needed.

---

## A1-5. Idempotency-Key internal-field vs HTTP-wire layering — NEW (ratification)

**Gap:** The original CCR text "Idempotency-Key 移除 body 字段" was interpreted by some as requiring deletion of `AnalysisRun.idempotencyKey` and `DeepAnalysisRequest.idempotencyKey` from 06-data-model.md. The r2 fast-fix kept both fields as canonical internal run/worker contract fields and enforced the HTTP-wire intent through a "body-smuggled key ⇒ 422" guard. QA r2 report adjudication item 1 ACCEPT-ed this layering; this addendum ratifies it as canonical.

**Evidence:**
- 06-data-model.md L450: `idempotencyKey: string;` on `AnalysisRun` — canonical internal field.
- 06-data-model.md L2020: `idempotencyKey: string;` on `DeepAnalysisRequest` — canonical internal field.
- CCR-20260725-ANALYSIS-01 §2.2: "Same Idempotency-Key + same normalized body ⇒ replay … Key format/length validation: IMPLEMENTATION_FREE".
- QA r2 report Adjudication 1: "The canonical-internal vs HTTP-wire layering therefore stands; the wire-side intent is enforced by the 'body-smuggled key ⇒ 422' guard."
- Task 9 idempotency-wire-fast-fix: `test_analysis_idempotency_wire.py` green (11/11), body-smuggled key yields 422.

**Ruling:** **NEW — the layering is canonically ratified.** `AnalysisRun.idempotencyKey` and `DeepAnalysisRequest.idempotencyKey` are canonical **internal** fields used for run/worker lifecycle correlation (creation-time key propagation, heartbeat association, worker claim deduplication). The HTTP wire surface does NOT accept `idempotencyKey` in the request body; any body carrying it MUST fail closed with 422. The two layers coexist: the internal field is a persistence/worker contract; the HTTP header is the caller-facing idempotency vehicle. Canonical text amendment: 06-data-model.md receives a layering declaration (sync SA1 below).

---

## A1-6. eventId on fresh resolution success — NEW (ratification)

**Gap:** CCR §2.1 freezes the resolution success envelope as `{ ok, data: { analysisRunId, classification, resolutionId, status, resumedFrom }, eventId }`. The Task 9 r1 implementation omitted `eventId` from the fresh success response (it was present in the replay path). The r2 fast-fix added it; byte-identical fresh/replay equivalence was verified. QA r2 report Adjudication item 2 ACCEPT-ed this; this addendum ratifies it.

**Evidence:**
- CCR-20260725-ANALYSIS-01 §2.1: "Success envelope frozen as documented: `{ ok, data: { analysisRunId, classification: { classificationId, result, changedFrozenFields }, resolutionId, status, resumedFrom }, eventId }`."
- 10-api-and-events.md L978-993: the post-S4 synced success envelope already includes `"eventId": "evt_run_resumed"`.
- QA r2 report Adjudication 2: "Fresh/replay equivalence verified: owner test asserts replayed data and eventId equal the original byte-for-byte."
- `test_analysis_idempotency_wire.py` (11/11 green): replay returns identical `eventId`.

**Ruling:** **NEW — ratified.** The fresh resolution success response MUST include `eventId`. The 10-api-and-events.md example (L978-993) already reflects this, as applied by CCR sync S4. No additional text amendment needed; this item is a ratification of the S4 sync already on main.

---

## A1-7. Amendment persistence timing: commit-before-raise — NEW (canonical timing)

**Gap:** CCR §2.3 freezes "server FIRST persists an append-only RunInterventionClassification" before returning 409. The r1 implementation raised the 409 before committing, causing the classification row and `analysis.amendment_required` event to be rolled back under production session lifecycle. The r3 fast-fix (`codex/task-09-amendment-durability-fast-fix` @ 628f672) fixed this: classification AND event are committed before `RunAmendmentRequired` is raised. QA-P1 was promoted from xfail to hard assertion and passes.

**Evidence:**
- CCR-20260725-ANALYSIS-01 §2.3: "server FIRST persists an append-only RunInterventionClassification. Only when changedFrozenFields == [] … does a RunResolution get appended."
- QA r2 report QA-P1: "the route raises before any commit; under the production get_session lifecycle the classification row AND the analysis.amendment_required event are rolled back and lost."
- QA r3 closure: "Owner r3 fast-fix … 628f672 … QA-P1 probe promoted to HARD assertion and passes."
- `test_amendment_classification_is_durable_under_production_session`: xfail → green.

**Ruling:** **NEW — canonical timing ratified.** The amendment rejection path's order of operations is now frozen as: (1) classify the payload, (2) persist `RunInterventionClassification` row with `result: "amendment"`, (3) persist `analysis.amendment_required` event, (4) commit the transaction, (5) raise `RUN_AMENDMENT_REQUIRED` 409. The two persisted rows (classification + event) are durable regardless of the caller's handling of the 409. Canonical text amendment: 10-api-and-events.md amendment paragraph receives a timing clause (sync SA2 below).

---

## A1-8. Idempotency race loser replay semantics — NEW (canonical semantics)

**Gap:** CCR §2.2 states same key + same body ⇒ replay always. In a true dual-connection race, the loser that passed the idempotency pre-check before the winner committed re-reads a resumed run and answers 409 `ANALYSIS_RUN_NOT_RESUMABLE` — failing the "always replay" guarantee (QA-P2). The r3 fast-fix (`codex/task-09-amendment-durability-fast-fix` @ 628f672) added a re-check: on `RunNotResumable`, the handler re-queries the idempotency record; a winner hit triggers replay of the winner's success (double 200, exactly one resolution row, `meta.idempotencyReplay: true` on the loser's response). Same key + different body still yields 409 `IDEMPOTENCY_CONFLICT`. QA-P2 promoted from xfail to hard assertion and passes.

**Evidence:**
- CCR-20260725-ANALYSIS-01 §2.2: "Same Idempotency-Key + same normalized body ⇒ replay of the original success … same key + different body ⇒ IDEMPOTENCY_CONFLICT 409."
- QA r2 report QA-P2: "In a true dual-connection race the loser … re-reads a resumed run and answers 409 ANALYSIS_RUN_NOT_RESUMABLE … the non-negotiable invariants (exactly one resolution row, winner 200, loser answers a documented code) hold."
- QA r3 closure: "QA-P2 probe promoted to HARD assertion and passes."
- `test_dual_connection_same_key_race_loser_replays_strict_ccr`: xfail → green.
- `test_dual_connection_same_key_race_appends_exactly_one_resolution`: always green.

**Ruling:** **NEW — canonical race-loser semantics ratified.** The idempotency replay guarantee is now race-safe: under any connection-level race condition, the same key + same body ALWAYS replays the winner's success (double 200, exactly one resolution row, `meta.idempotencyReplay: true` on the loser). The mechanism — `RunNotResumable` handler re-checks the idempotency record before answering — is **IMPLEMENTATION_FREE** in its exact form but the semantic guarantee is canonical. Canonical text amendment: 10-api-and-events.md idempotency section receives the race-safety clause (sync SA3 below).

---

## A1-9. Evidence read API paths — DEFERRED-to-A3

**Gap:** 10-api-and-events.md contains no evidence read API paths (detail, quality, provenance, direction, same-source group, run evidence list, conflict list). Task 8 shipped an unmounted `app/evidence/routes.py` with internal DTOs (`schemas_api.py`), but the paths are not canonicalized. Task 8 r1 handoff §5 item 1: "Evidence read API paths are absent from 10-api-and-events.md. … CCR needed before mounting."

**Evidence:**
- 10-api-and-events.md L44-80: full endpoint table — no evidence read paths (no `/evidence/` or `/retrieval-tasks/` entries).
- 10-api-and-events.md: evidence-related text only in file-upload (L456-469) and data-model references; no dedicated evidence API subsection.
- Task 8 r1 handoff §5 item 1: "conflict/provenance query layer is therefore delivered as a relative, UNMOUNTED router with internal DTOs only."
- Task 8 r1 handoff §1: `app/evidence/routes.py` — "relative and NOT mounted"; `app/evidence/schemas_api.py` — "camelCase CanonicalModel views (NOT exported to generated contracts)."
- QA Phase A verdict: PASS, with the unmounted-router state accepted as contract-mandated.

**Ruling:** **DEFERRED-to-A3.** The evidence read API surface is a distinct contract surface from the analysis run API. The A3 lane receives the following as裁决输入: (a) the proposed path set and wire shapes in `app/evidence/schemas_api.py` (evidence detail, quality assessment, provenance chain, evidence direction, same-source group, run evidence list, conflict list), (b) the unmounted `app/evidence/routes.py`, (c) the canonical `EvidenceItem`/`QualityAssessment`/`RetrievalTask`/`RawArtifact` interfaces from 06-data-model.md L661-700. The A3 lane MUST produce a CCR adding the evidence read paths to 10-api-and-events.md before mounting. Until that CCR lands, the evidence router stays unmounted — this is the contract-mandated state.

---

## A1-10. Evidence enum sets (SourceGrade, verdict, retrieval_task_status, etc.) — IMPLEMENTATION_FREE (same logic as A1-1)

**Gap:** `SourceGrade` (L1-L6), `EvidenceVerdict` (four-tier), `RetrievalTaskStatus`, `FreshnessStatus` (fresh|aging|stale|unknown), `stableToolName` — all have canonical literal sets in 06-data-model.md but no `app.types` Python enums. Task 8 r1 handoff §5 item 2: "Persisted per the SIM-02A response_kind precedent (CHECK-constrained strings; retrieval_task_status as a PG enum from the canonical tuple). CCR requested to promote these sets into app.types."

**Evidence:**
- 06-data-model.md L670: `sourceGrade: "L1_primary" | "L2_reputable" | "L3_industry" | "L4_general" | "L5_opinion" | "L6_unverified"` — canonical six-tier literal.
- 06-data-model.md L635: `verdict: EvidenceVerdict` — the four-tier verdict type.
- 06-data-model.md L678: `freshnessStatus: "fresh" | "aging" | "stale" | "unknown"` — canonical four-value literal.
- Task 8 r1 handoff §2: migration creates PG enums `evidence_verdict` and `retrieval_task_status`.
- Task 8 r1 handoff §5 item 2: CCR requested.

**Ruling:** **IMPLEMENTATION_FREE (DB-first, same logic as A1-1).** The DB-layer constraint (CHECK strings + PG enums) is already canonical and sufficient. `SourceGrade` and `FreshnessStatus` are wire literal unions (not PG enums), which matches the pattern established by `CharterFrozenField` and `AnalysisEventCategory` — CHECK-constrained strings at the persistence boundary, TypeScript literal unions on the wire. Python enum promotion to `app.types` is IMPLEMENTATION_FREE for the DB layer but MUST be completed before A3 mounts the evidence read routes (same execution owner as A1-1: A3 integration lane).

---

## Canonical text synchronization performed in this commit

Each amendment below is applied verbatim to the named subsection — nothing else in those documents is touched.

- **SA1** `06-data-model.md`, after the `AnalysisRun` interface closing brace (L463 `}`) and before `export type CharterFrozenField` (L465), insert:

  "`AnalysisRun.idempotencyKey` 与 `DeepAnalysisRequest.idempotencyKey` 是 canonical **内部**字段（run/worker 生命周期关联），不属于 HTTP wire 请求体；HTTP 面以 `Idempotency-Key` header 为载体，请求体夹带 `idempotencyKey` 字段的请求必须返回 422（CCR-20260725-ANALYSIS-01-ADDENDUM-A1）。"

- **SA2** `10-api-and-events.md`, amendment paragraph (after "服务端保存 `result == amendment` 的 classification，不创建 resolution" in L998), append:

  "分类与 `analysis.amendment_required` 事件先于 409 响应提交（CCR-20260725-ANALYSIS-01-ADDENDUM-A1）：持久化行在调用方收到错误前已 commit，不因 HTTP 响应状态回滚。"

- **SA3** `10-api-and-events.md`, 幂等 section (after "不得用 `ANALYSIS_RUN_ALREADY_ACTIVE` 表示幂等命中" in L938), append:

  "竞争安全保证（CCR-20260725-ANALYSIS-01-ADDENDUM-A1）：任意连接级竞争下，同一 key + 同一 body 始终重放胜者成功——双 200、恰好一条 resolution 行、败者响应携带 `meta.idempotencyReplay: true`；同一 key 不同 body 仍返回 `IDEMPOTENCY_CONFLICT` 409。"

---

## Canonical Impact

- 06-data-model.md: SA1 (one paragraph after AnalysisRun interface).
- 10-api-and-events.md: SA2 (one sentence, amendment paragraph), SA3 (one paragraph, 幂等 section).
- Event/error/status impact: no new error codes; no enum value changes; no event category/type changes. The SA2 timing clause and SA3 race-safety clause are semantic clarifications, not surface changes.

## Compatibility

- Backward compatible: yes — all Task 9 r3 lanes already implement the ratified behaviors; this addendum records the contract state, it does not change it.
- Migration required: none.
- Fixture migration: none.
- Generated client impact: none (SA1-SA3 are contract clarifications, not wire surface changes).

## A3 lane input summary

The following items require code action from the A3 integration lane:

| Item | Action | Input |
|---|---|---|
| A1-1 | Promote event/charter/frozen-field enums to `app.types` | 06-data-model literal sets; SIM-02A `response_kind` precedent |
| A1-4 | Mount Charter/Run HTTP endpoints | 10-api-and-events.md L65-75; Task 9 domain/repository layer |
| A1-9 | Canonicalize evidence read API paths in 10-api, then mount | `app/evidence/schemas_api.py` + `routes.py`; 06-data-model L661-700 |
| A1-10 | Promote SourceGrade/FreshnessStatus/verdict enums to `app.types` | Same as A1-1 precedent |

## Decision

- Accepted by: Contract/Mainline Lead (contracts function), 2026-07-25 (Asia/Shanghai).
- Date: 2026-07-25
- Required follow-up: A3 integration lane consumes the four DEFERRED/IMPLEMENTATION_FREE items above; no other lane action needed.
- ready_for_merge: YES (docs-only; git diff --name-only limited to contract-changes/, 06-data-model.md, 10-api-and-events.md, handoff, HEAD, HISTORY).
