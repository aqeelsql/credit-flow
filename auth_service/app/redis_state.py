from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.errors import AuthError


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
            raise AuthError("redis_unavailable", "Redis is unavailable.", 503) from exc
        if self._client is None:
            raise AuthError("redis_unavailable", "Redis is unavailable.", 503)
        return self._client

    async def ping(self) -> bool:
        try:
            client = await self.client()
            return bool(await client.ping())
        except AuthError:
            return False

    async def mark_jti_active(self, jti: str, user_id: str, account_id: str, role: str, ttl_seconds: int) -> None:
        client = await self.client()
        await client.hset(
            f"jwt:active:{jti}",
            mapping={"user_id": user_id, "account_id": account_id, "role": role},
        )
        await client.expire(f"jwt:active:{jti}", ttl_seconds)

    async def revoke_jti(self, jti: str, ttl_seconds: int) -> None:
        client = await self.client()
        await client.set(f"jwt:revoked:{jti}", "1", ex=max(ttl_seconds, 60))
        await client.delete(f"jwt:active:{jti}")

    async def is_jti_active(self, jti: str) -> bool:
        client = await self.client()
        return bool(await client.exists(f"jwt:active:{jti}"))

    async def is_jti_revoked(self, jti: str) -> bool:
        client = await self.client()
        return bool(await client.exists(f"jwt:revoked:{jti}"))

    async def increment_login_attempts(self, email: str, ip: str) -> int:
        client = await self.client()
        key = f"login:attempts:{email.lower()}:{ip}"
        value = await client.incr(key)
        if value == 1:
            await client.expire(key, self.settings.login_rate_limit_window_seconds)
        return int(value)

    async def clear_login_attempts(self, email: str, ip: str) -> None:
        client = await self.client()
        await client.delete(f"login:attempts:{email.lower()}:{ip}")
