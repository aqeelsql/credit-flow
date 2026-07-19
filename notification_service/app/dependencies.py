from fastapi import Request

from app.database import Database
from app.email_client import EmailClient
from app.events import NotificationEventBus
from app.config import Settings, get_settings


def database_dep(request: Request) -> Database:
    return request.app.state.database


def email_client_dep(request: Request) -> EmailClient:
    return request.app.state.email_client


def event_bus_dep(request: Request) -> NotificationEventBus:
    return request.app.state.event_bus


def settings_dep() -> Settings:
    return get_settings()
