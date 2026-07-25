# CCR-20260725-ANALYSIS-01: Task 9/10 deep-analysis pipeline wire-contract pre-freeze

- Status: accepted
- Requested by: Contract/Mainline Lead (CCR Guest-Analysis contracts lane) — pre-freezing the
  wire contract consumed by Task 9 Phase B (analysis state machine / worker / SSE, Fable5)
  and Task 10 (`ways_agent_pipeline` owner), so those lanes never stop mid-flight to file a CCR
- Contract owner: Contract/Integration Lead
- Related task: task-09 / task-10
- Adjudication branch: `codex/ccr-guest-analysis-contracts`, base
  `bd9fde15278afd63d351b2adaeb95ec32441cd6f` (live ls-remote verified main)

Legend used below for every frozen item:

- **REAFFIRM** — already canonical; this CCR only records the citation (no text change).
- **NEW** — adjudicated here; the named canonical subsection is amended in this same commit
  and the amended sentence appears verbatim in section 7.
- **IMPLEMENTATION_FREE** — deliberately NOT frozen; implementers choose.

## 1. State enums and transition matrix

Canonical sources: `06-data-model.md` (AnalysisCharter/AnalysisRun interfaces and the three
state paragraphs after `QuickAnalysisResult`), `18-detailed-development-plan.md` §1.9 + Task 9
Step 2, `services/api/app/types.py` (`AnalysisRunStatus`, sole enum authority;
`AnalysisStatus = AnalysisRunStatus` is the same object, never a second value set).

### 1.1 Enum values — REAFFIRM

- `AnalysisCharter.status`: `draft | awaiting_confirmation | confirmed | superseded`
  (06 `AnalysisCharter.status`; 18 §1.9).
- `AnalysisRunStatus`: `queued | planning | retrieving | analyzing | criticizing |
  synthesizing | validating | ready | blocked | needs_attention | cancelled`
  (06 export; `types.py` `AnalysisRunStatus` — implementation lanes MUST import it,
  never redeclare).

### 1.2 Divergence check 06 vs 18 Task 9 — result: NO substantive divergence

18 Task 9 Step 2 draws the run pipeline linearly and lists
`needs_attention → planning|retrieving|analyzing|criticizing|synthesizing|validating
（仅回到 lastResumableStage）`; 06 states the interruption edges
(`planning..validating -> needs_attention`), the cancellable set (`queued` + six execution
stages + `needs_attention`), the terminal set (`ready/blocked/cancelled` never resume), and
`queued` never being a resume target. These are complementary, not conflicting. Two points
were underspecified in both documents and are adjudicated NEW here (frozen matrix cells
marked ✚ below).

### 1.3 Charter transition matrix — frozen

| From | To | Legality |
|---|---|---|
| draft | awaiting_confirmation | legal (REAFFIRM, 18 Task 9 Step 2) |
| awaiting_confirmation | confirmed | legal, human confirm only (REAFFIRM) |
| confirmed | superseded | legal, ONLY when the replacement Charter is confirmed (REAFFIRM, 06) |
| any other pair | — | illegal |

- The mechanism that moves `draft → awaiting_confirmation` (explicit endpoint vs an internal
  step inside the confirm flow) is **IMPLEMENTATION_FREE**, provided the persisted status
  order above is observed and `PATCH` remains legal only while unconfirmed
  (`CHARTER_IMMUTABLE` afterwards, 10-api error table).
- While a replacement draft is unconfirmed, the old confirmed Charter stays effective
  (REAFFIRM, 06).

### 1.4 Run transition matrix — frozen

