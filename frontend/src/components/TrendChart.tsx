import { useLayoutEffect, useRef, useState } from "react";
import type { DailyCount } from "../api/types";
import { formatCount, formatDay } from "../lib/format";
import { td, th } from "./ui";

/*
 * Single-series column chart of captured events per day.
 * Spec (dataviz): one hue, columns <= 24px with a 4px rounded data-end and a
 * square baseline, hairline solid grid, per-column hover/focus tooltip, a
 * table-view twin, and no legend (the title names the one series).
 */

const COLORS = {
  series: "#2a78d6",
  grid: "#e1e0d9",
  baseline: "#c3c2b7",
  muted: "#6b6a65",
};
const HEIGHT = 180;
const PAD = { top: 12, right: 8, bottom: 24, left: 36 };

function niceMax(max: number): { top: number; step: number } {
  if (max <= 0) return { top: 4, step: 1 };
  const raw = max / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw)!;
  return { top: Math.ceil(max / step) * step, step };
}

/** Column path: 4px rounded top, square bottom on the baseline. */
function columnPath(x: number, y: number, w: number, h: number): string {
  const r = Math.min(4, w / 2, h);
  const b = y + h;
  return `M${x},${b} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${b} Z`;
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry!.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

export function TrendChart({ data, label }: { data: DailyCount[]; label: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);

  const max = Math.max(0, ...data.map((d) => d.events));
  const { top, step } = niceMax(max);
  const plotW = Math.max(0, width - PAD.left - PAD.right);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const band = data.length ? plotW / data.length : 0;
  const barW = Math.max(2, Math.min(24, band - 2)); // 2px surface gap when bands are narrow
  const y = (v: number) => PAD.top + plotH - (v / top) * plotH;
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  const labelEvery = Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor(plotW / 56))));
  const activeDay = active === null ? null : data[active];

  return (
    <div>
      <div ref={ref} className="relative" style={{ height: HEIGHT }}>
        {width > 0 && (
          <svg width={width} height={HEIGHT} role="img" aria-label={`${label}. Use the table view for exact values.`}>
            {ticks.map((t) => (
              <g key={t}>
                <line
                  x1={PAD.left}
                  x2={width - PAD.right}
                  y1={y(t)}
                  y2={y(t)}
                  stroke={t === 0 ? COLORS.baseline : COLORS.grid}
                  strokeWidth={1}
                  shapeRendering="crispEdges"
                />
                <text x={PAD.left - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill={COLORS.muted} className="tabular">
                  {formatCount(t)}
                </text>
              </g>
            ))}
            {data.map((d, i) => {
              const cx = PAD.left + band * i + band / 2;
              const h = (d.events / top) * plotH;
              return (
                <g key={d.date}>
                  {h > 0 && (
                    <path
                      d={columnPath(cx - barW / 2, y(d.events), barW, h)}
                      fill={COLORS.series}
                      opacity={active === null || active === i ? 1 : 0.55}
                    />
                  )}
                  {i % labelEvery === 0 && (
                    <text x={cx} y={HEIGHT - 6} textAnchor="middle" fontSize={11} fill={COLORS.muted}>
                      {formatDay(d.date)}
                    </text>
                  )}
                  {/* Hit target: the full column band, bigger than the mark. */}
                  <rect
                    x={PAD.left + band * i}
                    y={PAD.top}
                    width={band}
                    height={plotH}
                    fill="transparent"
                    tabIndex={0}
                    role="graphics-symbol"
                    aria-label={`${formatDay(d.date)}: ${d.events} events`}
                    onPointerEnter={() => setActive(i)}
                    onPointerLeave={() => setActive(null)}
                    onFocus={() => setActive(i)}
                    onBlur={() => setActive(null)}
                    style={{ outline: "none" }}
                  />
                </g>
              );
            })}
            {active !== null && (
              <rect
                x={PAD.left + band * active + 1}
                y={PAD.top}
                width={Math.max(0, band - 2)}
                height={plotH}
                fill="none"
                stroke={COLORS.baseline}
                strokeWidth={1}
                pointerEvents="none"
              />
            )}
          </svg>
        )}
        {activeDay && active !== null && (
          <div
            className="pointer-events-none absolute z-10 -translate-x-1/2 rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs shadow-md"
            style={{
              left: Math.min(Math.max(PAD.left + band * active + band / 2, 60), width - 60),
              top: Math.max(0, y(activeDay.events) - 46),
            }}
          >
            <div className="text-sm font-semibold tabular">{formatCount(activeDay.events)} events</div>
            <div className="text-ink-3">{formatDay(activeDay.date)}</div>
          </div>
        )}
      </div>
      <div className="mt-2 flex justify-end">
        <button
          type="button"
          className="rounded px-1.5 py-0.5 text-xs text-ink-3 hover:bg-sunken hover:text-ink"
          aria-expanded={showTable}
          onClick={() => setShowTable((s) => !s)}
        >
          {showTable ? "Hide table" : "Show table"}
        </button>
      </div>
      {showTable && (
        <div className="mt-2 max-h-56 overflow-auto rounded-md border border-line">
          <table className="w-full text-sm" aria-label={label}>
            <thead className="sticky top-0 border-b border-line bg-sunken">
              <tr>
                <th className={th} scope="col">
                  Day (UTC)
                </th>
                <th className={`${th} text-right`} scope="col">
                  Events
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.date} className="border-b border-line last:border-0">
                  <td className={`${td} py-1.5`}>{formatDay(d.date)}</td>
                  <td className={`${td} py-1.5 text-right tabular`}>{formatCount(d.events)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
