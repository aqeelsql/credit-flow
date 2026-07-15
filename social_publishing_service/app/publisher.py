from app.config import Settings
from app.content_client import ContentClient
from app.crypto import TokenCipher
from app.events import SocialEventBus
from app.linkedin import LinkedInClient
from app.repository import SocialRepository


def linkedin_post_url(post_id: str) -> str:
    return f"https://www.linkedin.com/feed/update/{post_id}" if post_id else ""


class PublishPipeline:
    def __init__(self, settings: Settings, cipher: TokenCipher, events: SocialEventBus):
        self.settings = settings
        self.cipher = cipher
        self.events = events
        self.linkedin = LinkedInClient(settings)
        self.content = ContentClient(settings)

    async def publish_scheduled(self, repo: SocialRepository, payload: dict) -> dict:
        account_id = str(payload.get("account_id") or "")
        content_id = str(payload.get("content_id") or "")
        scheduled_post_id = payload.get("scheduled_post_id")
        if not account_id or not content_id:
            raise ValueError("content.scheduled payload must include account_id and content_id")

        job = await repo.create_or_get_job(account_id=account_id, scheduled_post_id=str(scheduled_post_id) if scheduled_post_id else None, content_id=content_id, payload=payload)
        if job["status"] == "published":
            return dict(job)

        connection = await repo.get_connection(account_id)
        if not connection:
            raise ValueError("No connected LinkedIn account for this CreditFlow account")
        await repo.mark_job_publishing(job["id"], connection["id"])

        content = await self.content.get_content(account_id, content_id)
        text = str(content.get("body") or "").strip()
        if not text:
            raise ValueError("Scheduled content body is empty")

        if self.settings.mock_mode:
            fake_id = f"urn:li:ugcPost:mock-{job['id']}"
            published = await repo.mark_job_published(job["id"], fake_id, linkedin_post_url(fake_id))
            await self.events.publish("post.published", {**dict(published), "mock": True})
            return dict(published)

        access_token = self.cipher.decrypt(connection["encrypted_access_token"])
        owner_urn = connection.get("linkedin_member_urn") or f"urn:li:person:{connection['linkedin_sub']}"
        image_bytes = await self.content.fetch_image_bytes(content)
        asset_urn = None
        if image_bytes:
            media = await repo.create_media(job_id=job["id"], content_id=content_id, source_url=content.get("image_url"), image_asset_ref=content.get("image_asset_ref"))
            registered = await self.linkedin.register_image_upload(access_token, owner_urn)
            upload = registered["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]
            upload_url = upload["uploadUrl"]
            asset_urn = registered["asset"]
            await self.linkedin.upload_image_binary(access_token, upload_url, image_bytes[0], image_bytes[1])
            await repo.mark_media_uploaded(media["id"], asset_urn, upload_url)

        result = await self.linkedin.create_ugc_post(access_token, owner_urn, text, asset_urn)
        published = await repo.mark_job_published(job["id"], result["id"], result["url"])
        await self.events.publish("post.published", {**dict(published), "content_title": payload.get("content_title")})
        return dict(published)

