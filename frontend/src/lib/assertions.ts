import type {
  Assertion,
  AssertionDefinition,
  AssertionResult,
  ExecutionOutcome,
  ResponseSummary,
} from "../api/types";
import { getPath } from "./jsonPath";

/** Structural JSON equality; object key order does not matter (same as the server and CLI). */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.entries(value).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`;
  }
  return JSON.stringify(value ?? null);
}

function deepEqual(a: unknown, b: unknown): boolean {
  return canonical(a) === canonical(b);
}

export function describeAssertion(a: Assertion): string {
  switch (a.type) {
    case "json_path_equals":
      return `${a.path} equals ${JSON.stringify(a.expected)}`;
    case "json_path_exists":
      return `${a.path} exists`;
    case "body_contains":
      return `body contains ${JSON.stringify(a.expected)}`;
  }
}

/**
 * Evaluate a case's expectations against a response. The backend runs the same
 * rules for real runs; this copy powers the mock API and is unit-tested.
 */
export function evaluateAssertions(
  definition: AssertionDefinition,
  response: ResponseSummary,
): { outcome: ExecutionOutcome; results: AssertionResult[] } {
  const results: AssertionResult[] = [
    {
      description: `status is ${definition.expected_status}`,
      passed: response.status === definition.expected_status,
      expected: definition.expected_status,
      actual: response.status,
    },
  ];
  for (const a of definition.assertions) {
    const description = describeAssertion(a);
    if (a.type === "body_contains") {
      const text = typeof response.body === "string" ? response.body : JSON.stringify(response.body);
      results.push({
        description,
        passed: text.includes(a.expected),
        expected: a.expected,
        actual: null,
      });
      continue;
    }
    const lookup = getPath(response.body, a.path);
    if (a.type === "json_path_exists") {
      results.push({ description, passed: lookup.found, expected: true, actual: lookup.found });
    } else {
      results.push({
        description,
        passed: lookup.found && deepEqual(lookup.value, a.expected),
        expected: a.expected,
        actual: lookup.found ? lookup.value : undefined,
      });
    }
  }
  return { outcome: results.every((r) => r.passed) ? "passed" : "failed", results };
}
