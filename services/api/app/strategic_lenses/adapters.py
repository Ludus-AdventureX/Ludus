"""Thin LensImplementation adapters for the self-contained lens lanes.

Pre-Mortem and Meadows shipped as framework-free behavior modules (no seam
import). These adapters wrap them into the shared ``app.agents.lenses``
protocol without changing any lane behavior: prompt assembly is deterministic
and behavior verdicts map one-to-one onto the lanes' stable finding codes.
Reference resolution against the frozen Run stays with the harness.
"""

from __future__ import annotations

import json
from typing import Any

from app.agents.lenses import (
    LensBehaviorReport,
    LensPromptInputs,
    LensRequest,
    StrategicLensStageOutput,
    lens_content_example,
    lens_output_contract,
    load_lens_content_schema,
)
from app.types import StrategicLensType

from .lenses.meadows_leverage_points import (
    MeadowsLensValidationError,
    check_meadows_behavior,
    validate_meadows_stage_output,
)
from .lenses.pre_mortem import validate_pre_mortem_output


def _stage_output_payload(output: StrategicLensStageOutput) -> dict[str, Any]:
    """Project the seam dataclass back onto the wire payload the lanes validate."""

    return {
        "lensType": output.lens_type.value,
        "sourceSkillVersion": output.source_skill_version,
        "phase": output.phase,
        "references": {key: list(value) for key, value in output.references.items()},
        "researchRequests": [dict(item) for item in output.research_requests],
        "content": dict(output.content),
    }


def _deterministic_user_prompt(request: LensRequest) -> str:
    """Stable, sorted serialization of the frozen request references."""

    body = {
        "workspaceId": request.workspace_id,
        "analysisRunId": request.analysis_run_id,
        "optionIds": sorted(request.option_ids),
        "researchPacketRefs": sorted(request.research_packet_refs),
        "evidenceRefs": sorted(request.evidence_refs),
        "claimRefs": sorted(request.claim_refs),
        "assumptionRefs": sorted(request.assumption_refs),
        "challengeRefs": sorted(request.challenge_refs),
        "upstreamLenses": sorted(
            lens.value for lens in request.upstream_lens_outputs
        ),
    }
    return json.dumps(body, ensure_ascii=False, sort_keys=True)


class PreMortemLensAdapter:
    """Seam adapter over the Pre-Mortem behavior gate (Critic-owned, L2)."""

    lens_type = StrategicLensType.PRE_MORTEM
    _phase = "adversarial_stress"
    _content_def = "preMortemContent"

    def build_prompt_inputs(self, request: LensRequest) -> LensPromptInputs:
        return LensPromptInputs(
            system=request.prompt_text,
            user=_deterministic_user_prompt(request)
            + "\n\n"
            + lens_output_contract(
                lens_type=self.lens_type.value,
                phase=self._phase,
                source_skill_version="1.0.0",
                content_def=self._content_def,
                content_schema=load_lens_content_schema(self._content_def),
                content_example=lens_content_example(self._content_def),
            ),
            schema_content_def=self._content_def,
        )

    def validate_behavior(self, output: StrategicLensStageOutput) -> LensBehaviorReport:
        result = validate_pre_mortem_output(_stage_output_payload(output))
        blockers = result.blockers
        return LensBehaviorReport(
            lens_type=self.lens_type,
            ok=result.passed,
            reason_codes=tuple(finding.code for finding in blockers),
            findings=tuple(
                f"{finding.code} @ {finding.path}: {finding.message}"
                for finding in result.findings
            ),
        )


class MeadowsLensAdapter:
    """Seam adapter over the Meadows leverage-points gate (Synthesis-owned, L5)."""

    lens_type = StrategicLensType.MEADOWS_LEVERAGE_POINTS
    _phase = "strategic_synthesis"
    _content_def = "meadowsContent"

    def build_prompt_inputs(self, request: LensRequest) -> LensPromptInputs:
        return LensPromptInputs(
            system=request.prompt_text,
            user=_deterministic_user_prompt(request)
            + "\n\n"
            + lens_output_contract(
                lens_type=self.lens_type.value,
                phase=self._phase,
                source_skill_version="1.0.0",
                content_def=self._content_def,
                content_schema=load_lens_content_schema(self._content_def),
                content_example=lens_content_example(self._content_def),
            ),
            schema_content_def=self._content_def,
        )

    def validate_behavior(self, output: StrategicLensStageOutput) -> LensBehaviorReport:
        payload = _stage_output_payload(output)
        try:
            stage_output = validate_meadows_stage_output(payload)
        except MeadowsLensValidationError as exc:
            violations = getattr(exc, "violations", ())
            reason_codes = tuple(v.code for v in violations) or ("meadows_schema_invalid",)
            findings = tuple(f"{v.code}: {v.message}" for v in violations) or (str(exc),)
            return LensBehaviorReport(
                lens_type=self.lens_type,
                ok=False,
                reason_codes=reason_codes,
                findings=findings,
            )
        violations = check_meadows_behavior(stage_output)
        return LensBehaviorReport(
            lens_type=self.lens_type,
            ok=not violations,
            reason_codes=tuple(v.code for v in violations),
            findings=tuple(f"{v.code}: {v.message}" for v in violations),
        )
