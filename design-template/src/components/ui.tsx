// =============================================================================
// Design System — single-file UI kit
// Copy this file + tailwind.config.ts + globals.css into any project.
//
// Deps: clsx  tailwind-merge  class-variance-authority  lucide-react
//   npm install clsx tailwind-merge class-variance-authority lucide-react
//
// Usage:
//   import { Button, Badge, Card, Input, ... } from "@/components/ui";
// =============================================================================

"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  Loader2, X, ChevronDown, Inbox,
} from "lucide-react";

// ─────────────────────────────────────────────────────────────────────────────
// Utility
// ─────────────────────────────────────────────────────────────────────────────

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ─────────────────────────────────────────────────────────────────────────────
// Button
// Variants: primary | secondary | ghost | danger | outline
// Sizes:    sm | md | lg | icon
// Props:    loading, disabled
// ─────────────────────────────────────────────────────────────────────────────

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap",
    "rounded-lg font-medium transition-all duration-200",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-brand-500/50",
    "disabled:pointer-events-none disabled:opacity-50",
    "active:scale-[0.98]",
  ].join(" "),
  {
    variants: {
      variant: {
        primary:   "bg-brand-600 text-white shadow-sm hover:bg-brand-700 dark:bg-brand-500 dark:hover:bg-brand-600",
        secondary: "bg-surface-100 text-surface-700 shadow-sm hover:bg-surface-200 dark:bg-surface-800 dark:text-surface-200 dark:hover:bg-surface-700",
        ghost:     "text-surface-600 hover:bg-surface-100 dark:text-surface-400 dark:hover:bg-surface-800",
        danger:    "bg-red-600 text-white shadow-sm hover:bg-red-700",
        outline:   "border border-surface-300 bg-transparent text-surface-700 hover:bg-surface-50 dark:border-surface-600 dark:text-surface-300 dark:hover:bg-surface-800",
      },
      size: {
        sm:   "h-8 px-3 text-xs",
        md:   "h-9 px-4 text-sm",
        lg:   "h-11 px-6 text-base",
        icon: "h-9 w-9 p-0",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading = false, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin shrink-0" aria-hidden="true" />}
      {children}
    </button>
  ),
);
Button.displayName = "Button";

// ─────────────────────────────────────────────────────────────────────────────
// Badge
// Variants: default | success | warning | danger | info | outline
// Props:    dot (coloured prefix dot)
// ─────────────────────────────────────────────────────────────────────────────

const badgeVariants = {
  default: "bg-surface-100 text-surface-700 dark:bg-surface-800 dark:text-surface-300",
  success: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400",
  warning: "bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400",
  danger:  "bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-400",
  info:    "bg-brand-50 text-brand-700 dark:bg-brand-950/50 dark:text-brand-400",
  outline: "bg-transparent border border-surface-300 text-surface-600 dark:border-surface-600 dark:text-surface-400",
} as const;

export type BadgeVariant = keyof typeof badgeVariants;

const dotColors: Record<BadgeVariant, string> = {
  default: "bg-surface-400",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger:  "bg-red-500",
  info:    "bg-brand-500",
  outline: "bg-surface-400",
};

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  dot?: boolean;
}

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = "default", dot = false, children, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium leading-5 transition-colors",
        badgeVariants[variant],
        className,
      )}
      {...props}
    >
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", dotColors[variant])} aria-hidden="true" />}
      {children}
    </span>
  ),
);
Badge.displayName = "Badge";

// ─────────────────────────────────────────────────────────────────────────────
// Card  (compound: Card > CardHeader > CardTitle + CardDescription
//                      > CardContent
//                      > CardFooter)
// Variants: default | elevated | interactive | glass
// ─────────────────────────────────────────────────────────────────────────────

const cardVariants = {
  default:     "bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-700 shadow-card",
  elevated:    "bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-700 shadow-elevated",
  interactive: "bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-700 shadow-card hover:shadow-card-hover hover:border-brand-400/40 dark:hover:border-brand-500/40 cursor-pointer transition-all duration-200",
  glass:       "bg-white/60 dark:bg-surface-900/60 backdrop-blur-xl border border-white/20 dark:border-surface-700/50 shadow-card",
} as const;

