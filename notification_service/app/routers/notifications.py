import uuid

from fastapi import APIRouter, Depends, Query

from app.database import Database
from app.dependencies import database_dep, email_client_dep, event_bus_dep
from app.email_client import EmailClient
from app.events import NotificationEventBus
from app.repository import NotificationRepository
from app.schemas import NotificationLogResponse, TestEmailRequest, TestEmailResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/logs", response_model=NotificationLogResponse)
async def list_notification_logs(limit: int = Query(default=50, ge=1, le=200), db: Database = Depends(database_dep)):
    async with db.acquire() as conn:
        rows = await NotificationRepository(conn).list_logs(limit)
    return NotificationLogResponse(items=rows)


@router.post("/test-email", response_model=TestEmailResponse)
async def send_test_email(
    payload: TestEmailRequest,
    db: Database = Depends(database_dep),
    email_client: EmailClient = Depends(email_client_dep),
    event_bus: NotificationEventBus = Depends(event_bus_dep),
) -> TestEmailResponse:
    event_id = f"notification.test:{uuid.uuid4()}"
    subject = "CreditFlow notification test"
    html = f"<h2>CreditFlow notification test</h2><p>Your notification service can reach {email_client.provider.upper()}.</p>"
    text = f"CreditFlow notification test. Your notification service can reach {email_client.provider.upper()}."
    provider_message_id = None
    try:
        provider_message_id = await email_client.send_email(to=payload.recipient, subject=subject, html=html, text=text)
        async with db.transaction() as conn:
            await NotificationRepository(conn).log_attempt(event_id=event_id, event_type="notification.test", notification_type="test_email", channel="email", recipient=payload.recipient, subject=subject, status="sent", provider=email_client.provider, provider_message_id=provider_message_id, metadata={"manual_test": True})
        await event_bus.publish("notification.sent", {"event_id": event_id, "source_event_type": "notification.test", "notification_type": "test_email", "recipient": payload.recipient, "provider_message_id": provider_message_id})
    except Exception as exc:
        async with db.transaction() as conn:
            await NotificationRepository(conn).log_attempt(event_id=event_id, event_type="notification.test", notification_type="test_email", channel="email", recipient=payload.recipient, subject=subject, status="failed", provider=email_client.provider, error=str(exc), metadata={"manual_test": True})
        raise
    return TestEmailResponse(status="sent", recipient=payload.recipient, provider_message_id=provider_message_id)
