# CreditFlow Content Service

FastAPI service for generated and manually authored content.

## Responsibilities

- Stores drafts, approved posts, published posts, and soft-deleted content.
- Maintains immutable `content_versions` rows on create/update/status changes.
- Accepts optional `image_url` or local `image_asset_ref`.
- Supports multipart image upload for user-supplied post images.
- Consumes `ai.generation_completed` and creates a draft when the generation is for a post/social content prompt.
- Publishes `content.created` and `content.updated`.
- Enforces account-scoped access from gateway principal headers.
- Allows team members to create/edit drafts, while only `Owner` and `TenantAdmin` can approve or publish.

## Main endpoints

- `POST /drafts` - create a draft.
- `GET /drafts` - list active drafts for the current account.
- `GET /items` - list active content, optionally filtered by `status`.
- `GET /items/{content_id}` - fetch one content item in the current account.
- `PATCH /items/{content_id}` - edit draft/approved content and create a new version.
- `DELETE /items/{content_id}` - soft-delete content.
- `POST /items/{content_id}/status` - server-side status transition.
- `POST /items/{content_id}/approve` - approve content for scheduling/publishing.
- `POST /items/{content_id}/publish` - mark content as published.
- `GET /items/{content_id}/versions` - list edit history.
- `POST /items/{content_id}/image` - multipart manual image upload.

## Run locally

```powershell
cd content_service
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --port 8003
```

The gateway already proxies `/content/*` to `GATEWAY_CONTENT_SERVICE_URL`.