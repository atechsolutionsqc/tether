FROM python:3.12-slim

WORKDIR /app

# System deps (none strictly required for these wheels, kept minimal)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend

# Data directory for the SQLite database (mount a volume here to persist)
ENV ASSETTRACK_DATA=/data
RUN mkdir -p /data && \
    groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app /data

VOLUME ["/data"]

EXPOSE 8000

USER appuser
WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
