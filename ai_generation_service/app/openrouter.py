from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json

import httpx

from app.config import Settings
from app.errors import GenerationError


@dataclass
class OpenRouterChunk:
    text: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost: Decimal | None = None


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


class OpenRouterClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    def validate_configuration(self) -> None:
        missing = []
        if not self.settings.openrouter_api_key:
            missing.append("OPENROUTER_API_KEY")
        if not self.settings.openrouter_model:
            missing.append("OPENROUTER_MODEL")
        if missing:
            raise GenerationError(
                "provider_not_configured",
                "OpenRouter text generation is not configured.",
                503,
                {"missing": missing},
            )

    async def stream(self, prompt: str):
        self.validate_configuration()
        models = [self.settings.openrouter_model]
        fallback = self.settings.openrouter_fallback_model
        if fallback and fallback not in models:
            models.append(fallback)
        last_error: GenerationError | None = None
        for model in models:
            emitted_text = False
            try:
                async for chunk in self._stream_model(prompt, model):
                    emitted_text = emitted_text or bool(chunk.text)
                    yield chunk
                return
            except GenerationError as exc:
                if emitted_text:
                    raise
                last_error = exc
        if last_error is not None:
            raise last_error

    async def complete(self, prompt: str, model: str | None = None, max_tokens: int = 260) -> str:
        self.validate_configuration()
        models = [model or self.settings.openrouter_model]
        fallback = self.settings.openrouter_fallback_model
        if fallback and fallback not in models:
            models.append(fallback)
        last_error: GenerationError | None = None
        for selected_model in models:
            try:
                return await self._complete_model(prompt, selected_model, max_tokens)
            except GenerationError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise GenerationError("provider_empty_response", "OpenRouter returned an empty image prompt.", 502)

    async def _complete_model(self, prompt: str, selected_model: str, max_tokens: int) -> str:
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self.settings.openrouter_site_url:
            headers["HTTP-Referer"] = self.settings.openrouter_site_url
        if self.settings.openrouter_app_name:
            headers["X-Title"] = self.settings.openrouter_app_name
        payload = {
            "model": selected_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": 0.4,
        }
        timeout = httpx.Timeout(self.settings.openrouter_timeout_seconds, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
                response = await client.post(
                    f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.RequestError as exc:
            raise GenerationError("provider_unavailable", "OpenRouter is unavailable.", 502) from exc
        if response.is_error:
            body = response.text[:500]
            raise GenerationError(
                "provider_rejected_request",
                "OpenRouter rejected the image prompt request.",
                502,
                {"provider_status": response.status_code, "provider_body": body},
            )
        try:
            data = response.json()
            choices = data.get("choices") or []
            content = choices[0].get("message", {}).get("content", "") if choices else ""
        except (ValueError, AttributeError, IndexError) as exc:
            raise GenerationError("provider_invalid_response", "OpenRouter returned an invalid image prompt response.", 502) from exc
        content = str(content).strip().strip('"')
        if not content:
            raise GenerationError("provider_empty_response", "OpenRouter returned an empty image prompt.", 502)
        return content

    async def _stream_model(self, prompt: str, model: str):
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self.settings.openrouter_site_url:
            headers["HTTP-Referer"] = self.settings.openrouter_site_url
        if self.settings.openrouter_app_name:
            headers["X-Title"] = self.settings.openrouter_app_name
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "max_tokens": self.settings.max_output_tokens,
        }
        timeout = httpx.Timeout(self.settings.openrouter_timeout_seconds, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
                async with client.stream(
                    "POST",
                    f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.is_error:
                        body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        raise GenerationError(
                            "provider_rejected_request",
                            "OpenRouter rejected the generation request.",
                            502,
                            {"provider_status": response.status_code, "provider_body": body},
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if event.get("error"):
                            provider_error = event["error"]
                            message = provider_error.get("message", "OpenRouter stream failed.") if isinstance(provider_error, dict) else str(provider_error)
                            raise GenerationError(
                                "provider_stream_failed",
                                "OpenRouter stopped the generation stream.",
                                502,
                                {"provider_message": message},
                            )
                        choices = event.get("choices") or []
                        delta = choices[0].get("delta", {}).get("content", "") if choices else ""
                        usage = event.get("usage") or {}
                        yield OpenRouterChunk(
                            text=delta or "",
                            prompt_tokens=usage.get("prompt_tokens"),
                            completion_tokens=usage.get("completion_tokens"),
                            total_tokens=usage.get("total_tokens"),
                            cost=_decimal(usage.get("cost")),
                        )
        except GenerationError:
            raise
        except httpx.RequestError as exc:
            raise GenerationError("provider_unavailable", "OpenRouter is unavailable.", 502) from exc
