# traceback-sdk

Python SDK and CLI for [Traceback](../README.md). The SDK captures unhandled
exceptions and server-side failures in FastAPI / Starlette applications and
sends redacted events to the Traceback ingestion API. The CLI sends a test
event and runs saved regression cases in CI.

The import name is `traceback_sdk`. It is not `traceback`, because that would
shadow the standard-library module.

## Install

```bash
pip install traceback-sdk            # from a package index
pip install -e path/to/sdk           # from this repository
pip install -e "path/to/sdk[dev]"    # plus pytest, fastapi and ruff for development
```

Requires Python 3.10+, `httpx`, and a Starlette-based framework (FastAPI or Starlette).

## Quickstart

```python
import os

from fastapi import FastAPI
from traceback_sdk import Traceback

app = FastAPI()

Traceback(app, api_key=os.environ["TRACEBACK_API_KEY"], environment="production")
```

Call `Traceback(...)` once, after you create the app and before it serves its
first request. Then check the connection:

```bash
traceback check --api-key "$TRACEBACK_API_KEY"
```

## What gets captured

For every request where an exception goes unhandled, or the response status is
`>= capture_status_min` (default 500), the SDK sends one event:

- `event_type`: `exception` (unhandled exception) or `http_error` (failing status, no exception)
- `event_id`: a UUID4 generated per event. The server uses it as the idempotency key, so retries reuse it.
- method, normalized route template (`/orders/{order_id}`; the raw path when no route matched), path,
  query (a repeated key becomes a list), lower-cased headers, request body, duration
- response status, headers and (bounded) body
- for exceptions: the qualified type (`ZeroDivisionError`, `httpx.ReadTimeout`), the message, and
  up to 100 stack frames, most recent call last, each with `filename`, `lineno`, `function`,
  `context_line` and `in_app`
- `environment`, `release`, `correlation_id`, SDK name and version

Successful requests send nothing.

### Correlation ID

The SDK reads `X-Correlation-ID`, then `X-Request-ID`, from the request. If
neither is there, it generates `req_<12 hex>`. It sets `X-Correlation-ID` on
every response, including the 500 that Starlette's error handler sends. If the
app already set its own `X-Correlation-ID`, the SDK leaves it alone.

### Redaction

Before an event is queued, the SDK replaces with `"[REDACTED]"` the value of
any header, query parameter or JSON body key (request and response, at any
depth) in these two cases:

- the key **contains**, ignoring case, one of: `authorization, cookie, set-cookie, password,
  passwd, secret, token, api_key, apikey, api-key, x-api-key, session, csrf, credit_card,
  card_number, cvv, ssn`
- the key **equals**, ignoring case, one of your `redact_fields`

`application/x-www-form-urlencoded` bodies are redacted the same way. The
server applies the same rules again before it stores anything.

### Your app behaves exactly as before

- The middleware is pure ASGI and wraps the outermost layer of the app. It does not use `BaseHTTPMiddleware`.
- The request body is pre-read up to `max_body_bytes`. The app then receives the full original
  body, unchanged and in the same messages.
- Exceptions are re-raised after capture, so Starlette's error handling and your server see them
  as before. Responses keep their status, body and headers; the only addition is `X-Correlation-ID`.
- Delivery runs on a background daemon thread fed by a bounded queue. The request path never
  waits on the network.
- Delivery errors are logged at WARNING through `logging.getLogger("traceback_sdk")` and never
  raised. Request and response bodies never appear in logs.

## Options

```python
Traceback(
    app,
    api_key,                      # project ingestion key, "tb_..."; empty disables capture with a warning
    endpoint=None,                # default: $TRACEBACK_ENDPOINT, else http://localhost:8100/api/v1
    environment=None,             # e.g. "production" (max 64 chars)
    release=None,                 # e.g. "2.14.0" (max 128 chars)
    enabled=True,                 # False: attach nothing, send nothing
    environments=None,            # allow-list; capture is disabled if `environment` is not in it
    capture_status_min=500,       # capture responses with status >= this
    capture_body=True,            # capture request/response bodies (body_captured=false when off)
    max_body_bytes=16384,         # per body; longer bodies are cut and body_truncated=true
    ignore_routes=(),             # exact or fnmatch patterns, matched against the path and the route template
    redact_fields=(),             # extra keys to redact (exact match, ignoring case)
    timeout=2.0,                  # per-attempt HTTP timeout, seconds
    max_retries=3,                # maximum delivery attempts per event, the first one included
    queue_size=1000,              # events waiting for delivery; new events are dropped when full
    in_app_include=None,          # module/path prefixes that count as in_app (see below)
    transport=None,               # custom httpx transport (tests: httpx.MockTransport)
    backoff_base=0.5,             # retry delays: backoff_base * 2**(attempt-1) ...
    max_backoff=10.0,             # ... capped at this; also caps the Retry-After of a 429
)
```

