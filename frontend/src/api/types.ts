/**
 * API contract for /api/v1 (PRD §11). The backend's Pydantic schemas must
 * serialize to exactly these shapes; the mock API in ./mock implements them too.
 *
 * Conventions:
 * - Timestamps are ISO-8601 UTC strings.
 * - A captured value replaced by server-side redaction is the string "[REDACTED]".
 * - A value that was never captured is absent/null — the UI shows these differently.
 */

export const REDACTED = "[REDACTED]";

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------- projects

export interface ApiKeySummary {
  id: string;
  /** Non-secret leading characters, e.g. "tb_3f9a1c". */
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
}

/** Returned once on create/rotate; the plaintext key is never retrievable again. */
export interface ApiKeyCreated {
  key: string;
  api_key: ApiKeySummary;
}

export interface RedactionRule {
  /** Field name matched case-insensitively in headers, query and JSON bodies. */
  field: string;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  retention_days: number;
  redaction_rules: RedactionRule[];
  api_key: ApiKeySummary | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectUpdate {
  name?: string;
  retention_days?: number;
  redaction_rules?: RedactionRule[];
}

// ---------------------------------------------------------------- incidents & events

export type IncidentStatus = "open" | "resolved";

export interface Incident {
  id: string;
  project_id: string;
  fingerprint: string;
  title: string;
  error_type: string;
  error_message: string;
  normalized_route: string | null;
  status: IncidentStatus;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
  resolved_at: string | null;
}

export interface IncidentFilters {
  status?: IncidentStatus;
  error_type?: string;
  q?: string;
  /** Only incidents last seen within this many days. */
  since_days?: number;
  page?: number;
  page_size?: number;
}

export type EventType = "exception" | "http_error" | "diagnostic";

export interface StackFrame {
  filename: string;
  lineno: number;
  function: string;
  context_line: string | null;
  /** True for application code, false for libraries/stdlib. */
  in_app: boolean;
}

export interface ExceptionData {
  type: string;
  message: string;
  frames: StackFrame[];
}

export type QueryValue = string | string[];

export interface RequestData {
  path: string;
  query: Record<string, QueryValue>;
  headers: Record<string, string>;
  /** False when body capture is disabled for the route/project. */
  body_captured: boolean;
  body: unknown;
  body_truncated: boolean;
  response_headers: Record<string, string> | null;
  /** Original response body, when the SDK captured it. */
  response_body: unknown;
}

export interface TracebackEvent {
  id: string;
  incident_id: string | null;
  event_type: EventType;
  correlation_id: string | null;
  environment: string | null;
  release: string | null;
  request_method: string | null;
  normalized_route: string | null;
  request_data: RequestData | null;
  response_status: number | null;
  duration_ms: number | null;
  exception_data: ExceptionData | null;
  occurred_at: string;
  received_at: string;
}

// ---------------------------------------------------------------- replay

export type TargetEnvironment = "local" | "development" | "staging" | "test";

export interface ReplayTarget {
  id: string;
  name: string;
  base_url: string;
  environment: TargetEnvironment;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ReplayTargetInput {
  name: string;
  base_url: string;
  environment: TargetEnvironment;
  enabled?: boolean;
}

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD" | "OPTIONS";

export const MUTATING_METHODS: readonly HttpMethod[] = ["POST", "PUT", "PATCH", "DELETE"];

/** A request the replay service can send. Never contains captured credentials. */
export interface RequestDefinition {
  method: HttpMethod;
  path: string;
  /** Repeated keys are arrays, so ?tag=a&tag=b round-trips. */
  query: Record<string, QueryValue>;
  headers: Record<string, string>;
  body: unknown;
}

export type ExecutionKind = "replay" | "regression_run";
export type ExecutionStatus = "pending" | "running" | "completed" | "error";
export type ExecutionOutcome = "passed" | "failed";

export interface ResponseSummary {
  status: number;
  headers: Record<string, string>;
  body: unknown;
  body_truncated: boolean;
}

export interface AssertionResult {
  description: string;
  passed: boolean;
  expected: unknown;
  actual: unknown;
}

export interface ReplayExecution {
  id: string;
  kind: ExecutionKind;
  regression_case_id: string | null;
  event_id: string | null;
  target_id: string | null;
  status: ExecutionStatus;
  outcome: ExecutionOutcome | null;
  request_summary: { method: HttpMethod; url: string; headers: Record<string, string> };
  response_summary: ResponseSummary | null;
  assertion_results: AssertionResult[] | null;
  duration_ms: number | null;
  error_summary: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface CreateReplay {
  target_id: string;
  event_id: string | null;
  request: RequestDefinition;
  /** Must be true for POST/PUT/PATCH/DELETE, or the API rejects with confirmation_required. */
  confirm_mutation: boolean;
}

// ---------------------------------------------------------------- regression cases

export type Assertion =
  | { type: "json_path_equals"; path: string; expected: unknown }
  | { type: "json_path_exists"; path: string }
  | { type: "body_contains"; expected: string };

export interface AssertionDefinition {
  expected_status: number;
  assertions: Assertion[];
}

export interface RegressionCase {
  id: string;
  incident_id: string | null;
  source_event_id: string | null;
  name: string;
  description: string | null;
  request_definition: RequestDefinition;
  assertion_definition: AssertionDefinition;
  last_run: ReplayExecution | null;
  created_at: string;
  updated_at: string;
}

export interface RegressionCaseInput {
  name: string;
  description: string | null;
  incident_id: string | null;
  source_event_id: string | null;
  request_definition: RequestDefinition;
  assertion_definition: AssertionDefinition;
}

export interface RunCase {
  target_id: string;
  confirm_mutation: boolean;
}

// ---------------------------------------------------------------- dashboard

export interface DailyCount {
  /** YYYY-MM-DD (UTC). */
  date: string;
  events: number;
}

export interface RecentRun {
  execution: ReplayExecution;
  case_id: string;
  case_name: string;
}

/** GET /projects/{id}/stats?days=N — computed from stored data, never hardcoded. */
export interface ProjectStats {
  days: number;
  open_incidents: number;
  events_in_range: number;
  new_incidents_in_range: number;
  daily: DailyCount[];
  /** Most frequent incidents by events within the range. */
  top_incidents: { incident: Incident; events: number }[];
  recent_incidents: Incident[];
  recent_runs: RecentRun[];
  regression: { total: number; passing: number; failing: number; never_run: number };
}
