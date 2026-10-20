/**
 * In-browser mock of the Traceback API (enabled with VITE_USE_MOCKS=true).
 *
 * It implements the same contract and the same server-side rules the real
 * backend must enforce — auth, per-project authorization (404 for other
 * projects' resources), validation errors, replay target restrictions and
 * mutation confirmation — so the UI is built against realistic behavior.
 * State persists in localStorage; never use this outside local development.
 */
import { evaluateAssertions } from "../../lib/assertions";
import { isMutating, safeReplayHeaders } from "../../lib/request";
import type { TransportResponse } from "../client";
import type {
  ApiKeySummary,
  CreateReplay,
  Incident,
  IncidentStatus,
  Page,
  Project,
  ProjectStats,
  RedactionRule,
  RegressionCase,
  RegressionCaseInput,
  ReplayExecution,
  ReplayTarget,
  ReplayTargetInput,
  RequestDefinition,
  TargetEnvironment,
  TracebackEvent,
  User,
} from "../types";
import { DEMO_EMAIL, DEMO_PASSWORD } from "./demo";
import { seedDemo } from "./seed";
import { simulate } from "./simulatedApp";

export type StoredProject = Omit<Project, "api_key"> & { owner_id: string; api_key: ApiKeySummary | null };
type Scoped<T> = T & { project_id: string };

export interface MockDb {
  users: (User & { password: string })[];
  projects: StoredProject[];
  incidents: Incident[];
  events: Scoped<TracebackEvent>[];
  targets: Scoped<ReplayTarget>[];
  cases: Scoped<Omit<RegressionCase, "last_run">>[];
  executions: Scoped<ReplayExecution>[];
  appFixed: boolean;
}

const DB_KEY = "traceback.mock.db.v1";
const SESSION_KEY = "traceback.mock.session";

function freshDb(): MockDb {
  const db: MockDb = {
    users: [],
    projects: [],
    incidents: [],
    events: [],
    targets: [],
    cases: [],
    executions: [],
    appFixed: false,
  };
  const demo = {
    id: crypto.randomUUID(),
    email: DEMO_EMAIL,
    password: DEMO_PASSWORD,
    created_at: new Date(Date.now() - 14 * 86400_000).toISOString(),
  };
  db.users.push(demo);
  seedDemo(db, demo.id);
  return db;
}

const memory = new Map<string, string>();
const memoryStorage = {
  getItem: (k: string) => memory.get(k) ?? null,
  setItem: (k: string, v: string) => void memory.set(k, v),
  removeItem: (k: string) => void memory.delete(k),
} as Storage;

/** localStorage when it works (it can be blocked or stubbed), else in-memory. */
function storage(): Storage {
  try {
    const ls = window.localStorage;
    if (typeof ls?.getItem === "function" && typeof ls.removeItem === "function") return ls;
  } catch {
    /* blocked by privacy settings */
  }
  return memoryStorage;
}

let db: MockDb = load();

function load(): MockDb {
  try {
    const raw = storage().getItem(DB_KEY);
    if (raw) return JSON.parse(raw) as MockDb;
  } catch {
    /* corrupted or unavailable: start fresh */
  }
  return freshDb();
}

function save(): void {
  try {
    storage().setItem(DB_KEY, JSON.stringify(db));
  } catch {
    /* quota or privacy mode: keep in memory only */
  }
}

/** Dev controls surfaced by the mock-mode banner. */
export const mockControls = {
  reset(): void {
    db = freshDb();
    storage().removeItem(SESSION_KEY);
    save();
  },
  isAppFixed: (): boolean => db.appFixed,
  setAppFixed(fixed: boolean): void {
    db.appFixed = fixed;
    save();
  },
};

// ---------------------------------------------------------------- helpers

class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: { field: string; message: string }[],
  ) {
    super(message);
  }
}

const notFound = (what: string) => new HttpError(404, "not_found", `The requested ${what} was not found.`);

