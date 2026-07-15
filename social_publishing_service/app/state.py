import base64
import hashlib
import hmac
import json
import time
import uuid

from app.config import Settings
from app.errors import SocialPublishingError


def _secret(settings: Settings) -> bytes:
    secret = settings.oauth_state_secret or settings.internal_service_token or settings.linkedin_client_secret
    if not secret:
        raise SocialPublishingError("oauth_state_secret_missing", "Set SOCIAL_PUBLISHING_OAUTH_STATE_SECRET or INTERNAL_SERVICE_TOKEN before connecting LinkedIn.", 500)
    return secret.encode("utf-8")


def create_state(settings: Settings, account_id: str, user_id: str) -> str:
    payload = {"account_id": account_id, "user_id": user_id, "nonce": str(uuid.uuid4()), "iat": int(time.time())}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_secret(settings), raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw + b"." + signature).decode("utf-8")


def verify_state(settings: Settings, state: str, max_age_seconds: int = 900) -> dict:
    try:
        decoded = base64.urlsafe_b64decode(state.encode("utf-8"))
        raw, signature = decoded.rsplit(b".", 1)
    except Exception as exc:
        raise SocialPublishingError("invalid_oauth_state", "LinkedIn OAuth state is invalid.", 400) from exc
    expected = hmac.new(_secret(settings), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise SocialPublishingError("invalid_oauth_state", "LinkedIn OAuth state signature is invalid.", 400)
    payload = json.loads(raw.decode("utf-8"))
    if int(time.time()) - int(payload.get("iat", 0)) > max_age_seconds:
        raise SocialPublishingError("oauth_state_expired", "LinkedIn OAuth state expired. Please connect again.", 400)
    return payload

