import { ArrowRight, Bug, CheckCircle2, GitCompare, Radar, RotateCcw, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { ApiError } from "../api/client";
import { waitlistApi } from "../api/endpoints";
import { useMe } from "../api/queries";
import { CodeBlock } from "../components/Code";
import { Logo } from "../components/Logo";
import { TopBanner } from "../components/AppShell";
import { Button, ButtonLink, Field, InlineError, Input, Textarea } from "../components/ui";
import { SHOW_DEMO_LOGIN } from "../lib/config";
import { DEMO_EMAIL, DEMO_PASSWORD } from "../api/mock/demo";

const STEPS = [
  { icon: Radar, title: "Capture", text: "The FastAPI SDK records the exception, stack trace and sanitized request — redacted before it leaves your app." },
  { icon: Bug, title: "Investigate", text: "Failures are grouped into incidents by a stable fingerprint, with every occurrence and its context." },
  { icon: RotateCcw, title: "Reproduce", text: "Replay the captured request against an approved local or staging target. Never production." },
  { icon: GitCompare, title: "Compare", text: "See the original and replayed responses side by side, down to individual JSON fields." },
  { icon: CheckCircle2, title: "Verify", text: "Save it as a regression case and rerun it after the fix to prove the bug is gone." },
];

const INSTALL = `# pip install traceback-sdk
import os
from fastapi import FastAPI
from traceback_sdk import Traceback

app = FastAPI()
Traceback(app, api_key=os.environ["TRACEBACK_API_KEY"], environment="production")

# In CI: run saved regression cases from your own machine
# $ traceback run --target http://localhost:8000`;

/** Phase 0 validation: collect interest and the one question that matters most. */
function WaitlistForm() {
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done">("idle");
  const [error, setError] = useState<unknown>(null);
  const fieldError = error instanceof ApiError ? error.fieldErrors().email : undefined;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setState("sending");
    try {
      await waitlistApi.join(email.trim(), "landing", note.trim() || undefined);
      setState("done");
    } catch (err) {
      setError(err);
      setState("idle");
    }
  }

  if (state === "done") {
    return (
      <p role="status" className="flex items-center gap-2 rounded-md bg-good-wash px-4 py-3 text-good-ink">
        <CheckCircle2 className="size-4" aria-hidden /> Thanks — you’re on the list. We’ll email you when hosted Traceback opens.
      </p>
    );
  }
  return (
    <form onSubmit={submit} noValidate className="space-y-3">
      <Field label="Work email" error={fieldError}>
        {(p) => (
          <Input {...p} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
        )}
      </Field>
      <Field label="How did you reproduce your last production bug?" hint="Optional, but it shapes what we build next.">
        {(p) => <Textarea {...p} rows={2} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />}
      </Field>
      {Boolean(error) && !fieldError && <InlineError error={error} />}
      <Button type="submit" variant="primary" loading={state === "sending"}>
        Join the waitlist
      </Button>
    </form>
  );
}

