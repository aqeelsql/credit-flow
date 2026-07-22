from fastapi import APIRouter, Depends, Query

from app.aggregator import AggregatorClient
from app.config import get_settings
from app.database import Database
from app.dependencies import current_principal, database_dep, redis_sessions_dep, scoped_account
from app.redis_sessions import RedisSessions
from app.repository import AuditRepository, PlatformReadRepository
from app.schemas import AccountDirectoryResponse, AccountOverviewResponse, AuditLogResponse, OpsSummaryResponse, Principal, RevokeSessionResponse, SessionResponse

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


@router.get("/accounts", response_model=AccountDirectoryResponse)
async def account_directory(q: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=250), offset: int = Query(default=0, ge=0), principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)):
    settings = get_settings()
    if principal.role != "SuperAdmin":
        account_id = scoped_account(principal, None)
        data = await AggregatorClient(settings).account_overview(account_id or "", principal)
        account = data.get("account") or {}
        return AccountDirectoryResponse(
            items=[
                {
                    "id": account_id or "",
                    "name": str(account.get("name") or account_id or "Current account"),
                    "type": str(account.get("type") or "team"),
                    "plan": str(account.get("plan") or "Unknown"),
                    "credits": int(account.get("credits") or 0),
                    "team_size": len(data.get("members") or []),
                    "owner_name": None,
                    "owner_email": None,
                    "created_at": "",
                    "updated_at": "",
                }
            ],
            errors=data.get("errors") or {},
        )

    data = await AggregatorClient(settings).list_accounts(q=q, limit=limit, offset=offset, principal=principal)
    errors = data.get("errors") or {}
    if data.get("items") and not errors.get("accounts"):
        return AccountDirectoryResponse(**data)

    try:
        async with db.acquire() as conn:
            rows = await PlatformReadRepository(
                conn,
                user_tenant_schema=settings.user_tenant_database_schema,
                billing_schema=settings.billing_database_schema,
            ).list_accounts(q=q, limit=limit, offset=offset)
        return AccountDirectoryResponse(items=rows, errors={})
    except Exception as exc:
        fallback_errors = errors if isinstance(errors, dict) else {}
        fallback_errors["accounts"] = f"Directory fallback failed: {exc}"
        return AccountDirectoryResponse(items=[], errors=fallback_errors)


@router.get("/ops-summary", response_model=OpsSummaryResponse)
async def ops_summary(principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)):
    if principal.role != "SuperAdmin":
        from app.errors import AdminError
        raise AdminError("forbidden", "Only SuperAdmin can view platform-wide ops metrics.", 403)

    settings = get_settings()
    data = await AggregatorClient(settings).platform_ops_summary(principal)
    inventory = {
        "total_credits_generated": data.get("total_credits_generated", 0),
        "package_count": data.get("package_count", 0),
        "active_package_credits": data.get("active_package_credits", 0),
        "active_package_count": data.get("active_package_count", 0),
        "total_credits_sold": data.get("total_credits_sold", 0),
        "total_money_generated_cents": data.get("total_money_generated_cents", 0),
        "purchase_count": data.get("purchase_count", 0),
        "currency": data.get("currency", "usd"),
        "credits_left": data.get("credits_left", 0),
    }
    async with db.acquire() as conn:
        repo = PlatformReadRepository(
            conn,
            user_tenant_schema=settings.user_tenant_database_schema,
            billing_schema=settings.billing_database_schema,
        )
        try:
            inventory = await repo.credit_package_inventory()
        except Exception as exc:
            data.setdefault("errors", {})["credit_inventory"] = str(exc)
        if data.get("errors", {}).get("accounts"):
            try:
                accounts = await repo.list_accounts(limit=250, offset=0)
                data["account_count"] = len(accounts)
                data["errors"].pop("accounts", None)
            except Exception:
                pass

    merged = {**data, **inventory}
    merged["errors"] = data.get("errors") or {}
    return OpsSummaryResponse(**merged)


@router.get("/accounts/{account_id}/overview", response_model=AccountOverviewResponse)
async def account_overview(account_id: str, principal: Principal = Depends(current_principal)):
    scoped_account(principal, account_id)
    data = await AggregatorClient(get_settings()).account_overview(account_id, principal)
    return AccountOverviewResponse(**data)


