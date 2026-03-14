# Logo Design Guide

A repeatable recipe for creating project logos that share the same visual DNA.
Every logo follows a **shield + inner motif + domain badge + wordmark** structure
so they look like siblings — instantly recognisable as part of the same family,
yet distinct enough to identify each project at a glance.

---

## Canvas & Dimensions

| Property | Value | Notes |
|----------|-------|-------|
| **viewBox** | `0 0 400 120` | Fixed for all logos |
| **Width × Height** | `400 × 120 px` | Use as-is for web; scale proportionally for other media |
| **Icon centre** | `(60, 52)` | Shield + inner motif centred here |
| **Icon bounding box** | `88 × 88 px` | Outer shield from `(28, 12)` to `(92, 100)` |
| **Inner safe area** | `44 × 44 px` circle at `(60, 52)` | All motif artwork stays inside this |
| **Wordmark start** | `x = 120` | Left edge of all text elements |

### Sizing Variants

Generate these from the same SVG source by adjusting `width`/`height`:

| Use case | Size | Notes |
|----------|------|-------|
| Navbar / header | `400 × 120` | Default — full lockup |
| Favicon | `32 × 32` | Shield icon only (crop to viewBox `24 0 72 112`) |
| Social / OG image | `1200 × 630` | Centre the 400×120 lockup on a brand-coloured background |
| README badge | `200 × 60` | Half-size lockup |
| App icon (square) | `120 × 120` | Shield icon only, centred on background |

---

## Anatomy (4 Layers)

Every logo is built from exactly four layers, stacked bottom to top:

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 1: Shield Container                              │
│  ┌──────────┐                                           │
│  │ ┌──────┐ │   LAYER 4: Wordmark                      │
│  │ │ L2:  │ │   ┌──────────────────────────────┐        │
│  │ │ Inner│ │   │  PROJECT NAME    (38px bold)  │        │
│  │ │ Icon │ │   │  ─────────────── (accent line)│        │
│  │ │      │ │   │  FULL SUBTITLE   (9px light)  │        │
│  │ └──────┘ │   │  & TAGLINE       (9px light)  │        │
│  │  ┌────┐  │   └──────────────────────────────┘        │
│  │  │ L3 │  │                                           │
│  │  └────┘  │                                           │
│  └──────────┘                                           │
└─────────────────────────────────────────────────────────┘
```

### Layer 1 — Shield Container

The shield shape is **identical across all projects**. It provides the
recognisable silhouette that ties the family together.

```xml
<path d="M60,12 L92,24 L92,52 C92,76 60,100 60,100 C60,100 28,76 28,52 L28,24 Z"
      fill="url(#shieldGrad)" stroke="{brand-700}" stroke-width="1.5"/>
