from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings
from app.errors import SocialPublishingError


class TokenCipher:
    def __init__(self, settings: Settings):
        if not settings.token_encryption_key:
            raise SocialPublishingError("encryption_key_missing", "SOCIAL_PUBLISHING_TOKEN_ENCRYPTION_KEY is required before storing LinkedIn tokens.", 500)
        try:
            self._fernet = Fernet(settings.token_encryption_key.encode("utf-8"))
        except Exception as exc:
            raise SocialPublishingError("invalid_encryption_key", "SOCIAL_PUBLISHING_TOKEN_ENCRYPTION_KEY must be a valid Fernet key.", 500) from exc

    def encrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise SocialPublishingError("token_decrypt_failed", "Stored LinkedIn token could not be decrypted.", 500) from exc

