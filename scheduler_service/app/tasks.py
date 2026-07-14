from datetime import timedelta
import json
import logging

import pika
import psycopg
from psycopg.rows import dict_row
import redis

from app.celery_app import celery_app
from app.config import get_settings


def _publish(routing_key: str, payload: dict) -> None:
    settings = get_settings()
    connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    try:
        channel = connection.channel()
        channel.exchange_declare(exchange=settings.rabbitmq_exchange, exchange_type="topic", durable=True)
        channel.basic_publish(exchange=settings.rabbitmq_exchange, routing_key=routing_key, body=json.dumps(payload, default=str).encode("utf-8"), properties=pika.BasicProperties(content_type="application/json", delivery_mode=2))
    finally:
        connection.close()


@celery_app.task(name="scheduler.scan_due_posts")
def scan_due_posts() -> dict:
    settings = get_settings()
    lock_client = redis.Redis.from_url(settings.lock_redis_url, decode_responses=True)
    dispatched = 0
    skipped_locked = 0
    with psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=False, options=f"-c search_path={settings.database_schema},public") as conn:
        rows = conn.execute(
            """
            SELECT id::text AS id, account_id, created_by_user_id, content_id::text AS content_id,
                   content_title, publish_at, timezone, recurrence
            FROM scheduled_posts
            WHERE status = 'scheduled' AND publish_at <= now()
            ORDER BY publish_at ASC LIMIT %s
            """,
            (settings.due_batch_size,),
        ).fetchall()
        for row in rows:
            lock_key = f"scheduler:scheduled_post:{row['id']}"
            if not lock_client.set(lock_key, "1", nx=True, ex=300):
                skipped_locked += 1
                continue
            try:
                claimed = conn.execute(
                    """
                    UPDATE scheduled_posts
                    SET status = 'dispatching', locked_at = now(), dispatch_attempts = dispatch_attempts + 1, updated_at = now()
                    WHERE id = %s AND status = 'scheduled'
                    RETURNING id::text AS id
                    """,
                    (row["id"],),
                ).fetchone()
                if not claimed:
                    conn.rollback()
                    continue
                _publish("content.scheduled", {"scheduled_post_id": row["id"], "account_id": row["account_id"], "content_id": row["content_id"], "content_title": row["content_title"], "publish_at": row["publish_at"], "timezone": row["timezone"], "recurrence": row["recurrence"]})
                if row["recurrence"] in {"daily", "weekly", "monthly"}:
                    if row["recurrence"] == "daily":
                        next_publish_at = row["publish_at"] + timedelta(days=1)
                    elif row["recurrence"] == "weekly":
                        next_publish_at = row["publish_at"] + timedelta(days=7)
                    else:
                        next_publish_at = row["publish_at"] + timedelta(days=30)
                    conn.execute("UPDATE scheduled_posts SET status = 'scheduled', publish_at = %s, dispatched_at = now(), locked_at = NULL, updated_at = now() WHERE id = %s", (next_publish_at, row["id"]))
                else:
                    conn.execute("UPDATE scheduled_posts SET status = 'dispatched', dispatched_at = now(), locked_at = NULL, updated_at = now() WHERE id = %s", (row["id"],))
                conn.commit()
                dispatched += 1
            except Exception as exc:
                logging.exception("Failed to dispatch scheduled post %s", row["id"])
                conn.rollback()
                with conn.transaction():
                    conn.execute("UPDATE scheduled_posts SET status = 'scheduled', locked_at = NULL, last_error = %s, updated_at = now() WHERE id = %s AND status = 'dispatching'", (str(exc), row["id"]))
            finally:
                lock_client.delete(lock_key)
    return {"dispatched": dispatched, "skipped_locked": skipped_locked}
