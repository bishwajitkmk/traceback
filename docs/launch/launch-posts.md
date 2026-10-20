# Launch post drafts

Edit to your own voice before posting. Lead with the problem and the demo, be
upfront that it's early, and ask a real question — communities reward that.
Replace `<…>` placeholders.

## r/FastAPI (and r/Python "Showcase" flair)

**Title:** I built a tool that turns a FastAPI 500 into a replayable regression test — looking for feedback

> When a FastAPI endpoint 500s in production, I usually end up copying
> headers and payloads out of logs to reproduce it locally, and then I forget
> to write the regression test. So I built Traceback:
>
> 1. A small middleware captures the exception, stack trace and the
>    *sanitized* request (auth headers, cookies, passwords, card numbers are
>    redacted before anything leaves your app).
> 2. Failures are grouped into incidents.
> 3. You replay the exact request against your local or staging server and see
>    a field-by-field diff of the responses.
> 4. One click saves it as a regression case; `traceback run --target …` runs
>    them in CI and fails the build if a fixed bug comes back.
>
> 2-minute demo: <video link> · Try it: <demo link> · SDK/CLI (MIT): <repo link>
>
> It's early and FastAPI-only on purpose. I'd love to hear: **how did you
> reproduce your last production bug?** And what would stop you from trying
> something like this?

## Show HN

**Title:** Show HN: Traceback – turn a production API failure into a replayable regression test

> Hi HN — Traceback captures failures in FastAPI apps (exception, stack trace,
> redacted request), groups them, and lets you replay the captured request
> against a local/staging target and diff the responses. Then you save it as a
> regression case and run it from CI with a CLI, so a fixed bug can't quietly
> come back.
>
> A few design decisions you might find interesting:
> - Replay is an SSRF boundary. The server checks every resolved IP at connect
>   time (not just at registration), only follows redirects within the target's
>   origin, and never forwards captured credentials.
> - Hosted servers can't reach your localhost, so the CLI executes cases from
>   your machine/CI and the server re-evaluates the assertions.
> - Ingestion is idempotent per event id; counts stay exact under retries.
>
> Demo: <link> · Code: <link>. It's early; I'm mostly looking for people who
> fight "can't reproduce" bugs to tell me where this falls short.

## FastAPI Discord / GitHub Discussions (short)

> Built a FastAPI middleware + CLI that captures 500s with the sanitized request,
> lets you replay them against local/staging with a response diff, and saves them
> as CI regression cases. 2-min demo: <link>. Feedback very welcome — especially
> "why I wouldn't use this".

## Follow-up email to a waitlist sign-up

> Subject: Traceback — 20 minutes about your last production bug?
>
> Hi <name>, thanks for joining the Traceback waitlist. You mentioned
> "<their answer>". I'm talking to a few FastAPI developers before opening
> access — would you have 20 minutes this week? No pitch; I want to understand
> how you reproduce bugs today. Here's my calendar: <link>.
