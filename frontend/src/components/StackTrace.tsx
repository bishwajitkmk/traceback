import { useState } from "react";
import type { ExceptionData } from "../api/types";
import { CopyButton } from "./Code";
import { cx } from "./ui";

export function formatTrace(exc: ExceptionData): string {
  const frames = exc.frames.map(
    (f) => `  File "${f.filename}", line ${f.lineno}, in ${f.function}${f.context_line ? `\n    ${f.context_line}` : ""}`,
  );
  return ["Traceback (most recent call last):", ...frames, `${exc.type}: ${exc.message}`].join("\n");
}

/** Python-ordered stack trace (most recent call last); library frames can be collapsed. */
export function StackTrace({ exception }: { exception: ExceptionData }) {
  const [showAll, setShowAll] = useState(false);
  const libraryCount = exception.frames.filter((f) => !f.in_app).length;
  const frames = showAll ? exception.frames : exception.frames.filter((f) => f.in_app);

  return (
    <div className="overflow-hidden rounded-md border border-line bg-sunken">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-1">
        <span className="text-xs font-medium text-ink-3">Most recent call last</span>
        <div className="flex items-center gap-1">
          {libraryCount > 0 && (
            <button
              type="button"
              className="rounded px-1.5 py-0.5 text-xs text-ink-3 hover:bg-surface hover:text-ink"
              aria-pressed={showAll}
              onClick={() => setShowAll((s) => !s)}
            >
              {showAll ? "Hide" : "Show"} {libraryCount} library frame{libraryCount === 1 ? "" : "s"}
            </button>
          )}
          <CopyButton text={formatTrace(exception)} label="Copy trace" />
        </div>
      </div>
      <ol className="overflow-x-auto font-mono text-[12.5px] leading-relaxed" tabIndex={0} aria-label="Stack frames">
        {frames.length === 0 && <li className="px-3 py-2 text-ink-3">No application frames captured.</li>}
        {frames.map((f, i) => (
          <li
            key={`${f.filename}:${f.lineno}:${i}`}
            className={cx(
              "border-b border-line px-3 py-2 last:border-0",
              f.in_app ? "bg-surface" : "text-ink-3",
              i === frames.length - 1 && f.in_app && "border-l-2 border-l-critical",
            )}
          >
            <div className="whitespace-nowrap">
              <span className={f.in_app ? "font-semibold" : undefined}>{f.filename}</span>
              <span className="text-ink-3">:{f.lineno}</span>
              <span className="text-ink-3"> in </span>
              <span>{f.function}</span>
              {!f.in_app && <span className="ml-2 text-[11px] text-ink-3">(library)</span>}
            </div>
            {f.context_line && <pre className="mt-0.5 pl-4 whitespace-pre text-ink-2">{f.context_line}</pre>}
          </li>
        ))}
        <li className="bg-critical-wash px-3 py-2 font-semibold text-critical-ink">
          {exception.type}: {exception.message}
        </li>
      </ol>
    </div>
  );
}
