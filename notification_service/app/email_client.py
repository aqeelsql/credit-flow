from __future__ import annotations

import httpx

from app.config import Settings
from app.errors import NotificationError


class EmailClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def ensure_configured(self) -> None:
        if not self.settings.resend_api_key:
            raise NotificationError("resend_not_configured", "Resend API key is not configured.", 503)

    async def send_email(self, *, to: str, subject: str, html: str, text: str | None = None) -> str | None:
        self.ensure_configured()
        payload = {"from": self.settings.resend_from_email, "to": [to], "subject": subject, "html": html}
        if text:
            payload["text"] = text
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(self.settings.resend_api_url, headers={"Authorization": f"Bearer {self.settings.resend_api_key}", "Content-Type": "application/json"}, json=payload)
        if response.status_code >= 400:
            detail = response.text[:500]
            try:
                body = response.json()
                if isinstance(body, dict):
                    message = body.get("message") or body.get("error") or body.get("name")
                    if message:
                        detail = str(message)[:500]
            except ValueError:
                pass
            status_code = 502 if response.status_code >= 500 else 400
            raise NotificationError("email_dispatch_failed", f"Resend email dispatch failed ({response.status_code}): {detail}", status_code)
        body = response.json()
        return str(body.get("id")) if isinstance(body, dict) and body.get("id") else None
