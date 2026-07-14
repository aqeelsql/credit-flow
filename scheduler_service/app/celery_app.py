from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery("creditflow_scheduler", broker=settings.celery_broker_url, backend=settings.celery_result_backend)
celery_app.conf.timezone = "UTC"
celery_app.conf.beat_schedule = {
    "scan-due-scheduled-posts": {"task": "scheduler.scan_due_posts", "schedule": settings.scan_interval_seconds}
}

import app.tasks  # noqa: E402,F401
