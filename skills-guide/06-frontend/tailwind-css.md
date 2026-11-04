# Tailwind CSS

## 30-second answer
Tailwind CSS is a **utility-first** CSS framework: instead of writing CSS classes like `.card`, you compose small single-purpose classes in the markup — `rounded-xl border-2 bg-sunken p-5` — and the build generates only the CSS you actually use. I used **Tailwind CSS v4** in **MedVision AI**, through the official **Vite plugin**, with a custom **design system defined as CSS variables in an `@theme` block** (a clinical palette with WCAG-AA contrast, semantic colours for benign / caution / alert, fonts, shadows, animations) and a **dark theme**. (CareFlow deliberately uses hand-written CSS instead.)

---

## Basics you must know

### Utility classes
| Area | Examples |
|---|---|
| Spacing | `p-5`, `px-4`, `mt-3`, `gap-3`, `space-y-0.5` |
| Layout | `flex`, `grid`, `items-start`, `justify-between`, `shrink-0` |
| Sizing | `w-full`, `h-7`, `max-w-3xl` |
| Typography | `text-xl`, `font-bold`, `leading-snug`, `tracking-tight`, `uppercase` |
| Colour | `text-ink`, `bg-surface`, `border-line-strong` (custom tokens) |
| Borders/shadow | `rounded-xl`, `border-2`, `shadow-card` |
| Arbitrary values | `text-[15px]`, `tracking-[0.1em]` |

### Variants (prefixes)
- **Responsive (mobile-first):** `sm:`, `md:`, `lg:` — `text-xl sm:text-2xl` = bigger from the `sm` breakpoint up.
- **State:** `hover:`, `focus-visible:`, `disabled:`, `aria-*`.
- **Dark mode:** `dark:` (can be tied to a class/attribute or `prefers-color-scheme`).

### Why utility-first?
- No naming bikeshedding, no dead CSS, styles live next to the markup.
- Consistent design scale (spacing, colours) from the theme.
- Small production CSS — only used classes are generated.
- Downsides: long class lists (extract components or constants), learning the names.

### Tailwind v4 changes (vs v3)
- **CSS-first configuration:** `@import "tailwindcss";` and design tokens in `@theme { --color-…; --font-…; }` — no `tailwind.config.js` needed.
- Official **Vite plugin** `@tailwindcss/vite`.
- Faster engine; automatic content detection.
- Tokens become real CSS variables usable anywhere.

### Accessibility reminders
Contrast (WCAG AA ≥ 4.5:1 for normal text), visible focus styles (`focus-visible:ring`), don't rely on colour alone (MedVision pairs colours with icons and words).

---

## How I used it in MedVision AI (`frontend/`)

### Setup
```js
// vite.config.js
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({ plugins: [react(), tailwindcss()], ... });
```
```css
/* src/index.css */
@import "tailwindcss";
@import "@fontsource-variable/plus-jakarta-sans";
@import "@fontsource/ibm-plex-mono/400.css";
```

### Design tokens (`@theme` in `src/index.css`)
```css
@theme {
  --font-sans: "Plus Jakarta Sans Variable", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, ...;

  --color-canvas: #f5f7fb;   --color-surface: #ffffff;  --color-sunken: #eef2f8;
  --color-ink: #0f1b2d;      --color-ink-soft: #46556a; --color-line: #dbe2ec;
  --color-accent: #1d5fc4;   /* one medical-blue accent for actions and focus */

  --color-benign: #116a43;   --color-benign-soft: #e7f5ee;   /* no flag  = green */
  --color-caution: #8a5100;  --color-caution-soft: #fdf3e1;  /* unsure   = amber */
  --color-alert: #b4232d;    --color-alert-soft: #fdecec;    /* refer    = red   */

  --shadow-card: ...; --shadow-workspace: ...;
  --animate-fade-in: fade-in 0.25s ease-out both;
  --animate-shimmer: shimmer 1.6s linear infinite;          /* scanning effect while analysing */
}
```
Each `--color-x` automatically creates utilities `text-x`, `bg-x`, `border-x`. The file's comment notes **every text colour meets WCAG AA contrast** on the surfaces it is used on, and the semantic colours are kept separate from the accent so "alert red" never looks like a button.

### Dark mode
`:root[data-theme="dark"]` and a `@media (prefers-color-scheme: dark)` block redefine the same tokens, so components don't change — only the variables do. `lib/theme.js` follows the system setting until the user picks light or dark with `ThemeToggle`.

### In components (`src/components/ResultCard.jsx`)
```jsx
const HEADING = "text-xl leading-snug font-bold tracking-tight sm:text-2xl";   // shared class string

<div className="animate-fade-in rounded-xl border-2 border-line-strong bg-sunken p-5">
  <div className="flex items-start gap-3 text-ink-soft">
    <ImageOffIcon className="mt-0.5 h-7 w-7 shrink-0" />
    <h2 id="result-heading" className={HEADING}>{title}</h2>
  </div>
  <p className="mt-3 text-[15px] leading-relaxed text-ink">{guidance}</p>
</div>
```
- Repeated class lists are extracted into constants (`HEADING`, `BADGE_TONES`).
- Responsive layout: on phones the result comes **before** the image.
- Prettier formats the code (the Tailwind class order stays consistent).

## Why CareFlow doesn't use Tailwind
CareFlow has many dense, table-heavy staff screens and needed custom behaviour (tables turning into labelled cards on phones, large-text mode, Devanagari typography), so it uses hand-written CSS in `ui/src/styles.css`. Good answer if asked: "I pick per project — Tailwind for a focused UI with a design system, plain CSS when the layout rules are very custom."

---

## Interview questions

**Q: What is utility-first CSS?**
Composing small, single-purpose classes in markup instead of writing semantic class names with custom CSS.

**Q: Doesn't that make HTML messy?**
It can; I extract repeated combinations into constants or components. The trade-off is no dead CSS and a consistent design scale.

**Q: How did you theme it?**
Tailwind v4 `@theme` tokens as CSS variables (colours, fonts, shadows, animations), redefined for dark mode, so components use names like `text-ink` and `bg-alert-soft` and switch automatically.

**Q: How does Tailwind keep CSS small?**
It scans source files for class names and generates only those utilities.

**Q: Mobile-first meaning?**
Unprefixed classes apply to all sizes; `sm:`/`md:` override from that width upward.
