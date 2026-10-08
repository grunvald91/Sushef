FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m -u 10001 sushef
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
USER sushef
# First migrate the persisted database; never silently recreate/reset a volume.
CMD ["sh", "-c", "alembic upgrade head && exec python -m sushef"]