export type CardVariant = keyof typeof cardVariants;

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> { variant?: CardVariant; }

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant = "default", ...props }, ref) => (
    <div ref={ref} className={cn("rounded-xl", cardVariants[variant], className)} {...props} />
  ),
);
Card.displayName = "Card";

export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1.5 px-6 pt-6 pb-2", className)} {...props} />
  ),
);
CardHeader.displayName = "CardHeader";

export const CardTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn("text-base font-semibold leading-tight tracking-tight text-surface-900 dark:text-surface-50", className)} {...props} />
  ),
);
CardTitle.displayName = "CardTitle";

export const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn("text-sm text-surface-500 dark:text-surface-400", className)} {...props} />
  ),
);
CardDescription.displayName = "CardDescription";

export const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn("px-6 py-4", className)} {...props} />,
);
CardContent.displayName = "CardContent";

export const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center px-6 pb-6 pt-2 border-t border-surface-100 dark:border-surface-800", className)} {...props} />
  ),
);
CardFooter.displayName = "CardFooter";

// ─────────────────────────────────────────────────────────────────────────────
// Input
// Props: label, helperText, error, prefix (icon), suffix (icon), wrapperClassName
// ─────────────────────────────────────────────────────────────────────────────

export interface InputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "prefix"> {
  label?: string;
  helperText?: string;
  error?: string;
  prefix?: React.ReactNode;
  suffix?: React.ReactNode;
  wrapperClassName?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, helperText, error, prefix, suffix, id, wrapperClassName, ...props }, ref) => {
    const inputId = id ?? React.useId();
    const hasError = !!error;
    return (
      <div className={cn("flex flex-col gap-1.5", wrapperClassName)}>
        {label && (
          <label htmlFor={inputId} className="text-sm font-medium text-surface-700 dark:text-surface-300">
            {label}
          </label>
        )}
        <div className="relative flex items-center">
          {prefix && <span className="pointer-events-none absolute left-3 flex items-center text-surface-400">{prefix}</span>}
          <input
            ref={ref}
            id={inputId}
            className={cn(
              "flex h-9 w-full rounded-lg border bg-white px-3 py-2 text-sm text-surface-900",
              "placeholder:text-surface-400 transition-colors duration-200",
              "focus:outline-none focus:ring-2 focus:ring-offset-1",
              "disabled:cursor-not-allowed disabled:opacity-50",
              "dark:bg-surface-900 dark:text-surface-100 dark:placeholder:text-surface-500",
              hasError
                ? "border-red-400 focus:ring-red-500/30 dark:border-red-500"
                : "border-surface-300 focus:border-brand-500 focus:ring-brand-500/30 dark:border-surface-600 dark:focus:border-brand-400",
              prefix && "pl-10",
              suffix && "pr-10",
              className,
            )}
            aria-invalid={hasError}
            aria-describedby={hasError ? `${inputId}-error` : helperText ? `${inputId}-helper` : undefined}
            {...props}
          />
          {suffix && <span className="pointer-events-none absolute right-3 flex items-center text-surface-400">{suffix}</span>}
        </div>
        {hasError && <p id={`${inputId}-error`} className="text-xs text-red-600 dark:text-red-400" role="alert">{error}</p>}
        {!hasError && helperText && <p id={`${inputId}-helper`} className="text-xs text-surface-500 dark:text-surface-400">{helperText}</p>}
      </div>
    );
  },
);
Input.displayName = "Input";

// ─────────────────────────────────────────────────────────────────────────────
// Select — native <select> with design-system styling
// Props: label, wrapperClassName
// ─────────────────────────────────────────────────────────────────────────────

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  wrapperClassName?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, id, wrapperClassName, children, ...props }, ref) => {
    const selectId = id ?? React.useId();
    return (
      <div className={cn("flex flex-col gap-1.5", wrapperClassName)}>
        {label && (
          <label htmlFor={selectId} className="text-sm font-medium text-surface-700 dark:text-surface-300">
            {label}
          </label>
        )}
        <div className="relative">
          <select
            ref={ref}
            id={selectId}
            className={cn(
              "flex h-9 w-full appearance-none rounded-lg border bg-white px-3 py-2 pr-8 text-sm",
              "text-surface-900 dark:text-surface-100",
              "border-surface-300 dark:border-surface-600 dark:bg-surface-900",
              "focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500",
              "disabled:cursor-not-allowed disabled:opacity-50 transition-colors duration-200",
              className,
            )}
            {...props}
          >
            {children}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-400" />
        </div>
      </div>
    );
  },
);
Select.displayName = "Select";

