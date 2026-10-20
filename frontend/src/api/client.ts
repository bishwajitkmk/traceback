import { API_BASE_URL, USE_MOCKS } from "../lib/config";

/** Mirrors the backend error envelope: {"error": {code, message, details}}. */
export interface ApiErrorBody {
  code: string;
  message: string;
  details?: { field: string; message: string }[];
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiErrorBody,
  ) {
    super(body.message);
  }

  /** Field-level validation messages keyed by the last path segment. */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const d of this.body.details ?? []) out[d.field.split(".").pop() ?? d.field] = d.message;
    return out;
  }
}

export interface TransportResponse {
  status: number;
  body: unknown;
}

export type Transport = (method: string, path: string, body?: unknown) => Promise<TransportResponse>;

const CSRF_COOKIE = "tb_csrf";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | null {
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

/** Real backend: HttpOnly session cookie + double-submit CSRF header on unsafe methods. */
const httpTransport: Transport = async (method, path, body) => {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const csrf = readCookie(CSRF_COOKIE);
  if (csrf && UNSAFE.has(method)) headers["X-CSRF-Token"] = csrf;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      credentials: "include",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, {
      code: "network_error",
      message: `Could not reach the Traceback API at ${API_BASE_URL}.`,
    });
  }
  const text = await response.text();
  return { status: response.status, body: text ? JSON.parse(text) : undefined };
};

// The mock is loaded lazily so it is code-split out of builds that do not use it.
let transport: Transport | null = USE_MOCKS ? null : httpTransport;

async function getTransport(): Promise<Transport> {
  transport ??= (await import("./mock/server")).mockTransport;
  return transport;
}

/** Tests swap the transport to exercise components against a controlled API. */
export function setTransport(next: Transport): void {
  transport = next;
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await (await getTransport())(method, path, body);
  if (response.status >= 400) {
    const envelope = response.body as { error?: ApiErrorBody } | undefined;
    throw new ApiError(
      response.status,
      envelope?.error ?? { code: "http_error", message: `Request failed (${response.status}).` },
    );
  }
  return response.body as T;
}

export function qs(params: object): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") search.set(k, String(v));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}
