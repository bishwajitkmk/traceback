# Phase 0 — validate before building more

Goal: find out, cheaply, whether FastAPI developers want "turn a production
failure into a replayable regression case" enough to use it and pay for it.

## What is already built for this

- **Waitlist** on the landing page (`#waitlist`): email + the open question
  *"How did you reproduce your last production bug?"*. Stored in
  `waitlist_signups`; export with `python -m app.jobs.export_waitlist > waitlist.csv`.
- **A live demo** anyone can try: the seeded demo account, the sample app,
  and the 2-minute flow in the root README.
- **Open-source SDK + CLI** (`sdk/`), so you can share code, not just a pitch.

## Two-week plan

| Days | Do | Output |
|---|---|---|
| 1–2 | Deploy the landing page + demo (see "Minimum deploy" below). Record the demo video ([script](demo-video-script.md)). | Public URL, 2-min video |
| 3–4 | Post in r/FastAPI, r/Python, FastAPI Discord/GitHub Discussions ([drafts](launch-posts.md)). | First sign-ups |
| 3–10 | Book 10–15 calls from sign-ups and your network; run the [interview guide](interview-guide.md). | Notes per call |
| 8–10 | "Show HN" with the video and demo link. | Second wave |
| 11–14 | Score against the go/no-go criteria; decide. | Decision memo |

## Go / no-go (decide on day 14)

| Signal | Go | Pivot or stop |
|---|---|---|
| Waitlist sign-ups | ≥ 100 | < 30 |
| Answered the open question | ≥ 30% of sign-ups | mostly empty |
| Interviewees who describe a recent painful repro (unprompted) | ≥ 6 of 12 | ≤ 2 |
| "Would pay ~$9/mo" with a concrete reason | ≥ 5 people | 0–1 |
| Someone runs the demo/SDK on their own app | ≥ 3 | 0 |

If it's a "go": Phase 2 (production deploy) — see the plan in the conversation
history / roadmap. If it's a "stop": the project is still a strong portfolio
piece; ship the public demo and write-up and move on.

**Track honestly.** Count only people who are not friends being polite. A
"sounds cool" is not a signal; "can I try it on our staging this week?" is.

## Minimum deploy for Phase 0

You need a public landing page with a working waitlist and a demo. Cheapest
reliable option:

- Frontend: Cloudflare Pages or Vercel (Pro if commercial), build `frontend/`
  with `VITE_API_BASE_URL=https://api.<your-domain>/api/v1`.
- API: one Render web service from `backend/Dockerfile`, Postgres on Neon.
  Set `TRACEBACK_ENV=production`, `TRACEBACK_SECRET_KEY`, `TRACEBACK_DATABASE_URL`,
  `TRACEBACK_CORS_ORIGINS=https://app.<your-domain>`, `TRACEBACK_COOKIE_DOMAIN=.<your-domain>`,
  `TRACEBACK_TRUSTED_PROXY_HOPS=1`. Run `alembic upgrade head` as the release command.
- Put app and API on the **same registrable domain** (`app.` / `api.`) so
  session cookies are first-party.
- Seed the demo account (`python -m app.jobs.seed_demo --target https://<sample-app-url>`)
  and deploy the sample app as a second small service. In production,
  server-side replay only reaches public targets — use a public sample-app URL
  with environment `staging`, and show the CLI for local replay.

Never put real customer data in the public demo (PRD §19).
