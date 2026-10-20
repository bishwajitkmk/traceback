import { Plus, Trash2 } from "lucide-react";
import type { Assertion, AssertionDefinition } from "../api/types";
import { parsePath } from "../lib/jsonPath";
import { Button, Field, Input, Select } from "./ui";

type AssertionType = Assertion["type"];

export interface AssertionDraft {
  expectedStatus: string;
  rows: { type: AssertionType; path: string; expected: string }[];
}

export function draftFromAssertions(def: AssertionDefinition): AssertionDraft {
  return {
    expectedStatus: String(def.expected_status),
    rows: def.assertions.map((a) => ({
      type: a.type,
      path: "path" in a ? a.path : "",
      expected: a.type === "json_path_equals" ? JSON.stringify(a.expected) : a.type === "body_contains" ? a.expected : "",
    })),
  };
}

export function assertionsFromDraft(draft: AssertionDraft): {
  definition: AssertionDefinition | null;
  errors: { status?: string; rows: Record<number, string> };
} {
  const errors: { status?: string; rows: Record<number, string> } = { rows: {} };
  const status = Number(draft.expectedStatus);
  if (!Number.isInteger(status) || status < 100 || status > 599) errors.status = "Enter an HTTP status between 100 and 599.";

  const assertions: Assertion[] = [];
  draft.rows.forEach((row, i) => {
    if (row.type === "body_contains") {
      if (!row.expected) errors.rows[i] = "Enter the text the body must contain.";
      else assertions.push({ type: "body_contains", expected: row.expected });
      return;
    }
    if (!parsePath(row.path) || !row.path.trim()) {
      errors.rows[i] = "Enter a JSON path such as $.error.code or $.items[0].id.";
      return;
    }
    if (row.type === "json_path_exists") {
      assertions.push({ type: "json_path_exists", path: row.path.trim() });
      return;
    }
    try {
      assertions.push({ type: "json_path_equals", path: row.path.trim(), expected: JSON.parse(row.expected) });
    } catch {
      errors.rows[i] = 'Expected value must be JSON — quote strings, e.g. "USD".';
    }
  });

  const ok = !errors.status && Object.keys(errors.rows).length === 0;
  return { definition: ok ? { expected_status: status, assertions } : null, errors };
}

const LABELS: Record<AssertionType, string> = {
  json_path_equals: "JSON path equals",
  json_path_exists: "JSON path exists",
  body_contains: "Body contains text",
};

export function AssertionEditor({
  draft,
  onChange,
  errors,
}: {
  draft: AssertionDraft;
  onChange: (d: AssertionDraft) => void;
  errors: { status?: string; rows: Record<number, string> };
}) {
  const setRow = (i: number, patch: Partial<AssertionDraft["rows"][number]>) => {
    const rows = [...draft.rows];
    rows[i] = { ...rows[i]!, ...patch };
    onChange({ ...draft, rows });
  };

  return (
    <div className="space-y-4">
      <Field label="Expected status" error={errors.status} className="max-w-40">
        {(p) => (
          <Input
            {...p}
            inputMode="numeric"
            className="tabular"
            value={draft.expectedStatus}
            onChange={(e) => onChange({ ...draft, expectedStatus: e.target.value })}
          />
        )}
      </Field>

      <fieldset>
        <legend className="mb-2 text-[13px] font-medium">Response assertions</legend>
        {draft.rows.length === 0 && <p className="mb-2 text-[13px] text-ink-3">Only the status is checked.</p>}
        <ol className="space-y-3">
          {draft.rows.map((row, i) => (
            <li key={i} className="rounded-md border border-line p-3">
              <div className="flex flex-wrap items-start gap-2">
                <Select
                  aria-label={`Assertion ${i + 1} type`}
                  className="w-48"
                  value={row.type}
                  onChange={(e) => setRow(i, { type: e.target.value as AssertionType })}
                >
                  {Object.entries(LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
                {row.type !== "body_contains" && (
                  <Input
                    aria-label={`Assertion ${i + 1} JSON path`}
                    placeholder="$.error.code"
                    className="min-w-40 flex-1 font-mono"
                    value={row.path}
                    onChange={(e) => setRow(i, { path: e.target.value })}
                  />
                )}
                {row.type !== "json_path_exists" && (
                  <Input
                    aria-label={`Assertion ${i + 1} expected value`}
                    placeholder={row.type === "body_contains" ? "text" : '"USD"'}
                    className="min-w-32 flex-1 font-mono"
                    value={row.expected}
                    onChange={(e) => setRow(i, { expected: e.target.value })}
                  />
                )}
                <Button
                  variant="ghost"
                  icon={Trash2}
                  aria-label={`Remove assertion ${i + 1}`}
                  onClick={() => onChange({ ...draft, rows: draft.rows.filter((_, j) => j !== i) })}
                />
              </div>
              {errors.rows[i] && (
                <p role="alert" className="mt-1.5 text-xs text-critical-ink">
                  {errors.rows[i]}
                </p>
              )}
            </li>
          ))}
        </ol>
        <Button
          className="mt-2"
          size="sm"
          variant="ghost"
          icon={Plus}
          onClick={() => onChange({ ...draft, rows: [...draft.rows, { type: "json_path_equals", path: "", expected: "" }] })}
        >
          Add assertion
        </Button>
      </fieldset>
    </div>
  );
}