export function LandingPage() {
  const me = useMe();
  const signedIn = Boolean(me.data);

  return (
    <div className="min-h-screen bg-surface">
      <TopBanner />
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <Link to="/" className="flex items-center gap-2 font-semibold">
          <Logo size={26} />
          Traceback
        </Link>
        <nav aria-label="Main" className="flex items-center gap-2">
          <a href="#how" className="hidden px-2 text-ink-2 hover:text-ink sm:inline">
            How it works
          </a>
          <a href="#install" className="hidden px-2 text-ink-2 hover:text-ink sm:inline">
            Install
          </a>
          <a href="#waitlist" className="hidden px-2 text-ink-2 hover:text-ink sm:inline">
            Early access
          </a>
          {signedIn ? (
            <ButtonLink to="/projects" variant="primary">
              Open dashboard
            </ButtonLink>
          ) : (
            <>
              <ButtonLink to="/login" variant="ghost">
                Sign in
              </ButtonLink>
              <ButtonLink to="/register" variant="primary">
                Create account
              </ButtonLink>
            </>
          )}
        </nav>
      </header>

      <main>
        <section className="mx-auto grid max-w-6xl items-center gap-10 px-6 pt-10 pb-20 lg:grid-cols-[1.1fr_1fr]">
          <div>
            <p className="mb-3 text-[13px] font-medium tracking-wide text-accent-strong uppercase">For Python & FastAPI APIs</p>
            <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
              Turn a production bug report into a repeatable test case.
            </h1>
            <p className="mt-5 max-w-xl text-lg text-ink-2">
              Traceback captures API failures with their request context, lets you replay them safely against your own
              environment, and keeps them as regression cases — so you can prove a fix works.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonLink to={signedIn ? "/projects" : "/register"} variant="primary" className="h-10 px-4">
                {signedIn ? "Open dashboard" : "Create a free account"}
                <ArrowRight className="size-4" aria-hidden />
              </ButtonLink>
              {!signedIn && (
                <ButtonLink to="/login?demo=1" className="h-10 px-4">
                  Open the demo project
                </ButtonLink>
              )}
            </div>
            {SHOW_DEMO_LOGIN && !signedIn && (
              <p className="mt-3 text-[13px] text-ink-3">
                Demo login: <span className="font-mono">{DEMO_EMAIL}</span> / <span className="font-mono">{DEMO_PASSWORD}</span>
              </p>
            )}
          </div>

          {/* Product glimpse: the comparison that makes Traceback different. */}
          <figure className="rounded-xl border border-line bg-page p-4 shadow-sm" aria-label="Example response comparison">
            <div className="mb-3 flex items-center justify-between text-[13px]">
              <span className="font-medium">POST /checkout · replay vs original</span>
              <span className="rounded bg-good-wash px-1.5 py-0.5 text-xs font-medium text-good-ink">Fix verified</span>
            </div>
            <div className="grid grid-cols-2 gap-3 font-mono text-[12px]">
              <div className="rounded-md border border-line bg-surface p-3">
                <div className="mb-2 text-ink-3">Original · 500</div>
                <div className="rounded bg-diff-remove px-1">"detail": "Internal Server Error"</div>
              </div>
              <div className="rounded-md border border-line bg-surface p-3">
                <div className="mb-2 text-ink-3">Replayed · 422</div>
                <div className="rounded bg-diff-add px-1">"code": "invalid_quantity"</div>
              </div>
            </div>
            <figcaption className="mt-3 text-[13px] text-ink-2">
              ZeroDivisionError in <span className="font-mono">pricing.unit_price</span> — reproduced, fixed and locked in as a regression case.
            </figcaption>
          </figure>
        </section>

        <section id="how" className="border-y border-line bg-page">
          <div className="mx-auto max-w-6xl px-6 py-16">
            <h2 className="text-2xl font-semibold tracking-tight">One workflow, from failure to proof</h2>
            <p className="mt-2 max-w-2xl text-ink-2">
              A conventional error dashboard answers “what failed?”. Traceback also answers “can I reproduce it, and can I
              prove the fix works?”
            </p>
            <ol className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              {STEPS.map((s, i) => (
                <li key={s.title} className="rounded-lg border border-line bg-surface p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <span className="flex size-6 items-center justify-center rounded-full bg-accent-wash text-xs font-semibold text-accent-strong">
                      {i + 1}
                    </span>
                    <s.icon className="size-4 text-ink-2" aria-hidden />
                  </div>
                  <h3 className="font-semibold">{s.title}</h3>
                  <p className="mt-1 text-[13px] text-ink-2">{s.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="mx-auto grid max-w-6xl gap-10 px-6 py-16 lg:grid-cols-2" id="install">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Install in a minute</h2>
            <p className="mt-2 text-ink-2">
              Add the SDK to your FastAPI app with a project API key. Delivery failures never break your app, and sensitive
              fields are redacted before anything is sent.
            </p>
            <ul className="mt-6 space-y-3 text-[13px]">
              {[
                "Authorization headers, cookies, passwords and API keys are always redacted.",
                "Replays go only to targets you register. Cloud metadata and private networks are blocked.",
                "Mutating requests (POST, PUT, PATCH, DELETE) require explicit confirmation.",
              ].map((t) => (
                <li key={t} className="flex gap-2">
                  <ShieldCheck className="mt-0.5 size-4 shrink-0 text-good-ink" aria-hidden />
                  {t}
                </li>
              ))}
            </ul>
          </div>
          <CodeBlock value={INSTALL} title="main.py" />
        </section>

        <section id="waitlist" className="border-t border-line bg-page">
          <div className="mx-auto grid max-w-6xl gap-10 px-6 py-16 lg:grid-cols-2">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">Get early access to hosted Traceback</h2>
              <p className="mt-2 text-ink-2">
                The SDK and CLI are open source. We’re opening the hosted dashboard to a small group of FastAPI teams first.
                Leave your email and we’ll reach out — no newsletter, no spam.
              </p>
            </div>
            <WaitlistForm />
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-2 px-6 py-6 text-[13px] text-ink-3">
          <span>Traceback — make failures reproducible, understandable and verifiable.</span>
          <a href="https://github.com" className="hover:text-ink">
            Documentation
          </a>
        </div>
      </footer>
    </div>
  );
}
