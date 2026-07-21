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
    checks = {"postgres": await db.ping(), "smtp_configured": settings.smtp_configured, "resend_api_key": bool(settings.resend_api_key)}
    email_configured = checks["smtp_configured"] or checks["resend_api_key"]
    resend_dev_mode = "@resend.dev" in settings.resend_from_email.lower()
    warnings = []
    if not email_configured:
        warnings.append("No email provider configured. Set SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD or RESEND_API_KEY.")
    if resend_dev_mode and not settings.smtp_configured:
        warnings.append("Using onboarding@resend.dev may restrict delivery to Resend-approved test recipients. Use a verified sender domain for real user emails.")
    status = "ready" if checks["postgres"] and email_configured and not warnings else "degraded"
    return {"status": status, "checks": checks, "provider": "smtp" if settings.smtp_configured else "resend", "resend_dev_mode": resend_dev_mode, "warnings": warnings}
