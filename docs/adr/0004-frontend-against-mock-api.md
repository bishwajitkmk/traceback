# ADR 0004: Build the frontend against a contract-faithful mock API

**Status:** Accepted — 2026-10-14 · Updated 2026-10-20: the backend implements the full contract; development now uses the real API by default and the mock remains for component tests and offline demos.

## Context
The frontend was built before the backend endpoints beyond `/health` and
`/ready`. Waiting would serialize the work; building against ad-hoc fixtures
would let the UI drift from the real behavior (auth, authorization, validation,
replay restrictions).

## Decision
- `frontend/src/api/types.ts` is the API contract. The backend's Pydantic
  response models must serialize to exactly these shapes.
- `frontend/src/api/mock/` implements the contract in the browser, including
  the server-side rules: session auth, 404 for other users' projects, the error
  envelope with field details, replay-target validation, host-override
  rejection, and `confirmation_required` for unconfirmed mutating replays.
- It is enabled only by `VITE_USE_MOCKS=true` (set in `frontend/.env.development`).
  Production builds never load it; the client loads it lazily as a separate chunk.
- Workflow tests (`frontend/src/test/`) render the real route tree against the
  mock, so they keep passing when the mock is swapped for the real backend only
  if the backend honors the same contract.

## Contract additions beyond PRD §11
The UI needed three read endpoints that the PRD did not list:

| Endpoint | Purpose |
|---|---|
| `GET /projects/{id}/stats?days=N` | Dashboard metrics, computed from stored data (`ProjectStats`) |
| `GET /projects/{id}/events/{event_id}` | Load one captured request for the replay workspace |
| `GET /projects/{id}/replays?event_id=…` | Replay history for one captured request |

Conventions the backend must follow:
- Redacted values are the literal string `"[REDACTED]"`; values never captured are `null`/absent.
- `RequestData.body_captured=false` means body capture was disabled (distinct from an empty body).
- Query values are `string | string[]` so repeated keys round-trip.
- CSRF: double-submit cookie `tb_csrf`, echoed in `X-CSRF-Token` on POST/PUT/PATCH/DELETE.

## Consequences
- Every page works today and is covered by tests.
- The mock duplicates some rules the backend will own; when an endpoint ships,
  run the app with `VITE_USE_MOCKS=false` and the workflow tests become the
  acceptance check for that endpoint.
