#!/bin/sh
# Migrate, seed an empty database, load the knowledge base if it changed, then serve the API.
set -e
alembic upgrade head
python -m simulator seed --if-empty
python -m app.rag.ingest --if-needed
exec uvicorn app.api.main:app --host 0.0.0.0 --port "${PORT:-7860}" --proxy-headers --forwarded-allow-ips="*"