- **Retries.** The SDK retries network errors, timeouts, 5xx and `429`. It honors
  `Retry-After` up to `max_backoff`. Any other 4xx (invalid key, validation error, payload
  too large) is logged once and the event is dropped.
- **`in_app`.** By default a frame is in-app unless it lives in site-packages / dist-packages,
  the standard library or the SDK itself. With `in_app_include=["myapp", "services/"]`, only
  frames whose module name or (cwd-relative) filename starts with one of the prefixes count.
- **Filenames** are relative to the working directory, or to `site-packages` for libraries.
  This keeps incident fingerprints the same across hosts.
- **`ignore_routes`.** `"/health"`, `"/internal/*"` and `"/orders/{order_id}"` all work. The
  path is checked before the request is handled; the route template is checked after routing.

Methods:

- `tb.flush(timeout=2.0) -> bool` waits until queued events are delivered. It returns `True` if the queue drained.
- `tb.close(timeout=2.0)` flushes, then stops the worker thread. It is registered with `atexit`.
  The queue is also flushed during ASGI lifespan shutdown (for example when uvicorn stops).
- `tb.dropped_events` is the number of events dropped because the queue was full.

For a plain ASGI app (no `build_middleware_stack`), wrap it yourself:
`app = TracebackMiddleware(inner_app, client=tb)`.

## CLI

The package installs a `traceback` console script. It is the same as `python -m traceback_sdk.cli`.

### `traceback check`

```bash
traceback check --api-key tb_... [--endpoint http://localhost:8100/api/v1] [--environment development]
```

Sends one synthetic `exception` event of type `TracebackTestEvent` and prints
the incident it was grouped into. It exits 0 when the server accepts the event
(HTTP 202), 2 for a bad key or an unreachable server, and 1 for any other
rejection.

### `traceback run`

```bash
export TRACEBACK_API_KEY=tb_...
traceback run --target http://localhost:9101 \
  [--case CASE_ID ...] [--endpoint URL] [--junit report.xml] [--timeout 10]
```

1. Fetches the project's cases from `GET /ci/regression-cases`. `--case` (repeatable) picks a subset.
2. Sends each case's request to `--target` **from the machine the CLI runs on**, so it can reach
   `localhost` and private networks. Redirects are not followed. The response body is read up to
   256 KiB (`body_truncated` beyond that). Credential headers (`authorization`, `proxy-authorization`,
   `cookie`, `set-cookie`, `x-api-key`, `x-auth-token`, `x-csrf-token`) and values still set to
   `[REDACTED]` are never sent to the target.
3. Reports each result to `POST /ci/regression-cases/{id}/runs`. The server evaluates the
   assertions, and the CLI shows the server's outcome. If the report cannot be delivered, the CLI
   evaluates the assertions locally with the same rules and prints a warning.
4. Prints a pass/fail table and, with `--junit`, writes a JUnit XML report.

Each case runs exactly as saved, including `POST`/`PUT`/`PATCH`/`DELETE`, so
point `--target` at a test environment.

Exit codes: `0` all passed, `1` at least one case failed or errored, `2`
configuration, authentication or API errors (missing key, `401`, unknown case
id, server unreachable).

```yaml
# GitHub Actions example
- run: traceback run --target http://localhost:9101 --junit traceback.xml
  env:
    TRACEBACK_API_KEY: ${{ secrets.TRACEBACK_API_KEY }}
    TRACEBACK_ENDPOINT: https://traceback.example.com/api/v1
```

Assertion semantics (shared with the server):

- `status is N` always comes first.
- `json_path_equals` passes when the path exists and its value is equal by JSON structure.
- `json_path_exists` passes when the path exists; a `null` value counts.
- `body_contains` passes when the text is a substring of the body (JSON-serialized when the body is not a string).

Paths support `$`, `.key`, `["key"]` and `[0]`, and the leading `$` is optional.

## Limitations

- **One process, one background thread.** Each worker process (for example each uvicorn or gunicorn
  worker) has its own queue and thread. Nothing is shared between processes.
- **Events can be lost.** Events still in the queue are lost if the process is killed hard
  (SIGKILL, OOM, crash). On normal shutdown, the queue is flushed for up to 2 seconds. Events are
  also dropped when the queue is full or ingestion stays down past the retry budget.
- **Body capture is bounded.** Only the first `max_body_bytes` of each request and response body is
  kept, and a truncated body is sent as text. Non-UTF-8 bytes are replaced. Streaming and
  very large uploads are passed through untouched, but only their first bytes are captured.
- **ASGI only.** Supported: Starlette-based ASGI apps (FastAPI, Starlette) directly, other ASGI apps
  through `TracebackMiddleware`. Not supported: WSGI frameworks (Flask, Django WSGI) and
  WebSocket connections.
- **Mounted sub-applications** report the route template relative to the mount.
- **Exception chains.** Only the outermost exception's own traceback is sent; `__cause__` and
  `__context__` are not.

## Development

```bash
cd sdk
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"   # Windows paths
.venv/Scripts/python -m pytest
.venv/Scripts/ruff check .
```
