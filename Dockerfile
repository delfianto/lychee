# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.14-slim-trixie
ARG NODE_IMAGE=node:24-trixie-slim
ARG BUN_IMAGE=oven/bun:1.4.4
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.5

FROM ${BUN_IMAGE} AS bun
FROM ${UV_IMAGE} AS uv

# Node runs Vite+ and Vue's type checker; Bun installs the locked dependencies.
FROM ${NODE_IMAGE} AS frontend
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /build/frontend
COPY frontend/package.json frontend/bun.lock ./
RUN --mount=type=cache,target=/root/.bun/install/cache bun install --frozen-lockfile
COPY frontend/ ./
ENV VITE_USE_MOCKS=false
RUN bun run build

FROM ${PYTHON_IMAGE} AS backend
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

FROM ${PYTHON_IMAGE} AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data /library
ENV PATH="/app/backend/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    DATABASE_URL=sqlite:////data/lychee.db \
    STORAGE_PATH=/library \
    LOG_LEVEL=INFO \
    LOG_FORMAT=json
WORKDIR /app/backend
COPY --from=backend /app/backend/.venv/ ./.venv/
COPY backend/src/ ./src/
COPY backend/alembic/ ./alembic/
COPY backend/alembic.ini ./alembic.ini
COPY LICENSE /app/LICENSE
COPY --from=frontend /build/frontend/dist/ /app/frontend/
COPY docker/deployment.py ./deployment.py
ARG LYCHEE_REPOSITORY=https://github.com/delfianto/lychee
ARG LYCHEE_REVISION=development
ARG LYCHEE_VERSION=development
LABEL org.opencontainers.image.title="Lychee" \
      org.opencontainers.image.source="${LYCHEE_REPOSITORY}" \
      org.opencontainers.image.revision="${LYCHEE_REVISION}" \
      org.opencontainers.image.version="${LYCHEE_VERSION}" \
      org.opencontainers.image.licenses="MIT"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
# Task ownership and the SSE broker are process-local: keep one Uvicorn worker.
CMD ["python", "-m", "uvicorn", "deployment:app", "--host", "0.0.0.0", "--port", "8000"]
