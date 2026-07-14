import json
import logging
from typing import Awaitable, Callable

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from app.config import Settings

EventHandler = Callable[[dict, aio_pika.IncomingMessage], Awaitable[None]]


class ScraperEventBus:
    def __init__(self, settings: Settings, handler: EventHandler | None = None):
        self.settings = settings
        self.handler = handler
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.RobustExchange | None = None
        self._queue: aio_pika.RobustQueue | None = None

    async def connect(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            return
        self._connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=2)
        self._exchange = await self._channel.declare_exchange(self.settings.rabbitmq_exchange, ExchangeType.TOPIC, durable=True)
        dlq = await self._channel.declare_queue(self.settings.dlq_queue, durable=True)
        await dlq.bind(self._exchange, routing_key="scrape.failed.dlq")
        await self._channel.declare_queue(
            self.settings.retry_queue,
            durable=True,
            arguments={
                "x-message-ttl": self.settings.retry_delay_ms,
                "x-dead-letter-exchange": self.settings.rabbitmq_exchange,
                "x-dead-letter-routing-key": "scrape.requested",
            },
        )
        self._queue = await self._channel.declare_queue(
            self.settings.rabbitmq_queue,
            durable=True,
            arguments={"x-dead-letter-exchange": self.settings.rabbitmq_exchange, "x-dead-letter-routing-key": "scrape.failed.dlq"},
        )
        await self._queue.bind(self._exchange, routing_key="scrape.requested")

    async def publish(self, routing_key: str, payload: dict, headers: dict | None = None) -> None:
        await self.connect()
        if self._exchange is None:
            raise RuntimeError("RabbitMQ exchange is not connected")
        await self._exchange.publish(
            Message(json.dumps(payload, default=str).encode("utf-8"), content_type="application/json", delivery_mode=DeliveryMode.PERSISTENT, headers=headers or {}),
            routing_key=routing_key,
        )

    async def publish_retry(self, payload: dict, retry_count: int) -> None:
        await self.connect()
        if self._channel is None:
            raise RuntimeError("RabbitMQ channel is not connected")
        await self._channel.default_exchange.publish(
            Message(json.dumps(payload, default=str).encode("utf-8"), content_type="application/json", delivery_mode=DeliveryMode.PERSISTENT, headers={"x-retry-count": retry_count}),
            routing_key=self.settings.retry_queue,
        )

    async def start_consuming(self) -> None:
        await self.connect()
        if self._queue is None:
            raise RuntimeError("RabbitMQ queue is not connected")
        await self._queue.consume(self._consume)

    async def _consume(self, message: aio_pika.IncomingMessage) -> None:
        async with message.process(ignore_processed=True, requeue=False):
            try:
                payload = json.loads(message.body.decode("utf-8"))
            except json.JSONDecodeError:
                logging.warning("Dropped malformed scrape.requested message")
                return
            if self.handler is not None:
                await self.handler(payload, message)

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._queue = None
        self._exchange = None
        self._channel = None
        self._connection = None
