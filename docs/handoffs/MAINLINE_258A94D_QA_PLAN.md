# MAINLINE_258A94D_QA_PLAN — Acceptance matrices for the post-Task-3 parallel lanes

- QA owner: qa_release; QA branch `codex/qa-mainline-258a94d`.
- Baseline: main `258a94df9c7663ab2257d54d3a05b5e7e7c1dfae` (live `ls-remote` verified; supersedes freeze `2396206`). No Task 3 QA branch reused.
- Baseline regression (re-run fresh on this SHA, not inherited from r3): full API suite **118 passed / 1 xfailed** (`-W error`, disposable migrated PG16); `alembic upgrade head`+`check` clean (`f850d361ee42`); Decision OS verifier PASS (tasks=26, validators=9, ways 1.1.0 active); OpenAPI/types drift OK (script-equivalent normalized compare + `openapi-typescript 7.13.0`); ruff + compileall PASS.
- Standing registered findings carried over: QA-TASK03-001 (P2, login rate limiting — becomes a **Security Hardening lane acceptance row**, see SH-01), QA-TASK03-002 (P2, tokenVersion enforcement, xfail in place), P3 EOF blank line `auth/routes.py:343`.

## Common gate applied to every IMPLEMENTATION_HANDOFF (all lanes)

| ID | Check |
|---|---|
| G-01 | Base freshness: candidate base = current live remote main at review time (`merge-base` ancestry; live `ls-remote` re-read) |
| G-02 | Changed-path audit vs `agent-work-manifest.yaml` owner write_scope; zero out-of-scope paths; no `**/schemas.py`/contracts/migrations edits unless the owner is contract_lead or an accepted CCR exists |
| G-03 | Full API suite `-W error` on fresh migrated disposable PG16; no baseline regression (118/1xfail floor) |
| G-04 | Alembic upgrade/downgrade/re-upgrade + `alembic check` when migrations change; clean-database bootstrap |
| G-05 | Contract drift (canonical builder + types regeneration) and Decision OS verifier |
| G-06 | Ruff, compileall; `pnpm --dir apps/web test` + `build` when apps/web changes |
| G-07 | Secret/IP/publish-scope scan over the candidate diff; `git diff --check`; no LICENSE/visibility changes |
| G-08 | Review in a fresh detached worktree at the exact declared HEAD; QA overlay is non-destructive; QA_HANDOFF records exact_tested_head |
| G-09 | P0/P1 → QA_FINDING routed to the manifest owner; QA never patches product source |

## Lane 1 — Security Hardening (owner: case_api_data; scope app/security/**, app/files/**, app/connectors/**, docs/security-exceptions.md)

| ID | Requirement (source) | Verification |
|---|---|---|
| SH-01 | Postgres-backed rate limiting on login/high-cost/connector/upload with structured limit error (AGENTS §11; closes QA-TASK03-001) | burst tests → structured 429; limits persisted in PG, not memory |
| SH-02 | Upload validation: type/size/filename/path traversal/Workspace ownership; PDF magic/MIME, TXT/MD encoding policy (AGENTS §12) | negative upload battery incl. `../` names, oversized, spoofed MIME |
| SH-03 | Shared filesystem ArtifactStore `put/open/stat` only; workspace-scoped paths; DB stores relpath+hash+size; reads re-check ownership; no static direct links (AGENTS §4/12) | API/Worker/Renderer visibility test; cross-tenant 404; direct-path probe fails |
| SH-04 | BYOK connectors: audited catalog only (Exa/Firecrawl/Tavily), AES-256-GCM via CONNECTOR_MASTER_KEY, ciphertext+nonce+key-version+mask only in DB; no full key in any response/SSE/log (AGENTS §8/12) | encryption round-trip; masked responses; log/error scan |
| SH-05 | Connector states exactly `available|missing_credentials|invalid_credentials|rate_limited|quota_exhausted|provider_error|disabled` | enum + transition tests |
| SH-06 | SSRF-safe outbound client: approved-IP pinning, Host/SNI preserved, re-resolve per redirect (AGENTS §11) | redirect/rebind negative probes |
| SH-07 | Cross-tenant uniform 404 preserved across all new security endpoints; no existence oracle | anti-oracle byte-compare |
| SH-08 | QA-TASK03-002 disposition: fix or approved amendment | xfail flip or CCR reference |

