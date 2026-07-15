# CreditFlow Social Publishing Service

Service 10 handles LinkedIn OAuth, encrypted token storage, and publishing scheduled content when `content.scheduled` events arrive.

## Run locally

```powershell
cd D:\ATS\CF\social_publishing_service
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --port 8005
```

The service uses the shared root `.env`. Required values:

```env
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
LINKEDIN_REDIRECT_URI=http://localhost:8005/linkedin/callback
LINKEDIN_SCOPES=openid profile email w_member_social
SOCIAL_PUBLISHING_TOKEN_ENCRYPTION_KEY=
```

Generate the Fernet key with:

```powershell
py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Event contract

- Consumes: `content.scheduled`
- Publishes: `post.published`, `post.failed`
- DLQ routing key: `post.failed.dlq`

## API

- `GET /health`
- `GET /linkedin/status`
- `GET /linkedin/connect` returns `{ auth_url }`
- `GET /linkedin/callback` OAuth callback
- `DELETE /linkedin/disconnect`
- `GET /linkedin/jobs`