| From | To | Legality |
|---|---|---|
| queued | planning | legal (worker claim) — REAFFIRM |
| planning → retrieving → analyzing → criticizing → synthesizing → validating | next stage only | ✚ NEW: strictly linear, no stage skipping (focused runs traverse all six stages too; they simply produce no lens artifacts) |
| each of the six execution stages | needs_attention | legal interruption edge — REAFFIRM (06) |
| needs_attention | the persisted `lastResumableStage` (one of the six) | legal ONLY after a successful resolution append — REAFFIRM (06/10) |
| validating | ready | legal ONLY here, quality gates passed — REAFFIRM (18 Task 9 Step 2) |
| validating | blocked | ✚ NEW: `blocked` (quality-gate terminal) is entered ONLY from `validating`; earlier-stage failures are recoverable interruptions (`needs_attention`) or cancellations |
| queued, six stages, needs_attention | cancelled | legal — REAFFIRM (06/10 cancel section) |
| ready / blocked / cancelled | anywhere | illegal, terminal — REAFFIRM |

### 1.5 `lastResumableStage` semantics — REAFFIRM

Type `Exclude<AnalysisRunStatus, "queued"|"ready"|"blocked"|"needs_attention"|"cancelled">`
(06). Persisted server-side at interruption time as the stage the run occupied; resolution
resumes exactly there; never client-specifiable; `queued` is never a resume target (10-api
resolution section). Heartbeat expiry of an active-execution run moves it to
`needs_attention` (18 Task 9 Step 4) and answers `ANALYSIS_RUN_STALE` on writes.

- Heartbeat interval, claim primitive (advisory lock vs `FOR UPDATE SKIP LOCKED`), and
  progress-value granularity: **IMPLEMENTATION_FREE** (18 Task 9 Step 4 offers both claim
  primitives).

## 2. RunResolution — three kinds, payloads, idempotency, amendment boundary

Canonical sources: `06-data-model.md` (`RunInterventionClassification`,
`RunResolutionPayload`, `RunResolution`), `10-api-and-events.md`
"Run resolution、amendment 与取消" + 幂等 section + error table.

### 2.1 Exact type names and payload schema — REAFFIRM

`RunResolutionPayload` is the closed discriminated union on `kind`:

1. `source_conflict` — `{ conflictGroupId: string, selectedEvidenceIds: string[],
   rationale: string }`
2. `hard_constraint_confirmation` — `{ confirmedConstraintIds: string[] }`
3. `provider_recovery` — `{ action: "retry" | "use_cached" | "switch_allowed_connector",
   connectorId?: string }`; the switch target MUST already be in the Charter's
   `allowedConnectorIds`; a resolution can never add connectors, materials, or budget.

`RunResolution.resumeStage` uses the same `Exclude<…>` type as `lastResumableStage` and MUST
equal the persisted value. Endpoint: `POST /api/workspaces/{workspaceId}/analyses/{analysisRunId}/resolutions`
with mandatory `Idempotency-Key`. Success envelope frozen as documented:
`{ ok, data: { analysisRunId, classification: { classificationId, result,
changedFrozenFields }, resolutionId, status, resumedFrom }, eventId }`.

### 2.2 Idempotency semantics — REAFFIRM

Same `Idempotency-Key` + same normalized body ⇒ replay of the original success (original
HTTP status, same body, `meta.idempotencyReplay: true`); same key + different body ⇒
`IDEMPOTENCY_CONFLICT` 409. An idempotent hit is NEVER expressed as
`ANALYSIS_RUN_ALREADY_ACTIVE` (10-api 幂等 section). Key format/length validation:
**IMPLEMENTATION_FREE**, follow the SIM-02A precedent (`validate_idempotency_key`).

### 2.3 Amendment boundary — "amendment never travels the resolution path" — REAFFIRM

Order of operations is frozen: the server FIRST persists an append-only
`RunInterventionClassification`. Only when `changedFrozenFields == []` AND the payload is one
of the three kinds within the frozen scope does a `RunResolution` get appended and the run
atomically resumed. Any change to a `CharterFrozenField`
(`decision_question | goals | options | preference_weights | hard_constraints |
material_scope | connector_scope | budget | method | analysis_level | strategic_lens_set`)
⇒ classification persists with `result: "amendment"`, NO resolution row is created, and the
response is:

- HTTP `409`, error code `RUN_AMENDMENT_REQUIRED`, `retryable: false`,
  `details: { "changedFrozenFields": [...], "replacementUrl": "..." }` — the `details` key
  names are ✚ NEW (10-api previously said "changedFrozenFields 和 replacement URL" without
  naming the second key; frozen as `replacementUrl`, section 7 sync S4).