function invalid(field: string, message: string): HttpError {
  return new HttpError(422, "validation_error", "Request validation failed.", [
    { field: `body.${field}`, message },
  ]);
}

const nowIso = () => new Date().toISOString();

function currentUser(): User {
  const id = storage().getItem(SESSION_KEY);
  const user = db.users.find((u) => u.id === id);
  if (!user) throw new HttpError(401, "unauthenticated", "Sign in to continue.");
  return { id: user.id, email: user.email, created_at: user.created_at };
}

function ownedProject(projectId: string): StoredProject {
  const user = currentUser();
  const project = db.projects.find((p) => p.id === projectId && p.owner_id === user.id);
  // Same response for "missing" and "someone else's" — UUIDs cannot be probed.
  if (!project) throw notFound("project");
  return project;
}

function publicProject(p: StoredProject): Project {
  const { owner_id: _owner, ...rest } = p;
  return rest;
}

function paginate<T>(items: T[], query: URLSearchParams): Page<T> {
  const page = Math.max(1, Number(query.get("page") ?? 1) || 1);
  const pageSize = Math.min(100, Math.max(1, Number(query.get("page_size") ?? 20) || 20));
  return {
    items: items.slice((page - 1) * pageSize, page * pageSize),
    total: items.length,
    page,
    page_size: pageSize,
  };
}

function strip<T extends { project_id: string }>(row: T): Omit<T, "project_id"> {
  const { project_id: _p, ...rest } = row;
  return rest;
}

function slugify(name: string): string {
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60) || "project"
  );
}

function newKey(): { key: string; summary: ApiKeySummary } {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  const key = `tb_${[...bytes].map((b) => b.toString(16).padStart(2, "0")).join("")}`;
  return {
    key,
    summary: { id: crypto.randomUUID(), key_prefix: key.slice(0, 9), created_at: nowIso(), last_used_at: null },
  };
}

// ---------------------------------------------------------------- replay safety

const METADATA_HOSTS = new Set([
  "169.254.169.254",
  "metadata.google.internal",
  "100.100.100.200",
  "[fd00:ec2::254]",
]);
const ENVIRONMENTS: TargetEnvironment[] = ["local", "development", "staging", "test"];

function isPrivateHost(host: string): boolean {
  return (
    host === "localhost" ||
    host.endsWith(".localhost") ||
    host === "[::1]" ||
    /^127\./.test(host) ||
    /^10\./.test(host) ||
    /^192\.168\./.test(host) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(host) ||
    /^169\.254\./.test(host) ||
    host === "0.0.0.0"
  );
}

/** Mirrors the backend's target validation (PRD §6.6, §12). */
function validateTarget(input: Partial<ReplayTargetInput>, existing?: ReplayTarget): void {
  const name = input.name ?? existing?.name ?? "";
  if (!name.trim()) throw invalid("name", "Name is required.");
  const environment = input.environment ?? existing?.environment;
  if (!environment || !ENVIRONMENTS.includes(environment)) {
    throw invalid("environment", "Environment must be local, development, staging or test. Production is never a replay target.");
  }
  const raw = input.base_url ?? existing?.base_url ?? "";
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw invalid("base_url", "Enter a full URL, e.g. https://staging.example.com.");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") throw invalid("base_url", "Only http and https are allowed.");
  if (url.username || url.password) throw invalid("base_url", "Credentials in the URL are not allowed.");
  if (url.search || url.hash) throw invalid("base_url", "The base URL cannot contain a query or fragment.");
  if (METADATA_HOSTS.has(url.hostname)) {
    throw new HttpError(422, "target_not_allowed", "Cloud metadata endpoints can never be replay targets.");
  }
  if (isPrivateHost(url.hostname) && environment !== "local") {
    throw new HttpError(
      422,
      "target_not_allowed",
      "Loopback and private-network addresses are only allowed for local targets in local-development mode.",
    );
  }
}

const MAX_BODY_BYTES = 64 * 1024;

