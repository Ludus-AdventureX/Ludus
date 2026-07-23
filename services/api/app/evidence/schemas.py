from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, RootModel, model_validator

from app.contracts.schemas import CanonicalModel, ContentHash, Identifier, NonEmptyText
from app.types import OriginMode, SourceKind


class SourceRecordBase(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    decision_case_id: Identifier
    kind: SourceKind
    canonical_uri: NonEmptyText
    title: NonEmptyText
    content_hash: ContentHash
    source_version: NonEmptyText
    origin_mode: OriginMode
    raw_artifact_id: Identifier | None = None
    created_at: datetime


class PreRunSourceRecord(SourceRecordBase):
    source_scope: Literal["pre_run"]


class RunFrozenSourceRecord(SourceRecordBase):
    source_scope: Literal["run_frozen"]
    analysis_run_id: Identifier
    frozen_from_source_record_id: Identifier
    frozen_at: datetime

    @model_validator(mode="after")
    def freeze_timestamp_is_valid(self) -> RunFrozenSourceRecord:
        if self.frozen_at < self.created_at:
            raise ValueError("frozenAt cannot precede createdAt")
        if self.frozen_from_source_record_id == self.id:
            raise ValueError("a frozen source record cannot freeze itself")
        return self


SourceRecordValue = Annotated[
    PreRunSourceRecord | RunFrozenSourceRecord,
    Field(discriminator="source_scope"),
]


class SourceRecord(RootModel[SourceRecordValue]):
    """Named discriminated union for pre-run and run-frozen sources."""


class SourceSpanLocator(CanonicalModel):
    page_number: int | None = Field(default=None, ge=1)
    paragraph_index: int | None = Field(default=None, ge=0)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    sheet_name: NonEmptyText | None = None
    row_start: int | None = Field(default=None, ge=1)
    row_end: int | None = Field(default=None, ge=1)
    column_start: int | None = Field(default=None, ge=1)
    column_end: int | None = Field(default=None, ge=1)
    case_field_path: NonEmptyText | None = None
    message_id: Identifier | None = None

    @model_validator(mode="after")
    def locator_is_deterministic(self) -> SourceSpanLocator:
        values = self.model_dump(exclude_none=True)
        if not values:
            raise ValueError("a source span locator must identify at least one stable location")
        for start_name, end_name in (
            ("char_start", "char_end"),
            ("row_start", "row_end"),
            ("column_start", "column_end"),
        ):
            start = getattr(self, start_name)
            end = getattr(self, end_name)
            if (start is None) != (end is None):
                raise ValueError(f"{start_name} and {end_name} must be supplied together")
            if start is not None and end is not None and end < start:
                raise ValueError(f"{end_name} cannot be smaller than {start_name}")
        return self


class SourceSpanBase(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    decision_case_id: Identifier
    source_record_id: Identifier
    locator: SourceSpanLocator
    quote: NonEmptyText
    quote_hash: ContentHash
    context_before: str | None = None
    context_after: str | None = None
    created_at: datetime


class PreRunSourceSpan(SourceSpanBase):
    source_scope: Literal["pre_run"]


class RunFrozenSourceSpan(SourceSpanBase):
    source_scope: Literal["run_frozen"]
    analysis_run_id: Identifier
    frozen_from_source_span_id: Identifier

    @model_validator(mode="after")
    def frozen_span_does_not_reference_itself(self) -> RunFrozenSourceSpan:
        if self.frozen_from_source_span_id == self.id:
            raise ValueError("a frozen source span cannot freeze itself")
        return self


SourceSpanValue = Annotated[
    PreRunSourceSpan | RunFrozenSourceSpan,
    Field(discriminator="source_scope"),
]


class SourceSpan(RootModel[SourceSpanValue]):
    """Named discriminated union for pre-run and run-frozen source spans."""
