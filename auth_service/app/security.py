import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str, rounds: int) -> str:
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def random_token_urlsafe(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def random_numeric_otp(length: int) -> str:
    floor = 10 ** (length - 1)
    ceiling = (10**length) - 1
    return str(secrets.randbelow(ceiling - floor + 1) + floor)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def expires_in(seconds: int) -> datetime:
    return utcnow() + timedelta(seconds=seconds)