function validateRequest(req: RequestDefinition): void {
  // The path is joined to the target's base URL; it must not be able to change the host.
  if (!req.path.startsWith("/") || req.path.startsWith("//") || req.path.includes("://") || req.path.includes("\\")) {
    throw new HttpError(422, "invalid_path", "The path must be relative to the target, starting with a single '/'.");
  }
  if (req.body !== null && JSON.stringify(req.body).length > MAX_BODY_BYTES) {
    throw new HttpError(413, "payload_too_large", "Replay bodies are limited to 64 KB.");
  }
}

function execute(
  project: StoredProject,
  targetId: string,
  req: RequestDefinition,
  confirmMutation: boolean,
  extra: Partial<ReplayExecution> & Pick<ReplayExecution, "kind">,
): Scoped<ReplayExecution> {
  const target = db.targets.find((t) => t.id === targetId && t.project_id === project.id);
  if (!target) throw notFound("replay target");
  if (!target.enabled) throw new HttpError(409, "target_disabled", `Target "${target.name}" is disabled.`);
  validateRequest(req);
  if (isMutating(req.method) && !confirmMutation) {
    throw new HttpError(
      409,
      "confirmation_required",
      `${req.method} may change data on "${target.name}". Confirm the replay to send it.`,
    );
  }
  const headers = safeReplayHeaders(req.headers);
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(req.query)) for (const x of Array.isArray(v) ? v : [v]) query.append(k, x);
  const url = `${target.base_url.replace(/\/$/, "")}${req.path}${query.size ? `?${query}` : ""}`;
  const started = Date.now();
  const response = simulate({ ...req, headers }, db.appFixed);
  const duration = 12 + Math.round(Math.random() * 80);
  const execution: Scoped<ReplayExecution> = {
    id: crypto.randomUUID(),
    project_id: project.id,
    regression_case_id: null,
    event_id: null,
    target_id: target.id,
    status: "completed",
    outcome: null,
    request_summary: { method: req.method, url, headers },
    response_summary: response,
    assertion_results: null,
    duration_ms: duration,
    error_summary: null,
    started_at: new Date(started).toISOString(),
    completed_at: new Date(started + duration).toISOString(),
    ...extra,
  };
  db.executions.push(execution);
  return execution;
}

function withLastRun(c: Scoped<Omit<RegressionCase, "last_run">>): RegressionCase {
  const runs = db.executions
    .filter((e) => e.regression_case_id === c.id)
    .sort((a, b) => b.started_at.localeCompare(a.started_at));
  return { ...strip(c), last_run: runs[0] ? strip(runs[0]) : null };
}

function validateCase(input: Partial<RegressionCaseInput>): void {
  if (input.name !== undefined && !input.name.trim()) throw invalid("name", "Name is required.");
  if (input.request_definition) validateRequest(input.request_definition);
  const status = input.assertion_definition?.expected_status;
  if (status !== undefined && (!Number.isInteger(status) || status < 100 || status > 599)) {
    throw invalid("expected_status", "Expected status must be between 100 and 599.");
  }
}

// ---------------------------------------------------------------- routes

type Handler = (ctx: { params: string[]; query: URLSearchParams; body: any }) => unknown;

const routes: [string, RegExp, Handler][] = [];
function route(method: string, pattern: string, handler: Handler): void {
  const regex = new RegExp(`^${pattern.replace(/:\w+/g, "([^/]+)")}$`);
  routes.push([method, regex, handler]);
}

// auth
route("GET", "/auth/me", () => currentUser());

route("POST", "/auth/register", ({ body }) => {
  const email = String(body?.email ?? "").trim().toLowerCase();
  const password = String(body?.password ?? "");
  const details = [];
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) details.push({ field: "body.email", message: "Enter a valid email address." });
  if (password.length < 10) details.push({ field: "body.password", message: "Use at least 10 characters." });
  if (details.length) throw new HttpError(422, "validation_error", "Request validation failed.", details);
  if (db.users.some((u) => u.email === email)) {
    throw new HttpError(409, "email_taken", "An account with this email already exists.");
  }
  const user = { id: crypto.randomUUID(), email, password, created_at: nowIso() };
  db.users.push(user);
  storage().setItem(SESSION_KEY, user.id);
  return { id: user.id, email, created_at: user.created_at };
});

