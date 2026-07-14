import asyncio
from decimal import Decimal
import logging
import uuid

from app.config import Settings
from app.database import Database
from app.errors import GenerationError
from app.events import EventPublisher
from app.models import GenerationStatus
from app.openrouter import OpenRouterClient
from app.redis_state import GenerationRedis
from app.repository import GenerationRepository
from app.schemas import StartGenerationRequest
from app.usage import UsageQuotaClient


class GenerationManager:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        redis_state: GenerationRedis,
        events: EventPublisher,
    ):
        self.settings = settings
        self.database = database
        self.redis_state = redis_state
        self.events = events
        self.provider = OpenRouterClient(settings)
        self.usage = UsageQuotaClient(settings)
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self, request: StartGenerationRequest) -> dict:
        self.provider.validate_configuration()
        if len(request.prompt) > self.settings.max_prompt_characters:
            raise GenerationError(
                "prompt_too_long",
                f"Prompt exceeds {self.settings.max_prompt_characters} characters.",
                422,
            )
        model = request.model or self.settings.openrouter_model
        if model != self.settings.openrouter_model:
            raise GenerationError(
                "unsupported_model",
                "Only the configured text model is currently available.",
                422,
                {"available_models": [self.settings.openrouter_model]},
            )
        quota_backend = self.settings.quota_backend.lower()
        if quota_backend == "redis":
            await self.redis_state.reserve_daily_quota(request.account_id)
        elif quota_backend == "usage":
            await self.usage.check(
                request.account_id,
                request.user_id,
                model,
                self.settings.max_output_tokens,
                request.request_id,
            )
        else:
            raise GenerationError(
                "invalid_quota_backend",
                "AI generation quota backend must be 'redis' or 'usage'.",
                500,
            )
        channel = f"{self.settings.stream_channel_prefix}:{request.account_id}:{uuid.uuid4()}"
        async with self.database.acquire() as conn:
            job = await GenerationRepository(conn).create_job(
                request.account_id,
                request.user_id,
                request.request_id,
                channel,
                model,
                request.prompt,
            )
        task = asyncio.create_task(self._run(job), name=f"generation-{job['id']}")
        self._tasks[job["id"]] = task
        task.add_done_callback(lambda _: self._tasks.pop(job["id"], None))
        return job

    async def cancel(self, job_id: str, account_id: str | None = None) -> dict:
        async with self.database.acquire() as conn:
            job = await GenerationRepository(conn).request_cancellation(job_id, account_id)
        if job is None:
            raise GenerationError("job_not_found", "Generation job was not found.", 404)
        if job["status"] in {GenerationStatus.COMPLETED.value, GenerationStatus.FAILED.value, GenerationStatus.CANCELLED.value}:
            return job
        await self.redis_state.request_cancellation(job_id)
        task = self._tasks.get(job_id)
        if task is not None:
            task.cancel()
        return job

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, job: dict) -> None:
        job_id = job["id"]
        channel = job["channel"]
        response_parts: list[str] = []
        prompt_tokens = completion_tokens = total_tokens = None
        cost: Decimal | None = None
        try:
            async with self.database.acquire() as conn:
                await GenerationRepository(conn).mark_streaming(job_id)
            async for chunk in self.provider.stream(job["prompt"]):
                if await self.redis_state.cancellation_requested(job_id):
                    raise asyncio.CancelledError
                if chunk.text:
                    response_parts.append(chunk.text)
                    await self.redis_state.publish(channel, {"event": "token", "token": chunk.text, "job_id": job_id})
                prompt_tokens = chunk.prompt_tokens if chunk.prompt_tokens is not None else prompt_tokens
                completion_tokens = chunk.completion_tokens if chunk.completion_tokens is not None else completion_tokens
                total_tokens = chunk.total_tokens if chunk.total_tokens is not None else total_tokens
                cost = chunk.cost if chunk.cost is not None else cost

            response_text = "".join(response_parts)
            async with self.database.transaction() as conn:
                completed = await GenerationRepository(conn).complete_job(
                    job_id,
                    response_text,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cost,
                )
            await self.redis_state.publish(channel, "[DONE]")
            await self._publish_event(
                "ai.generation_completed",
                {
                    "job_id": job_id,
                    "account_id": job["account_id"],
                    "user_id": job["user_id"],
                    "request_id": job.get("request_id"),
                    "model": job["model"],
                    "prompt": job["prompt"],
                    "response_text": response_text,
                    "content_type": "post",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "cost": cost,
                    "completed_at": completed["completed_at"],
                },
            )
        except asyncio.CancelledError:
            await self._finish_cancelled(job)
        except Exception as exc:
            await self._finish_failed(job, exc)

    async def _finish_cancelled(self, job: dict) -> None:
        async with self.database.acquire() as conn:
            await GenerationRepository(conn).finish_with_status(job["id"], GenerationStatus.CANCELLED, "Generation cancelled.")
        try:
            await self.redis_state.publish(job["channel"], "[DONE]")
        except Exception:
            logging.exception("Unable to publish cancellation for generation %s", job["id"])

    async def _finish_failed(self, job: dict, exc: Exception) -> None:
        reason = exc.message if isinstance(exc, GenerationError) else "Generation failed unexpectedly."
        logging.exception("Generation %s failed", job["id"])
        try:
            async with self.database.acquire() as conn:
                await GenerationRepository(conn).finish_with_status(job["id"], GenerationStatus.FAILED, reason)
        except Exception:
            logging.exception("Unable to persist failure for generation %s", job["id"])
        try:
            await self.redis_state.publish(job["channel"], {"event": "error", "job_id": job["id"], "message": reason})
        except Exception:
            logging.exception("Unable to publish stream failure for generation %s", job["id"])
        await self._publish_event(
            "ai.generation_failed",
            {
                "job_id": job["id"],
                "account_id": job["account_id"],
                "user_id": job["user_id"],
                "model": job["model"],
                "error_reason": reason,
            },
        )

    async def _publish_event(self, routing_key: str, payload: dict) -> None:
        try:
            await self.events.publish(routing_key, payload)
        except Exception as exc:
            logging.warning("Skipped publishing %s: %s", routing_key, exc)
