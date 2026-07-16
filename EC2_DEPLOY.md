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

If a build fails with `No space left on device`, clean partial Docker build layers and try again:

```bash
docker system prune -af
docker builder prune -af
docker volume prune -f
COMPOSE_PARALLEL_LIMIT=1 docker compose -f docker-compose.yml up -d --build
```

The scraper Docker image intentionally uses `scraper_service/requirements.docker.txt`, which omits the heavy Crawl4AI browser stack for small EC2 disks. The service still works through its HTTP/BeautifulSoup fallback. Use the local `scraper_service/requirements.txt` if you specifically want full Crawl4AI locally or on a larger server.

Before rebuilding on EC2, confirm the updated scraper Dockerfile is actually on the server:

```bash
grep -n "requirements.docker" scraper_service/Dockerfile
ls scraper_service/requirements.docker.txt
```

If that grep prints nothing, the server still has the old Dockerfile and will try to install the huge Crawl4AI stack again. Copy or pull the latest files first.

If Docker still fails while exporting images, check disk usage:

```bash
df -h
sudo du -h --max-depth=1 /var/lib/docker 2>/dev/null | sort -h
```

On small EC2 root volumes, expanding EBS to 30 GB or more is usually the cleanest fix. After increasing the EBS volume in AWS, run this on Ubuntu to grow the filesystem:

```bash
lsblk
sudo growpart /dev/xvda 1
sudo resize2fs /dev/xvda1
df -h
```

If your disk device is `/dev/nvme0n1`, use:

```bash
sudo growpart /dev/nvme0n1 1
sudo resize2fs /dev/nvme0n1p1
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