route("POST", "/auth/login", ({ body }) => {
  const email = String(body?.email ?? "").trim().toLowerCase();
  const user = db.users.find((u) => u.email === email && u.password === body?.password);
  if (!user) throw new HttpError(401, "invalid_credentials", "Email or password is incorrect.");
  storage().setItem(SESSION_KEY, user.id);
  return { id: user.id, email: user.email, created_at: user.created_at };
});

route("POST", "/waitlist", ({ body }) => {
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(body?.email ?? ""))) throw invalid("email", "Enter a valid email address.");
  return undefined;
});

route("POST", "/auth/logout", () => {
  storage().removeItem(SESSION_KEY);
  return undefined;
});

// projects
route("GET", "/projects", () => {
  const user = currentUser();
  return db.projects.filter((p) => p.owner_id === user.id).map(publicProject);
});

route("POST", "/projects", ({ body }) => {
  const user = currentUser();
  const name = String(body?.name ?? "").trim();
  if (!name) throw invalid("name", "Name is required.");
  if (name.length > 120) throw invalid("name", "Use 120 characters or fewer.");
  let slug = slugify(name);
  const taken = new Set(db.projects.filter((p) => p.owner_id === user.id).map((p) => p.slug));
  for (let i = 2; taken.has(slug); i++) slug = `${slugify(name)}-${i}`;
  const project: StoredProject = {
    id: crypto.randomUUID(),
    owner_id: user.id,
    name,
    slug,
    retention_days: 30,
    redaction_rules: [],
    api_key: null,
    created_at: nowIso(),
    updated_at: nowIso(),
  };
  db.projects.push(project);
  return publicProject(project);
});

route("GET", "/projects/:id", ({ params }) => publicProject(ownedProject(params[0]!)));

route("PATCH", "/projects/:id", ({ params, body }) => {
  const project = ownedProject(params[0]!);
  if (body.name !== undefined) {
    const name = String(body.name).trim();
    if (!name) throw invalid("name", "Name is required.");
    project.name = name;
  }
  if (body.retention_days !== undefined) {
    const days = Number(body.retention_days);
    if (!Number.isInteger(days) || days < 1 || days > 365) throw invalid("retention_days", "Retention must be 1–365 days.");
    project.retention_days = days;
  }
  if (body.redaction_rules !== undefined) {
    const rules = (body.redaction_rules as RedactionRule[]).map((r) => ({ field: String(r.field).trim() }));
    if (rules.some((r) => !r.field)) throw invalid("redaction_rules", "Field names cannot be empty.");
    project.redaction_rules = rules;
  }
  project.updated_at = nowIso();
  return publicProject(project);
});

route("POST", "/projects/:id/api-keys", ({ params }) => {
  const project = ownedProject(params[0]!);
  if (project.api_key) throw new HttpError(409, "key_exists", "This project already has a key. Rotate it instead.");
  const { key, summary } = newKey();
  project.api_key = summary;
  return { key, api_key: summary };
});

route("POST", "/projects/:id/api-keys/rotate", ({ params }) => {
  const project = ownedProject(params[0]!);
  const { key, summary } = newKey();
  project.api_key = summary; // previous key is invalid from this moment
  return { key, api_key: summary };
});

