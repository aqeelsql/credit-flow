from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request):
    database = request.app.state.database
    return {"status": "ok", "service": "social_publishing", "database": await database.ping()}

