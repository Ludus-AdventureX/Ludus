# TASK03_RELEASE_GATE_QA_HANDOFF (round 2, combined candidate)

- QA owner: qa_release; QA branch `codex/qa-task-03-release-gate`.
- Combined candidate audited: `codex/task-03-contract-integration` @ `9555ae68c8e65013272aeb5530e72252a6ebec64` (functional contract head `f6d211b`; implementation ancestor `aa240f7`; base = CONTRACT_FREEZE_SHA `2396206`).
- Exact tested HEAD: this QA branch tip (see commit below) = product tree of `9555ae6` (byte-identical, verified `git status` clean before tests) + QA-owned overlay from `b5611d1` (`services/api/tests/**`, `docs/handoffs/**`) + this round's QA additions (`test_release_gate_task03.py`, conftest canonical-app mode, this handoff). No product file differs from `9555ae6`.
- Environment: fresh worktree `decision-lab-G0/worktrees/qa-release-task03-r2`; disposable PostgreSQL 16 @55433 migrated to `f850d361ee42 (head)`.

## Verdicts

- **IMPLEMENTATION_QA_VERDICT: BLOCKED** — new P1 (QA-TASK03-003) found in implementation-owned `app/security/envelope.py`; revises the round-1 PASS, which had a coverage gap on the `RequestValidationError` path (now closed with a permanent regression test).
- **RELEASE_CONTENT_VERDICT: BLOCKED** — solely by QA-TASK03-003. Every other release-content item passes (see matrix). One-line fix expected; re-verdict after case_api_data ships it and QA re-runs the suite.
- **REMOTE_PUBLISH_VERDICT: BLOCKED** — network recovered during this session and live `ls-remote` confirms remote `main` still = `2396206` (no concurrent advance) but `codex/task-03-contract-integration` is absent on origin (upload still pending) and release content is blocked anyway.
- Mainline Lead merge flow: **NOT cleared**. Do not merge until QA-TASK03-003 is fixed, QA re-runs green on the revised candidate, and the candidate branch is uploaded and live-verified.

## Audit results (structure)

- Ancestry: `2396206` and `aa240f7` are ancestors of `9555ae6`; `aa240f7~2 == freeze SHA`; `f6d211b..9555ae6` touches `HEAD` only; implementation tree unmodified by the merge (`git diff aa240f7 9555ae6 -- services/api/app` = `main.py` only, which is the CCR mount).
- Changed paths: merge brings exactly the 10 implementation files; contract_lead increment is exactly the 6 declared files + lifecycle. All within owner scopes; QA tests not touched by either owner.
- CCR-20260724-005: accepted and on-disk; all four decisions executed; QA's two round-1 notes answered (4 existing error codes verified present in doc-10; cookie/header names fixed as P0 contract values). ENDORSED.
- Secret/publish-scope scan over `2396206..9555ae6` (excluding generated contracts): 0 hits; no LICENSE/COPYRIGHT/visibility files touched. `git diff --check`: only the known P3 EOF blank line (`auth/routes.py:343`).

## Verification matrix (fresh runs on the combined HEAD)

| Item | Result |
|---|---|
| Canonical `app.main` endpoint reachability (5 auth paths via `app.openapi()` + live ASGI probes) | PASS |
| `register_error_handlers` active on canonical app (unauth session → enveloped 401 `SESSION_REVOKED_OR_EXPIRED`; no-CSRF register → enveloped 403 `CSRF_VALIDATION_FAILED`) | PASS |
| Uniform workspace 404 / capability projection / CSRF / session lifecycle (full QA gate suites, canonical-app mode) | PASS |
| Full suite `pytest tests -q -W error` | **1 failed (QA-TASK03-003 regression), 111 passed, 1 xfailed** |
| `alembic upgrade head` + `check` (no new migration) | PASS, `f850d361ee42 (head)` |
| Contract drift: canonical `build_openapi.py` output vs committed `openapi.json` (script-equivalent newline-normalized compare) | OPENAPI_NORMALIZED_DRIFT_OK |
| Generated types drift: `openapi-typescript 7.13.0` from fresh canonical OpenAPI vs committed `types.gen.ts` | TYPESCRIPT_DRIFT_OK |
| OpenAPI + types contain all 5 auth endpoints | PASS (asserted in `test_release_gate_task03.py`) |
| Ruff (`app` + tests) / compileall | PASS / PASS |
| Note: official `generate_contracts.ps1 -Check` could not run in this worktree (no `node_modules`); the two drift checks above reproduce its exact comparison semantics with the sibling installed toolchain. Integration Lead's own `-Check` PASS at `f6d211b` stands as corroboration. | recorded |

## New finding

QA_FINDING
severity: P1
implementation_sha: aa240f78edf812e6f3b1d98a356dea5c56264e9d (surfaces on combined candidate 9555ae6 once routers are mounted)
location: services/api/app/security/envelope.py:91 (handle_validation_error)
reproduction:
  - POST /api/auth/register with a CSRF token and an invalid body (e.g. malformed email) against canonical app.main
  - handler calls exc.errors(include_url=False, include_input=False); on pinned FastAPI 0.139.2 RequestValidationError.errors() accepts no kwargs
expected:
  - uniform 422 envelope {ok:false, error:{code:"VALIDATION_FAILED", ...}} per AGENTS §9
actual:
  - TypeError inside the exception handler; every malformed request body escapes as an unhandled 500 with no canonical envelope
evidence:
  - tests/test_release_gate_task03.py::test_canonical_validation_error_uses_envelope (fails with the TypeError traceback; becomes the permanent regression once fixed)
  - round-1 QA missed this path because its 422 assertions exercised the ApiFailure duplicate-email branch, not RequestValidationError; coverage gap closed this round
required_owner: case_api_data (app/security/** scope); suggested minimal fix: call exc.errors() and strip url/input fields manually if needed
blocks_integration: YES

## Standing registered P2s (not blocking content acceptance, unchanged)

- QA-TASK03-001: Postgres-backed login rate limiting — must land before public exposure.
- QA-TASK03-002: tokenVersion request-path enforcement — xfail regression in place.

## Re-review protocol after the P1 fix

1. case_api_data ships the envelope fix on the implementation lane; contract_lead rebuilds/extends the integration candidate (implementation tree must remain otherwise byte-identical).
2. QA re-runs on the new combined HEAD: full suite (expect 112+ passed, 1 xfailed, 0 failed), drift checks, canonical probes; flips this handoff's verdicts.
3. Only then: candidate upload, live remote re-read, and Mainline Lead merge with fresh pre-push `ls-remote`.
