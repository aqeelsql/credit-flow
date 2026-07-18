# CreditFlow Usage / Metering Service

FastAPI service for real-time AI quota checks and immutable AI usage metering.

## Run locally

```powershell
cd D:\ATS\CF\usage_service
py -3.12 -m pip install -r requirements.txt
py -3.12 -m uvicorn app.main:app --reload --port 8009
```

The service reads `usage_service/.env` first and then the root `.env`.

## Core API

- `POST /internal/quota/check` — called by AI Generation before a model call.
- `GET /usage/accounts/{account_id}/summary` — per-account usage summary grouped by model.
- `GET /admin/usage/summary` — platform usage summary for admin dashboards.
- `POST /internal/quotas/{account_id}` — set an account monthly token quota.
- `POST /internal/reconcile/{account_id}` — force Redis counters to match the durable Postgres ledger.

Consumes: `ai.generation_completed`

Publishes: `usage.threshold_reached`

