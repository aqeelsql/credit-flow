from fastapi import APIRouter, Request

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live():
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request):
    redis_ok = await request.app.state.redis_state.ping()
    rabbit_ok = await request.app.state.publisher.ready()
    return {
        "status": "ok" if redis_ok and rabbit_ok else "degraded",
        "checks": {
            "redis": redis_ok,
            "rabbitmq": rabbit_ok,
        },
    }