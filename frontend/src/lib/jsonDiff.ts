export type DiffKind = "added" | "removed" | "changed";

export interface DiffEntry {
  /** JSONPath-style location, e.g. `$.items[0].price`. */
  path: string;
  kind: DiffKind;
  before?: unknown;
  after?: unknown;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function childPath(path: string, key: string | number): string {
  if (typeof key === "number") return `${path}[${key}]`;
  return /^[A-Za-z_$][\w$]*$/.test(key) ? `${path}.${key}` : `${path}[${JSON.stringify(key)}]`;
}

/**
 * Structural diff of two JSON values. Objects are compared by key, arrays by index.
 * A value whose type changes (object -> string, etc.) is reported once as `changed`.
 */
export function jsonDiff(before: unknown, after: unknown, path = "$"): DiffEntry[] {
  if (isObject(before) && isObject(after)) {
    const out: DiffEntry[] = [];
    const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
    for (const key of [...keys].sort()) {
      const p = childPath(path, key);
      if (!(key in after)) out.push({ path: p, kind: "removed", before: before[key] });
      else if (!(key in before)) out.push({ path: p, kind: "added", after: after[key] });
      else out.push(...jsonDiff(before[key], after[key], p));
    }
    return out;
  }
  if (Array.isArray(before) && Array.isArray(after)) {
    const out: DiffEntry[] = [];
    const length = Math.max(before.length, after.length);
    for (let i = 0; i < length; i++) {
      const p = childPath(path, i);
      if (i >= after.length) out.push({ path: p, kind: "removed", before: before[i] });
      else if (i >= before.length) out.push({ path: p, kind: "added", after: after[i] });
      else out.push(...jsonDiff(before[i], after[i], p));
    }
    return out;
  }
  if (Object.is(before, after)) return [];
  return [{ path, kind: "changed", before, after }];
}
