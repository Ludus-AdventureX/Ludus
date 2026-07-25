# Task 4+5 Backend Handoff — 档案、候选记忆与日常问答 (r1)

- Lane: Case/API/Data Owner (`codex/task-04-05-backend-r1`), Fable5
- Gate 0 base: `4941e58bee3b91f14a4a92b7fab92750ef85b3b6` (remote-verified main via `git ls-remote origin refs/heads/main`, 2026-07-25)
- Rebuild lineage (principal-approved "backup-then-port"): the prior r1 attempt was a single unpushed commit `1ea3925` on the stale base `4508b30`. Gate 0's "zero-commit" premise did not hold, so `1ea3925` was preserved as tag `archive/task-04-05-backend-r1-1ea3925` (zero work lost), the old worktree/branch were removed, this fresh worktree + same-name branch were rebuilt from the new base, and the implementation was ported via `git cherry-pick -n 1ea3925`. No rebase/amend/force. New-base delta (27 commits): `app/models.py` / `app/agents/model_provider.py` / `app/tenancy/routes.py` / `main.py` are byte-identical across bases (port applied clean; only HEAD/HISTORY conflicted, resolved append-only); migration chain head advanced `b2c7e9d4a1f6` -> `f9a4b7e2c8d3`.
- Plan source: `docs/product-plan/18-detailed-development-plan.md` Task 4 (L665-712) + Task 5 (L714-773), consumed verbatim
- Frozen contracts consumed: `docs/product-plan/10-api-and-events.md` (核心 API 表, 创建决策项目, 讨论消息), `docs/product-plan/06-data-model.md` (DossierEntry / DossierVersion / CandidateRevision / CaseVersion / QuickAnalysisResult / ArgumentNode)

## Delivery summary

### ① Case canonical routes (first priority) — DELIVERED
`services/api/app/cases/routes.py` — RELATIVE router (no `/api/workspaces/{workspaceId}` prefix of its own):

- `POST /cases` (201; frozen response `decisionCaseId/version/title/inferredDecisionType/clarifyingQuestions`)
- `GET /cases` (workspace-bounded query with `status`/`operationalStatus`/`limit`/`cursor`; frozen list item shape + `nextCursor`)
- `GET /cases/{decisionCaseId}` (canonical DecisionCase + confirmed DossierVersion reference + `caseVersion` + `argumentNodes: ArgumentNode[]` projection)
- `GET /cases/{decisionCaseId}/versions/{version}` (immutable CaseVersion row)

**Frontend flag: `caseListRouteAvailable` may be flipped at the MOUNTING WAVE** —
the router is relative and NOT yet included in `app.tenancy.routes.workspace_router`
(mounting is Contract-Lead-owned; this lane did not touch `main.py` or
`tenancy/routes.py`). Mount instruction: `workspace_router.include_router(cases_router)`
(same for `dossiers_router`, `conversations_router` below).

### ② Command objects — DELIVERED
`services/api/app/dossiers/service.py`: `ProposeEntry` / `ConfirmEntry` / `RejectEntry` / `ExpireEntry` / `ReclassifyEntry`.

- Propose/Reject write ONLY `candidate_revisions` + `domain_events` audit rows; zero Dossier/Case versions (owner test + QA battery enforce).
- Confirm validates `base_dossier_version` (+ optional `base_case_version`) and writes formal entry + new DossierVersion + new CaseVersion + confirmation event in one transaction (single commit at the route boundary; service only flushes). Stale base → `DossierVersionConflictError` → HTTP 409 `DOSSIER_VERSION_CONFLICT`.
- Expire/Reclassify fork: confirmed entry → formal edit, entry.version+1, new DossierVersion + event; pending candidate → candidate-only update, zero versions.

### ③ Immutable snapshots — DELIVERED
Frozen canonical `dossier_versions` (entry_ids + snapshot_hash + reason + created_by) plus this lane's companion table `dossier_version_snapshots` (`app/dossiers/models.py`) carrying per-entry `{entryId, entryVersion, statementType, scope, contentHash}` + `decision_maker_profile_version` + `subject_version`. Rows are write-once; owner test proves later edits never rewrite an existing snapshot.

