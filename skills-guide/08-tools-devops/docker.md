# Docker

## 30-second answer
Docker packages an application with its runtime, libraries and configuration into an **image** that runs the same everywhere as an isolated **container**. Both my apps ship as **one multi-stage Docker image**: a **Node stage builds the React UI**, and a slim **Python stage** runs the FastAPI API and serves the built UI on one port (7860) — running as a **non-root user** with a **HEALTHCHECK**. CareFlow's container migrates the database, seeds demo data, loads the knowledge base and starts Uvicorn; **Docker Compose** runs it locally with a **pgvector Postgres** service. MedVision's image **downloads the model from a GitHub Release and verifies SHA-256 checksums at build time**, and contains **no TensorFlow** — only ONNX Runtime. CI builds both images and smoke-tests them.

---

## Basics you must know

### Concepts
| Term | Meaning |
|---|---|
| **Image** | Read-only template made of layers (built from a Dockerfile) |
| **Container** | A running instance of an image (isolated process with its own filesystem, network) |
| **Layer** | Result of one instruction; cached and reused |
| **Registry** | Stores images (Docker Hub, GHCR) |
| **Volume** | Persistent data outside the container's filesystem |
| **Container vs VM** | Containers share the host kernel → lighter, start in seconds |

### Dockerfile instructions
`FROM`, `WORKDIR`, `COPY`, `RUN`, `ENV`, `ARG`, `EXPOSE`, `USER`, `HEALTHCHECK`, `CMD`, `ENTRYPOINT`.
- `CMD` = default command (overridable); `ENTRYPOINT` = fixed executable.
- `ARG` = build-time variable; `ENV` = runtime variable.

### Best practices
1. **Multi-stage builds** — build tools in one stage, copy only results into a small final image.
2. **Layer caching** — copy dependency files (`requirements.txt`, `package-lock.json`, `uv.lock`) and install *before* copying source code, so code changes don't reinstall dependencies.
3. **Slim base images** (`python:3.11-slim`, `node:22-slim`).
4. **Run as non-root** (`USER`).
5. **`.dockerignore`** — keep `node_modules`, `.git`, data, `.env` out of the build context.
6. **HEALTHCHECK** so orchestrators know if the app is healthy.
7. One process per container; configuration via environment variables; no secrets baked into images.
8. `exec` the server in entrypoint scripts so it receives signals (PID 1).

### Commands
```bash
docker build -t careflow .
docker run --rm -p 8000:8000 --env-file .env careflow
docker ps / docker logs -f <id> / docker exec -it <id> sh
docker images / docker system prune
docker compose up --build / docker compose down -v
```

### Docker Compose
YAML describing several services (app + database), networks, volumes, `depends_on` with health conditions.

---

## How I used it in CareFlow

### `Dockerfile` (two stages)
```dockerfile
# Stage 1: build the React UI
FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund                  # cached unless dependencies change
COPY ui/ ./
RUN npm run build

# Stage 2: API, which also serves the UI
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=7860 \
    EMBEDDING_BACKEND=local RERANKER_BACKEND=local \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*   # OpenMP for LightGBM
RUN useradd --create-home --uid 1000 careflow
WORKDIR /home/careflow/app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY --chown=careflow:careflow alembic.ini pyproject.toml ./
COPY --chown=careflow:careflow alembic ./alembic
COPY --chown=careflow:careflow app ./app
...
COPY --chown=careflow:careflow --from=ui /ui/dist ./ui/dist
USER careflow
ARG PRELOAD_MODELS=false
RUN if [ "$PRELOAD_MODELS" = "true" ]; then python -m app.rag.preload; fi    # optional: bake in neural models
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/api/v1/health')"
ENTRYPOINT ["sh", "./entrypoint.sh"]
```
- **One thread for numeric libraries** (D-138): the free instance has a fraction of one CPU; more threads only compete.
- **Local retrieval models by default** (D-135): fits 512 MB; a service once downloaded the neural models at start-up and never opened its port.

