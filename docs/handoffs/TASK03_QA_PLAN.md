# TASK03_QA_PLAN — Authentication and Workspace Isolation

- QA owner: qa_release (independent QA/Release Owner, Task 3 lane).
- QA branch: `codex/qa-task-03-auth-workspace`.
- Baseline: `contract_freeze_sha 239620681f88c525912c2e1d8b23483a5f362a5e` (= remote `refs/heads/main`, verified live via `git ls-remote` before branching).
- Implementation owner: `case_api_data` (secondary `web_ux` for login page/client); contract changes route to `contract_lead`. Per manifest `source_fix_policy: handoff_to_original_owner`, QA never edits product source.
- QA write scope actually used: `services/api/tests/**`, `docs/handoffs/**`, `HEAD`/`HISTORY`.

## 1. Baseline facts (frozen main)

- `services/api/app/auth/**`, `app/security/**`, tenancy routes, and CSRF do not exist yet; API exposes only `GET /health`. OpenAPI contains no auth/workspace path.
- Task 19A already delivered the persistence contracts the implementation must consume, with real PostgreSQL constraints: `users` (unique email, argon2 hash column), `user_sessions` (`token_version > 0`, `revoked_at`, `expires_at`), `workspace_memberships` (unique workspace+user, `role owner|member`, `capabilities workspace_capability[]`), workspace-scoped uniques and cross-workspace FK rejection.
- Baseline regression suite: 84 passed with `-W error` (fresh run recorded below).

## 2. Acceptance matrix

IDs are stable; every implementation handoff must map its evidence to these rows.
Verdict values: PASS / FAIL / BLOCKED / NOT-RUN.

