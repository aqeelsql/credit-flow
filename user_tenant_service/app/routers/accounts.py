import logging
from typing import Any

from fastapi import APIRouter, Depends, Response, status

from app.config import Settings
from app.database import Database
from app.dependencies import (
    current_principal,
    database_dep,
    event_bus_dep,
    require_account_manager_membership,
    require_internal,
    settings_dep,
)
from app.errors import AccountError
from app.events import EventBus
from app.models import AccountType
from app.repository import AccountRepository
from app.schemas import (
    AcceptInviteRequest,
    AdminAccountListResponse,
    AccountResponse,
    AccountSummaryResponse,
    CreateAccountRequest,
    InternalCreateIndividualRequest,
    InternalAcceptInviteRequest,
    InternalValidateInviteRequest,
    InviteMemberRequest,
    InviteMemberResponse,
    MembershipListResponse,
    MembershipResponse,
    Principal,
    TeamMemberResponse,
    UpdateMemberRoleRequest,
)

router = APIRouter(tags=["accounts"])


def account_response(row: dict[str, Any]) -> AccountResponse:
    return AccountResponse(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        role=row["role"],
        plan=row["plan"],
        credits=row["credits"],
        teamSize=row["team_size"],
    )


def account_summary_response(row: dict[str, Any]) -> AccountSummaryResponse:
    return AccountSummaryResponse(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        plan=row["plan"],
        credits=row["credits"],
        teamSize=row["team_size"],
    )


def membership_response(row: dict[str, Any]) -> MembershipResponse:
    return MembershipResponse(
        id=row["id"],
        account_id=row["account_id"],
        account_name=row["account_name"],
        account_type=row["account_type"],
        role=row["role"],
        status=row["status"],
        plan=row["plan"],
        credits=row["credits"],
        team_size=row["team_size"],
    )


def account_event(row: dict[str, Any], user_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "account_id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "plan": row["plan"],
        "credits": row["credits"],
        "team_size": row["team_size"],
    }
    if user_id:
        payload["user_id"] = user_id
    return payload


async def publish_or_log(event_bus: EventBus, routing_key: str, payload: dict[str, Any]) -> None:
    try:
        await event_bus.publish(routing_key, payload)
    except AccountError as exc:
        logging.warning("Unable to publish %s: %s", routing_key, exc.message)


@router.get("/", response_model=list[AccountResponse])
async def list_accounts(
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
) -> list[AccountResponse]:
    async with db.acquire() as conn:
        repo = AccountRepository(conn, settings)
        rows = await repo.list_user_memberships(principal.user_id)
    return [
        account_response(
            {
                "id": row["account_id"],
                "name": row["account_name"],
                "type": row["account_type"],
                "role": row["role"],
                "plan": row["plan"],
                "credits": row["credits"],
                "team_size": row["team_size"],
            }
        )
        for row in rows
    ]


@router.post("/", response_model=AccountResponse, status_code=201)
async def create_account(
    payload: CreateAccountRequest,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    event_bus: EventBus = Depends(event_bus_dep),
) -> AccountResponse:
    if payload.type == AccountType.PLATFORM:
        raise AccountError("invalid_account_type", "Platform accounts cannot be created through this endpoint.", 400)
    async with db.transaction() as conn:
        repo = AccountRepository(conn, settings)
        row = await repo.create_account_with_owner(
            principal.user_id,
            principal.email or f"user-{principal.user_id}@creditflow.local",
            payload.type,
            payload.name,
            principal.email.split("@", 1)[0] if principal.email else None,
        )
    await publish_or_log(event_bus, "account.created", account_event(row, principal.user_id))
    return account_response(row)


@router.get("/{account_id}/summary", response_model=AccountSummaryResponse)
async def account_summary(
    account_id: str,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
) -> AccountSummaryResponse:
    if principal.role != "SuperAdmin" and principal.account_id != account_id:
        raise AccountError("wrong_account_scope", "Request account does not match the active JWT account.", 403)
    async with db.acquire() as conn:
        repo = AccountRepository(conn, settings)
        if principal.role != "SuperAdmin":
            membership = await repo.get_active_membership(account_id, principal.user_id)
            if membership is None:
                raise AccountError("membership_required", "Active account membership is required.", 403)
        row = await repo.account_summary(account_id)
    if row is None:
        raise AccountError("account_not_found", "Account was not found.", 404)
    return account_summary_response(row)


@router.get("/{account_id}/team", response_model=list[TeamMemberResponse])
async def list_team(
    account_id: str,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
) -> list[TeamMemberResponse]:
    if principal.role != "SuperAdmin":
        await require_account_manager_membership(account_id, principal, db, settings)
    async with db.acquire() as conn:
        repo = AccountRepository(conn, settings)
        rows = await repo.list_team_members(account_id)
    return [TeamMemberResponse(**row) for row in rows]


