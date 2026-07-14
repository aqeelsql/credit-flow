import json
import logging
import threading
from typing import Callable

import pika

from app.config import Settings

EventHandler = Callable[[str, dict], None]


class EventBus:
    def __init__(self, settings: Settings, handler: EventHandler | None = None):
        self.settings = settings
        self.handler = handler
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def publish(self, routing_key: str, payload: dict) -> None:
        params = pika.URLParameters(self.settings.rabbitmq_url)
        connection = pika.BlockingConnection(params)
        try:
            channel = connection.channel()
            channel.exchange_declare(exchange=self.settings.rabbitmq_exchange, exchange_type="topic", durable=True)
            channel.basic_publish(exchange=self.settings.rabbitmq_exchange, routing_key=routing_key, body=json.dumps(payload, default=str).encode("utf-8"), properties=pika.BasicProperties(content_type="application/json", delivery_mode=2))
        finally:
            connection.close()

    def start_consuming_background(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._consume_forever, name="content-events", daemon=True)
        self._thread.start()

    def _consume_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self._consume_once()
            except Exception as exc:
                logging.warning("Content event consumer disconnected: %s", exc)
                self._stop.wait(5)

    def _consume_once(self) -> None:
        params = pika.URLParameters(self.settings.rabbitmq_url)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.exchange_declare(exchange=self.settings.rabbitmq_exchange, exchange_type="topic", durable=True)
        channel.queue_declare(queue=self.settings.rabbitmq_queue, durable=True)
        channel.queue_bind(exchange=self.settings.rabbitmq_exchange, queue=self.settings.rabbitmq_queue, routing_key="ai.generation_completed")
        channel.basic_qos(prefetch_count=5)

        def callback(ch, method, properties, body):
            try:
                payload = json.loads(body.decode("utf-8"))
                if isinstance(payload, dict) and self.handler:
                    self.handler(method.routing_key, payload)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception:
                logging.exception("Failed to process content event %s", method.routing_key)
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        channel.basic_consume(queue=self.settings.rabbitmq_queue, on_message_callback=callback)
        channel.start_consuming()

    def close(self) -> None:
        self._stop.set()
