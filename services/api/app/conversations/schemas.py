"""Wire schemas for the conversation surface (Task 5).

Frozen shapes: docs/product-plan/10-api-and-events.md "讨论消息" and the
QuickAnalysisResult projection from 06-data-model.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class CaseMessageRequest(ApiModel):
    message: str = Field(min_length=1)
    propose_structured_updates: bool = Field(alias="proposeStructuredUpdates", default=True)


class ProposedPatchData(ApiModel):
    goals_added: int = Field(alias="goalsAdded", default=0)
    constraints_added: int = Field(alias="constraintsAdded", default=0)
    facts_added: int = Field(alias="factsAdded", default=0)
    assumptions_added: int = Field(alias="assumptionsAdded", default=0)
    unknowns_added: int = Field(alias="unknownsAdded", default=0)


class CaseMessageData(ApiModel):
    candidate_revision_id: UUID | None = Field(alias="candidateRevisionId", default=None)
    base_dossier_version: int = Field(alias="baseDossierVersion")
    base_case_version: int | None = Field(alias="baseCaseVersion", default=None)
    assistant_message: str = Field(alias="assistantMessage")
    proposed_patch: ProposedPatchData = Field(alias="proposedPatch")


class QuickAnalysisRequest(ApiModel):
    question: str | None = None
