# React

## 30-second answer
React is a JavaScript library for building user interfaces from **components** — functions that take **props** and return JSX describing the UI. When **state** changes, React re-renders and updates only what changed in the DOM. Both my projects have React frontends in plain JavaScript: **CareFlow** (React 18 + React Router) has ~30 screens for patients, front desk, doctors and admins — chat with confirmation cards, booking, a **live queue over WebSockets**, analytics — in **3 languages** with accessibility checks. **MedVision** (React 19) is a single workspace card that changes with state: drop/paste an image → scanning animation → result with high-risk alert, confidence and a heatmap viewer, in light and dark themes.

---

## Basics you must know

### Components, JSX, props
```jsx
function SectionTitle({ children }) {
  return <h3 className="text-xs font-semibold uppercase">{children}</h3>;
}
<SectionTitle>Most likely lesion type</SectionTitle>
```
JSX compiles to `React.createElement` calls. Props are read-only inputs; `children` is the content between tags.

### State and re-rendering
```jsx
const [result, setResult] = useState(null);
```
Calling the setter schedules a re-render. State updates are **asynchronous and batched**; use the functional form `setCount(c => c + 1)` when the new value depends on the old one. Never mutate state directly — create new objects/arrays.

### Hooks (rules: only at the top level of a component, only in components/custom hooks)
| Hook | Use | Example in my code |
|---|---|---|
| `useState` | Local state | Everywhere (~280 uses across both apps) |
| `useEffect` | Side effects: fetch, subscriptions, timers; return a cleanup | WebSocket + polling in CareFlow's `QueueStatus.jsx` |
| `useRef` | Mutable value that doesn't trigger re-render; DOM refs | Holding the WebSocket; focusing elements |
| `useCallback` / `useMemo` | Memoise functions/values to keep identity stable | `refresh` callback passed to effects; context value |
| `useContext` | Read shared data without prop drilling | CareFlow `SessionContext` (user, token, language, rules) |
| `useId` | Unique ids for accessible label/aria links | Form fields |

### Effects and the dependency array
`useEffect(fn, [a, b])` runs after render when `a` or `b` changes; `[]` runs once on mount; the returned function runs before the next effect and on unmount — that's where you close sockets and clear timers.

### Lists and keys
`items.map(item => <li key={item.id}>…</li>)` — stable keys let React match elements between renders.

### Controlled inputs
`<input value={text} onChange={e => setText(e.target.value)} />`.

### Lifting state up / context
Share state through the closest common parent; use context for app-wide data (session, theme, language).

### Virtual DOM / reconciliation
React builds a new element tree, diffs it with the previous one and applies minimal DOM changes.

### React 18/19 notes
Automatic batching, concurrent rendering, `createRoot`; React 19 adds Actions, `use`, improved ref handling.

### Routing (React Router v6)
`<Routes>`, `<Route path="/library/:collection/:slug" element={<LibraryDoc />} />`, `useParams`, `useNavigate`, `<Navigate>`, nested layouts with `<Outlet>`.

---

## How I used it in CareFlow (`ui/src/`)

### Structure
- `pages/` — one component per screen: `Chat`, `Book`, `Appointments`, `QueueStatus`, `Receipt`, `FrontDesk`, `Kiosk`, `DoctorQueue`, `Coordination`, `Dashboard`, `Analytics`, `HospitalSetup`, `Documents`, `Accounts`, `Messaging`, `Profile`, `Library`, …
- `components/` — `Layout` (bottom tabs on phones + "More" menu), `ConfirmDialog`, `ErrorMessage`, `TableWrap` (tables become labelled cards on phones), `QueueBadges`, …
- `session.jsx` — **`SessionProvider` context**: current user, token, language, booking rules from `/config`; stored in `sessionStorage` inside `try/catch` (works even when storage is blocked).
- `i18n.js` — every string in English, Hindi, Marathi; `translate(key, lang)`.
- `App.jsx` — React Router routes, role-based redirects.

### Notable features
- **Chat** shows the assistant's reply, **source chips** (citations), progress labels for running tools, and a **confirmation card** (region "Please confirm") with Confirm / Cancel — the booking only happens after Confirm.
- **Emergency panel** takes over the chat with 112 / 108.
- **Live queue** — `useEffect` opens a WebSocket, re-fetches on each message, falls back to 5-second polling, and cleans up on unmount.
- **Receipts** with a QR code (`qrcode` library); icons from `lucide-react`.
- **Accessibility:** large-text mode, 44 px tap targets, keyboard and screen-reader support; every screen checked with **axe-core** (WCAG A/AA) and at **360 px** width in Playwright tests.
- Hand-written CSS (`styles.css`), self-hosted Noto Sans + Noto Sans Devanagari fonts.

## How I used it in MedVision AI (`frontend/src/`)
- `App.jsx` — one **workspace card** whose content depends on state: empty drop zone → image + scanning line + three server steps + elapsed time → result (or "Not checked" with the reason).
- `UploadPanel.jsx` — drag-and-drop, file picker, **paste with Ctrl+V**, sample images; client-side validation (`lib/validation.js`).
- `ResultCard.jsx` — fixed order: **high-risk alert first**, then the lesion type with Confident/Uncertain badge and top 3, then the cancer probability vs the alert line; `NotChecked` explains what to fix.
- `HeatmapViewer.jsx` — overlay toggle and strength slider.
- `ThemeToggle.jsx` + `lib/theme.js` — follows `prefers-color-scheme` until the user chooses.
- `api/client.js` — `explain(file, { signal })` with `AbortController` so a new image cancels the old request.
- On phones the result is shown above the image.
- Tests with Vitest + Testing Library for each component, plus **API contract tests** against the backend's OpenAPI schema.

---

## Interview questions

**Q: Props vs state?**
Props come from the parent and are read-only; state is owned by the component and changes over time via its setter.

**Q: How do you avoid memory leaks with WebSockets in React?**
Open the socket in `useEffect` and return a cleanup that closes it and clears any intervals — CareFlow's `QueueStatus` does exactly that, using a `closed` flag so a deliberate close doesn't start polling.

**Q: Why might an effect run twice in development?**
React 18 Strict Mode mounts, unmounts and re-mounts components to surface missing cleanups.

**Q: `useMemo` vs `useCallback`?**
`useMemo` caches a computed value; `useCallback` caches a function's identity — useful when the function is an effect dependency or passed to memoised children.

**Q: Why are keys important?**
They let React match list items across renders; using indexes as keys breaks state when items are reordered.

**Q: How did you handle multiple languages?**
A translation dictionary with all strings in English, Hindi and Marathi, the language in context, dates formatted per language, and fonts that support Devanagari.

**Q: How do you test React components?**
Vitest + React Testing Library: render, interact as a user would (by role and label), assert on visible output; mock `fetch` for API calls.
