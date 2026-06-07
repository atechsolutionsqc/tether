FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    TETHER_DATA=/data

# System packages — mysqldump/pg_dump needed by the backup service
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    postgresql-client \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend

# Data directory for SQLite database and uploads (mount a volume here to persist)
RUN mkdir -p /data && \
    groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app /data

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

VOLUME ["/data"]

EXPOSE 8000

USER appuser
WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
