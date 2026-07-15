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
- Supports topic-based research jobs where the user supplies what to research, not a fixed URL.
- Stores recurring research drafts and generated research packs.
- Can generate a social post from a research pack with OpenRouter and save it into Content Service drafts.

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
SCRAPER_RESEARCH_SEARCH_ENDPOINT=https://www.bing.com/news/search
SCRAPER_CONTENT_SERVICE_URL=http://localhost:8003
```

MongoDB collections owned by this service:

- `scraped_documents`
- `processed_events`
- `domain_rate_limits`
- `recurring_scrapes`
- `research_jobs`
- `research_packs`

## Topic research flow

1. User enters a topic such as `latest stock market news for fintech founders`.
2. Scraper discovers source URLs using the configured RSS/news search endpoint.
3. Scraper crawls the discovered sources while respecting `robots.txt`.
4. Scraped results are saved as a MongoDB research pack.
5. User can click `Generate post draft with LLM` to create a social post.
6. The generated post is saved to Content Service as a normal draft, so Content Studio, approval, and Scheduler continue to work as before.

## RabbitMQ event contract

Consumes:

- `scrape.requested`

Publishes:

- `scrape.completed`
- `scrape.failed`
