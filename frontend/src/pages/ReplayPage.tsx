import { AlertTriangle, ChevronLeft, FlaskConical, Send, Server } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import { useCreateReplay, useEvent, useReplayHistory, useTargets } from "../api/queries";
import type { ReplayExecution, ReplayTarget, RequestDefinition } from "../api/types";
import { CodeBlock } from "../components/Code";
import { ConfirmDialog } from "../components/Dialog";
import { ResponseComparison } from "../components/DiffView";
import {
  draftFromRequest,
  RequestEditor,
  requestFromDraft,
  type DraftErrors,
  type RequestDraft,
} from "../components/RequestEditor";
import {
  Badge,
  Button,
  ButtonLink,
  cx,
  EmptyState,
  ErrorState,
  Field,
  HttpStatus,
  InlineError,
  MethodTag,
  PageHeader,
  Panel,
  Select,
  Spinner,
  StatusBadge,
} from "../components/ui";
import { formatDuration, formatRelative } from "../lib/format";
import { isMutating, queryToString, requestFromEvent } from "../lib/request";

export interface CaseDraftState {
  request: RequestDefinition;
  expectedStatus: number | null;
}

function fullUrl(target: ReplayTarget | undefined, req: RequestDefinition): string {
  const q = queryToString(req.query);
  return `${target?.base_url.replace(/\/$/, "") ?? ""}${req.path}${q ? `?${q}` : ""}`;
}

function ExecutionResult({ execution, original }: { execution: ReplayExecution; original: Parameters<typeof ResponseComparison>[0]["original"] }) {
  if (execution.status === "error" || !execution.response_summary) {
    return (
      <div role="alert" className="flex gap-2 rounded-md bg-warning-wash px-3 py-2 text-[13px] text-warning-ink">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>The replay did not complete: {execution.error_summary ?? "unknown error"}</span>
      </div>
    );
  }
  const r = execution.response_summary;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3 text-[13px]">
        <HttpStatus status={r.status} />
        <span className="text-ink-2">{formatDuration(execution.duration_ms)}</span>
        <span className="min-w-0 truncate font-mono text-xs text-ink-3">
          {execution.request_summary.method} {execution.request_summary.url}
        </span>
      </div>
      <section>
        <h3 className="mb-2 text-[13px] font-semibold">Compared with the original</h3>
        <ResponseComparison original={original} replayed={r} />
      </section>
      <CodeBlock value={r.body} title={r.body_truncated ? "Replayed response body · truncated" : "Replayed response body"} maxHeight="18rem" />
    </div>
  );
}