- Budget exhaustion is NOT resolvable either: run goes `needs_attention`, but extending
  budget is an amendment (replacement Charter + new Run; 18 Task 8A/Step 3 + 06).
- Lens set changes (`strategic_lens_set`) are ALWAYS amendments, never resolutions and never
  report revisions (08 `requiredStrategicLensTypes` paragraph; 06 frozen-field list).
- The replacement flow (`POST …/analysis-charters/{charterId}/replacements` with
  `baseVersion` + `replacesAnalysisRunId`; old run atomically `cancelled` with
  `cancellationReason: "charter_replaced"` + `supersededByAnalysisRunId` when the new Run is
  created) — REAFFIRM (10-api).

## 3. AnalysisEvent envelope and SSE mapping

Canonical sources: `06-data-model.md` (`AnalysisEventCategory`, `AnalysisEventType`,
`AnalysisEvent`), `10-api-and-events.md` "SSE 事件" + the sentence after the third example.

### 3.1 Closed enum sets — REAFFIRM

- `category` (exactly five): `agent.status | agent.task | tool.call | citation.added |
  user.confirmation.required`.
- `type` (exactly the twenty values of 06): `analysis.stage.started`,
  `analysis.stage.progressed`, `analysis.stage.completed`, `analysis.needs_attention`,
  `analysis.resumed`, `analysis.amendment_required`, `analysis.cancelled`,
  `analysis.blocked`, `analysis.ready`, `research.packet.completed`, `retrieval.completed`,
  `quality.warning`, `strategic_lens.completed`, `tool.call.started`, `tool.call.completed`,
  `tool.call.failed`, `fallback.cached_evidence`, `fallback.fixture.loaded`,
  `citation.added`, `user.confirmation.required`.
- Boundary ruling (REAFFIRM by derivation): the lifecycle events listed in 10-api
  "决策生命周期事件与不可调用能力" (`case.scope_confirmed`, `analysis.run_manifest.frozen`,
  `analysis.validator.completed`, `signoff.*`, `decision.record.*`, …) are the case-level
  domain-event ledger, NOT `AnalysisEvent.type` values — 10-api states the SSE stream
  "只使用 06-data-model.md 的一套合同". Streaming lifecycle events over this SSE channel would
  require a future CCR; Task 9 MUST NOT widen the union.

### 3.2 Envelope fields — REAFFIRM

`AnalysisEvent = { id, sequence, workspaceId, decisionCaseId, analysisRunId, category, type,
originMode, sourceOriginModes[], createdAt, payload }` (06). `originMode` single-valued,
`sourceOriginModes[]` deduplicated; conservative display order `fixture > cached > live`.
No `reasoning_content`, credentials, or raw tool output may ever appear in any field.

### 3.3 Sequence monotonicity — ✚ NEW (scope made explicit)

`sequence` is a server-assigned integer, **strictly increasing within a single
`analysisRunId` event stream**, assigned at persistence time; regressions are forbidden,
gaps are permitted (crash between reserve and commit). Canonical text amended (section 7,
sync S5). Whether sequences are gap-free, and the storage mechanism (per-run counter vs
table sequence): **IMPLEMENTATION_FREE**.

### 3.4 SSE mapping — REAFFIRM

Stream URL: `GET /api/workspaces/{workspaceId}/analyses/{analysisRunId}/events`
(the `eventsUrl` returned on run creation). Frame mapping:

- `id:` = `AnalysisEvent.id`;
- `event:` = `category` (exactly the five values — front-end dispatch key);
- `data:` = the COMPLETE `AnalysisEvent` envelope as one JSON document, never a fragment;
- `Last-Event-ID` (reconnect): server resolves the supplied event id to its persisted
  `sequence` and replays history strictly after it from the database, then continues live.

Keep-alive comments, retry hints, buffer sizes: **IMPLEMENTATION_FREE**.

### 3.5 `strategic_lens.completed` — payload and timing

