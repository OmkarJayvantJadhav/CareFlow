# GitHub Actions

## 30-second answer
GitHub Actions is GitHub's built-in CI/CD: **workflows** written in YAML (`.github/workflows/*.yml`) run **jobs** of **steps** on GitHub-hosted runners when events happen (push, pull request, schedule, manual). Both my projects use it as the quality gate. **CareFlow** runs four jobs on every push and PR — Python lint + 473 tests against a **real pgvector Postgres service container**, UI lint/tests/build, **Playwright end-to-end tests**, and a **Docker build + smoke test**. **MedVision** runs a **matrix** over `ml` and `backend` (ruff, format, **mypy strict**, pytest with coverage), a frontend job, and a Docker job that **builds with cache, runs the container and smoke-tests it**; Render deploys only after checks pass, and a **scheduled workflow smoke-tests the live site daily**.

---

## Basics you must know

### Structure
```yaml
name: CI
on:                      # triggers
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: "17 6 * * *"
  workflow_dispatch:     # manual "Run workflow" button
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4          # an action from the marketplace
      - uses: actions/setup-python@v5
        with: { python-version: "3.11", cache: pip }
      - run: pip install -r requirements-dev.txt
      - run: pytest
```

### Key concepts
| Concept | Meaning |
|---|---|
| Workflow | One YAML file, triggered by events |
| Job | Runs on one runner; jobs run **in parallel** unless `needs:` |
| Step | A shell command (`run`) or an action (`uses`) |
| Runner | VM that executes the job (`ubuntu-latest`, `ubuntu-24.04`) |
| **Matrix** | Run a job for each combination (`package: [ml, backend]`) |
| **Service containers** | Side containers like Postgres/Redis for tests |
| **Caching** | `actions/cache` or `cache:` in setup actions; Docker `type=gha` |
| Artifacts | Upload files (logs, reports) from a run |
| Secrets / variables | `${{ secrets.X }}`, `${{ vars.X }}` |
| `if:` | Conditional steps (`if: failure()`) |
| `concurrency` | Cancel outdated runs on the same branch |
| `permissions` | Least-privilege token (`contents: read`) |

### CI vs CD
- **CI** (continuous integration): every change is built and tested automatically.
- **CD** (continuous delivery/deployment): passing changes are released automatically.

---

## How I used it in CareFlow (`.github/workflows/ci.yml`)

Triggered on every `push` and `pull_request`. Four jobs:

| Job | What it does |
|---|---|
| **test** | Service container `pgvector/pgvector:pg16` with `pg_isready` health check; Python 3.11 with pip cache; `ruff check` + `ruff format --check`; `pytest` (unit, integration, **concurrency**, agent with a scripted LLM) |
| **ui** | Node 22 with npm cache; `npm ci`, `npm run lint`, `npm test` (Vitest), `npm run build` |
| **e2e** | `needs: [test, ui]`; Postgres service; `python -m playwright install --with-deps chromium`; build the UI; `pytest -m e2e tests/e2e` (all screens, accessibility, live queue); **on failure upload the server log as an artifact** |
| **docker** | `docker build`; run Python inside the image to assert the LightGBM model loads and `ui/dist/index.html` exists |

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    env: { POSTGRES_USER: careflow, POSTGRES_PASSWORD: careflow, POSTGRES_DB: careflow_test }
    ports: ["5432:5432"]
    options: >-
      --health-cmd "pg_isready -U careflow -d careflow_test"
      --health-interval 5s --health-timeout 5s --health-retries 20
env:
  TEST_DATABASE_URL: postgresql+psycopg://careflow:careflow@localhost:5432/careflow_test
```
Render redeploys from `develop` (its own auto-deploy).

## How I used it in MedVision AI

### `ci.yml` — on push to `main` and every PR
```yaml
concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }   # cancel stale runs
permissions: { contents: read }                                          # least privilege
jobs:
  python:
    strategy:
      fail-fast: false
      matrix: { package: [ml, backend] }
    defaults: { run: { working-directory: ${{ matrix.package }} } }
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
        with: { enable-cache: true, cache-dependency-glob: "${{ matrix.package }}/uv.lock" }
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy
      - run: uv run pytest --cov --cov-report=term-missing
  frontend:   # Node version from .nvmrc; npm ci, lint (ESLint + Prettier), vitest --run, build
  docker:
    steps:
      - uses: docker/setup-buildx-action@v4
      - uses: docker/build-push-action@v7
        with: { context: ., load: true, tags: medvisionai:ci, cache-from: type=gha, cache-to: "type=gha,mode=max" }
      - name: Report image size        # ::warning:: if larger than 1 GB
      - name: Smoke test the container
        run: |
          docker run -d --name app -p 7860:7860 medvisionai:ci
          python3 .github/scripts/smoke_test.py http://localhost:7860 frontend/public/samples/melanoma.jpg --wait 90
      - name: Container logs
        if: failure()
        run: docker logs app
```
The smoke test checks: ready, home page, predict, explain, **a non-skin image and a grainy image are rejected**, and p95 latency.

### `live.yml` — the deployed site
```yaml
on:
  schedule: [{ cron: "17 6 * * *" }]   # daily
  workflow_dispatch:
env: { LIVE_URL: ${{ vars.LIVE_URL }} }
# same smoke_test.py against the public URL, --wait 300 because the free service sleeps
```

### Deployment gate
`render.yaml` has `autoDeployTrigger: checksPass` — Render deploys `main` only after GitHub checks pass, so no deploy token is stored in GitHub.

---

## Interview questions

**Q: How do you run tests that need a database in CI?**
A service container (`pgvector/pgvector:pg16`) with a health check; tests connect via `localhost:5432` with a test URL.

**Q: What is a matrix build?**
One job definition run for each value — MedVision runs the same Python checks for `ml` and `backend` in parallel; `fail-fast: false` lets both finish.

**Q: How do you speed up CI?**
Dependency caches (pip, npm, uv), Docker layer cache (`type=gha`), parallel jobs, `needs:` only where required, cancel outdated runs with `concurrency`.

**Q: How do you debug a failed CI run?**
Upload logs as artifacts on failure (CareFlow's e2e server log) or print container logs (`docker logs app` in MedVision).

**Q: How is deployment connected to CI?**
Render watches the branch and deploys after GitHub checks pass (MedVision) or on push to `develop` (CareFlow); a scheduled workflow smoke-tests the live site daily.

**Q: Why smoke-test the Docker image and not just the code?**
The image is what runs in production; the test catches missing files, a model that failed to download, wrong ports or start-up errors that unit tests can't see.
