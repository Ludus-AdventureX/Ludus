# Ludus

> Ludus is an AI-native decision operating system that turns complex questions into traceable evidence, structured analysis, causal simulations, and human-signed, reviewable decisions.

## Current status

- **Development phase:** Gate 0 offline bootstrap
- **Repository visibility:** Private
- **License:** No public license granted; All Rights Reserved
- **Capacity clock:** Not started. The 6-agent/72-hour Hackathon Prototype clock begins only after Gate 0 passes.
- **Production readiness:** Not ready

See [`LICENSING.md`](LICENSING.md) and [`COPYRIGHT`](COPYRIGHT) before copying, distributing, relicensing, or publishing any part of this repository.

## Authoritative workspace sources

In the current development workspace, the canonical sources are external sibling directories:

| Purpose | Local path |
|---|---|
| Product, architecture, contract, execution, and acceptance plan | `../decision-lab-product-plan` |
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
scripts/                  Preflight, provider probe, contract generation, validation
ways/                     Versioned decision-method packages (private core by default)
HEAD                      Current work record
HISTORY                   Append-only completed/prior work history
```

## Environment policy

Do not install global tools, install project dependencies, create `.venv`, start persistent containers, or install browser runtimes without explicit product-owner approval. Secrets belong only in ignored local environment files or the host secret store; never place them in Git, logs, `HEAD`, or `HISTORY`.

## Work log protocol

`HEAD` describes the current work. Before starting a different work item and when completing the current item, append the existing `HEAD` record to `HISTORY`; then write the new active or idle state to `HEAD`. Existing `HISTORY` entries are append-only.
