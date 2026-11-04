# Vite

## 30-second answer
Vite is a fast frontend **build tool and dev server**. In development it serves source files as native **ES modules** (no bundling), pre-bundles dependencies with **esbuild**, and updates the page instantly with **Hot Module Replacement (HMR)**. For production it bundles, minifies and splits code (Rollup, and Rolldown in newer versions) into static files in `dist/`. Both my frontends use Vite with the React plugin: CareFlow (Vite 5) and MedVision (Vite 8, with the Tailwind CSS v4 plugin). The **dev-server proxy** forwards `/api` (and in CareFlow `/ws` WebSockets) to the FastAPI backend, and in production **FastAPI serves Vite's `dist/` build** from the same origin — inside one Docker image.

---

## Basics you must know

### Why Vite is fast
| Older bundlers (webpack/CRA) | Vite |
|---|---|
| Bundle the whole app before the dev server starts | Serve source on demand as ES modules |
| Re-bundle on change | HMR updates only the changed module |
| JS-based tooling | esbuild (Go) for dependency pre-bundling and TS/JSX transforms |

### Project files
```
index.html            # the entry point (not in /public); loads /src/main.jsx
vite.config.js        # plugins, dev server, build, (Vitest) test config
src/main.jsx          # createRoot(...).render(<App />)
public/               # copied as-is (e.g. MedVision's sample images)
```

### Commands
| Script | Command | Does |
|---|---|---|
| `dev` | `vite` | Dev server with HMR (port 5173) |
| `build` | `vite build` | Production bundle → `dist/` |
| `preview` | `vite preview` | Serve the built `dist/` locally |

### Config essentials
```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
  build: { outDir: "dist", sourcemap: false },
});
```

### Environment variables
`import.meta.env.MODE`, and variables prefixed `VITE_` (e.g. `VITE_API_URL`) are exposed to client code — never put secrets there.

### Vitest integration
Vitest reads the same `vite.config.js` (`test: { environment: "jsdom", setupFiles: [...] }`), so tests use the same plugins and transforms as the app.

---

## How I used it

### CareFlow (`ui/vite.config.js`)
```js
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },     // WebSocket proxy for live queues
    },
  },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/setupTests.js"] },
});
```
- `npm run dev` → http://localhost:5173 with API calls proxied to Uvicorn on :8000, so the browser sees one origin (no CORS in development either).
- Production: the Dockerfile's **first stage** (`node:22-slim`) runs `npm ci && npm run build`; the second stage copies `ui/dist` into the Python image and FastAPI serves it.

### MedVision (`frontend/vite.config.js`)
```js
export default defineConfig({
  plugins: [react(), tailwindcss()],                 // @tailwindcss/vite — Tailwind v4 as a Vite plugin
  server: { proxy: { "/api": "http://localhost:8000" } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
    css: false,
    coverage: { include: ["src/**/*.{js,jsx}"], exclude: ["src/main.jsx", "src/test/**"] },
  },
});
```
- Make targets: `make frontend-setup frontend-dev` (UI on :5173 proxied to the API on :8000).
- Production: Docker stage `node:24-slim` builds `dist/`, copied to `/app/static`; FastAPI serves it when `MEDVISION_STATIC_DIR` is set.
- Self-hosted fonts via `@fontsource` packages are bundled by Vite — no requests to Google Fonts (privacy).
- `.nvmrc` pins the Node version; CI uses it (`node-version-file`).

---

## Interview questions

**Q: Why is Vite's dev server so fast?**
It doesn't bundle in development; the browser requests ES modules on demand, dependencies are pre-bundled once with esbuild, and HMR swaps only the changed module.

**Q: What does the proxy do and why use it?**
It forwards `/api` (and `/ws`) from the dev server to the backend, so the frontend uses relative URLs in both development and production and avoids CORS.

**Q: How is the production build served?**
`vite build` outputs static files; a multi-stage Dockerfile builds them with Node and copies them into the Python image, where FastAPI serves them — one container, one origin.

**Q: How do env variables work in Vite?**
Only `VITE_`-prefixed variables are exposed via `import.meta.env`, and they're baked into the bundle at build time — public, so no secrets.

**Q: Vite vs Create React App?**
CRA (webpack) is deprecated and slow to start; Vite is the recommended modern default.
