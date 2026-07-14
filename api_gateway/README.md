# CreditFlow API Gateway

FastAPI service that acts as the single entry point for frontend/API traffic.

## Responsibilities

- Route REST traffic to downstream services.
- Verify JWTs on protected routes and forward account/user context headers.
- Enforce IP and account rate limits using Redis sliding-window counters.
- Receive Stripe, LinkedIn, and OpenRouter webhooks.
- Verify webhook signatures before doing any work.
- Deduplicate webhook events in Redis with a 24 hour TTL.
- Publish normalized webhook events to RabbitMQ using the contract prefixes:
  - `billing.*` for Stripe
  - `social.*` for LinkedIn
  - `ai.*` for OpenRouter
- Re-stream AI generation tokens to the frontend via SSE by subscribing to Redis pub/sub.
- Compose multi-service dashboard summaries.
- Return consistent error envelopes.

## Run locally

```powershell
cd api_gateway
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

Set the frontend env var to point at the gateway:

```text
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8080
```

## Protected route behavior

The gateway expects access tokens with these claims:

```json
{
  "user_id": "usr_123",
  "account_id": "acct_123",
  "role": "Owner",
  "jti": "session-id",
  "exp": 1893456000
}
```

For every protected request it:

1. Requires `Authorization: Bearer <token>`.
2. Verifies signature, expiry, issuer/audience when configured.
3. Checks Redis key `jwt:revoked:<jti>` to reject revoked sessions.
4. Adds `x-user-id`, `x-account-id`, `x-role`, `x-jti`, and `x-request-id` headers to downstream requests.

## Public routes

- `GET /health/live`
- `GET /health/ready`
- `POST /webhooks/stripe`
- `POST /webhooks/linkedin`
- `POST /webhooks/openrouter`
- Auth proxy paths configured in `PUBLIC_AUTH_PATHS`, including login, signup, refresh, forgot password, and verify email.

## SSE flow

Frontend calls:

```text
GET /content/generate/stream?prompt=...
```

The gateway authenticates the request, starts generation by calling:

```text
POST {AI_GENERATION_SERVICE_URL}/internal/generations
```

The generation service should return:

```json
{ "channel": "ai-generation:acct_123:req_123" }
```

The gateway subscribes to that Redis channel and forwards messages as Server-Sent Events until `[DONE]`, `{ "event": "done" }`, or `{ "event": "error" }` arrives.

## Error schema

All gateway-generated errors use:

```json
{
  "error": {
    "code": "invalid_token",
    "message": "Access token is invalid.",
    "request_id": "...",
    "details": null
  }
}
```