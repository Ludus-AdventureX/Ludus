# SIMULATION_ALPHA runbook — seed + smoke (prototype)

Scope: `SIM_ALPHA_SEED_SMOKE_FAST` on branch `codex/prototype-sim-seed-smoke`
(base `d2ae634`). Two scripts, one fixture, no product-code or migration
changes:

- `scripts/seed_simulation_alpha.py` — idempotent seeder for the demo scope;
- `scripts/smoke_simulation_alpha.py` — csrf → login → run → replay smoke;
- `fixtures/simulation-alpha/seed/simulation_alpha.json` — frozen seed payload.

## Prerequisites

1. PostgreSQL 16 reachable and migrated to this baseline:

   ```powershell
   $env:DATABASE_URL = "postgresql+asyncpg://<user>:<pass>@localhost:<port>/<db>"
   Set-Location services/api
   python -m alembic upgrade head
   ```

2. Environment variables (never committed, never printed):

   | Variable | Meaning |
   | --- | --- |
   | `DATABASE_URL` (or `POSTGRES_*`) | target database for seed + smoke |
   | `SIMULATION_ALPHA_DEMO_PASSWORD` | demo login password, >= 8 chars, env-only |

   The demo password lives **only** in the environment. The fixture and the
   JSON summaries carry no credentials; the seeder re-aligns the stored Argon2
   hash whenever the env password changes.

## Seed

```powershell
python scripts/seed_simulation_alpha.py
```

Seeds (in FK order): demo user → workspace + owner membership → decision
subject/case anchor → analysis run + ready `scenario_planning` lens artifact
(scenario provenance) → confirmed graph version with 4 nodes / 4 edges →
strategy / scenario / score-definition versions → decision-maker profile
(append-only repository path; `content_hash` computed server-side).

Output: a JSON summary with `demoEmail`, `workspaceId`, `caseId`, `graphId`,
all version IDs (`graphVersionId`, `strategyVersionId`, `scenarioVersionId`,
`scoreDefinitionId` + `scoreDefinitionVersion`), and the profile
`profileId`/`version`.

Idempotency: every row UUID is uuid5-derived from the fixture, and each insert
is guarded by a natural-key lookup — re-running converges on the same rows and
prints the same summary.

## Smoke

```powershell
python scripts/smoke_simulation_alpha.py
```

The SIM-02A run routes are now real product surface (mounted under the
tenancy-guarded `workspace_router`), so the smoke drives the canonical app
in-process through httpx `ASGITransport`, passing the production
auth/CSRF/tenancy/idempotency dependencies:

1. `GET /api/auth/csrf` — double-submit token;
2. `POST /api/auth/login` — demo credentials (env password);
3. `POST /api/workspaces/{workspaceId}/simulations/{graphId}/runs`
   (with `Idempotency-Key`), then an idempotent re-POST replay;
4. `GET .../runs/{simulationRunId}` — replay.

Asserted contract:

- create answers **201**, or the contract non-convergence **409** envelope
  (`ok=false`, `error.code=SIMULATION_NOT_CONVERGED`);
- the run ID exists (valid UUID);
- `engineVersion == sim-engine-1.1.0`;
- `inputHash` present and matches `sha256:<64 hex>`;
- the idempotent re-POST replays the identical payload with
  `meta.idempotencyReplay = true`;
- the replay payload equals the creation payload exactly.

Exit code 0 + `SMOKE PASS` on success; non-zero with `SMOKE FAIL: <reason>`
otherwise. Each smoke invocation persists one new `simulation_runs` row (runs
are append-only history by design).

## Targeted verification (what CI/reviewers run)

```powershell
python -m compileall scripts/seed_simulation_alpha.py scripts/smoke_simulation_alpha.py
python scripts/seed_simulation_alpha.py   # run twice to witness idempotency
python scripts/seed_simulation_alpha.py
python scripts/smoke_simulation_alpha.py
```

## Troubleshooting

- `SIMULATION_ALPHA_DEMO_PASSWORD must be set` — export the env var; it is
  intentionally absent from `.env.example` and the repo.
- Login 403 `CSRF_VALIDATION_FAILED` — the smoke already sends the matching
  `Origin`; if `AUTH_ALLOWED_ORIGINS` is set in your env it must include
  `http://simulation-alpha.local` or be left empty.
- Login 429 — the P2-001 rate limiter counts failed attempts per IP/account;
  wait out `AUTH_LOGIN_RATE_WINDOW_MINUTES` or reseed a fresh database.
- `CASE_NOT_FOUND` from the run route — seed and smoke are pointing at
  different databases; both read the same `DATABASE_URL`.
