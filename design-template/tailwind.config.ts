import type { Config } from "tailwindcss";

// ─────────────────────────────────────────────────────────────────────────────
// Design System — Tailwind Configuration
//
// Palette:
//   brand-{50–950}   teal/cyan accent  (swap for your brand colour)
//   surface-{0–950}  cool neutral grey (backgrounds, borders, text)
//
// To rebrand: replace the brand colour ramp with any hue.
// Run  npx tailwindcss-palette-generator <hex>  to get a matching ramp.
// ─────────────────────────────────────────────────────────────────────────────

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#E0F7FA",
          100: "#B2EBF2",
          200: "#80DEEA",
          300: "#4DD0E1",
          400: "#26C6DA",
          500: "#14919B",
          600: "#0D7377",
          700: "#095E61",
          800: "#064A4D",
          900: "#033638",
          950: "#012224",
        },
        surface: {
          0:   "#FFFFFF",
          50:  "#F8FAFB",
          100: "#F1F5F7",
          200: "#E4E9ED",
          300: "#CBD3DA",
          400: "#8E9BAA",
          500: "#64748B",
          600: "#475569",
          700: "#334155",
          800: "#1E293B",
          900: "#0F172A",
          950: "#020617",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      boxShadow: {
        card:       "0 1px 3px 0 rgb(0 0 0 / 0.04), 0 1px 2px -1px rgb(0 0 0 / 0.04)",
        "card-hover": "0 4px 12px 0 rgb(0 0 0 / 0.08), 0 2px 4px -2px rgb(0 0 0 / 0.04)",
        elevated:   "0 8px 24px 0 rgb(0 0 0 / 0.12), 0 2px 8px -2px rgb(0 0 0 / 0.06)",
      },
      borderRadius: {
        xl:  "0.875rem",
        "2xl": "1rem",
      },
      animation: {
        "fade-in":   "fadeIn 0.3s ease-out",
        "slide-up":  "slideUp 0.3s ease-out",
        "pulse-soft":"pulseSoft 2s infinite",
      },
      keyframes: {
        fadeIn: {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%":   { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: "0.7" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
