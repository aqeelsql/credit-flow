# CreditFlow EC2 Docker Deployment

This deployment uses `docker-compose.ec2.yml` to run the frontend, API Gateway, PostgreSQL, Redis, RabbitMQ, MongoDB, and the implemented backend services.

## 1. Prepare EC2

Install Docker and the Compose plugin on the EC2 instance, then copy this project to the server.

Open inbound security-group ports as needed:

- `3000` frontend
- `8000` API Gateway
- `8005` LinkedIn callback, if LinkedIn redirects directly to the service
- `15672` RabbitMQ management, optional and should be restricted to your IP

## 2. Configure `.env`

On EC2, update the root `.env` values that point to localhost from the browser perspective.

Example:

```env
NEXT_PUBLIC_API_BASE_URL=http://YOUR_EC2_PUBLIC_IP_OR_DOMAIN:8000
NEXT_PUBLIC_USE_LOCAL_AUTH=false
NEXT_PUBLIC_USE_MOCK_AI=false
FRONTEND_BASE_URL=http://YOUR_EC2_PUBLIC_IP_OR_DOMAIN:3000
LINKEDIN_REDIRECT_URI=http://YOUR_EC2_PUBLIC_IP_OR_DOMAIN:8005/linkedin/callback
POSTGRES_USER=creditflow
POSTGRES_PASSWORD=replace-with-strong-password
POSTGRES_DB=creditflow
RABBITMQ_DEFAULT_USER=creditflow
RABBITMQ_DEFAULT_PASS=replace-with-strong-password
```

Keep your real API keys in `.env`; it is passed at container runtime and is not copied into images by the root `.dockerignore`.

## 3. Build and start

```bash
docker compose -f docker-compose.ec2.yml up -d --build
```

Check logs:

```bash
docker compose -f docker-compose.ec2.yml logs -f api_gateway frontend social_publishing_service
```

Stop everything:

```bash
docker compose -f docker-compose.ec2.yml down
```

Stop and remove local databases too:

```bash
docker compose -f docker-compose.ec2.yml down -v
```

## 4. LinkedIn app settings

In the LinkedIn Developer Portal, the redirect URL must exactly match:

```text
http://YOUR_EC2_PUBLIC_IP_OR_DOMAIN:8005/linkedin/callback
```

If you put the API behind Nginx/HTTPS later, change both LinkedIn Developer Portal and `.env` to the HTTPS callback URL.

