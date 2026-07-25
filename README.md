# CreditFlow

CreditFlow is a multi-tenant SaaS platform for AI-assisted LinkedIn content creation, research, scheduling, publishing, billing, credits, notifications, and platform operations.

The system is built as independent microservices. The frontend talks through the API Gateway, services use REST for direct reads/writes where appropriate, and RabbitMQ carries domain events between services. PostgreSQL stores most service-owned data, MongoDB stores flexible scraped research documents, and Redis is used for sessions, quota counters, scheduler locks, and Celery broker/backend state.

## What the platform does

1. Users sign up, verify email, log in, and work as account Owners or invited Members.
2. Owners can invite team members, manage credits, buy subscription plans, review content, schedule posts, and publish to LinkedIn.
3. Members can create AI content inside their account scope.
4. Content Studio sends prompts to the AI Generation Service. Credits are checked and deducted through Usage/Credits services.
5. Research Scraper searches Google via SerpAPI, scrapes useful source content, and lets users generate posts from selected research.
6. Content Service stores generated posts, drafts, versions, approval state, and optional images.
7. Scheduler Service stores publish times and emits publishing events when posts are due.
8. Social Publishing Service connects LinkedIn OAuth and publishes text or text+image posts.
9. Billing Service handles Stripe test-mode checkout, subscriptions, credit purchases, invoices, refunds, and outbox publishing.
10. Notification Service sends verification, invite, billing, usage, and publishing emails through Gmail SMTP.
11. Admin/Ops Service powers the SuperAdmin console with account directory, audit trail, sessions, credits, revenue, and usage visibility.

## Project structure

```text
CreditFlow/
+-- frontend/                    # Next.js web app
+-- api_gateway/                 # Public API entrypoint and request proxy
+-- auth_service/                # Login, signup, verification, password reset, sessions
+-- user_tenant_service/         # Accounts, members, invitations, tenant roles
+-- credits_service/             # Credit packages, balances, purchases, ledger sync
+-- usage_service/               # AI quota checks, token/credit usage metering
+-- ai_generation_service/       # OpenRouter text generation and Pollinations image generation
+-- content_service/             # Drafts, content versions, approvals, image uploads
+-- scheduler_service/           # Calendar scheduling and due-post scanner
+-- social_publishing_service/   # LinkedIn OAuth and LinkedIn publishing
+-- billing_service/             # Stripe checkout, subscriptions, invoices, refunds
+-- scraper_service/             # SerpAPI/Crawl4AI research scraping into MongoDB
+-- notification_service/        # Email notifications and notification audit log
+-- admin_service/               # SuperAdmin/Ops console APIs and audit log
+-- docker-compose.yml           # Single local/EC2 Docker Compose stack
+-- .env_example                 # Safe environment template
+-- EC2_DEPLOY.md                # EC2 deployment notes
```

## Services and default ports

| Service | Path | Port | Main responsibility |
|---|---:|---:|---|
| Frontend | `frontend/` | `3000` | User interface |
| API Gateway | `api_gateway/` | `8000 -> 8080` | Public API routing/proxy |
| Auth | `auth_service/` | `8001 -> 8000` | Authentication and sessions |
| User/Tenant | `user_tenant_service/` | `8002` | Accounts, members, invites |
| Content | `content_service/` | `8003` | Drafts, content, media metadata |
| Scheduler | `scheduler_service/` | `8004` | Calendar and scheduled handoff |
| Social Publishing | `social_publishing_service/` | `8005` | LinkedIn OAuth/publishing |
| Billing | `billing_service/` | `8006` | Stripe checkout/subscriptions/invoices |
| Credits | `credits_service/` | `8007` | Credit balances and packages |
| Admin/Ops | `admin_service/` | `8008` | SuperAdmin console data |
| Usage | `usage_service/` | `8009` | AI quota and metering |
| AI Generation | `ai_generation_service/` | `8010` | LLM and image generation |
| Scraper | `scraper_service/` | `8012` | Topic research scraping |
| Notification | `notification_service/` | `8013` | Email dispatch and notification logs |

## Infrastructure

The compose stack runs these dependencies as containers:

- PostgreSQL 16
- Redis 7
- RabbitMQ 3 Management
- MongoDB 7

Persistent Docker volumes are used for database data, RabbitMQ data, Redis data, MongoDB data, uploaded content images, and scraper runtime storage.

## Configuration

Create your local environment from the example:

```bash
cp .env_example .env
```

Then fill in the real values in `.env`.

Important notes:

- Do not commit `.env`.
- Use Stripe test-mode keys for educational/local deployment.
- Use a Gmail App Password for SMTP, not your normal Gmail password.
- LinkedIn publishing requires valid LinkedIn app credentials and a matching redirect URI.
- OpenRouter and SerpAPI require API keys for AI generation and Google research scraping.

## Running with Docker Compose

Build and run the full stack:

```bash
docker compose up -d --build
```

View logs:

```bash
docker compose logs -f api_gateway frontend
```

Stop services:

```bash
docker compose down
```

Stop services and delete local Docker volumes/databases:

```bash
docker compose down -v
```

## Local URLs

- Frontend: <http://localhost:3000>
- API Gateway: <http://localhost:8000>
- RabbitMQ Management: <http://localhost:15672>
- LinkedIn OAuth callback service: <http://localhost:8005>

## Deployment note

For an educational EC2 deployment without a domain, use the EC2 public IP in `.env` values such as `FRONTEND_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL`, `ALLOWED_ORIGINS`, `LINKEDIN_REDIRECT_URI`, and Stripe checkout URLs.

Example:

```env
FRONTEND_BASE_URL=http://YOUR_EC2_PUBLIC_IP:3000
NEXT_PUBLIC_API_BASE_URL=http://YOUR_EC2_PUBLIC_IP:8000
LINKEDIN_REDIRECT_URI=http://YOUR_EC2_PUBLIC_IP:8005/linkedin/callback
```

Then run:

```bash
docker compose up -d --build
```
