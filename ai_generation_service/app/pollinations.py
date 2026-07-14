from random import randint
from urllib.parse import quote, urlencode

import httpx

from app.config import Settings
from app.errors import GenerationError


class PollinationsImageClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build_image_url(self, prompt: str, seed: int) -> str:
        base_url = self.settings.pollinations_image_base_url.rstrip("/")
        params = {
            "model": self.settings.image_generation_model,
            "width": str(self.settings.image_generation_width),
            "height": str(self.settings.image_generation_height),
            "seed": str(seed),
            "nologo": "true",
        }
        return f"{base_url}/{quote(prompt, safe='')}?{urlencode(params)}"

    async def generate(self, prompt: str) -> dict[str, str | int]:
        seed = randint(1, 2_147_483_647)
        image_url = self.build_image_url(prompt, seed)
        headers = {}
        if self.settings.pollinations_api_key:
            headers["Authorization"] = f"Bearer {self.settings.pollinations_api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.settings.image_generation_timeout_seconds, follow_redirects=True) as client:
                response = await client.get(image_url, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GenerationError("image_provider_failed", "Pollinations image generation failed.", 502) from exc

        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            raise GenerationError("image_provider_invalid_response", "Pollinations did not return an image.", 502)

        return {
            "image_url": image_url,
            "seed": seed,
            "width": self.settings.image_generation_width,
            "height": self.settings.image_generation_height,
        }
