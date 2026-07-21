# CreditFlow Notification Service

FastAPI service that consumes domain events, sends transactional emails via Gmail SMTP, optionally sends Slack ops alerts, logs every attempt, and publishes `notification.sent` after successful dispatch.

## Gmail SMTP configuration

Use a Google App Password for `SMTP_PASSWORD`; do not use your normal Gmail password.

```env
EMAIL_FROM=CreditFlow <yourgmail@gmail.com>
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=yourgmail@gmail.com
SMTP_PASSWORD=your_google_app_password
SMTP_USE_TLS=true
SMTP_USE_SSL=false
FRONTEND_URL=http://localhost:3000
```

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

