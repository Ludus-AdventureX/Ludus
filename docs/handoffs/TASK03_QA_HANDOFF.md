# TASK03_QA_HANDOFF — Authentication and Workspace Isolation

- QA owner: qa_release; QA branch `codex/qa-task-03-auth-workspace`.
- Reviewed candidate: branch `codex/task-03-auth-workspace`, head `aa240f78edf812e6f3b1d98a356dea5c56264e9d` (commits `f05e665` + `aa240f7`).
- Base: `239620681f88c525912c2e1d8b23483a5f362a5e` (CONTRACT_FREEZE_SHA); verified `merge-base --is-ancestor` and `candidate~2 == freeze SHA` — base exact and fresh.
- Remote verification (live `git ls-remote`, after intermittent 443 retries): `refs/heads/codex/task-03-auth-workspace = aa240f7` (matches handoff claim); `refs/heads/main = 2396206` (no concurrent advance).
- Review environment: fresh detached worktree `decision-lab-G0/worktrees/qa-review-task03` @ `aa240f7`; QA tests overlaid from the QA branch; disposable PostgreSQL 16 (port 55433) migrated to `f850d361ee42 (head)`.

## Verdicts

- **IMPLEMENTATION_QA_VERDICT: PASS** — P0=0, P1=0. All activated acceptance rows pass against the delivered routers; two P2 findings below, both routed, neither blocks integration.
- **RELEASE_GATE_VERDICT: BLOCKED** — Contract Integration prerequisites are not done and are outside this lane's write scope: the auth/tenancy routers are not mounted in canonical `app.main` (verified: canonical route set is only `/health` + docs), canonical OpenAPI/types do not yet contain the five auth endpoints, doc-10 error-code table lacks `AUTH_INVALID_CREDENTIALS`/`WORKSPACE_NOT_FOUND`, and `.env.example` lacks the `AUTH_*` placeholders. This is a sequencing gate owned by contract_lead per the reviewed CONTRACT_CHANGE_REQUEST, not a defect in the candidate and not a fabricated green.

## Scope and hygiene audit

- Changed paths (16 files): `services/api/app/auth/**` (6), `app/security/**` (2), `app/tenancy/**` (2), `HEAD`/`HISTORY` — all inside the `case_api_data` manifest write scope; `app/main.py`, `**/schemas.py`, migrations, `packages/contracts/**`, `apps/web/**` untouched. Zero out-of-scope paths.
- No new migration; `alembic upgrade head` + `alembic check` clean on the disposable database (no model drift introduced).
- Secret scan over `2396206..aa240f7` diff (sk-/AKIA/private-key/ghp- patterns): 0 findings. JWT dev default secret is a clearly labeled non-secret placeholder overridden by `AUTH_JWT_SECRET`.
- `git diff --check`: one cosmetic notice (`app/auth/routes.py:343` new blank line at EOF); recorded, not blocking.

## Acceptance matrix results (commands run 2026-07-24, `-W error`)

| Row | Verdict | Evidence |
|---|---|---|
| A-01 Argon2 storage | PASS | `test_register_stores_argon2_hash_only`: hash prefix `$argon2`, plaintext absent |
| A-02 minimal JWT claims | PASS | claim set exactly `{sub, session_id, iat, exp}` |
| A-03 hardened cookie | PASS | `HttpOnly; SameSite=Lax`; `Secure` env-driven (`AUTH_COOKIE_SECURE`) |
| A-04 logout revocation | PASS | `revoked_at` persisted before cookie clear; replayed JWT → 401 `SESSION_REVOKED_OR_EXPIRED` |
| A-05 expiry enforcement | PASS (expiry) / XFAIL (tokenVersion, QA-TASK03-002) | expired session → 401; version bump not checked |
| A-06 live membership re-read | PASS | membership revoke → uniform 404; disabled user → 401 |
| W-01 uniform 404 | PASS | foreign vs nonexistent workspace responses byte-identical, code `WORKSPACE_NOT_FOUND`, never 403 |
| W-02 no existence oracle | PASS | same test + no leaking words; unauthenticated → uniform 401 |
| W-03 capability projection | PASS | owner projects all four capabilities from role; member limited to stored grants; DB unique membership enforced |
| W-04 own-tenant sanity | PASS | own workspace probe 200 |
| C-01 double-submit issuance | PASS | readable (non-HttpOnly) cookie + matching body token |
| C-02 CSRF enforcement | PASS | missing header / mismatched token / foreign Origin / no Origin+Referer all → 403 `CSRF_VALIDATION_FAILED` |
| C-03 no token leakage | PASS | failure envelope echoes no token values |
| S-01 login rate limiting | DEFERRED | not implemented; disclosed; owned by the security slice task, tracked as QA-TASK03-001 |
| S-02 secret non-leakage + anti-enumeration | PASS | duplicate email → uniform 422; unknown email vs wrong password → identical 401 bodies; no hash/password echo |
| D-01 canonical tables reused | PASS | no new tables/enums; models untouched |
| D-02 migration roundtrip | PASS (n/a new) | no new revision; head roundtrip clean |
| CT-01 contract regeneration | BLOCKED (release gate) | canonical builder output semantically identical to committed `openapi.json` (no illegal drift from this lane); auth endpoints absent pending contract_lead mounting |
| CT-02 no sensitive serialization | PASS | envelopes expose no `passwordHash`/hash fields |
| R-01 full suite | PASS | **108 passed, 1 xfailed** (baseline 84 + QA gates) on candidate + QA tests |
| R-02 ruff + compileall | PASS | product `app` and QA tests clean; compileall exit 0 |
| O-01 owner scope | PASS | see hygiene audit |
| O-02 base freshness | PASS | exact freeze-SHA base; main unadvanced |

