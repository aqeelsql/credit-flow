import asyncio
import uuid

from app.events import ScraperEventBus
from app.repository import ScraperRepository


class RecurringScrapeScheduler:
    def __init__(self, repo: ScraperRepository, events: ScraperEventBus, interval_seconds: int):
        self.repo = repo
        self.events = events
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="recurring-scrape-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                due = await self.repo.due_recurring()
                for job in due:
                    event_id = f"recurring:{job['_id']}:{uuid.uuid4()}"
                    await self.events.publish("scrape.requested", {"event_id": event_id, "account_id": job.get("account_id"), "requested_by_user_id": job.get("created_by_user_id"), "target_url": job["target_url"], "job_type": job.get("job_type", "competitor_check"), "metadata": {**job.get("metadata", {}), "recurring_job_id": str(job["_id"])}})
                    await self.repo.mark_recurring_dispatched(job["_id"], int(job.get("interval_seconds", 86400)))
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue
