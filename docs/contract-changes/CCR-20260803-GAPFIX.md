# CCR-20260803-GAPFIX — Gap-fix wave A: packet-evidence read-model projection

- Status: proposed (implementation on `codex/lens-behavior-closed-loop`)
- Date: 2026-08-03 (Asia/Shanghai)
- Owner: backend/runtime lane (E2E gap fix, wave A)
- Affected surface:
  - `GET /api/workspaces/{workspaceId}/analyses/{analysisRunId}/evidence` response
    gains `packetEvidence` (additive wire field, default `[]`)

## Problem

The E2E flash/pro verification (HEAD archive 2026-08-03) found that the E page
evidence list is ALWAYS empty: the analysis worker persists funnel-admitted
research packets (`research_packets`, carrying the minted `ev-retrieving-NNN
[Lx] source` ids) but never the Task 11 ingest chain
(RetrievalTask→RawArtifact→QualityAssessment→SourceRecord→EvidenceItem, all
NOT NULL upstream links). `evidence_items` holds 0 rows across the whole
database, so `list_run_evidence` returns `items: []` for every run and the
four per-item endpoints (quality/direction/provenance/same-source-group) have
nothing to serve. The whitepaper's evidence-traceability requirement
(证据门槛对称性 / quality-gate ⑲) is therefore invisible to the user even
though the run DID work with a real, graded evidence set.

## Change

Additive read-model projection — no DDL, no ingest-chain fabrication:

```
PacketEvidenceView {
  packetId: uuid,
  factor: str | null,
  direction: str | null,          -- supporting / opposing / neutral
  conclusion: str,
  claimSupportScore: float,
  evidenceIds: str[],             -- funnel-minted ids, tier annotation intact
  role: str                       -- research / critic / synthesis
}
RunEvidenceListView.packetEvidence: PacketEvidenceView[]  (default [])
```

`list_run_evidence` projects every persisted research packet of the run into
`packetEvidence`, ordered by creation. `items` (ingest chain) stays the
authoritative detailed surface when it exists; `packetEvidence` is the honest
"what the run actually reasoned from" list that is always available.

## Compatibility

- Purely additive: existing callers see one extra array field; fixtures and
  tests are unaffected (new field defaults to `[]`).
- No migration: `research_packets` already persists everything projected.
- The four per-item detail endpoints keep their evidence_items semantics;
  packet rows are list-only until the ingest chain lands (recorded in HEAD
  Remaining as the Task 11 follow-up).

## Contract regeneration

Run `scripts/generate_contracts.ps1` (generate then `-Check`); ops count only
grows; `-Check` must return CONTRACT_DRIFT_OK.
