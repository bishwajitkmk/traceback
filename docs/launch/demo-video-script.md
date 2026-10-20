# Demo video script (≈ 2 minutes)

Setup before recording: API, dashboard and sample app running (README "Run it
locally"), a fresh project with a key, sample app started *buggy*, browser at
1440×900, terminal with large font.

| Time | Screen | Say |
|---|---|---|
| 0:00 | Landing page hero | "When an API fails in production, the hard part isn't seeing the error — it's reproducing it and proving the fix. Traceback turns the failure into a test." |
| 0:10 | Terminal: `curl … /checkout -d '{"quantity":0}'` → 500 | "Here's a checkout endpoint with a bug. A customer hits it." |
| 0:20 | Incidents list → ZeroDivisionError appears | "The SDK captured it — grouped as an incident." |
| 0:30 | Incident detail: stack trace, request, *Redacted* badges | "Full stack trace and the exact request. Card numbers, cookies and auth headers were redacted before they left the app." |
| 0:45 | Replay this request → Review & send → tick the acknowledgement | "Replay it against my local copy. It's a POST, so Traceback makes me confirm — it never replays against production." |
| 0:55 | Result: 500 vs 500, bodies identical | "Reproduced. Same 500." |
| 1:05 | Save as regression case → expected status 422 → Save → Run → *Failed* | "Save it as a regression case that expects the correct behavior. Right now it fails — good." |
| 1:20 | Editor: fix `pricing.py`; restart with `SAMPLE_APP_FIXED=1` | "Fix the bug…" |
| 1:30 | Run case → *Passed*; diff shows `$.detail` removed, `$.error` added | "…run it again. Passed — and here's exactly what changed in the response." |
| 1:40 | Terminal: `traceback run --target http://localhost:9101` → PASS | "The same cases run in CI with one command, so this bug can't quietly come back." |
| 1:50 | Landing page waitlist | "It's early and FastAPI-only. If this is a problem you have, I'd love to talk — link below." |
