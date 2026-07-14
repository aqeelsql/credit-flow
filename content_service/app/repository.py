from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from app.errors import ContentError

VALID_STATUSES = {"draft", "approved", "published", "deleted"}
STATUS_TRANSITIONS = {
    "draft": {"draft", "approved", "deleted"},
    "approved": {"draft", "approved", "published", "deleted"},
    "published": {"published", "deleted"},
    "deleted": {"deleted"},
}

RETURNING_COLUMNS = """
    id::text AS id, account_id, created_by_user_id, title, body, prompt, status,
    source_generation_job_id::text AS source_generation_job_id,
    image_url, image_asset_ref, metadata, created_at, updated_at,
    approved_at, published_at, deleted_at
"""


def as_uuid(value: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise ContentError("invalid_content_id", "Content ID is invalid.", 422) from exc


def make_title(body: str, prompt: str | None = None) -> str:
    source = (prompt or body).strip().replace("\n", " ")
    if not source:
        return "Untitled draft"
    return source[:72] + ("..." if len(source) > 72 else "")


class ContentRepository:
    def __init__(self, conn):
        self.conn = conn

    def create(self, account_id: str, user_id: str, body: str, title: str | None = None, prompt: str | None = None, source_generation_job_id: str | None = None, image_url: str | None = None, image_asset_ref: str | None = None, metadata: dict[str, Any] | None = None) -> dict:
        row = self.conn.execute(
            f"""
            INSERT INTO content (account_id, created_by_user_id, title, body, prompt, source_generation_job_id, image_url, image_asset_ref, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {RETURNING_COLUMNS}
            """,
            (account_id, user_id, title or make_title(body, prompt), body, prompt, as_uuid(source_generation_job_id) if source_generation_job_id else None, image_url, image_asset_ref, Jsonb(metadata or {})),
        ).fetchone()
        self._create_version(row)
        return row

    def list(self, account_id: str, status: str | None, limit: int) -> list[dict]:
        if status:
            if status not in VALID_STATUSES:
                raise ContentError("invalid_status", "Content status is invalid.", 422)
            return self.conn.execute(
                f"""SELECT {RETURNING_COLUMNS} FROM content WHERE account_id = %s AND status = %s AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT %s""",
                (account_id, status, limit),
            ).fetchall()
        return self.conn.execute(
            f"""SELECT {RETURNING_COLUMNS} FROM content WHERE account_id = %s AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT %s""",
            (account_id, limit),
        ).fetchall()

    def get(self, content_id: str, account_id: str) -> dict | None:
        return self.conn.execute(
            f"""SELECT {RETURNING_COLUMNS} FROM content WHERE id = %s AND account_id = %s AND deleted_at IS NULL""",
            (as_uuid(content_id), account_id),
        ).fetchone()

    def update(self, content_id: str, account_id: str, updates: dict[str, Any], user_id: str) -> dict:
        current = self.get(content_id, account_id)
        if not current:
            raise ContentError("content_not_found", "Content item was not found.", 404)
        if current["status"] == "published":
            raise ContentError("published_content_locked", "Published content cannot be edited.", 409)
        allowed = {"title", "body", "prompt", "image_url", "image_asset_ref", "metadata"}
        clean = {key: value for key, value in updates.items() if key in allowed}
        if "metadata" in clean:
            clean["metadata"] = Jsonb(clean["metadata"] or {})
        if not clean:
            return current
        assignments = ", ".join(f"{key} = %s" for key in clean)
        values = list(clean.values()) + [as_uuid(content_id), account_id]
        row = self.conn.execute(
            f"""UPDATE content SET {assignments}, updated_at = now() WHERE id = %s AND account_id = %s AND deleted_at IS NULL RETURNING {RETURNING_COLUMNS}""",
            values,
        ).fetchone()
        self._create_version(row, user_id)
        return row

    def transition(self, content_id: str, account_id: str, status: str, user_id: str) -> dict:
        if status not in VALID_STATUSES:
            raise ContentError("invalid_status", "Content status is invalid.", 422)
        current = self.get(content_id, account_id)
        if not current:
            raise ContentError("content_not_found", "Content item was not found.", 404)
        if status not in STATUS_TRANSITIONS[current["status"]]:
            raise ContentError("invalid_status_transition", f"Cannot move content from {current['status']} to {status}.", 409)
        row = self.conn.execute(
            f"""
            UPDATE content
            SET status = %s, updated_at = now(),
                approved_at = CASE WHEN %s = 'approved' THEN now() ELSE approved_at END,
                published_at = CASE WHEN %s = 'published' THEN now() ELSE published_at END,
                deleted_at = CASE WHEN %s = 'deleted' THEN now() ELSE deleted_at END
            WHERE id = %s AND account_id = %s
            RETURNING {RETURNING_COLUMNS}
            """,
            (status, status, status, status, as_uuid(content_id), account_id),
        ).fetchone()
        self._create_version(row, user_id)
        return row

    def versions(self, content_id: str, account_id: str) -> list[dict]:
        if not self.get(content_id, account_id):
            raise ContentError("content_not_found", "Content item was not found.", 404)
        return self.conn.execute(
            """
            SELECT id::text AS id, content_id::text AS content_id, version_number, title, body, prompt, image_url, image_asset_ref, status, created_by_user_id, created_at
            FROM content_versions WHERE content_id = %s ORDER BY version_number DESC
            """,
            (as_uuid(content_id),),
        ).fetchall()

    def exists_for_generation(self, generation_job_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM content WHERE source_generation_job_id = %s LIMIT 1", (as_uuid(generation_job_id),)).fetchone() is not None

    def _create_version(self, content: dict, user_id: str | None = None) -> None:
        next_version = self.conn.execute("SELECT COALESCE(MAX(version_number), 0) + 1 AS version_number FROM content_versions WHERE content_id = %s", (as_uuid(content["id"]),)).fetchone()["version_number"]
        self.conn.execute(
            """
            INSERT INTO content_versions (content_id, version_number, title, body, prompt, image_url, image_asset_ref, status, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (as_uuid(content["id"]), next_version, content["title"], content["body"], content.get("prompt"), content.get("image_url"), content.get("image_asset_ref"), content["status"], user_id or content["created_by_user_id"]),
        )
