# CreditFlow Notification Service

FastAPI service that consumes domain events, sends transactional emails via Resend, optionally sends Slack ops alerts, logs every attempt, and publishes `notification.sent` after successful dispatch.

## Run locally

```powershell
cd D:\ATS\CF\notification_service
py -3.12 -m pip install -r requirements.txt
py -3.12 -m uvicorn app.main:app --reload --port 8013
```

## Consumes

- `user.registered`
- `invoice.paid`
- `payment.failed`
- `member.joined`
- `team.invite.created`
- `post.published`
- `post.failed`
- `usage.threshold_reached`

## Publishes

- `notification.sent`

