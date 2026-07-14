from app.config import Settings
from app.database import Database
from app.events import EventPublisher
from app.errors import GenerationError
from app.openrouter import OpenRouterClient
from app.pollinations import PollinationsImageClient
from app.repository import GenerationRepository
from app.schemas import StartImageGenerationRequest


def build_image_prompt(source_text: str, prompt_override: str | None = None) -> str:
    if prompt_override and prompt_override.strip():
        return prompt_override.strip()
    trimmed = source_text.strip()[:1800]
    return (
        "Create a polished professional LinkedIn post visual inspired by this generated text. "
        "Use a modern SaaS editorial style, clean composition, premium lighting, no readable text, "
        "no logos, no watermarks. Visual brief: "
        f"{trimmed}"
    )


def build_image_prompt_instruction(source_text: str) -> str:
    trimmed = source_text.strip()[:3500]
    return (
        "Convert this generated social post into one strong text-to-image prompt for a LinkedIn post visual.\n"
        "Rules:\n"
        "- Describe the actual visual scene, objects, composition, mood, palette, and style.\n"
        "- Use concrete visual nouns from the post.\n"
        "- Do not copy the post. Do not include hashtags.\n"
        "- Do not ask for readable text, letters, logos, watermarks, UI labels, or brand names inside the image.\n"
        "- Keep it under 90 words.\n"
        "- Output only the image prompt, no explanation.\n\n"
        f"Generated post:\n{trimmed}"
    )


class ImageGenerationManager:
    def __init__(self, settings: Settings, database: Database, events: EventPublisher):
        self.settings = settings
        self.database = database
        self.events = events
        self.text_provider = OpenRouterClient(settings)

    async def _build_visual_prompt(self, source_text: str, prompt_override: str | None) -> str:
        if prompt_override and prompt_override.strip():
            return prompt_override.strip()
        try:
            visual_prompt = await self.text_provider.complete(
                build_image_prompt_instruction(source_text),
                model=self.settings.image_prompt_model or self.settings.openrouter_model,
                max_tokens=220,
            )
        except GenerationError:
            return build_image_prompt(source_text)
        visual_prompt = " ".join(visual_prompt.split()).rstrip(" .")
        return (
            f"{visual_prompt}. Professional LinkedIn editorial visual, modern SaaS aesthetic, "
            "clean composition, premium lighting, no readable text, no logos, no watermarks."
        )[:1800]

    async def generate(self, body: StartImageGenerationRequest) -> dict:
        if self.settings.image_generation_provider.lower() != "pollinations":
            raise GenerationError("unsupported_image_provider", "Only Pollinations image generation is configured.", 400)
        source_text = body.source_text.strip()
        prompt = await self._build_visual_prompt(source_text, body.prompt)
        client = PollinationsImageClient(self.settings)

        async with self.database.transaction() as conn:
            repo = GenerationRepository(conn)
            job = await repo.create_image_job(
                account_id=body.account_id,
                user_id=body.user_id,
                source_generation_job_id=body.source_generation_job_id,
                provider=self.settings.image_generation_provider,
                model=self.settings.image_generation_model,
                prompt=prompt,
                source_text=source_text,
                width=self.settings.image_generation_width,
                height=self.settings.image_generation_height,
                seed=0,
            )

        try:
            result = await client.generate(prompt)
            async with self.database.transaction() as conn:
                job = await GenerationRepository(conn).complete_image_job(job["id"], str(result["image_url"]), int(result["seed"]))
        except GenerationError as exc:
            async with self.database.transaction() as conn:
                await GenerationRepository(conn).fail_image_job(job["id"], exc.message)
            await self._publish_failed(job, exc.message)
            raise

        await self._publish_completed(job)
        return job

    async def get(self, image_id: str) -> dict | None:
        async with self.database.acquire() as conn:
            return await GenerationRepository(conn).get_image_job(image_id)

    async def _publish_completed(self, job: dict) -> None:
        await self.events.publish("image_generation_completed", job)

    async def _publish_failed(self, job: dict, reason: str) -> None:
        await self.events.publish("image_generation_failed", {**job, "error_reason": reason})
