from fastapi import APIRouter, Depends, Query

from app.aggregator import AggregatorClient
from app.config import get_settings
from app.database import Database
from app.dependencies import current_principal, database_dep, redis_sessions_dep, scoped_account
from app.redis_sessions import RedisSessions
from app.repository import AuditRepository
from app.schemas import AccountOverviewResponse, AuditLogResponse, PlatformAccountResponse, PlatformOverviewResponse, Principal, RevokeSessionResponse, SessionResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(account_id: str | None = Query(default=None), principal: Principal = Depends(current_principal), redis_sessions: RedisSessions = Depends(redis_sessions_dep)):
    scoped = scoped_account(principal, account_id)
    rows = await redis_sessions.list_sessions(scoped)
    return [SessionResponse(**row) for row in rows]


@router.delete("/sessions/{jti}", response_model=RevokeSessionResponse)
async def revoke_session(jti: str, principal: Principal = Depends(current_principal), redis_sessions: RedisSessions = Depends(redis_sessions_dep)):
    if principal.role != "SuperAdmin":
        rows = await redis_sessions.list_sessions(principal.account_id)
        if not any(row["jti"] == jti for row in rows):
            from app.errors import AdminError
            raise AdminError("wrong_account_scope", "TenantAdmin can only revoke sessions in their own account.", 403)
    result = await redis_sessions.revoke_session(jti)
    return RevokeSessionResponse(**result)


@router.get("/audit-log", response_model=AuditLogResponse)
async def audit_log(account_id: str | None = Query(default=None), action: str | None = Query(default=None), actor_user_id: str | None = Query(default=None), q: str | None = Query(default=None), limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)):
    scoped = scoped_account(principal, account_id)
    async with db.acquire() as conn:
        rows = await AuditRepository(conn).search(account_id=scoped, action=action, actor_user_id=actor_user_id, q=q, limit=limit, offset=offset)
    return AuditLogResponse(items=rows)



@router.get("/accounts", response_model=list[PlatformAccountResponse])
async def list_accounts(q: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0), principal: Principal = Depends(current_principal)):
    if principal.role != "SuperAdmin":
        from app.errors import AdminError
        raise AdminError("superadmin_required", "SuperAdmin role is required to browse all platform accounts.", 403)
    rows = await AggregatorClient(get_settings()).list_accounts(principal, q=q, limit=limit, offset=offset)
    return [PlatformAccountResponse(**row) for row in rows]


@router.get("/platform/overview", response_model=PlatformOverviewResponse)
async def platform_overview(q: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500), principal: Principal = Depends(current_principal)):
    if principal.role != "SuperAdmin":
        from app.errors import AdminError
        raise AdminError("superadmin_required", "SuperAdmin role is required to view platform-wide operations.", 403)
    data = await AggregatorClient(get_settings()).platform_overview(principal, q=q, limit=limit)
    return PlatformOverviewResponse(**data)

@router.get("/accounts/{account_id}/overview", response_model=AccountOverviewResponse)
async def account_overview(account_id: str, principal: Principal = Depends(current_principal)):
    scoped_account(principal, account_id)
    data = await AggregatorClient(get_settings()).account_overview(account_id, principal)
    return AccountOverviewResponse(**data)


