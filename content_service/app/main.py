import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from app.auth import Principal, current_principal, require_publish_permission
from app.config import get_settings
from app.database import Database
from app.errors import ContentError, register_error_handlers
from app.events import EventBus
from app.repository import ContentRepository
from app.uploads import save_upload




async def json_body_or_empty(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()
    if not content_type.startswith("application/json"):
        return {}
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}

def wants_post_draft(payload: dict[str, Any]) -> bool:
    content_type = str(payload.get("content_type") or payload.get("post_type") or "").lower()
    if content_type in {"post", "linkedin_post", "social_post"}:
        return True
    if content_type and content_type not in {"post", "linkedin_post", "social_post"}:
        return False
    prompt = str(payload.get("prompt") or "").lower()
    return any(word in prompt for word in ("post", "linkedin", "tweet", "social"))


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    database = Database(settings)
    event_bus = EventBus(settings)

    def publish_or_log(routing_key: str, payload: dict[str, Any]) -> None:
        try:
            event_bus.publish(routing_key, payload)
        except Exception as exc:
            logging.warning("Skipped publishing %s: %s", routing_key, exc)

    def handle_event(routing_key: str, payload: dict[str, Any]) -> None:
        if routing_key != "ai.generation_completed" or not wants_post_draft(payload):
            return
        job_id = payload.get("job_id")
        account_id = payload.get("account_id")
        user_id = payload.get("user_id")
        response_text = payload.get("response_text")
        if not job_id or not account_id or not user_id or not response_text:
            logging.warning("Skipped incomplete ai.generation_completed event for content draft")
            return
        with database.transaction() as conn:
            repo = ContentRepository(conn)
            if repo.exists_for_generation(str(job_id)):
                return
            content = repo.create(
                account_id=str(account_id),
                user_id=str(user_id),
                body=str(response_text),
                prompt=str(payload.get("prompt") or ""),
                source_generation_job_id=str(job_id),
                image_url=payload.get("image_url"),
                image_asset_ref=payload.get("image_asset_ref"),
                metadata={"source": "ai.generation_completed", "model": payload.get("model")},
            )
        publish_or_log("content.created", content)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.bootstrap()
        event_bus.handler = handle_event
        app.state.database = database
        app.state.event_bus = event_bus
        app.state.settings = settings
        try:
            event_bus.start_consuming_background()
        except Exception as exc:
            logging.warning("RabbitMQ unavailable for content events: %s", exc)
        try:
            yield
        finally:
            event_bus.close()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        content_length = request.headers.get("content-length")
        try:
            too_large = bool(content_length) and int(content_length or "0") > settings.max_upload_mb * 1024 * 1024
        except ValueError:
            too_large = False
        if too_large:
            raise ContentError("payload_too_large", f"Request body cannot exceed {settings.max_upload_mb} MB.", 413)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "service": "content", "database": database.ping()}

    @app.post("/drafts", status_code=status.HTTP_201_CREATED)
    async def create_draft(request: Request, principal: Principal = Depends(current_principal)) -> dict[str, Any]:
        data = await json_body_or_empty(request)
        body = str(data.get("body") or "").strip()
        if not body:
            raise ContentError("body_required", "Draft body is required.", 422)
        with database.transaction() as conn:
            content = ContentRepository(conn).create(
                account_id=principal.account_id,
                user_id=principal.user_id,
                title=data.get("title"),
                body=body,
                prompt=data.get("prompt"),
                source_generation_job_id=data.get("source_generation_job_id"),
                image_url=data.get("image_url"),
                image_asset_ref=data.get("image_asset_ref"),
                metadata=data.get("metadata") or {"has_image": bool(data.get("has_image"))},
            )
        publish_or_log("content.created", content)
        return content

    @app.get("/items")
    @app.get("/drafts")
    async def list_content(
        request: Request,
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=100),
        principal: Principal = Depends(current_principal),
    ) -> dict[str, Any]:
        effective_status = status_filter
        if request.url.path.endswith("/drafts") and not effective_status:
            effective_status = "draft"
        with database.transaction() as conn:
            items = ContentRepository(conn).list(principal.account_id, effective_status, limit)
        return {"items": items}

    @app.get("/items/{content_id}")
    async def get_content(content_id: str, principal: Principal = Depends(current_principal)) -> dict[str, Any]:
        with database.transaction() as conn:
            item = ContentRepository(conn).get(content_id, principal.account_id)
        if not item:
            raise ContentError("content_not_found", "Content item was not found.", 404)
        return item

    @app.patch("/items/{content_id}")
    async def update_content(content_id: str, request: Request, principal: Principal = Depends(current_principal)) -> dict[str, Any]:
        data = await json_body_or_empty(request)
        with database.transaction() as conn:
            item = ContentRepository(conn).update(content_id, principal.account_id, data, principal.user_id)
        publish_or_log("content.updated", item)
        return item

    @app.delete("/items/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_content(content_id: str, principal: Principal = Depends(current_principal)) -> Response:
        with database.transaction() as conn:
            item = ContentRepository(conn).transition(content_id, principal.account_id, "deleted", principal.user_id)
        publish_or_log("content.updated", item)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/items/{content_id}/status")
    async def change_status(content_id: str, request: Request, principal: Principal = Depends(current_principal)) -> dict[str, Any]:
        data = await json_body_or_empty(request)
        next_status = str(data.get("status") or "").strip().lower()
        if next_status in {"approved", "published"}:
            require_publish_permission(principal)
        with database.transaction() as conn:
            item = ContentRepository(conn).transition(content_id, principal.account_id, next_status, principal.user_id)
        publish_or_log("content.updated", item)
        return item

    @app.post("/items/{content_id}/approve")
    async def approve_content(content_id: str, principal: Principal = Depends(current_principal)) -> dict[str, Any]:
        require_publish_permission(principal)
        with database.transaction() as conn:
            item = ContentRepository(conn).transition(content_id, principal.account_id, "approved", principal.user_id)
        publish_or_log("content.updated", item)
        return item

    @app.post("/items/{content_id}/publish")
    async def publish_content(content_id: str, principal: Principal = Depends(current_principal)) -> dict[str, Any]:
        require_publish_permission(principal)
        with database.transaction() as conn:
            item = ContentRepository(conn).transition(content_id, principal.account_id, "published", principal.user_id)
        publish_or_log("content.updated", item)
        return item

    @app.get("/items/{content_id}/versions")
    async def versions(content_id: str, principal: Principal = Depends(current_principal)) -> dict[str, Any]:
        with database.transaction() as conn:
            rows = ContentRepository(conn).versions(content_id, principal.account_id)
        return {"items": rows}

    @app.post("/items/{content_id}/image")
    async def upload_image(content_id: str, file: UploadFile | None = File(default=None), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
        asset_ref = save_upload(settings, file, principal.account_id)
        with database.transaction() as conn:
            item = ContentRepository(conn).update(content_id, principal.account_id, {"image_asset_ref": asset_ref}, principal.user_id)
        publish_or_log("content.updated", item)
        return item

    return app


app = create_app()