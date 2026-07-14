import asyncio

from app.config import Settings
from app.errors import GenerationError
from app.openrouter import OpenRouterClient


async def main() -> int:
    settings = Settings()
    characters = 0
    total_tokens = None
    try:
        async for chunk in OpenRouterClient(settings).stream("Reply with exactly: OK"):
            characters += len(chunk.text)
            total_tokens = chunk.total_tokens if chunk.total_tokens is not None else total_tokens
    except GenerationError as exc:
        print(f"provider check failed: {exc.code}")
        print(f"message: {exc.message}")
        print(f"details: {exc.details}")
        return 1
    print("provider check passed")
    print(f"response characters: {characters}")
    print(f"total tokens: {total_tokens}")
    return 0 if characters else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
