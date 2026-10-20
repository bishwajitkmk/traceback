import { describe, expect, test } from "vitest";
import type { TracebackEvent } from "../api/types";
import { evaluateAssertions } from "./assertions";
import { formatRelative } from "./format";
import { jsonDiff } from "./jsonDiff";
import { getPath } from "./jsonPath";
import { findRedactedPaths, queryFromString, queryToString, requestFromEvent } from "./request";

describe("jsonDiff", () => {
  test("reports added, removed and changed fields with paths", () => {
    const before = { status: "error", detail: "boom", items: [1, 2], meta: { v: 1 } };
    const after = { status: "ok", items: [1], meta: { v: 1, w: 2 }, total: 3 };
    expect(jsonDiff(before, after)).toEqual([
      { path: "$.detail", kind: "removed", before: "boom" },
      { path: "$.items[1]", kind: "removed", before: 2 },
      { path: "$.meta.w", kind: "added", after: 2 },
      { path: "$.status", kind: "changed", before: "error", after: "ok" },
      { path: "$.total", kind: "added", after: 3 },
    ]);
  });

  test("identical values produce no entries", () => {
    expect(jsonDiff({ a: [1, { b: null }] }, { a: [1, { b: null }] })).toEqual([]);
  });

  test("type change is a single change, not a recursive diff", () => {
    expect(jsonDiff({ a: { b: 1 } }, { a: "x" })).toEqual([
      { path: "$.a", kind: "changed", before: { b: 1 }, after: "x" },
    ]);
  });

  test("quotes keys that are not identifiers", () => {
    expect(jsonDiff({}, { "content-type": "x" })[0]?.path).toBe('$["content-type"]');
  });
});

describe("getPath", () => {
  const doc = { error: { code: "E1" }, items: [{ id: 7 }], "a-b": { "x y": 1 }, nil: null };

  test.each([
    ["$.error.code", "E1"],
    ["error.code", "E1"],
    ["$.items[0].id", 7],
    ['$["a-b"]["x y"]', 1],
    ["$.nil", null],
  ])("%s", (path, value) => {
    expect(getPath(doc, path)).toEqual({ found: true, value });
  });

  test("missing and malformed paths are not found", () => {
    expect(getPath(doc, "$.items[3]").found).toBe(false);
    expect(getPath(doc, "$.error.code.deeper").found).toBe(false);
    expect(getPath(doc, "$..bad").found).toBe(false);
  });
});

describe("evaluateAssertions", () => {
  const response = { status: 200, headers: {}, body: { order: { total: 42 } }, body_truncated: false };

  test("passes when status and every assertion match", () => {
    const { outcome, results } = evaluateAssertions(
      {
        expected_status: 200,
        assertions: [
          { type: "json_path_equals", path: "$.order.total", expected: 42 },
          { type: "json_path_exists", path: "$.order" },
          { type: "body_contains", expected: "total" },
        ],
      },
      response,
    );
    expect(outcome).toBe("passed");
    expect(results).toHaveLength(4);
  });

  test("fails on status mismatch and reports actual values", () => {
    const { outcome, results } = evaluateAssertions(
      { expected_status: 201, assertions: [{ type: "json_path_equals", path: "$.order.total", expected: 40 }] },
      response,
    );
    expect(outcome).toBe("failed");
    expect(results.map((r) => r.passed)).toEqual([false, false]);
    expect(results[1]?.actual).toBe(42);
  });
});

describe("requestFromEvent", () => {
  const event = {
    request_method: "post",
    normalized_route: "/orders/{id}",
    request_data: {
      path: "/orders/12",
      query: { tag: ["a", "b"] },
      headers: {
        Authorization: "Bearer prod-secret",
        Cookie: "session=1",
        "X-Api-Key": "[REDACTED]",
        "Content-Type": "application/json",
        Host: "api.example.com",
        "X-Custom": "[REDACTED]",
      },
      body_captured: true,
      body: { qty: 0, card: "[REDACTED]" },
    },
  } as unknown as TracebackEvent;

  test("never carries captured credentials or redacted headers into the replay", () => {
    const req = requestFromEvent(event);
    expect(req.method).toBe("POST");
    expect(req.path).toBe("/orders/12");
    expect(req.headers).toEqual({ "Content-Type": "application/json" });
    expect(req.query).toEqual({ tag: ["a", "b"] });
  });

  test("finds redacted body values that need an override", () => {
    expect(findRedactedPaths(requestFromEvent(event).body)).toEqual(["$.card"]);
  });

  test("body is null when capture was disabled", () => {
    const noBody = { ...event, request_data: { ...event.request_data!, body_captured: false } };
    expect(requestFromEvent(noBody).body).toBeNull();
  });
});

test("query string round-trips repeated keys", () => {
  const q = queryFromString("?tag=a&tag=b&page=2");
  expect(q).toEqual({ tag: ["a", "b"], page: "2" });
  expect(queryToString(q)).toBe("tag=a&tag=b&page=2");
});

test("formatRelative", () => {
  const now = Date.parse("2026-10-14T12:00:00Z");
  expect(formatRelative("2026-10-14T11:59:30Z", now)).toBe("just now");
  expect(formatRelative("2026-10-14T11:59:10Z", now)).toBe("1 minute ago");
  expect(formatRelative("2026-10-14T09:00:00Z", now)).toBe("3 hours ago");
  expect(formatRelative("2026-10-12T12:00:00Z", now)).toBe("2 days ago");
});
