FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    IPA_LABELER_DATA_DIR=/data \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Non-root user (matches deployment.yaml runAsNonRoot: true).
# Owns /app and /data so the seed copy + uploads work even with a fresh PVC.
RUN groupadd --system --gid 1000 app \
 && useradd  --system --uid 1000 --gid 1000 --home /app app \
 && mkdir -p /data \
 && chown -R app:app /app /data
USER app

EXPOSE 8080

# Phase 1 uses a single JSON annotations file; pin -w 1 so the in-process
# threading.Lock is sufficient for write safety. Lift to -w 2+ once Phase 2
# moves storage to Postgres.
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8080", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "app:app"]
