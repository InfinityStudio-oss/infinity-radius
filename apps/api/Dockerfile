FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg[binary]/asyncpg wheels and building any packages
# that need compilation — kept minimal, removed from the final layer.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir -e .

# Railway injects $PORT at runtime; never hardcode a port here.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
