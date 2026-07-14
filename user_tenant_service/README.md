# CreditFlow User / Tenant Service

FastAPI service for accounts/tenants, account-scoped memberships, team invitations, role assignment, and account profile data.

This service uses the shared PostgreSQL database and stores its tables in the `user_tenant` schema: `accounts`, `account_members`, and `invites`.

## Local setup

1. Start the service; SQLAlchemy creates the `user_tenant` schema/tables automatically. The SQL file remains as a manual fallback.
2. Install deps: `py -m pip install -r requirements.txt`
3. Run: `uvicorn app.main:app --reload --port 8002`

## Main endpoints

- `GET /` - list current user's accounts from gateway identity headers.
- `POST /` - create an individual or team account with the current user as Owner.
- `GET /{account_id}/summary` - account profile data for dashboard/header aggregation.
- `GET /{account_id}/team` - Owner/TenantAdmin member list.
- `POST /{account_id}/invites` - Owner/TenantAdmin invite creation and notification event.
- `PATCH /{account_id}/members/{membership_id}` - Owner/TenantAdmin role change.
- `DELETE /{account_id}/members/{membership_id}` - Owner/TenantAdmin member removal.
- `POST /invites/accept` - accept an invite code and create an active membership.
- `GET /internal/users/{user_id}/memberships` - internal Auth Service lookup for account switching.
- `POST /internal/users/{user_id}/individual-account` - internal signup bootstrap.

## Event contract

Publishes:

- `account.created`
- `account.updated`
- `member.joined`
- `member.invited`

Consumes:

- `user.registered`
- `invoice.paid`


