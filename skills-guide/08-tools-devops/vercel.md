# Vercel

## Where it fits in my work (say this honestly)
**Neither CareFlow nor MedVision is deployed on Vercel** — both run on **Render** as single Docker containers where FastAPI serves the React build. Vercel is the natural choice when the frontend is deployed **separately** from the backend.

> If asked "where did you use Vercel?" → "For deploying frontend projects (<name your project/coursework if you have one>). For CareFlow and MedVision I chose Render because each app is one Docker container — a Python backend with an ML model, WebSockets and background jobs — and Vercel's serverless functions aren't a good fit for long-lived connections, background threads or a 16 MB ONNX model with a warm session. If I split them, I'd put the React app on Vercel and keep the API on Render."

---

## 30-second answer
Vercel is a frontend cloud platform (the company behind **Next.js**) for deploying static sites and frontend frameworks with **serverless/edge functions**. Connect a Git repo and every push builds and deploys automatically; every pull request gets its own **preview URL**; content is served from a global **CDN** with automatic HTTPS.

---

## Basics you must know

### Deploying a Vite + React app
1. Import the GitHub repo in Vercel.
2. Framework preset **Vite**: build command `npm run build`, output directory `dist`.
3. Set environment variables (e.g. `VITE_API_URL=https://careflow-zy87.onrender.com`).
4. Every push to the production branch deploys; every PR gets a preview deployment.

### `vercel.json` (common settings)
```json
{
  "rewrites": [
    { "source": "/api/(.*)", "destination": "https://my-api.onrender.com/api/$1" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```
- The second rewrite makes client-side routing (React Router) work on refresh.
- The first proxies API calls to a separate backend — similar to Vite's dev proxy.

### Serverless and edge functions
- Files in `/api` become functions (Node.js, Python and others).
- Short-lived, stateless, scale to zero; time and size limits.
- **Not suitable for:** WebSocket servers, long-running background threads, large ML models that need to stay loaded in memory.

### Other features
Preview deployments, instant rollbacks, environment variables per environment (production/preview/development), analytics, image optimisation, custom domains.

---

## How my projects *would* use Vercel

| Part | Today (Render) | With Vercel |
|---|---|---|
| CareFlow React UI (`ui/`) | Built in Docker stage 1, served by FastAPI | Vercel static deploy (`dist/`), rewrites `/api/*` to the Render API |
| CareFlow WebSockets `/ws/queue/*` | Same container | Must connect directly to the Render API (`wss://...onrender.com/ws/...`) — Vercel can't host them |
| CareFlow background jobs (reminders, outbox) | Threads in the API process | Stay on Render |
| MedVision React UI (`frontend/`) | Copied to `/app/static` in the image | Vercel static deploy |
| MedVision ONNX inference | FastAPI on Render | Stay on Render (warm model, 512 MB) |

**Trade-offs of splitting:** global CDN and preview URLs for the UI, but two deployments, **CORS** to configure (MedVision already supports `MEDVISION_ALLOWED_ORIGINS`), and the token must be sent cross-origin.

---

## Interview questions

**Q: Vercel vs Render?**
Vercel is optimised for frontends and serverless functions with a global CDN and preview deployments; Render runs long-lived services, Docker containers, workers and databases. My apps need long-lived processes, so Render.

**Q: Why do SPAs need a rewrite to `index.html`?**
Routes like `/library/policies/cancellation` exist only in the client router; without the rewrite the CDN returns 404 on refresh.

**Q: Can Vercel host a WebSocket server?**
Not in its serverless functions — they're short-lived. Use a separate service (Render, Fly.io) or a managed realtime service.

**Q: What are preview deployments?**
Every pull request gets its own deployed URL, so reviewers can try the change before merging.
