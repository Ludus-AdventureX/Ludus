from __future__ import annotations

from datetime import datetime

from pydantic import Field, SecretStr, field_validator, model_validator

from app.contracts.schemas import CanonicalModel, Identifier
from app.types import (
    UserStatus,
    WorkspaceCapability,
    WorkspaceMembershipStatus,
    WorkspaceRole,
)


class User(CanonicalModel):
    id: Identifier
    email: str = Field(min_length=3, max_length=320)
    password_hash: SecretStr = Field(exclude=True, repr=False, json_schema_extra={"writeOnly": True})
    status: UserStatus
    created_at: datetime
    updated_at: datetime


class WorkspaceMembership(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    user_id: Identifier
    role: WorkspaceRole
    capabilities: list[WorkspaceCapability]
    status: WorkspaceMembershipStatus
    created_at: datetime
    updated_at: datetime

    @field_validator("capabilities")
    @classmethod
    def capabilities_are_unique(
        cls, capabilities: list[WorkspaceCapability]
    ) -> list[WorkspaceCapability]:
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("workspace capabilities must not contain duplicates")
        return capabilities


class UserSession(CanonicalModel):
    id: Identifier
    user_id: Identifier
    token_version: int = Field(gt=0)
    expires_at: datetime
    revoked_at: datetime | None = None
    last_seen_at: datetime
    created_at: datetime

    @model_validator(mode="after")
    def timestamps_are_ordered(self) -> UserSession:
        if self.expires_at <= self.created_at:
            raise ValueError("session expiry must be later than creation")
        if self.last_seen_at < self.created_at:
            raise ValueError("lastSeenAt cannot precede createdAt")
        if self.revoked_at is not None and self.revoked_at < self.created_at:
            raise ValueError("revokedAt cannot precede createdAt")
        return self
