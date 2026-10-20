import { evaluateAssertions } from "../../lib/assertions";
import type {
  ExceptionData,
  Incident,
  RegressionCase,
  ReplayExecution,
  ReplayTarget,
  RequestData,
  TracebackEvent,
} from "../types";
import { REDACTED } from "../types";
import type { MockDb, StoredProject } from "./server";
import { simulate } from "./simulatedApp";


/** Deterministic PRNG so the seeded demo looks the same on every reset. */
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const HOUR = 3600_000;
const DAY = 24 * HOUR;

interface IncidentSpec {
  error_type: string;
  message: string;
  method: string;
  route: string;
  path: string;
  status: number;
  event_type: TracebackEvent["event_type"];
  occurrences: number;
  /** Days ago of first occurrence. */
  span_days: number;
  resolved: boolean;
  query?: Record<string, string | string[]>;
  body?: unknown;
  body_captured?: boolean;
  frames: [string, number, string, string, boolean][];
}

const SPECS: IncidentSpec[] = [
  {
    error_type: "ZeroDivisionError",
    message: "division by zero",
    method: "POST",
    route: "/checkout",
    path: "/checkout",
    status: 500,
    event_type: "exception",
    occurrences: 47,
    span_days: 6,
    resolved: false,
    body: { cart_id: "cart_19f2", quantity: 0, coupon: null, card_number: REDACTED },
    frames: [
      ["starlette/routing.py", 74, "app", "response = await func(request)", false],
      ["app/routes/checkout.py", 41, "create_checkout", "price = pricing.unit_price(cart.total, body.quantity)", true],
      ["app/services/pricing.py", 18, "unit_price", "return round(total / quantity, 2)", true],
    ],
  },
  {
    error_type: "KeyError",
    message: "'ord_missing'",
    method: "GET",
    route: "/orders/{order_id}",
    path: "/orders/ord_missing",
    status: 500,
    event_type: "exception",
    occurrences: 12,
    span_days: 9,
    resolved: false,
    query: { expand: ["items", "customer"] },
    frames: [
      ["app/routes/orders.py", 27, "get_order", "order = ORDERS[order_id]", true],
    ],
  },
  {
    error_type: "TypeError",
    message: "unsupported operand type(s) for +: 'int' and 'str'",
    method: "GET",
    route: "/reports/daily",
    path: "/reports/daily",
    status: 500,
    event_type: "exception",
    occurrences: 21,
    span_days: 3,
    resolved: false,
    query: { date: "2026-10-13", tz: "UTC" },
    frames: [
      ["app/routes/reports.py", 33, "daily_report", "return build_report(rows)", true],
      ["app/services/reports.py", 52, "build_report", "revenue = sum(r.amount for r in rows) + adjustment", true],
    ],
  },
  {
    error_type: "httpx.ReadTimeout",
    message: "timed out",
    method: "POST",
    route: "/payments/charge",
    path: "/payments/charge",
    status: 504,
    event_type: "exception",
    occurrences: 8,
    span_days: 12,
    resolved: false,
    body_captured: false,
    frames: [
      ["app/services/payments.py", 64, "charge", "resp = await client.post(PSP_URL, json=payload)", true],
      ["httpx/_client.py", 1617, "send", "response = await self._send_handling_auth(", false],
      ["httpcore/_async/connection_pool.py", 216, "handle_async_request", "raise exc from None", false],
    ],
  },
  {
    error_type: "UpstreamUnavailable",
    message: "inventory service returned 503",
    method: "GET",
    route: "/inventory/{sku}",
    path: "/inventory/TB-001",
    status: 503,
    event_type: "http_error",
    occurrences: 5,
    span_days: 2,
    resolved: false,
    frames: [],
  },
  {
    error_type: "sqlalchemy.exc.IntegrityError",
    message: 'duplicate key value violates unique constraint "uq_users_email"',
    method: "POST",
    route: "/users",
    path: "/users",
    status: 500,
    event_type: "exception",
    occurrences: 3,
    span_days: 13,
    resolved: true,
    body: { email: "ada@example.com", password: REDACTED, name: "Ada" },
    frames: [
      ["app/routes/users.py", 22, "create_user", "db.commit()", true],
      ["sqlalchemy/orm/session.py", 2028, "commit", "trans.commit(_to_root=True)", false],
    ],
  },
  {
    error_type: "AttributeError",
    message: "'NoneType' object has no attribute 'currency'",
    method: "GET",
    route: "/cart",
    path: "/cart",
    status: 500,
    event_type: "exception",
    occurrences: 16,
    span_days: 11,
    resolved: true,
    frames: [
      ["app/routes/cart.py", 15, "get_cart", "return CartOut.from_cart(cart)", true],
      ["app/schemas/cart.py", 30, "from_cart", "currency=cart.pricing.currency,", true],
    ],
  },
];

function fingerprint(spec: IncidentSpec): string {
  let h = 2166136261;
  for (const c of `${spec.error_type}|${spec.route}|${spec.frames.at(-1)?.[2] ?? ""}`) {
    h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  }
  return (h >>> 0).toString(16).padStart(8, "0").repeat(8);
}

function requestData(spec: IncidentSpec, correlationId: string): RequestData {
  const captured = spec.body_captured ?? spec.method !== "GET";
  return {
    path: spec.path,
    query: spec.query ?? {},
    headers: {
      authorization: REDACTED,
      cookie: REDACTED,
      "content-type": "application/json",
      "user-agent": "checkout-web/2.14.0",
      "x-request-id": correlationId,
    },
    body_captured: captured,
    body: captured ? (spec.body ?? null) : null,
    body_truncated: false,
    response_headers: { "content-type": "application/json", "x-correlation-id": correlationId },
    response_body: { detail: spec.status === 500 ? "Internal Server Error" : "Upstream error" },
  };
}

