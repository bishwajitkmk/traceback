import { ArrowRight, Bug, CheckCircle2, Circle, FlaskConical } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router";
import { useProject, useStats, useTargets } from "../api/queries";
import type { Project, ProjectStats } from "../api/types";
import { ApiKeyManager, installSnippet } from "../components/ApiKey";
import { CodeBlock } from "../components/Code";
import { TrendChart } from "../components/TrendChart";
import {
  ButtonLink,
  cx,
  EmptyState,
  ErrorState,
  MethodTag,
  PageHeader,
  Panel,
  Spinner,
  StatusBadge,
  td,
  th,
} from "../components/ui";
import { formatCount, formatRelative } from "../lib/format";

const RANGES = [7, 14, 30] as const;

function RangePicker({ days, onChange }: { days: number; onChange: (d: number) => void }) {
  return (
    <div role="radiogroup" aria-label="Date range" className="inline-flex rounded-md border border-line-strong bg-surface p-0.5">
      {RANGES.map((d) => (
        <button
          key={d}
          type="button"
          role="radio"
          aria-checked={days === d}
          onClick={() => onChange(d)}
          className={cx(
            "rounded px-2.5 py-1 text-[13px]",
            days === d ? "bg-ink font-medium text-white" : "text-ink-2 hover:bg-sunken",
          )}
        >
          Last {d} days
        </button>
      ))}
    </div>
  );
}

