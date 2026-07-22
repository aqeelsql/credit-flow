from __future__ import annotations

from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.errors import AdminError


class RedisSessions:
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
            raise AdminError("redis_unavailable", "Redis is unavailable.", 503) from exc
        if self._client is None:
            raise AdminError("redis_unavailable", "Redis is unavailable.", 503)
        return self._client

    async def ping(self) -> bool:
        try:
            return bool(await (await self.client()).ping())
        except AdminError:
            return False

    async def list_sessions(self, account_id: str | None = None) -> list[dict[str, Any]]:
        client = await self.client()
        rows: list[dict[str, Any]] = []
        async for key in client.scan_iter("jwt:active:*"):
            jti = str(key).replace("jwt:active:", "", 1)
            data = await client.hgetall(key)
            if account_id and data.get("account_id") != account_id:
                continue
            ttl = await client.ttl(key)
            rows.append({"jti": jti, "user_id": data.get("user_id"), "account_id": data.get("account_id"), "role": data.get("role"), "ttl_seconds": ttl})
        return sorted(rows, key=lambda item: (item.get("account_id") or "", item.get("user_id") or ""))

    async def revoke_session(self, jti: str) -> dict[str, Any]:
        client = await self.client()
        key = f"jwt:active:{jti}"
        data = await client.hgetall(key)
        deleted = await client.delete(key)
        await client.set(f"jwt:revoked:{jti}", "1", ex=max(self.settings.revoked_session_ttl_seconds, 60))
        return {"jti": jti, "revoked": bool(deleted), "session": data or None}
