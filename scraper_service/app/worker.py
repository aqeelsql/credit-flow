import logging

import aio_pika

from app.config import Settings
from app.crawler import ScrapeRunner
from app.errors import ScraperError
from app.events import ScraperEventBus
from app.repository import ScraperRepository
from app.schemas import ScrapeRequested


class ScrapeWorker:
    def __init__(self, settings: Settings, repo: ScraperRepository, events: ScraperEventBus):
        self.settings = settings
        self.repo = repo
        self.events = events

    async def handle(self, raw_payload: dict, message: aio_pika.IncomingMessage | None = None) -> None:
        payload = ScrapeRequested.model_validate(raw_payload)
        claimed = await self.repo.claim_event(payload.event_id, raw_payload)
        if not claimed:
            logging.info("Skipping duplicate scrape event %s", payload.event_id)
            return
        try:
            result = await ScrapeRunner(self.settings, self.repo).run(payload)
            await self.repo.complete_event(payload.event_id, result["document_id"])
            await self.events.publish("scrape.completed", {"event_id": payload.event_id, "account_id": payload.account_id, "job_type": payload.job_type, "target_url": payload.target_url, "document_id": result["document_id"], "mongodb_database": self.settings.mongodb_database, "mongodb_collection": self.settings.mongodb_collection})
        except Exception as exc:
            reason = exc.message if isinstance(exc, ScraperError) else str(exc)
            retry_count = 0
            if message is not None and message.headers:
                retry_count = int(message.headers.get("x-retry-count") or 0)
            if retry_count < self.settings.max_retries:
                next_retry_count = retry_count + 1
                await self.repo.retry_event(payload.event_id, reason, next_retry_count)
                await self.events.publish_retry(raw_payload, next_retry_count)
                return
            await self.repo.fail_event(payload.event_id, reason)
            await self.events.publish("scrape.failed", {"event_id": payload.event_id, "account_id": payload.account_id, "job_type": payload.job_type, "target_url": payload.target_url, "error_reason": reason})
            raise
