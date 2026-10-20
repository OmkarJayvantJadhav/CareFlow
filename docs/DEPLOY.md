# Deploying CareFlow on free tiers (docs §12)

The whole app — API, chat, live queue and the React UI — is one Docker image listening on port 7860.
The database is a free Neon Postgres with pgvector. Nothing here costs money; free tiers change, so
check the limits when you deploy.

## 1. Database: Neon (free plan)

1. Sign up at <https://neon.tech> and create a project (region: Singapore or Mumbai, closest to Pune).
2. In the project's SQL editor run `CREATE EXTENSION IF NOT EXISTS vector;` (the migrations also try).
3. Copy the **pooled** connection string and change its scheme for SQLAlchemy:
   `postgresql+psycopg://USER:PASSWORD@HOST/neondb?sslmode=require`
   This is your `DATABASE_URL`. Keep it secret.

The first start migrates the database, seeds the fictional hospital (~20 s) and loads the knowledge base.
Neon's free plan suspends compute when idle; the first request after a pause takes a few seconds.

## 2. App: Hugging Face Spaces (free CPU)

1. Sign up at <https://huggingface.co>, then **New Space**: name `careflow`, SDK **Docker**, hardware
   **CPU basic (free)**, visibility public.
2. In the Space's **Settings → Variables and secrets**, add these **secrets**:

   | Name | Value |
   | --- | --- |
   | `DATABASE_URL` | the Neon string from step 1 |
   | `GROQ_API_KEY` | from <https://console.groq.com/keys> |
   | `GEMINI_API_KEY` | from <https://aistudio.google.com/apikey> (fallback provider) |
   | `AUTH_SECRET` | any long random string (e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"`) |

   and the **variable** `DEMO_MODE` = `true`.
3. Create a Hugging Face **access token** with *write* permission (Settings → Access Tokens).

## 3. Deploy from GitHub

In the GitHub repository's **Settings → Secrets and variables → Actions**:

* add the secret `HF_TOKEN` = the write token from step 2.3;
* add the variable `HF_SPACE` = `your-hf-username/careflow`.

Merge `develop` into `main` (or run the **Deploy to Hugging Face Spaces** workflow by hand). The workflow
uploads the repository to the Space, which builds the Dockerfile (about 10 minutes the first time, because
the embedding and re-ranking models are baked into the image). The demo is then at
`https://YOUR-USERNAME-careflow.hf.space`.

**Check from a fresh browser (the Phase 5 gate):** open the link in a private window → pick a language and
"Patient" → ask "Book a Marathi-speaking cardiologist on Saturday" → confirm the card → see it under
My appointments. `https://YOUR-USERNAME-careflow.hf.space/api/v1/health` should say `"status": "ok"`.

## 4. Backup host: Render (free web service)

If Spaces is unavailable: on <https://render.com> choose **New → Blueprint**, point it at the GitHub repo
(it reads `render.yaml`), and fill in `DATABASE_URL`, `GROQ_API_KEY` and `GEMINI_API_KEY`. Render's free
service sleeps after 15 minutes idle; the first request then takes about a minute.

## 5. Monitoring

* Add a free uptime monitor (e.g. UptimeRobot) on `/api/v1/health` every 30 minutes; alert after two failures.
* The admin dashboard shows median latency, LLM errors and cost for recent chat turns on the server, and the
  latest evaluation results shipped with the build.
* Provider dashboards (Groq console, Google AI Studio) show quota use.

## Runbook

| Situation | Action |
| --- | --- |
| The page says it is waking up / first request is slow | Expected after idle (Space, Neon or Render); wait a minute |
| Chat answers "The assistant is busy right now" | Free LLM quota reached; it recovers within minutes to a day. Check the Groq console |
| Visitors left messy data | Admin → Dashboard → **Reset demo data** |
| Database suspended (free limit hit) | Wait for the monthly reset, or create a new Neon project and update `DATABASE_URL` |
| A deploy broke the demo | Re-run the deploy workflow on the previous commit (Actions → Deploy → Run workflow) |
| Slots run out on a long-running demo | They should not: the next 21 days are topped up at every start and every 6 hours |
