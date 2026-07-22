from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
import json
import logging

import aio_pika
from aio_pika import ExchangeType

from app.config import Settings

EventHandler = Callable[[str, dict[str, Any], aio_pika.IncomingMessage], Awaitable[None]]


class AuditEventBus:
    def __init__(self, settings: Settings, handler: EventHandler | None = None):
        self.settings = settings
        self.handler = handler
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._queue: aio_pika.RobustQueue | None = None

    def set_handler(self, handler: EventHandler) -> None:
        self.handler = handler

    async def connect(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            return
        self._connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
        self._channel = await self._connection.channel(publisher_confirms=True)
        await self._channel.set_qos(prefetch_count=100)
        self._queue = await self._channel.declare_queue(self.settings.rabbitmq_queue, durable=True)
        for exchange_name in self.settings.exchanges:
            exchange = await self._channel.declare_exchange(exchange_name, ExchangeType.TOPIC, durable=True)
            await self._queue.bind(exchange, routing_key="#")

    async def start_consuming(self) -> None:
        await self.connect()
        if self._queue is None:
            raise RuntimeError("Audit queue is unavailable")
        await self._queue.consume(self._consume)

    async def _consume(self, message: aio_pika.IncomingMessage) -> None:
        async with message.process(ignore_processed=True, requeue=False):
            try:
                payload = json.loads(message.body.decode("utf-8"))
            except json.JSONDecodeError:
                logging.warning("Dropped malformed audit message %s", message.routing_key)
                return
            if isinstance(payload, dict) and self.handler is not None:
                await self.handler(message.routing_key, payload, message)

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._queue = None
        self._channel = None
        self._connection = None
