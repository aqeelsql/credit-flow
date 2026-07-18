from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
import json
import logging

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from app.config import Settings

EventHandler = Callable[[str, dict[str, Any], aio_pika.IncomingMessage], Awaitable[None]]

EVENT_TOPICS = [
    "user.registered",
    "invoice.paid",
    "payment.failed",
    "member.joined",
    "team.invite.created",
    "post.published",
    "post.failed",
    "usage.threshold_reached",
]


class NotificationEventBus:
    def __init__(self, settings: Settings, handler: EventHandler | None = None):
        self.settings = settings
        self.handler = handler
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._publish_exchange: aio_pika.RobustExchange | None = None
        self._retry_exchange: aio_pika.RobustExchange | None = None
        self._queue: aio_pika.RobustQueue | None = None

    def set_handler(self, handler: EventHandler) -> None:
        self.handler = handler

    async def connect(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            return
        self._connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
        self._channel = await self._connection.channel(publisher_confirms=True)
        await self._channel.set_qos(prefetch_count=10)

        self._publish_exchange = await self._channel.declare_exchange(self.settings.publish_exchange, ExchangeType.TOPIC, durable=True)
        self._retry_exchange = await self._channel.declare_exchange(self.settings.retry_exchange, ExchangeType.TOPIC, durable=True)

        dlq = await self._channel.declare_queue(self.settings.dlq_queue, durable=True)
        await dlq.bind(self._publish_exchange, routing_key="notification.failed.dlq")

        await self._channel.declare_queue(
            self.settings.retry_queue,
            durable=True,
            arguments={
                "x-message-ttl": self.settings.retry_delay_ms,
                "x-dead-letter-exchange": self.settings.retry_exchange,
                "x-dead-letter-routing-key": "notification.retry",
            },
        )

        self._queue = await self._channel.declare_queue(
            self.settings.rabbitmq_queue,
            durable=True,
            arguments={"x-dead-letter-exchange": self.settings.publish_exchange, "x-dead-letter-routing-key": "notification.failed.dlq"},
        )

        for exchange_name in self.settings.exchanges:
            exchange = await self._channel.declare_exchange(exchange_name, ExchangeType.TOPIC, durable=True)
            for topic in EVENT_TOPICS:
                await self._queue.bind(exchange, routing_key=topic)
        await self._queue.bind(self._retry_exchange, routing_key="notification.retry")

    async def start_consuming(self) -> None:
        await self.connect()
        if self._queue is None:
            raise RuntimeError("RabbitMQ queue is not connected")
        await self._queue.consume(self._consume)

    async def publish(self, routing_key: str, payload: dict[str, Any], headers: dict | None = None) -> None:
        await self.connect()
        if self._publish_exchange is None:
            raise RuntimeError("RabbitMQ publish exchange is unavailable")
        message = Message(json.dumps(payload, default=str).encode("utf-8"), content_type="application/json", delivery_mode=DeliveryMode.PERSISTENT, headers=headers or {})
        await self._publish_exchange.publish(message, routing_key=routing_key)

    async def publish_retry(self, original_routing_key: str, payload: dict[str, Any], retry_count: int) -> None:
        await self.connect()
        if self._channel is None:
            raise RuntimeError("RabbitMQ channel is unavailable")
        message = Message(
            json.dumps(payload, default=str).encode("utf-8"),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            headers={"x-retry-count": retry_count, "x-original-routing-key": original_routing_key},
        )
        await self._channel.default_exchange.publish(message, routing_key=self.settings.retry_queue)

    async def publish_dlq(self, original_routing_key: str, payload: dict[str, Any], error: str, retry_count: int) -> None:
        await self.publish("notification.failed.dlq", {"original_routing_key": original_routing_key, "payload": payload, "error": error, "retry_count": retry_count}, headers={"x-original-routing-key": original_routing_key, "x-retry-count": retry_count})

    async def _consume(self, message: aio_pika.IncomingMessage) -> None:
        async with message.process(ignore_processed=True, requeue=False):
            try:
                payload = json.loads(message.body.decode("utf-8"))
            except json.JSONDecodeError:
                logging.warning("Dropped malformed notification message %s", message.routing_key)
                return
            if not isinstance(payload, dict) or self.handler is None:
                return
            routing_key = str(message.headers.get("x-original-routing-key") or message.routing_key)
            await self.handler(routing_key, payload, message)

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._queue = None
        self._retry_exchange = None
        self._publish_exchange = None
        self._channel = None
        self._connection = None
