import json

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractRobustConnection

from app.config import Settings
from app.errors import AuthError


class EventPublisher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None

    async def connect(self) -> None:
        if self._exchange is not None:
            return
        self._connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(self.settings.rabbitmq_exchange, ExchangeType.TOPIC, durable=True)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
        self._connection = None
        self._channel = None
        self._exchange = None

    async def ready(self) -> bool:
        try:
            await self.connect()
            return True
        except Exception:
            return False

    async def publish(self, routing_key: str, payload: dict) -> None:
        try:
            await self.connect()
        except Exception as exc:
            raise AuthError("event_bus_unavailable", "RabbitMQ event bus is unavailable.", 503) from exc
        if self._exchange is None:
            raise AuthError("event_bus_unavailable", "RabbitMQ event bus is unavailable.", 503)
        await self._exchange.publish(
            Message(
                body=json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"),
                content_type="application/json",
                delivery_mode=DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )