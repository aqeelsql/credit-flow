FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

ENV FLASK_APP=app.main:app
EXPOSE 8003
CMD ["flask", "--app", "app.main:app", "run", "--host", "0.0.0.0", "--port", "8003"]
