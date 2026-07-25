# CreditFlow Scheduler Service

Service 9 owns account calendars and scheduled publishing handoff.

## Responsibilities

- Stores scheduled publish times in UTC in `scheduler.scheduled_posts`.
- Returns scheduled posts for an account within a requested date range.
- Converts UTC times to the requested display timezone in `publish_at_local`.
- Schedules existing content by `content_id`; it does not duplicate post bodies.
- Supports reschedule, cancel, and optional weekly recurrence.
- Runs an embedded due-post scanner while the Scheduler API is running, with Redis locks for idempotency.
- Celery/Beat can still be used as an optional production scanner by setting `SCHEDULER_EMBEDDED_SCANNER_ENABLED=false`.
- Emits `content.scheduled` to RabbitMQ when a post is due.
- Does not call LinkedIn directly.

## Run REST API locally

```powershell
cd scheduler_service
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --port 8004
```

## Due scanner

The API now starts the due-post scanner automatically. Keep RabbitMQ, Redis, Scheduler Service, and Social Publishing Service running. If you disable the embedded scanner with `SCHEDULER_EMBEDDED_SCANNER_ENABLED=false`, run Celery worker and beat separately.

Manual one-shot scan:

```powershell
cd scheduler_service
py -c "from app.due_scanner import scan_due_posts; print(scan_due_posts())"
```
