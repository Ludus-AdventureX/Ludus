# CCR-20260724-SIM-02A — ADDENDUM A1 (Contract Erratum: internal caller impact)

- Status: ADJUDICATED — ADDITIVE ERRATUM, ORIGINAL CCR TEXT NOT REWRITTEN
- Date: 2026-07-25 (Asia/Shanghai)
- Owner: Contract/Mainline Lead — Simulation Engine Profile-Aware Hash Contract Owner
- Applies to: `docs/product-plan/docs/contract-changes/CCR-20260724-SIM-02A.md`
  (frozen at `codex/ccr-sim-02a-run-api-contract` @ `0289b2e36a7765891e4f1908231ac2384c541318`)
- Trigger: P1/P3 independent QA formally recorded **CONTRACT_ERRATUM_CONFIRMED**
  at `codex/qa-sim-02a-profile-idempotency-r1` @
  `edaa8421c330de7cfe02a53c1e38574533e99c48`.

## Erratum

Original CCR-SIM-02A §2 (Consequences) states:

> "Internal service-level callers (tests) are unaffected until the route lands."

This sentence is FACTUALLY INCORRECT and is hereby formally SUPERSEDED. It is
not rewritten in place — the frozen file stays byte-identical; this addendum is
the sole normative correction.

## Corrected statement (normative)

1. No public HTTP API for simulation runs existed before or during the P1/P3
   slice, so **no public API compatibility promise was ever at stake**. The
   erratum concerns internal accuracy only.
2. Internal service/test callers WERE affected by the P1/P3 prerequisites, as
   shipped at `fb75b8f5dc282b9df3cf8172e3ed114fe23ae29a`:
   - `SimulationRun` gained a frozen, tenant-scoped Profile reference
     (composite FK to `decision_maker_profiles` via migration `b2c7e9d4a1f6`);
   - `SimulationRunRequest` REMOVED the caller-supplied `risk_tolerance` field;
     riskTolerance is resolved server-side from the verified frozen Profile row;
   - every service caller and test fixture must now seed or reference a real
     frozen `decision_maker_profiles` row (workspace/version/case-scope valid)
     before invoking the run service.
3. The required adaptation of internal callers and fixtures has ALREADY been
   completed and independently locked by QA at
   `edaa8421c330de7cfe02a53c1e38574533e99c48` (RELEASE_CONTENT_VERDICT: PASS;
   test_ownership_verdict: ADOPT). No further caller migration debt exists for
   the P1/P3 surface.
4. It is forbidden to cite the superseded sentence — in any future handoff,
   CCR, or integration audit — as evidence that internal callers were or are
   unaffected. The authoritative description is this addendum.

## Scope guard

- This addendum changes NO other ruling of CCR-SIM-02A. Route scope, profile
  authority (public_post_run_blocked_by_profile = true), inputHash verdict,
  idempotency verdict, request/response schemas, error mapping, capability
  matrix, mounting plan, and slice ownership all remain exactly as frozen.
- ready_for_public_route remains **NO** until CCR-ENG-02 P2 + independent P2 QA
  + SIM-02A I1/I2/I3 land through the standard integration chain.
- No credentials or secret values are recorded here.
