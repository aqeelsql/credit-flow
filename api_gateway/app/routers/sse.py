import json
import uuid

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.auth import authenticate_request, enforce_roles, require_account
from app.errors import GatewayError

router = APIRouter(tags=["sse"])


async def start_generation(request: Request, prompt: str) -> tuple[str, str]:
    settings = request.app.state.settings
    principal = await authenticate_request(request, settings, request.app.state.redis_state)
    enforce_roles(principal, {"Owner", "TenantAdmin", "Member"})
    require_account(principal)

    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    payload = {
        "prompt": prompt,
        "account_id": principal.account_id,
        "user_id": principal.user_id,
        "request_id": request_id,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.sse_start_timeout_seconds) as client:
            response = await client.post(
                f"{settings.ai_generation_service_url.rstrip('/')}/internal/generations",
                json=payload,
                headers={"x-internal-token": settings.internal_service_token},
            )
            response.raise_for_status()
    except httpx.RequestError as exc:
        raise GatewayError("generation_service_unavailable", "AI Generation service is unavailable.", 502) from exc
    except httpx.HTTPStatusError as exc:
        raise GatewayError("generation_start_failed", "AI Generation service rejected the request.", exc.response.status_code) from exc

    data = response.json()
    channel = data.get("channel")
    if not channel:
        channel = f"ai-generation:{principal.account_id}:{request_id}"
    job_id = data.get("job_id")
    if not job_id:
        raise GatewayError("invalid_generation_response", "AI Generation service did not return a job ID.", 502)
    return str(channel), str(job_id)


async def cancel_generation(request: Request, job_id: str) -> None:
    settings = request.app.state.settings
    try:
        async with httpx.AsyncClient(timeout=settings.sse_start_timeout_seconds) as client:
            await client.post(
                f"{settings.ai_generation_service_url.rstrip('/')}/internal/generations/{job_id}/cancel",
                headers={"x-internal-token": settings.internal_service_token},
            )
    except httpx.RequestError:
        pass


async def event_stream(request: Request, channel: str, job_id: str):
    redis_state = request.app.state.redis_state
    pubsub = await redis_state.subscribe(channel)
    terminal_event_received = False
    try:
        while True:
            if await request.is_disconnected():
                break
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
            if message is None:
                yield ": heartbeat\n\n"
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            if data is None:
                continue
            yield f"data: {data}\n\n"
            if data == "[DONE]":
                terminal_event_received = True
                break
            try:
                parsed = json.loads(data)
                if parsed.get("event") in {"done", "error"}:
                    terminal_event_received = True
                    break
            except json.JSONDecodeError:
                pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        if not terminal_event_received:
            await cancel_generation(request, job_id)


@router.get("/content/generate/stream")
async def stream_generation(request: Request, prompt: str = Query(min_length=1)):
    channel, job_id = await start_generation(request, prompt)
    return StreamingResponse(
        event_stream(request, channel, job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
