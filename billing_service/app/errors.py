from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class BillingError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BillingError)
    async def billing_error_handler(request: Request, exc: BillingError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details, "request_id": getattr(request.state, "request_id", None)}})

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "An unexpected billing service error occurred.", "request_id": getattr(request.state, "request_id", None)}})

