from fastapi import APIRouter, Depends, Query

from app.config import Settings
from app.database import Database
from app.dependencies import database_dep, redis_quota_dep
from app.redis_quota import RedisQuota
from app.repository import UsageRepository, current_period
from app.schemas import AccountQuotaRequest, AccountQuotaResponse, QuotaCheckRequest, QuotaCheckResponse, UsageSummaryResponse
from app.security import require_internal, settings_dep

router = APIRouter(tags=["usage"])


@router.post("/internal/quota/check", response_model=QuotaCheckResponse, dependencies=[Depends(require_internal)])
async def check_quota(payload: QuotaCheckRequest, settings: Settings = Depends(settings_dep), db: Database = Depends(database_dep), redis_quota: RedisQuota = Depends(redis_quota_dep)):
    period = redis_quota.period()
    request_id = payload.request_id or f"{payload.operation}:{payload.account_id}:{payload.user_id or 'unknown'}:{payload.model}:{period}"
    async with db.acquire() as conn:
        repo = UsageRepository(conn)
        quota = await repo.quota_for_account(payload.account_id, settings.default_monthly_token_quota)
        ledger_used = await repo.used_tokens(payload.account_id, period)
    quota_tokens = int(quota["monthly_token_quota"])
    if not quota.get("enabled", True):
        return QuotaCheckResponse(allowed=False, account_id=payload.account_id, quota_tokens=quota_tokens, used_tokens=ledger_used, reserved_tokens=0, remaining_tokens=max(quota_tokens - ledger_used, 0), period=period, request_id=request_id, reason="quota_disabled")
    result = await redis_quota.reserve(payload.account_id, request_id, payload.max_tokens, quota_tokens, ledger_used)
    return QuotaCheckResponse(allowed=result["allowed"], account_id=payload.account_id, quota_tokens=quota_tokens, used_tokens=result["used_tokens"], reserved_tokens=payload.max_tokens if result["allowed"] else 0, remaining_tokens=result["remaining_tokens"], period=period, request_id=request_id, reason=None if result["allowed"] else "quota_exceeded")


@router.post("/internal/reconcile/{account_id}", dependencies=[Depends(require_internal)])
async def reconcile_account(account_id: str, period: str | None = Query(default=None), db: Database = Depends(database_dep), redis_quota: RedisQuota = Depends(redis_quota_dep)):
    period = period or current_period()
    async with db.acquire() as conn:
        used = await UsageRepository(conn).used_tokens(account_id, period)
    await redis_quota.reconcile(account_id, used, period)
    return {"account_id": account_id, "period": period, "used_tokens": used, "reconciled": True}


@router.post("/internal/quotas/{account_id}", response_model=AccountQuotaResponse, dependencies=[Depends(require_internal)])
async def set_account_quota(account_id: str, payload: AccountQuotaRequest, db: Database = Depends(database_dep)):
    async with db.transaction() as conn:
        row = await UsageRepository(conn).upsert_quota(account_id, payload.monthly_token_quota, payload.enabled, payload.metadata)
    return AccountQuotaResponse(**row)


@router.get("/usage/accounts/{account_id}/summary", response_model=UsageSummaryResponse)
async def account_usage_summary(account_id: str, period: str | None = Query(default=None), settings: Settings = Depends(settings_dep), db: Database = Depends(database_dep)):
    period = period or current_period()
    async with db.acquire() as conn:
        repo = UsageRepository(conn)
        quota = await repo.quota_for_account(account_id, settings.default_monthly_token_quota)
        summary = await repo.summary(account_id=account_id, period=period)
    quota_tokens = int(quota["monthly_token_quota"])
    return UsageSummaryResponse(account_id=account_id, period=period, quota_tokens=quota_tokens, used_tokens=summary["used_tokens"], total_cost=summary["total_cost"], remaining_tokens=max(quota_tokens - summary["used_tokens"], 0), models=summary["models"])


@router.get("/admin/usage/summary", response_model=UsageSummaryResponse)
async def admin_usage_summary(period: str | None = Query(default=None), db: Database = Depends(database_dep)):
    async with db.acquire() as conn:
        summary = await UsageRepository(conn).summary(period=period)
    return UsageSummaryResponse(account_id=None, period=period, quota_tokens=None, used_tokens=summary["used_tokens"], total_cost=summary["total_cost"], remaining_tokens=None, models=summary["models"])

