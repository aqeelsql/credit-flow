from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AccountError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details=None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


def error_payload(code: str, message: str, request: Request | None = None, details=None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", None) if request else None,
            "details": details,
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AccountError)
    async def account_error_handler(request: Request, exc: AccountError):
        return JSONResponse(status_code=exc.status_code, content=error_payload(exc.code, exc.message, request, exc.details))

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content=error_payload("http_error", str(exc.detail), request))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content=error_payload("validation_error", "Request validation failed.", request, exc.errors()))

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content=error_payload("internal_error", "An unexpected account service error occurred.", request))