- `category: "agent.task"`, `type: "strategic_lens.completed"` — REAFFIRM (10-api lens
  section).
- Payload is CLOSED ("payload 只包含"): `{ lensArtifactId, lensType, producerRole,
  referenceCounts, contentHash }`. ✚ NEW: the reference-count member is frozen as
  `referenceCounts` with the same shape as `StrategicLensArtifactSummary.referenceCounts`
  (`{ sourcePacketCount, claimCount, evidenceCount, assumptionCount, challengeCount }`);
  10-api previously said "引用计数" without a key name (section 7, sync S2). Note the id key
  is `lensArtifactId`, NOT `artifactId` — implementers must not shorten it.
- ✚ NEW (timing made explicit, same sync S2): the event may be appended ONLY after the
  artifact row's transaction has committed (`strategic_lens_artifacts` insert per
  CCR-20260724-Ways-01). Consumers fetch the body through the read endpoints; content is
  never duplicated into the event stream (REAFFIRM, 10-api).
- Payloads of the other nineteen event types: the keys shown in the 10-api examples
  (e.g. `analysis.stage.progressed` ⇒ `{ status, progress, message }`) are the canonical
  minimum; additional payload keys are **IMPLEMENTATION_FREE** (additive only, same
  no-secrets/no-reasoning rule).

## 4. Five-lens contract linkage

Canonical sources: `08-deep-research-pipeline.md` (`requiredStrategicLensTypes` paragraph,
behavior requirements, 持久化与读取 API), `10-api-and-events.md` 战略透镜产物,
`06-data-model.md` (`AnalysisRun.strategicLensArtifactIds`), `types.py`
(`StrategicLensType`, `FULL_REQUIRED_STRATEGIC_LENSES`, `StrategicLensArtifactStatus`,
`LensProducerRole`), CCR-20260724-Ways-01 (persistence contract, live on main).

1. **Normalization — REAFFIRM.** `requiredStrategicLensTypes` comes from the confirmed
   Charter. `focused` ⇒ exactly the empty set; `full` ⇒ exactly the five-element set,
   normalized to the canonical order `porter_five_forces, pre_mortem,
   counterparty_response_matrix, scenario_planning, meadows_leverage_points`
   (= `FULL_REQUIRED_STRATEGIC_LENSES` in `types.py`, the only importable authority).
   The normalized set freezes with the Charter; runtime add/remove/replace ⇒
   `strategic_lens_set` amendment (section 2.3).
2. **`strategicLensArtifactIds` — REAFFIRM.** full Run records the five persisted artifact
   ids on the run row; focused keeps `[]` (06 + 18 Task 9 Step 4). Producer mapping is fixed:
   Research ⇒ porter; Critic ⇒ pre_mortem + counterparty_response_matrix; Synthesis ⇒
   scenario_planning + meadows_leverage_points; Validation checks, never produces
   (`LensProducerRole` docstring; 18 Task 9 Step 5).
3. **Read/write path reference — REAFFIRM.** Artifacts are written ONLY through the internal
   repository (no POST/PATCH/DELETE); `(workspace_id, analysis_run_id, lens_type)` unique;
   rows immutable; `ready` requires the Validation witness (`validation_accepted_at` CHECK,
   Ways-01 §3). User-visible reads are the already-shipped
   `GET …/analyses/{analysisRunId}/strategic-lenses` (summary list, canonical five order) and
   the item endpoint (full discriminated union). Task 9's worker MUST reference these
   artifacts by id and MUST NOT introduce a parallel lens store or a second read surface.
