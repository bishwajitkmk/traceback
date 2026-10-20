# ADR 0005: Connect-time SSRF guard, and a CLI runner for local targets

**Status:** Accepted — 2026-10-20

## Context
Replay makes the Traceback server send HTTP requests chosen by users — a
server-side request forgery (SSRF) boundary (PRD §6.6). Validating a URL when a
target is registered is not enough: DNS answers can change later (rebinding),
redirects can point elsewhere, and hostnames can resolve to internal addresses.

Separately, a hosted service cannot reach a developer's `localhost`, yet
"replay against local" is central to the product.

## Decision
1. **Guard at connect time.** The replay client is httpx with a custom
   `httpcore` network backend (`GuardedBackend`). Every TCP connection resolves
   the host, rejects it if *any* address is prohibited (metadata, link-local,
   multicast, reserved, and — unless local-development mode is on for a `local`
   target — loopback/private/CGNAT), then connects to the vetted IP. TLS still
   verifies against the hostname. Proxies from the environment are ignored.
   Redirects are followed only within the target's origin.
   This relies on one private attribute (`HTTPTransport._pool`), so httpx is
   pinned to `0.28.*` and a test fails if the guard stops running.
2. **The CLI runs cases where the target is reachable.** `traceback run`
   (in the SDK package) fetches cases with the project key, sends the requests
   from the developer's machine or CI, and reports the responses. The server
   re-evaluates assertions, so outcome rules live in one place and a runner
   cannot report a pass for a failing response.
3. **Rate limiting is in-process** for the single-instance MVP.

## Consequences
- Hosted Traceback never needs network access into customer environments.
- Local replay from the dashboard is a self-hosted / development feature
  (`TRACEBACK_REPLAY_ALLOW_PRIVATE_NETWORKS=true`, refused in production).
- The ingestion key currently also authorizes the two CI endpoints; a separate
  CI-scoped token is a planned follow-up.
- Rate limits must move to Redis before running more than one API instance.
