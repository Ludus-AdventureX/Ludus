# SIM_ENG_02_PROFILE_AWARE_INPUT_HASH_R1_HANDOFF

- Task: CCR-ENG-02 P2 — profile-aware input hash, `sim-engine-1.1.0`
- Role: Simulation/Graph Owner (Fable5 throughout)
- Date: 2026-07-25 (Asia/Shanghai)
- Product branch: `codex/sim-eng-02-profile-aware-input-hash-r1`
- **Exact parent: `edaa8421c330de7cfe02a53c1e38574533e99c48`** (P1/P3 exact QA combination) —
  direct-parent proof: `git rev-list --parents -n 1` of the product head shows edaa842 as the
  sole parent; the branch was created `worktree add -b ... edaa842` in a fresh worktree; no
  bare-fb75b8f start, no hand-copied QA assets, no merge/cherry-pick of any contract branch.
- Authoritative contracts consumed READ-ONLY via `git show`:
  - CCR-ENG-02 `codex/ccr-eng-02-profile-aware-input-hash-r1 @ c8c9167b219fa8aa06bf9769776f49706f43b219`
    (verified direct child of the SIM-02A contract 0289b2e)
  - CCR-SIM-02A `@ 0289b2e36a7765891e4f1908231ac2384c541318` + SIM-02A-ADDENDUM-A1 (erratum)
- Baselines live-verified at lane start: main `387041d4…`, P1/P3 product `fb75b8f5…`,
  QA parent `edaa8421…`, both contract SHAs; edaa842 product bytes == fb75b8f (QA delta =
  tests/handoff/HISTORY only); migration head exactly `b2c7e9d4a1f6`.
- ready_for_independent_qa: **YES**
- ready_for_public_route: **NO** (SIM-02A §2/§3 double-lock: I1/I2/I3 still pending)

## 1. Changed paths (exact)

| Path | Change |
|---|---|
| `services/api/app/simulations/domain.py` | + `ProfileFingerprint` frozen/slots engine-internal value object (id: str, version: int, content_hash: str) — non-ORM, non-wire, never HTTP-exposed |
| `services/api/app/simulations/engine.py` | `ENGINE_VERSION = "sim-engine-1.1.0"`; `compute_input_hash`/`run_simulation` gain keyword-only `profile: ProfileFingerprint \| None = None`; payload gains the nested §2 `profile` block when supplied; bare dicts rejected (`SimulationInputError`); ZERO numeric changes |
| `services/api/app/simulations/assembly.py` | + `assemble_profile_fingerprint(row)` — the mandatory format gate (§3) at the ORM→domain boundary: regex `^sha256:[0-9a-f]{64}$`, version ≥ 1 int, canonical lowercase UUID; violations raise `FrozenReferenceError` (`frozen_reference_incomplete`) |
| `services/api/app/simulations/service.py` | fingerprint built EXACTLY ONCE in `_load_frozen_input` from the verified profile row (after anchor scope checks, before any engine work); passed via `row_refs` into `run_simulation(profile=…)` |
| `services/api/app/simulations/tests/test_sim_eng_02_profile_hash.py` | NEW owner battery (13 tests) |

NOT changed: `profile_hash.py` (not needed — persisted hash trusted per contract §3),
`sensitivity.py` (outside write scope; contract §4.4 enumerates the change surface as
ENGINE_VERSION + hash payload/signature + service fingerprint pass-through only),
`repository.py`, `models.py`, `types.py`, `schemas.py`, `errors.py`, `migrations/**`,
`services/api/tests/**` (byte-identical to edaa842), `packages/contracts/**`, routes/mount
(none exist), `apps/web/**`, `scripts/**`.

## 2. Exact ENGINE_VERSION and before/after hash payload

- `ENGINE_VERSION = "sim-engine-1.1.0"` — single authoritative constant in engine.py; the
  persisted row, the wire self-check, and `SimulationRunView` all carry it via
  `result.engine_version` (no duplicated literals in product code).
