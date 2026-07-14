from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request):
    return {"status": "ok", "service": "scraper", "mongodb": await request.app.state.mongo.ping()}