## Lane 2 — Agent Runtime (owner: ways_agent_pipeline; scope app/agents/**, app/methods/**, app/workers/**, method-packs/**)

| ID | Requirement | Verification |
|---|---|---|
| AR-01 | ModelProvider abstraction only; env-driven MODEL_*; no vendor fields in business contracts (AGENTS §8) | code audit + fixture provider tests |
| AR-02 | `reasoning_content` never persisted: absent from DB, events, tool trace, logs, fixtures (AGENTS §8) | targeted scan tests over run artifacts |
| AR-03 | Tool registry exposes only read-only `search_web/fetch_url/crawl_site/extract_document/get_source_status`; no `sign_decision`/`transition_to_decided` anywhere in agent tool surface (AGENTS §5/7) | registry snapshot assertion |
| AR-04 | Worker claims AnalysisRun via `SELECT ... FOR UPDATE SKIP LOCKED`; duplicate-claim protection, heartbeat/attempt persisted; interrupted runs recover or land in `needs_attention` (AGENTS §3/7) | two-worker contention test; kill/resume test |
| AR-05 | Run state machine: exact enum, `blocked/cancelled` terminal, three canonical RunResolutions only, amendment → new Run with supersession (AGENTS §5/9) | state-transition matrix tests |
| AR-06 | SSE: fixed categories, monotonic sequence, `Last-Event-ID` resume, per-Run scope isolation (AGENTS §3/9) | resume/no-crosstalk tests |
| AR-07 | Budgets/depth/iteration hard caps for delegated tools; subset permissions (AGENTS §7) | envelope violation tests |
| AR-08 | Method pack immutability: published hash re-check, no runtime read of `ways/`, no hot reload (AGENTS §6) | loader negative tests (existing suite baseline) |
| AR-09 | originMode single value on artifacts; events keep origin + sourceOriginModes[] (AGENTS §8) | schema/DB assertions |

## Lane 3 — Web/UX (owner: web_ux; scope apps/web/** except tests/simulation; QA owns apps/web/tests/**)

| ID | Requirement | Verification |
|---|---|---|
| WX-01 | Look V7 five workspaces IA; first screen is working Q&A, no marketing/template wall (AGENTS §2/11) | Playwright golden-path + snapshot review |
| WX-02 | Theme tokens only; public IDs `ink/ledger/.../purple`; semantic tokens for Human/Analysis/Unknown & statuses; no hex in JSX (AGENTS §11) | token lint + design-debt scan of changed files |
| WX-03 | HTTP/SSE types imported from `packages/contracts` generated client; no hand-written parallel DTOs; generated files unmodified (AGENTS §11) | import audit + drift check |
| WX-04 | Auth client: `credentials:"include"`, CSRF header wiring, no cached foreign workspaceId (task-03 secondary scope) | Vitest against mock contract |
| WX-05 | Core components cover loading/empty/error/partial/unsupported/blocked/needs_attention/recovery/fallback states (AGENTS §11) | Vitest state coverage per changed component |
| WX-06 | Accessibility: aria-labels on icon buttons, keyboard path for create/clarify/switch/run/save, color not sole signal (AGENTS §11) | axe/Playwright a11y run |
| WX-07 | Responsive: 1440x900 primary, 390x844 mobile acceptance, 768-1199 drawer layout; no text overflow (AGENTS §11) | Playwright viewport sweep + screenshot review |
| WX-08 | `focused` hides report/PDF/sandbox controls; `unsupported` keeps chat/quick with formal features disabled in UI (AGENTS §6/11) | gated-control tests |
| WX-09 | `pnpm --dir apps/web test` + `build` green | fresh run |