4. **Which contract owns the Task 10 quality-gate assertions — adjudicated (REAFFIRM by
   assignment, no text change):**
   - The wire-level exact-set gate — "full Run 在进入 `ready` 前必须各有一份 `ready` 产物，
     报告恰好引用这五个 ID", failure code `STRATEGIC_LENS_INCOMPLETE` 422 — belongs to
     `10-api-and-events.md` (战略透镜产物 + 错误码表). full `ready` therefore implies five
     `ready` artifacts; `validating → blocked` is the failure edge (section 1.4).
   - The five per-lens BEHAVIOR validators (Porter dual-market five forces, Pre-Mortem three
     perspectives/top-3, Counterparty matrix rules, Scenario two-axis/killed strategy,
     Meadows leverage analysis) belong to the method-pack/ways stage-output schema contract
     (`08-deep-research-pipeline.md` 行为要求 + `hardtech-market-direction@1.1.0` ways
     schemas), NOT to the HTTP wire contract; Task 10 owns their enforcement.
   - The database invariants (composite FKs, partial unique `ready` index, immutability)
     belong to CCR-20260724-Ways-01 and are already live; Task 9/10 consume, never re-migrate.

## 5. Reserved error codes (fail-closed, SIM-precedent style)

Canonical source: `10-api-and-events.md` 错误码 table (already normative). Precedent for
stability discipline: CCR-SIM-01 Addendum A1's two verbatim lower-snake codes and SIM-02A §8.
Every foreseeable rejection path of Task 9/10 already has, or now receives, a stable code —
implementers MUST NOT invent codes.

| Path | Code | HTTP | Status |
|---|---|---:|---|
| second active formal Run on the same Case (not an idempotent hit) | `ANALYSIS_RUN_ALREADY_ACTIVE` + `details.existingAnalysisRunId` | 409 | REAFFIRM |
| heartbeat-expired run written to | `ANALYSIS_RUN_STALE` | 409 | REAFFIRM |
| resolution on a run not in `needs_attention` / terminal | `ANALYSIS_RUN_NOT_RESUMABLE` | 409 | REAFFIRM |
| cancel on `ready`/`blocked` | `ANALYSIS_RUN_NOT_CANCELLABLE` | 409 | REAFFIRM (repeat cancel of an already-`cancelled` run replays the same terminal response, it is NOT an error — 10-api cancel section) |
| frozen-field change smuggled as resolution | `RUN_AMENDMENT_REQUIRED` + `details.{changedFrozenFields, replacementUrl}` | 409 | REAFFIRM + NEW details keys (§2.3) |
| resolution payload outside the three kinds / outside frozen scope | `RUN_RESOLUTION_INVALID` | 422 | REAFFIRM |
| run creation from unconfirmed Charter | `CHARTER_NOT_CONFIRMED` | 409 | REAFFIRM |
| mutation of confirmed/superseded Charter | `CHARTER_IMMUTABLE` | 409 | REAFFIRM |
| chaotic/disorder without human override | `CYNEFIN_GATE_BLOCKED` | 422 | REAFFIRM |
| same Idempotency-Key, different body | `IDEMPOTENCY_CONFLICT` | 409 | REAFFIRM |
| publication/export attempt after cancel or on non-ready run (incl. post-cancel publish) | `REPORT_PUBLICATION_BLOCKED` (report), `EXPORT_NOT_ALLOWED` (export) | 409 / 403 | REAFFIRM — no new "cancelled" code; cancelled ⊂ "Run 未 ready" |
| full run missing any of the five lenses / report references incomplete | `STRATEGIC_LENS_INCOMPLETE` | 422 | REAFFIRM |
| any API-reachable run transition outside the section 1.4 matrix with no more-specific code above | `ANALYSIS_TRANSITION_INVALID` | 409 | ✚ NEW reservation (section 7, sync S3) — defense-in-depth backstop, e.g. race between state check and act; MUST NOT replace the specific codes |

`details` members beyond those named above: **IMPLEMENTATION_FREE** (sanitized, no secrets,
no hash echoes beyond documented fields). The two lower-snake SIM codes
(`strategy_edge_gating_unsupported`, `score_constraint_operator_unsupported`) are unaffected
and remain verbatim.

## 6. What this CCR deliberately does NOT freeze (summary of IMPLEMENTATION_FREE)

- Charter `draft → awaiting_confirmation` trigger mechanics (§1.3).
- Worker claim primitive, heartbeat interval, progress granularity (§1.5).
- Idempotency-Key format validation details (§2.2).
- Sequence storage mechanism / gap-freeness (§3.3); SSE keep-alive/retry/buffering (§3.4).
- Additive payload keys on non-lens event types (§3.5).
- Additional sanitized `details` members on error envelopes (§5).
- All prompt content, stage internals, and model/provider mechanics (Task 10 scope).

