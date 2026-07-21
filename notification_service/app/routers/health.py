from fastapi import APIRouter, Depends

from app.config import Settings
from app.database import Database
from app.dependencies import database_dep, settings_dep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "notification",
    }


@router.get("/ready")
async def ready(
    db: Database = Depends(database_dep),
    settings: Settings = Depends(settings_dep),
):
    checks = {
        "postgres": await db.ping(),
        "smtp_configured": settings.smtp_configured,
        "resend_configured": settings.resend_configured,
    }

    email_configured = (
        settings.smtp_configured
        or settings.resend_configured
    )

    gmail_smtp = (
        settings.smtp_configured
        and settings.smtp_host.lower() == "smtp.gmail.com"
    )

    resend_dev_mode = (
        settings.resend_configured
        and "@resend.dev" in settings.resend_from_email.lower()
    )

    warnings = []

    if not email_configured:
        warnings.append(
            "No email provider configured. Configure SMTP or Resend."
        )

    if gmail_smtp:
        warnings.append(
            "Using Gmail SMTP. SMTP_PASSWORD should be a Google App Password."
        )

    if resend_dev_mode:
        warnings.append(
            "Using onboarding@resend.dev. Emails may only reach Resend-approved recipients until you verify your own sending domain."
        )

    status = (
        "ready"
        if checks["postgres"] and email_configured
        else "degraded"
    )

    return {
        "status": status,
        "checks": checks,
        "provider": settings.provider if hasattr(settings, "provider") else (
            "smtp" if settings.smtp_configured else "resend"
        ),
        "warnings": warnings,
    }