route("GET", "/projects/:id/stats", ({ params, query }) => {
  const project = ownedProject(params[0]!);
  const days = Math.min(90, Math.max(1, Number(query.get("days") ?? 14) || 14));
  const today = new Date(new Date().toISOString().slice(0, 10) + "T00:00:00Z").getTime();
  const start = today - (days - 1) * 86400_000;
  const events = db.events.filter((e) => e.project_id === project.id && Date.parse(e.occurred_at) >= start);
  const incidents = db.incidents.filter((i) => i.project_id === project.id);

  const byDay = new Map<string, number>();
  for (let t = start; t <= today; t += 86400_000) byDay.set(new Date(t).toISOString().slice(0, 10), 0);
  const byIncident = new Map<string, number>();
  for (const e of events) {
    const day = e.occurred_at.slice(0, 10);
    byDay.set(day, (byDay.get(day) ?? 0) + 1);
    if (e.incident_id) byIncident.set(e.incident_id, (byIncident.get(e.incident_id) ?? 0) + 1);
  }

  const cases = db.cases.filter((c) => c.project_id === project.id).map(withLastRun);
  const runs = db.executions
    .filter((e) => e.project_id === project.id && e.kind === "regression_run")
    .sort((a, b) => b.started_at.localeCompare(a.started_at))
    .slice(0, 5);

  const stats: ProjectStats = {
    days,
    open_incidents: incidents.filter((i) => i.status === "open").length,
    events_in_range: events.length,
    new_incidents_in_range: incidents.filter((i) => Date.parse(i.first_seen_at) >= start).length,
    daily: [...byDay].map(([date, count]) => ({ date, events: count })),
    top_incidents: [...byIncident]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([id, count]) => ({ incident: incidents.find((i) => i.id === id)!, events: count })),
    recent_incidents: [...incidents].sort((a, b) => b.last_seen_at.localeCompare(a.last_seen_at)).slice(0, 5),
    recent_runs: runs.map((r) => ({
      execution: strip(r),
      case_id: r.regression_case_id!,
      case_name: db.cases.find((c) => c.id === r.regression_case_id)?.name ?? "Deleted case",
    })),
    regression: {
      total: cases.length,
      passing: cases.filter((c) => c.last_run?.outcome === "passed").length,
      failing: cases.filter((c) => c.last_run && c.last_run.outcome !== "passed").length,
      never_run: cases.filter((c) => !c.last_run).length,
    },
  };
  return stats;
});

// incidents & events
route("GET", "/projects/:id/incidents", ({ params, query }) => {
  const project = ownedProject(params[0]!);
  const status = query.get("status");
  const errorType = query.get("error_type");
  const q = query.get("q")?.toLowerCase();
  const sinceDays = Number(query.get("since_days") ?? 0);
  const since = sinceDays ? Date.now() - sinceDays * 86400_000 : 0;
  const items = db.incidents
    .filter((i) => i.project_id === project.id)
    .filter((i) => !status || i.status === status)
    .filter((i) => !errorType || i.error_type === errorType)
    .filter((i) => !since || Date.parse(i.last_seen_at) >= since)
    .filter(
      (i) =>
        !q ||
        i.title.toLowerCase().includes(q) ||
        i.error_message.toLowerCase().includes(q) ||
        (i.normalized_route ?? "").toLowerCase().includes(q),
    )
    // Deterministic ordering: most recent first, id as tiebreaker.
    .sort((a, b) => b.last_seen_at.localeCompare(a.last_seen_at) || a.id.localeCompare(b.id));
  return paginate(items, query);
});

function ownedIncident(projectId: string, incidentId: string): Incident {
  const project = ownedProject(projectId);
  const incident = db.incidents.find((i) => i.id === incidentId && i.project_id === project.id);
  if (!incident) throw notFound("incident");
  return incident;
}

route("GET", "/projects/:id/incidents/:iid", ({ params }) => ownedIncident(params[0]!, params[1]!));

route("PATCH", "/projects/:id/incidents/:iid", ({ params, body }) => {
  const incident = ownedIncident(params[0]!, params[1]!);
  const status = body?.status as IncidentStatus;
  if (status !== "open" && status !== "resolved") throw invalid("status", "Status must be open or resolved.");
  incident.status = status;
  incident.resolved_at = status === "resolved" ? nowIso() : null;
  return incident;
});

