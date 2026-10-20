import { Check, Copy, EyeOff, MinusCircle } from "lucide-react";
import { useState, type ReactNode } from "react";
import { REDACTED } from "../api/types";
import { prettyJson } from "../lib/format";
import { cx, td, th } from "./ui";

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard blocked: the text is still selectable */
        }
      }}
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-3 hover:bg-sunken hover:text-ink"
    >
      {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
      <span>{copied ? "Copied" : label}</span>
    </button>
  );
}

/** Monospaced, scrollable, copyable block for JSON, stack traces and snippets. */
export function CodeBlock({
  value,
  title,
  className,
  maxHeight = "28rem",
}: {
  value: unknown;
  title?: ReactNode;
  className?: string;
  maxHeight?: string;
}) {
  const text = prettyJson(value);
  return (
    <div className={cx("overflow-hidden rounded-md border border-line bg-sunken", className)}>
      <div className="flex items-center justify-between border-b border-line px-3 py-1">
        <span className="text-xs font-medium text-ink-3">{title}</span>
        <CopyButton text={text} />
      </div>
      <pre className="overflow-auto p-3 font-mono text-[12.5px] leading-relaxed" style={{ maxHeight }} tabIndex={0}>
        {text}
      </pre>
    </div>
  );
}

/** Deliberately removed by redaction — distinct from information that was never captured. */
export function Redacted() {
  return (
    <span className="inline-flex items-center gap-1 rounded bg-warning-wash px-1.5 text-xs font-medium text-warning-ink">
      <EyeOff className="size-3" aria-hidden />
      Redacted
    </span>
  );
}

export function NotCaptured({ children = "Not captured" }: { children?: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-ink-3 italic">
      <MinusCircle className="size-3" aria-hidden />
      {children}
    </span>
  );
}

export function CapturedValue({ value }: { value: unknown }) {
  if (value === REDACTED) return <Redacted />;
  if (value === undefined || value === null) return <NotCaptured>Unavailable</NotCaptured>;
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return <span className="font-mono text-[12.5px] break-all">{text}</span>;
}

export function KeyValueTable({
  data,
  label,
  empty = "None",
}: {
  data: Record<string, unknown> | null | undefined;
  label: string;
  empty?: string;
}) {
  if (data === null || data === undefined) return <NotCaptured />;
  const entries = Object.entries(data);
  if (entries.length === 0) return <p className="text-[13px] text-ink-3">{empty}</p>;
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="w-full text-sm" aria-label={label}>
        <thead className="sr-only">
          <tr>
            <th>Name</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k} className="border-b border-line last:border-0">
              <th scope="row" className={cx(th, "w-1/3 py-1.5 align-top font-mono text-[12.5px] font-normal text-ink-2")}>
                {k}
              </th>
              <td className={cx(td, "py-1.5")}>
                {Array.isArray(v) ? (
                  <span className="flex flex-wrap gap-1">
                    {v.map((x, i) => (
                      <CapturedValue key={i} value={x} />
                    ))}
                  </span>
                ) : (
                  <CapturedValue value={v} />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
