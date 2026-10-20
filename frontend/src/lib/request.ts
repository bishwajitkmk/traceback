import {
  MUTATING_METHODS,
  REDACTED,
  type HttpMethod,
  type QueryValue,
  type RequestDefinition,
  type TracebackEvent,
} from "../api/types";

/**
 * Headers never carried into a replay, even if a capture somehow kept them.
 * The server strips these too; this keeps them out of the editor in the first place.
 */
const CREDENTIAL_HEADERS = new Set([
  "authorization",
  "proxy-authorization",
  "cookie",
  "set-cookie",
  "x-api-key",
  "x-auth-token",
  "x-csrf-token",
]);

/** Hop-by-hop / transport headers that the replay client sets itself. */
const TRANSPORT_HEADERS = new Set(["host", "content-length", "connection", "accept-encoding"]);

const METHODS: HttpMethod[] = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];

export function isMutating(method: HttpMethod): boolean {
  return MUTATING_METHODS.includes(method);
}

export function toMethod(value: string | null): HttpMethod {
  const upper = (value ?? "GET").toUpperCase();
  return (METHODS as string[]).includes(upper) ? (upper as HttpMethod) : "GET";
}

export function safeReplayHeaders(headers: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [name, value] of Object.entries(headers)) {
    const lower = name.toLowerCase();
    if (CREDENTIAL_HEADERS.has(lower) || TRANSPORT_HEADERS.has(lower) || value === REDACTED) {
      continue;
    }
    out[name] = value;
  }
  return out;
}

/** Reconstruct a sendable request from a captured event (PRD §6.6). */
export function requestFromEvent(event: TracebackEvent): RequestDefinition {
  const data = event.request_data;
  return {
    method: toMethod(event.request_method),
    path: data?.path ?? event.normalized_route ?? "/",
    query: data?.query ?? {},
    headers: safeReplayHeaders(data?.headers ?? {}),
    body: data?.body_captured ? (data.body ?? null) : null,
  };
}

/** JSON paths whose value is the redaction placeholder — they must be overridden before replay. */
export function findRedactedPaths(value: unknown, path = "$"): string[] {
  if (value === REDACTED) return [path];
  if (Array.isArray(value)) return value.flatMap((v, i) => findRedactedPaths(v, `${path}[${i}]`));
  if (typeof value === "object" && value !== null) {
    return Object.entries(value).flatMap(([k, v]) => findRedactedPaths(v, `${path}.${k}`));
  }
  return [];
}

export function queryToString(query: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    for (const v of Array.isArray(value) ? value : [value]) params.append(key, v);
  }
  return params.toString();
}

export function queryFromString(text: string): Record<string, QueryValue> {
  const out: Record<string, QueryValue> = {};
  for (const [key, value] of new URLSearchParams(text.replace(/^\?/, ""))) {
    const existing = out[key];
    if (existing === undefined) out[key] = value;
    else out[key] = Array.isArray(existing) ? [...existing, value] : [existing, value];
  }
  return out;
}
