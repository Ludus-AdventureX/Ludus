# ANALYSIS RUN VISIBILITY — HANDOFF (r1)

- Branch: `codex/analysis-run-visibility`
- Worktree: `decision-lab-worktrees/analysis-run-visibility` (section 20 layout)
- Base: local `main` `db38e16`; tip `6300dc1`
- Section 20 check: worktree `AGENTS.md` byte-matches canonical (`d9f1f79`) — PASS
- Status: `ready_for_qa`
- Migration: none. Schema/route/DTO/event/error-code changes: none. New deps: none.

## Why this exists

The product owner reported "the analysis worker does not work, the whole flow
does not run, and there is no progress indicator". Running the golden path live
(rather than reading the code) produced a different diagnosis than a code review
had: the worker worked, but **a running analysis was completely invisible**.

## Defects

| id | defect | status |
|---|---|---|
| P0-A | whole run advanced inside ONE transaction → status/progress/heartbeat/SSE invisible until the run finished; a crash discarded the run; `recover_stale_runs` could never see a heartbeat | fixed |
| P0-A' | failure parking re-claimed the GLOBAL queue head (no workspace filter) → could park an innocent run, even another tenant's | fixed |
| P0-B | `FIXTURE_MODE=true` could not complete any analysis: every stage resolved to `{}` → `EmptyModelContentError` → parked within ~3s | fixed |
| P0-C | READY report hook wrote funnel warning STRINGS into a `list[dict]` field; the failure only logged, so any run with an evidence warning reached `ready` with NO report | fixed |
| P1-D | `AnalysisRun.origin_modes` never written → `originModes: []` on every run, live and fixture indistinguishable (section 8 forbids hiding it) | fixed |
| P1 | SSE never closed for a `needs_attention` run → browser EventSource hung on a 50ms server-side poll | fixed |
| P1-E | `packages/contracts/openapi.json` = 56 operations, app serves 69 | **reported, NOT fixed** |

### P0-A evidence (the decisive measurement)

A live run five minutes and six DeepSeek calls deep still read, through the API:

```
status = queued   progress = 0   started_at = NULL   originModes = []
```

with a matching `pg_stat_activity` row: `idle in transaction 00:05:07`.

### P0-B provenance note

`HISTORY` recorded this once as *"fixture-mode deep analysis parks by design
(fixture provider has no registered stage outputs)"*. It is **not** by design:
`compose.prototype.yaml` advertises the worker as deterministic and key-free, and
AGENTS.md section 8 requires the fixture path to run without a key.

### P1-E detail (for the contract/integration lane)

Eleven paths never had contracts regenerated: `auth/invites/redeem`, `invites`,
`invites/{id}/revoke`, `calibration`, `cases/{id}/mentor-reviews`,
`cases/{id}/question-clarifier`, `cases/{id}/sandbox`, `cases/{id}/sandbox/preview`,
`export`, `portfolio`, `purge`. The web app therefore cannot type these endpoints
from the generated package, which section 11 requires. Needs a CCR plus an
official `generate_contracts.ps1` run; out of this lane's write domain.

## Changes

| file | change |
|---|---|
| `app/workers/analysis_worker.py` | injectable `checkpoint` (defaults to `session.commit`); commits at claim / stage entry+heartbeat / packets / each lens / each enrichment / stage completion / terminal transition / report; exposes `claimed`; stamps `originModes`; binds the fixture synthesizer in `build_role_executors_from_env` |
| `app/workers/run.py` | `_park_run(workspace_id, run_id)` replaces `_park_queue_head()`; transaction-ownership docstring corrected |
| `app/workers/fixture_stages.py` | NEW — deterministic per-stage payloads, funnel- and gate-survivable, every fact `[fixture]`-labelled and L6-graded |
| `app/workers/report_builder.py` | `_funnel_quality_findings()` emits structured `evidence_quality` findings |
| `app/agents/model_provider.py` | `FixtureModelProvider.fallback` (None by default, so tests still assert structural failure) |
| `app/analyses/repository.py` | `record_origin_mode()` — idempotent, additive |
| `app/analyses/routes.py` | `_STREAM_CLOSING_STATUSES` = terminal ∪ `needs_attention` |
| `app/analyses/tests/test_run_visibility_and_fixture_path.py` | NEW — 5 tests |
| `app/analyses/tests/test_analysis_sse_and_commands.py` | +1 test (parked-run stream closes) |

## Verification

- Owner suite `app/analyses/tests`: **210 passed** (baseline 204 + 6 new), 0 failed.
- Canonical suite `services/api/tests`: **574 passed** — identical to baseline, zero regression.
- Contract neutrality: this tree's app and main's app emit **identical OpenAPI**
  (69 ops both sides, no added/removed operation, no schema delta) →
  `CONTRACT_NEUTRAL`.
- `ruff check app` clean; `compileall app` clean.
- **Live end-to-end** (DeepSeek `deepseek-v4-pro`, real HTTP; guest → case →
  charter → confirm → run), read from OUTSIDE the worker's transaction while the
  run was executing: `criticizing 0.43 {live}` → `synthesizing 0.57 {live}` →
  `ready 1.0 {live}`; 105 events, 5 research packets, 1 persisted report.
- P0-C proven on that same run: Exa timed out → all sources L6 → the funnel
  raised its 100%-low-trust warning → the report **persisted anyway** carrying
  that warning as a structured `evidence_quality` finding. The previous live run
  (real Exa sources, no warning) has 0 such findings, which is precisely why the
  defect stayed hidden.
- P0-B proven live: with `MODEL_PROVIDER=fixture` the worker drained a backlog of
  queued runs to `ready` at ~0.2s each (previously each was parked within ~3s).

## Notes for QA

1. **Re-run the gates on a run-scoped disposable PG16 project** per section 14.
   This lane ran the owner suite against the shared dev container, so
   `decision_lab` now holds test-created runs in intermediate states.
2. `generate_contracts.ps1 -Check` cannot complete in this worktree: the OpenAPI
   export succeeds, then `openapi-typescript` is missing because worktree
   `node_modules` are not installed (installation needs product-owner approval).
   The OpenAPI-level comparison above answers the drift question for this change.
   Side effects created by that script run: worktree-local `.venv` (uv, 83
   packages) and `.contract-check/` — both gitignored.
3. `HISTORY` append used LF; git warned it will normalise to CRLF on next touch.
   The append-only prefix assertion passed (433248 → 435560 bytes, base verbatim).
4. Scope not covered: `recover_stale_runs` is still not called anywhere (it only
   becomes meaningful now that heartbeats are visible); the fixture path
   synthesizes no lens payloads, so a fixture `full` run still blocks at the
   five-lens audit — an honest verdict, not a crash.
5. Frontend work (progress bar, stage indicator, queued timeout) is the next
   wave and now has real per-stage data to consume.