// ─────────────────────────────────────────────────────────────────────────────
// Dialog  (compound: Dialog > DialogContent > DialogTitle
//                                           > DialogDescription
//                                           > DialogFooter)
// Sizes: sm | md | lg | xl
// Features: Escape-to-close, body scroll lock, backdrop click to dismiss
// ─────────────────────────────────────────────────────────────────────────────

interface DialogCtx { onClose: () => void; }
const DialogCtx = React.createContext<DialogCtx | null>(null);
const useDialog = () => {
  const ctx = React.useContext(DialogCtx);
  if (!ctx) throw new Error("Dialog sub-components must be inside <Dialog />");
  return ctx;
};

export interface DialogProps { open: boolean; onClose: () => void; children: React.ReactNode; }

export function Dialog({ open, onClose, children }: DialogProps) {
  React.useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  React.useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  if (!open) return null;

  return (
    <DialogCtx.Provider value={{ onClose }}>
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        <div className="absolute inset-0 bg-black/40 backdrop-blur-sm animate-fade-in" onClick={onClose} aria-hidden="true" />
        {children}
      </div>
    </DialogCtx.Provider>
  );
}

const dialogSizes = { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl" };

export interface DialogContentProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: keyof typeof dialogSizes;
}

export const DialogContent = React.forwardRef<HTMLDivElement, DialogContentProps>(
  ({ className, size = "md", children, ...props }, ref) => {
    const { onClose } = useDialog();
    return (
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        className={cn(
          "relative z-10 w-full mx-4", dialogSizes[size],
          "rounded-xl bg-white dark:bg-surface-900",
          "border border-surface-200 dark:border-surface-700 shadow-elevated",
          "animate-[fadeIn_0.2s_ease-out] [animation-fill-mode:both]",
          className,
        )}
        {...props}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close dialog"
          className="absolute right-4 top-4 rounded-md p-1 text-surface-400 hover:text-surface-600 dark:hover:text-surface-200 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-brand-500/50"
        >
          <X className="h-4 w-4" />
        </button>
        {children}
      </div>
    );
  },
);
DialogContent.displayName = "DialogContent";

export const DialogTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h2 ref={ref} className={cn("px-6 pt-6 pb-2 text-lg font-semibold text-surface-900 dark:text-surface-50", className)} {...props} />
  ),
);
DialogTitle.displayName = "DialogTitle";

export const DialogDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn("px-6 pb-4 text-sm text-surface-500 dark:text-surface-400", className)} {...props} />
  ),
);
DialogDescription.displayName = "DialogDescription";

export const DialogFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center justify-end gap-3 px-6 py-4 border-t border-surface-100 dark:border-surface-800", className)} {...props} />
  ),
);
DialogFooter.displayName = "DialogFooter";

// ─────────────────────────────────────────────────────────────────────────────
// Tabs  (compound: Tabs > TabList > Tab
//                      > TabPanel)
// Supports controlled (value + onValueChange) and uncontrolled (defaultValue)
// ─────────────────────────────────────────────────────────────────────────────

interface TabsCtx { activeTab: string; setActiveTab: (id: string) => void; }
const TabsCtx = React.createContext<TabsCtx | null>(null);
const useTabs = () => {
  const ctx = React.useContext(TabsCtx);
  if (!ctx) throw new Error("Tab sub-components must be inside <Tabs />");
  return ctx;
};

export interface TabsProps {
  defaultValue: string;
  value?: string;
  onValueChange?: (v: string) => void;
  children: React.ReactNode;
  className?: string;
}

export function Tabs({ defaultValue, value, onValueChange, children, className }: TabsProps) {
  const [internal, setInternal] = React.useState(defaultValue);
  const active = value ?? internal;
  const setActive = React.useCallback((id: string) => {
    if (!value) setInternal(id);
    onValueChange?.(id);
  }, [value, onValueChange]);

  return (
    <TabsCtx.Provider value={{ activeTab: active, setActiveTab: setActive }}>
      <div className={cn("flex flex-col", className)}>{children}</div>
    </TabsCtx.Provider>
  );
}

export const TabList = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} role="tablist" className={cn("relative flex border-b border-surface-200 dark:border-surface-700", className)} {...props} />
  ),
);
TabList.displayName = "TabList";

