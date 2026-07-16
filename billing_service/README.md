# CreditFlow Billing Service

FastAPI service for Stripe sandbox checkout, subscriptions, invoices, refunds, webhook persistence, and transactional outbox publishing.

Run locally:

```powershell
cd D:\ATS\CF\billing_service
py -3.12 -m pip install -r requirements.txt
py -3.12 -m uvicorn app.main:app --reload --port 8006
```

Important routes:

- `POST /checkout/sessions`
- `GET /billing/invoices`
- `POST /billing/refunds`
- `POST /webhooks/stripe`
- `POST /internal/customers`
- `POST /internal/marketplace/escrow/confirm`

