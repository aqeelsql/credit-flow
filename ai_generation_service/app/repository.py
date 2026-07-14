from decimal import Decimal
from typing import Any
import uuid

import asyncpg

from app.errors import GenerationError
from app.models import GenerationStatus, ImageGenerationStatus


def _uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


RETURNING_COLUMNS = """
    id::text AS id, account_id, user_id, request_id, channel, model, prompt,
    response_text, status, prompt_tokens, completion_tokens, total_tokens,
    cost, error_reason, cancellation_requested, created_at, started_at, completed_at
"""

IMAGE_RETURNING_COLUMNS = """
    id::text AS id, account_id, user_id, source_generation_job_id::text AS source_generation_job_id,
    provider, model, prompt, source_text, status, image_url, width, height, seed,
    error_reason, created_at, completed_at
"""


class GenerationRepository:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def create_job(
        self,
        account_id: str,
        user_id: str,
        request_id: str | None,
        channel: str,
        model: str,
        prompt: str,
    ) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            f"""
            INSERT INTO generation_jobs (account_id, user_id, request_id, channel, model, prompt)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING {RETURNING_COLUMNS}
            """,
            account_id,
            user_id,
            request_id,
            channel,
            model,
            prompt,
        )
        if row is None:
            raise GenerationError("job_create_failed", "Unable to create generation job.", 500)
        return dict(row)

    async def mark_streaming(self, job_id: str) -> None:
        await self.conn.execute(
            "UPDATE generation_jobs SET status = $2, started_at = now() WHERE id = $1",
            _uuid(job_id),
            GenerationStatus.STREAMING.value,
        )

    async def complete_job(
        self,
        job_id: str,
        response_text: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        cost: Decimal | None,
    ) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            f"""
            UPDATE generation_jobs
            SET status = $2, response_text = $3, prompt_tokens = $4,
                completion_tokens = $5, total_tokens = $6, cost = $7,
                completed_at = now()
            WHERE id = $1
            RETURNING {RETURNING_COLUMNS}
            """,
            _uuid(job_id),
            GenerationStatus.COMPLETED.value,
            response_text,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cost,
        )
        if row is None:
            raise GenerationError("job_not_found", "Generation job was not found.", 404)
        job = dict(row)
        await self.conn.execute(
            """
            INSERT INTO prompt_history (
                generation_job_id, account_id, user_id, model, prompt, response_text,
                prompt_tokens, completion_tokens, total_tokens, cost
            )
            SELECT id, account_id, user_id, model, prompt, response_text,
                   prompt_tokens, completion_tokens, total_tokens, cost
            FROM generation_jobs WHERE id = $1
            ON CONFLICT (generation_job_id) DO NOTHING
            """,
            _uuid(job_id),
        )
        return job

    async def finish_with_status(self, job_id: str, status: GenerationStatus, reason: str | None = None) -> None:
        await self.conn.execute(
            """
            UPDATE generation_jobs
            SET status = $2, error_reason = $3, completed_at = now()
            WHERE id = $1
            """,
            _uuid(job_id),
            status.value,
            reason,
        )

    async def request_cancellation(self, job_id: str, account_id: str | None = None) -> dict[str, Any] | None:
        if account_id is None:
            row = await self.conn.fetchrow(
                f"""UPDATE generation_jobs SET cancellation_requested = true
                WHERE id = $1 RETURNING {RETURNING_COLUMNS}""",
                _uuid(job_id),
            )
        else:
            row = await self.conn.fetchrow(
                f"""UPDATE generation_jobs SET cancellation_requested = true
                WHERE id = $1 AND account_id = $2 RETURNING {RETURNING_COLUMNS}""",
                _uuid(job_id),
                account_id,
            )
        return _dict(row)

    async def get_job(self, job_id: str, account_id: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(
            f"SELECT {RETURNING_COLUMNS} FROM generation_jobs WHERE id = $1 AND account_id = $2",
            _uuid(job_id),
            account_id,
        )
        return _dict(row)

    async def list_jobs(self, account_id: str, limit: int) -> list[dict[str, Any]]:
        rows = await self.conn.fetch(
            f"""SELECT {RETURNING_COLUMNS} FROM generation_jobs
            WHERE account_id = $1 ORDER BY created_at DESC LIMIT $2""",
            account_id,
            limit,
        )
        return [dict(row) for row in rows]

    async def create_image_job(
        self,
        account_id: str,
        user_id: str,
        source_generation_job_id: str | None,
        provider: str,
        model: str,
        prompt: str,
        source_text: str,
        width: int,
        height: int,
        seed: int,
    ) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            f"""
            INSERT INTO image_generation_jobs (
                account_id, user_id, source_generation_job_id, provider, model,
                prompt, source_text, width, height, seed
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING {IMAGE_RETURNING_COLUMNS}
            """,
            account_id,
            user_id,
            _uuid(source_generation_job_id) if source_generation_job_id else None,
            provider,
            model,
            prompt,
            source_text,
            width,
            height,
            seed,
        )
        if row is None:
            raise GenerationError("image_job_create_failed", "Unable to create image generation job.", 500)
        return dict(row)

    async def complete_image_job(self, image_id: str, image_url: str, seed: int) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            f"""
            UPDATE image_generation_jobs
            SET status = $2, image_url = $3, seed = $4, completed_at = now()
            WHERE id = $1
            RETURNING {IMAGE_RETURNING_COLUMNS}
            """,
            _uuid(image_id),
            ImageGenerationStatus.COMPLETED.value,
            image_url,
            seed,
        )
        if row is None:
            raise GenerationError("image_job_not_found", "Image generation job was not found.", 404)
        return dict(row)

    async def fail_image_job(self, image_id: str, reason: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(
            f"""
            UPDATE image_generation_jobs
            SET status = $2, error_reason = $3, completed_at = now()
            WHERE id = $1
            RETURNING {IMAGE_RETURNING_COLUMNS}
            """,
            _uuid(image_id),
            ImageGenerationStatus.FAILED.value,
            reason,
        )
        return _dict(row)

    async def get_image_job(self, image_id: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(
            f"SELECT {IMAGE_RETURNING_COLUMNS} FROM image_generation_jobs WHERE id = $1",
            _uuid(image_id),
        )
        return _dict(row)
