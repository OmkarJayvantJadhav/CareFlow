# Playwright

## 30-second answer
Playwright is Microsoft's **end-to-end browser testing** framework: it drives real Chromium, Firefox and WebKit, auto-waits for elements, and finds them by **role, label and text** like a user would. CareFlow has **45 Playwright tests** (Python, with pytest) that start the real app with its own database, a **fixed clock** and a **rule-based stand-in LLM**, then test every screen: booking through a **confirmation card**, emergencies, cited answers, Hindi/Marathi switching, front desk, kiosk, doctor queue, admin setup — plus **accessibility with axe-core (WCAG A/AA)**, **every screen at 360 px wide in large-text mode**, and a test that the **live queue updates in under 2 seconds**. The same browser scripts also **record the README's GIFs**.

---

## Basics you must know

### Core API (Python, sync)
```python
from playwright.sync_api import Page, expect

def test_login(page: Page):
    page.goto("/")
    page.get_by_role("button", name="Patient").click()
    page.get_by_label("Type your message…").fill("Book ENT on Monday")
    page.get_by_role("button", name="Send").click()
    expect(page.get_by_role("region", name="Please confirm")).to_be_visible()
```

### Locators (prefer user-facing ones)
`get_by_role`, `get_by_label`, `get_by_text`, `get_by_placeholder`, `get_by_test_id`; chain with `.filter(has_text=...)`, `.nth()`.

### Auto-waiting and web-first assertions
Actions wait until the element is visible, enabled and stable; `expect(locator).to_contain_text(...)` retries until a timeout — no manual `sleep`.

### Other features
- Browser contexts (isolated sessions), multiple pages.
- Viewport and device emulation (`viewport={"width": 360, ...}`), dark mode, locale, geolocation.
- Network interception (`page.route`), `page.evaluate` (run JS in the page).
- Screenshots, videos, traces (`trace.zip` viewer).
- `pytest-playwright` plugin gives `page`, `browser`, `base_url` fixtures.
- `playwright install --with-deps chromium` installs the browser and OS libraries (in CI).

### E2E vs unit tests
E2E tests are slower and fewer, but they test the real system: UI + API + database + WebSockets together.

### Accessibility testing with axe-core
Inject `axe.min.js` into the page and run `axe.run(document, { runOnly: ["wcag2a", "wcag2aa"] })`; assert there are no violations.

---

## How I used it in CareFlow (`tests/e2e/`)

### Server for tests (`tests/e2e/server.py`, `tests/e2e/conftest.py`)
- Starts the real FastAPI app in a subprocess on a free port with its **own database** (`E2E_DATABASE_URL`), serving the **built UI** (`ui/dist`).
- **Clock** starts at Monday 19 Oct 2026, 08:00 IST and then runs normally (every module's `now_ist` is patched) — so slots, check-in windows and queues are predictable.
- **Rule-based stand-in for the LLM** — flows are repeatable and need no API key.
- Waits for `/api/v1/health`; on failure the server log is printed (and uploaded as a CI artifact).
- `expect.set_options(timeout=10_000)`.

### What the 45 tests cover (`tests/e2e/test_ui.py`)
- **Patients:** booking goes through a card and shows in My appointments; create an account and log in; change password; book from recommendations → receipt → reschedule → cancel; profile changes saved; **emergency takes over the chat**; **knowledge answer has a source chip**; assistant joins and leaves a queue online; hospital information without signing in; **interface switches to Hindi and Marathi**; online check-in inside the window; consent and caregiver approval; download data and delete account.
- **Front desk / doctors:** check in and register a walk-in; existing record found for a walk-in; check in by receipt code and at the **kiosk**; calendar leave; doctor queue.
- **Admins:** create a staff account with a one-time password; correct and erase a patient record; setup, documents, messaging.
- **TC-20 live queue:**
  ```python
  expect(card.get_by_text("Live")).to_be_visible()            # WebSocket connected
  started = time.monotonic()
  staff_api.post(f"/queue/sessions/{sid}/events", {"type": "delay", "minutes": 20})
  expect(card).to_contain_text("Running late (20 min)", timeout=5000)
  assert time.monotonic() - started < 2.0
  ```
- **Accessibility:** `_axe_violations(page)` injects axe-core from `ui/node_modules` and runs WCAG 2 A and AA rules on every screen; the result must be empty.
- **Phones:** `PHONE_WIDTH = 360`; staff and patient screens must fit a 360 px phone **in large-text mode** (no horizontal overflow, reachable through bottom tabs or the "More" sheet).

### Running
```bash
cd ui && npm ci && npm run build && cd ..
pytest -m e2e tests/e2e          # excluded from plain `pytest` via addopts "-m 'not e2e'"
```
CI job `e2e` (`needs: [test, ui]`) installs Chromium with `python -m playwright install --with-deps chromium`.

### Recording the README GIFs (`tests/e2e/record_gifs.py`)
`python -m tests.e2e.record_gifs [name …]` replays scripted flows (chat booking, cited answer, emergency, live queue, front desk, kiosk, …) in a real browser and converts the videos to GIFs in `docs/gifs/` with ffmpeg — so the README shows the real app, and clips are repeatable.

---

## Interview questions

**Q: Why Playwright over Selenium?**
Auto-waiting and web-first assertions (fewer flaky tests), modern locators by role/label, fast parallel contexts, built-in tracing and video, and one API for Chromium/Firefox/WebKit.

**Q: How do you avoid flaky E2E tests?**
Deterministic environment (own DB, fixed clock, scripted LLM), role/label locators instead of CSS paths, web-first assertions instead of sleeps, and isolated data per test (e.g. each test uses a doctor no other test uses).

**Q: How did you test real-time updates?**
Trigger a queue event through the staff API while the patient page is open and assert the text changes within 2 seconds.

**Q: How did you test accessibility?**
axe-core injected into each page for WCAG A/AA rules, plus layout checks at 360 px in large-text mode, plus keyboard/role-based locators throughout (which only work if the UI is accessible).

**Q: Why not mock the backend in E2E tests?**
The value of E2E is testing the whole stack — UI, API, database, WebSockets; mocks belong in unit tests (Vitest).
