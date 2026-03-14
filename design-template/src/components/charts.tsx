// =============================================================================
// Design System — Chart Components
// Recharts-based data visualisation kit for the GHARRA design system.
// Brand teal palette, dark mode support, glassmorphism, smooth animations.
//
// Deps (in addition to ui.tsx deps):
//   npm install recharts
//
// Usage:
//   import { MetricCard, AreaChartCard, BarChartCard, DonutChart, ... } from "@/components/charts";
// =============================================================================

"use client";

import * as React from "react";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid,
} from "recharts";
import { TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "./ui";
import {
  Card, CardHeader, CardTitle, CardDescription, CardContent,
} from "./ui";

// ─────────────────────────────────────────────────────────────────────────────
// Palette — shared colour constants for all charts
// ─────────────────────────────────────────────────────────────────────────────

export const BRAND = "#0D7377";
export const BRAND_LIGHT = "#14919B";
export const BRAND_GLOW = "rgba(13,115,119,0.15)";

export const STATUS_COLORS: Record<string, string> = {
  active: "#10b981", suspended: "#f59e0b", revoked: "#ef4444", retired: "#94a3b8",
};

export const SERIES_COLORS = [
  "#0D7377", "#6366f1", "#f59e0b", "#ec4899",
  "#8b5cf6", "#14b8a6", "#f97316", "#06b6d4",
  "#84cc16", "#e11d48",
];

export const SEVERITY_COLORS: Record<string, string> = {
  healthy: "#10b981", degraded: "#f59e0b", critical: "#ef4444", unknown: "#94a3b8",
};

const CHART_GRID_CLASS = "stroke-surface-200 dark:stroke-surface-700";

// ─────────────────────────────────────────────────────────────────────────────
// ChartTooltip — custom Recharts tooltip with brand styling
// ─────────────────────────────────────────────────────────────────────────────

export function ChartTooltip({
  active, payload, label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900 px-3 py-2 shadow-elevated text-xs">
      {label && <p className="text-surface-500 dark:text-surface-400 mb-1">{label}</p>}
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full shrink-0" style={{ background: entry.color }} />
          <span className="text-surface-700 dark:text-surface-200 font-medium">{entry.name}:</span>
          <span className="text-surface-900 dark:text-surface-50 font-semibold">
            {typeof entry.value === "number" ? entry.value.toLocaleString() : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MetricCard — KPI card with trend indicator and optional sparkline / ring
// ─────────────────────────────────────────────────────────────────────────────

interface MetricCardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  trend?: { value: number; label: string };
  gradient?: string;
  sparkline?: { ts: string; value: number }[];
  ring?: { percent: number; color?: string };
  subtitle?: string;
  className?: string;
}

export function MetricCard({
  title, value, icon, trend,
  gradient = "bg-gradient-to-br from-brand-500 to-brand-700",
  sparkline, ring, subtitle, className,
}: MetricCardProps) {
  return (
    <Card className={cn("relative overflow-hidden group hover:shadow-card-hover transition-shadow duration-300", className)}>
      <div className={cn("absolute inset-0 opacity-[0.04] group-hover:opacity-[0.07] transition-opacity duration-300", gradient)} />
      <CardContent className="relative p-5">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium uppercase tracking-wider text-surface-500 dark:text-surface-400 mb-1">{title}</p>
            <p className="text-2xl font-bold text-surface-900 dark:text-surface-50 tracking-tight">
              {typeof value === "number" ? value.toLocaleString() : value}
            </p>
            {trend && (
              <div className="flex items-center gap-1 mt-1.5">
                {trend.value >= 0
                  ? <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />
                  : <TrendingDown className="h-3.5 w-3.5 text-red-500" />}
                <span className={cn("text-xs font-medium", trend.value >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
                  {trend.value > 0 ? "+" : ""}{trend.value}%
                </span>
                <span className="text-xs text-surface-400 dark:text-surface-500">{trend.label}</span>
              </div>
            )}
            {subtitle && <p className="text-xs text-surface-400 dark:text-surface-500 mt-1">{subtitle}</p>}
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-100 dark:bg-surface-800 text-brand-600 dark:text-brand-400">
              {icon}
            </div>
            {sparkline && sparkline.length > 1 && (
              <div className="w-20 h-8">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={sparkline}>
                    <defs>
                      <linearGradient id="mcSparkGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={BRAND} stopOpacity={0.3} />
                        <stop offset="100%" stopColor={BRAND} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <Area type="monotone" dataKey="value" stroke={BRAND} strokeWidth={1.5} fill="url(#mcSparkGrad)" isAnimationActive animationDuration={1200} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
            {ring && (
              <svg viewBox="0 0 36 36" className="w-10 h-10">
                <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" className="text-surface-200 dark:text-surface-700" strokeWidth="3" />
                <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke={ring.color ?? BRAND} strokeWidth="3" strokeDasharray={`${ring.percent}, 100`} strokeLinecap="round" className="transition-all duration-1000 ease-out" />
                <text x="18" y="20.5" textAnchor="middle" className="fill-surface-700 dark:fill-surface-200 text-[9px] font-semibold">{ring.percent}%</text>
              </svg>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// AreaChartCard — reusable area chart with gradient fill
// ─────────────────────────────────────────────────────────────────────────────

interface AreaChartCardProps {
  title: string;
  description?: string;
  data: Record<string, unknown>[];
  dataKey: string;
  xKey?: string;
  height?: number;
  color?: string;
  secondaryDataKey?: string;
  secondaryColor?: string;
  className?: string;
  gradientId?: string;
}

export function AreaChartCard({
  title, description, data, dataKey, xKey = "time",
  height = 256, color = BRAND, secondaryDataKey,
  secondaryColor = BRAND_LIGHT, className, gradientId,
}: AreaChartCardProps) {
  const gid = gradientId ?? `areaGrad_${dataKey}`;
  const gid2 = `${gid}_sec`;
  return (
    <Card className={cn("", className)}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="pb-6">
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.25} />
                  <stop offset="100%" stopColor={color} stopOpacity={0.02} />
                </linearGradient>
                {secondaryDataKey && (
                  <linearGradient id={gid2} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={secondaryColor} stopOpacity={0.2} />
                    <stop offset="100%" stopColor={secondaryColor} stopOpacity={0.02} />
                  </linearGradient>
                )}
              </defs>
              <CartesianGrid strokeDasharray="3 3" className={CHART_GRID_CLASS} vertical={false} />
              <XAxis dataKey={xKey} tick={{ fontSize: 11 }} className="text-surface-500 dark:text-surface-400" axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11 }} className="text-surface-500 dark:text-surface-400" axisLine={false} tickLine={false} width={40} />
              <Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} fill={`url(#${gid})`} isAnimationActive animationDuration={1200} animationEasing="ease-out" />
              {secondaryDataKey && (
                <Area type="monotone" dataKey={secondaryDataKey} stroke={secondaryColor} strokeWidth={1.5} fill={`url(#${gid2})`} isAnimationActive animationDuration={1400} animationEasing="ease-out" strokeDasharray="4 2" />
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// BarChartCard — horizontal or vertical bar chart
// ─────────────────────────────────────────────────────────────────────────────

interface BarChartCardProps {
  title: string;
  description?: string;
  data: Record<string, unknown>[];
  dataKey: string;
  nameKey?: string;
  height?: number;
  color?: string;
  layout?: "vertical" | "horizontal";
  colorByIndex?: boolean;
  className?: string;
  barRadius?: number;
}

export function BarChartCard({
  title, description, data, dataKey, nameKey = "name",
  height = 256, color = BRAND, layout = "horizontal",
  colorByIndex = false, className, barRadius = 4,
}: BarChartCardProps) {
  const isVertical = layout === "vertical";
  return (
    <Card className={cn("", className)}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="pb-6">
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout={isVertical ? "vertical" : "horizontal"} margin={isVertical ? { left: 20 } : undefined}>
              <CartesianGrid strokeDasharray="3 3" className={CHART_GRID_CLASS} vertical={!isVertical} horizontal={isVertical} />
              {isVertical ? (
                <>
                  <XAxis type="number" tick={{ fontSize: 11 }} className="text-surface-500 dark:text-surface-400" axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey={nameKey} tick={{ fontSize: 11 }} className="text-surface-500 dark:text-surface-400" axisLine={false} tickLine={false} width={100} />
                </>
              ) : (
                <>
                  <XAxis dataKey={nameKey} tick={{ fontSize: 11 }} className="text-surface-500 dark:text-surface-400" axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11 }} className="text-surface-500 dark:text-surface-400" axisLine={false} tickLine={false} width={40} />
                </>
              )}
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey={dataKey} fill={color} radius={[barRadius, barRadius, barRadius, barRadius]} isAnimationActive animationDuration={900} animationEasing="ease-out">
                {colorByIndex && data.map((_, i) => <Cell key={i} fill={SERIES_COLORS[i % SERIES_COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// DonutChart — pie/donut with center label and legend
// ─────────────────────────────────────────────────────────────────────────────

interface DonutChartProps {
  title: string;
  description?: string;
  data: { name: string; value: number; fill?: string }[];
  colors?: string[];
  centerLabel?: string | number;
  centerSubLabel?: string;
  height?: number;
  innerRadius?: string;
  outerRadius?: string;
  className?: string;
  showLegend?: boolean;
}

export function DonutChart({
  title, description, data, colors = SERIES_COLORS,
  centerLabel, centerSubLabel, height = 256,
  innerRadius = "55%", outerRadius = "80%",
  className, showLegend = true,
}: DonutChartProps) {
  const total = data.reduce((s, d) => s + d.value, 0);
  const displayCenter = centerLabel ?? total;
  return (
    <Card className={cn("", className)}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <div className="relative" style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data} cx="50%" cy="50%" innerRadius={innerRadius} outerRadius={outerRadius} paddingAngle={2} dataKey="value" isAnimationActive animationDuration={1000} animationEasing="ease-out">
                {data.map((d, i) => <Cell key={d.name} fill={d.fill ?? colors[i % colors.length]} />)}
              </Pie>
              <Tooltip content={<ChartTooltip />} />
            </PieChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <span className="text-2xl font-bold text-surface-900 dark:text-surface-50">
              {typeof displayCenter === "number" ? displayCenter.toLocaleString() : displayCenter}
            </span>
            {centerSubLabel && <span className="text-xs text-surface-500 dark:text-surface-400">{centerSubLabel}</span>}
          </div>
        </div>
        {showLegend && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
            {data.slice(0, 8).map((d, i) => (
              <div key={d.name} className="flex items-center gap-1.5 text-xs">
                <span className="h-2 w-2 rounded-full shrink-0" style={{ background: d.fill ?? colors[i % colors.length] }} />
                <span className="text-surface-600 dark:text-surface-300">{d.name}</span>
                <span className="text-surface-400 dark:text-surface-500">{d.value}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SloGauge — SLO burn-rate radial gauge with animated ring
// ─────────────────────────────────────────────────────────────────────────────

interface SloGaugeProps {
  title: string;
  target: number;          // e.g. 0.999
  current: number;         // e.g. 0.9994
  budgetRemaining: number; // 0–1
  totalRequests: number;
  totalErrors: number;
  className?: string;
}

function getGaugeColor(budgetPct: number): string {
  if (budgetPct > 0.5) return "#10b981";
  if (budgetPct > 0.2) return "#f59e0b";
  return "#ef4444";
}

export function SloGauge({
  title, target, current, budgetRemaining,
  totalRequests, totalErrors, className,
}: SloGaugeProps) {
  const pct = Math.round(budgetRemaining * 100);
  const color = getGaugeColor(budgetRemaining);
  const targetPct = (target * 100).toFixed(2);
  const currentPct = (current * 100).toFixed(3);
  const isMet = current >= target;
  return (
    <Card className={cn("", className)}>
      <CardHeader className="pb-2"><CardTitle className="text-sm">{title}</CardTitle></CardHeader>
      <CardContent>
        <div className="flex items-center gap-6">
          <div className="relative shrink-0">
            <svg viewBox="0 0 120 120" className="w-28 h-28">
              <circle cx="60" cy="60" r="50" fill="none" stroke="currentColor" className="text-surface-200 dark:text-surface-700" strokeWidth="10" strokeLinecap="round" />
              <circle cx="60" cy="60" r="50" fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" strokeDasharray={`${pct * 3.14} 314`} transform="rotate(-90 60 60)" className="transition-all duration-1000 ease-out" />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-lg font-bold text-surface-900 dark:text-surface-50">{pct}%</span>
              <span className="text-[10px] text-surface-500 dark:text-surface-400">budget</span>
            </div>
          </div>
          <div className="flex-1 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-surface-500 dark:text-surface-400">Target</span>
              <span className="text-xs font-semibold text-surface-900 dark:text-surface-50">{targetPct}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-surface-500 dark:text-surface-400">Current</span>
              <span className={cn("text-xs font-semibold", isMet ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>{currentPct}%</span>
            </div>
            <div className="h-px bg-surface-200 dark:bg-surface-700" />
            <div className="flex items-center justify-between">
              <span className="text-xs text-surface-500 dark:text-surface-400">Total</span>
              <span className="text-xs font-medium text-surface-700 dark:text-surface-200">{totalRequests.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-surface-500 dark:text-surface-400">Errors</span>
              <span className="text-xs font-medium text-red-600 dark:text-red-400">{totalErrors.toLocaleString()}</span>
            </div>
            <div className="mt-2">
              <span className={cn("inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full", isMet ? "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400" : "bg-red-100 dark:bg-red-950/40 text-red-700 dark:text-red-400")}>
                {isMet ? "SLO MET" : "SLO BREACHED"}
              </span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SparklineChart — tiny inline area sparkline
// ─────────────────────────────────────────────────────────────────────────────

interface SparklineChartProps {
  data: { value: number }[];
  color?: string;
  width?: number;
  height?: number;
}

export function SparklineChart({ data, color = BRAND, width = 80, height = 32 }: SparklineChartProps) {
  if (!data || data.length < 2) return null;
  return (
    <div style={{ width, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={1.5} fill="url(#sparkGrad)" isAnimationActive animationDuration={800} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// LatencyHistogram — specialized bar chart for latency bucket distribution
// ─────────────────────────────────────────────────────────────────────────────

interface LatencyHistogramProps {
  title: string;
  description?: string;
  buckets: { le: string; count: number }[];
  height?: number;
  className?: string;
}

function bucketToLabel(le: string): string {
  if (le === "+Inf") return ">10s";
  const n = parseFloat(le);
  if (n < 0.001) return `${n * 1000000}µs`;
  if (n < 1) return `${Math.round(n * 1000)}ms`;
  return `${n}s`;
}

function bucketColor(le: string): string {
  if (le === "+Inf") return "#ef4444";
  const n = parseFloat(le);
  if (n <= 0.1) return "#10b981";
  if (n <= 0.5) return BRAND;
  if (n <= 1.0) return BRAND_LIGHT;
  if (n <= 2.5) return "#f59e0b";
  return "#ef4444";
}

export function LatencyHistogram({ title, description, buckets, height = 220, className }: LatencyHistogramProps) {
  const barData = buckets.map((b, i) => {
    const prevCount = i > 0 ? buckets[i - 1].count : 0;
    return { label: bucketToLabel(b.le), count: Math.max(0, b.count - prevCount), le: b.le };
  });
  return (
    <Card className={cn("", className)}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="pb-6">
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData}>
              <CartesianGrid strokeDasharray="3 3" className={CHART_GRID_CLASS} vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} className="text-surface-500 dark:text-surface-400" axisLine={false} tickLine={false} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 11 }} className="text-surface-500 dark:text-surface-400" axisLine={false} tickLine={false} width={40} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]} isAnimationActive animationDuration={900}>
                {barData.map((d, i) => <Cell key={i} fill={bucketColor(d.le)} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
