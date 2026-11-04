# Vitest

## 30-second answer
Vitest is a fast unit-test framework for JavaScript built on **Vite** — it reuses the app's Vite config and transforms, and has a **Jest-compatible API** (`describe`, `it`, `expect`, `vi.fn()`). With **jsdom** and **React Testing Library** it tests React components the way a user sees them. CareFlow has **13 Vitest tests** for the chat (confirmation cards, emergencies), start page, home page, analytics and the **i18n dictionary**; MedVision tests each component (upload, result card, heatmap viewer, theme toggle, info sections), the API client, and — importantly — **contract tests that validate test fixtures against the backend's OpenAPI schema**, giving type safety without TypeScript.

---

## Basics you must know

### Test syntax
```js
import { describe, it, expect, vi } from "vitest";

describe("formatPercent", () => {
  it("rounds to a whole percent", () => {
    expect(formatPercent(0.904)).toBe("90%");
  });
});
```
Matchers: `toBe`, `toEqual` (deep), `toContain`, `toHaveProperty`, `toThrow`, `toBeTruthy`, `toHaveBeenCalledWith`; jest-dom adds `toBeInTheDocument`, `toHaveTextContent`, `toBeVisible`.

### Mocks
- `vi.fn()` — a spy function; `vi.spyOn(obj, "method")`.
- `vi.mock("./module")` — replace a module.
- Mock `fetch`: `globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(data), { status: 200 }))`.
- Fake timers: `vi.useFakeTimers()`, `vi.advanceTimersByTime(5000)`.

### Environment
`environment: "jsdom"` simulates a browser DOM in Node. `setupFiles` runs before tests (e.g. `import "@testing-library/jest-dom"`).

### React Testing Library (RTL) philosophy
"Test what the user sees": query by **role, label, text** (`getByRole("button", { name: "Send" })`), interact with `fireEvent` or `user-event`, assert on visible output. Avoid testing implementation details (state variables, class names).
- `getBy*` (throws if missing), `queryBy*` (returns null), `findBy*` (async, waits).
- `waitFor(() => expect(...))` for async updates.

### Running
`vitest` (watch mode), `vitest run` (once, for CI), `--coverage` (v8 provider).

### Vitest vs Jest
Same API; Vitest is faster with Vite projects, supports ESM natively and needs no separate Babel config.

---

## How I used it in CareFlow (`ui/`)

### Config (`ui/vite.config.js`)
```js
test: { environment: "jsdom", globals: true, setupFiles: ["./src/setupTests.js"] }
```

### Chat test (`ui/src/pages/Chat.test.jsx`)
```js
function mockReplies(...replies) {
  const calls = [];
  globalThis.fetch = vi.fn(async (url, init) => {
    if (String(url).endsWith("/config")) {          // the session asks once for config
      return new Response(JSON.stringify({ demo_mode: true, allow_registration: true }), { status: 200 });
    }
    calls.push({ body: JSON.parse(String(init?.body ?? "{}")) });
    return new Response(JSON.stringify({ ...base, ...replies.shift() }), { status: 200 });
  });
  return calls;
}
render(<SessionProvider><MemoryRouter><Chat /></MemoryRouter></SessionProvider>);
```
Tests include "shows the emergency panel and nothing else to act on" and "confirms a card with its action id and shows citations as chips" — i.e. **Confirm sends the card's `confirm_action_id`** and sources appear as chips. `calls` lets the test assert on the exact request bodies.

### Other tests
`Start.test.jsx`, `Home.test.jsx`, `Analytics.test.js`, and `i18n.test.js` ("has every string in English, Hindi and Marathi with the same placeholders", and placeholders are filled correctly).

### CI
`npm run lint && npm test` in the `ui` job.

## How I used it in MedVision AI (`frontend/`)

### Config (`frontend/vite.config.js`)
```js
test: {
  environment: "jsdom",
  setupFiles: ["./src/test/setup.js"],
  css: false,
  coverage: { include: ["src/**/*.{js,jsx}"], exclude: ["src/main.jsx", "src/test/**"] },
}
```
Libraries: `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`, `@vitest/coverage-v8`.

### Component tests
`UploadPanel.test.jsx` (drop, browse, paste, validation), `ResultCard.test.jsx` (alert shown first, confident vs uncertain, "Not checked" reasons), `HeatmapViewer.test.jsx` (toggle, strength slider), `ThemeToggle.test.jsx`, `InfoSections.test.jsx`, `AnalysisPanel.test.jsx`, `App.test.jsx`, `api/client.test.js`, `lib/lib.test.js`. Shared fixtures in `src/test/fixtures.js`.

### API contract test (`frontend/src/api/contract.test.js`)
```js
import openapi from "./openapi.json";               // generated from the FastAPI backend
const schemas = openapi.components.schemas;

function checkAgainst(schemaName, value) {
  for (const field of schemas[schemaName].required ?? [])
    expect(value, `${schemaName}.${field}`).toHaveProperty(field);           // nothing missing
  for (const key of Object.keys(value))
    expect(Object.keys(schemas[schemaName].properties)).toContain(key);       // nothing invented
}

it("explain fixture matches ExplanationResponse", () => {
  checkAgainst("ExplanationResponse", explainResponse);
});
it("every status and risk value gets a plain answer, and every reason has wording", () => {
  for (const status of schemas.Status.enum) for (const risk_flag of schemas.RiskFlag.enum) { ... }
});
```
- If the backend renames a field, the regenerated `openapi.json` breaks this test.
- If someone forgets to regenerate `openapi.json`, a **backend** snapshot test fails.
- Every enum value (`ok`/`low_confidence`/`rejected`, every rejection reason) must have user-facing wording.

### CI
`npm ci && npm run lint && npm test -- --run && npm run build`.

---

## Interview questions

**Q: Why Vitest instead of Jest?**
It shares Vite's config and transforms (JSX, ESM, plugins), so there's no separate Babel setup, and it's faster; the API is Jest-compatible.

**Q: How do you test a component that calls an API?**
Mock `fetch` (or the API module) with `vi.fn`, render the component, interact by role/label, and wait for the result with `findBy`/`waitFor`.

**Q: How did you get type safety without TypeScript?**
Contract tests validate fixtures against the backend's OpenAPI schema; mocks can't drift from the real API.

**Q: `getBy` vs `queryBy` vs `findBy`?**
`getBy` throws if absent, `queryBy` returns null (use to assert absence), `findBy` is async and waits.

**Q: What is jsdom?**
A JavaScript implementation of the DOM that runs in Node, so component tests run without a browser (real browsers are for Playwright tests).
