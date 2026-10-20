# ADR 0001: Monorepo with one directory per deployable

**Status:** Accepted — 2026-10-14

## Context
Traceback has four parts with different runtimes and release cadences: the
core API, the Python SDK (published separately), the React frontend, and a
sample instrumented app used for demos and E2E tests.

## Decision
One repository, with `backend/`, `sdk/`, `frontend/` and `examples/` as
independent projects, each with its own dependency manifest and test suite.
The SDK has **no dependency** on backend code; the event schema is the only
contract between them and is documented and tested on both sides.

The SDK's import name is `traceback_sdk`, because `traceback` would shadow the
standard library module.

## Consequences
- Each part can be built, tested and deployed alone (Vercel / Render / PyPI).
- CI runs one job per project.
- Shared schema changes need coordinated edits in two places.
