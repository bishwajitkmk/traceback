import { Equal, Minus, PenLine, Plus } from "lucide-react";
import type { ResponseSummary } from "../api/types";
import { jsonDiff, type DiffEntry } from "../lib/jsonDiff";
import { cx, HttpStatus, td, th } from "./ui";

const KIND: Record<DiffEntry["kind"], { label: string; icon: typeof Plus; row: string }> = {
  added: { label: "Added", icon: Plus, row: "bg-diff-add" },
  removed: { label: "Removed", icon: Minus, row: "bg-diff-remove" },
  changed: { label: "Changed", icon: PenLine, row: "bg-diff-change" },
};

function short(value: unknown): string {
  if (value === undefined) return "";
  const s = JSON.stringify(value);
  return s.length > 120 ? `${s.slice(0, 117)}…` : s;
}

/** Original vs replayed: status, selected headers, and field-level JSON differences. */
export function ResponseComparison({
  original,
  replayed,
}: {
  original: { status: number | null; headers: Record<string, string> | null; body: unknown };
  replayed: ResponseSummary;
}) {
  const bodyComparable = original.body !== undefined && original.body !== null;
  const entries = bodyComparable ? jsonDiff(original.body, replayed.body) : [];
  const counts = { added: 0, removed: 0, changed: 0 };
  for (const e of entries) counts[e.kind]++;
  const contentType = (h: Record<string, string> | null) =>
    h ? (Object.entries(h).find(([k]) => k.toLowerCase() === "content-type")?.[1] ?? "—") : "—";

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-md border border-line">
        <table className="w-full text-sm" aria-label="Response summary comparison">
          <thead className="border-b border-line bg-sunken">
            <tr>
              <th className={th} scope="col">
                Field
              </th>
              <th className={th} scope="col">
                Original
              </th>
              <th className={th} scope="col">
                Replayed
              </th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-line">
              <th scope="row" className={cx(td, "text-left font-normal text-ink-2")}>
                Status
              </th>
              <td className={td}>
                <HttpStatus status={original.status} />
              </td>
              <td className={td}>
                <HttpStatus status={replayed.status} />
              </td>
            </tr>
            <tr>
              <th scope="row" className={cx(td, "text-left font-normal text-ink-2")}>
                Content-Type
              </th>
              <td className={cx(td, "font-mono text-[12.5px]")}>{contentType(original.headers)}</td>
              <td className={cx(td, "font-mono text-[12.5px]")}>{contentType(replayed.headers)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {!bodyComparable ? (
        <p className="text-[13px] text-ink-3">The original response body was not captured, so only status and headers are compared.</p>
      ) : entries.length === 0 ? (
        <p className="flex items-center gap-1.5 text-[13px] text-ink-2">
          <Equal className="size-4" aria-hidden /> Response bodies are identical.
        </p>
      ) : (
        <div>
          <p className="mb-2 text-[13px] text-ink-2" aria-live="polite">
            <span className="tabular">{counts.added}</span> added · <span className="tabular">{counts.removed}</span> removed ·{" "}
            <span className="tabular">{counts.changed}</span> changed
          </p>
          <div className="overflow-x-auto rounded-md border border-line">
            <table className="w-full text-sm" aria-label="JSON body differences">
              <thead className="border-b border-line bg-sunken">
                <tr>
                  <th className={th} scope="col">
                    Change
                  </th>
                  <th className={th} scope="col">
                    Path
                  </th>
                  <th className={th} scope="col">
                    Original
                  </th>
                  <th className={th} scope="col">
                    Replayed
                  </th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => {
                  const k = KIND[e.kind];
                  return (
                    <tr key={`${e.kind}:${e.path}`} className={cx("border-b border-line last:border-0", k.row)}>
                      <td className={cx(td, "whitespace-nowrap")}>
                        <span className="inline-flex items-center gap-1 text-xs font-medium">
                          <k.icon className="size-3.5" aria-hidden />
                          {k.label}
                        </span>
                      </td>
                      <td className={cx(td, "font-mono text-[12.5px] whitespace-nowrap")}>{e.path}</td>
                      <td className={cx(td, "min-w-40 font-mono text-[12.5px] [overflow-wrap:anywhere] text-ink-2")}>{short(e.before)}</td>
                      <td className={cx(td, "min-w-40 font-mono text-[12.5px] [overflow-wrap:anywhere]")}>{short(e.after)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