- BEFORE (sim-engine-1.0.0): `{engineVersion, mode, epsilon, maxSteps, riskTolerance, graph,
  strategy{id,version,nodeOverrides}, scenario, scoreDefinition, nodeOverrides}`
- AFTER (sim-engine-1.1.0): identical + `"profile": {"id": <canonical lowercase UUID str>,
  "version": <int ≥ 1>, "contentHash": <"sha256:"+64 lowercase hex>}`
- Delta is exactly two things (engineVersion value; the profile block). `riskTolerance`
  retained as an unchanged top-level key. Canonical serialization unchanged
  (`sort_keys=True, separators=(",",":"), ensure_ascii=False`, UTF-8). No ORM repr / row PK /
  createdAt in the payload. `includeSensitivity` remains excluded.
- Owner test `test_hash_payload_independent_rederivation` re-derives the full payload
  independently and matches the engine output byte-for-byte.

## 3. Profile fingerprint representation + trust/format gate verdict

- Representation: `ProfileFingerprint` frozen+slots dataclass in domain.py; carries the
  STABLE `profile_id` (owner-tested `fingerprint.id != str(row.id)`), version, persisted
  content_hash. Engine rejects bare dicts (`SimulationInputError`), so no caller-constructed
  dict can impersonate a verified fingerprint.
- Trust verdict implemented: `PERSISTED_HASH_TRUSTED_VIA_APPEND_ONLY_WRITE_PATH` — no per-run
  rehash; mandatory format gate in `assemble_profile_fingerprint`: missing / non-str /
  non-lowercase / missing `sha256:` / wrong digest length / non-hex → `FrozenReferenceError`
  code `frozen_reference_incomplete`, engine NOT called (owner-tested with an
  engine-must-not-run monkeypatch), zero SimulationRun rows, no SQLAlchemy/ValueError leak.
- Anchor denials unchanged: ghost/foreign/wrong-case/wrong-version profile refs stay the
  uniform `CASE_NOT_FOUND` 404 before the gate (P1 behavior, QA-locked at edaa842).

## 4. Service/assembly data-flow + sensitivity verdicts

- Flow: verified WorkspaceContext → tenant/case-scoped repository lookup → verified immutable
  row → `assemble_profile_fingerprint` ONCE → `row_refs` → `run_simulation(profile=fp)` →
  optional sensitivity → single-transaction insert → frozen view. Service accepts no caller
  engineVersion / profileContentHash / riskTolerance (`SimulationRunRequest` unchanged from
  P1; QA test re-proves construction rejects `risk_tolerance`).
- Sensitivity verdict: base run receives the single service-computed fingerprint
  (owner-tested: `assemble_profile_fingerprint` called exactly once per
  `run_and_record(include_sensitivity=True)`; captured engine call got that same object);
  sensitivity sweeps re-run the UNCHANGED numeric algorithm with the same riskTolerance and
  trigger no additional profile lookup; their internal hashes are discarded, never persisted.
  Note: `sensitivity.py` is contractually outside the change surface (§4.4) and outside this
  lane's write scope — recorded as the interpretation applied.
- persisted row == view for profile id/version, riskTolerance, engineVersion, inputHash
  (owner-tested end-to-end, plus independent hash re-derivation through
  `_load_frozen_input` + direct `compute_input_hash`).

## 5. Historical immutability + Addendum A1 verdicts

- Historical 1.0.0: owner test seeds a legitimate `sim-engine-1.0.0` row with a frozen
  hash, executes a fresh 1.1.0 run, re-reads the legacy row → engine_version, input_hash,
  node_results, steps, risk_tolerance all byte-unchanged. No data migration, no UPDATE, no
  rehash, no upgrade path exists in the code.
- Addendum A1 non-regression: `strategy_edge_gating_unsupported` and
  `score_constraint_operator_unsupported` untouched (assembly fail-fast paths unmodified;
  full behavior tests still green in the suite); engine `Comparison` still has no `"="`;
  no equality scoring, no edge gating smuggled under the bump.

