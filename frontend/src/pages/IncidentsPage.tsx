import { Bug, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { useIncidents } from "../api/queries";
import type { IncidentFilters, IncidentStatus } from "../api/types";
import {
  Button,
  cx,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  Pagination,
  Panel,
  Select,
  Spinner,
  StatusBadge,
  Table,
  td,
  th,
} from "../components/ui";
import { formatCount, formatDateTime, formatRelative } from "../lib/format";

const PAGE_SIZE = 20;

function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export function IncidentsPage() {
  const { projectId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const debouncedSearch = useDebounced(search);

  const status = (params.get("status") as IncidentStatus | null) ?? undefined;
  const errorType = params.get("error_type") ?? undefined;
  const sinceDays = Number(params.get("since_days")) || undefined;
  const page = Math.max(1, Number(params.get("page")) || 1);

  const update = (patch: Record<string, string | undefined>, resetPage = true) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) v ? next.set(k, v) : next.delete(k);
    if (resetPage) next.delete("page");
    setParams(next, { replace: true });
  };

  useEffect(() => {
    if ((params.get("q") ?? "") !== debouncedSearch) update({ q: debouncedSearch || undefined });
  }, [debouncedSearch]);

  const filters: IncidentFilters = {
    status,
    error_type: errorType,
    q: params.get("q") || undefined,
    since_days: sinceDays,
    page,
    page_size: PAGE_SIZE,
  };
  const incidents = useIncidents(projectId, filters);
  const filtered = Boolean(status || errorType || filters.q || sinceDays);
  const base = `/projects/${projectId}`;

  return (
    <>
      <PageHeader title="Incidents" description="Failures grouped by a stable fingerprint of error type and stack location." />

      {/* One filter row above everything it scopes. */}
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <div className="relative min-w-60 flex-1">
          <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-ink-3" aria-hidden />
          <Input
            type="search"
            aria-label="Search incidents by message or endpoint"
            placeholder="Search message or endpoint…"
            className="pl-8"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select
          aria-label="Status"
          className="w-36"
          value={status ?? ""}
          onChange={(e) => update({ status: e.target.value || undefined })}
        >
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
        </Select>
        <Select
          aria-label="Last seen"
          className="w-40"
          value={sinceDays ?? ""}
          onChange={(e) => update({ since_days: e.target.value || undefined })}
        >
          <option value="">Any time</option>
          <option value="1">Last 24 hours</option>
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
        </Select>
        {errorType && (
          <span className="inline-flex h-9 items-center gap-1 rounded-md border border-accent bg-accent-wash pr-1 pl-2.5 text-[13px] text-accent-strong">
            Type: <span className="font-mono">{errorType}</span>
            <button
              type="button"
              className="rounded p-1 hover:bg-surface"
              aria-label={`Remove error type filter ${errorType}`}
              onClick={() => update({ error_type: undefined })}
            >
              <X className="size-3.5" aria-hidden />
            </button>
          </span>
        )}
      </div>

      <Panel bodyClassName="p-0">
        {incidents.isPending ? (
          <Spinner label="Loading incidents…" />
        ) : incidents.isError ? (
          <ErrorState error={incidents.error} retry={() => incidents.refetch()} />
        ) : incidents.data.total === 0 ? (
          filtered ? (
            <EmptyState
              icon={Search}
              title="No incidents match these filters"
              action={
                <Button
                  size="sm"
                  onClick={() => {
                    setSearch("");
                    setParams({}, { replace: true });
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState icon={Bug} title="No incidents captured yet">
              Once the SDK sends its first failure, it appears here. Set up the SDK from the{" "}
              <Link to={base} className="text-accent-strong hover:underline">
                project dashboard
              </Link>
              .
            </EmptyState>
          )
        ) : (
          <div className={cx("transition-opacity", incidents.isPlaceholderData && "opacity-60")} aria-busy={incidents.isFetching}>
            <Table label="Incidents">
              <thead className="border-b border-line bg-sunken">
                <tr>
                  <th className={th} scope="col">
                    Error
                  </th>
                  <th className={th} scope="col">
                    Endpoint
                  </th>
                  <th className={th} scope="col">
                    Status
                  </th>
                  <th className={cx(th, "text-right")} scope="col">
                    Events
                  </th>
                  <th className={th} scope="col">
                    First seen
                  </th>
                  <th className={th} scope="col">
                    Last seen
                  </th>
                </tr>
              </thead>
              <tbody>
                {incidents.data.items.map((i) => (
                  <tr key={i.id} className="border-b border-line last:border-0 hover:bg-sunken">
                    <td className={cx(td, "max-w-md")}>
                      <Link to={`${base}/incidents/${i.id}`} className="font-medium hover:underline">
                        {i.error_type}
                      </Link>
                      <div className="truncate text-[13px] text-ink-2" title={i.error_message}>
                        {i.error_message}
                      </div>
                      {i.error_type !== errorType && (
                        <button
                          type="button"
                          className="mt-0.5 text-xs text-ink-3 hover:text-accent-strong hover:underline"
                          onClick={() => update({ error_type: i.error_type })}
                        >
                          Filter by this type
                        </button>
                      )}
                    </td>
                    <td className={cx(td, "font-mono text-[12.5px] whitespace-nowrap")}>{i.normalized_route ?? "—"}</td>
                    <td className={td}>
                      <StatusBadge status={i.status} />
                    </td>
                    <td className={cx(td, "text-right font-medium tabular")}>{formatCount(i.occurrence_count)}</td>
                    <td className={cx(td, "whitespace-nowrap text-ink-2")} title={formatDateTime(i.first_seen_at)}>
                      {formatRelative(i.first_seen_at)}
                    </td>
                    <td className={cx(td, "whitespace-nowrap text-ink-2")} title={formatDateTime(i.last_seen_at)}>
                      {formatRelative(i.last_seen_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <div className="border-t border-line px-3 py-2">
              <Pagination
                page={incidents.data.page}
                pageSize={incidents.data.page_size}
                total={incidents.data.total}
                onPage={(p) => update({ page: p > 1 ? String(p) : undefined }, false)}
              />
            </div>
          </div>
        )}
      </Panel>
    </>
  );
}
