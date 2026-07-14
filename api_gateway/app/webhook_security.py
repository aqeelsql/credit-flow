import hashlib
import hmac
import json
import time

from fastapi import Request
from starlette import status

from app.config import Settings
from app.errors import GatewayError
from app.schemas import WebhookEnvelope


def _normalize_signature(value: str) -> list[str]:
    cleaned = value.strip()
    if cleaned.startswith("sha256="):
        cleaned = cleaned[len("sha256=") :]
    return [part.strip() for part in cleaned.split(",") if part.strip()]


def verify_stripe_signature(body: bytes, signature_header: str | None, settings: Settings) -> None:
    if not settings.stripe_webhook_secret:
        raise GatewayError("webhook_secret_missing", "Stripe webhook secret is not configured.", status.HTTP_503_SERVICE_UNAVAILABLE)
    if not signature_header:
        raise GatewayError("webhook_signature_missing", "Stripe signature header is missing.", status.HTTP_401_UNAUTHORIZED)

    parts: dict[str, list[str]] = {}
    for item in signature_header.split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            parts.setdefault(key, []).append(value)
    timestamp_raw = parts.get("t", [None])[0]
    signatures = parts.get("v1", [])
    if not timestamp_raw or not signatures:
        raise GatewayError("webhook_signature_invalid", "Stripe signature header is malformed.", status.HTTP_401_UNAUTHORIZED)

    timestamp = int(timestamp_raw)
    if abs(time.time() - timestamp) > settings.webhook_signature_tolerance_seconds:
        raise GatewayError("webhook_signature_expired", "Stripe signature timestamp is outside tolerance.", status.HTTP_401_UNAUTHORIZED)

    signed_payload = f"{timestamp}.{body.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(settings.stripe_webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise GatewayError("webhook_signature_invalid", "Stripe signature verification failed.", status.HTTP_401_UNAUTHORIZED)


def verify_hmac_sha256(body: bytes, signature_header: str | None, secret: str, provider: str) -> None:
    if not secret:
        raise GatewayError("webhook_secret_missing", f"{provider} webhook secret is not configured.", status.HTTP_503_SERVICE_UNAVAILABLE)
    if not signature_header:
        raise GatewayError("webhook_signature_missing", f"{provider} signature header is missing.", status.HTTP_401_UNAUTHORIZED)
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    signatures = _normalize_signature(signature_header)
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise GatewayError("webhook_signature_invalid", f"{provider} signature verification failed.", status.HTTP_401_UNAUTHORIZED)


async def verify_provider_signature(provider: str, request: Request, body: bytes, settings: Settings) -> None:
    if provider == "stripe":
        verify_stripe_signature(body, request.headers.get("stripe-signature"), settings)
        return
    if provider == "linkedin":
        signature = request.headers.get("x-linkedin-signature") or request.headers.get("x-hub-signature-256")
        verify_hmac_sha256(body, signature, settings.linkedin_webhook_secret, "LinkedIn")
        return
    if provider == "openrouter":
        signature = request.headers.get("x-openrouter-signature") or request.headers.get("x-webhook-signature")
        verify_hmac_sha256(body, signature, settings.openrouter_webhook_secret, "OpenRouter")
        return
    raise GatewayError("unknown_webhook_provider", "Unknown webhook provider.", status.HTTP_404_NOT_FOUND)


def normalize_webhook(provider: str, body: bytes) -> WebhookEnvelope:
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise GatewayError("webhook_json_invalid", "Webhook body must be valid JSON.", status.HTTP_400_BAD_REQUEST) from exc

    if provider == "stripe":
        event_id = str(payload.get("id") or "")
        event_type = str(payload.get("type") or "stripe.event")
        account_id = payload.get("account") or payload.get("data", {}).get("object", {}).get("metadata", {}).get("account_id")
    elif provider == "linkedin":
        event_id = str(payload.get("id") or payload.get("eventId") or payload.get("notificationId") or "")
        event_type = str(payload.get("eventType") or payload.get("type") or "linkedin.event")
        account_id = payload.get("account_id") or payload.get("accountId")
    else:
        event_id = str(payload.get("id") or payload.get("event_id") or payload.get("generation_id") or "")
        event_type = str(payload.get("type") or payload.get("event") or "openrouter.event")
        account_id = payload.get("account_id") or payload.get("accountId")

    if not event_id:
        digest = hashlib.sha256(body).hexdigest()
        event_id = f"body:{digest}"

    return WebhookEnvelope(
        provider=provider,
        provider_event_id=event_id,
        event_type=event_type,
        account_id=str(account_id) if account_id else None,
        payload=payload,
    )