### ④ ModelProvider — DELIVERED
`services/api/app/agents/model_provider.py` (the ONLY `app/agents` file touched; additive only, existing Protocol/FixtureModelProvider surface unchanged):

- `DeepSeekModelProvider` (OpenAI-compatible `/chat/completions`; every constructor parameter from env via `build_model_provider_from_env` — `MODEL_PROVIDER/MODEL_BASE_URL/MODEL_API_KEY/MODEL_NAME/MODEL_TIMEOUT_SECONDS/MODEL_THINKING_ENABLED`; no hard-coded endpoint/model defaults; missing vars fail fast).
- `complete_structured_checked`: empty-content detection + canonical JSON-schema-subset validation + AT MOST one repair retry; NO free-text fallback parse.
- `reasoning_content`: dropped via `message.pop("reasoning_content", None)` inside the provider before any result object exists — never returned/persisted/evented/logged (QA-1 scans both ORM metadata and source).
- Fixture provider extended with deterministic `complete_text`; injectable `httpx` transport keeps unit tests at zero real network. Gate 0 model probe (`probe()`) exists but is never called by tests.

### ⑤ Message persistence — DELIVERED
`app/conversations/routes.py` persists to frozen `messages`: raw user text, assistant final text, `provider`, `request_model_id`, `response_model_id`, `provider_response_version`, `token_metadata`/`cost_metadata`, and the associated DecisionSubject (+ case binding enforced by the frozen same-subject composite FKs).

### ⑥ Candidate extraction after reply — DELIVERED
`app/conversations/memory_extractor.py`: writes ONLY `candidate_revisions` (never `dossier_entries`/`case_versions`); candidates persist `base_dossier_version` + `base_case_version`; identifies candidate decision questions + options besides facts/constraints/assumptions; explicit "临时想法"/"不要记住"/"off the record" instructions deterministically return empty candidates without a model call. Message→candidate link recorded on `domain_events` (the frozen schema has no `conversation_revisions` table).
- Note: the frozen `讨论消息` response includes `candidateRevisionId`, so extraction completes inside the request before the envelope is assembled; it is structurally isolated (`MemoryExtractor.extract`) and directly callable from a background worker when the streaming path lands.

### ⑦ QuickAnalysisResult — DELIVERED
`app/conversations/quick_analysis.py` + `POST /conversations/{conversationId}/quick-analyses`: generated ONLY from confirmed dossier entries (candidates structurally excluded); no MethodRouter, no Charter/Run/report/PDF/sandbox; persisted with single-member `formality=non_formal` enum and projected with the permanent "非正式方法输出" disclaimer.