export function ReplayPage() {
  const { projectId = "" } = useParams();
  const [params] = useSearchParams();
  const eventId = params.get("event");
  const navigate = useNavigate();
  const event = useEvent(projectId, eventId);
  const targets = useTargets(projectId);
  const history = useReplayHistory(projectId, eventId);
  const replay = useCreateReplay(projectId);

  const [draft, setDraft] = useState<RequestDraft | null>(null);
  const [errors, setErrors] = useState<DraftErrors>({});
  const [targetId, setTargetId] = useState("");
  const [confirming, setConfirming] = useState<RequestDefinition | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [shownId, setShownId] = useState<string | null>(null);

  useEffect(() => {
    if (event.data && !draft) setDraft(draftFromRequest(requestFromEvent(event.data)));
  }, [event.data, draft]);

  const enabledTargets = useMemo(() => targets.data?.filter((t) => t.enabled) ?? [], [targets.data]);
  useEffect(() => {
    if (!targetId && enabledTargets[0]) setTargetId(enabledTargets[0].id);
  }, [enabledTargets, targetId]);

  const base = `/projects/${projectId}`;
  if (!eventId) {
    return (
      <Panel>
        <EmptyState title="Pick a captured request to replay" action={<ButtonLink to={`${base}/incidents`}>Browse incidents</ButtonLink>}>
          Open an incident and choose “Replay this request”.
        </EmptyState>
      </Panel>
    );
  }
  if (event.isPending || targets.isPending) return <Spinner />;
  if (event.isError) return <ErrorState error={event.error} retry={() => event.refetch()} />;
  if (targets.isError) return <ErrorState error={targets.error} retry={() => targets.refetch()} />;

  const ev = event.data;
  const target = enabledTargets.find((t) => t.id === targetId);
  const shown = history.data?.find((h) => h.id === shownId) ?? (shownId === null ? history.data?.[0] : undefined);
  const original = {
    status: ev.response_status,
    headers: ev.request_data?.response_headers ?? null,
    body: ev.request_data?.response_body,
  };

  function review() {
    if (!draft) return;
    const { request, errors } = requestFromDraft(draft);
    setErrors(errors);
    if (!request || !target) return;
    setAcknowledged(false);
    replay.reset();
    setConfirming(request);
  }

  function send() {
    if (!confirming || !target) return;
    replay.mutate(
      { target_id: target.id, event_id: ev.id, request: confirming, confirm_mutation: isMutating(confirming.method) && acknowledged },
      {
        onSuccess: (execution) => {
          setConfirming(null);
          setShownId(execution.id);
        },
      },
    );
  }

  function saveAsCase() {
    if (!draft) return;
    const { request, errors } = requestFromDraft(draft);
    setErrors(errors);
    if (!request) return;
    const state: CaseDraftState = { request, expectedStatus: null };
    navigate(`${base}/cases/new?event=${ev.id}${ev.incident_id ? `&incident=${ev.incident_id}` : ""}`, { state });
  }

  const mutating = confirming ? isMutating(confirming.method) : false;

  return (
    <>
      <PageHeader
        breadcrumb={
          ev.incident_id ? (
            <Link to={`${base}/incidents/${ev.incident_id}?event=${ev.id}`} className="inline-flex items-center gap-0.5 hover:text-ink">
              <ChevronLeft className="size-3.5" aria-hidden /> Back to incident
            </Link>
          ) : undefined
        }
        title="Replay workspace"
        description={
          <>
            Reproduce the captured <span className="font-mono text-[13px]">{ev.request_method} {ev.normalized_route}</span> request
            against an approved target, then compare.
          </>
        }
        actions={
          <Button icon={FlaskConical} onClick={saveAsCase}>
            Save as regression case
          </Button>
        }
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="min-w-0 space-y-6">
          <Panel title="Target">
            {enabledTargets.length === 0 ? (
              <EmptyState
                icon={Server}
                title="No replay targets"
                action={<ButtonLink to={`${base}/settings#targets`}>Add a target</ButtonLink>}
              >
                Requests can only be replayed against local or staging environments you register. Production is never allowed.
              </EmptyState>
            ) : (
              <div className="space-y-3">
                <Field label="Send to" hint="Only registered, enabled targets are available. The server validates the destination again.">
                  {(p) => (
                    <Select {...p} value={targetId} onChange={(e) => setTargetId(e.target.value)}>
                      {enabledTargets.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name} ({t.environment}) — {t.base_url}
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
                {target && (
                  <p className="flex items-center gap-2 text-[13px] text-ink-2">
                    <Badge tone="accent">{target.environment}</Badge>
                    <span className="font-mono text-xs break-all">
                      {target.base_url}
                      {draft?.path}
                      {draft?.queryText ? `?${draft.queryText.replace(/^\?/, "")}` : ""}
                    </span>
                  </p>
                )}
              </div>
            )}
          </Panel>

          <Panel
            title="Request"
            actions={
              <Button variant="primary" icon={Send} disabled={!target || !draft} onClick={review}>
                Review & send
              </Button>
            }
          >
            {draft && <RequestEditor draft={draft} onChange={setDraft} errors={errors} />}
          </Panel>
        </div>

        <div className="min-w-0 space-y-6">
          <Panel title="Result">
            {shown ? (
              <ExecutionResult execution={shown} original={original} />
            ) : (
              <EmptyState icon={Send} title="Nothing replayed yet">
                Review the request, choose a target and send it. The response is compared with the original failure.
              </EmptyState>
            )}
          </Panel>

          <Panel title="Replay history" bodyClassName="p-0">
            {history.isPending ? (
              <Spinner />
            ) : !history.data?.length ? (
              <p className="px-4 py-3 text-[13px] text-ink-3">No previous replays of this request.</p>
            ) : (
              <ol>
                {history.data.map((h) => (
                  <li key={h.id} className="border-b border-line last:border-0">
                    <button
                      type="button"
                      aria-current={h.id === shown?.id || undefined}
                      onClick={() => setShownId(h.id)}
                      className={cx(
                        "flex w-full items-center gap-3 px-4 py-2 text-left text-[13px]",
                        h.id === shown?.id ? "bg-accent-wash" : "hover:bg-sunken",
                      )}
                    >
                      <MethodTag method={h.request_summary.method} />
                      <span className="min-w-0 flex-1 truncate font-mono text-xs">{h.request_summary.url}</span>
                      {h.status === "error" ? <StatusBadge status="error" /> : <HttpStatus status={h.response_summary?.status ?? null} />}
                      <span className="text-xs whitespace-nowrap text-ink-3">{formatRelative(h.started_at)}</span>
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </div>
      </div>

      <ConfirmDialog
        open={confirming !== null}
        onOpenChange={(open) => !open && setConfirming(null)}
        title={mutating ? "Send a request that may change data?" : "Send this replay?"}
        description={
          <>
            Traceback will send this request to <strong>{target?.name}</strong> ({target?.environment}).
          </>
        }
        confirmLabel="Send replay"
        danger={mutating}
        loading={replay.isPending}
        confirmDisabled={mutating && !acknowledged}
        onConfirm={send}
      >
        {confirming && (
          <div className="rounded-md border border-line bg-sunken px-3 py-2 font-mono text-[12.5px] break-all">
            {confirming.method} {fullUrl(target, confirming)}
          </div>
        )}
        {mutating && (
          <label className="flex items-start gap-2 rounded-md bg-critical-wash px-3 py-2 text-[13px] text-critical-ink">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
            />
            <span>
              I understand this {confirming?.method} request may create, change or delete data on {target?.name}.
            </span>
          </label>
        )}
        {mutating && !acknowledged && <p className="text-xs text-ink-3">Tick the box to enable sending.</p>}
        <InlineError error={replay.error instanceof ApiError ? replay.error : null} />
      </ConfirmDialog>
    </>
  );
}