## 7. Canonical text synchronization performed in this commit

Each amendment below is applied verbatim to the named subsection — nothing else in those
documents is touched.

- **S1** `06-data-model.md`, analysis-state paragraph (after "…ready、blocked、cancelled
  都不得恢复。"), append:
  "六个执行阶段严格按 `planning → retrieving → analyzing → criticizing → synthesizing →
  validating` 线性推进，不得跳步；`ready` 与 `blocked` 只能从 `validating` 进入
  （CCR-20260725-ANALYSIS-01）。"
- **S2** `10-api-and-events.md`, sentence after the lens list example, replace
  "payload 只包含 `lensArtifactId`、`lensType`、`producerRole`、引用计数和 `contentHash`。"
  with
  "payload 只包含 `lensArtifactId`、`lensType`、`producerRole`、`referenceCounts`（与
  `StrategicLensArtifactSummary.referenceCounts` 同形）和 `contentHash`，且只能在 artifact
  行持久化提交成功后追加（CCR-20260725-ANALYSIS-01）。"
- **S3** `10-api-and-events.md`, 错误码 table, insert after the `RUN_RESOLUTION_INVALID`
  row:
  "| `ANALYSIS_TRANSITION_INVALID` | 409 | 请求隐含的 Run 状态迁移不在 canonical 迁移矩阵内，且没有更具体的错误码适用（CCR-20260725-ANALYSIS-01） | 否 |"
- **S4** `10-api-and-events.md`, amendment paragraph, replace
  "details 包含 `changedFrozenFields` 和 replacement URL"
  with
  "details 固定为 `{ \"changedFrozenFields\": [...], \"replacementUrl\": \"...\" }`"
- **S5** `10-api-and-events.md`, SSE contract paragraph, append after "…按持久化 `sequence`
  从数据库历史继续。":
  "`sequence` 在单个 `analysisRunId` 事件流内严格单调递增：由服务端在持久化时分配，禁止回退，
  允许缺口（CCR-20260725-ANALYSIS-01）。"

## Canonical Impact

- 06-data-model.md: S1 (one sentence, analysis-state paragraph).
- 10-api-and-events.md: S2/S3/S4/S5 (lens event payload, one error row, amendment details
  keys, sequence scope).
- Event/error/status impact: one NEW reserved code `ANALYSIS_TRANSITION_INVALID` (409);
  no enum value added or removed anywhere; no event category/type change.

## Compatibility

- Backward compatible: yes — no shipped surface emits these objects yet (Task 9 Phase B not
  started); all amendments narrow ambiguity rather than change values.
- Migration required: none (this CCR); Task 9's own tables arrive with its slice.
- Fixture migration: none.
- Generated client impact: none now (analysis routes are not in the generated catalog yet);
  when Task 9 mounts routes, contracts regeneration is intentional drift under that slice's
  CCR step, per SIM-02A precedent.

## Validation

- Contract tests (to be written by Task 9/10 owners, asserting THIS document):
  transition-matrix property tests (§1.4 legality table, including the two NEW cells);
  resolution union round-trip + amendment 409 body (§2); SSE envelope/`Last-Event-ID`
  resume + per-run sequence monotonicity (§3); focused-empty/full-exact-five normalization
  (§4); every §5 code reachable via its documented path and no undeclared codes emitted.
- OpenAPI drift check: `generate_contracts.ps1 -Check` stays `CONTRACT_DRIFT_OK` for this
  docs-only commit.
- Rollback: revert this commit (CCR + the five sentence-level syncs revert together).

## Decision

- Accepted by: Contract/Mainline Lead (contracts function), 2026-07-25 (Asia/Shanghai).
- Date: 2026-07-25
- Required follow-up: Task 9 Phase B and Task 10 lanes implement against this freeze; any
  deviation discovered during implementation requires an addendum to THIS CCR before code
  diverges (ready_for_consumption: YES for Delivery B).
