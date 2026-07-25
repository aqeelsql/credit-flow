import httpx

from app.config import Settings
from app.errors import GenerationError


class CreditsClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def debit(self, *, account_id: str, amount: int, event_id: str, reason: str, metadata: dict) -> dict:
        return await self._post("internal/debit", account_id, amount, event_id, reason, metadata, debit=True)

    async def credit(self, *, account_id: str, amount: int, event_id: str, reason: str, metadata: dict) -> dict:
        return await self._post("internal/credit", account_id, amount, event_id, reason, metadata, debit=False)

    async def _post(self, path: str, account_id: str, amount: int, event_id: str, reason: str, metadata: dict, debit: bool) -> dict:
        if amount <= 0:
            return {}
        headers = {"x-internal-token": self.settings.internal_service_token}
        payload = {"account_id": account_id, "amount": int(amount), "event_id": event_id, "reason": reason, "metadata": metadata}
        try:
            async with httpx.AsyncClient(timeout=self.settings.credit_reservation_timeout_seconds, transport=self.transport) as client:
                response = await client.post(f"{self.settings.credits_service_url.rstrip('/')}/{path}", json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise GenerationError("credits_service_unavailable", "Credits Service is unavailable, so generation cannot start.", 503) from exc
        if response.status_code in {402, 403, 409, 429}:
            if debit:
                raise GenerationError("insufficient_credits", "Not enough tokens to generate this post. Please buy more credits.", 429)
            return {}
        if response.is_error:
            raise GenerationError("credits_update_failed", "Credits Service rejected the token update.", 502)
        try:
            return response.json()
        except ValueError:
            return {}
