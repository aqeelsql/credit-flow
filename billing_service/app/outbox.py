import asyncio
import logging

from app.database import Database
from app.events import BillingEventPublisher
from app.repository import BillingRepository


class OutboxPoller:
    def __init__(self, database: Database, publisher: BillingEventPublisher):
        self.database = database
        self.publisher = publisher
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="billing-outbox-poller")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        settings = self.database.settings
        while not self._stop.is_set():
            try:
                await self.publish_once()
            except Exception:
                logging.exception("Billing outbox poll failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.outbox_poll_interval_seconds)
            except TimeoutError:
                pass

    async def publish_once(self) -> None:
        async with self.database.acquire() as conn:
            repo = BillingRepository(conn)
            batch = await repo.claim_outbox_batch(self.database.settings.outbox_batch_size)
        for event in batch:
            try:
                await self.publisher.publish(event["routing_key"], dict(event["payload"] or {}))
                async with self.database.acquire() as conn:
                    await BillingRepository(conn).mark_outbox_published(event["id"])
            except Exception as exc:
                async with self.database.acquire() as conn:
                    await BillingRepository(conn).mark_outbox_failed(event["id"], str(exc))