@router.post("/{account_id}/invites", response_model=InviteMemberResponse, status_code=201)
async def invite_member(
    account_id: str,
    payload: InviteMemberRequest,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    event_bus: EventBus = Depends(event_bus_dep),
) -> InviteMemberResponse:
    await require_account_manager_membership(account_id, principal, db, settings)
    async with db.transaction() as conn:
        repo = AccountRepository(conn, settings)
        row, code = await repo.create_invite(account_id, payload.email, payload.role, principal.user_id)
    await publish_or_log(
        event_bus,
        "member.invited",
        {
            "account_id": account_id,
            "account_name": row.get("account_name"),
            "invite_id": row["invite_id"],
            "email": row["email"],
            "role": row["role"],
            "code": code,
            "expires_at": row["expires_at"],
            "created_by_user_id": principal.user_id,
        },
    )
    return InviteMemberResponse(**{**row, "code": code, "expires_at": row["expires_at"].isoformat()})


@router.patch("/{account_id}/members/{membership_id}", response_model=TeamMemberResponse)
async def update_member_role(
    account_id: str,
    membership_id: str,
    payload: UpdateMemberRoleRequest,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    event_bus: EventBus = Depends(event_bus_dep),
) -> TeamMemberResponse:
    await require_account_manager_membership(account_id, principal, db, settings)
    async with db.transaction() as conn:
        repo = AccountRepository(conn, settings)
        row = await repo.update_member_role(account_id, membership_id, payload.role)
    await publish_or_log(event_bus, "account.updated", {"account_id": account_id, "action": "member_role_updated", "member": row})
    return TeamMemberResponse(**row)


@router.delete("/{account_id}/members/{membership_id}", status_code=204)
async def remove_member(
    account_id: str,
    membership_id: str,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    event_bus: EventBus = Depends(event_bus_dep),
) -> Response:
    await require_account_manager_membership(account_id, principal, db, settings)
    async with db.transaction() as conn:
        repo = AccountRepository(conn, settings)
        row = await repo.remove_member(account_id, membership_id)
    await publish_or_log(event_bus, "account.updated", {"account_id": account_id, "action": "member_removed", "member": row})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/invites/accept", response_model=AccountResponse)
async def accept_invite(
    payload: AcceptInviteRequest,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    event_bus: EventBus = Depends(event_bus_dep),
) -> AccountResponse:
    async with db.transaction() as conn:
        repo = AccountRepository(conn, settings)
        row = await repo.accept_invite(payload.code, principal.user_id, principal.email)
    await publish_or_log(
        event_bus,
        "member.joined",
        {
            "account_id": row["id"],
            "user_id": principal.user_id,
            "member_id": row.get("member_id"),
            "invite_id": row.get("invite_id"),
            "role": row["role"],
        },
    )
    return account_response(row)


@router.get("/internal/users/{user_id}/memberships", response_model=MembershipListResponse, dependencies=[Depends(require_internal)])
async def internal_memberships(
    user_id: str,
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
) -> MembershipListResponse:
    async with db.acquire() as conn:
        repo = AccountRepository(conn, settings)
        rows = await repo.list_user_memberships(user_id)
    return MembershipListResponse(memberships=[membership_response(row) for row in rows])


@router.get("/internal/accounts", response_model=AdminAccountListResponse, dependencies=[Depends(require_internal)])
async def internal_admin_accounts(
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
) -> AdminAccountListResponse:
    safe_limit = max(1, min(limit, 250))
    safe_offset = max(0, offset)
    async with db.acquire() as conn:
        repo = AccountRepository(conn, settings)
        rows = await repo.list_accounts_for_admin(q=q, limit=safe_limit, offset=safe_offset)
    return AdminAccountListResponse(items=rows)


@router.post("/internal/users/{user_id}/individual-account", response_model=AccountResponse, dependencies=[Depends(require_internal)])
async def internal_create_individual_account(
    user_id: str,
    payload: InternalCreateIndividualRequest,
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    event_bus: EventBus = Depends(event_bus_dep),
) -> AccountResponse:
    async with db.transaction() as conn:
        repo = AccountRepository(conn, settings)
        row = await repo.ensure_individual_account(user_id, payload.email, payload.account_name, payload.name)
    if row.get("_created"):
        await publish_or_log(event_bus, "account.created", account_event(row, user_id))
    return account_response(row)


@router.post("/internal/invites/validate", dependencies=[Depends(require_internal)])
async def internal_validate_invite(
    payload: InternalValidateInviteRequest,
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
) -> dict[str, Any]:
    async with db.transaction() as conn:
        repo = AccountRepository(conn, settings)
        invite = await repo.validate_invite_for_email(payload.code, str(payload.email))
    return {"status": "valid", **invite, "expires_at": invite["expires_at"].isoformat()}


@router.post("/internal/invites/accept", response_model=AccountResponse, dependencies=[Depends(require_internal)])
async def internal_accept_invite(
    payload: InternalAcceptInviteRequest,
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    event_bus: EventBus = Depends(event_bus_dep),
) -> AccountResponse:
    async with db.transaction() as conn:
        repo = AccountRepository(conn, settings)
        row = await repo.accept_invite(payload.code, payload.user_id, str(payload.email), payload.name)
    await publish_or_log(
        event_bus,
        "member.joined",
        {
            "account_id": row["id"],
            "user_id": payload.user_id,
            "member_id": row.get("member_id"),
            "invite_id": row.get("invite_id"),
            "role": row["role"],
        },
    )
    return account_response(row)
