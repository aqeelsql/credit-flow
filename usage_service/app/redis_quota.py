from __future__ import annotations

from datetime import UTC, datetime

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.errors import UsageError


class RedisQuota:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Redis | None = None

    async def connect(self) -> None:
        if self._client is None:
            self._client = Redis.from_url(self.settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose(); self._client = None

    async def client(self) -> Redis:
        await self.connect()
        if self._client is None:
            raise UsageError("redis_unavailable", "Redis quota state is unavailable.", 503)
        return self._client

    async def ping(self) -> bool:
        try:
            return bool(await (await self.client()).ping())
        except Exception:
            return False

    def period(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m")

    def counter_key(self, account_id: str, period: str | None = None) -> str:
        return f"{self.settings.redis_key_prefix}:quota:{account_id}:{period or self.period()}:tokens"

    def reservation_key(self, account_id: str, request_id: str) -> str:
        return f"{self.settings.redis_key_prefix}:reservation:{account_id}:{request_id}"

    async def reserve(self, account_id: str, request_id: str, requested_tokens: int, quota_tokens: int, used_tokens: int | None = None) -> dict:
        client = await self.client(); period = self.period(); key = self.counter_key(account_id, period)
        script = """
        local current = tonumber(redis.call('GET', KEYS[1]) or ARGV[4] or '0')
        local quota = tonumber(ARGV[1]); local amount = tonumber(ARGV[2])
        if current + amount > quota then return {0, current, quota - current} end
        local next_value = redis.call('INCRBY', KEYS[1], amount)
        redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
        redis.call('SET', KEYS[2], amount, 'EX', tonumber(ARGV[5]))
        return {1, next_value, quota - next_value}
        """
        try:
            allowed, used_after, remaining = await client.eval(script, 2, key, self.reservation_key(account_id, request_id), quota_tokens, requested_tokens, self.settings.redis_counter_ttl_seconds, used_tokens if used_tokens is not None else 0, self.settings.reservation_ttl_seconds)
        except RedisError as exc:
            raise UsageError("redis_unavailable", "Redis quota state is unavailable.", 503) from exc
        return {"allowed": bool(int(allowed)), "used_tokens": int(used_after), "remaining_tokens": max(int(remaining), 0), "period": period}

    async def reconcile(self, account_id: str, actual_used_tokens: int, period: str | None = None) -> None:
        await (await self.client()).set(self.counter_key(account_id, period), int(actual_used_tokens), ex=self.settings.redis_counter_ttl_seconds)

    async def adjust_after_completion(self, account_id: str, request_id: str | None, actual_tokens: int, ledger_used_tokens: int, period: str | None = None) -> None:
        client = await self.client()
        if not request_id:
            await self.reconcile(account_id, ledger_used_tokens, period); return
        reserved = await client.get(self.reservation_key(account_id, request_id))
        if reserved is None:
            await self.reconcile(account_id, ledger_used_tokens, period); return
        delta = int(actual_tokens) - int(reserved)
        if delta:
            await client.incrby(self.counter_key(account_id, period), delta)
        await client.delete(self.reservation_key(account_id, request_id))

