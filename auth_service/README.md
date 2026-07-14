# CreditFlow Auth Service

FastAPI service for identity, simple signup/login, password reset, JWT issuance/refresh, account-scoped session switching, and session revocation. Email verification tables/routes are retained for the later full-auth phase, but signup is currently active immediately for local development.

## Stack

- Framework: FastAPI
- Database: PostgreSQL with SQLAlchemy startup schema creation plus asyncpg query execution
- Hashing: `bcrypt`
- Cache/session state: Redis
- Events: RabbitMQ topic exchange
- Tokens: JWT, HS256 by default with RS256-compatible key settings

## Local setup

1. Create the shared app database: `createdb creditflow`
2. Start the service; SQLAlchemy creates the `auth` schema/tables automatically. The SQL file remains as a manual fallback.
3. Use the root `.env` file for shared app settings, or copy `.env.example` only for standalone service runs.
4. Install deps: `py -m pip install -r requirements.txt`
5. Run: `uvicorn app.main:app --reload --port 8001`

## HTTP endpoints

The API Gateway strips `/auth` before proxying, so this service exposes routes at the root:

- `POST /signup` - create an active user, bcrypt-hash password, bootstrap an individual Owner account through User / Tenant Service, emit `user.registered`.
- `POST /verify-email` - retained for the later full-auth flow; not required by the current simple signup/login path.
- `POST /login` - rate-limit by email/IP, verify password, issue account-scoped JWT and refresh cookie.
- `POST /refresh` - rotate refresh token and issue a new access JWT.
- `POST /switch-account` - issue a new account-scoped session for the selected account.
- `POST /logout` - revoke refresh session and Redis JTI state.
- `POST /revoke` - SuperAdmin-only JTI revocation.
- `GET /sessions` - SuperAdmin-only active refresh session list.
- `POST /forgot-password/request` - create short-lived OTP and emit `user.password_reset_requested`.
- `POST /forgot-password/reset` - consume OTP, update bcrypt password hash, revoke active sessions.
- `GET /me` - return current JWT claims.
- `GET /health`, `GET /ready` - liveness/readiness.

## Event contract

Publishes:

- `user.registered`
- `user.logged_in`
- `user.password_reset_requested`

Consumes: none.

## JWT claims

Access tokens include `user_id`, `sub`, `account_id`, `role`, `jti`, `iss`, `iat`, and `exp`.





