FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . .

ENV FORELI_DB_PATH=/data/foreli.db \
    FORELI_COOKIE_SECURE=1 \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data
EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
