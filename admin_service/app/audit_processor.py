from __future__ import annotations

from typing import Any
import uuid

import aio_pika

from app.database import Database
from app.repository import AuditRepository


def _first(payload: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    return None


class AuditProcessor:
    def __init__(self, database: Database):
        self.database = database

    async def handle_event(self, routing_key: str, payload: dict[str, Any], message: aio_pika.IncomingMessage) -> None:
        event_id = str(payload.get("event_id") or payload.get("id") or message.message_id or f"audit:{routing_key}:{uuid.uuid5(uuid.NAMESPACE_URL, str(payload))}")
        account_id = _first(payload, ["account_id", "seller_account_id", "buyer_account_id", "related_account_id"])
        actor_user_id = _first(payload, ["user_id", "actor_user_id", "created_by_user_id", "updated_by_user_id"])
        summary = str(payload.get("summary") or payload.get("message") or payload.get("reason") or "")[:1000] or None
        exchange = getattr(message, "exchange", None)
        async with self.database.transaction() as conn:
            await AuditRepository(conn).insert_event(event_id=event_id, routing_key=routing_key, exchange=str(exchange) if exchange else None, account_id=account_id, actor_user_id=actor_user_id, action=routing_key, summary=summary, payload=payload)
