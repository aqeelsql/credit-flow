from fastapi import APIRouter, Request

from app.proxy import proxy_request

router = APIRouter(tags=["proxy"])


async def route_to_service(request: Request, service_key: str, path: str = ""):
    return await proxy_request(
        request,
        service_key=service_key,
        path=path,
        settings=request.app.state.settings,
        redis_state=request.app.state.redis_state,
    )


@router.api_route("/auth", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def auth_proxy(request: Request, path: str = ""):
    return await route_to_service(request, "auth", path)


@router.api_route("/accounts", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/accounts/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def accounts_proxy(request: Request, path: str = ""):
    return await route_to_service(request, "accounts", path)


@router.api_route("/content", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/content/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def content_proxy(request: Request, path: str = ""):
    return await route_to_service(request, "content", path)


@router.api_route("/calendar", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/calendar/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def calendar_proxy(request: Request, path: str = ""):
    return await route_to_service(request, "calendar", path)


@router.api_route("/linkedin", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/linkedin/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def linkedin_proxy(request: Request, path: str = ""):
    return await route_to_service(request, "linkedin", path)


@router.api_route("/billing", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/billing/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def billing_proxy(request: Request, path: str = ""):
    return await route_to_service(request, "billing", path)


@router.api_route("/credits", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/credits/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def credits_proxy(request: Request, path: str = ""):
    return await route_to_service(request, "credits", path)


@router.api_route("/admin", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/admin/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def admin_proxy(request: Request, path: str = ""):
    return await route_to_service(request, "admin", path)


@router.api_route("/usage", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/usage/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def usage_proxy(request: Request, path: str = ""):
    return await route_to_service(request, "usage", path)


@router.api_route("/ai", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/ai/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def ai_generation_proxy(request: Request, path: str = ""):
    return await route_to_service(request, "ai", path)


@router.api_route("/scraper", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@router.api_route("/scraper/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def scraper_proxy(request: Request, path: str = ""):
    return await route_to_service(request, "scraper", path)
