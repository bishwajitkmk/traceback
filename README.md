# Traceback

Turn a production bug report into a repeatable test case.

Traceback captures failures from Python/FastAPI applications, groups them into
incidents, replays the captured request against a safe local or staging target,
and saves it as a regression case to prove a fix works — in the dashboard, or
from CI with the CLI. See [PRD.md](PRD.md).

## Repository layout

| Path | What it is |
|---|---|
| `backend/` | FastAPI API: auth, projects, ingestion, incidents, guarded replay, regression cases, CI endpoints. SQLAlchemy 2 + Alembic on PostgreSQL. |
| `sdk/` | `traceback-sdk` (import `traceback_sdk`): FastAPI/ASGI middleware **and** the `traceback` CLI. See [sdk/README.md](sdk/README.md). |
| `frontend/` | React + TypeScript + Vite dashboard (Tailwind, TanStack Query, React Router). |
| `examples/sample_app/` | Deliberately buggy FastAPI checkout API, instrumented with the SDK. |
| `docs/` | [Wire contracts](docs/contracts.md), [threat model](docs/threat-model.md), [ADRs](docs/adr/), [Phase 0 launch kit](docs/launch/). |

## Run it locally

Prerequisites: Docker, Python 3.12, Node 22+. Commands are written for Git Bash
on Windows (`.venv/Scripts/…`); on macOS/Linux use `.venv/bin/…`.

```bash
cp .env.example .env            # then set TRACEBACK_REPLAY_ALLOW_PRIVATE_NETWORKS=true for local replays
docker compose up -d db         # Postgres (also creates traceback_test)

# API on :8100
cd backend
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.jobs.seed_demo      # demo account + data; prints an ingestion key
.venv/Scripts/uvicorn app.main:app --reload --port 8100

# Dashboard on :5180
cd ../frontend && npm install && npm run dev

# The instrumented sample app on :9101 (uses the SDK venv)
cd ../sdk && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]" -r ../examples/sample_app/requirements.txt
cd ../examples/sample_app
TRACEBACK_API_KEY=tb_… ../../sdk/.venv/Scripts/uvicorn app:app --port 9101
```

Open http://localhost:5180 → **Open the demo project** (`demo@traceback.dev` /
`traceback-demo`). Then walk the whole workflow:

1. Trigger a real failure:
   `curl -X POST localhost:9101/checkout -H 'content-type: application/json' -d '{"cart_id":"c1","quantity":0}'`
2. Open the new `ZeroDivisionError` incident → **Replay this request** against
   *Sample app (local)* → the 500 reproduces.
3. **Save as regression case** with expected status `422`, run it → *Failed*.
4. Restart the sample app with `SAMPLE_APP_FIXED=1`, run the case again → *Passed*.
5. Or from a terminal / CI: `TRACEBACK_API_KEY=tb_… traceback run --target http://localhost:9101`

No backend? `VITE_USE_MOCKS=true npm run dev` serves the dashboard from an
in-browser mock with synthetic data ([ADR 0004](docs/adr/0004-frontend-against-mock-api.md)).

Ports are 8100/5180 (not 8000/5173) to avoid clashing with other local projects.

## Checks

```bash
cd backend  && .venv/Scripts/ruff format --check . && .venv/Scripts/ruff check . && .venv/Scripts/pytest   # needs the db container
cd sdk      && .venv/Scripts/ruff check src tests && .venv/Scripts/pytest
cd frontend && npm test && npm run build
cd frontend && npx playwright install chromium && npm run e2e    # full flow on the real stack
```

| Suite | What it proves |
|---|---|
| Backend (pytest, real Postgres) | auth/CSRF/sessions, cross-project isolation, ingestion idempotency under concurrency, redaction before persistence, grouping, filters/pagination, stats, replay SSRF rules (metadata, private ranges, redirects, connect-time DNS checks), size/time limits, regression runs, CLI endpoints, retention |
| SDK (pytest) | capture, fail-open delivery (timeouts, 5xx, retries, overflow), redaction, original response preserved, CLI exit codes and JUnit |
| Frontend (Vitest) | forms, loading/error states, filters, detail rendering, replay confirmation, diffs, cases — against the mock API |
| E2E (Playwright) | PRD §1 MVP definition: register → key → real SDK capture → incident → replay → case fails → fix → case passes (UI and CLI) → another account is rejected |

## Operations

| Task | Command |
|---|---|
| Health (liveness, no dependencies) | `GET /api/v1/health` |
| Readiness (database) | `GET /api/v1/ready` → 503 when not ready |
| Retention purge (run daily) | `python -m app.jobs.retention` |
| Export the waitlist | `python -m app.jobs.export_waitlist > waitlist.csv` |
| Reset the demo account | `python -m app.jobs.seed_demo` |
| OpenAPI | `GET /openapi.json`, docs at `/docs` outside production |

Configuration is environment variables only — see [.env.example](.env.example).
In production set `TRACEBACK_ENV=production`, a real `TRACEBACK_SECRET_KEY`,
`TRACEBACK_COOKIE_DOMAIN` (when the app and API are on sibling subdomains) and
`TRACEBACK_TRUSTED_PROXY_HOPS=1` behind Render's proxy. The API refuses to start
in production with the default secret or with private-network replay enabled.
