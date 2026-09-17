# SiaCore Dashboard (NexusFlow AI frontend)

React + Vite + Tailwind frontend, branded from the SiaCore brand guide, wired
to Supabase for live data. Same six-screen architecture as the previous
NexusFlow app: **Overview, Parts & Stock, Inventory Records, Add Data, News,
Reports** — with a working dark/light theme toggle.

## 1. Install

```bash
npm install
```

## 2. Configure Supabase

```bash
cp .env.example .env
```

Fill in your project's URL and anon key (Supabase dashboard → Project
Settings → API).

## 3. Create the stored procedures

Open the Supabase SQL editor and run `sql/01_stored_procedures.sql`. This
creates the `get_*` Postgres functions the frontend calls via
`supabase.rpc(...)`. **Check the column names against your real tables
first** — a few (e.g. `"Current_Stock"`, `"Manufacturer_Risk"."M_ID"`) use
the exact casing seen in your ERD and may need adjusting if your live schema
differs.

Also make sure Row Level Security policies exist on the underlying tables —
granting `execute` on a function does not bypass RLS on the tables it reads.

## 4. Run

```bash
npm run dev
```

## Project structure

```
src/
  components/     Layout, Logo, ThemeToggle, StatCard, DateFilter (shared across screens)
  lib/
    supabaseClient.js   Supabase client + all api.* data-access calls
    ThemeContext.jsx    dark/light theme provider (persisted to localStorage)
  pages/
    Landing.jsx          Overview / risk dashboard
    PartsStock.jsx        Parts + stock search table
    InventoryRecords.jsx  Warehouse inventory + KPIs
    AddData.jsx           Dynamic insert form (parts, distributer, manufactures, stock, inventory)
    News.jsx               Risk events + alerts feed
    Reports.jsx             Generated reports list
sql/
  01_stored_procedures.sql   All Postgres RPC functions used by the frontend
```

## Theming

Brand tokens live in two places:

- `tailwind.config.js` — raw palette (`navy`, `royal`, `teal`, `violet`,
  `magenta`, `slate`, `soft`) and the three brand gradients (Aurora Flow,
  Ocean Intelligence, Sunset Insight) straight from the brand guide.
- `src/index.css` — semantic CSS variables (`--bg-app`, `--text-primary`,
  etc.) that remap for `.dark`, so components use `var(--bg-surface)` etc.
  rather than hardcoding a color, and both themes stay in sync automatically.

Fonts: **Sora** (display/headings) and **Outfit** (body), loaded from Google
Fonts in `index.html`, matching the brand guide's typography spec.

## Logo

`src/components/Logo.jsx` uses the real transparent hexagon "S" artwork
(`src/assets/logo-icon.png`, background removed, no rectangle) with a soft
aurora-gradient glow behind it, paired with a live HTML/CSS gradient
wordmark rather than a baked-in raster logo image. That makes it crisp at
any size and automatically correct in both themes with no separate
light/dark asset swapping needed.

## Notifications

The bell icon in the top bar (`src/components/NotificationBell.jsx`) is
backed by Supabase Realtime, not polling — it fires the moment a new row is
inserted into `reports` or `inventory`, anywhere, by anyone.

This needs two things set up on the Supabase side that aren't automatic:
1. **Enable Realtime replication** on both tables (Supabase dashboard →
   Database → Replication → toggle `reports` and `inventory` on), or run
   the `alter publication supabase_realtime add table ...` statements at
   the bottom of `sql/01_stored_procedures.sql`.
2. **A SELECT policy** on both tables for whatever role your key uses —
   RLS silently blocks realtime payloads even if replication is on.

Without step 1 the bell just never lights up, with no error anywhere —
worth checking first if new reports/inventory rows aren't triggering it.

## Design system

- **Background**: layered aurora gradient blobs (slow-drifting, `.app-background`) + a faint hexagon lattice pattern + a flowing wave accent (`.wave-accent`, used behind the Home hero)
- **Cards/surfaces**: glassmorphism (`.surface` / `.surface-2` / `.sidebar-glass`) — translucent background, backdrop blur, soft border, blue-tinted shadow
- **Gradients** (`tailwind.config.js` → `backgroundImage`, mirrored in `index.css` as `.bg-*` / `*-gradient-text` utilities):
  - **Aurora Flow** (teal → royal → magenta) — primary buttons, active nav
  - **Ocean Intelligence** (teal → royal → violet) — chart strokes, icon chips
  - **Sunset Insight** (violet → magenta → orange) — critical/high-risk badges only
- **Hover motion**: `.card-hover` lifts cards slightly with a soft glow on hover — applied to stat cards, tables, and workspace buttons
