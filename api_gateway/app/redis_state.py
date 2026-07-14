import time
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.errors import GatewayError


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


class RedisState:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Redis | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
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
            raise GatewayError("redis_unavailable", "Redis state is unavailable.", 503) from exc
        if self._client is None:
            raise GatewayError("redis_unavailable", "Redis state is unavailable.", 503)
        return self._client

    async def ping(self) -> bool:
        try:
            client = await self.client()
            return bool(await client.ping())
        except GatewayError:
            return False

    async def is_session_active(self, jti: str) -> bool:
        client = await self.client()
        return bool(await client.exists(f"jwt:active:{jti}"))

    async def is_session_revoked(self, jti: str) -> bool:
        client = await self.client()
        return bool(await client.exists(f"jwt:revoked:{jti}"))

    async def mark_webhook_seen(self, provider: str, event_id: str, ttl_seconds: int) -> bool:
        client = await self.client()
        key = f"webhook:seen:{provider}:{event_id}"
        return bool(await client.set(key, "1", ex=ttl_seconds, nx=True))

    async def sliding_window_allow(self, scope: str, limit: int, window_seconds: int) -> RateLimitDecision:
        client = await self.client()
        now = time.time()
        bucket = int(now // window_seconds)
        elapsed = now % window_seconds
        current_key = f"rl:{scope}:{bucket}"
        previous_key = f"rl:{scope}:{bucket - 1}"

        pipe = client.pipeline()
        pipe.incr(current_key)
        pipe.expire(current_key, window_seconds * 2)
        pipe.get(previous_key)
        current_count, _, previous_raw = await pipe.execute()

        previous_count = int(previous_raw or 0)
        previous_weight = (window_seconds - elapsed) / window_seconds
        estimated_count = int(current_count) + int(previous_count * previous_weight)
        remaining = max(limit - estimated_count, 0)
        reset_seconds = max(int(window_seconds - elapsed), 1)
        return RateLimitDecision(estimated_count <= limit, limit, remaining, reset_seconds)

    async def subscribe(self, channel: str):
        client = await self.client()
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        return pubsub
