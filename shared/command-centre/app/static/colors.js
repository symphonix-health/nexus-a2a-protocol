/**
 * Color Palette System for NEXUS-A2A Command Centre
 * 
 * Provides colorblind-safe, perceptually uniform color schemes for:
 * - Agent health status indicators
 * - Task state transitions
 * - Heatmap gradients (latency, throughput, error rates)
 * - Temporal pulse animations
 * 
 * All colors meet WCAG AA contrast ratios for accessibility.
 */

const COLORS = {
  // ── Brand palette (from design-template) ─────────────────────────
  brand: {
    50:  '#E0F7FA',
    100: '#B2EBF2',
    200: '#80DEEA',
    300: '#4DD0E1',
    400: '#26C6DA',
    500: '#14919B',
    600: '#0D7377',
    700: '#095E61',
    800: '#064A4D',
    900: '#033638',
    950: '#012224',
  },

  // Status Colors (colorblind-safe)
  status: {
    healthy: '#10b981',    // emerald-500
    degraded: '#f59e0b',   // amber-500
    unhealthy: '#ef4444',  // red-500
    unknown: '#64748B',    // surface-500
  },

  // Task State Colors (brand-tinted)
  task: {
    accepted: '#0D7377',   // brand-600
    working: '#8b5cf6',    // violet-500
    final: '#10b981',      // emerald-500
    error: '#dc2626',      // red-600
    cancelled: '#64748b',  // slate-500
  },

  // Heatmap Gradients (perceptually uniform, 5-step)
  heatmap: {
    // Latency: green (fast) → red (slow), 0-5000ms
    latency: ['#ecfdf5', '#6ee7b7', '#10b981', '#047857', '#064e3b'],

    // Throughput: brand spectrum, 0-100 tasks/min
    throughput: ['#E0F7FA', '#80DEEA', '#14919B', '#0D7377', '#012224'],

    // Error Rate: white → red, 0-100%
    errorRate: ['#fef2f2', '#fecaca', '#f87171', '#dc2626', '#991b1b'],

    // Load: cool → hot, 0-100%
    load: ['#E0F7FA', '#80DEEA', '#26C6DA', '#f59e0b', '#dc2626'],
  },

  // UI Elements (design-system surface palette)
  ui: {
    background: '#020617',    // surface-950
    surface: '#0F172A',       // surface-900
    elevated: '#1E293B',      // surface-800
    border: '#334155',        // surface-700
    text: '#F1F5F7',          // surface-100
    textMuted: '#8E9BAA',     // surface-400
    accent: '#0D7377',        // brand-600
  },

  // Chart Colors (distinct, colorblind-safe — brand-first)
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

/**
 * Get color for a given status value
 */
function getStatusColor(status) {
  return COLORS.status[status] || COLORS.status.unknown;
}

/**
 * Get color for a given task state
 */
function getTaskColor(state) {
  return COLORS.task[state] || COLORS.ui.textMuted;
}

/**
 * Map a numeric value to a heatmap color
 * @param {number} value - The value to map
 * @param {number} min - Minimum value in range
 * @param {number} max - Maximum value in range
 * @param {string} type - Heatmap type: 'latency', 'throughput', 'errorRate', 'load'
 * @returns {string} Hex color code
 */
function getHeatmapColor(value, min, max, type = 'latency') {
  const gradient = COLORS.heatmap[type] || COLORS.heatmap.latency;
  
  // Normalize value to 0-1
  const normalized = Math.max(0, Math.min(1, (value - min) / (max - min || 1)));
  
  // Map to gradient index
  const idx = normalized * (gradient.length - 1);
  const lowerIdx = Math.floor(idx);
  const upperIdx = Math.ceil(idx);
  const fraction = idx - lowerIdx;
  
  if (lowerIdx === upperIdx) {
    return gradient[lowerIdx];
  }
  
  // Interpolate between two colors
  return interpolateColor(gradient[lowerIdx], gradient[upperIdx], fraction);
}

/**
 * Interpolate between two hex colors
 */
function interpolateColor(color1, color2, fraction) {
  const c1 = hexToRgb(color1);
  const c2 = hexToRgb(color2);
  
  const r = Math.round(c1.r + (c2.r - c1.r) * fraction);
  const g = Math.round(c1.g + (c2.g - c1.g) * fraction);
  const b = Math.round(c1.b + (c2.b - c1.b) * fraction);
  
  return rgbToHex(r, g, b);
}

/**
 * Convert hex to RGB
 */
function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16),
  } : { r: 0, g: 0, b: 0 };
}

/**
 * Convert RGB to hex
 */
function rgbToHex(r, g, b) {
  return '#' + [r, g, b].map(x => {
    const hex = x.toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  }).join('');
}

/**
 * Get latency-based color (convenience function)
 */
function getLatencyColor(latencyMs) {
  return getHeatmapColor(latencyMs, 0, 5000, 'latency');
}

/**
 * Get throughput-based color (convenience function)
 */
function getThroughputColor(tasksPerMin) {
  return getHeatmapColor(tasksPerMin, 0, 100, 'throughput');
}

/**
 * Get error rate-based color (convenience function)
 */
function getErrorRateColor(errorRate) {
  return getHeatmapColor(errorRate, 0, 1, 'errorRate');
}

/**
 * Get load-based color (convenience function)
 */
function getLoadColor(loadFraction) {
  return getHeatmapColor(loadFraction, 0, 1, 'load');
}

/**
 * Apply temporal pulse animation via opacity
 * @param {number} ageMs - Age of event in milliseconds
 * @param {number} duration - Pulse duration in ms (default 2000)
 * @returns {number} Opacity value 0.3-1.0
 */
function getPulseOpacity(ageMs, duration = 2000) {
  if (ageMs >= duration) return 0.3;
  const progress = ageMs / duration;
  return 1.0 - (0.7 * progress); // Fade from 1.0 to 0.3
}

// Export for use in modules or inline scripts
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