## 6. Verification (fresh PG16 `ludus-pg-eng02` @ localhost:55437, main venv, no installs)

| Gate | Result |
|---|---|
| alembic heads | exactly `b2c7e9d4a1f6` (single) |
| alembic upgrade head / current / check | clean; "No new upgrade operations detected"; **no new migration, b2c7e9d4a1f6 unmodified** |
| owner suite `app/simulations/tests` | **82 passed** (prior 69 + 13 new) |
| Task 12 engine tests | **28 passed** (baseline 28 — zero numeric drift) |
| persistence directed (`-k persistence`) | **16 passed** (baseline 16) |
| read-path + IO semantics | **16 passed** (baseline 16) |
| `pytest tests/lens_lanes -q` | **121 passed** (baseline 121) |
| **full, UNMODIFIED QA tests** `pytest tests app/simulations/tests -q -W error -rxX` | **458 passed / 1 failed / 0 xfailed / 0 xpassed** |
| filtered regression (deselect the exact stale node id only) | **458 passed / 0 failed** |
| official `generate_contracts.ps1 -Check` | **CONTRACT_DRIFT_OK** (read-only junction toolchain: local uv + preinstalled openapi-typescript 7.13.0, UV_NO_SYNC/UV_OFFLINE, zero installs/network); `packages/contracts/**` git ZERO diff |
| ruff / compileall / `git diff --check` / conflict markers / secret scan / scope audit | all clean; changed paths = exactly the 5 files in §1 |
| lifecycle | HEAD replaced per protocol; HISTORY append-only (this entry) |

## 7. QA-owned expected failures (exact)

Exactly ONE failure in the original full run, and it is the contract-named pinned-pending
assertion (CCR-ENG-02 §7.3 designed signal, NOT a regression):

| node id | reason (P2 pending → implemented) |
|---|---|
| `tests/test_sim_02a_profile_idempotency_qa.py::test_p2_engine_hash_gap_is_pinned_pending_dependency` | pins `ENGINE_VERSION == "sim-engine-1.0.0"`, "profile"/"content_hash" absent from the hash source, and same-rt/different-profile → same hash; all four pins flip by design under sim-engine-1.1.0 |

No other failures exist (`services/api/tests/**` byte-identical to edaa842; not modified,
not skipped, not xfailed). The independent P2 QA lane owns flipping this test to permanent
green from this product head.

## 8. P0/P1/P2 findings

- P0: 0. P1: 0. P2: 0.
- Interpretation notes (not findings): (a) engine `profile` parameter is keyword-only and
  optional at the pure-engine boundary so the QA acceptance suite (positional pure-engine
  calls, contractually not in the expected-red set) stays green; the SERVICE always supplies
  the fingerprint, so every persisted run carries the §2-shaped hash — enforced by owner
  tests. (b) sensitivity pass-through per contract §4.4 change-surface enumeration (§4 above).

## 9. Remote verification (live ls-remote after push)

- main = `387041d40442faf16557b266ef3f844b7af8fb69` (untouched)
- SIM-02A contract = `0289b2e36a7765891e4f1908231ac2384c541318`
- ENG-02 contract = `c8c9167b219fa8aa06bf9769776f49706f43b219`
- P1/P3 QA parent = `edaa8421c330de7cfe02a53c1e38574533e99c48`
- P2 product branch head = recorded in HEAD/worklog after push re-read

## 10. Environment / next steps

- Disposable container `ludus-pg-eng02` (postgres:16-alpine @55437) kept for independent QA;
  removable after acceptance. Junction toolchain artifacts are untracked and git-invisible.
- Next: independent P2 QA (flip the pinned test, full battery) from this head → then SIM-02A
  I1/I2/I3 wave → Mainline Lead integration. ready_for_public_route stays NO.
- No credentials recorded.
