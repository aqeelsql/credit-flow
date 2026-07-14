from fastapi import APIRouter, Request

from app.webhook_security import normalize_webhook, verify_provider_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

ROUTING_PREFIX = {
    "stripe": "billing",
    "linkedin": "social",
    "openrouter": "ai",
}


async def handle_webhook(provider: str, request: Request):
    settings = request.app.state.settings
    redis_state = request.app.state.redis_state
    publisher = request.app.state.publisher
    body = await request.body()

    await verify_provider_signature(provider, request, body, settings)
    envelope = normalize_webhook(provider, body)
    is_new = await redis_state.mark_webhook_seen(provider, envelope.provider_event_id, settings.webhook_ttl_seconds)
    if not is_new:
        return {"status": "duplicate", "provider": provider, "event_id": envelope.provider_event_id}

    routing_key = f"{ROUTING_PREFIX[provider]}.{envelope.event_type}"
    await publisher.publish(routing_key, envelope.model_dump())
    return {"status": "accepted", "provider": provider, "event_id": envelope.provider_event_id, "routing_key": routing_key}


@router.post("/stripe")
async def stripe_webhook(request: Request):
    return await handle_webhook("stripe", request)


@router.post("/linkedin")
async def linkedin_webhook(request: Request):
    return await handle_webhook("linkedin", request)


@router.post("/openrouter")
async def openrouter_webhook(request: Request):
    return await handle_webhook("openrouter", request)