export interface TabProps extends React.ButtonHTMLAttributes<HTMLButtonElement> { value: string; }

export const Tab = React.forwardRef<HTMLButtonElement, TabProps>(
  ({ className, value, children, ...props }, ref) => {
    const { activeTab, setActiveTab } = useTabs();
    const isActive = activeTab === value;
    return (
      <button
        ref={ref}
        type="button"
        role="tab"
        aria-selected={isActive}
        tabIndex={isActive ? 0 : -1}
        onClick={() => setActiveTab(value)}
        className={cn(
          "relative px-4 py-2.5 text-sm font-medium transition-colors duration-200",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50 focus-visible:ring-inset",
          isActive
            ? "text-brand-600 dark:text-brand-400"
            : "text-surface-500 hover:text-surface-700 dark:text-surface-400 dark:hover:text-surface-200",
          className,
        )}
        {...props}
      >
        {children}
        {isActive && <span className="absolute inset-x-0 -bottom-px h-0.5 bg-brand-600 dark:bg-brand-400 rounded-full" aria-hidden="true" />}
      </button>
    );
  },
);
Tab.displayName = "Tab";

export interface TabPanelProps extends React.HTMLAttributes<HTMLDivElement> { value: string; }

export const TabPanel = React.forwardRef<HTMLDivElement, TabPanelProps>(
  ({ className, value, children, ...props }, ref) => {
    const { activeTab } = useTabs();
    if (activeTab !== value) return null;
    return <div ref={ref} role="tabpanel" tabIndex={0} className={cn("animate-fade-in pt-4", className)} {...props}>{children}</div>;
  },
);
TabPanel.displayName = "TabPanel";

// ─────────────────────────────────────────────────────────────────────────────
// StatusDot — coloured indicator with optional pulse ring
// Built-in statuses: healthy | degraded | critical | unknown | active |
//                    suspended | revoked | retired | connected | disconnected
// Extend statusColorMap with your own domain keys.
// ─────────────────────────────────────────────────────────────────────────────

export const statusColorMap: Record<string, string> = {
  healthy:      "bg-emerald-500",
  degraded:     "bg-amber-500",
  critical:     "bg-red-500",
  unknown:      "bg-surface-400 dark:bg-surface-500",
  active:       "bg-emerald-500",
  suspended:    "bg-amber-500",
  revoked:      "bg-red-500",
  retired:      "bg-surface-400 dark:bg-surface-500",
  connected:    "bg-emerald-500",
  disconnected: "bg-red-500",
};

const pulseRingMap: Record<string, string> = {
  healthy: "bg-emerald-500/30", degraded: "bg-amber-500/30", critical: "bg-red-500/30",
  active:  "bg-emerald-500/30", suspended: "bg-amber-500/30", revoked: "bg-red-500/30",
  connected: "bg-emerald-500/30", disconnected: "bg-red-500/30",
};

const dotSize  = { sm: "h-1.5 w-1.5", md: "h-2 w-2",   lg: "h-2.5 w-2.5" };
const ringSize = { sm: "h-3 w-3",     md: "h-4 w-4",   lg: "h-5 w-5"     };

export interface StatusDotProps extends React.HTMLAttributes<HTMLSpanElement> {
  status: string;
  pulse?: boolean;
  size?: "sm" | "md" | "lg";
}

export const StatusDot = React.forwardRef<HTMLSpanElement, StatusDotProps>(
  ({ className, status, pulse = false, size = "md", ...props }, ref) => {
    const color = statusColorMap[status] ?? statusColorMap.unknown;
    const ring  = pulseRingMap[status]   ?? "bg-surface-400/30";
    return (
      <span ref={ref} className={cn("relative inline-flex shrink-0", className)} role="img" aria-label={status} {...props}>
        {pulse && <span className={cn("absolute inset-0 m-auto rounded-full animate-ping", ringSize[size], ring)} aria-hidden="true" />}
        <span className={cn("relative rounded-full", dotSize[size], color)} />
      </span>
    );
  },
);
StatusDot.displayName = "StatusDot";

// ─────────────────────────────────────────────────────────────────────────────
// Skeleton — animated loading placeholders
// Variants: text | circle | rect | card
// Presets:  SkeletonText (N lines)  SkeletonCard (avatar + text + button)
// ─────────────────────────────────────────────────────────────────────────────

