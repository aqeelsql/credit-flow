from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import httpx

from app.config import PROJECT_ROOT, Settings
from app.errors import SocialPublishingError


CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


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

    def _content_type_for_path(self, path: Path) -> str:
        return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")

    def _resolve_local_content_asset(self, asset_ref: str) -> Path:
        parsed = urlparse(asset_ref)
        if parsed.scheme != "local" or parsed.netloc != "content":
            raise SocialPublishingError("unsupported_image_asset_ref", "Attached local image asset reference is not supported.", 422)
        parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
        if len(parts) != 2:
            raise SocialPublishingError("invalid_image_asset_ref", "Attached local image asset reference is invalid.", 422)
        account_id, filename = parts
        root = Path(self.settings.content_upload_dir)
        if not root.is_absolute():
            root = PROJECT_ROOT / root
        root = root.resolve()
        path = (root / account_id / filename).resolve()
        if not str(path).lower().startswith(str(root).lower()):
            raise SocialPublishingError("invalid_image_asset_ref", "Attached local image asset escapes the upload directory.", 422)
        return path

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
            asset_ref_text = str(asset_ref)
            if asset_ref_text.startswith("local://content/"):
                path = self._resolve_local_content_asset(asset_ref_text)
            else:
                path = Path(asset_ref_text)
                if not path.is_absolute():
                    path = PROJECT_ROOT / path
            if not path.exists() or not path.is_file():
                raise SocialPublishingError("image_asset_missing", "Attached local image asset was not found.", 404)
            return path.read_bytes(), self._content_type_for_path(path)
        return None

