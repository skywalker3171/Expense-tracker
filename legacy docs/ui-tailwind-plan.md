# UI Redesign — Tailwind CSS v4 + Dark Blue Theme + Form Wrapping

## Overview

Migrate the expense tracker frontend from its custom hand-rolled CSS to **Tailwind CSS v4** (Vite plugin variant). Replace the current light gray / white card theme with a **plain dark navy background** (`#0d1b2e`). Wrap every interactive field group in a semantic `<form>` element with a proper `onSubmit` handler. Remove `Dollar2.jpg` background overlay — it is replaced by the flat dark colour.

**Scope:** 5 files touched — `package.json`, `vite.config.js`, `styles.css`, and the three page/layout files (`App.jsx`, `Login.jsx`, `Dashboard.jsx`, `Upload.jsx`).

**Non-goals:** No new features, no routing changes, no backend changes, no component library added.

---

## Sub-Tasks

### 1 — Install Tailwind CSS v4 + Vite plugin

**Intent:** Add Tailwind and its Vite plugin as dev-dependencies and wire it into the build so utility classes are available across the project.

**Expected Outcomes:**
- `tailwindcss` and `@tailwindcss/vite` listed in `devDependencies` in `web/frontend/package.json`
- `vite.config.js` imports and registers the Tailwind Vite plugin
- Running `npm install` inside `web/frontend` succeeds

**Todo List:**
1. In `web/frontend/package.json` add `"tailwindcss": "^4.1.0"` and `"@tailwindcss/vite": "^4.1.0"` to `devDependencies`
2. In `web/frontend/vite.config.js` import `tailwindcss` from `"@tailwindcss/vite"` and add it to the `plugins` array (before the existing `react()` plugin)

**Relevant Context:**
- [`web/frontend/package.json`](web/frontend/package.json) — current deps
- [`web/frontend/vite.config.js`](web/frontend/vite.config.js) — Vite config

**Status:** [ ] pending

---

### 2 — Replace styles.css with Tailwind base + dark-blue theme tokens

**Intent:** Delete the hand-rolled CSS and replace it with a minimal `@import "tailwindcss"` entry plus a `:root` / `body` override that sets the dark navy background and white text as the baseline. Keep only the very few styles that cannot be expressed as a utility (e.g. the recharts tooltip).

**Expected Outcomes:**
- `web/frontend/src/styles.css` contains only the Tailwind import and minimal overrides
- `body` has `background: #0d1b2e` and `color: #e2e8f0`
- No `.navbar`, `.card`, `.btn-primary`, etc. class definitions remain in the CSS file

**Todo List:**
1. Overwrite `web/frontend/src/styles.css` with:
   ```css
   @import "tailwindcss";

   body {
     background: #0d1b2e;
     color: #e2e8f0;
   }
   ```
   (All other styling moves to Tailwind utility classes in JSX)

**Relevant Context:**
- [`web/frontend/src/styles.css`](web/frontend/src/styles.css) — current 245-line CSS file
- [`web/frontend/src/main.jsx`](web/frontend/src/main.jsx) — imports styles.css

**Status:** [x] done

---

### 3 — Restyle App.jsx (layout shell + NavBar)

**Intent:** Remove the `bg-layer` background image overlay (no longer needed with a flat dark background) and restyle the `NavBar` with Tailwind utility classes matching the dark navy theme.

**Expected Outcomes:**
- `<div className="bg-layer" ...>` element and `bgImage` import removed from `App.jsx`
- NavBar uses a dark blue surface (`bg-[#0a1628]`) with white links and a subtle bottom border
- `<main>` uses `max-w-5xl mx-auto px-4 py-6`

**Todo List:**
1. Remove the `import bgImage from "./Dollar2.jpg"` line
2. Remove the `<div className="bg-layer" ...>` element
3. Replace all className strings in `NavBar` and `App` with Tailwind utilities
4. Style active links with `hover:text-indigo-400`

**Relevant Context:**
- [`web/frontend/src/App.jsx`](web/frontend/src/App.jsx) — layout shell
- [`web/frontend/src/styles.css`](web/frontend/src/styles.css) — `.bg-layer` and `.navbar` classes being removed

**Status:** [x] done

---

### 4 — Restyle Login.jsx + confirm form wrapping

**Intent:** Apply Tailwind utility classes to the login/register card. The `<form>` already exists here, so no structural change needed — just restyle with the dark theme.

**Expected Outcomes:**
- Login card is centred, dark surface card (`bg-slate-800`), rounded corners, shadow
- Input fields have dark backgrounds (`bg-slate-700`), white text, and indigo focus ring
- Submit button is indigo, full-width, with hover and disabled states
- Toggle link is styled as a subtle text button

