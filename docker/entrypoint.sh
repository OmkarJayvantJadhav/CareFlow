#!/bin/sh
# Migrate, seed an empty database, then serve the API.
set -e
alembic upgrade head
python -m simulator seed --if-empty
exec uvicorn app.api.main:app --host 0.0.0.0 --port "${PORT:-7860}"
