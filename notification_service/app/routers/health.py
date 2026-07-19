from fastapi import APIRouter, Depends

from app.config import Settings
from app.database import Database
from app.dependencies import database_dep, settings_dep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "notification"}


@router.get("/ready")
async def ready(db: Database = Depends(database_dep), settings: Settings = Depends(settings_dep)):
    checks = {"postgres": await db.ping(), "resend_api_key": bool(settings.resend_api_key)}
    resend_dev_mode = "@resend.dev" in settings.resend_from_email.lower()
    warnings = []
    if resend_dev_mode:
        warnings.append("Using onboarding@resend.dev may restrict delivery to Resend-approved test recipients. Use a verified sender domain for real user emails.")
    status = "ready" if all(checks.values()) and not warnings else "degraded"
    return {"status": status, "checks": checks, "resend_dev_mode": resend_dev_mode, "warnings": warnings}
