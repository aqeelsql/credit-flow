FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN crawl4ai-setup || true
COPY app ./app

EXPOSE 8012
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8012"]