function StatTile({ label, value, detail, to }: { label: string; value: string; detail?: string; to?: string }) {
  const body = (
    <>
      <div className="text-[13px] text-ink-2">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
      {detail && <div className="mt-0.5 text-xs text-ink-3">{detail}</div>}
    </>
  );
  const cls = "block rounded-lg border border-line bg-surface p-4";
  return to ? (
    <Link to={to} className={cx(cls, "hover:border-line-strong")}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

function SetupChecklist({ project, hasEvents, hasTargets }: { project: Project; hasEvents: boolean; hasTargets: boolean }) {
  const steps = [
    { done: Boolean(project.api_key), title: "Generate an ingestion key" },
    { done: hasEvents, title: "Install the SDK and send your first failure" },
    { done: hasTargets, title: "Register a local or staging replay target" },
  ];
  return (
    <Panel title="Set up this project" className="mb-6">
      <ol className="mb-5 space-y-2">
        {steps.map((s) => (
          <li key={s.title} className="flex items-center gap-2 text-sm">
            {s.done ? (
              <CheckCircle2 className="size-4 text-good" aria-label="Done" />
            ) : (
              <Circle className="size-4 text-ink-3" aria-label="To do" />
            )}
            <span className={s.done ? "text-ink-3 line-through" : undefined}>{s.title}</span>
          </li>
        ))}
      </ol>
      <div className="space-y-4">
        <ApiKeyManager project={project} />
        <CodeBlock title="main.py" value={installSnippet(project.api_key ? `starts with ${project.api_key.key_prefix}` : "generate a key above")} />
        <p className="text-[13px] text-ink-2">
          Then trigger an error in your app. It appears here within seconds.{" "}
          {!hasTargets && (
            <Link to={`/projects/${project.id}/settings#targets`} className="font-medium text-accent-strong hover:underline">
              Add a replay target
            </Link>
          )}
        </p>
      </div>
    </Panel>
  );
}

function Overview({ projectId, stats }: { projectId: string; stats: ProjectStats }) {
  const base = `/projects/${projectId}`;
  const reg = stats.regression;
  return (
    <>
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Open incidents" value={formatCount(stats.open_incidents)} to={`${base}/incidents?status=open`} />
        <StatTile label="Events captured" value={formatCount(stats.events_in_range)} detail={`Last ${stats.days} days`} />
        <StatTile label="New incidents" value={formatCount(stats.new_incidents_in_range)} detail={`First seen in last ${stats.days} days`} />
        <StatTile
          label="Regression cases passing"
          value={reg.total ? `${reg.passing} / ${reg.total}` : "—"}
          detail={reg.total ? `${reg.failing} failing · ${reg.never_run} never run` : "No cases yet"}
          to={`${base}/cases`}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <Panel title="Events per day">
          <TrendChart data={stats.daily} label={`Captured events per day, last ${stats.days} days`} />
        </Panel>

        <Panel title="Most frequent errors" bodyClassName="p-0" actions={<span className="text-xs text-ink-3">events in range</span>}>
          {stats.top_incidents.length === 0 ? (
            <EmptyState title="No errors in this range" />
          ) : (
            <ol>
              {stats.top_incidents.map(({ incident, events }) => (
                <li key={incident.id} className="border-b border-line last:border-0">
                  <Link to={`${base}/incidents/${incident.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-sunken">
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{incident.error_type}</div>
                      <div className="truncate font-mono text-xs text-ink-3">{incident.normalized_route ?? "—"}</div>
                    </div>
                    <span className="text-sm font-semibold tabular">{formatCount(events)}</span>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </Panel>

        <Panel
          title="Recent incident activity"
          bodyClassName="p-0"
          actions={
            <Link to={`${base}/incidents`} className="text-[13px] text-accent-strong hover:underline">
              All incidents
            </Link>
          }
        >
          {stats.recent_incidents.length === 0 ? (
            <EmptyState icon={Bug} title="No incidents yet" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" aria-label="Recent incidents">
                <thead className="border-b border-line">
                  <tr>
                    <th className={th}>Incident</th>
                    <th className={th}>Status</th>
                    <th className={cx(th, "text-right")}>Last seen</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.recent_incidents.map((i) => (
                    <tr key={i.id} className="border-b border-line last:border-0 hover:bg-sunken">
                      <td className={td}>
                        <Link to={`${base}/incidents/${i.id}`} className="font-medium hover:underline">
                          {i.error_type}
                        </Link>
                        <div className="truncate text-xs text-ink-3">{i.error_message}</div>
                      </td>
                      <td className={td}>
                        <StatusBadge status={i.status} />
                      </td>
                      <td className={cx(td, "text-right whitespace-nowrap text-ink-2")}>{formatRelative(i.last_seen_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel
          title="Recent regression runs"
          bodyClassName="p-0"
          actions={
            <Link to={`${base}/cases`} className="text-[13px] text-accent-strong hover:underline">
              All cases
            </Link>
          }
        >
          {stats.recent_runs.length === 0 ? (
            <EmptyState icon={FlaskConical} title="No runs yet">
              Save a replayed request as a regression case, then run it after a fix.
            </EmptyState>
          ) : (
            <ul>
              {stats.recent_runs.map(({ execution, case_id, case_name }) => (
                <li key={execution.id} className="border-b border-line last:border-0">
                  <Link to={`${base}/cases/${case_id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-sunken">
                    <MethodTag method={execution.request_summary.method} />
                    <span className="min-w-0 flex-1 truncate">{case_name}</span>
                    <StatusBadge status={execution.outcome ?? execution.status} />
                    <span className="hidden text-xs whitespace-nowrap text-ink-3 sm:inline">{formatRelative(execution.started_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}

export function DashboardPage() {
  const { projectId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const days = RANGES.includes(Number(params.get("days")) as 7) ? Number(params.get("days")) : 14;
  const project = useProject(projectId);
  const stats = useStats(projectId, days);
  const targets = useTargets(projectId);

  if (project.isPending) return <Spinner />;
  if (project.isError) return <ErrorState error={project.error} retry={() => project.refetch()} />;

  const hasEvents = (stats.data?.events_in_range ?? 0) > 0 || (stats.data?.recent_incidents.length ?? 0) > 0;
  const hasTargets = (targets.data?.length ?? 0) > 0;
  const needsSetup = stats.isSuccess && targets.isSuccess && (!project.data.api_key || !hasEvents || !hasTargets);

  return (
    <>
      <PageHeader
        title={project.data.name}
        description="Failures captured from your API, and the cases that prove they stay fixed."
        actions={
          <>
            <RangePicker days={days} onChange={(d) => setParams({ days: String(d) }, { replace: true })} />
            <ButtonLink to={`/projects/${projectId}/incidents`} variant="primary">
              Investigate incidents <ArrowRight className="size-4" aria-hidden />
            </ButtonLink>
          </>
        }
      />
      {needsSetup && <SetupChecklist project={project.data} hasEvents={hasEvents} hasTargets={hasTargets} />}
      {stats.isPending ? (
        <Spinner label="Loading statistics…" />
      ) : stats.isError ? (
        <ErrorState error={stats.error} retry={() => stats.refetch()} />
      ) : (
        // Refetch keeps the frame: previous numbers stay visible at reduced opacity.
        <div className={cx("transition-opacity", stats.isPlaceholderData && "opacity-60")} aria-busy={stats.isFetching}>
          <Overview projectId={projectId} stats={stats.data} />
        </div>
      )}
    </>
  );
}
