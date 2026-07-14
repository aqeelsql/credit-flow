import base64
import json
import time
import unittest

from starlette.requests import Request

from app.auth import authenticate_request
from app.config import Settings
from app.errors import GatewayError


def encode(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def mock_token() -> str:
    payload = {
        "user_id": "usr_demo_001",
        "account_id": "local_demo",
        "role": "Owner",
        "jti": "jti_demo",
        "email": "demo@example.com",
        "exp": int(time.time()) + 300,
    }
    return f"{encode({'alg': 'HS256', 'typ': 'JWT'})}.{encode(payload)}.mock-signature"


def request_with_token(token: str) -> Request:
    return Request({"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]})


class UnexpectedRedis:
    async def is_session_revoked(self, jti: str) -> bool:
        raise AssertionError("Local mock authentication must not query session state")

    async def is_session_active(self, jti: str) -> bool:
        raise AssertionError("Local mock authentication must not query session state")


class LocalMockAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_environment_accepts_frontend_mock_token(self):
        principal = await authenticate_request(
            request_with_token(mock_token()),
            Settings(_env_file=None, environment="local"),
            UnexpectedRedis(),
        )
        self.assertEqual(principal.account_id, "local_demo")
        self.assertEqual(principal.role, "Owner")

    async def test_non_local_environment_rejects_mock_token(self):
        with self.assertRaises(GatewayError):
            await authenticate_request(
                request_with_token(mock_token()),
                Settings(_env_file=None, environment="production"),
                UnexpectedRedis(),
            )


if __name__ == "__main__":
    unittest.main()
