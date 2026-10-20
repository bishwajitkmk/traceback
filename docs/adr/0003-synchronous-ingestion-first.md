# ADR 0003: Synchronous ingestion before a queue

**Status:** Accepted — 2026-10-14

## Context
The PRD marks Redis and a background worker as P1.

## Decision
The first vertical slice persists events and updates incidents inside the
ingestion request, in one transaction, using `INSERT ... ON CONFLICT` for
incident upserts. The queue is introduced only once the full
capture → replay → regression workflow works end to end.

## Consequences
- Fewer moving parts in weeks 1–3; Docker Compose runs only Postgres, API and frontend.
- Ingestion latency includes the database write until the worker exists.
- Because idempotency and aggregation are already enforced by constraints and
  atomic upserts (ADR 0002), moving the work to a worker later does not change
  correctness.
