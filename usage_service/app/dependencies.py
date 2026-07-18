from fastapi import Request

from app.database import Database
from app.events import UsageEventBus
from app.redis_quota import RedisQuota


def database_dep(request: Request) -> Database:
    return request.app.state.database


def redis_quota_dep(request: Request) -> RedisQuota:
    return request.app.state.redis_quota


def event_bus_dep(request: Request) -> UsageEventBus:
    return request.app.state.event_bus

