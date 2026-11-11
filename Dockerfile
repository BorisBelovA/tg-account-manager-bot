FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Nicosia

WORKDIR /app

# tzdata: correct local times; sqlite3: safe backups
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot

RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data /app/backups \
    && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-m", "bot.main"]
