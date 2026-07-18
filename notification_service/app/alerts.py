from __future__ import annotations

import logging

import httpx

from app.config import Settings


class AlertClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def send_slack_alert(self, text: str) -> None:
        if not self.settings.slack_webhook_url:
            return
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.settings.slack_webhook_url, json={"text": text})
            if response.status_code >= 400:
                logging.warning("Slack alert failed with status %s", response.status_code)
        except Exception:
            logging.exception("Slack alert failed")
