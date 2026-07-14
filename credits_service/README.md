# CreditFlow Credits / Marketplace Service

FastAPI service for the account credit ledger and peer-to-peer credits marketplace.

## Local Run

```powershell
cd D:\ATS\CF\credits_service
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --port 8007
```

The service reads the shared root `.env` by default. It creates the `credits` PostgreSQL schema and its own tables on startup with SQLAlchemy, then uses asyncpg for runtime queries.

## Owned Data

- `credits.credits_ledger`: append-only credit ledger. Balances are derived from `SUM(amount)`.
- `credits.marketplace_listings`: active, sold, and cancelled marketplace listings.
- `credits.processed_events`: idempotency table for consumed events and internal operations.

## Main Routes

- `GET /balance`
- `GET /transactions`
- `GET /marketplace/listings`
- `GET /marketplace/my-listings`
- `POST /marketplace/listings`
- `POST /marketplace/listings/{listing_id}/buy`
- `POST /marketplace/listings/{listing_id}/cancel`
- `POST /consume`
- `POST /internal/credit`
- `POST /internal/debit`

The API Gateway forwards protected user identity through `x-user-id`, `x-account-id`, and `x-role` headers. Internal routes require `x-internal-token`.
