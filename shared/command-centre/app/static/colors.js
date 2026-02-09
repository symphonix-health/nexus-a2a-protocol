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
  // Status Colors (colorblind-safe)
  status: {
    healthy: '#10b981',    // emerald-500
    degraded: '#f59e0b',   // amber-500
    unhealthy: '#ef4444',  // red-500
    unknown: '#6b7280',    // gray-500
  },

  // Task State Colors
  task: {
    accepted: '#3b82f6',   // blue-500
    working: '#8b5cf6',    // violet-500
    final: '#10b981',      // emerald-500
    error: '#dc2626',      // red-600
    cancelled: '#64748b',  // slate-500
  },

  // Heatmap Gradients (perceptually uniform, 5-step)
  heatmap: {
    // Latency: green (fast) → red (slow), 0-5000ms
    latency: ['#ecfdf5', '#6ee7b7', '#10b981', '#047857', '#064e3b'],
    
    // Throughput: blue spectrum, 0-100 tasks/min
    throughput: ['#eff6ff', '#93c5fd', '#3b82f6', '#1d4ed8', '#1e3a8a'],
    
    // Error Rate: white → red, 0-100%
    errorRate: ['#fef2f2', '#fecaca', '#f87171', '#dc2626', '#991b1b'],
    
    // Load: cool → hot, 0-100%
    load: ['#dbeafe', '#93c5fd', '#60a5fa', '#f59e0b', '#dc2626'],
  },

  // UI Elements
  ui: {
    background: '#0f172a',    // slate-900
    surface: '#1e293b',       // slate-800
    border: '#334155',        // slate-700
    text: '#f1f5f9',          // slate-100
    textMuted: '#94a3b8',     // slate-400
    accent: '#3b82f6',        // blue-500
  },

  // Chart Colors (distinct, colorblind-safe)
  chart: [
    '#3b82f6', // blue
    '#10b981', // emerald
    '#f59e0b', // amber
    '#8b5cf6', // violet
    '#ec4899', // pink
    '#06b6d4', // cyan
    '#84cc16', // lime
    '#f97316', // orange
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
