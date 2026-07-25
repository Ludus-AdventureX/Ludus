# syntax=docker/dockerfile:1
# FastAPI service image for the Guest Simulation Alpha prototype stack
# (compose.prototype.yaml). Dependencies come from the committed uv.lock so
# the container matches local development exactly.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install locked runtime dependencies first so source edits reuse this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Application source and migration toolchain (migrations run as an explicit
# command, never implicitly at import time).
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

FROM python:3.12-slim-bookworm AS runtime

RUN useradd --create-home --uid 10001 api

WORKDIR /app
COPY --from=builder --chown=api:api /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER api
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
