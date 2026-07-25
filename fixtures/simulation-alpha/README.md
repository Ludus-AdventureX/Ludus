# simulation-alpha fixture

Deterministic seed input for the SIM alpha prototype (`SIM_ALPHA_SEED_SMOKE_FAST`).
It is consumed only by `scripts/seed_simulation_alpha.py` and
`scripts/smoke_simulation_alpha.py`; it never impersonates live data
(`originModes = ["fixture"]` on every seeded row).

Layout:

- `seed/simulation_alpha.json` — the frozen business payload: demo identity,
  workspace/case anchors, one confirmed causal graph (4 nodes / 4 edges),
  one strategy version, one scenario version, one score definition, and one
  decision-maker profile. All row UUIDs are derived deterministically
  (uuid5) from the `key` fields in this file, so repeated seeding is
  idempotent by construction.

Security: this fixture carries **no credentials**. The demo password is
supplied exclusively through the `SIMULATION_ALPHA_DEMO_PASSWORD` environment
variable at seed/smoke time (see `docs/runbooks/SIMULATION_ALPHA.md`).
