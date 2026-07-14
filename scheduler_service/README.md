# CreditFlow Scheduler Service

Service 9 owns account calendars and scheduled publishing handoff.

## Responsibilities

- Stores scheduled publish times in UTC in `scheduler.scheduled_posts`.
- Returns scheduled posts for an account within a requested date range.
- Converts UTC times to the requested display timezone in `publish_at_local`.
- Schedules existing content by `content_id`; it does not duplicate post bodies.
- Supports reschedule, cancel, and optional weekly recurrence.
- Uses Celery + Redis for the due-post scanner and Redis locks for idempotency.
- Emits `content.scheduled` to RabbitMQ when a post is due.
- Does not call LinkedIn directly.

## Run REST API locally

```powershell
cd scheduler_service
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --port 8004
```

## Run due scanner locally

Worker:

```powershell
cd scheduler_service
py -m celery -A app.celery_app.celery_app worker --loglevel=info --pool=solo
```

Beat:

```powershell
cd scheduler_service
py -m celery -A app.celery_app.celery_app beat --loglevel=info
```

Manual one-shot scan:

```powershell
cd scheduler_service
py -c "from app.tasks import scan_due_posts; print(scan_due_posts())"
```
