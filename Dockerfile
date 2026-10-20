# Stage 1: build the React UI.
FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/ ./
RUN npm run build

# Stage 2: the API, which also serves the built UI on one port (7860).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    MODEL_CACHE_DIR=/home/careflow/models

# LightGBM needs the OpenMP runtime, which the slim image does not ship.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user.
RUN useradd --create-home --uid 1000 careflow
WORKDIR /home/careflow/app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=careflow:careflow alembic.ini pyproject.toml ./
COPY --chown=careflow:careflow alembic ./alembic
COPY --chown=careflow:careflow app ./app
COPY --chown=careflow:careflow simulator ./simulator
COPY --chown=careflow:careflow knowledge ./knowledge
COPY --chown=careflow:careflow docker/entrypoint.sh ./entrypoint.sh
# The dashboard shows the latest evaluation results (FR-32); only the result files are shipped.
COPY --chown=careflow:careflow eval/results ./eval/results
COPY --chown=careflow:careflow --from=ui /ui/dist ./ui/dist

USER careflow
# The demo uses the local retriever (render.yaml, D-67). To serve the neural embedding and
# re-ranking models instead, bake them in with --build-arg PRELOAD_MODELS=true so cold starts
# do not download them.
ARG PRELOAD_MODELS=false
RUN if [ "$PRELOAD_MODELS" = "true" ]; then python -m app.rag.preload; fi

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/api/v1/health')"
ENTRYPOINT ["sh", "./entrypoint.sh"]
