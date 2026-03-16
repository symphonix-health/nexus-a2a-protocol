/**
 * NEXUS Color System — JavaScript bridge
 *
 * Reads all colour values from CSS custom properties defined in nexus-theme.css.
 * This means CSS is the single source of truth — changing a token in the theme
 * file automatically flows through to charts, heatmaps, and dynamic JS styling.
 *
 * Public API (unchanged):
 *   getStatusColor(status)
 *   getTaskColor(state)
 *   getHeatmapColor(value, min, max, type)
 *   getLatencyColor(ms)
 *   getThroughputColor(tpm)
 *   getErrorRateColor(rate)
 *   getLoadColor(fraction)
 *   getPulseOpacity(ageMs, duration)
 *   COLORS  — raw palette object (for Chart.js dataset config etc.)
 */

/** Read a CSS custom property from :root */
function _css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * Live colour palette — values are resolved at call time from the active theme.
 * Assign COLORS once at startup; call _refreshColors() if the theme ever changes.
 */
const COLORS = {
  // ── Status indicators ─────────────────────────────────────────────────────
  status: {
    healthy:   null,
    degraded:  null,
    unhealthy: null,
    unknown:   null,
  },

  // ── Task state colours ─────────────────────────────────────────────────────
  task: {
    accepted:  null,
    working:   null,
    final:     null,
    error:     null,
    cancelled: null,
  },

  // ── UI element colours ─────────────────────────────────────────────────────
  ui: {
    background: null,
    surface:    null,
    border:     null,
    text:       null,
    textMuted:  null,
    accent:     null,
  },

  // ── Heatmap gradients (perceptually uniform, 5-step) ──────────────────────
  // These are static arrays — they reference palette primitives directly
  // because CSS vars cannot encode array structures.
  heatmap: {
    // Latency: green (fast) → red (slow), 0–5 000 ms
    latency:    ['#ecfdf5', '#6ee7b7', '#10b981', '#047857', '#064e3b'],
    // Throughput: blue spectrum, 0–100 tasks/min
    throughput: ['#eff6ff', '#93c5fd', '#3b82f6', '#1d4ed8', '#1e3a8a'],
    // Error rate: white → red, 0–100 %
    errorRate:  ['#fef2f2', '#fecaca', '#f87171', '#dc2626', '#991b1b'],
    // Load: cool → hot, 0–100 %
    load:       ['#dbeafe', '#93c5fd', '#60a5fa', '#f59e0b', '#dc2626'],
  },

  // ── Chart dataset colours (distinct, colorblind-safe 8-step palette) ──────
  // Kept as literals; these are aesthetic chart series colours, not semantic.
  chart: [
    '#0D7377', // brand-600
    '#6366f1', // indigo
    '#f59e0b', // amber
    '#ec4899', // pink
    '#8b5cf6', // violet
    '#14b8a6', // teal-light
    '#f97316', // orange
    '#06b6d4', // cyan
    '#84cc16', // lime
    '#e11d48', // rose
  ],
};

/** Populate every CSS-var-backed field from the live theme. */
function _refreshColors() {
  COLORS.status.healthy   = _css('--status-healthy');
  COLORS.status.degraded  = _css('--status-degraded');
  COLORS.status.unhealthy = _css('--status-unhealthy');
  COLORS.status.unknown   = _css('--status-unknown');

  COLORS.task.accepted  = _css('--task-accepted');
  COLORS.task.working   = _css('--task-working');
  COLORS.task.final     = _css('--task-final');
  COLORS.task.error     = _css('--task-error');
  COLORS.task.cancelled = _css('--task-cancelled');

  COLORS.ui.background = _css('--bg-primary');
  COLORS.ui.surface    = _css('--bg-surface');
  COLORS.ui.border     = _css('--border-color');
  COLORS.ui.text       = _css('--text-primary');
  COLORS.ui.textMuted  = _css('--text-muted');
  COLORS.ui.accent     = _css('--accent');
}

// Resolve on DOMContentLoaded so the theme stylesheet has been parsed.
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _refreshColors);
  } else {
    _refreshColors();
  }
}

// ── Public helper functions (API unchanged) ──────────────────────────────────

/** Get colour for a given agent health status. */
function getStatusColor(status) {
  return COLORS.status[status] || COLORS.status.unknown;
}

/** Get colour for a given task state. */
function getTaskColor(state) {
  return COLORS.task[state] || COLORS.ui.textMuted;
}

/**
 * Map a numeric value to a heatmap colour.
 * @param {number} value
 * @param {number} min
 * @param {number} max
 * @param {'latency'|'throughput'|'errorRate'|'load'} type
 * @returns {string} hex colour
 */
function getHeatmapColor(value, min, max, type = 'latency') {
  const gradient = COLORS.heatmap[type] || COLORS.heatmap.latency;
  const normalized = Math.max(0, Math.min(1, (value - min) / (max - min || 1)));
  const idx = normalized * (gradient.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return gradient[lo];
  return interpolateColor(gradient[lo], gradient[hi], idx - lo);
}

/** Interpolate between two hex colours. */
function interpolateColor(color1, color2, fraction) {
  const c1 = hexToRgb(color1);
  const c2 = hexToRgb(color2);
  return rgbToHex(
    Math.round(c1.r + (c2.r - c1.r) * fraction),
    Math.round(c1.g + (c2.g - c1.g) * fraction),
    Math.round(c1.b + (c2.b - c1.b) * fraction),
  );
}

function hexToRgb(hex) {
  const r = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return r ? { r: parseInt(r[1], 16), g: parseInt(r[2], 16), b: parseInt(r[3], 16) } : { r: 0, g: 0, b: 0 };
}

function rgbToHex(r, g, b) {
  return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('');
}

/** Convenience wrappers */
function getLatencyColor(ms)          { return getHeatmapColor(ms,   0,   5000, 'latency'); }
function getThroughputColor(tpm)      { return getHeatmapColor(tpm,  0,    100, 'throughput'); }
function getErrorRateColor(rate)      { return getHeatmapColor(rate, 0,      1, 'errorRate'); }
function getLoadColor(fraction)       { return getHeatmapColor(fraction, 0, 1, 'load'); }

/**
 * Temporal pulse opacity — fades from 1.0 → 0.3 over `duration` ms.
 * @param {number} ageMs
 * @param {number} duration  default 2 000 ms
 * @returns {number} 0.3–1.0
 */
function getPulseOpacity(ageMs, duration = 2000) {
  if (ageMs >= duration) return 0.3;
  return 1.0 - 0.7 * (ageMs / duration);
}

// CommonJS export for test environments
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    COLORS,
    getStatusColor,
    getTaskColor,
    getHeatmapColor,
    getLatencyColor,
    getThroughputColor,
    getErrorRateColor,
    getLoadColor,
    getPulseOpacity,
    interpolateColor,
  };
}
