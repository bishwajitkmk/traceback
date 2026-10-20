import { Lock, Plus, Server, Trash2, X } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useLocation, useParams } from "react-router";
import { ApiError } from "../api/client";
import { useProject, useTargetMutations, useTargets, useUpdateProject } from "../api/queries";
import type { Project, ReplayTarget, TargetEnvironment } from "../api/types";
import { ApiKeyManager } from "../components/ApiKey";
import { ConfirmDialog } from "../components/Dialog";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Field,
  InlineError,
  Input,
  PageHeader,
  Select,
  Spinner,
  Table,
  td,
  th,
} from "../components/ui";

/** Always redacted by the SDK and again by the server, whatever the project rules say. */
const BUILT_IN_REDACTIONS = ["authorization", "cookie", "set-cookie", "password", "api_key", "token", "secret"];

function Saved({ show }: { show: boolean }) {
  return show ? (
    <span role="status" className="text-[13px] text-good-ink">
      Saved
    </span>
  ) : null;
}

function useFlag(): [boolean, () => void] {
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!on) return;
    const t = setTimeout(() => setOn(false), 2000);
    return () => clearTimeout(t);
  }, [on]);
  return [on, () => setOn(true)];
}

function Section({ id, title, description, children }: { id?: string; title: string; description: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="grid scroll-mt-20 gap-4 border-b border-line py-8 first:pt-0 last:border-0 lg:grid-cols-[16rem_1fr]">
      <div>
        <h2 className="font-semibold">{title}</h2>
        <p className="mt-1 text-[13px] text-ink-2">{description}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

// ---------------------------------------------------------------- general

function GeneralForm({ project }: { project: Project }) {
  const update = useUpdateProject(project.id);
  const [name, setName] = useState(project.name);
  const [saved, flash] = useFlag();
  const fieldError = update.error instanceof ApiError ? update.error.fieldErrors().name : undefined;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    update.mutate({ name: name.trim() }, { onSuccess: flash });
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-3">
      <Field label="Project name" error={!name.trim() ? "Name is required." : fieldError}>
        {(p) => <Input {...p} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <div className="text-[13px] text-ink-3">
        Slug <span className="font-mono">{project.slug}</span> · ID <span className="font-mono">{project.id}</span>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" variant="primary" loading={update.isPending} disabled={name.trim() === project.name || !name.trim()}>
          Save
        </Button>
        <Saved show={saved} />
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- targets

const ENVIRONMENTS: TargetEnvironment[] = ["local", "development", "staging", "test"];

function AddTargetForm({ projectId }: { projectId: string }) {
  const { create } = useTargetMutations(projectId);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [environment, setEnvironment] = useState<TargetEnvironment>("staging");
  const fields = create.error instanceof ApiError ? create.error.fieldErrors() : {};
  const formError = create.error instanceof ApiError && !create.error.body.details ? create.error : null;

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate(
      { name: name.trim(), base_url: baseUrl.trim(), environment },
      {
        onSuccess: () => {
          setName("");
          setBaseUrl("");
        },
      },
    );
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-3 rounded-md border border-line p-4">
      <h3 className="text-[13px] font-semibold">Add a target</h3>
      <div className="grid gap-3 sm:grid-cols-[1fr_2fr_10rem]">
        <Field label="Name" error={fields.name}>
          {(p) => <Input {...p} placeholder="Staging" value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label="Base URL" error={fields.base_url}>
          {(p) => (
            <Input
              {...p}
              className="font-mono"
              placeholder="https://staging.example.com"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          )}
        </Field>
        <Field label="Environment" error={fields.environment}>
          {(p) => (
            <Select {...p} value={environment} onChange={(e) => setEnvironment(e.target.value as TargetEnvironment)}>
              {ENVIRONMENTS.map((env) => (
                <option key={env}>{env}</option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <p className="text-xs text-ink-3">
        Production cannot be a target. Loopback and private-network addresses are accepted only for <em>local</em> targets when the
        server runs in local-development mode; cloud metadata endpoints are always blocked.
      </p>
      <InlineError error={formError} />
      <Button type="submit" variant="primary" icon={Plus} loading={create.isPending}>
        Add target
      </Button>
    </form>
  );
}

function TargetsSection({ projectId }: { projectId: string }) {
  const targets = useTargets(projectId);
  const { update, remove } = useTargetMutations(projectId);
  const [deleting, setDeleting] = useState<ReplayTarget | null>(null);

  return (
    <div className="space-y-4">
      {targets.isPending ? (
        <Spinner />
      ) : targets.isError ? (
        <ErrorState error={targets.error} retry={() => targets.refetch()} />
      ) : targets.data.length === 0 ? (
        <div className="rounded-md border border-dashed border-line-strong">
          <EmptyState icon={Server} title="No replay targets yet">
            Add the local or staging environment you want to reproduce failures against.
          </EmptyState>
        </div>
      ) : (
        <div className="rounded-md border border-line">
          <Table label="Replay targets">
            <thead className="border-b border-line bg-sunken">
              <tr>
                <th className={th} scope="col">
                  Name
                </th>
                <th className={th} scope="col">
                  Base URL
                </th>
                <th className={th} scope="col">
                  Environment
                </th>
                <th className={th} scope="col">
                  Enabled
                </th>
                <th className={th} scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {targets.data.map((t) => (
                <tr key={t.id} className="border-b border-line last:border-0">
                  <td className={`${td} font-medium`}>{t.name}</td>
                  <td className={`${td} font-mono text-[12.5px] break-all`}>{t.base_url}</td>
                  <td className={td}>
                    <Badge tone="accent">{t.environment}</Badge>
                  </td>
                  <td className={td}>
                    <label className="inline-flex items-center gap-1.5 text-[13px]">
                      <input
                        type="checkbox"
                        checked={t.enabled}
                        disabled={update.isPending}
                        onChange={(e) => update.mutate({ targetId: t.id, patch: { enabled: e.target.checked } })}
                      />
                      <span className="sr-only">Enable {t.name}</span>
                      {t.enabled ? "On" : "Off"}
                    </label>
                  </td>
                  <td className={`${td} text-right`}>
                    <Button size="sm" variant="ghost" icon={Trash2} aria-label={`Delete target ${t.name}`} onClick={() => setDeleting(t)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
      <InlineError error={update.error} />
      <AddTargetForm projectId={projectId} />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete target “${deleting?.name}”?`}
        description="Past replays keep their recorded URL and results. Regression cases will need another target to run."
        confirmLabel="Delete target"
        danger
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => setDeleting(null) })}
      >
        <InlineError error={remove.error} />
      </ConfirmDialog>
    </div>
  );
}

// ---------------------------------------------------------------- privacy

function RedactionForm({ project }: { project: Project }) {
  const update = useUpdateProject(project.id);
  const [field, setField] = useState("");
  const [saved, flash] = useFlag();
  const rules = project.redaction_rules;

  function add(e: FormEvent) {
    e.preventDefault();
    const f = field.trim();
    if (!f || rules.some((r) => r.field.toLowerCase() === f.toLowerCase())) return;
    update.mutate({ redaction_rules: [...rules, { field: f }] }, { onSuccess: () => (setField(""), flash()) });
  }

  return (
    <div className="space-y-3">
      <div>
        <h3 className="mb-1.5 text-[13px] font-medium">Always redacted</h3>
        <ul className="flex flex-wrap gap-1.5">
          {BUILT_IN_REDACTIONS.map((f) => (
            <li key={f} className="inline-flex items-center gap-1 rounded bg-sunken px-2 py-0.5 font-mono text-xs text-ink-2">
              <Lock className="size-3" aria-label="Built in" />
              {f}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="mb-1.5 text-[13px] font-medium">Project fields</h3>
        {rules.length === 0 ? (
          <p className="text-[13px] text-ink-3">No extra fields.</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {rules.map((r) => (
              <li key={r.field} className="inline-flex items-center gap-1 rounded border border-line py-0.5 pr-0.5 pl-2 font-mono text-xs">
                {r.field}
                <button
                  type="button"
                  className="rounded p-0.5 text-ink-3 hover:bg-sunken hover:text-ink"
                  aria-label={`Stop redacting ${r.field}`}
                  onClick={() => update.mutate({ redaction_rules: rules.filter((x) => x.field !== r.field) }, { onSuccess: flash })}
                >
                  <X className="size-3" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <form onSubmit={add} className="flex flex-wrap items-end gap-2">
        <Field label="Add field name" hint="Matched case-insensitively in headers, query parameters and JSON bodies." className="min-w-60 flex-1">
          {(p) => <Input {...p} className="font-mono" placeholder="card_number" value={field} onChange={(e) => setField(e.target.value)} />}
        </Field>
        <Button type="submit" icon={Plus} loading={update.isPending} disabled={!field.trim()} className="mb-5">
          Add
        </Button>
      </form>
      <Saved show={saved} />
      <InlineError error={update.error} />
    </div>
  );
}

function RetentionForm({ project }: { project: Project }) {
  const update = useUpdateProject(project.id);
  const [days, setDays] = useState(String(project.retention_days));
  const [saved, flash] = useFlag();
  const n = Number(days);
  const error = !Number.isInteger(n) || n < 1 || n > 365 ? "Enter a whole number of days from 1 to 365." : undefined;

  return (
    <form
      noValidate
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!error) update.mutate({ retention_days: n }, { onSuccess: flash });
      }}
    >
      <Field
        label="Keep events for (days)"
        error={error}
        hint="Older events and replay results are deleted. Incidents keep their counts and first/last-seen times."
        className="max-w-xs"
      >
        {(p) => <Input {...p} inputMode="numeric" className="tabular" value={days} onChange={(e) => setDays(e.target.value)} />}
      </Field>
      <div className="flex items-center gap-3">
        <Button type="submit" variant="primary" loading={update.isPending} disabled={Boolean(error) || n === project.retention_days}>
          Save
        </Button>
        <Saved show={saved} />
      </div>
      <InlineError error={update.error} />
    </form>
  );
}

export function SettingsPage() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);
  const { hash } = useLocation();

  useEffect(() => {
    if (hash && project.data) document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [hash, project.data]);

  if (project.isPending) return <Spinner />;
  if (project.isError) return <ErrorState error={project.error} retry={() => project.refetch()} />;
  const p = project.data;

  return (
    <>
      <PageHeader title="Project settings" />
      <div className="rounded-lg border border-line bg-surface px-6 py-8">
        <Section title="General" description="How this project appears in Traceback.">
          <GeneralForm project={p} />
        </Section>
        <Section id="api-key" title="Ingestion key" description="The SDK authenticates with this key. Only a hash is stored; rotating it invalidates the old key immediately.">
          <ApiKeyManager project={p} />
        </Section>
        <Section id="targets" title="Replay targets" description="The only destinations requests can be replayed to. Validated on the server on every replay.">
          <TargetsSection projectId={p.id} />
        </Section>
        <Section id="redaction" title="Redaction" description="Values of these fields are replaced with [REDACTED] before events are stored.">
          <RedactionForm project={p} />
        </Section>
        <Section id="retention" title="Retention" description="How long captured events are kept.">
          <RetentionForm project={p} />
        </Section>
      </div>
    </>
  );
}