## Findings

QA_FINDING
severity: P2
implementation_sha: aa240f78edf812e6f3b1d98a356dea5c56264e9d
location: services/api/app/auth (absent rate limiting dependency)
reproduction:
  - POST /api/auth/login repeatedly with wrong password; no structured 429/limit response ever returned
expected:
  - AGENTS §11: login must use Postgres-backed rate limiting with a structured limit error
actual:
  - No limiter; unlimited online password guessing possible once endpoints are mounted
evidence:
  - code inspection app/auth/routes.py (no limiter dependency); handoff known_risks discloses deferral
required_owner: case_api_data (delivery may land in the security-slice task, but MUST land before public exposure of the login endpoint)
blocks_integration: NO (blocks release exposure, tracked as QA-TASK03-001)

QA_FINDING
severity: P2
implementation_sha: aa240f78edf812e6f3b1d98a356dea5c56264e9d
location: services/api/app/auth/sessions.py:resolve_active_session (~line 50)
reproduction:
  - login; UPDATE user_sessions SET token_version = token_version + 1; replay old JWT → request still succeeds
expected:
  - plan 18 Task 3 Step 2: every request validates unrevoked, unexpired AND tokenVersion
actual:
  - only revocation and expiry are checked; token_version is stored but never enforced (JWT carries no version claim)
evidence:
  - QA test test_token_version_bump_invalidates_live_session (xfail, flips green when fixed)
required_owner: case_api_data
blocks_integration: NO (no exploit path today because revocation covers invalidation; contract-wording deviation tracked as QA-TASK03-002)

Cosmetic (P3, no format block): trailing blank line at EOF `app/auth/routes.py:343`.

## CONTRACT_CHANGE_REQUEST review (QA position: ENDORSE with two notes)

1. Mount `app.auth.routes:router` + `app.tenancy.routes:workspace_router` and call `register_error_handlers(app)` in `app.main` — verified locally: the QA assembly using exactly these steps makes all five endpoints functional and the error envelope uniform. Required before RELEASE_GATE can pass.
2. Regenerate `packages/contracts/openapi.json` + `types.gen.ts` after mounting — correct; QA verified current canonical output is semantically unchanged by this lane (no premature drift).
3. New error codes `AUTH_INVALID_CREDENTIALS` (401) and `WORKSPACE_NOT_FOUND` (404) — behavior verified in tests; doc-10 table addition is consistent. Note: `SESSION_REVOKED_OR_EXPIRED` (401), `CSRF_VALIDATION_FAILED` (403), `MEMBERSHIP_CAPABILITY_REQUIRED` (403) and the uniform 422 `VALIDATION_FAILED` are also emitted by this lane and should be added/confirmed in the same doc-10 update to avoid a second CCR.
4. `.env.example` placeholders `AUTH_JWT_SECRET`, `AUTH_COOKIE_SECURE`, `AUTH_SESSION_TTL_MINUTES`, `AUTH_ALLOWED_ORIGINS` — matches `AuthSettings`; placeholders only, no secrets. Note: consider also documenting `AUTH_SESSION_COOKIE_NAME`/`AUTH_CSRF_*` as optional overrides or explicitly fixing them as non-configurable contract values.

## QA-side additions on this branch

- Acceptance tests updated from skip-gates to live contract assertions (envelope camelCase, exact error codes, `/api/auth/session`, tenancy probe route per `workspace_router` docstring).
- QA app assembly fixture mirrors the CCR mounting steps; a NullPool session override isolates per-test event loops (product's module-level engine pools connections across loops under pytest-asyncio — test-harness concern only, not a product defect).
- No product source, migration, contract, or web file modified by QA.

## Evidence log (fresh commands)

1. `pytest tests -q -W error` (candidate + QA tests, disposable DB): 108 passed, 1 xfailed.
2. `alembic upgrade head` / `alembic check` / `current`: clean, `f850d361ee42 (head)`.
3. `ruff check app <qa tests>`: All checks passed. `compileall app`: exit 0.
4. Canonical OpenAPI probe (build_openapi.py) vs committed: semantically identical (byte delta is CRLF checkout normalization only).
5. Canonical mount check: `app.main` routes = `/health` + docs only → release gate blocker confirmed.
6. Secret scan + `git diff --check` over `2396206..aa240f7`: no secrets; one EOF blank-line notice.
7. Live `git ls-remote`: candidate branch and main SHAs as recorded above.

## Required follow-ups before RELEASE_GATE re-review

1. contract_lead executes the CCR (mount, error handlers, regenerate contracts, doc-10 codes, `.env.example`).
2. QA re-runs: endpoint reachability on canonical `app.main`, `generate_contracts.ps1 -Check`, full suite, and flips CT-01; then RELEASE_GATE re-verdict.
3. case_api_data schedules QA-TASK03-001 (rate limiting) before any public exposure and answers QA-TASK03-002 (tokenVersion) with a fix or an approved contract amendment.
