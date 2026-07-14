from fastapi import APIRouter, Depends, Query

from app.database import Database
from app.dependencies import current_principal, database_dep, image_manager_dep, manager_dep, require_internal
from app.errors import GenerationError
from app.generation import GenerationManager
from app.images import ImageGenerationManager
from app.repository import GenerationRepository
from app.schemas import (
    CancellationResponse,
    GenerationJobResponse,
    GenerationListResponse,
    ImageGenerationResponse,
    Principal,
    StartImageGenerationRequest,
    StartGenerationRequest,
    StartGenerationResponse,
)

router = APIRouter(tags=["generations"])


@router.post(
    "/internal/generations",
    response_model=StartGenerationResponse,
    status_code=202,
    dependencies=[Depends(require_internal)],
)
async def start_internal_generation(
    body: StartGenerationRequest,
    manager: GenerationManager = Depends(manager_dep),
) -> StartGenerationResponse:
    job = await manager.start(body)
    return StartGenerationResponse(job_id=job["id"], channel=job["channel"], status=job["status"], model=job["model"])


@router.post(
    "/internal/generations/{job_id}/cancel",
    response_model=CancellationResponse,
    dependencies=[Depends(require_internal)],
)
async def cancel_internal_generation(
    job_id: str,
    manager: GenerationManager = Depends(manager_dep),
) -> CancellationResponse:
    job = await manager.cancel(job_id)
    return CancellationResponse(job_id=job["id"], status="cancellation_requested")


@router.post(
    "/internal/images",
    response_model=ImageGenerationResponse,
    dependencies=[Depends(require_internal)],
)
async def start_internal_image_generation(
    body: StartImageGenerationRequest,
    image_manager: ImageGenerationManager = Depends(image_manager_dep),
) -> ImageGenerationResponse:
    job = await image_manager.generate(body)
    return ImageGenerationResponse.model_validate(job)


@router.get(
    "/internal/images/{image_id}",
    response_model=ImageGenerationResponse,
    dependencies=[Depends(require_internal)],
)
async def get_internal_image_generation(
    image_id: str,
    image_manager: ImageGenerationManager = Depends(image_manager_dep),
) -> ImageGenerationResponse:
    job = await image_manager.get(image_id)
    if job is None:
        raise GenerationError("image_job_not_found", "Image generation job was not found.", 404)
    return ImageGenerationResponse.model_validate(job)


@router.get("/generations", response_model=GenerationListResponse)
async def list_generations(
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(current_principal),
    db: Database = Depends(database_dep),
) -> GenerationListResponse:
    async with db.acquire() as conn:
        jobs = await GenerationRepository(conn).list_jobs(principal.account_id or "", limit)
    return GenerationListResponse(items=[GenerationJobResponse.model_validate(job) for job in jobs])


@router.get("/generations/{job_id}", response_model=GenerationJobResponse)
async def get_generation(
    job_id: str,
    principal: Principal = Depends(current_principal),
    db: Database = Depends(database_dep),
) -> GenerationJobResponse:
    async with db.acquire() as conn:
        job = await GenerationRepository(conn).get_job(job_id, principal.account_id or "")
    if job is None:
        raise GenerationError("job_not_found", "Generation job was not found.", 404)
    return GenerationJobResponse.model_validate(job)


@router.post("/generations/{job_id}/cancel", response_model=CancellationResponse)
async def cancel_generation(
    job_id: str,
    principal: Principal = Depends(current_principal),
    manager: GenerationManager = Depends(manager_dep),
) -> CancellationResponse:
    job = await manager.cancel(job_id, principal.account_id)
    return CancellationResponse(job_id=job["id"], status="cancellation_requested")
