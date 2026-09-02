# syntax=docker/dockerfile:1

# ---------- Stage 1: dependências ----------
FROM python:3.12-slim AS deps

ENV POETRY_VERSION=2.1.1 \
    POETRY_HOME=/opt/poetry \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# build-essential é necessário porque hdbscan e umap-learn compilam
# extensões nativas na instalação
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="$POETRY_HOME/bin:$PATH"

WORKDIR /app
COPY pyproject.toml poetry.lock* ./
RUN poetry lock --no-update 2>/dev/null || poetry lock
RUN poetry install --only main --no-root

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PORT=8000

# libpq5 é a runtime do Postgres; curl serve ao healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 decoded

COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

WORKDIR /app
COPY --chown=decoded:decoded src ./src
COPY --chown=decoded:decoded migrations ./migrations
COPY --chown=decoded:decoded alembic.ini ./
COPY --chown=decoded:decoded prefect.yaml ./

USER decoded

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/v1/health || exit 1

CMD ["uvicorn", "decoded.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--app-dir", "src", \
     "--workers", "2", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]