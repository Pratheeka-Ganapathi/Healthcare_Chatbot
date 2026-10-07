# Backend image for Render (or any Docker host). Multi-stage, slim, no torch.
# The embedding model and the MedlinePlus demo cache are baked in at image build time.
# The database is PostgreSQL with pgvector, reached through DATABASE_URL. The RAG index
# lives there: built on first start (about 5 seconds), then only when the docs change.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    FASTEMBED_CACHE_PATH=/app/models \
    HEALTH_CACHE_DIR=/app/cache/medlineplus
WORKDIR /app
COPY server/pyproject.toml server/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY server/src ./src
COPY server/data ./data
RUN uv sync --frozen --no-dev
RUN uv run --no-sync clinic-prewarm-embedder
# Pre-warm is best effort: a network hiccup at build time must not fail the image.
RUN uv run --no-sync clinic-prewarm-health || echo "MedlinePlus pre-warm skipped"

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build --chown=app /app /app
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/app/models \
    HEALTH_CACHE_DIR=/app/cache/medlineplus \
    DATA_DIR=/app/data
USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn clinic_bot.api.app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
