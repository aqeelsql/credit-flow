import logging
import uuid

from flask import Flask, g, jsonify, request
from flask_cors import CORS

from app.auth import current_principal, require_publish_permission
from app.config import get_settings
from app.database import Database
from app.errors import ContentError, register_error_handlers
from app.events import EventBus
from app.repository import ContentRepository
from app.uploads import save_upload


def wants_post_draft(payload: dict) -> bool:
    content_type = str(payload.get("content_type") or payload.get("post_type") or "").lower()
    if content_type in {"post", "linkedin_post", "social_post"}:
        return True
    if content_type and content_type not in {"post", "linkedin_post", "social_post"}:
        return False
    prompt = str(payload.get("prompt") or "").lower()
    return any(word in prompt for word in ("post", "linkedin", "tweet", "social"))


def create_app() -> Flask:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_mb * 1024 * 1024
    CORS(app, origins=settings.cors_origins, supports_credentials=True)
    register_error_handlers(app)

    database = Database(settings)
    database.bootstrap()
    event_bus = EventBus(settings)
    app.config["database"] = database
    app.config["event_bus"] = event_bus

    def publish_or_log(routing_key: str, payload: dict) -> None:
        try:
            event_bus.publish(routing_key, payload)
        except Exception as exc:
            app.logger.warning("Skipped publishing %s: %s", routing_key, exc)

    def handle_event(routing_key: str, payload: dict) -> None:
        if routing_key != "ai.generation_completed" or not wants_post_draft(payload):
            return
        job_id = payload.get("job_id")
        account_id = payload.get("account_id")
        user_id = payload.get("user_id")
        response_text = payload.get("response_text")
        if not job_id or not account_id or not user_id or not response_text:
            app.logger.warning("Skipped incomplete ai.generation_completed event for content draft")
            return
        with database.transaction() as conn:
            repo = ContentRepository(conn)
            if repo.exists_for_generation(str(job_id)):
                return
            content = repo.create(account_id=str(account_id), user_id=str(user_id), body=str(response_text), prompt=str(payload.get("prompt") or ""), source_generation_job_id=str(job_id), image_url=payload.get("image_url"), image_asset_ref=payload.get("image_asset_ref"), metadata={"source": "ai.generation_completed", "model": payload.get("model")})
        publish_or_log("content.created", content)

    event_bus.handler = handle_event
    try:
        event_bus.start_consuming_background()
    except Exception as exc:
        app.logger.warning("RabbitMQ unavailable for content events: %s", exc)

    @app.before_request
    def add_request_id():
        g.request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

    @app.after_request
    def attach_request_id(response):
        response.headers["x-request-id"] = g.request_id
        return response

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "content", "database": database.ping()})

    @app.post("/drafts")
    def create_draft():
        principal = current_principal()
        data = request.get_json(silent=True) or {}
        body = str(data.get("body") or "").strip()
        if not body:
            raise ContentError("body_required", "Draft body is required.", 422)
        with database.transaction() as conn:
            content = ContentRepository(conn).create(account_id=principal.account_id, user_id=principal.user_id, title=data.get("title"), body=body, prompt=data.get("prompt"), source_generation_job_id=data.get("source_generation_job_id"), image_url=data.get("image_url"), image_asset_ref=data.get("image_asset_ref"), metadata=data.get("metadata") or {"has_image": bool(data.get("has_image"))})
        publish_or_log("content.created", content)
        return jsonify(content), 201

    @app.get("/items")
    @app.get("/drafts")
    def list_content():
        principal = current_principal()
        status = request.args.get("status")
        if request.path.endswith("/drafts") and not status:
            status = "draft"
        limit = min(max(int(request.args.get("limit", "50")), 1), 100)
        with database.transaction() as conn:
            items = ContentRepository(conn).list(principal.account_id, status, limit)
        return jsonify({"items": items})

    @app.get("/items/<content_id>")
    def get_content(content_id: str):
        principal = current_principal()
        with database.transaction() as conn:
            item = ContentRepository(conn).get(content_id, principal.account_id)
        if not item:
            raise ContentError("content_not_found", "Content item was not found.", 404)
        return jsonify(item)

    @app.patch("/items/<content_id>")
    def update_content(content_id: str):
        principal = current_principal()
        data = request.get_json(silent=True) or {}
        with database.transaction() as conn:
            item = ContentRepository(conn).update(content_id, principal.account_id, data, principal.user_id)
        publish_or_log("content.updated", item)
        return jsonify(item)

    @app.delete("/items/<content_id>")
    def delete_content(content_id: str):
        principal = current_principal()
        with database.transaction() as conn:
            item = ContentRepository(conn).transition(content_id, principal.account_id, "deleted", principal.user_id)
        publish_or_log("content.updated", item)
        return "", 204

    @app.post("/items/<content_id>/status")
    def change_status(content_id: str):
        principal = current_principal()
        data = request.get_json(silent=True) or {}
        status = str(data.get("status") or "").strip().lower()
        if status in {"approved", "published"}:
            require_publish_permission(principal)
        with database.transaction() as conn:
            item = ContentRepository(conn).transition(content_id, principal.account_id, status, principal.user_id)
        publish_or_log("content.updated", item)
        return jsonify(item)

    @app.post("/items/<content_id>/approve")
    def approve_content(content_id: str):
        principal = current_principal()
        require_publish_permission(principal)
        with database.transaction() as conn:
            item = ContentRepository(conn).transition(content_id, principal.account_id, "approved", principal.user_id)
        publish_or_log("content.updated", item)
        return jsonify(item)

    @app.post("/items/<content_id>/publish")
    def publish_content(content_id: str):
        principal = current_principal()
        require_publish_permission(principal)
        with database.transaction() as conn:
            item = ContentRepository(conn).transition(content_id, principal.account_id, "published", principal.user_id)
        publish_or_log("content.updated", item)
        return jsonify(item)

    @app.get("/items/<content_id>/versions")
    def versions(content_id: str):
        principal = current_principal()
        with database.transaction() as conn:
            rows = ContentRepository(conn).versions(content_id, principal.account_id)
        return jsonify({"items": rows})

    @app.post("/items/<content_id>/image")
    def upload_image(content_id: str):
        principal = current_principal()
        asset_ref = save_upload(settings, request.files.get("file"), principal.account_id)
        with database.transaction() as conn:
            item = ContentRepository(conn).update(content_id, principal.account_id, {"image_asset_ref": asset_ref}, principal.user_id)
        publish_or_log("content.updated", item)
        return jsonify(item)

    return app


app = create_app()
