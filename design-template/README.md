# Design System Template

A portable, zero-dependency UI kit built on **Tailwind CSS + React**.
Extracted from the GHARRA Command Centre — drop it into any Next.js or Vite project.

## Palette

| Token | Value | Usage |
|-------|-------|-------|
| `brand-600` | `#0D7377` (teal) | Primary buttons, active states, focus rings |
| `surface-50` | `#F8FAFB` | Page background (light) |
| `surface-950` | `#020617` | Page background (dark) |
| `surface-{200-700}` | Cool grays | Borders, dividers |
| `surface-{500-900}` | Dark grays | Body text |

**To rebrand:** replace the `brand` ramp in `tailwind.config.ts` with your colour.
`npx tailwindcss-palette-generator <your-hex>` generates a compatible 50–950 ramp.

---

## Files

```
design-template/
├── tailwind.config.ts        ← colour ramp, fonts, shadows, animations
├── logo-guide.md             ← logo design specification & checklist
├── src/
│   ├── globals.css           ← design tokens, dark mode, scrollbar, glass, utilities
│   ├── showcase.tsx          ← every component on one page (add as /showcase route)
│   ├── logo-template.svg     ← annotated SVG template — copy for each new project
│   └── components/
│       ├── ui.tsx            ← ALL base components in one file
│       └── charts.tsx        ← Recharts-based data visualisation components
```

## Install

```bash
# Base components (ui.tsx)
npm install tailwindcss clsx tailwind-merge class-variance-authority lucide-react

# Chart components (charts.tsx) — optional, only if you use data visualisation
npm install recharts
```

## Setup

1. Copy `tailwind.config.ts` → your project root (merge `theme.extend` if needed).
2. Copy `src/globals.css` → `src/app/globals.css` (Next.js) or `src/index.css` (Vite).
3. Copy `src/components/ui.tsx` → your project's `src/components/ui.tsx`.
4. *(Optional)* Copy `src/components/charts.tsx` → `src/components/charts.tsx` for data vis.

```tsx
// Base components
import { Button, Badge, Card, Input, Table, Dialog, Tabs, StatusDot } from "@/components/ui";

// Chart components (requires recharts)
import { MetricCard, AreaChartCard, BarChartCard, DonutChart, SloGauge } from "@/components/charts";
```

---

## Components

| Component | Variants / Notes |
|-----------|-----------------|
| `Button` | `primary` `secondary` `ghost` `danger` `outline` · `sm` `md` `lg` `icon` · `loading` prop |
| `Badge` | `default` `success` `warning` `danger` `info` `outline` · `dot` prop |
| `Card` | `default` `elevated` `interactive` `glass` · compound: Header/Title/Description/Content/Footer |
| `Input` | `label` `helperText` `error` `prefix` `suffix` · accessible aria-invalid |
| `Select` | `label` · native `<select>` with ChevronDown icon |
| `Dialog` | `sm` `md` `lg` `xl` · Escape-to-close · body scroll lock · compound: Title/Description/Footer |
| `Tabs` | Controlled & uncontrolled · animated underline indicator · compound: List/Tab/Panel |
| `StatusDot` | `healthy` `degraded` `critical` `active` `suspended` `revoked` `connected` + more · `pulse` prop |
| `Skeleton` | `text` `circle` `rect` `card` · presets: `SkeletonText` `SkeletonCard` |
| `EmptyState` | `icon` `title` `description` `action` |
| `Table` | Compound: `TableHeader` `TableBody` `TableFooter` `TableRow` `TableHead` `TableCell` · hover/selected states |

### Chart Components (`charts.tsx`)

Requires `recharts`. All charts support dark mode, brand palette, and smooth animations.

