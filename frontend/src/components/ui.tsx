import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  Clock,
  Loader2,
  type LucideIcon,
  XCircle,
} from "lucide-react";
import {
  forwardRef,
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { Link, type LinkProps } from "react-router";
import { ApiError } from "../api/client";

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

// ---------------------------------------------------------------- buttons

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const buttonBase =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-50";
const buttonVariants: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-strong",
  secondary: "border border-line-strong bg-surface text-ink hover:bg-sunken",
  ghost: "text-ink-2 hover:bg-sunken hover:text-ink",
  danger: "bg-critical text-white hover:bg-critical-ink",
};
const buttonSizes: Record<Size, string> = { sm: "h-7 px-2.5 text-[13px]", md: "h-9 px-3.5 text-sm" };

export function buttonClass(variant: Variant = "secondary", size: Size = "md"): string {
  return cx(buttonBase, buttonVariants[variant], buttonSizes[size]);
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: LucideIcon;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon: Icon, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cx(buttonClass(variant, size), className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <Loader2 className="size-4 animate-spin" aria-hidden />
      ) : (
        Icon && <Icon className="size-4" aria-hidden />
      )}
      {children}
    </button>
  );
});

export function ButtonLink({
  variant = "secondary",
  size = "md",
  className,
  ...rest
}: LinkProps & { variant?: Variant; size?: Size }) {
  return <Link className={cx(buttonClass(variant, size), className)} {...rest} />;
}

// ---------------------------------------------------------------- form fields

const control =
  "w-full rounded-md border border-line-strong bg-surface px-2.5 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none focus-visible:outline-2 focus-visible:outline-accent aria-[invalid=true]:border-critical";

interface FieldProps {
  label: string;
  hint?: ReactNode;
  error?: string;
  children: (props: { id: string; "aria-invalid"?: boolean; "aria-describedby"?: string }) => ReactNode;
  className?: string;
}

/** Label + control + hint/error, wired with ids for screen readers. */
export function Field({ label, hint, error, children, className }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className={cx("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="text-[13px] font-medium text-ink">
        {label}
      </label>
      {children({
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": [hintId, errorId].filter(Boolean).join(" ") || undefined,
      })}
      {hint && !error && (
        <p id={hintId} className="text-xs text-ink-3">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="flex items-center gap-1 text-xs text-critical-ink">
          <XCircle className="size-3.5 shrink-0" aria-hidden />
          {error}
        </p>
      )}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={cx(control, "h-9", className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...rest }, ref) {
    return <textarea ref={ref} className={cx(control, "py-2", className)} {...rest} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, ...rest },
  ref,
) {
  return <select ref={ref} className={cx(control, "h-9 pr-8", className)} {...rest} />;
});

// ---------------------------------------------------------------- status

export type Tone = "critical" | "good" | "warning" | "neutral" | "accent";

const toneClass: Record<Tone, string> = {
  critical: "bg-critical-wash text-critical-ink",
  good: "bg-good-wash text-good-ink",
  warning: "bg-warning-wash text-warning-ink",
  neutral: "bg-sunken text-ink-2",
  accent: "bg-accent-wash text-accent-strong",
};

export function Badge({ tone = "neutral", icon: Icon, children }: { tone?: Tone; icon?: LucideIcon; children: ReactNode }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap", toneClass[tone])}>
      {Icon && <Icon className="size-3.5 shrink-0" aria-hidden />}
      {children}
    </span>
  );
}

/** One place that maps every status in the product to a consistent label. */
export function StatusBadge({ status }: { status: string | null }) {
  switch (status) {
    case "open":
      return <Badge tone="critical" icon={CircleDot}>Open</Badge>;
    case "resolved":
      return <Badge tone="good" icon={CheckCircle2}>Resolved</Badge>;
    case "passed":
      return <Badge tone="good" icon={CheckCircle2}>Passed</Badge>;
    case "failed":
      return <Badge tone="critical" icon={XCircle}>Failed</Badge>;
    case "error":
      return <Badge tone="warning" icon={AlertTriangle}>Error</Badge>;
    case "pending":
    case "running":
      return <Badge tone="neutral" icon={Clock}>Running</Badge>;
    case null:
      return <Badge tone="neutral">Never run</Badge>;
    default:
      return <Badge>{status}</Badge>;
  }
}

export function HttpStatus({ status }: { status: number | null }) {
  if (status === null) return <span className="text-ink-3">—</span>;
  const tone: Tone = status >= 500 ? "critical" : status >= 400 ? "warning" : "good";
  return (
    <Badge tone={tone}>
      <span className="tabular">{status}</span>
    </Badge>
  );
}

export function MethodTag({ method }: { method: string | null }) {
  return (
    <span className="inline-block min-w-12 rounded border border-line px-1 text-center font-mono text-[11px] font-semibold text-ink-2">
      {method ?? "—"}
    </span>
  );
}

// ---------------------------------------------------------------- layout pieces

export function Panel({
  title,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx("rounded-lg border border-line bg-surface", className)}>
      {(title || actions) && (
        <header className="flex min-h-11 flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2">
          {title && <h2 className="text-sm font-semibold">{title}</h2>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      {/* bodyClassName replaces the default padding rather than competing with it. */}
      <div className={bodyClassName ?? "p-4"}>{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  breadcrumb,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  breadcrumb?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {breadcrumb && <div className="mb-1 text-[13px] text-ink-3">{breadcrumb}</div>}
        <h1 className="text-xl font-semibold tracking-tight break-words">{title}</h1>
        {description && <p className="mt-1 text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- states

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-10 text-ink-3">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      {Icon && <Icon className="mb-3 size-8 text-ink-3" aria-hidden />}
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 max-w-md text-ink-2">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const message =
    error instanceof ApiError ? error.message : error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div role="alert" className="flex flex-col items-center px-6 py-10 text-center">
      <AlertTriangle className="mb-2 size-6 text-critical" aria-hidden />
      <p className="font-medium">Couldn’t load this</p>
      <p className="mt-1 max-w-md text-ink-2">{message}</p>
      {retry && (
        <Button className="mt-4" size="sm" onClick={retry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** Inline error for a failed mutation, placed next to the control that caused it. */
export function InlineError({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <p role="alert" className="flex items-start gap-1.5 text-[13px] text-critical-ink">
      <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>{message}</span>
    </p>
  );
}

// ---------------------------------------------------------------- pagination

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-3 text-[13px] text-ink-2">
      <span className="tabular">
        {from}–{to} of {total}
      </span>
      <div className="flex items-center gap-1">
        <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </Button>
        <span className="tabular px-1" aria-current="page">
          Page {page} of {pages}
        </span>
        <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
        </Button>
      </div>
    </nav>
  );
}

// ---------------------------------------------------------------- tables

export const th = "px-3 py-2 text-left text-xs font-medium text-ink-3 whitespace-nowrap";
export const td = "px-3 py-2.5 align-top";

export function Table({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm" aria-label={label}>
        {children}
      </table>
    </div>
  );
}
