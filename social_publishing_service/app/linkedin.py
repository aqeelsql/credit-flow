from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.errors import SocialPublishingError


class LinkedInTransientError(Exception):
    pass


class LinkedInPermanentError(Exception):
    pass


def _raise_for_linkedin(response: httpx.Response) -> None:
    if response.status_code in {408, 425, 429, 500, 502, 503, 504}:
        raise LinkedInTransientError(f"LinkedIn transient error {response.status_code}: {response.text[:500]}")
    if response.status_code >= 400:
        raise LinkedInPermanentError(f"LinkedIn rejected request {response.status_code}: {response.text[:500]}")


class LinkedInClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def authorization_url(self, state: str) -> str:
        if not self.settings.linkedin_client_id:
            raise SocialPublishingError("linkedin_client_missing", "LINKEDIN_CLIENT_ID is required.", 500)
        params = {
            "response_type": "code",
            "client_id": self.settings.linkedin_client_id,
            "redirect_uri": self.settings.linkedin_redirect_uri,
            "scope": " ".join(self.settings.scopes),
            "state": state,
        }
        return f"{self.settings.linkedin_auth_url}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        if not self.settings.linkedin_client_id or not self.settings.linkedin_client_secret:
            raise SocialPublishingError("linkedin_credentials_missing", "LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET are required.", 500)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self.settings.linkedin_token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.settings.linkedin_redirect_uri,
                    "client_id": self.settings.linkedin_client_id,
                    "client_secret": self.settings.linkedin_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        _raise_for_linkedin(response)
        return response.json()

    async def refresh_access_token(self, refresh_token: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self.settings.linkedin_token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.settings.linkedin_client_id,
                    "client_secret": self.settings.linkedin_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        _raise_for_linkedin(response)
        return response.json()

    async def userinfo(self, access_token: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.settings.linkedin_api_base_url}/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"})
        _raise_for_linkedin(response)
        return response.json()

    async def register_image_upload(self, access_token: str, owner_urn: str) -> dict:
        body = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": owner_urn,
                "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}],
            }
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.settings.linkedin_api_base_url}/v2/assets?action=registerUpload",
                json=body,
                headers={"Authorization": f"Bearer {access_token}", "X-Restli-Protocol-Version": "2.0.0"},
            )
        _raise_for_linkedin(response)
        return response.json()["value"]

    async def upload_image_binary(self, access_token: str, upload_url: str, image_bytes: bytes, content_type: str = "application/octet-stream") -> None:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.put(upload_url, content=image_bytes, headers={"Authorization": f"Bearer {access_token}", "Content-Type": content_type})
        _raise_for_linkedin(response)

    async def create_ugc_post(self, access_token: str, owner_urn: str, text: str, asset_urn: str | None = None) -> dict:
        share_content = {"shareCommentary": {"text": text}, "shareMediaCategory": "IMAGE" if asset_urn else "NONE"}
        if asset_urn:
            share_content["media"] = [{"status": "READY", "media": asset_urn, "title": {"text": "CreditFlow generated image"}}]
        body = {
            "author": owner_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.settings.linkedin_api_base_url}/v2/ugcPosts",
                json=body,
                headers={"Authorization": f"Bearer {access_token}", "X-Restli-Protocol-Version": "2.0.0"},
            )
        _raise_for_linkedin(response)
        post_id = response.headers.get("x-restli-id") or response.headers.get("X-RestLi-Id") or ""
        return {"id": post_id, "url": f"https://www.linkedin.com/feed/update/{post_id}" if post_id else ""}

