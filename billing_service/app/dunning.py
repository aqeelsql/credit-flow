import asyncio
import logging

from app.database import Database
from app.repository import BillingRepository
from app.service import BillingService


class DunningPoller:
    def __init__(self, database: Database, service: BillingService):
        self.database = database
        self.service = service
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="billing-dunning-poller")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                async with self.database.transaction() as conn:
                    await self.service.process_dunning(BillingRepository(conn))
            except Exception:
                logging.exception("Billing dunning poll failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60)
            except TimeoutError:
                pass

