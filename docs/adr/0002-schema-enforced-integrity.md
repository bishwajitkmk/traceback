# ADR 0002: Enforce integrity rules in the database schema

**Status:** Accepted — 2026-10-14

## Context
Several correctness requirements (no duplicate incident counts, single active
API key, never replay to production) would be bugs-in-waiting if enforced only
in service code, especially once a background worker processes events
concurrently.

## Decision
Encode them as PostgreSQL constraints and cover each with a test against a
real database (`backend/tests/test_schema_constraints.py`):

| Rule | Constraint |
|---|---|
| One incident per fingerprint per project | `UNIQUE (project_id, fingerprint)` |
| Duplicate SDK deliveries are ignored | `UNIQUE (project_id, idempotency_key)` on events |
| Rotation invalidates the old key | partial unique index: one key per project `WHERE revoked_at IS NULL` |
| Replay never targets production | `CHECK environment IN ('local','development','staging','test')` |
| A regression run belongs to a case | `CHECK kind <> 'regression_run' OR regression_case_id IS NOT NULL` |
| Status columns hold known values | `CHECK col IN (...)` on VARCHAR (not native enums, which migrate poorly) |

Constraint names follow a fixed naming convention so Alembic migrations are deterministic.

## Consequences
- Services still validate first to return friendly errors; the database is the backstop.
- Adding a status value requires a migration that replaces the CHECK constraint.