## Migration discipline — DEFERRED, DECLARED
This lane is code-first and ships **no Alembic revision**. New-base finding: the frozen chain head is now single `f9a4b7e2c8d3` (advanced from `b2c7e9d4a1f6` by the Task 8/9 migrations `e7f3a2c9d5b1` add_evidence_ledger + `f9a4b7e2c8d3` add_analysis_runtime that landed on main). Task 10's own migration is STILL absent (`codex/task-10-lens-validators-r1` shipped validators/tests only, no `versions/` entry). Per the charter's ordering (my `down_revision` must point at Task 10's 0004), the migration for `dossier_version_snapshots` is withheld until A1 reports the 0004 rev-id; it will then be generated from `app/dossiers/models.py` metadata with `down_revision = <task10-0004-rev-id>` and land last. QA-7 (`test_qa7_no_lane_migration_until_task10_0004_lands`) is re-pinned to the new state (exact `versions/` set incl. the two Task 8/9 files, single head `f9a4b7e2c8d3`) and will fail loudly the moment the chain moves, forcing the follow-up.
Until then, owner/QA tests materialise the companion table via `Base.metadata.create_all(checkfirst=True)` on the migrated test database.

## Canonical reuse note (important for reviewers)
The canonical Task 4/5 tables (`dossier_entries`, `dossier_versions`, `candidate_revisions`, `case_versions`, `conversations`, `messages`, `quick_analysis_results`, `domain_events`) already exist in frozen `app/models.py` (Task 19A migration `6b246c283d7a`) and are REUSED — this lane defines no parallel tables/enums. Two adaptations to the frozen shapes:
- `candidate_revisions` has no subject column → subject-only candidates pin `decisionSubjectId` inside each proposal payload (JSONB), resolved at confirm time; case-bound candidates resolve via the case.
- There is no dossier-head table → current dossier version = `max(dossier_versions.version)` (empty dossier ⇒ version 1 per 06-data-model convention); the `decision_subjects` row is the `FOR UPDATE` concurrency anchor for version bumps.

## Acceptance gates (all green)
- Owner + QA tests: `tests/test_dossier_versions.py` (11) + `tests/test_memory_extractor.py` (13) + `tests/test_task0405_qa_battery.py` (9) = **33 passed** (9.07s) re-verified on the new base against a disposable migrated PostgreSQL (`alembic upgrade head` to `f9a4b7e2c8d3` on fresh DB `qa_task0405_r1new`, one-time PG16 container `ludus-pg-mainline-w1` @55447 reused; venv provisioned offline from the pre-set uv cache — zero installs).
- Charter gates covered: candidates never in snapshots; snapshot immutability; version-conflict 409 (service + HTTP); cross-tenant invisibility + anti-enumeration (foreign vs nonexistent 404 bodies byte-identical); empty-candidate opt-out; zero real network (fixture provider + httpx.MockTransport only).
- QA battery (≥6): ① whole-metadata + whole-source `reasoning_content` scan (zero persistence/logging paths, active drop asserted); ② full HTTP chain candidate→confirm→version+1→snapshot-excludes-pending; ③ stale-base confirm → 409 `DOSSIER_VERSION_CONFLICT`; ④ expire/reclassify fork candidate vs confirmed; ⑤ tenant anti-enumeration; ⑥ fixture provider byte-determinism; ⑦ migration lifecycle (deferred revision + single frozen head `f9a4b7e2c8d3` + metadata completeness).
- Regression smoke on shared seams: `test_agent_runtime.py`, `test_models.py`, `test_decision_os_invariants.py`, `app/simulations/tests/test_simulation_engine.py` = 81 passed (model_provider extension is additive).
- `ruff check` clean on all owned files; `python -m compileall` clean; conflict-marker scan 0; secret-pattern scan clean (no credentials; `reasoning_content` only documented + actively `pop`-dropped in-provider). Forbidden domains untouched (`git status`: only `app/agents/model_provider.py` modified + new `app/cases|dossiers|conversations` + own tests + this handoff + HEAD/HISTORY).
- CONTRACT_DRIFT_OK: canonical OpenAPI export from this worktree + regenerated TypeScript types are byte-identical (normalized) to the committed `packages/contracts` artifacts — the relative routers are unmounted so the wire surface is unchanged (`main.py`/`tenancy/routes.py` untouched). NOTE: `generate_contracts.ps1 -Check` itself needs the `openapi-typescript` CLI, which is absent from this fresh worktree's `node_modules`; the OpenAPI export step passed and the TS regen + both drift assertions were completed via the primary worktree's installed CLI.

## Known limits / follow-ups for later waves
- `bulk-review`, dossier version-timeline and snapshot-read HTTP endpoints: repository/service capabilities exist (`list_dossier_versions`, `get_dossier_version`, `get_version_snapshot`), but no HTTP routes were invented beyond the frozen 10-api path table; wire them when the Contract Lead freezes those paths.
- Assistant reply is non-streaming JSON in r1; SSE streaming belongs to a later wave (extraction is already isolated for the async path).
- OpenAPI/contract regeneration (`packages/contracts`) is Contract-Lead-owned and intentionally untouched; routers register plain envelope dicts and are ready for catalog registration at mount time.
