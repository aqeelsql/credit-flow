from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AdminError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AdminError)
    async def admin_error_handler(request: Request, exc: AdminError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "request_id": getattr(request.state, "request_id", None)}})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "An unexpected admin service error occurred.", "request_id": getattr(request.state, "request_id", None)}})