### `docker/entrypoint.sh`
```sh
set -e
alembic upgrade head                 # migrate
python -m app.manage prepare         # demo seed (demo mode) + first admin from env
timeout 600 python -m app.rag.ingest --if-needed || echo "...starting the server anyway"   # never block start-up (D-138)
exec uvicorn app.api.main:app --host 0.0.0.0 --port "${PORT:-7860}" --proxy-headers --forwarded-allow-ips="*"
```

### `docker-compose.yml`
```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment: { POSTGRES_USER: careflow, POSTGRES_PASSWORD: careflow, POSTGRES_DB: careflow }
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck: { test: ["CMD-SHELL", "pg_isready -U careflow -d careflow"], interval: 3s, retries: 20 }
  api:
    build: .
    environment: { DATABASE_URL: postgresql+psycopg://careflow:careflow@db:5432/careflow, DEMO_MODE: "true", PORT: "8000" }
    env_file: [{ path: .env, required: false }]
    ports: ["8000:8000"]
    depends_on: { db: { condition: service_healthy } }
volumes: { pgdata: {} }
```
`cp .env.example .env && docker compose up --build` → app on http://localhost:8000.

## How I used it in MedVision AI

### `Dockerfile`
```dockerfile
FROM node:24-slim AS frontend
... npm ci && npm run build

FROM python:3.12-slim AS runtime
ENV UV_COMPILE_BYTECODE=1 UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir uv==0.11.32 && useradd --create-home --uid 1000 app
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project       # exact locked deps, cached layer
COPY backend/app ./app
ARG MODEL_BASE_URL=https://github.com/OmkarJayvantJadhav/MedVisionAI/releases/download/model-v2.2.0
USER app
RUN python -m app.inference.download --base-url "$MODEL_BASE_URL" --dest /app/models   # fails on checksum mismatch
COPY --from=frontend --chown=app:app /src/frontend/dist /app/static
ENV MEDVISION_MODEL_DIR=/app/models MEDVISION_STATIC_DIR=/app/static PORT=7860
HEALTHCHECK ... /api/v1/health
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port \"$PORT\" --no-access-log"]
```
- **No TensorFlow** in the runtime image — ONNX Runtime + NumPy + Pillow only.
- **Model verified at build time** — a corrupted or tampered model breaks the build, not production.
- Port 7860 and uid 1000 come from its first host, Hugging Face Spaces.
- Measured: ~829 MB image, ~170 MB memory at runtime, p95 `/predict` 28 ms locally (D43).
- `docker compose up --build` → http://localhost:7860. `make docker-build`, `make docker-run`, `make smoke`.

### CI
- CareFlow: builds the image and runs a Python one-liner inside it to check the LightGBM model loads and `ui/dist/index.html` exists.
- MedVision: Buildx with **GitHub Actions cache**, reports image size (warns over 1 GB), runs the container and executes `.github/scripts/smoke_test.py` (ready, home page, predict, explain, non-skin and grainy images rejected, p95 latency).

---

## Interview questions

**Q: Image vs container?**
An image is the read-only template; a container is a running instance of it with a writable layer.

**Q: Why multi-stage builds?**
Node and build tools are needed only to build the UI. The final image keeps just Python, the app and the built static files — smaller and with less attack surface.

**Q: How do you make builds fast?**
Order layers from least to most frequently changed: copy lock files and install dependencies first, then copy source; use BuildKit cache in CI.

**Q: Why run as non-root?**
If the app is compromised, the attacker doesn't get root in the container — basic defence in depth.

**Q: What does HEALTHCHECK do?**
Docker periodically runs the command; failures mark the container unhealthy so platforms can restart it or stop routing traffic.

**Q: Why `exec` in the entrypoint?**
So Uvicorn replaces the shell as PID 1 and receives SIGTERM directly for graceful shutdown.

**Q: Where do secrets go?**
Environment variables provided by the platform (Render) or a `.env` file locally that's git-ignored — never in the image.
