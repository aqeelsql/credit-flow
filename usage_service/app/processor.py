from __future__ import annotations

import logging
from typing import Any

import aio_pika

from app.config import Settings
from app.database import Database
from app.events import UsageEventBus
from app.redis_quota import RedisQuota
from app.repository import UsageRepository, current_period, event_id_from_generation


class UsageProcessor:
    def __init__(self, settings: Settings, database: Database, redis_quota: RedisQuota, events: UsageEventBus):
        self.settings = settings
        self.database = database
        self.redis_quota = redis_quota
        self.events = events

    async def handle(self, routing_key: str, payload: dict[str, Any], message: aio_pika.IncomingMessage | None = None) -> None:
        retry_count = int((message.headers or {}).get("x-retry-count") or 0) if message is not None else 0
        try:
            await self._process_generation_completed(routing_key, payload)
        except Exception as exc:
            logging.exception("Usage event processing failed")
            if retry_count < self.settings.max_retries:
                await self.events.publish_retry(routing_key, payload, retry_count + 1)
                return
            await self.events.publish("usage.failed.dlq", {**payload, "reason": str(exc), "attempts": retry_count + 1})

    async def _process_generation_completed(self, routing_key: str, payload: dict[str, Any]) -> None:
        account_id = payload.get("account_id")
        if not account_id:
            logging.warning("Skipped %s without account_id", routing_key)
            return
        event_id = event_id_from_generation(payload)
        period = current_period()
        async with self.database.transaction() as conn:
            repo = UsageRepository(conn)
            if not await repo.record_processed_event(event_id, routing_key, payload):
                return
            row = await repo.append_usage_from_generation(event_id, payload, self.settings.default_currency)
            quota = await repo.quota_for_account(str(account_id), self.settings.default_monthly_token_quota)
            used_tokens = await repo.used_tokens(str(account_id), period)
            quota_tokens = int(quota["monthly_token_quota"])
            alerts: list[dict[str, Any]] = []
            if quota_tokens > 0:
                percent = used_tokens / quota_tokens * 100
                for threshold in self.settings.thresholds:
                    if percent >= threshold and await repo.record_threshold_alert(str(account_id), period, threshold, used_tokens, quota_tokens, event_id):
                        alerts.append({"threshold": threshold, "usage_percent": round(percent, 2)})
        await self.redis_quota.adjust_after_completion(str(account_id), payload.get("request_id"), int(row.get("total_tokens") or payload.get("total_tokens") or 0), used_tokens, period)
        for alert in alerts:
            await self.events.publish("usage.threshold_reached", {"event_id": f"usage.threshold_reached:{account_id}:{period}:{alert['threshold']}", "account_id": str(account_id), "period": period, "threshold": alert["threshold"], "usage_percent": alert["usage_percent"], "used_tokens": used_tokens, "quota_tokens": quota_tokens, "source_event_id": event_id})

