from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status


class GatewayError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 500, details: dict | list | str | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


def error_payload(code: str, message: str, request: Request | None = None, details=None) -> dict:
    request_id = None
    if request is not None:
        request_id = getattr(request.state, "request_id", None)
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details,
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(GatewayError)
    async def gateway_error_handler(request: Request, exc: GatewayError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, request, exc.details),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        code = "http_error"
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            code = "unauthorized"
        elif exc.status_code == status.HTTP_403_FORBIDDEN:
            code = "forbidden"
        elif exc.status_code == status.HTTP_404_NOT_FOUND:
            code = "not_found"
        elif exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            code = "rate_limited"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code, str(exc.detail), request),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_payload("validation_error", "Request validation failed.", request, exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload("internal_error", "An unexpected gateway error occurred.", request),
        )