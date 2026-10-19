FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    MODEL_CACHE_DIR=/home/careflow/models

# Hugging Face Spaces runs containers as uid 1000.
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

USER careflow
# Bake the multilingual embedding and re-ranking models into the image so cold starts
# do not download them (docs §12). Skipped with --build-arg PRELOAD_MODELS=false.
ARG PRELOAD_MODELS=true
RUN if [ "$PRELOAD_MODELS" = "true" ]; then python -m app.rag.preload; fi

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/api/v1/health')"
ENTRYPOINT ["sh", "./entrypoint.sh"]
