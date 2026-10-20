export interface PathLookup {
  found: boolean;
  value: unknown;
}

/**
 * Parse a simple JSONPath subset: `$`, `.key`, `["key"]`, `[0]`.
 * The leading `$` is optional, so `error.code` and `$.error.code` are equivalent.
 */
export function parsePath(path: string): (string | number)[] | null {
  const tokens: (string | number)[] = [];
  let rest = path.trim().replace(/^\$/, "");
  if (rest && !rest.startsWith(".") && !rest.startsWith("[")) rest = `.${rest}`;
  const pattern = /^(?:\.([A-Za-z_$][\w$-]*)|\[(\d+)\]|\["((?:[^"\\]|\\.)*)"\])/;
  while (rest) {
    const m = pattern.exec(rest);
    if (!m) return null;
    if (m[1] !== undefined) tokens.push(m[1]);
    else if (m[2] !== undefined) tokens.push(Number(m[2]));
    else tokens.push(JSON.parse(`"${m[3]}"`) as string);
    rest = rest.slice(m[0].length);
  }
  return tokens;
}

export function getPath(value: unknown, path: string): PathLookup {
  const tokens = parsePath(path);
  if (!tokens) return { found: false, value: undefined };
  let current: unknown = value;
  for (const token of tokens) {
    if (typeof token === "number") {
      if (!Array.isArray(current) || token >= current.length) return { found: false, value: undefined };
      current = current[token];
    } else {
      if (typeof current !== "object" || current === null || Array.isArray(current)) {
        return { found: false, value: undefined };
      }
      if (!(token in current)) return { found: false, value: undefined };
      current = (current as Record<string, unknown>)[token];
    }
  }
  return { found: true, value: current };
}
