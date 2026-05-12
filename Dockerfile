FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    IPA_LABELER_DATA_DIR=/data \
    HF_HOME=/app/.cache/huggingface \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Non-root user (matches deployment.yaml runAsNonRoot: true).
# Owns /app and /data so the seed copy + uploads work even with a fresh PVC.
RUN groupadd --system --gid 1000 app \
 && useradd  --system --uid 1000 --gid 1000 --home /app app \
 && mkdir -p /data /app/.cache/huggingface \
 && chown -R app:app /app /data
USER app

# Bake faster-whisper tiny.en weights into the image so the first
# /api/clips/<id>/transcribe call doesn't have to download from HF.
# Runs as 'app' so the cache files are readable by the runtime user.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('tiny.en', device='cpu', compute_type='int8')"

EXPOSE 8080

# Phase 2: storage is Postgres. Multi-worker is safe with the new endpoints,
# but we keep -w 1 for now since the PVC at /data is still RWO and a single
# pod is more than enough for this workload.
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8080", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "app:app"]
