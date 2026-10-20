import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import { DEMO_EMAIL, DEMO_PASSWORD } from "../api/mock/demo";
import { useLogin, useMe, useRegister } from "../api/queries";
import { TopBanner } from "../components/AppShell";
import { Logo } from "../components/Logo";
import { Button, Field, InlineError, Input, Spinner } from "../components/ui";
import { SHOW_DEMO_LOGIN } from "../lib/config";

/** Only same-app relative paths are honored, so `next` cannot redirect off-site. */
function safeNext(next: string | null, fallback: string): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : fallback;
}

function validate(email: string, password: string, mode: "login" | "register") {
  const errors: { email?: string; password?: string } = {};
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) errors.email = "Enter a valid email address.";
  if (!password) errors.password = "Enter your password.";
  else if (mode === "register" && password.length < 10) errors.password = "Use at least 10 characters.";
  return errors;
}

function AuthForm({ mode }: { mode: "login" | "register" }) {
  const [params] = useSearchParams();
  const demo = SHOW_DEMO_LOGIN && mode === "login" && params.has("demo");
  const [email, setEmail] = useState(demo ? DEMO_EMAIL : "");
  const [password, setPassword] = useState(demo ? DEMO_PASSWORD : "");
  const [touched, setTouched] = useState(false);
  const me = useMe();
  const login = useLogin();
  const register = useRegister();
  const mutation = mode === "login" ? login : register;
  const navigate = useNavigate();
  // New accounts land on the welcome/onboarding view. The same target is used by the
  // "already signed in" redirect below, which fires as soon as the session exists.
  const next = safeNext(params.get("next"), mode === "register" ? "/projects?new=1" : "/projects");

  if (me.isPending) return <Spinner />;
  if (me.data) return <Navigate to={next} replace />;

  const clientErrors = touched ? validate(email, password, mode) : {};
  const serverErrors = mutation.error instanceof ApiError ? mutation.error.fieldErrors() : {};
  const errors = { ...serverErrors, ...clientErrors };
  const formError = mutation.error instanceof ApiError && !mutation.error.body.details ? mutation.error : null;

  function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (Object.keys(validate(email, password, mode)).length) return;
    mutation.mutate({ email: email.trim(), password }, { onSuccess: () => navigate(next) });
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <Field label="Email" error={errors.email}>
        {(p) => (
          <Input {...p} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        )}
      </Field>
      <Field
        label="Password"
        error={errors.password}
        hint={mode === "register" ? "At least 10 characters." : undefined}
      >
        {(p) => (
          <Input
            {...p}
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        )}
      </Field>
      {formError && <InlineError error={formError} />}
      <Button type="submit" variant="primary" className="w-full" loading={mutation.isPending}>
        {mode === "login" ? "Sign in" : "Create account"}
      </Button>
    </form>
  );
}

function AuthLayout({ title, children, footer }: { title: string; children: React.ReactNode; footer: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <TopBanner />
      <main className="flex flex-col items-center px-4 pt-16">
        <Link to="/" className="mb-8 flex items-center gap-2 text-lg font-semibold">
          <Logo size={28} />
          Traceback
        </Link>
        <div className="w-full max-w-sm rounded-lg border border-line bg-surface p-6 shadow-sm">
          <h1 className="mb-5 text-lg font-semibold">{title}</h1>
          {children}
        </div>
        <p className="mt-4 text-[13px] text-ink-2">{footer}</p>
      </main>
    </div>
  );
}

export function LoginPage() {
  return (
    <AuthLayout
      title="Sign in"
      footer={
        <>
          New to Traceback?{" "}
          <Link to="/register" className="font-medium text-accent-strong hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <AuthForm mode="login" />
    </AuthLayout>
  );
}

export function RegisterPage() {
  return (
    <AuthLayout
      title="Create your account"
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-accent-strong hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <AuthForm mode="register" />
    </AuthLayout>
  );
}
