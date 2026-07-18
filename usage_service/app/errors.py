from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class UsageError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def error_payload(code: str, message: str, request: Request, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}, "request_id": getattr(request.state, "request_id", None)}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(UsageError)
    async def usage_error_handler(request: Request, exc: UsageError):
        return JSONResponse(status_code=exc.status_code, content=error_payload(exc.code, exc.message, request, exc.details))

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content=error_payload("internal_error", "An unexpected usage service error occurred.", request))

