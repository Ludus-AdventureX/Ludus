# TASK03_FINAL_RELEASE_QA_HANDOFF (round 3, recomposed candidate with P1 fix)

- QA owner: qa_release; QA branch `codex/qa-task-03-release-gate-r3`.
- Candidate audited: `codex/task-03-contract-integration` @ **`9205835e1932821f92937f6161a953fc4489ce31`** (product-tree-equivalent tip `aee4a43`; verified `aee4a43..9205835` touches `HEAD`/`HISTORY` only).
- **exact_tested_head**: QA branch tip committed below = product tree of `9205835` checked out byte-identical (fresh worktree `qa-release-task03-r3`, clean before overlay) + QA-owned overlay from `5ffe61a` (`services/api/tests/**`, `docs/handoffs/**`) + this round's QA additions (validation-envelope negative battery in `test_release_gate_task03.py`, this handoff, lifecycle). No product file differs from `9205835`; QA tested exactly the candidate it reports on.
- Environment: disposable PostgreSQL 16 @55433 migrated to `f850d361ee42 (head)`; commands run 2026-07-24 with `-W error`.

## Verdicts

- **P1_REGRESSION_VERDICT: PASS** — QA-TASK03-003 regression (`test_canonical_validation_error_uses_envelope`) flipped green on fix `36ee13b`; the new negative battery (malformed JSON, wrong field types, missing fields, constraint violations, illegal path parameter) all return the uniform 422 `VALIDATION_FAILED` envelope with only `type/loc/msg/scalar-ctx` fields and **zero echo of `input`, `url`, or submitted secret values**.
- **IMPLEMENTATION_QA_VERDICT: PASS** — P0=0, P1=0 on the recomposed candidate; the sanitizer implementation reviewed (whitelist projection; non-scalar ctx dropped, not stringified — reprs cannot leak raw input).
- **RELEASE_CONTENT_VERDICT: PASS** — all release-content gates green (matrix below).
- **REMOTE_PUBLISH_VERDICT: BLOCKED** — GitHub 443 blocked again during this round (live `ls-remote` attempt failed); `codex/task-03-contract-integration` upload remains unverified on origin. No upload or publishability of `main` is claimed. Mainline Lead may enter the merge flow **only after**: network recovery → candidate branch push → live `ls-remote` re-read of remote `main` (must still be `2396206` or conflict re-audit) and the candidate ref.

## Structure audit

- Ancestry: `2396206` (freeze), `aa240f7` (impl), `9555ae6` (r2 candidate) are all ancestors of `9205835`; chain matches the declared recomposition (`cc08531 → bdc30cd → 36ee13b → dc84a64 → aee4a43 → 9205835`).
- Product-tree delta vs implementation: `git diff aa240f7 9205835 -- services/api/app` = `main.py` (CCR-20260724-005 mount) + `security/envelope.py` (P1 fix `36ee13b`) — exactly the two authorized changes, nothing else.
- Full changed set vs freeze: 11 product/contract/doc files + lifecycle; **no** `apps/web`, `migrations`, or unauthorized `packages/contracts` change (contracts files are the CCR regeneration).
- Secret scan (excluding generated contracts): 0 hits. Publish-scope: no LICENSE/COPYRIGHT/visibility files. `git diff --check`: only the known P3 EOF blank line (`auth/routes.py:343`).

## Verification matrix (fresh runs on exact_tested_head)

| Item | Result |
|---|---|
| Full suite `pytest tests -q -W error` (candidate + all QA gates + new negative battery) | **118 passed, 1 xfailed, 0 failed** |
| P1 regression + validation-envelope negative battery (5 new tests) | PASS; no `input`/`url`/secret echo |
| Canonical `app.main`: 5 auth endpoints reachable; 401/403/422 envelopes correct; uniform workspace 404 | PASS |
| Auth/Workspace QA gates (session lifecycle, CSRF, capability projection, cross-tenant anti-oracle) | PASS |
| Alembic `upgrade head` + `check` (no new migration) | PASS, `f850d361ee42 (head)` |
| OpenAPI drift (canonical builder vs committed, script-equivalent normalized compare) | OPENAPI_NORMALIZED_DRIFT_OK |
| Types drift (`openapi-typescript 7.13.0` regeneration vs committed) | TYPESCRIPT_DRIFT_OK |
| Official `generate_contracts.ps1 -Check` | not runnable in this worktree (no `node_modules`); comparison semantics reproduced exactly as above — same limitation as r2, recorded, not a candidate defect |
| Ruff (`app` + tests) / compileall | PASS / PASS |
| Owner scope / ancestry / freeze base | PASS |

## Findings register

- P0: 0. P1: 0 (QA-TASK03-003 **closed** by `36ee13b`, permanent regression retained).
- P2 (registered, non-blocking for content acceptance, unchanged owners):
  - QA-TASK03-001 — Postgres-backed login rate limiting; MUST land before public exposure of login (case_api_data).
  - QA-TASK03-002 — tokenVersion request-path enforcement; xfail regression in place (case_api_data).
- P3: EOF blank line `auth/routes.py:343` (cosmetic).

## Clearance statement for Mainline Lead

Content-wise this candidate is cleared: once the network recovers, push `codex/task-03-contract-integration` (tip `9205835`), live-verify the remote ref and remote `main` (`2396206`, unadvanced — re-read immediately before merge), then proceed with the merge flow. If the QA branches are to be merged alongside, the QA coverage merged into main must be exactly the tip recorded on `codex/qa-task-03-release-gate-r3` (this tested combination); merging any other QA commit requires a fresh QA re-run.
