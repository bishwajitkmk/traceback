import { ChevronLeft, FlaskConical, Pencil, Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { useCase, useCaseMutations, useCaseRuns, useCases, useEvent, useTargets } from "../api/queries";
import type { ReplayExecution } from "../api/types";
import { CaseForm, type CaseFormValues } from "../components/CaseForm";
import { CodeBlock } from "../components/Code";
import { ConfirmDialog } from "../components/Dialog";
import {
  Button,
  ButtonLink,
  cx,
  EmptyState,
  ErrorState,
  HttpStatus,
  InlineError,
  MethodTag,
  PageHeader,
  Panel,
  Select,
  Spinner,
  StatusBadge,
  Table,
  td,
  th,
} from "../components/ui";
import { describeAssertion } from "../lib/assertions";
import { formatDateTime, formatDuration, formatRelative } from "../lib/format";
import { isMutating, queryToString, requestFromEvent } from "../lib/request";
import type { CaseDraftState } from "./ReplayPage";

// ---------------------------------------------------------------- list

export function CasesPage() {
  const { projectId = "" } = useParams();
  const cases = useCases(projectId);
  const base = `/projects/${projectId}`;

  return (
    <>
      <PageHeader
        title="Regression cases"
        description="Saved requests with expected responses. Rerun them to prove a fix works — and keeps working."
        actions={
          <ButtonLink to={`${base}/cases/new`} variant="primary">
            <Plus className="size-4" aria-hidden /> New case
          </ButtonLink>
        }
      />
      <Panel bodyClassName="p-0">
        {cases.isPending ? (
          <Spinner />
        ) : cases.isError ? (
          <ErrorState error={cases.error} retry={() => cases.refetch()} />
        ) : cases.data.length === 0 ? (
          <EmptyState
            icon={FlaskConical}
            title="No regression cases yet"
            action={<ButtonLink to={`${base}/incidents`}>Find an incident</ButtonLink>}
          >
            Replay a captured failure, then choose “Save as regression case”.
          </EmptyState>
        ) : (
          <Table label="Regression cases">
            <thead className="border-b border-line bg-sunken">
              <tr>
                <th className={th} scope="col">
                  Case
                </th>
                <th className={th} scope="col">
                  Request
                </th>
                <th className={th} scope="col">
                  Expects
                </th>
                <th className={th} scope="col">
                  Last run
                </th>
              </tr>
            </thead>
            <tbody>
              {cases.data.map((c) => (
                <tr key={c.id} className="border-b border-line last:border-0 hover:bg-sunken">
                  <td className={cx(td, "max-w-sm")}>
                    <Link to={`${base}/cases/${c.id}`} className="font-medium hover:underline">
                      {c.name}
                    </Link>
                    {c.description && <div className="truncate text-[13px] text-ink-3">{c.description}</div>}
                  </td>
                  <td className={cx(td, "whitespace-nowrap")}>
                    <MethodTag method={c.request_definition.method} />{" "}
                    <span className="font-mono text-[12.5px]">{c.request_definition.path}</span>
                  </td>
                  <td className={td}>
                    <HttpStatus status={c.assertion_definition.expected_status} />
                    {c.assertion_definition.assertions.length > 0 && (
                      <span className="ml-1.5 text-xs text-ink-3">+{c.assertion_definition.assertions.length}</span>
                    )}
                  </td>
                  <td className={cx(td, "whitespace-nowrap")}>
                    <StatusBadge status={c.last_run ? (c.last_run.outcome ?? c.last_run.status) : null} />
                    {c.last_run && <span className="ml-2 text-xs text-ink-3">{formatRelative(c.last_run.started_at)}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
    </>
  );
}

// ---------------------------------------------------------------- create

export function NewCasePage() {
  const { projectId = "" } = useParams();
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const fromReplay = location.state as CaseDraftState | null;
  const eventId = params.get("event");
  const event = useEvent(projectId, eventId);
  const { create } = useCaseMutations(projectId);
  const base = `/projects/${projectId}`;

  if (eventId && event.isPending) return <Spinner />;
  if (event.isError) return <ErrorState error={event.error} />;

  const request = fromReplay?.request ??
    (event.data ? requestFromEvent(event.data) : { method: "GET" as const, path: "/", query: {}, headers: {}, body: null });
  const route = event.data?.normalized_route ?? request.path;
  const initial: CaseFormValues = {
    name: event.data?.exception_data ? `${request.method} ${route} no longer raises ${event.data.exception_data.type}` : "",
    description: "",
    request,
    assertions: { expected_status: fromReplay?.expectedStatus ?? 200, assertions: [] },
  };

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link to={`${base}/cases`} className="inline-flex items-center gap-0.5 hover:text-ink">
            <ChevronLeft className="size-3.5" aria-hidden /> Regression cases
          </Link>
        }
        title="New regression case"
        description={
          fromReplay
            ? "Prefilled from the request you edited in the replay workspace. Credentials were not copied."
            : eventId
              ? "Prefilled from the captured request. Credentials were not copied."
              : undefined
        }
      />
      <CaseForm
        initial={initial}
        submitLabel="Save case"
        pending={create.isPending}
        error={create.error}
        onCancel={() => navigate(-1)}
        onSubmit={(v) =>
          create.mutate(
            {
              ...v,
              incident_id: params.get("incident") ?? event.data?.incident_id ?? null,
              source_event_id: eventId,
            },
            { onSuccess: (c) => navigate(`${base}/cases/${c.id}`, { replace: true }) },
          )
        }
      />
    </>
  );
}

// ---------------------------------------------------------------- detail

function RunResult({ run }: { run: ReplayExecution }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-[13px]">
        <StatusBadge status={run.outcome ?? run.status} />
        {run.response_summary && <HttpStatus status={run.response_summary.status} />}
        <span className="text-ink-2">{formatDuration(run.duration_ms)}</span>
        <span className="text-ink-3" title={formatDateTime(run.started_at)}>
          {formatRelative(run.started_at)}
        </span>
      </div>
      {run.error_summary && <InlineError error={new Error(run.error_summary)} />}
      {run.assertion_results && (
        <Table label="Assertion results">
          <thead className="border-b border-line bg-sunken">
            <tr>
              <th className={th} scope="col">
                Result
              </th>
              <th className={th} scope="col">
                Assertion
              </th>
              <th className={th} scope="col">
                Actual
              </th>
            </tr>
          </thead>
          <tbody>
            {run.assertion_results.map((r, i) => (
              <tr key={i} className="border-b border-line last:border-0">
                <td className={td}>
                  <StatusBadge status={r.passed ? "passed" : "failed"} />
                </td>
                <td className={cx(td, "font-mono text-[12.5px]")}>{r.description}</td>
                <td className={cx(td, "font-mono text-[12.5px] break-all text-ink-2")}>
                  {r.actual === undefined ? "missing" : r.actual === null ? "—" : JSON.stringify(r.actual)}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {run.response_summary && <CodeBlock value={run.response_summary.body} title="Response body" maxHeight="14rem" />}
    </div>
  );
}

export function CaseDetailPage() {
  const { projectId = "", caseId = "" } = useParams();
  const navigate = useNavigate();
  const kase = useCase(projectId, caseId);
  const runs = useCaseRuns(projectId, caseId);
  const targets = useTargets(projectId);
  const { update, remove, run } = useCaseMutations(projectId);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmRun, setConfirmRun] = useState(false);
  const [targetId, setTargetId] = useState("");
  const [shownId, setShownId] = useState<string | null>(null);
  const base = `/projects/${projectId}`;

  if (kase.isPending) return <Spinner />;
  if (kase.isError) return <ErrorState error={kase.error} retry={() => kase.refetch()} />;
  const c = kase.data;
  const enabled = targets.data?.filter((t) => t.enabled) ?? [];
  const selectedTarget = enabled.find((t) => t.id === targetId) ?? enabled[0];
  const shown = runs.data?.find((r) => r.id === shownId) ?? runs.data?.[0];
  const mutating = isMutating(c.request_definition.method);

  const doRun = () =>
    selectedTarget &&
    run.mutate(
      { caseId: c.id, targetId: selectedTarget.id, confirm: mutating },
      {
        onSuccess: (e) => {
          setConfirmRun(false);
          setShownId(e.id);
        },
      },
    );

  if (editing) {
    return (
      <>
        <PageHeader title={`Edit “${c.name}”`} />
        <CaseForm
          initial={{
            name: c.name,
            description: c.description ?? "",
            request: c.request_definition,
            assertions: c.assertion_definition,
          }}
          submitLabel="Save changes"
          pending={update.isPending}
          error={update.error}
          onCancel={() => setEditing(false)}
          onSubmit={(v) => update.mutate({ caseId: c.id, patch: v }, { onSuccess: () => setEditing(false) })}
        />
      </>
    );
  }

  const q = queryToString(c.request_definition.query);

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link to={`${base}/cases`} className="inline-flex items-center gap-0.5 hover:text-ink">
            <ChevronLeft className="size-3.5" aria-hidden /> Regression cases
          </Link>
        }
        title={
          <span className="flex flex-wrap items-center gap-2">
            {c.name}
            <StatusBadge status={c.last_run ? (c.last_run.outcome ?? c.last_run.status) : null} />
          </span>
        }
        description={c.description ?? undefined}
        actions={
          <>
            <Button icon={Pencil} onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button icon={Trash2} variant="ghost" onClick={() => setConfirmDelete(true)}>
              Delete
            </Button>
          </>
        }
      />

      <Panel title="Run this case" className="mb-6">
        {targets.isPending ? (
          <Spinner />
        ) : enabled.length === 0 ? (
          <EmptyState title="No enabled replay targets" action={<ButtonLink to={`${base}/settings#targets`}>Add a target</ButtonLink>} />
        ) : (
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex min-w-64 flex-1 flex-col gap-1 text-[13px] font-medium">
              Target
              <Select value={selectedTarget?.id ?? ""} onChange={(e) => setTargetId(e.target.value)}>
                {enabled.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.environment}) — {t.base_url}
                  </option>
                ))}
              </Select>
            </label>
            <Button
              variant="primary"
              icon={Play}
              loading={run.isPending && !confirmRun}
              onClick={() => (mutating ? setConfirmRun(true) : doRun())}
            >
              Run case
            </Button>
          </div>
        )}
        {!confirmRun && <div className="mt-2"><InlineError error={run.error} /></div>}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-6">
          <Panel title={shown ? "Latest result" : "Result"}>
            {runs.isPending ? (
              <Spinner />
            ) : shown ? (
              <RunResult run={shown} />
            ) : (
              <EmptyState icon={Play} title="Never run">
                Run the case against a target to check it against its expectations.
              </EmptyState>
            )}
          </Panel>
          <Panel title="Definition">
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <MethodTag method={c.request_definition.method} />
                <span className="font-mono text-[13px] break-all">
                  {c.request_definition.path}
                  {q && `?${q}`}
                </span>
              </div>
              {c.request_definition.body !== null && <CodeBlock value={c.request_definition.body} title="Body" maxHeight="12rem" />}
              <div>
                <h3 className="mb-1 text-[13px] font-semibold">Expectations</h3>
                <ul className="list-inside list-disc space-y-0.5 font-mono text-[12.5px]">
                  <li>status is {c.assertion_definition.expected_status}</li>
                  {c.assertion_definition.assertions.map((a, i) => (
                    <li key={i}>{describeAssertion(a)}</li>
                  ))}
                </ul>
              </div>
              {c.incident_id && (
                <Link to={`${base}/incidents/${c.incident_id}`} className="inline-block text-[13px] text-accent-strong hover:underline">
                  View the original incident
                </Link>
              )}
            </div>
          </Panel>
        </div>

        <Panel title="Run history" bodyClassName="p-0" className="self-start">
          {runs.data?.length ? (
            <ol>
              {runs.data.map((r) => (
                <li key={r.id} className="border-b border-line last:border-0">
                  <button
                    type="button"
                    aria-current={r.id === shown?.id || undefined}
                    onClick={() => setShownId(r.id)}
                    className={cx("flex w-full items-center gap-2 px-4 py-2 text-left text-[13px]", r.id === shown?.id ? "bg-accent-wash" : "hover:bg-sunken")}
                  >
                    <StatusBadge status={r.outcome ?? r.status} />
                    <span className="flex-1 text-ink-2" title={formatDateTime(r.started_at)}>
                      {formatRelative(r.started_at)}
                    </span>
                    <HttpStatus status={r.response_summary?.status ?? null} />
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <p className="px-4 py-3 text-[13px] text-ink-3">No runs yet.</p>
          )}
        </Panel>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this regression case?"
        description="The case and its run history are removed. The original incident and events are kept."
        confirmLabel="Delete case"
        danger
        loading={remove.isPending}
        onConfirm={() => remove.mutate(c.id, { onSuccess: () => navigate(`${base}/cases`, { replace: true }) })}
      >
        <InlineError error={remove.error} />
      </ConfirmDialog>

      <ConfirmDialog
        open={confirmRun}
        onOpenChange={setConfirmRun}
        title={`Run a ${c.request_definition.method} request?`}
        description={
          <>
            This case sends a {c.request_definition.method} request to <strong>{selectedTarget?.name}</strong>, which may
            create, change or delete data there.
          </>
        }
        confirmLabel="Run case"
        danger
        loading={run.isPending}
        onConfirm={doRun}
      >
        <InlineError error={run.error} />
      </ConfirmDialog>
    </>
  );
}