| ID | Requirement (source) | Verification |
|---|---|---|
| A-01 | Register/login uses Argon2 password hashes; no plaintext or reversible storage (18#task-3 Step 2) | `test_auth.py`: register then inspect `users.password_hash` prefix `$argon2`; login round-trip |
| A-02 | JWT contains only `sub`, `session_id`, `iat`, `exp`; no role/workspace claims (18#task-3 Step 2) | decode token payload in `test_auth_sessions.py`; assert exact claim set |
| A-03 | Session cookie is `HttpOnly; SameSite=Lax`; `Secure` env-controlled (Step 4, AGENTS §11/12) | inspect `Set-Cookie` attributes |
| A-04 | Logout atomically sets `revoked_at` before clearing cookie; revoked JWT fails before `exp` (Step 4) | `test_auth_sessions.py`: logout, replay old cookie -> 401; DB shows `revoked_at` set |
| A-05 | Expired or `token_version`-bumped session rejected on every request (Step 2) | force-expire / bump version in DB, replay -> 401 |
| A-06 | Every sensitive request re-validates active session + WorkspaceMembership + capability from DB, not JWT claims (AGENTS §5) | revoke membership after login; request -> 404 |
| W-01 | All `/api/workspaces/{id}/...` routes depend on `require_workspace_context`; non-member access returns uniform 404, not 403 (Step 3, AGENTS §5) | `test_workspace_isolation.py`: member of ws_a requests ws_b resource -> 404; body identical to true-missing 404 |
| W-02 | No existence leak via error message, count, timing-obvious body, or SSE (AGENTS §5) | compare 404 bodies/status for existing vs nonexistent foreign resource |
| W-03 | `WorkspaceContext` projects `contribute|review|sign|manage_connectors`; `sign` never granted to non-human/worker principals (AGENTS §5) | capability projection unit tests; negative grant test |
| W-04 | Workspace switch re-derives membership; stale/cached foreign workspaceId rejected (Step 5) | switch flow test with revoked second membership |
| C-01 | `GET /api/auth/csrf` issues double-submit token (Step 5A) | `test_csrf.py`: token issued, readable cookie + header pair |
| C-02 | All cookie mutations (register/login/logout onward) enforce exact `Origin` or same-origin `Referer` + constant-time token compare; failure -> `CSRF_VALIDATION_FAILED` (Step 5A, AGENTS §11) | mutation without header, with mismatched Origin, with token mismatch -> structured error |
| C-03 | CSRF failure does not leak token values or internals in body/logs | assert error envelope fields only |
| S-01 | Login and other auth endpoints rate-limited via Postgres-backed limiter (AGENTS §11) | burst login attempts -> structured 429/limit error |
| S-02 | Auth responses/logs never contain password, hash, JWT secret, or full token echo (AGENTS §12) | response body scan in tests |
| D-01 | Implementation reuses Task 19A canonical tables; no parallel session/user/membership tables or enums (AGENTS §5) | schema diff: no new tables beyond migration-approved set; `alembic check` clean |
| D-02 | Any new migration upgrades AND downgrades cleanly on a clean PostgreSQL 16 (AGENTS §14) | roundtrip: upgrade head / downgrade previous / re-upgrade / `alembic check` |
| CT-01 | New auth/workspace endpoints appear in regenerated OpenAPI + TypeScript with canonical wire IDs; no drift (AGENTS §5/13) | `generate_contracts.ps1 -Check` -> `CONTRACT_DRIFT_OK` |
| CT-02 | No legacy wire IDs, no sensitive fields (password/nonce hashes) serialized in OpenAPI | Decision OS verifier + targeted schema assertions |
| R-01 | Baseline regression: full API pytest `-W error` stays green (84 baseline tests + new ones) | full suite run |
| R-02 | Ruff + compileall over changed tree pass | lint run |
| O-01 | Changed paths confined to manifest scope: `services/api/app/auth/**`, `app/tenancy/**` (+ approved secondary web scope); tests only from QA (AGENTS manifest) | `git diff --name-only base..handoff` audit |
| O-02 | Handoff base is fresh frozen main; no stale base, no reuse of pre-freeze branches | ancestry check `merge-base` |

## 3. Regression baseline (must never regress)

Recorded on QA branch creation, all commands run from `services/api` with a disposable PostgreSQL 16 migrated to head:

1. `pytest tests -q -W error` — 84 passed (baseline, before QA gate tests added).
2. `alembic upgrade head` + full downgrade/re-upgrade roundtrip + `alembic check` — clean.
3. `generate_contracts.ps1 -Check` — `CONTRACT_DRIFT_OK`.
4. `verify_decision_os_contracts.py` — PASS 7/7 groups.
5. `ruff check` + `compileall` — pass.

## 4. QA gate tests added on this branch (implementation-independent)

New files under `services/api/tests/` use `pytest.importorskip` so they SKIP cleanly on the frozen baseline and automatically become live acceptance tests when `app.auth` / `app.security` land:

- `conftest.py` — shared async DB fixtures: rollback-only connection, tenancy factory (two workspaces, two users, memberships with distinct capabilities), API client factory bound to `app.main:app`.
- `test_auth.py` — A-01, A-03, S-02 rows.
- `test_auth_sessions.py` — A-02, A-04, A-05, A-06 rows.
- `test_workspace_isolation.py` — W-01, W-02, W-03, W-04 rows (plus DB-level negative tests that already run on baseline).
- `test_csrf.py` — C-01, C-02, C-03 rows.

Rows S-01, D-01/D-02, CT-01/CT-02, R-*, O-* are executed as commands/audits at handoff review time and recorded in the QA_HANDOFF evidence log.

## 5. Handoff review protocol (per IMPLEMENTATION_HANDOFF)

1. Verify handoff declares: implementation branch, HEAD SHA, base SHA; base must equal or descend from `2396206` and be current main at review time.
2. Check out the handoff SHA in a fresh clean worktree; never review in the implementer's dirty tree.
3. Run changed-path audit against manifest owner scope (O-01); any out-of-scope path is an automatic finding routed to the violating owner.
4. Run the full matrix; record每行 verdict + command + output digest in QA_HANDOFF.
5. P0/P1 findings use the QA_FINDING format (severity, implementation_sha, location, reproduction, expected, actual, evidence, required_owner, blocks_integration) and route to `case_api_data` / `web_ux` / `contract_lead`; QA does not patch product source.
6. Final verdict issued only after fresh reruns of R-01/R-02, D-02, CT-01 on the handoff SHA.

## 6. Out of scope for this QA lane

- Writing or fixing any product source (`services/api/app/**`, `apps/web` implementation files, migrations, contracts).
- Merging or pushing `main`; integration authority stays with the Mainline Audit/Integration owner.
- Task 19A QA branches (archive-only; must not be reused).