function exceptionData(spec: IncidentSpec): ExceptionData | null {
  if (spec.event_type !== "exception") return null;
  return {
    type: spec.error_type,
    message: spec.message,
    frames: spec.frames.map(([filename, lineno, fn, context_line, in_app]) => ({
      filename,
      lineno,
      function: fn,
      context_line,
      in_app,
    })),
  };
}

export function seedDemo(db: MockDb, ownerId: string, now = Date.now()): StoredProject {
  const rand = mulberry32(42);
  const iso = (t: number) => new Date(t).toISOString();

  const project: StoredProject = {
    id: crypto.randomUUID(),
    owner_id: ownerId,
    name: "Checkout API",
    slug: "checkout-api",
    retention_days: 30,
    redaction_rules: [{ field: "card_number" }, { field: "ssn" }],
    api_key: {
      id: crypto.randomUUID(),
      key_prefix: "tb_8c41d2",
      created_at: iso(now - 14 * DAY),
      last_used_at: iso(now - 20 * 60_000),
    },
    created_at: iso(now - 14 * DAY),
    updated_at: iso(now - 14 * DAY),
  };
  db.projects.push(project);

  for (const spec of SPECS) {
    const incidentId = crypto.randomUUID();
    const times: number[] = [];
    for (let i = 0; i < spec.occurrences; i++) {
      // Skew toward recent activity for open incidents; resolved ones stop early.
      const r = spec.resolved ? 0.35 + rand() * 0.65 : rand() ** 1.6;
      times.push(now - r * spec.span_days * DAY - rand() * HOUR);
    }
    times.sort((a, b) => a - b);
    const first = times[0]!;
    const last = times.at(-1)!;
    const incident: Incident = {
      id: incidentId,
      project_id: project.id,
      fingerprint: fingerprint(spec),
      title: `${spec.error_type} in ${spec.method} ${spec.route}`,
      error_type: spec.error_type,
      error_message: spec.message,
      normalized_route: spec.route,
      status: spec.resolved ? "resolved" : "open",
      occurrence_count: spec.occurrences,
      first_seen_at: iso(first),
      last_seen_at: iso(last),
      resolved_at: spec.resolved ? iso(last + 2 * HOUR) : null,
    };
    db.incidents.push(incident);

    for (const t of times) {
      const correlationId = `req_${Math.floor(rand() * 0xffffffff).toString(16).padStart(8, "0")}`;
      db.events.push({
        id: crypto.randomUUID(),
        project_id: project.id,
        incident_id: incidentId,
        event_type: spec.event_type,
        correlation_id: correlationId,
        environment: "production",
        release: rand() > 0.3 ? "2.14.0" : "2.13.2",
        request_method: spec.method,
        normalized_route: spec.route,
        request_data: requestData(spec, correlationId),
        response_status: spec.status,
        duration_ms: Math.round(spec.status === 504 ? 10_000 + rand() * 50 : 18 + rand() * 140),
        exception_data: exceptionData(spec),
        occurred_at: iso(t),
        received_at: iso(t + 120),
      });
    }
  }

  const local: ReplayTarget = {
    id: crypto.randomUUID(),
    name: "Local dev",
    base_url: "http://localhost:9000",
    environment: "local",
    enabled: true,
    created_at: iso(now - 13 * DAY),
    updated_at: iso(now - 13 * DAY),
  };
  const staging: ReplayTarget = {
    id: crypto.randomUUID(),
    name: "Staging",
    base_url: "https://staging.checkout.example.com",
    environment: "staging",
    enabled: true,
    created_at: iso(now - 13 * DAY),
    updated_at: iso(now - 13 * DAY),
  };
  db.targets.push({ ...local, project_id: project.id }, { ...staging, project_id: project.id });

  // One regression case for the resolved cart bug, with a passing history.
  const cartIncident = db.incidents.find((i) => i.project_id === project.id && i.error_type === "AttributeError")!;
  const caseId = crypto.randomUUID();
  const kase: Omit<RegressionCase, "last_run"> = {
    id: caseId,
    incident_id: cartIncident.id,
    source_event_id: null,
    name: "Empty cart returns currency",
    description: "Guards the AttributeError when a cart had no pricing record.",
    request_definition: { method: "GET", path: "/cart", query: {}, headers: { accept: "application/json" }, body: null },
    assertion_definition: {
      expected_status: 200,
      assertions: [{ type: "json_path_equals", path: "$.currency", expected: "USD" }],
    },
    created_at: iso(now - 4 * DAY),
    updated_at: iso(now - 4 * DAY),
  };
  db.cases.push({ ...kase, project_id: project.id });
  for (const daysAgo of [4, 2, 0.3]) {
    const started = now - daysAgo * DAY;
    const response = simulate(kase.request_definition, true);
    const { outcome, results } = evaluateAssertions(kase.assertion_definition, response);
    const execution: ReplayExecution = {
      id: crypto.randomUUID(),
      kind: "regression_run",
      regression_case_id: caseId,
      event_id: null,
      target_id: local.id,
      status: "completed",
      outcome,
      request_summary: { method: "GET", url: `${local.base_url}/cart`, headers: { accept: "application/json" } },
      response_summary: response,
      assertion_results: results,
      duration_ms: 31,
      error_summary: null,
      started_at: iso(started),
      completed_at: iso(started + 31),
    };
    db.executions.push({ ...execution, project_id: project.id });
  }

  return project;
}
