from pathlib import Path
from urllib.parse import urljoin

import httpx

from app.config import PROJECT_ROOT, Settings
from app.errors import SocialPublishingError


class ContentClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def get_content(self, account_id: str, content_id: str) -> dict:
        headers = {"x-user-id": "social-publishing-service", "x-account-id": account_id, "x-role": "TenantAdmin"}
        if self.settings.internal_service_token:
            headers["x-internal-service-token"] = self.settings.internal_service_token
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(urljoin(self.settings.content_service_url.rstrip("/") + "/", f"items/{content_id}"), headers=headers)
        if response.status_code == 404:
            raise SocialPublishingError("content_not_found", "Scheduled content was not found.", 404)
        if response.status_code >= 400:
            raise SocialPublishingError("content_fetch_failed", f"Content Service rejected lookup ({response.status_code}).", 502)
        return response.json()

    async def fetch_image_bytes(self, content: dict) -> tuple[bytes, str] | None:
        image_url = content.get("image_url")
        asset_ref = content.get("image_asset_ref")
        if image_url and str(image_url).startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(str(image_url))
            if response.status_code >= 400:
                raise SocialPublishingError("image_fetch_failed", "Attached image URL could not be downloaded.", 502)
            return response.content, response.headers.get("content-type", "application/octet-stream")
        if asset_ref:
            path = Path(str(asset_ref))
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            if not path.exists() or not path.is_file():
                raise SocialPublishingError("image_asset_missing", "Attached local image asset was not found.", 404)
            suffix = path.suffix.lower()
            content_type = "image/png" if suffix == ".png" else "image/jpeg" if suffix in {".jpg", ".jpeg"} else "application/octet-stream"
            return path.read_bytes(), content_type
        return None

