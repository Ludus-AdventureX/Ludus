# TASK_AUTH_SECURITY_QA_PREP — Login rate limiting + tokenVersion (implementation review)

- QA owner: qa_release (branch `codex/qa-mainline-258a94d`); priority-3 queue item.
- Reviewed implementation: `codex/task-auth-security-hardening` @ **`ac084c7`** (commits `60ef51c` + lifecycle; owner: case_api_data).
- Status: **implementation review + QA test preparation only.** FINAL RELEASE QA IS PENDING the Contract Lead combined HEAD (implementation + `login_rate_buckets` Alembic migration + `.env.example` AUTH_* rate placeholders). No release verdict is issued here.

## Structure audit

- Base: `ac084c7~1... == 258a94d` ancestry verified; changed paths exactly `HEAD`/`HISTORY` + `app/auth/{config,routes,sessions}.py` + `app/security/rate_limits.py` — inside case_api_data scope; the `login_rate_buckets` table is deliberately module-local metadata (not `Base.metadata`) with the migration routed to contract_lead via CCR — correct ownership discipline.
- Secret scan / diff-check over `258a94d..ac084c7`: clean.
- Remote: not yet verified by QA (443 intermittent); final review will re-read live.

## Implementation review notes (code-level, all positive)

- Dual sliding window (per hashed IP, per hashed normalized account) metered **before** any credential work; atomic `INSERT .. ON CONFLICT` upserts; storage failure → same 429 (fail-closed, no unmetered path); success clears the account dimension only; cleanup failure never widens limits; `retryAfterSeconds` bounded and value-only.
- Privacy: bucket keys are SHA-256 digests of `ip:<addr>` / `account:<email>`; raw identifiers never persist.
- tokenVersion: sessions are created with pinned version 1 and `resolve_active_session` rejects any bumped version — closes QA-TASK03-002 by design.

## Prepared QA evidence (services/api/tests/test_auth_rate_limiting.py, 10 tests, run against ac084c7 with the schema created via `ensure_login_rate_schema`)

All 10 PASS; suite total on the review tree: **128 passed, 1 xpassed** (the historical QA-TASK03-002 xfail now XPASSES, confirming the fix):

1. account bucket trips after `login_rate_account_max_attempts` failures → 429 `REQUEST_RATE_LIMITED`;
2. one IP rotating across accounts trips `login_rate_ip_max_attempts` → 429;
3. correct password during throttle still 429 (metering precedes credential work);
4. success clears only the account bucket (row count 0);
5. IP bucket survives successful login;
6. store contains only 64-hex digests — no raw email/IP;
7. missing table (renamed away) → limiter raises 429 fail-closed, never admits;
8. 8 concurrent sessions upsert atomically — total attempts exactly 8;
9. tokenVersion bump rejects a live session with the uniform 401 (formal green twin of the xfail; the xfail marker itself is removed at combined-HEAD review);
10. slices older than the window age out (no eternal throttle).

## Observed sequencing evidence for the migration dependency

Running the full suite on a database **without** the table caused every login in earlier test files to 429 (fail-closed working as designed) until the schema fixture ran. This is exactly why the final release verdict requires the canonical migration in the combined HEAD so `alembic upgrade head` provisions the table before any login path exists.

## Final-review checklist (combined HEAD)

1. Exact combined HEAD declared (implementation + migration + env placeholders); ancestry from current live main.
2. Alembic roundtrip incl. the new revision on a clean PG16; table present after `upgrade head` with the exact DDL the module defines.
3. Full suite `-W error` with **no** `ensure_login_rate_schema` needed (migration provides it) — expected all green with the xfail marker removed (formal tokenVersion test stays).
4. `.env.example` placeholders match `AuthSettings` rate fields; contract drift; ruff/compileall; scope/secret/diff-check; live remote re-read.
