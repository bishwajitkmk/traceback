import { AlertTriangle, Plus, ShieldCheck, Trash2 } from "lucide-react";
import type { HttpMethod, RequestDefinition } from "../api/types";
import { findRedactedPaths, queryFromString, queryToString } from "../lib/request";
import { Button, Field, Input, Select, Textarea } from "./ui";

const METHODS: HttpMethod[] = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];

export interface RequestDraft {
  method: HttpMethod;
  path: string;
  queryText: string;
  headers: { name: string; value: string }[];
  bodyText: string;
}

export function draftFromRequest(req: RequestDefinition): RequestDraft {
  return {
    method: req.method,
    path: req.path,
    queryText: queryToString(req.query),
    headers: Object.entries(req.headers).map(([name, value]) => ({ name, value })),
    bodyText: req.body === null || req.body === undefined ? "" : JSON.stringify(req.body, null, 2),
  };
}

export interface DraftErrors {
  path?: string;
  body?: string;
}

export function requestFromDraft(draft: RequestDraft): { request: RequestDefinition | null; errors: DraftErrors } {
  const errors: DraftErrors = {};
  const path = draft.path.trim();
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("://")) {
    errors.path = "Use a path relative to the target, starting with a single “/”.";
  }
  let body: unknown = null;
  if (draft.bodyText.trim()) {
    try {
      body = JSON.parse(draft.bodyText);
    } catch (e) {
      errors.body = `Body is not valid JSON: ${(e as Error).message}`;
    }
  }
  const headers: Record<string, string> = {};
  for (const h of draft.headers) if (h.name.trim()) headers[h.name.trim()] = h.value;
  if (errors.path || errors.body) return { request: null, errors };
  return {
    request: { method: draft.method, path, query: queryFromString(draft.queryText), headers, body },
    errors,
  };
}

export function RequestEditor({
  draft,
  onChange,
  errors,
}: {
  draft: RequestDraft;
  onChange: (draft: RequestDraft) => void;
  errors: DraftErrors;
}) {
  const set = (patch: Partial<RequestDraft>) => onChange({ ...draft, ...patch });
  let redacted: string[] = [];
  try {
    redacted = draft.bodyText.trim() ? findRedactedPaths(JSON.parse(draft.bodyText)) : [];
  } catch {
    /* invalid JSON is reported separately */
  }
  const bodyless = draft.method === "GET" || draft.method === "HEAD";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-[7rem_1fr] gap-2">
        <Field label="Method">
          {(p) => (
            <Select {...p} value={draft.method} onChange={(e) => set({ method: e.target.value as HttpMethod })}>
              {METHODS.map((m) => (
                <option key={m}>{m}</option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Path" error={errors.path} hint="Sent to the selected target. The host cannot be changed here.">
          {(p) => (
            <Input {...p} className="font-mono" value={draft.path} onChange={(e) => set({ path: e.target.value })} />
          )}
        </Field>
      </div>

      <Field label="Query string" hint="Repeated keys are kept, e.g. tag=a&tag=b.">
        {(p) => (
          <Input
            {...p}
            className="font-mono"
            placeholder="key=value&other=value"
            value={draft.queryText}
            onChange={(e) => set({ queryText: e.target.value })}
          />
        )}
      </Field>

      <fieldset>
        <legend className="mb-1 text-[13px] font-medium">Headers</legend>
        <p className="mb-2 flex items-center gap-1 text-xs text-ink-3">
          <ShieldCheck className="size-3.5" aria-hidden />
          Captured credentials (Authorization, Cookie, API keys) are never forwarded and are stripped again on the server.
        </p>
        <div className="space-y-2">
          {draft.headers.map((h, i) => (
            <div key={i} className="flex gap-2">
              <Input
                aria-label={`Header ${i + 1} name`}
                className="w-2/5 font-mono"
                value={h.name}
                onChange={(e) => {
                  const headers = [...draft.headers];
                  headers[i] = { ...h, name: e.target.value };
                  set({ headers });
                }}
              />
              <Input
                aria-label={`Header ${i + 1} value`}
                className="font-mono"
                value={h.value}
                onChange={(e) => {
                  const headers = [...draft.headers];
                  headers[i] = { ...h, value: e.target.value };
                  set({ headers });
                }}
              />
              <Button
                variant="ghost"
                aria-label={`Remove header ${h.name || i + 1}`}
                icon={Trash2}
                onClick={() => set({ headers: draft.headers.filter((_, j) => j !== i) })}
              />
            </div>
          ))}
          <Button size="sm" variant="ghost" icon={Plus} onClick={() => set({ headers: [...draft.headers, { name: "", value: "" }] })}>
            Add header
          </Button>
        </div>
      </fieldset>

      <Field
        label="Body (JSON)"
        error={errors.body}
        hint={bodyless ? `${draft.method} requests are normally sent without a body.` : "Leave empty to send no body."}
      >
        {(p) => (
          <Textarea
            {...p}
            rows={8}
            spellCheck={false}
            className="font-mono text-[12.5px]"
            value={draft.bodyText}
            onChange={(e) => set({ bodyText: e.target.value })}
          />
        )}
      </Field>
      {redacted.length > 0 && (
        <p role="note" className="flex items-start gap-1.5 rounded-md bg-warning-wash px-3 py-2 text-[13px] text-warning-ink">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            {redacted.length} value{redacted.length === 1 ? " was" : "s were"} redacted at capture (
            <span className="font-mono">{redacted.join(", ")}</span>). Replace {redacted.length === 1 ? "it" : "them"} with
            test data, or the placeholder text is sent as-is.
          </span>
        </p>
      )}
    </div>
  );
}
