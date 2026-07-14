import re

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.auth import authenticate_request, enforce_roles, require_account
from app.errors import GatewayError

router = APIRouter(tags=["images"])


class ImageGenerationRequest(BaseModel):
    source_text: str = Field(min_length=1)
    source_generation_job_id: str | None = None
    prompt: str | None = Field(default=None, max_length=4000)


class ImageGenerationResponse(BaseModel):
    id: str
    status: str
    provider: str
    model: str
    prompt: str
    image_url: str | None = None
    download_url: str | None = None


async def _principal(request: Request):
    settings = request.app.state.settings
    principal = await authenticate_request(request, settings, request.app.state.redis_state)
    enforce_roles(principal, {"Owner", "TenantAdmin", "Member"})
    require_account(principal)
    return principal


@router.post("/content/generate/image", response_model=ImageGenerationResponse)
async def generate_image(request: Request, body: ImageGenerationRequest) -> ImageGenerationResponse:
    settings = request.app.state.settings
    principal = await _principal(request)
    payload = {
        "account_id": principal.account_id,
        "user_id": principal.user_id,
        "source_text": body.source_text,
        "source_generation_job_id": body.source_generation_job_id,
        "prompt": body.prompt,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.downstream_timeout_seconds + 90) as client:
            response = await client.post(
                f"{settings.ai_generation_service_url.rstrip('/')}/internal/images",
                json=payload,
                headers={"x-internal-token": settings.internal_service_token},
            )
            response.raise_for_status()
    except httpx.RequestError as exc:
        raise GatewayError("generation_service_unavailable", "AI Generation service is unavailable.", 502) from exc
    except httpx.HTTPStatusError as exc:
        raise GatewayError("image_generation_failed", "AI Generation service rejected the image request.", exc.response.status_code) from exc

    data = response.json()
    return ImageGenerationResponse(
        id=data["id"],
        status=data["status"],
        provider=data["provider"],
        model=data["model"],
        prompt=data["prompt"],
        image_url=data.get("image_url"),
        download_url=f"/content/generate/image/{data['id']}/download" if data.get("image_url") else None,
    )


@router.get("/content/generate/image/{image_id}/download")
async def download_image(request: Request, image_id: str) -> Response:
    settings = request.app.state.settings
    principal = await _principal(request)
    try:
        async with httpx.AsyncClient(timeout=settings.downstream_timeout_seconds) as client:
            metadata_response = await client.get(
                f"{settings.ai_generation_service_url.rstrip('/')}/internal/images/{image_id}",
                headers={"x-internal-token": settings.internal_service_token},
            )
            metadata_response.raise_for_status()
    except httpx.RequestError as exc:
        raise GatewayError("generation_service_unavailable", "AI Generation service is unavailable.", 502) from exc
    except httpx.HTTPStatusError as exc:
        raise GatewayError("image_not_found", "Generated image was not found.", exc.response.status_code) from exc

    image = metadata_response.json()
    if image.get("account_id") != principal.account_id:
        raise GatewayError("forbidden", "Image does not belong to the active account.", 403)
    image_url = image.get("image_url")
    if not image_url:
        raise GatewayError("image_not_ready", "Generated image is not ready for download.", 409)

    try:
        async with httpx.AsyncClient(timeout=settings.downstream_timeout_seconds + 90, follow_redirects=True) as client:
            image_response = await client.get(image_url)
            image_response.raise_for_status()
    except httpx.RequestError as exc:
        raise GatewayError("image_download_failed", "Generated image could not be downloaded.", 502) from exc
    except httpx.HTTPStatusError as exc:
        raise GatewayError("image_download_failed", "Generated image provider rejected the download.", exc.response.status_code) from exc

    content_type = image_response.headers.get("content-type", "image/jpeg")
    extension = "png" if "png" in content_type else "jpg"
    filename = re.sub(r"[^a-zA-Z0-9_-]+", "-", image_id).strip("-") or "generated-image"
    return Response(
        content=image_response.content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}.{extension}"'},
    )