**Todo List:**
1. Replace `className="auth-card"` wrapper with Tailwind card classes
2. Replace `<label>` and `<input>` class strings with Tailwind utilities
3. Replace `className="btn-primary"` on the submit button
4. Replace `className="btn-link"` on the toggle button
5. Replace `className="error"` with `text-red-400`

**Relevant Context:**
- [`web/frontend/src/pages/Login.jsx`](web/frontend/src/pages/Login.jsx) — already has `<form onSubmit={onSubmit}>`

**Status:** [x] done

---

### 5 — Restyle Upload.jsx + wrap in `<form>`

**Intent:** Wrap the file-picker area in a `<form>` element. Restyle the dropzone, error, and results table using Tailwind utilities matching the dark theme.

**Expected Outcomes:**
- A `<form>` wraps the dropzone div and hidden file input; `onSubmit` calls `e.preventDefault()` (no actual submit — file trigger is via click/drop)
- Dropzone has a dashed indigo border that brightens on drag-over
- Result table uses dark surface with subtle row borders
- Error text is `text-red-400`

**Todo List:**
1. Wrap the dropzone and file input in `<form onSubmit={(e) => e.preventDefault()}>` 
2. Replace `className="dropzone"` and `className="dropzone over"` with Tailwind utilities
3. Replace `.upload-result`, `.table`, `.hint` class names with Tailwind utilities
4. Replace `className="error"` with `text-red-400`

**Relevant Context:**
- [`web/frontend/src/pages/Upload.jsx`](web/frontend/src/pages/Upload.jsx) — no `<form>` currently

**Status:** [x] done

---

### 6 — Restyle Dashboard.jsx + wrap query bar and category inputs in `<form>`

**Intent:** Apply Tailwind to all Dashboard UI elements and ensure the query bar and the category-add input are each wrapped in a proper `<form onSubmit={...}>` element so Enter-key submission works via the form rather than raw `onKeyDown`.

**Expected Outcomes:**
- Stats cards: dark surface, rounded, border-slate-700, grid of 4
- Chart wrapper: dark card surface
- Query bar wrapped in `<form onSubmit={...}>` — removes the `onKeyDown` enter hack on the input
- Category add row wrapped in `<form onSubmit={...}>` — removes the `onKeyDown` enter hack
- Expense and Deposits tables: dark surface, alternating row shading, right-aligned amount column
- Category tags: indigo pill badges
- `info-note` tooltip restyled as absolute positioned card

**Todo List:**
1. Replace `.page`, `.page-head`, `.cards`, `.card`, `.card-label`, `.card-value` classNames
2. Wrap query bar `<div className="query-bar">` → `<form onSubmit={(e) => { e.preventDefault(); runQuery(); }}>`, remove `onKeyDown` from the input
3. Wrap category-add `<div className="cat-add">` → `<form onSubmit={(e) => { e.preventDefault(); addCategory(); }}>`, remove `onKeyDown` from the input
4. Replace `.cat-editor`, `.cat-tags`, `.cat-tag`, `.cat-remove`, `.cat-add`, `.cat-msg` classNames
5. Replace `.query-bar`, `.query-input`, `.query-note` classNames
6. Replace `.table`, `.num`, `.cat-select`, `.cat-cell`, `.cat-edit` classNames
7. Replace `.chart-wrap` className
8. Replace `.empty`, `.error`, `.info-note` classNames

**Relevant Context:**
- [`web/frontend/src/pages/Dashboard.jsx`](web/frontend/src/pages/Dashboard.jsx) — query bar at line 191, cat-add at line 239
- `runQuery()` and `addCategory()` already exist as functions — just call them from `onSubmit`

**Status:** [x] done

---

## Notes for Implementation

- Tailwind v4 uses `@import "tailwindcss"` in CSS (not `@tailwind base/components/utilities` directives)
- The dark navy background colour is `#0d1b2e`; navbar/card surface is `#0a1628` or `bg-slate-800` (`#1e293b`)  
- Indigo (`#4f46e5`) remains the primary action colour — use `bg-indigo-600 hover:bg-indigo-700`
- recharts `<Tooltip>` renders outside React's className scope — leave it unstyled or use the `contentStyle` prop to pass inline dark styles
- The `Dollar2.jpg` import and `bg-layer` div can be deleted entirely — no CSS class references it after sub-task 2
- After sub-task 1, run `npm install` inside `web/frontend` before sub-tasks 2–6