route("GET", "/projects/:id/incidents/:iid/events", ({ params, query }) => {
  const incident = ownedIncident(params[0]!, params[1]!);
  const events = db.events
    .filter((e) => e.incident_id === incident.id)
    .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at))
    .map(strip);
  return paginate(events, query);
});

route("GET", "/projects/:id/events/:eid", ({ params }) => {
  const project = ownedProject(params[0]!);
  const event = db.events.find((e) => e.id === params[1] && e.project_id === project.id);
  if (!event) throw notFound("event");
  return strip(event);
});

// targets
route("GET", "/projects/:id/targets", ({ params }) => {
  const project = ownedProject(params[0]!);
  return db.targets.filter((t) => t.project_id === project.id).map(strip);
});

route("POST", "/projects/:id/targets", ({ params, body }) => {
  const project = ownedProject(params[0]!);
  validateTarget(body);
  if (db.targets.some((t) => t.project_id === project.id && t.name === body.name.trim())) {
    throw invalid("name", "A target with this name already exists.");
  }
  const target: Scoped<ReplayTarget> = {
    id: crypto.randomUUID(),
    project_id: project.id,
    name: body.name.trim(),
    base_url: body.base_url.replace(/\/$/, ""),
    environment: body.environment,
    enabled: body.enabled ?? true,
    created_at: nowIso(),
    updated_at: nowIso(),
  };
  db.targets.push(target);
  return strip(target);
});

function ownedTarget(projectId: string, targetId: string): Scoped<ReplayTarget> {
  const project = ownedProject(projectId);
  const target = db.targets.find((t) => t.id === targetId && t.project_id === project.id);
  if (!target) throw notFound("replay target");
  return target;
}

route("PATCH", "/projects/:id/targets/:tid", ({ params, body }) => {
  const target = ownedTarget(params[0]!, params[1]!);
  validateTarget(body, target);
  Object.assign(target, {
    ...(body.name !== undefined && { name: body.name.trim() }),
    ...(body.base_url !== undefined && { base_url: body.base_url.replace(/\/$/, "") }),
    ...(body.environment !== undefined && { environment: body.environment }),
    ...(body.enabled !== undefined && { enabled: Boolean(body.enabled) }),
    updated_at: nowIso(),
  });
  return strip(target);
});

route("DELETE", "/projects/:id/targets/:tid", ({ params }) => {
  const target = ownedTarget(params[0]!, params[1]!);
  db.targets = db.targets.filter((t) => t.id !== target.id);
  for (const e of db.executions) if (e.target_id === target.id) e.target_id = null;
  return undefined;
});

// replays
route("POST", "/projects/:id/replays", ({ params, body }) => {
  const project = ownedProject(params[0]!);
  const input = body as CreateReplay;
  if (input.event_id && !db.events.some((e) => e.id === input.event_id && e.project_id === project.id)) {
    throw notFound("event");
  }
  return strip(
    execute(project, input.target_id, input.request, input.confirm_mutation, {
      kind: "replay",
      event_id: input.event_id,
    }),
  );
});

route("GET", "/projects/:id/replays", ({ params, query }) => {
  const project = ownedProject(params[0]!);
  const eventId = query.get("event_id");
  return db.executions
    .filter((e) => e.project_id === project.id && e.kind === "replay" && (!eventId || e.event_id === eventId))
    .sort((a, b) => b.started_at.localeCompare(a.started_at))
    .map(strip);
});

route("GET", "/projects/:id/replays/:rid", ({ params }) => {
  const project = ownedProject(params[0]!);
  const execution = db.executions.find((e) => e.id === params[1] && e.project_id === project.id);
  if (!execution) throw notFound("replay");
  return strip(execution);
});

// regression cases
route("GET", "/projects/:id/regression-cases", ({ params }) => {
  const project = ownedProject(params[0]!);
  return db.cases
    .filter((c) => c.project_id === project.id)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .map(withLastRun);
});