| Component | Description |
|-----------|-------------|
| `ChartTooltip` | Shared custom tooltip with brand styling — used by all chart types |
| `MetricCard` | KPI card with trend indicator, optional sparkline or percentage ring |
| `AreaChartCard` | Time-series area chart with gradient fill · optional secondary series |
| `BarChartCard` | Horizontal or vertical bar chart · `colorByIndex` for category colouring |
| `DonutChart` | Pie/donut with center label, auto-legend · `colors` array or per-datum `fill` |
| `SloGauge` | SLO burn-rate radial gauge · target vs current · budget remaining ring |
| `SparklineChart` | Tiny inline area sparkline for embedding in tables or KPI rows |
| `LatencyHistogram` | Latency bucket distribution · auto colour-codes by threshold |

#### Palette Constants

| Export | Value | Usage |
|--------|-------|-------|
| `BRAND` | `#0D7377` | Default chart stroke/fill |
| `BRAND_LIGHT` | `#14919B` | Secondary series |
| `SERIES_COLORS` | 10-colour array | Multi-series / category charts |
| `STATUS_COLORS` | active/suspended/revoked/retired | Agent status visualisation |
| `SEVERITY_COLORS` | healthy/degraded/critical/unknown | Health dashboards |

---

## Dark Mode

Uses Tailwind's `class` strategy. Set `class="dark"` on `<html>` to activate.

```tsx
// Minimal theme toggle
function ThemeToggle() {
  const toggle = () => document.documentElement.classList.toggle("dark");
  return <button onClick={toggle}>Toggle theme</button>;
}
```

For persistence across sessions, store the preference in `localStorage` and apply on initial load.

---

## Showcase

`src/showcase.tsx` renders every component and variant on a single page.
Route it at `/showcase` during development, remove before production.

```tsx
// app/showcase/page.tsx (Next.js App Router)
export { default } from "@/showcase";
```

---

## Utility Classes (globals.css)

| Class | Effect |
|-------|--------|
| `.glass` | `bg-white/70 backdrop-blur-xl` — frosted glass panel |
| `.glow-brand` | Teal box-shadow glow — use on CTAs to lift them |
| `.text-gradient-brand` | `brand-500 → brand-600` gradient text |
| `.scrollbar-thin` | 6px custom scrollbar matching the surface palette |
| `.border-gradient-right` | Gradient right-border for sidebars |
| `.transition-smooth` | `350ms cubic-bezier(0.16, 1, 0.3, 1)` transition |
| `.transition-fast` | `150ms cubic-bezier(0.4, 0, 0.2, 1)` transition |

---

## Animations (tailwind.config.ts)

| Name | Duration | Effect |
|------|----------|--------|
| `animate-fade-in` | 300ms | Opacity 0 → 1 |
| `animate-slide-up` | 300ms | Fade + translate Y 8px → 0 |
| `animate-pulse-soft` | 2s loop | Gentle opacity pulse |

---

## Logo

The design system includes a repeatable logo framework so every project in the
family shares the same visual DNA while remaining distinct.

### Quick start

1. Copy `src/logo-template.svg` → your project's `docs/assets/{project}-logo.svg`
2. Replace the hex colours with your brand ramp (see colour mapping in the guide)
3. Swap the inner icon (Layer 2) for your project's motif
4. Choose or remove the domain badge (Layer 3)
5. Update the wordmark text (Layer 4)

### Structure

Every logo is 4 layers on a **400 × 120** canvas:

| Layer | Purpose | What changes per project |
|-------|---------|------------------------|
| 1 — Shield | Shared silhouette (brand identity) | Gradient colours only |
| 2 — Inner icon | Project-specific motif | Entirely replaced |
| 3 — Domain badge | Industry/domain symbol (14×14 at shield base) | Shape or removed |
| 4 — Wordmark | Name + subtitle + accent line | Text content only |

### Sizing

| Use case | Dimensions |
|----------|-----------|
| Navbar / header | 400 × 120 (default) |
| Favicon | 32 × 32 (shield only) |
| Social / OG image | 1200 × 630 (centred on brand background) |
| README badge | 200 × 60 (half-size) |
| App icon (square) | 120 × 120 (shield only) |

See **[logo-guide.md](logo-guide.md)** for the full specification, colour mapping
table, inner-icon design principles, and a pre-flight checklist.
