from fastapi import Request

from app.database import Database


def database_dep(request: Request) -> Database:
    return request.app.state.database
