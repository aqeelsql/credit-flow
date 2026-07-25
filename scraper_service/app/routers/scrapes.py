import uuid

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import current_principal, require_internal
from app.errors import ScraperError
from app.repository import ScraperRepository
from app.schemas import RecurringScrapeRequest, ResearchJobRequest, ScrapeRequested, StartScrapeRequest, TopicResearchRequest
from app.crawler import ScrapeRunner
from app.post_writer import build_social_prompt, generate_social_post, save_content_draft
from app.research import ResearchRunner

router = APIRouter(tags=["scrapes"])


@router.post("/scrapes", status_code=410)
async def request_scrape(request: Request, body: StartScrapeRequest):
    raise ScraperError("url_scraping_removed", "Direct URL scraping has been removed. Use topic research instead.", 410)


@router.post("/scrapes/run-now", status_code=410)
async def run_scrape_now(request: Request, body: StartScrapeRequest):
    raise ScraperError("url_scraping_removed", "Direct URL scraping has been removed. Use topic research instead.", 410)


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


@router.post("/recurring-scrapes", status_code=410)
async def create_account_recurring_scrape(request: Request, body: RecurringScrapeRequest):
    raise ScraperError("url_scraping_removed", "Recurring direct URL scraping has been removed. Use scheduled topic research instead.", 410)


@router.post("/research/run-now", status_code=201)
async def run_topic_research_now(request: Request, body: TopicResearchRequest):
    principal = current_principal(request)
    repo: ScraperRepository = request.app.state.repo
    pack = await ResearchRunner(request.app.state.settings, repo).run(body, principal.account_id, principal.user_id)
    return {"status": pack["status"], "research_pack_id": pack["id"], "pack": pack}


@router.post("/research-jobs", status_code=201)
async def create_research_job(request: Request, body: ResearchJobRequest):
    principal = current_principal(request)
    repo: ScraperRepository = request.app.state.repo
    research_job_id = await repo.create_research_job({**body.model_dump(), "account_id": principal.account_id, "created_by_user_id": principal.user_id})
    return {"id": research_job_id, "status": "created"}


@router.get("/research-jobs", response_model=dict)
async def list_research_jobs(request: Request, limit: int = Query(default=50, ge=1, le=100)):
    principal = current_principal(request)
    repo: ScraperRepository = request.app.state.repo
    return {"items": await repo.list_research_jobs(principal.account_id, limit)}


@router.get("/research-packs", response_model=dict)
async def list_research_packs(request: Request, limit: int = Query(default=25, ge=1, le=100)):
    principal = current_principal(request)
    repo: ScraperRepository = request.app.state.repo
    return {"items": await repo.list_research_packs(principal.account_id, limit)}


@router.get("/research-packs/{pack_id}", response_model=dict)
async def get_research_pack(request: Request, pack_id: str):
    repo: ScraperRepository = request.app.state.repo
    pack = await repo.get_research_pack(pack_id)
    if pack is None:
        raise ScraperError("research_pack_not_found", "Research pack was not found.", 404)
    return pack


@router.delete("/research-packs/{pack_id}", response_model=dict)
async def delete_research_pack(request: Request, pack_id: str):
    principal = current_principal(request)
    repo: ScraperRepository = request.app.state.repo
    deleted = await repo.delete_research_pack(pack_id, principal.account_id)
    if not deleted:
        raise ScraperError("research_pack_not_found", "Research pack was not found.", 404)
    return {"status": "deleted", "id": pack_id}


@router.post("/research-packs/{pack_id}/generate-post", response_model=dict)
async def generate_post_from_research_pack(request: Request, pack_id: str):
    principal = current_principal(request)
    repo: ScraperRepository = request.app.state.repo
    pack = await repo.get_research_pack(pack_id)
    if pack is None:
        raise ScraperError("research_pack_not_found", "Research pack was not found.", 404)
    prompt = build_social_prompt(pack, str(pack.get("output_type") or "linkedin_post"))
    post_text = await generate_social_post(request.app.state.settings, pack, str(pack.get("output_type") or "linkedin_post"))
    content_draft = await save_content_draft(request.app.state.settings, principal, pack, post_text, prompt)
    await repo.attach_generated_post(pack_id, post_text, content_draft)
    return {"status": "draft_created", "post_text": post_text, "content_draft": content_draft}


@router.get("/documents/{document_id}", response_model=dict)
async def get_document(request: Request, document_id: str):
    raise ScraperError("url_scraping_removed", "Direct URL scrape documents are no longer exposed. Use research packs instead.", 410)


@router.delete("/documents/{document_id}", response_model=dict)
async def delete_document(request: Request, document_id: str):
    raise ScraperError("url_scraping_removed", "Direct URL scrape documents are no longer exposed. Use research packs instead.", 410)


@router.get("/documents", response_model=dict)
async def list_documents(request: Request, limit: int = Query(default=25, ge=1, le=100)):
    raise ScraperError("url_scraping_removed", "Direct URL scrape documents are no longer exposed. Use research packs instead.", 410)
