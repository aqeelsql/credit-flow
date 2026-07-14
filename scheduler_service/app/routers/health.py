from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request):
    return {"status": "ok", "service": "scheduler", "database": await request.app.state.database.ping()}
