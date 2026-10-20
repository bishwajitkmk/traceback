# Traceback wire contracts

Contracts between independently built parts. The dashboard API contract
(browser ↔ API) lives in `frontend/src/api/types.ts`; this file covers the
SDK/CLI ↔ API contracts.

All paths are under `/api/v1`. Errors always use the envelope
`{"error": {"code": str, "message": str, "details"?: [{"field", "message"}]}}`.

## Authentication for SDK and CLI

Send the project ingestion key in a header:

```
Authorization: Bearer tb_<48 hex chars>
```

`401 invalid_api_key` for a missing, unknown or rotated key.
`429 rate_limited` (with `Retry-After` seconds) when the per-key limit is hit.

## POST /ingest/events

Body (JSON, max `TRACEBACK_MAX_EVENT_BYTES`, default 256 KiB → `413 payload_too_large`):

```jsonc
{
  "event_id": "8f0c…",              // SDK-generated UUID4; the idempotency key. Required.
  "event_type": "exception",        // "exception" | "http_error"
  "occurred_at": "2026-10-20T12:00:00.123Z",   // ISO-8601, timezone required
  "environment": "production",      // optional, <= 64 chars
  "release": "2.14.0",              // optional, <= 128 chars
  "correlation_id": "req_ab12…",    // optional, <= 128 chars
  "duration_ms": 37,                // optional, >= 0
  "request": {                      // optional for diagnostic events, present from the SDK
    "method": "POST",
    "route": "/orders/{order_id}",  // normalized route template; fallback: path
    "path": "/orders/12",
    "query": { "tag": ["a", "b"], "page": "2" },   // string | string[]
    "headers": { "content-type": "application/json" },  // lower-cased names
    "body_captured": true,          // false when capture is disabled for this route
    "body": { "quantity": 0 },      // any JSON or null; a string if not JSON
    "body_truncated": false
  },
  "response": {                     // optional
    "status": 500,
    "headers": { "content-type": "application/json" },
    "body": { "detail": "Internal Server Error" }
  },
  "exception": {                    // required when event_type = "exception"
    "type": "ZeroDivisionError",    // qualified for non-builtins, e.g. "httpx.ReadTimeout"
    "message": "division by zero",
    "frames": [                     // most recent call LAST (Python order), <= 100 frames
      { "filename": "app/services/pricing.py", "lineno": 18, "function": "unit_price",
        "context_line": "return round(total / quantity, 2)", "in_app": true }
    ]
  },
  "sdk": { "name": "traceback-sdk", "version": "0.1.0" }
}
```

Responses:

- `202` `{"event_id": "…", "incident_id": "…", "duplicate": false}`
- `202` with `"duplicate": true` when this `event_id` was already accepted for
  the project. Counts are not changed. Retrying is always safe.
- `422 validation_error` with field details.

Server behavior (the SDK must not rely on doing these itself, but should also do them):

- **Redaction before persistence.** Values of these keys are replaced with the
  string `"[REDACTED]"` anywhere in headers, query and JSON bodies (request and
  response), case-insensitive, matching when the key *contains* one of:
  `authorization, cookie, set-cookie, password, passwd, secret, token, api_key,
  apikey, api-key, x-api-key, session, csrf, credit_card, card_number, cvv, ssn`
  plus the project's configured redaction fields (exact, case-insensitive).
- **Fingerprint** = sha256 of `error type | method | route | top in-app frame
  (filename:function)`; line numbers are excluded so edits don't split incidents.
  For `http_error` the type is `HTTP <status>`.
- A new occurrence of a **resolved** incident reopens it.

## SDK behavior requirements (PRD §6.2)

- `Traceback(app, api_key=..., ...)` attaches to a FastAPI/Starlette app.
- Captures unhandled exceptions and responses with status >= `capture_status_min`
  (default 500). Never swallows or alters the app's own exception/response.
- Fail-open: delivery happens off the request path (background thread + bounded
  queue); timeouts (default 2 s), at most 3 attempts with exponential backoff,
  queue overflow drops events. Delivery errors are logged at WARNING, never raised.
- Redacts before sending (same key list as above plus `redact_fields`).
- Correlation ID: reads `X-Request-ID` / `X-Correlation-ID`, otherwise generates
  one, and sets `X-Correlation-ID` on the response.
- Body capture configurable: `capture_body` (default True), `max_body_bytes`
  (default 16 KiB, then `body_truncated: true`), `ignore_routes` (exact or
  `fnmatch` patterns), `enabled` / `environments` allow-list.

## Regression runs from the CLI (CI)

The CLI executes cases from the developer's machine or CI, so requests reach
`localhost` and private networks without the hosted service ever doing so.

### GET /ci/regression-cases

`200` → `[{ "id", "name", "request_definition", "assertion_definition" }]`
(shapes as in `frontend/src/api/types.ts`).

### POST /ci/regression-cases/{case_id}/runs

The CLI reports what happened; the **server re-evaluates the assertions** from
the reported response so the outcome rules live in one place.

```jsonc
{
  "target_url": "http://localhost:8000",
  "duration_ms": 41,
  "response": { "status": 404, "headers": {…}, "body": {…}, "body_truncated": false },
  "error": null                     // string when the request itself failed (timeout, refused…)
}
```

`200` → the stored `ReplayExecution` (with `outcome` and `assertion_results`).

## Assertion semantics (shared by server, mock and CLI)

- `status is N` always comes first.
- `json_path_equals`: path found and value equal by JSON structure.
- `json_path_exists`: path found (a `null` value counts as found).
- `body_contains`: substring of the body (JSON-serialized when not a string).
- Paths: `$`, `.key`, `["key"]`, `[0]`; leading `$` optional.
- Outcome `passed` iff every result passed.
