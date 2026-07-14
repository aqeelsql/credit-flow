import uuid

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import current_principal, require_internal
from app.repository import ScraperRepository
from app.schemas import RecurringScrapeRequest, ScrapeRequested, StartScrapeRequest
from app.crawler import ScrapeRunner

router = APIRouter(tags=["scrapes"])


@router.post("/scrapes", status_code=202)
async def request_scrape(request: Request, body: StartScrapeRequest):
    principal = current_principal(request)
    event_id = f"api:{uuid.uuid4()}"
    payload = {"event_id": event_id, "account_id": principal.account_id, "requested_by_user_id": principal.user_id, "target_url": body.target_url, "job_type": body.job_type, "metadata": body.metadata}
    await request.app.state.events.publish("scrape.requested", payload)
    return {"status": "queued", "event_id": event_id}


@router.post("/scrapes/run-now", status_code=201)
async def run_scrape_now(request: Request, body: StartScrapeRequest):
    principal = current_principal(request)
    repo: ScraperRepository = request.app.state.repo
    event_id = f"direct:{uuid.uuid4()}"
    payload = ScrapeRequested.model_validate(
        {
            "event_id": event_id,
            "account_id": principal.account_id,
            "requested_by_user_id": principal.user_id,
            "target_url": body.target_url,
            "job_type": body.job_type,
            "metadata": body.metadata,
        }
    )
    await repo.claim_event(payload.event_id, payload.model_dump())
    result = await ScrapeRunner(request.app.state.settings, repo).run(payload)
    await repo.complete_event(payload.event_id, result["document_id"])
    try:
        await request.app.state.events.publish(
            "scrape.completed",
            {
                "event_id": payload.event_id,
                "account_id": payload.account_id,
                "job_type": payload.job_type,
                "target_url": payload.target_url,
                "document_id": result["document_id"],
                "mongodb_database": request.app.state.settings.mongodb_database,
                "mongodb_collection": request.app.state.settings.mongodb_collection,
            },
        )
    except Exception:
        pass
    document = await repo.get_document(result["document_id"])
    return {"status": "completed", "event_id": payload.event_id, "document_id": result["document_id"], "document": document}


@router.post("/internal/scrapes", status_code=202, dependencies=[Depends(require_internal)])
async def request_internal_scrape(request: Request, body: StartScrapeRequest):
    event_id = f"internal:{uuid.uuid4()}"
    payload = {"event_id": event_id, "target_url": body.target_url, "job_type": body.job_type, "metadata": body.metadata}
    await request.app.state.events.publish("scrape.requested", payload)
    return {"status": "queued", "event_id": event_id}


@router.post("/internal/recurring-scrapes", dependencies=[Depends(require_internal)])
async def create_recurring_scrape(request: Request, body: RecurringScrapeRequest):
    repo: ScraperRepository = request.app.state.repo
    recurring_id = await repo.create_recurring(body.model_dump())
    return {"id": recurring_id, "status": "created"}


@router.post("/recurring-scrapes", status_code=201)
async def create_account_recurring_scrape(request: Request, body: RecurringScrapeRequest):
    principal = current_principal(request)
    repo: ScraperRepository = request.app.state.repo
    recurring_id = await repo.create_recurring({**body.model_dump(), "account_id": principal.account_id, "created_by_user_id": principal.user_id})
    return {"id": recurring_id, "status": "created"}


@router.get("/documents/{document_id}", response_model=dict)
async def get_document(request: Request, document_id: str):
    doc = await request.app.state.repo.get_document(document_id)
    if doc is None:
        from app.errors import ScraperError
        raise ScraperError("document_not_found", "Scraped document was not found.", 404)
    return doc


@router.get("/documents", response_model=dict)
async def list_documents(request: Request, limit: int = Query(default=25, ge=1, le=100)):
    principal = current_principal(request)
    repo: ScraperRepository = request.app.state.repo
    items = await repo.list_documents(principal.account_id, limit)
    return {"items": items}
