from flask import Flask, g, jsonify
from werkzeug.exceptions import HTTPException


class ContentError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details=None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


def error_payload(code: str, message: str, details=None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(g, "request_id", None),
            "details": details,
        }
    }


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ContentError)
    def content_error_handler(exc: ContentError):
        return jsonify(error_payload(exc.code, exc.message, exc.details)), exc.status_code

    @app.errorhandler(HTTPException)
    def http_error_handler(exc: HTTPException):
        return jsonify(error_payload("http_error", exc.description)), exc.code or 500

    @app.errorhandler(Exception)
    def unhandled_error_handler(exc: Exception):
        app.logger.exception("Unhandled content service error")
        return jsonify(error_payload("internal_error", "An unexpected content service error occurred.")), 500
