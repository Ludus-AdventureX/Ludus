# FastAPI service image for the Guest Simulation Alpha prototype stack
# (compose.prototype.yaml). Dependencies come from the committed uv.lock so
# the container matches local development exactly.
#
# Build context is the REPOSITORY ROOT, not services/api: the image must also
# carry method-packs/, because the server resolves a charter's
# methodContentHash from the published catalog and fails closed without it.
#
#   docker build -f services/api/Dockerfile .

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install locked runtime dependencies first so source edits reuse this layer.
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-dev

# Application source and migration toolchain (migrations run as an explicit
# command, never implicitly at import time).
COPY services/api/alembic.ini ./
COPY services/api/migrations ./migrations
COPY services/api/app ./app

# Published method catalog. app.methods.catalog probes /app/method-packs when
# METHOD_CATALOG_ROOT is unset, which is the container layout below.
COPY method-packs ./method-packs

FROM python:3.12-slim-bookworm AS runtime

RUN useradd --create-home --uid 10001 api

WORKDIR /app
COPY --from=builder --chown=api:api /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER api
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
