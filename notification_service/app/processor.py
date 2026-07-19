from __future__ import annotations

from typing import Any
import logging
import uuid

import aio_pika

from app.alerts import AlertClient
from app.config import Settings
from app.database import Database
from app.email_client import EmailClient
from app.events import NotificationEventBus
from app.repository import NotificationRepository
from app.templates import build_email, recipient_for_event
from app.errors import NotificationError


class NotificationProcessor:
    def __init__(self, settings: Settings, database: Database, event_bus: NotificationEventBus, email_client: EmailClient, alert_client: AlertClient):
        self.settings = settings
        self.database = database
        self.event_bus = event_bus
        self.email_client = email_client
        self.alert_client = alert_client

    async def handle_event(self, routing_key: str, payload: dict[str, Any], message: aio_pika.IncomingMessage) -> None:
        event_id = str(payload.get("event_id") or payload.get("id") or message.message_id or f"{routing_key}:{uuid.uuid5(uuid.NAMESPACE_URL, str(payload))}")
        retry_count = int((message.headers or {}).get("x-retry-count") or 0)
        try:
            await self._process_once(routing_key, event_id, payload, retry_count + 1)
        except Exception as exc:
            await self._handle_failure(routing_key, event_id, payload, retry_count, exc)

    async def _process_once(self, event_type: str, event_id: str, payload: dict[str, Any], attempt: int) -> None:
        async with self.database.transaction() as conn:
            repo = NotificationRepository(conn)
            claimed = await repo.claim_event(event_id, event_type)
            if not claimed:
                logging.info("Skipping duplicate notification event %s", event_id)
                return

        recipient = recipient_for_event(event_type, payload, self.settings)
        email = build_email(event_type, payload, self.settings)
        if not recipient:
            async with self.database.transaction() as conn:
                repo = NotificationRepository(conn)
                await repo.log_attempt(event_id=event_id, event_type=event_type, notification_type=email["notification_type"], channel="email", recipient="unknown", subject=email["subject"], status="skipped", attempt=attempt, error="No recipient email found.", metadata=payload)
                await repo.mark_event_processed(event_id)
            return

        provider_message_id: str | None = None
        try:
            provider_message_id = await self.email_client.send_email(to=recipient, subject=email["subject"], html=email["html"], text=email["text"])
        except Exception:
            async with self.database.transaction() as conn:
                await NotificationRepository(conn).mark_event_unprocessed(event_id)
            raise

        async with self.database.transaction() as conn:
            repo = NotificationRepository(conn)
            log = await repo.log_attempt(event_id=event_id, event_type=event_type, notification_type=email["notification_type"], channel="email", recipient=recipient, subject=email["subject"], status="sent", provider_message_id=provider_message_id, attempt=attempt, metadata=payload)
            await repo.mark_event_processed(event_id)
        await self.event_bus.publish("notification.sent", {"event_id": event_id, "source_event_type": event_type, "notification_log_id": log["id"], "notification_type": email["notification_type"], "recipient": recipient, "provider_message_id": provider_message_id})

    async def _handle_failure(self, routing_key: str, event_id: str, payload: dict[str, Any], retry_count: int, exc: Exception) -> None:
        next_retry = retry_count + 1
        error = str(exc)
        email = build_email(routing_key, payload, self.settings)
        recipient = recipient_for_event(routing_key, payload, self.settings) or "unknown"
        async with self.database.transaction() as conn:
            repo = NotificationRepository(conn)
            await repo.log_attempt(event_id=event_id, event_type=routing_key, notification_type=email["notification_type"], channel="email", recipient=recipient, subject=email["subject"], status="failed", attempt=next_retry, error=error, metadata=payload)

        is_permanent = isinstance(exc, NotificationError) and exc.status_code < 500
        if not is_permanent and retry_count < self.settings.max_retries:
            logging.warning("Notification event %s failed; retry %s/%s", event_id, next_retry, self.settings.max_retries)
            await self.event_bus.publish_retry(routing_key, payload, next_retry)
            return

        if is_permanent:
            logging.error("Notification event %s failed permanently: %s", event_id, error)
        else:
            logging.error("Notification event %s exhausted retries", event_id)
        await self.event_bus.publish_dlq(routing_key, payload, error, retry_count)
        async with self.database.transaction() as conn:
            repo = NotificationRepository(conn)
            await repo.claim_event(event_id, routing_key)
            await repo.mark_event_processed(event_id)
        await self.alert_client.send_slack_alert(f"CreditFlow notification failed after retries: {routing_key} event_id={event_id} error={error}")