```

- Fill: `shieldGrad` diagonal gradient from `brand-600` → `brand-500`
- Stroke: `brand-700` at 1.5 px
- **Never modify the path data** — only change the colours

### Layer 2 — Inner Icon (Project Identity)

This is what makes each logo unique. The motif should visually represent
the project's core purpose using **simple geometric shapes**.

| Constraint | Value |
|------------|-------|
| Safe area | 44 × 44 circle centred at `(60, 52)` |
| Max elements | 6–10 shapes (keep it simple at small sizes) |
| Stroke weight | 0.8–1.5 px |
| Fill opacity | 0.5–0.8 for wireframe layers, 1.0 for focal nodes |
| Colour source | `overlayGrad` (brand-50/100) for structure, `nodeGrad` (brand-300/400) for nodes |
| Focal point | One element should be white-filled with brand stroke (the "hero" element) |

**Design principles for the inner icon:**
1. **Abstract, not literal** — represent concepts (network, flow, layers) not literal objects
2. **Connected** — use lines/arcs between nodes to suggest relationships
3. **Layered** — wireframe structure underneath, solid nodes on top
4. **Centre-weighted** — the most important element sits at `(60, 52)`

**Examples by project type:**

| Project type | Inner icon idea |
|-------------|-----------------|
| Registry / directory | Network graph with hub node (GHARRA) |
| Data pipeline | Flow arrows or stream lines left-to-right |
| Auth / security | Concentric rings with keyhole centre |
| API gateway | Radiating spokes from centre node |
| Monitoring | Pulse/waveform line with peak at centre |
| ML / AI agent | Brain-like curved connections or neural net |
| Messaging / events | Overlapping speech bubbles or broadcast arcs |
| Storage / database | Stacked cylinder slices |

### Layer 3 — Domain Badge

A small symbol (max 14 × 14 px) at the bottom of the shield (y ≈ 78–92)
that anchors the logo to a specific **domain** or **industry**.

| Domain | Badge shape |
|--------|-------------|
| Healthcare | Cross (`+` shape) — as in GHARRA |
| Security | Padlock outline |
| Finance | Currency symbol or coin |
| Education | Mortarboard cap |
| Environment | Leaf |
| Engineering | Gear/cog |
| Government | Building columns |
| Generic tech | Chevron brackets `< >` |

- Fill: `brand-50` at `opacity="0.85"`
- Corner radius: `rx="1"` for rectangles
- The badge is **optional** — omit it if the project is domain-agnostic

### Layer 4 — Wordmark

Fixed-position text block. Only the **content** changes; layout stays constant.

```
Position        Font                              Size   Weight  Spacing  Fill
─────────────── ───────────────────────────────── ────── ─────── ──────── ──────────
Name   x=120 y=58   Segoe UI / Helvetica Neue    38px   700     4        brand-600
Line   x=120 y=64   (SVG line → x2=340)          —      —       —        brand-500 @ 0.4
Sub 1  x=121 y=78   Segoe UI / Helvetica Neue     9px   400     1.8      muted-text
Sub 2  x=121 y=91   Segoe UI / Helvetica Neue     9px   400     1.8      muted-text
```

- **Name**: The short project name (e.g. `GHARRA`, `NEXUS`, `BEACON`). All-caps, ≤ 10 characters ideally.
- **Accent line**: Thin horizontal rule under the name. Width fixed at 220 px.
- **Subtitle**: Full project name split across 1–2 lines. Use `&amp;` for `&` in SVG.
- **Muted text colour**: Blend `brand-600` toward grey — typically `#5C8A8C` for the default teal brand.

---

## Colour Mapping

When rebranding, replace **all** hex values in the SVG template using this mapping:

| Token | Default (Teal) | Maps to | Used in |
|-------|---------------|---------|---------|
| `brand-600` | `#0D7377` | Your primary | Shield fill start, name text, accent line |
| `brand-500` | `#14919B` | Your primary lighter | Shield fill end, accent line |
| `brand-700` | `#095E61` | Your primary darker | Shield stroke |
| `brand-50` | `#E0F7FA` | Your lightest | Overlay lines, domain badge, hub connections |
| `brand-100` | `#B2EBF2` | Your light | Overlay gradient end, connection lines |
| `brand-300` | `#4DD0E1` | Your medium light | Node gradient start |
| `brand-400` | `#00ACC1` | Your medium | Node gradient end, hero node stroke |
| muted-text | `#5C8A8C` | Blend brand→grey | Subtitle text |

Use `npx tailwindcss-palette-generator <your-hex>` to generate a full 50–950 ramp,
then pick the stops that correspond to each token above.

---

## Step-by-Step: Creating a New Logo

1. **Copy** `src/logo-template.svg` into your new project's `docs/assets/` directory
2. **Rename** it to `{project}-logo.svg`
3. **Replace colours** — swap hex values per the colour mapping table
4. **Design the inner icon** — delete the example content between the Layer 2 comments and draw your motif within the 44×44 safe area
5. **Choose a domain badge** — replace or remove the Layer 3 content
6. **Update text** — change the project name, subtitle line 1, and subtitle line 2
7. **Test at size** — view at 400×120 (normal), 200×60 (small), and 32×32 (favicon crop) to ensure legibility

---

## Checklist

Before finalising a new project logo, verify:

- [ ] Shield path is unmodified (identical silhouette across all logos)
- [ ] All colours come from a single brand ramp (no random hex values)
- [ ] Inner icon fits within the 44×44 safe area
- [ ] Inner icon has a white-filled "hero" element at centre
- [ ] Inner icon uses ≤ 10 shapes (readable at 32×32)
- [ ] Domain badge is ≤ 14×14 px and centred at x=60
- [ ] Project name is ≤ 10 characters and all-caps
- [ ] Subtitle uses letter-spacing 1.8 and 9px font size
- [ ] Accent line runs from x=120 to x=340
- [ ] Logo is legible at 200×60 (half-size)
- [ ] Favicon crop (shield only) is recognisable at 32×32
