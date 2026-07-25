FROM python:3.12-slim

WORKDIR /app
COPY requirements.docker.txt .
RUN pip install --no-cache-dir -r requirements.docker.txt
COPY app ./app

RUN groupadd --system app && useradd --system --gid app --home-dir /app appuser && mkdir -p /app/.crawl4ai-runtime && chown -R appuser:app /app
USER appuser

EXPOSE 8012
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8012"]
