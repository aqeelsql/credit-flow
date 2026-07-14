# CreditFlow Scraper Service

Service 11 runs web-scraping jobs for trend and competitor data.

## Responsibilities

- Consumes `scrape.requested` from RabbitMQ.
- Uses Crawl4AI to fetch and extract structured page data.
- Respects `robots.txt` and rate-limits requests per target domain.
- Stores raw scraped documents in MongoDB collection `scraped_documents`.
- Tracks processed `event_id` values for idempotency.
- Publishes `scrape.completed` with MongoDB document reference.
- Publishes `scrape.failed` after bounded retries.
- Configures durable RabbitMQ queues/messages plus retry queue and DLQ.
- Supports internal recurring scrape jobs.

## Run locally

Install dependencies:

```powershell
cd scraper_service
py -3.12 -m pip install -r requirements.txt
crawl4ai-setup
```

If `crawl4ai` takes a long time to install with the default `py` command, use Python 3.12 explicitly as shown above. Python 3.14 may not be the best target for Crawl4AI packages yet.

Run service:

```powershell
cd scraper_service
py -3.12 -m uvicorn app.main:app --reload --port 8012
```

## MongoDB

Expected env:

```env
MONGODB_URL=mongodb://localhost:27017/creditflow_scraper
SCRAPER_MONGODB_DATABASE=creditflow_scraper
SCRAPER_MONGODB_COLLECTION=scraped_documents
```

## RabbitMQ event contract

Consumes:

- `scrape.requested`

Publishes:

- `scrape.completed`
- `scrape.failed`
