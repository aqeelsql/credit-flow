import json

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from app.config import Settings
from app.errors import GenerationError


class EventPublisher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.RobustExchange | None = None

    @property
    def connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed and self._exchange is not None

    async def connect(self) -> None:
        if self.connected:
            return
        self._connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            self.settings.rabbitmq_exchange,
            ExchangeType.TOPIC,
            durable=True,
        )

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._exchange = None
        self._channel = None
        self._connection = None

    async def publish(self, routing_key: str, payload: dict) -> None:
        try:
            await self.connect()
        except Exception as exc:
            raise GenerationError("events_unavailable", "RabbitMQ is unavailable.", 503) from exc
        if self._exchange is None:
            raise GenerationError("events_unavailable", "RabbitMQ is unavailable.", 503)
        message = Message(
            json.dumps(payload, default=str).encode("utf-8"),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=routing_key)