## Lane 4 — Simulation/Graph (owner: simulation_graph; scope app/simulations/**, apps/web/components/simulation/**)

| ID | Requirement | Verification |
|---|---|---|
| SG-01 | Engine is a deterministic pure function: identical versions/riskTolerance/engineVersion/epsilon/maxSteps → identical inputHash and results (AGENTS §10) | repeat-run hash equality; property tests |
| SG-02 | Effect formula exactly `delta*polarity*strength*edgeMultiplier*damping`; relationshipQualityScore never enters numeric effect (AGENTS §10) | numeric fixture assertions |
| SG-03 | Normalized baseline before engine; no raw business-unit arithmetic (AGENTS §10) | unit conversion tests |
| SG-04 | GraphVersion `draft/confirmed/archived` immutable after save; ScenarioVersion immutable; no riskTolerance in ScenarioVersion (AGENTS §5/10) | DB constraint + API rejection tests |
| SG-05 | Formal SimulationRun pins graph/strategy/scenario/scoreDefinition/profile IDs+versions, engineVersion, epsilon, maxSteps, inputHash (AGENTS §10; Task 19A fields) | persistence assertions (extend existing 19A coverage) |
| SG-06 | experimental vs formal authorization: draft graphs only experimental; previews bind revision, go stale, never enter PDF/decision (AGENTS §10) | authorization negative tests |
| SG-07 | Non-convergence/saturation/invalid numeric/hard-constraint → structured status, excluded from formal recommendation (AGENTS §10) | boundary fixtures |
| SG-08 | Branch/compare/non-destructive rollback preserve history (AGENTS §10) | version-chain tests |
| SG-09 | Spherical-robot fixture: ≥8 nodes, ≥10 edges, 3 scenarios, sensitivity ordering, procurement-delay recommendation flip (AGENTS §10) | fixture acceptance run |

## Lane 5 — Five Lenses (owner: ways_agent_pipeline; scope app/strategic_lenses/**, method-packs, worker steps)

| ID | Requirement | Verification |
|---|---|---|
| FL-01 | Exactly five lens types produced by the mandated roles: Research→porter_five_forces; Critic→pre_mortem + counterparty_response_matrix; Synthesis→scenario_planning + meadows_leverage_points; not five new workers (AGENTS §6/7) | producerRole assertions per artifact |
| FL-02 | Execution order: Research → Critic/Safety Anchor → Counterparty → Pre-Mortem → adversarial review → Synthesis → Validation; Counterparty strictly before Pre-Mortem (AGENTS §7) | event-sequence assertions |
| FL-03 | Each lens runs its method-pack Prompt + discriminated JSON schema; artifact stores method/prompt/schema versions and claim/evidence/assumption references (AGENTS §7) | schema validation + reference resolution tests |
| FL-04 | Model returns identity-free StrategicLensOutput; server injects all identity/origin/hash fields; model-supplied identity rejected (AGENTS §7) | injection negative tests |
| FL-05 | Missing any lens blocks `ready`/PDF/formal sandbox (AGENTS §6) | validation-gate negative test |
| FL-06 | StructuredReport references accepted immutable artifacts via lensArtifactIds (AGENTS §7) | report linkage tests |
| FL-07 | 31-Skill dual-ledger counts unchanged (13/7/8/1/2) unless a CCR updates both ledgers (AGENTS §6) | verifier + ledger diff |

## Review workflow per handoff

1. Fresh detached worktree at the declared HEAD; G-01..G-09 first; lane matrix second.
2. Independent evidence per candidate: commands + outputs digested into a per-lane `TASK<±>_QA_HANDOFF.md` with exact_tested_head; one handoff per IMPLEMENTATION_HANDOFF.
3. P0/P1 emitted as QA_FINDING (severity/sha/location/reproduction/expected/actual/evidence/required_owner/blocks_integration) routed to the manifest owner; content verdicts separate from remote-publish verdicts; remote claims only after live `ls-remote`.
