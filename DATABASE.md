# CreditFlow Database Topology

CreditFlow uses one PostgreSQL instance and one local application database named `creditflow`.

Inside that one database, each service owns its own PostgreSQL schema. A service may read and write only the tables in its own schema. Services must not share tables or create cross-service foreign keys. When services need each other, they communicate through HTTP endpoints or RabbitMQ events.

## Local Instance

- PostgreSQL server: one local PostgreSQL instance
- Database: `creditflow`
- Shared connection URL: use the root `.env` value, currently `postgresql://postgres:12345@localhost:5432/creditflow`

## Service Schemas

| Service | Schema | Tables/state |
| --- | --- | --- |
| Auth Service | `auth` | `users`, `credentials`, `refresh_tokens`, `password_reset_tokens`, `email_verification_tokens` |
| User / Tenant Service | `user_tenant` | `accounts`, `account_members`, `invites` |
| Credits / Marketplace Service | `credits` | `credits_ledger`, `marketplace_listings`, `processed_events` |
| AI Generation Service | `ai_generation` | `generation_jobs`, `prompt_history`, `image_generation_jobs` |
| Content Service | `content` | `content`, `content_versions` |
| Scheduler Service | `scheduler` | `scheduled_posts` |
| Social Publishing Service | `social_publishing` | `social_connections`, `publish_jobs`, `post_media` |
| Scraper Service | MongoDB `creditflow_scraper` | `scraped_documents`, `processed_events`, `domain_rate_limits`, `recurring_scrapes`, `research_jobs`, `research_packs` |
| API Gateway | none | No PostgreSQL tables; uses Redis for rate limits, active JWT `jti`, webhook dedupe, and SSE state |

Future services should follow the same pattern. For example, Billing Service should use a `billing` schema, Content Service should use a `content` schema, and Calendar Service should use a `calendar` schema.

## Why This Works

`auth.users` and `user_tenant.accounts` live in the same database, but they are not shared tables. They are separated by schema ownership:

- Every database-backed service connects through the single shared `DATABASE_URL`.
- Auth Service sets `AUTH_DATABASE_SCHEMA=auth`, so unqualified SQL like `SELECT * FROM users` resolves to `auth.users`.
- User / Tenant Service sets `USER_TENANT_DATABASE_SCHEMA=user_tenant`, so unqualified SQL like `SELECT * FROM accounts` resolves to `user_tenant.accounts`.

The two services exchange IDs and events, but they do not join each other's tables.

## Apply Migrations Locally

Normally you do not need to run SQL files manually. Auth Service, User / Tenant Service, and Credits / Marketplace Service create their schemas and tables with SQLAlchemy on startup. If you want to apply the fallback SQL manually, run each service migration against the same `DATABASE_URL`:

```powershell
psql $env:DATABASE_URL -f auth_service/migrations/001_init.sql
psql $env:DATABASE_URL -f user_tenant_service/migrations/001_init.sql
psql $env:DATABASE_URL -f ai_generation_service/migrations/001_init.sql
psql $env:DATABASE_URL -f content_service/migrations/001_init.sql
psql $env:DATABASE_URL -f scheduler_service/migrations/001_init.sql
psql $env:DATABASE_URL -f social_publishing_service/migrations/001_init.sql
```

If you previously applied the older User/Tenant migration that created an `accounts` schema, the current `user_tenant_service` migration copies existing rows into `user_tenant` safely and leaves the old schema untouched.

