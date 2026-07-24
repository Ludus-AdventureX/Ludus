"""Canonical wire-schema QA for CCR-20260724-SIM-01 (qa_release-owned).

Pure-Pydantic negative batteries for ScenarioVersion / CausalNode /
CausalEdge / GraphVersion: extra=forbid, camelCase wire, bounds, uniqueness
and reference resolution. Known evidence-discipline gaps are xfail probes
carrying QA finding ids.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

pytest.importorskip("app.simulations.schemas", reason="SIM-01 not delivered yet")

from pydantic import ValidationError

from app.simulations import schemas as wire

NOW = "2026-07-24T10:00:00Z"


def _scenario(**overrides: Any) -> dict:
    payload = {
        "id": str(uuid4()),
        "workspaceId": str(uuid4()),
        "graphId": str(uuid4()),
        "decisionCaseId": str(uuid4()),
        "sourceLensArtifactId": str(uuid4()),
        "sourceStrategicScenarioId": "scenario-frame-1",
        "scenarioId": str(uuid4()),
        "version": 1,
        "name": "QA scenario",
        "description": "Wire battery scenario",
        "defaultEdgeMultiplier": 1.0,
        "edgeMultipliers": {"edge-1": 1.2},
        "nodeShifts": {"node-1": 0.2},
        "strategySurvives": True,
        "earlyWarningSignals": [],
        "damping": 0.8,
        "createdAt": NOW,
    }
    payload.update(overrides)
    return payload


def _node(**overrides: Any) -> dict:
    payload = {
        "id": "node-1",
        "label": "Outcome",
        "type": "outcome",
        "baseline": 0.5,
        "current": 0.5,
        "min": 0.0,
        "max": 1.0,
        "normalization": "linear",
        "controllability": "controllable",
        "authorship": "generated",
        "evidenceStatus": "assumed",
        "evidenceQualityScore": 0.5,
        "evidenceIds": [],
        "assumptionIds": ["assumption-1"],
        "rationale": "QA node",
        "status": "draft",
        "editable": True,
    }
    payload.update(overrides)
    return payload


def _edge(**overrides: Any) -> dict:
    payload = {
        "id": "edge-1",
        "sourceNodeId": "node-1",
        "targetNodeId": "node-2",
        "polarity": "positive",
        "strength": 0.5,
        "delaySteps": 0,
        "authorship": "generated",
        "evidenceStatus": "assumed",
        "relationshipQualityScore": 0.5,
        "rationale": "QA edge",
        "claimIds": ["claim-1"],
        "evidenceIds": [],
        "assumptionIds": [],
        "status": "draft",
    }
    payload.update(overrides)
    return payload


def _graph_version(**overrides: Any) -> dict:
    payload = {
        "id": str(uuid4()),
        "workspaceId": str(uuid4()),
        "graphId": str(uuid4()),
        "decisionCaseId": str(uuid4()),
        "caseVersion": 1,
        "sourceReportArtifactId": str(uuid4()),
        "version": 1,
        "status": "draft",
        "provenance": [],
        "originModes": ["fixture"],
        "title": "QA graph version",
        "contentHash": "sha256:qa-graph",
        "nodes": [_node(), _node(id="node-2", label="Driver", type="lever")],
        "edges": [_edge()],
        "createdBy": str(uuid4()),
        "createdAt": NOW,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# ScenarioVersion
# ---------------------------------------------------------------------------


def test_scenario_accepts_legal_payload_and_boundaries() -> None:
    assert wire.ScenarioVersion.model_validate(_scenario()).damping == 0.8
    # damping boundary 1 accepted; node shift boundaries -1 / 1 accepted
    accepted = wire.ScenarioVersion.model_validate(
        _scenario(damping=1.0, nodeShifts={"a": -1.0, "b": 1.0})
    )
    assert accepted.damping == 1.0


def test_scenario_rejects_risk_tolerance_on_the_wire() -> None:
    with pytest.raises(ValidationError) as excinfo:
        wire.ScenarioVersion.model_validate(_scenario(riskTolerance=0.5))
    assert "riskTolerance" in str(excinfo.value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"damping": 0},
        {"damping": 1.01},
        {"damping": -0.5},
        {"defaultEdgeMultiplier": -0.01},
        {"edgeMultipliers": {"edge-1": -0.5}},
        {"edgeMultipliers": {"edge-1": float("inf")}},
        {"nodeShifts": {"node-1": -1.01}},
        {"nodeShifts": {"node-1": 1.01}},
        {"nodeShifts": {"node-1": float("nan")}},
    ],
)
def test_scenario_rejects_out_of_range_dynamics(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        wire.ScenarioVersion.model_validate(_scenario(**overrides))


# ---------------------------------------------------------------------------
# CausalNode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"min": 1.0, "max": 1.0},  # min >= max
        {"min": 2.0, "max": 1.0},
        {"baseline": 1.5},  # outside [min, max]
        {"current": -0.5},
        {"baseline": float("nan")},
        {"max": float("inf")},
        {"evidenceQualityScore": 1.01},
        {"evidenceQualityScore": -0.01},
    ],
)
def test_causal_node_rejects_invalid_business_values(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        wire.CausalNode.model_validate(_node(**overrides))


def test_causal_node_accepts_boundaries() -> None:
    node = wire.CausalNode.model_validate(
        _node(baseline=0.0, current=1.0, evidenceQualityScore=1.0)
    )
    assert node.current == 1.0


@pytest.mark.xfail(
    reason=(
        "QA-SIM01-001: wire schema does not yet reject evidenceStatus=supported "
        "with empty evidenceIds (AGENTS section 10 evidence discipline)"
    ),
    strict=False,
)
def test_causal_node_supported_requires_evidence_ids() -> None:
    with pytest.raises(ValidationError):
        wire.CausalNode.model_validate(
            _node(evidenceStatus="supported", evidenceIds=[])
        )


# ---------------------------------------------------------------------------
# CausalEdge
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"strength": 1.01},
        {"strength": -0.01},
        {"relationshipQualityScore": 1.01},
        {"relationshipQualityScore": -0.01},
        {"delaySteps": -1},
        {"polarity": "sideways"},
        {"status": "not-a-status"},
    ],
)
def test_causal_edge_rejects_invalid_values(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        wire.CausalEdge.model_validate(_edge(**overrides))


@pytest.mark.xfail(
    reason=(
        "QA-SIM01-002: wire schema does not yet reject confirmed edges without "
        "claimIds nor edges with claim/evidence/assumption all empty"
    ),
    strict=False,
)
def test_causal_edge_confirmation_requires_traceable_sources() -> None:
    with pytest.raises(ValidationError):
        wire.CausalEdge.model_validate(_edge(status="confirmed", claimIds=[]))
    with pytest.raises(ValidationError):
        wire.CausalEdge.model_validate(
            _edge(claimIds=[], evidenceIds=[], assumptionIds=[])
        )


@pytest.mark.xfail(
    reason="QA-SIM01-003: self-loop edges are not rejected on the wire either",
    strict=False,
)
def test_causal_edge_self_loop_rejected_on_wire() -> None:
    with pytest.raises(ValidationError):
        wire.GraphVersion.model_validate(
            _graph_version(
                edges=[_edge(sourceNodeId="node-1", targetNodeId="node-1")]
            )
        )


# ---------------------------------------------------------------------------
# GraphVersion
# ---------------------------------------------------------------------------


def test_graph_version_uniqueness_and_reference_resolution() -> None:
    with pytest.raises(ValidationError):
        wire.GraphVersion.model_validate(
            _graph_version(nodes=[_node(), _node()])  # duplicate node ids
        )
    with pytest.raises(ValidationError):
        wire.GraphVersion.model_validate(
            _graph_version(edges=[_edge(), _edge()])  # duplicate edge ids
        )
    with pytest.raises(ValidationError):
        wire.GraphVersion.model_validate(
            _graph_version(edges=[_edge(targetNodeId="ghost-node")])
        )


def test_graph_version_confirmed_requires_timestamp_and_identity_shape() -> None:
    with pytest.raises(ValidationError):
        wire.GraphVersion.model_validate(_graph_version(status="confirmed"))
    confirmed = wire.GraphVersion.model_validate(
        _graph_version(status="confirmed", confirmedAt=NOW)
    )
    assert confirmed.confirmed_at is not None
    # server-owned / immutable identity fields are required on the wire shape
    for field in ("id", "workspaceId", "graphId", "decisionCaseId", "createdBy"):
        payload = _graph_version()
        payload.pop(field)
        with pytest.raises(ValidationError):
            wire.GraphVersion.model_validate(payload)
    # unknown extra fields are rejected everywhere (extra=forbid)
    with pytest.raises(ValidationError):
        wire.GraphVersion.model_validate(_graph_version(serverSecret="x"))
