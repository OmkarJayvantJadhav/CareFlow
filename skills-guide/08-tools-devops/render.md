# Render

## 30-second answer
Render is a cloud platform (PaaS) that builds and runs web services, static sites, background workers, cron jobs and managed Postgres straight from a Git repository — including **Docker-based services** — with automatic deploys and HTTPS. **Both my live demos run on Render's free web-service tier as Docker containers**, defined as code in a **`render.yaml` Blueprint**: CareFlow (Singapore region, deploys from `develop`, database on **Neon**) and a second CareFlow service for a hospital-style site, and MedVision (deploys `main` **only after GitHub CI checks pass**). I designed both to fit the free tier's limits: **512 MB RAM, a fraction of one CPU, and sleep after 15 idle minutes**.

---

## Basics you must know

### Service types
Web service (HTTP, gets a public URL), private service, background worker, cron job, static site, managed PostgreSQL, Redis-compatible key-value store.

### Deploy options
- **Native runtimes** (Python, Node, …) with build and start commands.
- **Docker** — Render builds your Dockerfile.
- **Prebuilt image** from a registry.

### Blueprints (`render.yaml`)
Infrastructure as code: services, plans, regions, branches, env vars, health checks. Create with **New → Blueprint**; Render asks for values marked `sync: false` (secrets).

### Key settings
| Setting | Meaning |
|---|---|
| `branch` | Git branch to deploy |
| `autoDeploy` / `autoDeployTrigger: checksPass` | Deploy on every push, or only after CI checks pass |
| `healthCheckPath` | Render waits for this to return 2xx before switching traffic (zero-downtime deploys) |
| `envVars` | `value` (plain), `sync: false` (secret entered in the dashboard), `generateValue: true` (random secret) |
| `PORT` | The port your app must listen on |

### Free tier realities
Spins down after ~15 minutes idle; the next request "cold starts" (~1 minute); limited RAM/CPU; good for demos, not production.

### Render vs alternatives
| Platform | Best for |
|---|---|
| **Render** | Full apps / Docker / background work, simple Heroku-like experience |
| Vercel / Netlify | Frontends and serverless functions |
| Railway, Fly.io | Similar PaaS; Fly runs containers close to users |
| Hugging Face Spaces | ML demos (Gradio/Streamlit/Docker) |
| AWS/GCP/Azure | Full control and scale, more ops work |

---

## How I used it

### CareFlow (`render.yaml`, `docs/DEPLOY.md`)
```yaml
services:
  - type: web
    name: careflow
    runtime: docker
    plan: free
    region: singapore           # closest to Maharashtra users
    branch: develop
    autoDeploy: true
    healthCheckPath: /api/v1/health
    envVars:
      - { key: PORT, value: "7860" }
      - { key: DEMO_MODE, value: "true" }
      - { key: DEMO_NOTICE, value: "false" }
      - { key: EMBEDDING_BACKEND, value: local }    # neural models need ~1 GB; free tier has 512 MB
      - { key: RERANKER_BACKEND, value: local }
      - { key: DATABASE_URL, sync: false }          # Neon connection string
      - { key: GROQ_API_KEY, sync: false }
      - { key: GEMINI_API_KEY, sync: false }
      - { key: AUTH_SECRET, generateValue: true }   # signs tokens and receipt codes
      - { key: DATA_KEY, generateValue: true }      # encrypts phone numbers (keep when rotating AUTH_SECRET)
```
- **Database:** Neon's free Postgres with pgvector (region Singapore), kept separate from the Render service; `docs/DEPLOY.md` walks through both. The app accepts Neon's `postgresql://` URL and disables prepared statements for its pooler. Neon suspends idle compute, so the first query after a pause takes a few seconds.
- **Two deployments of the same code:** the public demo (`careflow-zy87.onrender.com`, demo roles, reset) and a hospital site (`omkar-general-hospital.onrender.com`, `DEMO_MODE=false`, real accounts, its own homepage).
- **Designed for the free tier:**
  - Local retrieval models (fit in 512 MB) — what every published retrieval number was measured with.
  - One thread for NumPy/BLAS/OpenMP (`OMP_NUM_THREADS=1` etc.) — a fraction of a CPU gains nothing from more threads.
  - Knowledge-base loading at start-up wrapped in `timeout 600` so the port always opens (D-138).
  - Background jobs (reminders, outbox) resume after the instance wakes; messages wait while it sleeps (D-123).
- `/api/v1/health` returns `"degraded"` when no LLM key is set — useful in Render's dashboard.

### MedVision AI (`render.yaml`, `docs/deploy.md`)
```yaml
services:
  - type: web
    name: medvision-ai
    runtime: docker
    plan: free
    repo: https://github.com/OmkarJayvantJadhav/MedVisionAI
    branch: main
    dockerfilePath: ./Dockerfile
    healthCheckPath: /api/v1/health
    autoDeployTrigger: checksPass        # deploy only when GitHub CI passed
    envVars:
      - { key: MEDVISION_INFERENCE_THREADS, value: "1" }
      - { key: OMP_NUM_THREADS, value: "1" }
      - { key: OPENBLAS_NUM_THREADS, value: "1" }
      - { key: MEDVISION_RATE_LIMIT_PER_MINUTE, value: "60" }   # shared ceiling behind Render's proxy
```
- **Why Render (decision D44):** Hugging Face started requiring PRO for Docker Spaces on free CPU; Render's free tier builds Dockerfiles from GitHub with no card. Letting Render deploy on passing checks means **no deploy token in GitHub**.
- **Measured:** ~170 MB memory; an analysis takes **0.9–2.8 s** on the free CPU share (≈30 ms on a normal machine); first request after sleep ~1 minute.
- **Live check:** a GitHub Actions workflow smoke-tests the public URL daily (`live.yml`, `--wait 300` for the cold start).
- The rate limit is a shared ceiling because all traffic arrives through Render's proxy and `X-Forwarded-For` isn't trusted by default.

---

## Interview questions

**Q: Why Render instead of AWS?**
Free, Docker-native, deploys from GitHub with HTTPS and health checks, configured as code in `render.yaml` — the right level of effort for portfolio demos. On AWS I'd use ECS/Fargate or App Runner with RDS.

**Q: How do deployments work?**
Push to the branch → Render builds the Dockerfile → starts the new container → waits for `/api/v1/health` → switches traffic. MedVision waits for GitHub checks first (`checksPass`).

**Q: How did you handle the free tier's 512 MB?**
CareFlow: lightweight local retrieval models and one numeric thread. MedVision: ONNX Runtime instead of TensorFlow (~170 MB in use).

**Q: How are secrets managed?**
`sync: false` variables entered in Render's dashboard, `generateValue: true` for random secrets; nothing secret in Git or the image.

**Q: What are the downsides of the free tier?**
Cold starts after 15 minutes idle, limited CPU, single instance — the WebSocket broadcaster is single-process, which matches this. Fine for demos, not for production.
