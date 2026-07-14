from __future__ import annotations
from collections.abc import Awaitable, Callable
from typing import Any
import json
import logging

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from app.config import Settings
from app.errors import CreditsError

EventHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self, settings: Settings, handler: EventHandler | None = None):
        self.settings = settings
        self.handler = handler
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.RobustExchange | None = None
        self._queue: aio_pika.RobustQueue | None = None

    @property
    def connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed and self._exchange is not None

    def set_handler(self, handler: EventHandler) -> None:
        self.handler = handler

    async def connect(self) -> None:
        if self.connected:
            return
        self._connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)
        self._exchange = await self._channel.declare_exchange(
            self.settings.rabbitmq_exchange,
            ExchangeType.TOPIC,
            durable=True,
        )

    async def start_consuming(self) -> None:
        if self._channel is None or self._exchange is None:
            raise CreditsError("events_unavailable", "RabbitMQ is unavailable.", 503)
        self._queue = await self._channel.declare_queue(self.settings.rabbitmq_queue, durable=True)
        await self._queue.bind(self._exchange, routing_key="invoice.paid")
        await self._queue.bind(self._exchange, routing_key="refund.issued")
        await self._queue.consume(self._consume)

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._queue = None
        self._exchange = None
        self._channel = None
        self._connection = None

    async def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        if self._exchange is None:
            raise CreditsError("events_unavailable", "RabbitMQ is unavailable.", 503)
        message = Message(
            json.dumps(payload, default=str).encode("utf-8"),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=routing_key)

    async def _consume(self, message: aio_pika.IncomingMessage) -> None:
        async with message.process(ignore_processed=True):
            if self.handler is None:
                return
            try:
                payload = json.loads(message.body.decode("utf-8"))
            except json.JSONDecodeError:
                logging.warning("Dropped malformed event payload from %s", message.routing_key)
                return
            if not isinstance(payload, dict):
                logging.warning("Dropped non-object event payload from %s", message.routing_key)
                return
            await self.handler(message.routing_key, payload)
