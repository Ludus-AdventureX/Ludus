# TASK_AUTH_SECURITY_FINAL_QA_HANDOFF — combined candidate (impl + migration + env)

- QA owner: qa_release; QA branch `codex/qa-mainline-258a94d`.
- Combined candidate: `codex/task-auth-security-contract-integration` @ **`609a780cffb3184a44e185a6831d64a6b4ec301e`** (product-tree-equivalent tip `7fcce76`; `7fcce76..609a780` verified lifecycle-only).
- **exact_tested_head**: fresh detached worktree at `609a780` (byte-identical product tree, clean before overlay) + QA-owned test overlay from `codex/qa-mainline-258a94d` including this round's xfail-removal edit to `test_auth_sessions.py`. No product file modified by QA.
- Environment: brand-new empty PostgreSQL 16 database (`qa_auth_final_r1` on the disposable container) provisioned **exclusively via Alembic** — no `ensure_login_rate_schema` pre-step.

## Verdicts

- **AUTH_SECURITY_QA_VERDICT: PASS** — P0=0, P1=0, P2=0 new. QA-TASK03-001 (rate limiting) and QA-TASK03-002 (tokenVersion) are both **CLOSED** by this candidate.
- **MIGRATION_VERDICT: PASS** — clean-DB `upgrade head` → `c4a1f0b2d9e7`; roundtrips `→ f850d361ee42 → head → 0001 → head` clean; `alembic check` "No new upgrade operations detected" (env.py registers `rate_limit_metadata` so autogenerate cannot propose dropping the table); live `\d login_rate_buckets` matches the Core Table **column-by-column** (bucket_key VARCHAR(64) NOT NULL, slice_start TIMESTAMPTZ NOT NULL, attempts BIGINT NOT NULL, PK(bucket_key, slice_start) named `pk_login_rate_buckets`).
- **RELEASE_GATE_VERDICT (content): PASS** — all 14 requested items verified (below).
- **REMOTE_PUBLICATION_VERDICT: BLOCKED** — GitHub 443 blocked during this round (QA live `ls-remote` failed); candidate branch unverified on origin; consistent with the Lead's own BLOCKED status. Merge flow requires: network recovery → Lead pushes candidate → live re-read of remote main + candidate + all merged branch refs immediately before merge. No remote result is claimed.

## Requested items 1–14

| # | Item | Result |
|---|---|---|
| 1 | Clean-DB Alembic upgrade/roundtrip/check | PASS (see migration verdict) |
| 2 | Migration vs `rate_limits.py` Core Table column parity | PASS (live psql `\d` compare) |
| 3 | Missing table fail-closed / migrated env login works | PASS — rename-away probe still 429 fail-closed; **on the pure-migration DB every login path in the suite worked with no manual schema step** (alphabetical ordering runs `test_auth.py` logins before the schema fixture ever executes) |
| 4 | Account-dimension limit | PASS (429 `REQUEST_RATE_LIMITED` after `login_rate_account_max_attempts` failures) |
| 5 | IP cross-account limit | PASS (one IP rotating accounts trips `login_rate_ip_max_attempts`) |
| 6 | Correct password still 429 while throttled | PASS (metering precedes credential work) |
| 7 | Success clears only the account bucket | PASS (account rows 0; IP rows persist) |
| 8 | Concurrent ON CONFLICT atomicity | PASS (8 parallel sessions → exactly 8 counted) |
| 9 | retryAfter bounded, no info leak | PASS (integer 60..86400; details carry only retryAfterSeconds; no email echo) |
| 10 | No raw email/IP in store | PASS (all keys 64-hex digests) |
| 11 | tokenVersion bump rejection | PASS (uniform 401 `SESSION_REVOKED_OR_EXPIRED`) |
| 12 | QA-TASK03-002 xfail removed → formal green | DONE (this commit edits `test_auth_sessions.py`; test passes plainly) |
| 13 | `.env.example` placeholders only | PASS (three `AUTH_LOGIN_RATE_*` numeric defaults; no secrets; matches `AuthSettings` fields) |
| 14 | Full suite / ruff / compileall / scope / secret / diff-check | PASS (below) |

## Full test counts (fresh, `-W error`, pure-migration DB)

- **129 passed, 2 skipped, 0 failed, 0 xfailed/xpassed** — skips are the agent-runtime and simulation acceptance files (their candidates are separate branches, not in this tree). The former xfail is now an ordinary passing test.
- Ruff (`app` + tests + migrations): PASS. compileall: exit 0.
- Contract drift: canonical `build_openapi.py` output semantically identical to committed `openapi.json` (no API shape change, matching CCR-20260724-006's no-regeneration decision; `REQUEST_RATE_LIMITED` pre-exists in doc-10).
- Owner-scope audit: implementation tree byte-identical to `ac084c7` (`git diff ac084c7 609a780 -- services/api/app` empty); lead increment exactly the 4 declared files (+lifecycle); zero contracts/web/tests touches. Secret scan + `git diff --check` over `258a94d..609a780`: clean.
- Ancestry: `merge-base(258a94d, ac084c7) == 258a94d`; chain `5d831d4 → 5dab9d5(no-ff merge) → 7fcce76(CCR) → 609a780` verified.

## Findings register

- P0: 0. P1: 0. P2: 0 new; QA-TASK03-001 and QA-TASK03-002 closed. P3: none new.
- Post-merge note for QA baseline hygiene: once this candidate merges, `codex/qa-mainline-258a94d`'s promoted tokenVersion test requires candidates to include `60ef51c`; the QA branch itself is red against pre-fix trees by design (documented, intentional).

## Clearance for Mainline Lead

Content and migration are cleared. Merge only after: network recovery, candidate push, live `ls-remote` of remote main (must still be `258a94d` or re-audit) and the candidate ref. If QA coverage is merged alongside, use exactly the QA tip containing this handoff and the xfail removal; any other QA commit requires re-run.
