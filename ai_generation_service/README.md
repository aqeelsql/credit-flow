# CreditFlow AI Generation Service

Text-only generation service backed by OpenRouter. It persists every job in the shared PostgreSQL database, publishes token chunks through Redis for the API Gateway SSE stream, and emits completion/failure events through RabbitMQ.

Image generation is intentionally not implemented yet.

## Configuration

The service reads the project root `.env`. Set these values before generating text:

```dotenv
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
OPENROUTER_FALLBACK_MODEL=openrouter/free
```

The configured model remains the primary. If OpenRouter rejects it before any text is emitted, the service retries once through the free-model router. No fallback occurs after a partial response.

It also uses the shared `DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`, `RABBITMQ_EXCHANGE`, and `INTERNAL_SERVICE_TOKEN`. Its owned PostgreSQL schema is selected by `AI_GENERATION_DATABASE_SCHEMA`.

## Quota admission

The default `AI_GENERATION_QUOTA_BACKEND=redis` performs an atomic per-account quota reservation in Redis. `AI_GENERATION_DAILY_REQUEST_LIMIT` controls the rolling 24-hour request allowance.

When the Usage Service is implemented, set `AI_GENERATION_QUOTA_BACKEND=usage`. The service will then call:

```text
POST {USAGE_SERVICE_URL}/internal/quota/check
X-Internal-Token: {INTERNAL_SERVICE_TOKEN}
```

The response must be successful JSON containing `{"allowed": true}`. A denial or unavailable Usage Service prevents generation from starting in `usage` mode.

## API

- `POST /internal/generations` — gateway-only generation start
- `POST /internal/generations/{job_id}/cancel` — gateway-only cancellation
- `GET /generations` — account-scoped job and prompt history
- `GET /generations/{job_id}` — account-scoped job detail
- `POST /generations/{job_id}/cancel` — account-scoped cancellation
- `GET /health` and `GET /ready` — health checks

Client-facing text streaming remains at the API Gateway endpoint `GET /content/generate/stream?prompt=...`.

## Events

- `ai.generation_completed` includes model, token counts, cost, account, user, and job IDs.
- `ai.generation_failed` includes the error reason and generation scope.

## Run locally

```powershell
cd ai_generation_service
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --port 8010
```
