import httpx

from app.config import Settings
from app.errors import GenerationError


class UsageQuotaClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def check(
        self,
        account_id: str,
        user_id: str,
        model: str,
        max_tokens: int,
        request_id: str | None,
    ) -> dict:
        headers = {"x-internal-token": self.settings.internal_service_token}
        if request_id:
            headers["x-request-id"] = request_id
        payload = {
            "account_id": account_id,
            "user_id": user_id,
            "operation": "text_generation",
            "model": model,
            "max_tokens": max_tokens,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.usage_service_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.settings.usage_service_url.rstrip('/')}/internal/quota/check",
                    json=payload,
                    headers=headers,
                )
        except httpx.RequestError as exc:
            raise GenerationError("usage_service_unavailable", "Usage quota could not be checked.", 503) from exc

        if response.status_code in {402, 403, 409, 429}:
            raise GenerationError("quota_exceeded", "The account does not have quota for this generation.", 429)
        if response.is_error:
            raise GenerationError("quota_check_failed", "Usage Service rejected the quota check.", 502)
        try:
            result = response.json()
        except ValueError as exc:
            raise GenerationError("invalid_quota_response", "Usage Service returned an invalid quota response.", 502) from exc
        if not result.get("allowed", False):
            raise GenerationError("quota_exceeded", "The account does not have quota for this generation.", 429)
        return result
