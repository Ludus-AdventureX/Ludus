# Ludus

> Ludus is an AI-native decision operating system that turns complex questions into traceable evidence, structured analysis, causal simulations, and human-signed, reviewable decisions.

## Current status

- **Development phase:** Gate 0 validated; Task 2/19A implementation pending
- **Repository visibility:** Private
- **License:** No public license granted; All Rights Reserved
- **Capacity clock:** Not started. Automated Gate 0 passed; the 6-agent/72-hour clock remains conditional on accepting the proven system-Chrome Playwright fallback or acquiring bundled Chromium.
- **Production readiness:** Not ready

See [`LICENSING.md`](LICENSING.md) and [`COPYRIGHT`](COPYRIGHT) before copying, distributing, relicensing, or publishing any part of this repository.

## Authoritative repository and workspace sources

The canonical product, architecture, contract, execution, and acceptance plan is now versioned inside this Private repository. Visual reference and disposable validation artifacts remain external workspace inputs:

| Purpose | Path |
|---|---|
| Product, architecture, contract, execution, and acceptance plan | `docs/product-plan` |
| Final static frontend design reference | `../look` |
| Optional Gate 0 validation slice | `../decision-lab-G0` |
| Final implementation repository | `.` |

`../look` is a static design reference, not a runtime dependency. Production code must not load its `app.js`, and implementation changes must land in this repository rather than modifying the reference directory.

## Gate 0 objective

Gate 0 establishes a reproducible monorepo baseline and verifies, without exposing credentials:

- Python 3.12 with `uv`;
- Node.js 22 and pnpm;
- Docker daemon, Docker Compose, and PostgreSQL 16;
- canonical contract validation and OpenAPI-to-TypeScript drift checks;
- Ways `hardtech-market-direction/1.1.0` and fixture boundaries;
- Look V7 source snapshot integrity and frontend build;
- secure environment configuration;
- real provider probes for text, thinking/reasoning, strict tool calls, and structured output;
- the selected 3/4/6-agent capacity profile.

Offline bootstrap may continue while external services or credentials are unavailable, but it must not report `PREFLIGHT_OK` or start the capacity clock.

## Repository layout (bootstrap target)

```text
apps/web/                 Next.js frontend (Task 1W)
packages/contracts/       Generated OpenAPI/TypeScript contract package
services/api/             FastAPI service
scripts/                  Preflight, provider probe, contract generation, validation, QA teardown
ways/                     Versioned decision-method packages (private core by default)
HEAD                      Current work record
HISTORY                   Append-only completed/prior work history
```

## Environment policy

Do not install global tools, install project dependencies, create `.venv`, start persistent containers, or install browser runtimes without explicit product-owner approval. Secrets belong only in ignored local environment files or the host secret store; never place them in Git, logs, `HEAD`, or `HISTORY`.

QA/gate runs that start a compose stack must use a run-scoped project name (`docker compose -p ludus-qa-<run-id> ... up -d`) and must tear that stack down at the end of the run, pass or fail, via `scripts/qa_teardown.ps1 -Project ludus-qa-<run-id>`. Run `scripts/qa_teardown.ps1 -Inventory` first (read-only `docker ps`) and confirm with the product owner before any cleanup; stopping or removing containers not started by the current run requires separate authorization. A complete gate run must leave no QA containers behind in `docker ps`.

## Work log protocol

`HEAD` describes the current work. Before starting a different work item and when completing the current item, append the existing `HEAD` record to `HISTORY`; then write the new active or idle state to `HEAD`. Existing `HISTORY` entries are append-only.
