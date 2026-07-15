import logging

import aio_pika

from app.crypto import TokenCipher
from app.database import Database
from app.events import SocialEventBus
from app.linkedin import LinkedInPermanentError, LinkedInTransientError
from app.publisher import PublishPipeline
from app.repository import SocialRepository


class SocialWorker:
    def __init__(self, database: Database, events: SocialEventBus, cipher: TokenCipher):
        self.database = database
        self.events = events
        self.cipher = cipher

    async def handle(self, payload: dict, message: aio_pika.IncomingMessage | None = None) -> None:
        retry_count = 0
        if message is not None and message.headers:
            retry_count = int(message.headers.get("x-retry-count") or 0)
        async with self.database.transaction() as conn:
            repo = SocialRepository(conn)
            pipeline = PublishPipeline(self.database.settings, self.cipher, self.events)
            try:
                await pipeline.publish_scheduled(repo, payload)
            except LinkedInTransientError as exc:
                await self._retry_or_fail(repo, payload, retry_count, str(exc))
            except (LinkedInPermanentError, Exception) as exc:
                logging.exception("Social publishing failed")
                await self._fail(repo, payload, str(exc))

    async def _retry_or_fail(self, repo: SocialRepository, payload: dict, retry_count: int, reason: str) -> None:
        if retry_count < self.database.settings.max_retries:
            await self.events.publish_retry(payload, retry_count + 1)
            return
        await self._fail(repo, payload, reason)
        await self.events.publish("post.failed.dlq", {**payload, "reason": reason, "attempts": retry_count + 1})

    async def _fail(self, repo: SocialRepository, payload: dict, reason: str) -> None:
        account_id = str(payload.get("account_id") or "")
        content_id = str(payload.get("content_id") or "")
        scheduled_post_id = payload.get("scheduled_post_id")
        if account_id and content_id:
            job = await repo.create_or_get_job(account_id=account_id, scheduled_post_id=str(scheduled_post_id) if scheduled_post_id else None, content_id=content_id, payload=payload)
            await repo.mark_job_failed(job["id"], reason)
        await self.events.publish("post.failed", {**payload, "reason": reason})