const skeletonBase = "animate-pulse rounded-md bg-surface-200/70 dark:bg-surface-700/50";

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "text" | "circle" | "rect" | "card";
}

export const Skeleton = React.forwardRef<HTMLDivElement, SkeletonProps>(
  ({ className, variant = "text", ...props }, ref) => {
    const v = { text: "h-4 w-full rounded", circle: "h-10 w-10 rounded-full", rect: "h-24 w-full rounded-lg", card: "h-40 w-full rounded-xl" };
    return <div ref={ref} className={cn(skeletonBase, v[variant], className)} aria-hidden="true" {...props} />;
  },
);
Skeleton.displayName = "Skeleton";

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2.5", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} variant="text" className={cn(i === lines - 1 && "w-2/3")} />
      ))}
    </div>
  );
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-xl border border-surface-200 dark:border-surface-700 p-6 space-y-4", className)}>
      <div className="flex items-center gap-3">
        <Skeleton variant="circle" className="h-8 w-8" />
        <Skeleton variant="text" className="h-4 w-32" />
      </div>
      <SkeletonText lines={2} />
      <Skeleton variant="rect" className="h-8 w-24" />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// EmptyState — centred placeholder for empty lists / tables
// Props: icon, title, description, action
// ─────────────────────────────────────────────────────────────────────────────

export interface EmptyStateProps extends React.HTMLAttributes<HTMLDivElement> {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export const EmptyState = React.forwardRef<HTMLDivElement, EmptyStateProps>(
  ({ className, icon, title, description, action, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col items-center justify-center py-16 px-6 text-center", className)} {...props}>
      <div className="flex items-center justify-center h-14 w-14 rounded-xl mb-5 bg-surface-100 dark:bg-surface-800 text-surface-400 dark:text-surface-500">
        {icon ?? <Inbox className="h-6 w-6" />}
      </div>
      <h3 className="text-base font-semibold text-surface-900 dark:text-surface-50 mb-1.5">{title}</h3>
      {description && <p className="text-sm text-surface-500 dark:text-surface-400 max-w-sm mb-6">{description}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  ),
);
EmptyState.displayName = "EmptyState";

// ─────────────────────────────────────────────────────────────────────────────
// Table  (compound: Table > TableHeader > TableRow > TableHead
//                         > TableBody   > TableRow > TableCell
//                         > TableFooter)
// Semantic HTML table with design-system styling.
// ─────────────────────────────────────────────────────────────────────────────

export const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => (
    <div className="relative w-full overflow-auto scrollbar-thin">
      <table ref={ref} className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  ),
);
Table.displayName = "Table";

export const TableHeader = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <thead ref={ref} className={cn("[&_tr]:border-b", className)} {...props} />
  ),
);
TableHeader.displayName = "TableHeader";

export const TableBody = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <tbody ref={ref} className={cn("[&_tr:last-child]:border-0", className)} {...props} />
  ),
);
TableBody.displayName = "TableBody";

export const TableFooter = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <tfoot ref={ref} className={cn("border-t bg-surface-50/50 dark:bg-surface-800/50 font-medium [&>tr]:last:border-b-0", className)} {...props} />
  ),
);
TableFooter.displayName = "TableFooter";

export const TableRow = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr
      ref={ref}
      className={cn(
        "border-b border-surface-200 dark:border-surface-700 transition-colors",
        "hover:bg-surface-50/50 dark:hover:bg-surface-800/50",
        "data-[state=selected]:bg-brand-50/50 dark:data-[state=selected]:bg-brand-950/30",
        className,
      )}
      {...props}
    />
  ),
);
TableRow.displayName = "TableRow";

export const TableHead = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th
      ref={ref}
      className={cn(
        "h-10 px-4 text-left align-middle font-medium text-surface-500 dark:text-surface-400",
        "text-xs uppercase tracking-wider",
        "[&:has([role=checkbox])]:pr-0",
        className,
      )}
      {...props}
    />
  ),
);
TableHead.displayName = "TableHead";

export const TableCell = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <td
      ref={ref}
      className={cn("px-4 py-3 align-middle text-surface-700 dark:text-surface-300 [&:has([role=checkbox])]:pr-0", className)}
      {...props}
    />
  ),
);
TableCell.displayName = "TableCell";
