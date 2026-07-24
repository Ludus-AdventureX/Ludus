# TASK07_QA_HANDOFF — Agent Runtime Seam (r2)

- QA owner: qa_release (branch `codex/qa-mainline-258a94d`); independent review, one handoff per candidate.
- Candidate: `codex/task-07-agent-runtime-r2` @ **`cce4d7036967532366bb2e64483a21810ef4248d`** (owner: ways_agent_pipeline).
- exact_tested_head: fresh detached worktree at `cce4d70` (byte-identical product tree) + QA-owned overlay `services/api/tests/test_agent_runtime.py` (19 new tests) + updated shared `conftest.py` from the QA baseline branch. No product file modified by QA.

## Verdicts

- **IMPLEMENTATION_QA_VERDICT: PASS** — P0=0, P1=0, P2=0 new findings.
- **REMOTE_STATUS**: handoff claims live-verified `remote_branch_sha == cce4d70`; QA's own re-read attempt hit the intermittent GitHub 443 block this round, so QA records the remote claim as **unverified-by-QA (blocked)**, content verdict unaffected.
- Integration note: seam-only slice; lens implementations, persistence and CCR-20260724-Ways-01 (StrategicLensArtifact schema/migration + ConnectorStatus enum) remain pending with contract_lead — per the coordinator's own plan, this branch precedes those and is content-ready.

## Gate results (G-01..G-09)

- G-01 base: `cce4d70~1 == 258a94d` (current live main); fresh ✔
- G-02 scope: exactly `HEAD` + `services/api/app/agents/**` (11 files) — inside ways_agent_pipeline write_scope; no schemas/contracts/migrations/web ✔
- G-03 full suite `-W error` (disposable migrated PG16): **137 passed, 1 xfailed, 0 failed** (baseline 118 + 19 QA runtime tests) ✔
- G-04 migrations: none changed; alembic state untouched ✔ (n/a roundtrip)
- G-05 contracts: no contract files changed; baseline drift status carries ✔
- G-06 ruff + compileall over `app` + tests: PASS ✔ (no apps/web changes → web build n/a)
- G-07 secret scan + `git diff --check` over `258a94d..cce4d70`: clean ✔
- G-08/09 fresh worktree, exact head, findings routing: observed ✔

## QA test evidence (services/api/tests/test_agent_runtime.py, all PASS)

- **ToolRegistry fail-closed**: catalog is exactly the five read-only tools; non-catalog/write/duplicate registration rejected; `context=None` → MissingToolContext; unknown → UnknownTool; envelope violation → ToolScopeError; invalid payload → SchemaValidationError (with findings); availability=False → ToolUnavailable; valid call returns typed output.
- **Context isolation / subset / delegation**: `for_role` rejects unknown roles and superset envelopes; `tool_context()` pins workspace/run/user/connectors; `delegate` intersects tools, increments depth, and hard-fails past `max_depth` (DelegationError).
- **Hard budgets**: counter fails closed exactly at the limit (BudgetExhausted with key/limit); tool-call charges hit aggregate+specific counters; manifest parsing fails closed on missing budgets/level and ignores boolean flags.
- **Empty-content repair**: exactly one retry (attempts=2 on success; 2 provider calls then SchemaValidationError on persistent emptiness); each attempt charges `max_model_calls`; blank raw_text and empty object both trip EmptyModelContentError.
- **Provider neutrality**: runner exercised via a duck-typed fake using only the `ModelProvider` protocol; repair adds one message, same protocol call; `StructuredCompletion` has no `reasoning_content` slot (AR-02 structural guarantee).
- **LensSpec completeness**: LENS_SPECS == the canonical five; owner workers research/critic/critic/synthesis/synthesis; pre-mortem trigger encodes "after counterparty" (FL-02 ordering).
- **Server-owned guard**: `from_payload` rejects every probed server-owned field (id/workspaceId/…/contentHash) and unknown extras; allowed/forbidden sets are disjoint.
- **LensRegistry full-set**: unknown lens rejected, duplicates rejected, `require_full_set` fails until all five registered, then passes.
- **No unauthorized surface**: no `sign_decision`/`transition_to_decided`/write tools anywhere in the catalog; fixture_search tool is offline/deterministic (no implicit network import in `app/agents/**` — audit by inspection, no httpx/socket usage outside provider adapter seam).

## Findings

- P0/P1/P2: none new. P3 observation: none. Standing project-level items (CCR-20260724-Ways-01 pending; Task 7/8/10 write_scope doc-vs-manifest discrepancy) remain with contract_lead / Mainline Lead as reported by the coordinator.
