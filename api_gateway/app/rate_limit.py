from fastapi import Request
from jwt import decode as jwt_decode
from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import Settings
from app.errors import GatewayError, error_payload
from app.redis_state import RedisState


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings, redis_state: RedisState):
        super().__init__(app)
        self.settings = settings
        self.redis_state = redis_state

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(("/health", "/docs", "/openapi")):
            return await call_next(request)

        try:
            ip = request.client.host if request.client else "unknown"
            ip_decision = await self.redis_state.sliding_window_allow(
                f"ip:{ip}",
                self.settings.rate_limit_ip_requests,
                self.settings.rate_limit_window_seconds,
            )
            if not ip_decision.allowed:
                return self._limited_response(request, "ip", ip_decision.reset_seconds)

            account_id = self._account_id_from_request(request)
            if account_id:
                account_decision = await self.redis_state.sliding_window_allow(
                    f"account:{account_id}",
                    self.settings.rate_limit_account_requests,
                    self.settings.rate_limit_window_seconds,
                )
                if not account_decision.allowed:
                    return self._limited_response(request, "account", account_decision.reset_seconds)
        except GatewayError as exc:
            if not self.settings.rate_limit_fail_open:
                return JSONResponse(
                    status_code=exc.status_code,
                    content=error_payload(exc.code, exc.message, request, exc.details),
                )

        response = await call_next(request)
        return response

    @staticmethod
    def _account_id_from_request(request: Request) -> str | None:
        header_account_id = request.headers.get("x-account-id")
        if header_account_id:
            return header_account_id
        authorization = request.headers.get("authorization") or ""
        if not authorization.startswith("Bearer "):
            return None
        token = authorization.removeprefix("Bearer ").strip()
        try:
            claims = jwt_decode(token, options={"verify_signature": False})
        except Exception:
            return None
        account_id = claims.get("account_id")
        return str(account_id) if account_id else None

    @staticmethod
    def _limited_response(request: Request, scope: str, retry_after: int) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=error_payload("rate_limited", f"Rate limit exceeded for {scope} scope.", request),
            headers={"Retry-After": str(retry_after)},
        )