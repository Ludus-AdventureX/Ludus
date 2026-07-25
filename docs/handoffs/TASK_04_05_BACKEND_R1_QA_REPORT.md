# QA Report — Task 4/5 Backend r1 (adversarial verification)

- QA lane: `codex/qa-task-04-05-backend-r1` (independent worktree, offline venv from uv cache, zero installs)
- Candidate: `codex/task-04-05-backend-r1` @ `a51a4f9af63312e031e00581635dbf86ca64a3a9` (chain `4941e58 -> 6edeb4a -> a51a4f9`, remote ls-remote exact)
- Verdict: **PASS** — with two QA-owned revisions (F1/F2) carried on this tip; both are additive test/registration fixes, no product-code change.

## Special constraint compliance (migration scope ruling)

No alembic command was executed on the candidate tree — `a7c3e9f1b5d8` has a
by-design dangling parent `b6e8f3a1d7c2` whose FILE lives on the A1 branch
(`codex/task-10-quality-gate-r1` @ `82ee67c`).

1. **Static review** — `a7c3e9f1b5d8_add_dossier_version_snapshots.py` vs
   `app/dossiers/models.py` metadata, column by column: PK `id` (uuid,
   `gen_random_uuid()`), `workspace_id` FK→workspaces CASCADE,
   `dossier_version_id` FK→dossier_versions CASCADE, `entries` JSONB NOT NULL
   `'[]'::jsonb`, nullable `decision_maker_profile_version` / `subject_version`
   integers, `created_at` timestamptz `now()`,
   UNIQUE(`workspace_id`,`dossier_version_id`) = **MATCH**.
   DB-level cross-check: `information_schema.columns` + `pg_get_constraintdef`
   of the migration-built table (merged scratch DB) vs the metadata
   `create_all`-built table (fresh DB) = **zero diff**.
2. **QA-7 tripwires** independently re-run: 2 passed.
3. **Bonus (done)** — local-only scratch worktree, `82ee67c` + `a51a4f9`
   temp no-ff merge (conflicts confined to HEAD/HISTORY lifecycle files;
   worktree NEVER pushed, discarded after use). On disposable DB
   `qa0405_merge_lc` (one-time PG16 `ludus-pg-mainline-w1` @55447 reused):
   - `alembic heads` = single **`a7c3e9f1b5d8`** (convergence confirmed)
   - `upgrade head` clean → `downgrade -1` = `b6e8f3a1d7c2` → re-`upgrade` clean
   - `alembic check`: **FAILED before F1, passes after** (see F1)
   The integration wave may cite this lifecycle result.

## Findings

| # | Severity | Finding | Resolution |
|---|----------|---------|------------|
| F1 | P2 (merged-chain gate breaker) | `migrations/env.py` lacked `import app.dossiers.models`; on the merged chain `alembic check` reports a spurious `remove_table dossier_version_snapshots` drift | One-line import added on this QA tip; verified: merged-chain `alembic check` = "No new upgrade operations detected" |
| F2 | P2 (canonical-suite breaker) | `tests/test_models.py` exact-table-set equality was test-selection-order dependent: co-running any dossiers test registers `dossier_version_snapshots` and flips the assertion (reproduced on the candidate tree: `test_models.py + test_dossier_versions.py` = 1 failed) | Equality KEPT (not relaxed): expected set extended with `dossier_version_snapshots` + deterministic `import app.dossiers.models` (same pattern as the Task 8/9 QA directive); repro combo now 38 passed |
| F3 | Info (pre-merge state only) | Candidate-tree full suite with `-W error` promotes the alembic dangling-parent `UserWarning` to 1 failure in `app/evidence/tests/test_evidence_models.py` (chain-robustness test loads `ScriptDirectory`) | Not a candidate defect: on the merged scratch chain the same file = 23 passed. Disappears when the wave unites the branches. No change made |

## Gates

| Gate | Result |
|------|--------|
| Owner tests independent re-run (dossier_versions 11 + memory_extractor 13 + qa_battery 9) | **33 passed** (fresh DB `qa0405_fresh`, migrated to `f9a4b7e2c8d3` via the scratch tree — candidate tree ran zero alembic) |
| Regression smoke (agent_runtime / models / decision_os_invariants / simulation_engine) | **81 passed** |
| Adversarial battery `tests/test_task0405_qa_adversarial_r2.py` (NEW, ≥6 required) | **12 passed** — ADV-1 reject/pending negative matrix + snapshot payload scan; ADV-2 stale-confirm 409 leaves zero partial writes (entries/versions/case_versions/events counted, loser stays pending); ADV-3 snapshot + companion byte-stability across later formal edits, companion append-only 1-per-version; ADV-4 WRITE-path anti-enumeration (confirm/reject foreign candidate) byte-identical 404 bodies; ADV-5 opt-out ("临时想法"/"不要记住"/"off the record") → zero candidate rows AND zero extraction model calls (call-count audited); ADV-6 hostile envelope injecting `reasoning_content` (top-level + nested) → absent from response, messages, candidate proposals, domain_events, and `information_schema` column scan; ADV-7 `complete_structured_checked` repair budget exactly one retry (empty→valid = 2 calls; invalid×2 raises after exactly 2 calls with findings; empty×2 raises EmptyModelContentError); ADV-8 fixture determinism under adversarial key order/unicode payloads |
| Provider gate ③ | Covered by ADV-7 (empty-content single repair path) + ADV-8 (determinism); owner QA-6 also re-ran green inside the 33 |
| F2 repro combo (`test_models` + `test_dossier_versions` + `qa_battery` same process) | **38 passed** after F2 |
| Candidate full suite (`tests` + simulations + evidence + analyses, `-q -W error -rxX`) | 829 collected: **828 passed / 1 failed = F3** (adjudicated pre-merge-only; merged chain re-check green) |
| merge-base scope audit (`git diff 4941e58 a51a4f9 --name-only`) | Exactly the declared write scope: HEAD/HISTORY/handoff + `app/agents/model_provider.py` + new `app/cases|conversations|dossiers/**` + migration `a7c3e9f1b5d8` + own tests. Zero forbidden-domain files |
| CONTRACT_DRIFT_OK | Official script OpenAPI regeneration byte-identical to canonical `packages/contracts/openapi.json`; TS regen via `openapi-typescript` 7.13.0 (primary-worktree CLI, owner-run precedent) byte-identical to `types.gen.ts`. Unmounted relative routers → wire surface unchanged |
| Static | ruff clean (QA files), compileall clean, `git diff --check` clean, conflict-marker scan 0, secret scan clean |

## Integration-wave handoff notes

- Merge order MUST be **A1 first** (`a7c3e9f1b5d8`'s parent file is in A1's chain).
- Expected post-merge single head: `a7c3e9f1b5d8` (verified on scratch).
- `migrations/env.py` will conflict textually with A1's import block — keep
  BOTH import blocks (pure semantic merge; both are `# noqa: F401` registrations).
- QA-7's in-worktree head-pair assertion `{f9a4b7e2c8d3, a7c3e9f1b5d8}` is
  documented to collapse to a single head post-merge; the wave should re-pin it
  (or the owner's follow-up does) — the test's own comment states this.
- F3 self-resolves on the merged chain (evidence file 23 passed there).
