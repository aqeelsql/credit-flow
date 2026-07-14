from decimal import Decimal
import json
import unittest

import httpx

from app.config import Settings
from app.errors import GenerationError
from app.openrouter import OpenRouterClient
from app.redis_state import GenerationRedis
from app.usage import UsageQuotaClient


class OpenRouterClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_emits_text_and_final_usage(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertTrue(payload["stream"])
            self.assertNotIn("usage", payload)
            body = "\n".join(
                [
                    ': OPENROUTER PROCESSING',
                    'data: {"choices":[{"delta":{"content":"Hello "}}]}',
                    'data: {"choices":[{"delta":{"content":"world"}}]}',
                    'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5,"cost":0.001}}',
                    'data: [DONE]',
                    '',
                ]
            )
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

        settings = Settings(
            _env_file=None,
            openrouter_api_key="test-key",
            openrouter_model="test/text-model",
        )
        client = OpenRouterClient(settings, httpx.MockTransport(handler))
        chunks = [chunk async for chunk in client.stream("Say hello")]

        self.assertEqual("".join(chunk.text for chunk in chunks), "Hello world")
        self.assertEqual(chunks[-1].total_tokens, 5)
        self.assertEqual(chunks[-1].cost, Decimal("0.001"))

    async def test_midstream_provider_error_is_raised(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            body = 'data: {"error":{"code":429,"message":"Rate limited"},"choices":[]}\n\n'
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

        settings = Settings(
            _env_file=None,
            openrouter_api_key="test-key",
            openrouter_model="test/text-model",
        )
        client = OpenRouterClient(settings, httpx.MockTransport(handler))
        with self.assertRaisesRegex(GenerationError, "OpenRouter stopped"):
            _ = [chunk async for chunk in client.stream("Fail")]

    async def test_falls_back_before_any_text_is_emitted(self):
        requested_models = []

        async def handler(request: httpx.Request) -> httpx.Response:
            model = json.loads(request.content)["model"]
            requested_models.append(model)
            if model == "test/primary":
                return httpx.Response(429, json={"error": {"message": "temporarily unavailable"}})
            body = 'data: {"choices":[{"delta":{"content":"fallback worked"}}]}\n\ndata: [DONE]\n\n'
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

        settings = Settings(
            _env_file=None,
            openrouter_api_key="test-key",
            openrouter_model="test/primary",
            openrouter_fallback_model="openrouter/free",
        )
        chunks = [
            chunk
            async for chunk in OpenRouterClient(settings, httpx.MockTransport(handler)).stream("Try fallback")
        ]
        self.assertEqual(requested_models, ["test/primary", "openrouter/free"])
        self.assertEqual("".join(chunk.text for chunk in chunks), "fallback worked")

    def test_missing_provider_configuration_is_rejected(self):
        client = OpenRouterClient(Settings(_env_file=None, openrouter_api_key="", openrouter_model=""))
        with self.assertRaises(GenerationError) as raised:
            client.validate_configuration()
        self.assertEqual(raised.exception.code, "provider_not_configured")


class UsageQuotaClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_allows_generation_only_when_usage_service_allows_it(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["x-internal-token"], "internal-test")
            return httpx.Response(200, json={"allowed": True, "reservation_id": "res_1"})

        settings = Settings(_env_file=None, internal_service_token="internal-test")
        result = await UsageQuotaClient(settings, httpx.MockTransport(handler)).check(
            "acct_1", "user_1", "test/model", 512, "req_1"
        )
        self.assertTrue(result["allowed"])

    async def test_denied_quota_is_rejected(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"allowed": False})

        client = UsageQuotaClient(Settings(_env_file=None), httpx.MockTransport(handler))
        with self.assertRaises(GenerationError) as raised:
            await client.check("acct_1", "user_1", "test/model", 512, None)
        self.assertEqual(raised.exception.code, "quota_exceeded")


class RedisQuotaTests(unittest.IsolatedAsyncioTestCase):
    async def test_reserves_quota_atomically(self):
        class FakeRedis:
            async def eval(self, *args):
                return 99

        state = GenerationRedis(Settings(_env_file=None, daily_request_limit=100))
        state._client = FakeRedis()
        self.assertEqual(await state.reserve_daily_quota("acct_1"), 99)

    async def test_rejects_exhausted_quota(self):
        class FakeRedis:
            async def eval(self, *args):
                return -1

        state = GenerationRedis(Settings(_env_file=None, daily_request_limit=100))
        state._client = FakeRedis()
        with self.assertRaises(GenerationError) as raised:
            await state.reserve_daily_quota("acct_1")
        self.assertEqual(raised.exception.code, "quota_exceeded")


if __name__ == "__main__":
    unittest.main()
