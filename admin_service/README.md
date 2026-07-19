# CreditFlow Admin / Ops Service

Operational visibility service for active JWT sessions, per-account aggregation, and global audit logging.

## Run locally

```powershell
cd D:\ATS\CF\admin_service
py -3.12 -m pip install -r requirements.txt
py -3.12 -m uvicorn app.main:app --reload --port 8008
```

## Endpoints

- `GET /health`
- `GET /ready`
- `GET /admin/sessions`
- `DELETE /admin/sessions/{jti}`
- `GET /admin/audit-log`
- `GET /admin/accounts/{account_id}/overview`

RBAC is enforced from Gateway identity headers: `SuperAdmin` can view all accounts; `TenantAdmin` is scoped to `x-account-id`.
