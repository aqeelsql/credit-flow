import json

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from app.config import Settings


class BillingEventPublisher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.RobustExchange | None = None

    async def connect(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            return
        self._connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
        self._channel = await self._connection.channel(publisher_confirms=True)
        self._exchange = await self._channel.declare_exchange(self.settings.rabbitmq_exchange, ExchangeType.TOPIC, durable=True)

    async def publish(self, routing_key: str, payload: dict) -> None:
        await self.connect()
        if self._exchange is None:
            raise RuntimeError("RabbitMQ exchange is unavailable")
        await self._exchange.publish(Message(json.dumps(payload, default=str).encode("utf-8"), content_type="application/json", delivery_mode=DeliveryMode.PERSISTENT), routing_key=routing_key)

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._exchange = None; self._channel = None; self._connection = None

