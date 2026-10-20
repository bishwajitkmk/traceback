import type { ReactNode } from "react";
import type { TracebackEvent } from "../api/types";
import { formatDateTime, formatDuration } from "../lib/format";
import { CodeBlock, CopyButton, KeyValueTable, NotCaptured } from "./Code";
import { HttpStatus, MethodTag } from "./ui";

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="mt-0.5 truncate text-sm">{children}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-[13px] font-semibold">{title}</h3>
      {children}
    </section>
  );
}

/** Structured view of one captured request (PRD §6.5). */
export function RequestView({ event }: { event: TracebackEvent }) {
  const data = event.request_data;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <MethodTag method={event.request_method} />
        <span className="font-mono text-[13px] break-all">{data?.path ?? event.normalized_route ?? "—"}</span>
        <HttpStatus status={event.response_status} />
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
        <Meta label="Route">
          <span className="font-mono text-[12.5px]">{event.normalized_route ?? "—"}</span>
        </Meta>
        <Meta label="Correlation ID">
          {event.correlation_id ? (
            <span className="inline-flex items-center gap-1">
              <span className="font-mono text-[12.5px]">{event.correlation_id}</span>
              <CopyButton text={event.correlation_id} label="" />
            </span>
          ) : (
            <NotCaptured />
          )}
        </Meta>
        <Meta label="Occurred">{formatDateTime(event.occurred_at)}</Meta>
        <Meta label="Duration">{formatDuration(event.duration_ms)}</Meta>
        <Meta label="Environment">{event.environment ?? <NotCaptured />}</Meta>
        <Meta label="Release">{event.release ?? <NotCaptured />}</Meta>
      </dl>

      {!data ? (
        <p className="text-[13px] text-ink-3">No request data was captured for this event.</p>
      ) : (
        <>
          <Section title="Query parameters">
            <KeyValueTable data={data.query} label="Query parameters" empty="No query parameters." />
          </Section>
          <Section title="Request headers">
            <KeyValueTable data={data.headers} label="Request headers" />
          </Section>
          <Section title="Request body">
            {!data.body_captured ? (
              <NotCaptured>Body capture is disabled for this route</NotCaptured>
            ) : data.body === null || data.body === undefined ? (
              <p className="text-[13px] text-ink-3">Empty body.</p>
            ) : (
              <CodeBlock value={data.body} title={data.body_truncated ? "JSON · truncated at capture" : "JSON"} maxHeight="18rem" />
            )}
          </Section>
          <Section title="Response">
            <div className="space-y-2">
              <KeyValueTable data={data.response_headers} label="Response headers" />
              {data.response_body === null || data.response_body === undefined ? (
                <NotCaptured>Response body not captured</NotCaptured>
              ) : (
                <CodeBlock value={data.response_body} title="Response body" maxHeight="12rem" />
              )}
            </div>
          </Section>
        </>
      )}
    </div>
  );
}
