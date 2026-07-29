"""Auth endpoints from the canonical API contract (docs/product-plan/10).

| GET  /api/auth/csrf     | issue/refresh readable CSRF token + cookie |
| POST /api/auth/register | register and create the first revocable UserSession |
| POST /api/auth/login    | login and create a revocable UserSession |
| POST /api/auth/logout   | revoke the current UserSession, then clear cookies |
| GET  /api/auth/session  | current user, session state, membership summary |

Routers are mounted into ``app.main`` by the Contract Lead together with
``app.security.envelope.register_error_handlers`` (see the accompanying
CONTRACT_CHANGE_REQUEST); this module must not import ``app.main``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import SecretStr, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.config import get_auth_settings
from app.auth.deps import AuthenticatedPrincipal, require_authenticated_principal
from app.auth.passwords import DUMMY_PASSWORD_HASH, hash_password, verify_password
from app.auth.sessions import create_user_session, revoke_user_session, utc_now
from app.auth.signup_invites import signup_code_accepted
from app.auth.tokens import TokenDecodeError, decode_session_token, encode_session_token
from app.contracts.schemas import CanonicalModel, NonEmptyText
from app.db import get_session
from app.models import User, UserSession, Workspace, WorkspaceInvite, WorkspaceMembership
from app.security.csrf import issue_csrf_token, require_csrf
from app.security.envelope import ApiFailure
from app.security.rate_limits import LoginRateLimiter
from app.tenancy.invites import token_hash_of as invite_token_hash
from app.tenancy.context import project_capabilities
from app.types import (
    UserStatus,
    WorkspaceCapability,
    WorkspaceMembershipStatus,
    WorkspaceRole,
    WorkspaceStatus,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_DEFAULT_WORKSPACE_NAME = "Personal Workspace"

EmailField = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]
PasswordField = Annotated[str, StringConstraints(min_length=8, max_length=200)]


class RegisterRequest(CanonicalModel):
    email: EmailField
    password: PasswordField
    # Wire name inviteCode. Required in practice (registration is invite-gated),
    # but typed optional so a missing code is answered by the uniform gate
    # failure below rather than by a schema error that would confirm the field
    # matters.
    invite_code: Annotated[SecretStr, StringConstraints(max_length=200)] | None = None
    workspace_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None


class LoginRequest(CanonicalModel):
    email: EmailField
    password: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class CsrfTokenData(CanonicalModel):
    csrf_token: NonEmptyText


class CsrfEnvelope(CanonicalModel):
    ok: Literal[True] = True
    data: CsrfTokenData


class UserSummary(CanonicalModel):
    id: str
    email: str
    status: UserStatus
    created_at: datetime


class SessionSummary(CanonicalModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime


class MembershipSummary(CanonicalModel):
    workspace_id: str
    workspace_name: str
    role: WorkspaceRole
    capabilities: list[WorkspaceCapability]
    status: WorkspaceMembershipStatus


class AuthSessionData(CanonicalModel):
    user: UserSummary
    session: SessionSummary
    memberships: list[MembershipSummary]


class AuthSessionEnvelope(CanonicalModel):
    ok: Literal[True] = True
    data: AuthSessionData


class LogoutData(CanonicalModel):
    logged_out: Literal[True] = True


class LogoutEnvelope(CanonicalModel):
    ok: Literal[True] = True
    data: LogoutData


def _registration_rejected() -> ApiFailure:
    # One generic message for duplicates and race losers alike, so the
    # endpoint cannot be used to enumerate registered emails.
    return ApiFailure(
        "VALIDATION_FAILED",
        "Registration could not be completed with the provided details.",
        http_status=422,
    )


def _signup_unavailable() -> ApiFailure:
    # One response for "no code", "wrong code" and "registration is closed on
    # this deployment". Distinguishing them would tell a prober whether codes
    # exist at all and whether the one they hold is close to a real one; the
    # legitimately invited person already has a working code.
    return ApiFailure(
        "SIGNUP_INVITE_REQUIRED",
        "Registration requires a valid invite code.",
        http_status=403,
    )


def _invalid_credentials() -> ApiFailure:
    return ApiFailure(
        "AUTH_INVALID_CREDENTIALS",
        "Email or password is incorrect.",
        http_status=401,
    )


def _set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    settings = get_auth_settings()
    max_age = max(int((expires_at - utc_now()).total_seconds()), 0)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_auth_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


async def _membership_summaries(db: AsyncSession, user_id) -> list[MembershipSummary]:
    rows = (
        await db.execute(
            select(WorkspaceMembership, Workspace)
            .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
            .where(
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.status == WorkspaceMembershipStatus.ACTIVE,
                Workspace.status == WorkspaceStatus.ACTIVE,
            )
            .order_by(Workspace.created_at)
        )
    ).all()
    return [
        MembershipSummary(
            workspace_id=str(workspace.id),
            workspace_name=workspace.name,
            role=membership.role,
            capabilities=sorted(
                project_capabilities(membership.role, membership.capabilities),
                key=lambda capability: capability.value,
            ),
            status=membership.status,
        )
        for membership, workspace in rows
    ]


async def _session_envelope(
    db: AsyncSession, user: User, session: UserSession
) -> AuthSessionEnvelope:
    return AuthSessionEnvelope(
        data=AuthSessionData(
            user=UserSummary(
                id=str(user.id),
                email=user.email,
                status=user.status,
                created_at=user.created_at,
            ),
            session=SessionSummary(
                id=str(session.id),
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
                expires_at=session.expires_at,
            ),
            memberships=await _membership_summaries(db, user.id),
        )
    )


@router.get("/csrf", response_model=CsrfEnvelope)
async def get_csrf_token(response: Response) -> CsrfEnvelope:
    token = issue_csrf_token(response)
    return CsrfEnvelope(data=CsrfTokenData(csrf_token=token))


@router.post(
    "/register",
    response_model=AuthSessionEnvelope,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> AuthSessionEnvelope:
    # Invite gate + metering BEFORE any account work. Registration allocates a
    # workspace, and a workspace carries its own analysis-run budget, so an
    # unmetered open sign-up is the cheapest way to burn the product's money.
    client_ip = request.client.host if request.client else "unknown"
    limiter = LoginRateLimiter()
    await limiter.check_login_attempt(
        db, client_ip=client_ip, email=f"register:{body.email}"
    )

    code = body.invite_code.get_secret_value() if body.invite_code else None
    if not signup_code_accepted(code):
        raise _signup_unavailable()

    existing = await db.scalar(select(User.id).where(User.email == body.email))
    if existing is not None:
        raise _registration_rejected()

    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise _registration_rejected() from None

    workspace = Workspace(
        name=body.workspace_name or _DEFAULT_WORKSPACE_NAME,
        created_by_user_id=user.id,
    )
    db.add(workspace)
    await db.flush()
    db.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=WorkspaceRole.OWNER,
            # Stored grants stay empty for owners: the full capability set is
            # projected from the role on every read (docs/product-plan/26 §8).
            capabilities=[],
        )
    )
    session = await create_user_session(db, user.id)
    token = encode_session_token(
        user_id=user.id,
        session_id=session.id,
        issued_at=utc_now(),
        expires_at=session.expires_at,
    )
    envelope = await _session_envelope(db, user, session)
    await db.commit()
    _set_session_cookie(response, token, session.expires_at)
    return envelope


@router.post(
    "/login",
    response_model=AuthSessionEnvelope,
    dependencies=[Depends(require_csrf)],
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> AuthSessionEnvelope:
    # P2-001 mandatory gate: meter the attempt (IP + normalized account) in
    # Postgres before any credential work; storage failure fails closed.
    client_ip = request.client.host if request.client else "unknown"
    limiter = LoginRateLimiter()
    await limiter.check_login_attempt(db, client_ip=client_ip, email=body.email)

    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None:
        # Equalize timing with a real Argon2 verification, then fail uniformly.
        verify_password(DUMMY_PASSWORD_HASH, body.password)
        raise _invalid_credentials()
    if not verify_password(user.password_hash, body.password):
        raise _invalid_credentials()
    if user.status != UserStatus.ACTIVE:
        raise _invalid_credentials()

    session = await create_user_session(db, user.id)
    token = encode_session_token(
        user_id=user.id,
        session_id=session.id,
        issued_at=utc_now(),
        expires_at=session.expires_at,
    )
    envelope = await _session_envelope(db, user, session)
    # Successful authentication releases the account dimension only; the IP
    # dimension keeps counting so address-level abuse cannot launder budget.
    await limiter.reset_account(db, body.email)
    await db.commit()
    _set_session_cookie(response, token, session.expires_at)
    return envelope


@router.post(
    "/logout",
    response_model=LogoutEnvelope,
    dependencies=[Depends(require_csrf)],
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> LogoutEnvelope:
    # Revocation happens before the cookie is cleared (plan 18 Task 3 Step 4).
    # An absent or undecodable token still clears the cookie and succeeds, so
    # logout stays idempotent and leaks no session state.
    settings = get_auth_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        try:
            claims = decode_session_token(token, settings)
        except TokenDecodeError:
            claims = None
        if claims is not None:
            await revoke_user_session(db, claims.session_id)
            await db.commit()
    _clear_session_cookie(response)
    return LogoutEnvelope(data=LogoutData())


@router.get("/session", response_model=AuthSessionEnvelope)
async def read_session(
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
    db: AsyncSession = Depends(get_session),
) -> AuthSessionEnvelope:
    return await _session_envelope(db, principal.user, principal.session)

# --- invite redemption (multi-guest collaboration lane) -----------------------

class InviteRedeemRequest(CanonicalModel):
    token: SecretStr


def _invite_not_found() -> ApiFailure:
    # Anti-enumeration: unknown/expired/revoked/exhausted tokens are
    # indistinguishable - one code, one message, one status (case-surface
    # discipline). Never log the submitted token.
    return ApiFailure(
        "INVITE_NOT_FOUND",
        "The invite is invalid or no longer available.",
        http_status=404,
    )


@router.post("/invites/redeem", dependencies=[Depends(require_csrf)])
async def redeem_invite(
    body: InviteRedeemRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Redeem an invite token into an ACTIVE MEMBER membership.

    Fail-closed metering (login limiter, IP-scoped) runs before any lookup;
    the invite row is locked FOR UPDATE so concurrent redemptions count
    used_count atomically; re-redemption by an existing member is idempotent
    and consumes no use.
    """

    client_ip = request.client.host if request.client else "unknown"
    limiter = LoginRateLimiter()
    await limiter.check_login_attempt(
        db, client_ip=client_ip, email=f"invite-redeem:{client_ip}"
    )

    token = body.token.get_secret_value().strip()
    if not token or len(token) > 128:
        raise _invite_not_found()

    now = utc_now()
    invite = await db.scalar(
        select(WorkspaceInvite)
        .where(WorkspaceInvite.token_hash == invite_token_hash(token))
        .with_for_update()
    )
    if (
        invite is None
        or invite.revoked_at is not None
        or invite.expires_at <= now
        or invite.used_count >= invite.max_uses
    ):
        raise _invite_not_found()

    workspace = await db.scalar(
        select(Workspace).where(
            Workspace.id == invite.workspace_id,
            Workspace.status == WorkspaceStatus.ACTIVE,
        )
    )
    if workspace is None:
        raise _invite_not_found()

    existing = await db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == invite.workspace_id,
            WorkspaceMembership.user_id == principal.user.id,
        )
    )
    if existing is not None:
        if existing.status != WorkspaceMembershipStatus.ACTIVE:
            # A suspended/revoked member cannot re-enter through an invite.
            raise _invite_not_found()
        await db.commit()  # release the row lock; nothing consumed
        return {
            "ok": True,
            "data": {
                "workspaceId": str(invite.workspace_id),
                "membership": "existing",
                "capabilities": [c.value for c in existing.capabilities],
            },
        }

    membership = WorkspaceMembership(
        workspace_id=invite.workspace_id,
        user_id=principal.user.id,
        role=WorkspaceRole.MEMBER,
        capabilities=list(invite.granted_capabilities),
    )
    db.add(membership)
    invite.used_count += 1
    await db.commit()
    return {
        "ok": True,
        "data": {
            "workspaceId": str(invite.workspace_id),
            "membership": "created",
            "capabilities": [c.value for c in invite.granted_capabilities],
        },
    }

