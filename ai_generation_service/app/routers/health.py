from fastapi import APIRouter, Depends, Request

from app.database import Database
from app.dependencies import database_dep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ai-generation", "capabilities": ["text", "image"]}


@router.get("/ready")
async def ready(request: Request, db: Database = Depends(database_dep)) -> dict:
    postgres_ok = await db.ping()
    redis_ok = await request.app.state.redis_state.ping()
    provider_configured = bool(
        request.app.state.settings.openrouter_api_key and request.app.state.settings.openrouter_model
    )
    ready_state = postgres_ok and redis_ok and provider_configured
    return {
        "status": "ready" if ready_state else "degraded",
        "checks": {
            "postgres": postgres_ok,
            "redis": redis_ok,
            "openrouter_configured": provider_configured,
        },
    }