route("POST", "/projects/:id/regression-cases", ({ params, body }) => {
  const project = ownedProject(params[0]!);
  const input = body as RegressionCaseInput;
  validateCase(input);
  if (!input.name?.trim()) throw invalid("name", "Name is required.");
  const row = {
    id: crypto.randomUUID(),
    project_id: project.id,
    incident_id: input.incident_id,
    source_event_id: input.source_event_id,
    name: input.name.trim(),
    description: input.description?.trim() || null,
    request_definition: { ...input.request_definition, headers: safeReplayHeaders(input.request_definition.headers) },
    assertion_definition: input.assertion_definition,
    created_at: nowIso(),
    updated_at: nowIso(),
  };
  db.cases.push(row);
  return withLastRun(row);
});

function ownedCase(projectId: string, caseId: string) {
  const project = ownedProject(projectId);
  const kase = db.cases.find((c) => c.id === caseId && c.project_id === project.id);
  if (!kase) throw notFound("regression case");
  return { project, kase };
}

route("GET", "/projects/:id/regression-cases/:cid", ({ params }) => withLastRun(ownedCase(params[0]!, params[1]!).kase));

route("PATCH", "/projects/:id/regression-cases/:cid", ({ params, body }) => {
  const { kase } = ownedCase(params[0]!, params[1]!);
  const patch = body as Partial<RegressionCaseInput>;
  validateCase(patch);
  Object.assign(kase, {
    ...(patch.name !== undefined && { name: patch.name.trim() }),
    ...(patch.description !== undefined && { description: patch.description?.trim() || null }),
    ...(patch.request_definition && {
      request_definition: { ...patch.request_definition, headers: safeReplayHeaders(patch.request_definition.headers) },
    }),
    ...(patch.assertion_definition && { assertion_definition: patch.assertion_definition }),
    updated_at: nowIso(),
  });
  return withLastRun(kase);
});

route("DELETE", "/projects/:id/regression-cases/:cid", ({ params }) => {
  const { kase } = ownedCase(params[0]!, params[1]!);
  db.cases = db.cases.filter((c) => c.id !== kase.id);
  db.executions = db.executions.filter((e) => e.regression_case_id !== kase.id);
  return undefined;
});

route("POST", "/projects/:id/regression-cases/:cid/runs", ({ params, body }) => {
  const { project, kase } = ownedCase(params[0]!, params[1]!);
  const execution = execute(project, body?.target_id, kase.request_definition, Boolean(body?.confirm_mutation), {
    kind: "regression_run",
    regression_case_id: kase.id,
  });
  const { outcome, results } = evaluateAssertions(kase.assertion_definition, execution.response_summary!);
  execution.outcome = outcome;
  execution.assertion_results = results;
  return strip(execution);
});

route("GET", "/projects/:id/regression-cases/:cid/runs", ({ params }) => {
  const { kase } = ownedCase(params[0]!, params[1]!);
  return db.executions
    .filter((e) => e.regression_case_id === kase.id)
    .sort((a, b) => b.started_at.localeCompare(a.started_at))
    .map(strip);
});

// ---------------------------------------------------------------- transport

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function mockTransport(method: string, path: string, body?: unknown): Promise<TransportResponse> {
  // Simulated network latency, so loading states are visible in development.
  if (import.meta.env.MODE !== "test") await delay(120 + Math.random() * 180);
  const [pathname, search = ""] = path.split("?");
  const query = new URLSearchParams(search);
  for (const [m, regex, handler] of routes) {
    if (m !== method) continue;
    const match = regex.exec(pathname!);
    if (!match) continue;
    try {
      // Clone so callers cannot mutate stored state through returned objects.
      const result = handler({ params: match.slice(1), query, body: structuredClone(body) });
      save();
      return { status: result === undefined ? 204 : 200, body: result === undefined ? undefined : structuredClone(result) };
    } catch (e) {
      if (e instanceof HttpError) {
        return {
          status: e.status,
          body: { error: { code: e.code, message: e.message, ...(e.details && { details: e.details }) } },
        };
      }
      throw e;
    }
  }
  return { status: 404, body: { error: { code: "not_found", message: "Not Found" } } };
}
