import asyncio
import uuid
from types import SimpleNamespace

from app.events import ScraperEventBus
from app.post_writer import build_social_prompt, generate_social_post, save_content_draft
from app.repository import ScraperRepository
from app.research import ResearchRunner
from app.schemas import TopicResearchRequest


class RecurringScrapeScheduler:
    def __init__(self, repo: ScraperRepository, events: ScraperEventBus, interval_seconds: int, settings=None):
        self.repo = repo
        self.events = events
        self.interval_seconds = interval_seconds
        self.settings = settings
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
                if self.settings is not None:
                    due_research = await self.repo.due_research_jobs()
                    for job in due_research:
                        body = TopicResearchRequest.model_validate({
                            "topic": job["topic"],
                            "job_type": job.get("job_type", "topic_research"),
                            "output_type": job.get("output_type", "linkedin_post"),
                            "max_sources": int(job.get("max_sources", self.settings.research_default_max_sources)),
                            "metadata": {**job.get("metadata", {}), "research_job_id": str(job["_id"])},
                        })
                        pack = await ResearchRunner(self.settings, self.repo).run(body, job.get("account_id"), job.get("created_by_user_id"), str(job["_id"]))
                        if job.get("auto_generate_post"):
                            principal = SimpleNamespace(user_id=job.get("created_by_user_id"), account_id=job.get("account_id"), role="Owner")
                            prompt = build_social_prompt(pack, str(pack.get("output_type") or "linkedin_post"))
                            post_text = await generate_social_post(self.settings, pack, str(pack.get("output_type") or "linkedin_post"))
                            content_draft = await save_content_draft(self.settings, principal, pack, post_text, prompt)
                            await self.repo.attach_generated_post(pack["id"], post_text, content_draft)
                        await self.repo.mark_research_job_dispatched(job["_id"], str(job.get("cadence") or "daily"))
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue
