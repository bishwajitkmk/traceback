import { CheckCircle2, ChevronLeft, FlaskConical, RotateCcw, Undo2 } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router";
import { useIncident, useIncidentEvents, useSetIncidentStatus } from "../api/queries";
import { RequestView } from "../components/RequestView";
import { StackTrace } from "../components/StackTrace";
import {
  Button,
  ButtonLink,
  cx,
  EmptyState,
  ErrorState,
  HttpStatus,
  InlineError,
  PageHeader,
  Pagination,
  Panel,
  Spinner,
  StatusBadge,
} from "../components/ui";
import { formatCount, formatDateTime, formatRelative } from "../lib/format";

export function IncidentDetailPage() {
  const { projectId = "", incidentId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const incident = useIncident(projectId, incidentId);
  const events = useIncidentEvents(projectId, incidentId, page);
  const setStatus = useSetIncidentStatus(projectId, incidentId);
  const base = `/projects/${projectId}`;

  if (incident.isPending) return <Spinner />;
  if (incident.isError) return <ErrorState error={incident.error} retry={() => incident.refetch()} />;
  const i = incident.data;

  const selectedId = params.get("event") ?? events.data?.items[0]?.id;
  const selected = events.data?.items.find((e) => e.id === selectedId) ?? events.data?.items[0];
  const select = (patch: Record<string, string>) => setParams({ ...Object.fromEntries(params), ...patch }, { replace: true });

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link to={`${base}/incidents`} className="inline-flex items-center gap-0.5 hover:text-ink">
            <ChevronLeft className="size-3.5" aria-hidden /> Incidents
          </Link>
        }
        title={
          <span className="flex flex-wrap items-center gap-2">
            {i.error_type}
            <StatusBadge status={i.status} />
          </span>
        }
        description={<span className="font-mono text-[13px]">{i.error_message}</span>}
        actions={
          <>
            {i.status === "open" ? (
              <Button icon={CheckCircle2} loading={setStatus.isPending} onClick={() => setStatus.mutate("resolved")}>
                Mark resolved
              </Button>
            ) : (
              <Button icon={Undo2} loading={setStatus.isPending} onClick={() => setStatus.mutate("open")}>
                Reopen
              </Button>
            )}
            {selected && (
              <ButtonLink variant="primary" to={`${base}/replay?event=${selected.id}`}>
                <RotateCcw className="size-4" aria-hidden />
                Replay this request
              </ButtonLink>
            )}
          </>
        }
      />
      <InlineError error={setStatus.error} />

      <dl className="mb-6 grid grid-cols-2 gap-3 rounded-lg border border-line bg-surface p-4 sm:grid-cols-4">
        <div>
          <dt className="text-xs text-ink-3">Endpoint</dt>
          <dd className="mt-0.5 font-mono text-[13px]">{i.normalized_route ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-3">Occurrences</dt>
          <dd className="mt-0.5 font-semibold">{formatCount(i.occurrence_count)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-3">First seen</dt>
          <dd className="mt-0.5" title={formatDateTime(i.first_seen_at)}>
            {formatRelative(i.first_seen_at)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-3">Last seen</dt>
          <dd className="mt-0.5" title={formatDateTime(i.last_seen_at)}>
            {formatRelative(i.last_seen_at)}
          </dd>
        </div>
        {i.status === "resolved" && i.resolved_at && (
          <p className="col-span-full text-[13px] text-ink-2">
            Resolved {formatRelative(i.resolved_at)}. Event history is kept; a new occurrence will show here.
          </p>
        )}
      </dl>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-6">
          {events.isPending ? (
            <Spinner label="Loading events…" />
          ) : events.isError ? (
            <ErrorState error={events.error} retry={() => events.refetch()} />
          ) : !selected ? (
            <Panel>
              <EmptyState title="No events stored for this incident">They may have expired under the retention policy.</EmptyState>
            </Panel>
          ) : (
            <>
              {selected.exception_data ? (
                <Panel title="Stack trace">
                  <StackTrace exception={selected.exception_data} />
                </Panel>
              ) : (
                <Panel title="Failure">
                  <p className="text-[13px] text-ink-2">
                    This event is an HTTP error response without a Python exception, so there is no stack trace.
                  </p>
                </Panel>
              )}
              <Panel
                title="Request"
                actions={
                  <ButtonLink size="sm" to={`${base}/cases/new?event=${selected.id}`}>
                    <FlaskConical className="size-3.5" aria-hidden />
                    Save as regression case
                  </ButtonLink>
                }
              >
                <RequestView event={selected} />
              </Panel>
            </>
          )}
        </div>

        <Panel title="Event timeline" bodyClassName="p-0" className="self-start">
          {events.data && (
            <>
              <ol aria-label="Events, newest first">
                {events.data.items.map((e) => {
                  const active = e.id === selected?.id;
                  return (
                    <li key={e.id} className="border-b border-line last:border-0">
                      <button
                        type="button"
                        aria-current={active || undefined}
                        onClick={() => select({ event: e.id })}
                        className={cx(
                          "flex w-full items-center gap-2 px-4 py-2 text-left text-[13px]",
                          active ? "bg-accent-wash" : "hover:bg-sunken",
                        )}
                      >
                        <span className={cx("size-1.5 shrink-0 rounded-full", active ? "bg-accent" : "bg-line-strong")} aria-hidden />
                        <span className="flex-1">
                          <span className="block" title={formatDateTime(e.occurred_at)}>
                            {formatRelative(e.occurred_at)}
                          </span>
                          <span className="block font-mono text-[11px] text-ink-3">{e.correlation_id ?? "no correlation id"}</span>
                        </span>
                        <HttpStatus status={e.response_status} />
                      </button>
                    </li>
                  );
                })}
              </ol>
              {events.data.total > events.data.page_size && (
                <div className="border-t border-line px-3 py-2">
                  <Pagination
                    page={events.data.page}
                    pageSize={events.data.page_size}
                    total={events.data.total}
                    onPage={(p) => {
                      const next = new URLSearchParams(params);
                      next.set("page", String(p));
                      next.delete("event");
                      setParams(next, { replace: true });
                    }}
                  />
                </div>
              )}
            </>
          )}
        </Panel>
      </div>
    </>
  );
}
