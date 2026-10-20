# Threat model

Scope: the MVP (PRD §12). Covers the two boundaries that matter most — event
ingestion and request replay — plus browser authentication. Each threat lists
the control and where it is tested.

## Assets

1. Captured request data from customers' production systems (may contain personal data).
2. Project ingestion keys.
3. User accounts and sessions.
4. The network position of the Traceback servers (they must not become a proxy into private networks or cloud metadata).

## Trust boundaries

```
Customer app + SDK ──(API key, HTTPS)──▶ Ingestion API ──▶ Postgres
Browser ──(session cookie + CSRF)──▶ Dashboard API ──▶ Postgres
Dashboard API ──(guarded HTTP client)──▶ Registered replay target
CLI in customer CI ──(API key)──▶ CI API;  CLI ──▶ customer's own target (never via Traceback)
```

## Ingestion

| Threat | Control | Test |
|---|---|---|
| Secrets in captured data | Redaction in the SDK **and** again on the server before persistence; built-in key list plus project rules; request bodies only when capture is enabled | `test_ingest.py::test_sensitive_data_is_redacted_before_persistence`, SDK redaction tests |
| Free-text secrets (e.g. a token inside an exception message) | **Not fully mitigated**: messages and stack lines are stored as sent. Documented limitation; SDK users should avoid secrets in exception messages | — |
| Oversized / malicious payloads | 256 KiB limit enforced while streaming; strict schema; bounded list sizes and string lengths | `test_oversized_events_are_rejected`, `test_validation_errors_are_specific` |
| Retries inflating counts | `event_id` idempotency key + unique constraint; atomic incident upsert | `test_duplicate_delivery…`, `test_concurrent_and_duplicate_delivery_keeps_counts_exact` |
| Stolen/rotated key | Keys stored as SHA-256; rotation revokes atomically (partial unique index) | `test_rotation_invalidates_the_previous_key` |
| Flooding | Per-key rate limit (600/min) | — (limiter unit-tested via login) |

## Replay (SSRF boundary)

| Threat | Control | Test |
|---|---|---|
| Replay to arbitrary hosts | Only registered targets; the request carries a *path*, never a host; path validation rejects `//host`, schemes, backslashes, control characters | `test_path_cannot_change_the_host` |
| Cloud metadata (169.254.169.254, `metadata.google.internal`, IPv6/Alibaba variants, IPv4-mapped forms) | Always blocked at registration and at connect time | `test_blocked_reason`, `test_target_registration_rules` |
| Private networks / loopback | Blocked unless the server runs in local-development mode **and** the target environment is `local`; production refuses to start with that mode on | `test_target_registration_rules`, `test_connect_time_check_blocks_private_addresses` |
| DNS rebinding / names resolving to internal IPs | Every resolved address is checked inside the HTTP client's network backend at connect time; the connection is made to the vetted IP; all answers must pass | `test_connect_time_check_blocks_private_addresses` |
| Redirect to an internal host | Redirects followed only within the target's origin (max 3); every hop still goes through the connect-time check | `test_redirects_outside_the_target_are_not_followed` |
| Proxy env vars bypassing checks | Outbound client ignores proxy environment (`trust_env=False`) | — (code review) |
| Forwarding production credentials | Credential and transport headers stripped when cases are saved and again on send | `test_replay_records_response_and_never_forwards_credentials`, `test_case_crud_strips_credentials` |
| Accidental writes | POST/PUT/PATCH/DELETE require `confirm_mutation`; UI requires an explicit acknowledgement | `test_mutating_replays_require_explicit_confirmation`, E2E |
| Resource exhaustion | 10 s timeout (also bounds slow bodies), 256 KiB response cap, 64 KiB request cap, 8 concurrent replays | `test_response_size_and_time_are_bounded`, `test_oversized_replay_body_is_rejected` |
| Replay results leaking secrets | Response headers/bodies redacted with the same rules before storage | covered by executions service |

## Browser authentication

| Threat | Control | Test |
|---|---|---|
| Password theft from the database | Argon2id; timing-equalized login for unknown emails; generic error | `test_passwords_are_hashed_with_argon2`, `test_login_logout` |
| Session theft via XSS | HttpOnly, SameSite=Lax, Secure (production) cookie; only a hash stored | `test_session_cookie_is_httponly_and_lax` |
| CSRF | Double-submit token (`tb_csrf` cookie ↔ `X-CSRF-Token` header) on every unsafe method; narrow CORS | `test_unsafe_requests_need_matching_csrf_token` |
| Session reuse after logout | Session row deleted server-side | `test_logout_invalidates_the_session_server_side` |
| Cross-project access by guessed IDs | Every project route resolves the project through the owner check; missing and foreign return the same 404 | `test_cross_project_access_is_indistinguishable_from_missing`, E2E step 7 |
| Credential stuffing | Rate limits on login (per IP+email) and registration (per IP) | `test_login_is_rate_limited` |
| Open redirect after login | `next` accepted only as a same-app path | frontend `safeNext` |

## Known limitations (accepted for the MVP)

- Rate limits are per process (in memory). With several API instances, move them to Redis (planned with the background worker).
- The ingestion key also authorizes the CI endpoints (read cases, report runs). A separate CI-scoped token is planned; until then treat the key as a secret in CI.
- No email verification or password reset yet.
- Exception messages and source lines are stored verbatim (see Ingestion).
- Server-side replay of `local` targets only makes sense in self-hosted/local mode; for hosted use, run cases with the CLI from your own network ([ADR 0005](adr/0005-replay-guard-and-cli-runner.md)).
