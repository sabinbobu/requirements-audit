# API image: uv-managed install of the pinned lockfile, no dev/eval extras.
# Served by docker-compose as the `api` service; see the ops runbook in README.
FROM python:3.12-slim

# uv handles dependency resolution exactly as in dev (same uv.lock).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Layer-cache friendly: lockfile + metadata first, source after.
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev

# The demo corpus ships in the image so `POST /ingest {"corpus_dir": "corpus"}`
# works out of the box; mount ./data for the SQLite store to persist.
COPY corpus ./corpus

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "requirements_audit.api.app:app", \
     "--host", "0.0.0.0", "--port", "8000"]
