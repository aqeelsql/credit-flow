import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.errors import GenerationError


class GenerationRedis:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Redis | None = None

    async def connect(self) -> None:
        if self._client is None:
            self._client = Redis.from_url(self.settings.redis_url, decode_responses=True)
            await self._client.ping()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def client(self) -> Redis:
        try:
            await self.connect()
        except RedisError as exc:
            raise GenerationError("redis_unavailable", "Redis streaming state is unavailable.", 503) from exc
        if self._client is None:
            raise GenerationError("redis_unavailable", "Redis streaming state is unavailable.", 503)
        return self._client

    async def ping(self) -> bool:
        try:
            return bool(await (await self.client()).ping())
        except GenerationError:
            return False

    async def publish(self, channel: str, payload: dict[str, Any] | str) -> None:
        message = payload if isinstance(payload, str) else json.dumps(payload, default=str)
        client = await self.client()
        await client.publish(channel, message)
        await client.set(f"{channel}:last", message, ex=self.settings.stream_event_ttl_seconds)

    async def request_cancellation(self, job_id: str) -> None:
        client = await self.client()
        await client.set(f"ai-generation:cancel:{job_id}", "1", ex=self.settings.stream_event_ttl_seconds)

    async def cancellation_requested(self, job_id: str) -> bool:
        return bool(await (await self.client()).exists(f"ai-generation:cancel:{job_id}"))

    async def reserve_daily_quota(self, account_id: str) -> int:
        client = await self.client()
        key = f"ai-generation:quota:{account_id}"
        script = """
        local current = redis.call('INCR', KEYS[1])
        if current == 1 then
            redis.call('EXPIRE', KEYS[1], ARGV[2])
        end
        if current > tonumber(ARGV[1]) then
            redis.call('DECR', KEYS[1])
            return -1
        end
        return tonumber(ARGV[1]) - current
        """
        remaining = int(
            await client.eval(
                script,
                1,
                key,
                self.settings.daily_request_limit,
                24 * 60 * 60,
            )
        )
        if remaining < 0:
            raise GenerationError(
                "quota_exceeded",
                "The account has reached its daily text generation limit.",
                429,
                {"daily_request_limit": self.settings.daily_request_limit},
            )
        return remaining
