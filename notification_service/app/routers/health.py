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
    checks = {"postgres": await db.ping(), "smtp_configured": bool(settings.smtp_host and settings.smtp_username and settings.smtp_password)}
    gmail_smtp = settings.smtp_host.lower() == "smtp.gmail.com"
    warnings = []
    if gmail_smtp:
        warnings.append("Using Gmail SMTP. Make sure SMTP_PASSWORD is a Google App Password, not your normal Gmail password.")
    status = "ready" if all(checks.values()) else "degraded"
    return {"status": status, "checks": checks, "smtp_provider": "gmail" if gmail_smtp else "smtp", "warnings": warnings}
