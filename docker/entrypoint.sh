#!/bin/sh
# Migrate; in demo mode seed an empty database; create the first admin if configured; load the knowledge
# base if it changed; then serve the API.
set -e
alembic upgrade head
python -m app.manage prepare
# The knowledge base must never keep the site from starting (D-138): if loading it fails or takes longer
# than 10 minutes, the server starts anyway (chat answers about documents wait for the next deployment).
timeout 600 python -m app.rag.ingest --if-needed \
    || echo "knowledge base not loaded this time (exit $?); starting the server anyway"
exec uvicorn app.api.main:app --host 0.0.0.0 --port "${PORT:-7860}" --proxy-headers --forwarded-allow-ips="*"
