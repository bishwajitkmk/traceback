"""Assertion evaluation, ported from ``frontend/src/lib/assertions.ts``.

The server re-evaluates every reported run; the CLI uses this copy only when the
result could not be reported.
"""

from __future__ import annotations

import json
import math
from typing import Any

from .jsonpath import get_path


def to_json_text(value: Any) -> str:
    """Compact serialization equivalent to JavaScript ``JSON.stringify``."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)


def json_equal(a: Any, b: Any) -> bool:
    """Equality by JSON structure: booleans are not numbers, 1 == 1.0, key order ignored."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, float) and math.isnan(a) or isinstance(b, float) and math.isnan(b):
            return False
        return a == b
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, str) or isinstance(b, str):
        return isinstance(a, str) and isinstance(b, str) and a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    return False


def describe_assertion(a: dict[str, Any]) -> str:
    kind = a.get("type")
    if kind == "json_path_equals":
        return f"{a.get('path')} equals {to_json_text(a.get('expected'))}"
    if kind == "json_path_exists":
        return f"{a.get('path')} exists"
    if kind == "body_contains":
        return f"body contains {to_json_text(a.get('expected'))}"
    return f"unknown assertion {kind!r}"


def evaluate_assertions(
    definition: dict[str, Any], response: dict[str, Any]
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(outcome, results)`` where outcome is ``"passed"`` or ``"failed"``."""
    expected_status = definition.get("expected_status")
    results: list[dict[str, Any]] = [
        {
            "description": f"status is {expected_status}",
            "passed": response.get("status") == expected_status,
            "expected": expected_status,
            "actual": response.get("status"),
        }
    ]
    body = response.get("body")
    for a in definition.get("assertions") or []:
        description = describe_assertion(a)
        kind = a.get("type")
        if kind == "body_contains":
            text = body if isinstance(body, str) else to_json_text(body)
            expected = a.get("expected")
            results.append(
                {
                    "description": description,
                    "passed": isinstance(expected, str) and expected in text,
                    "expected": expected,
                    "actual": None,
                }
            )
            continue
        lookup = get_path(body, str(a.get("path", "")))
        if kind == "json_path_exists":
            results.append(
                {
                    "description": description,
                    "passed": lookup.found,
                    "expected": True,
                    "actual": lookup.found,
                }
            )
        elif kind == "json_path_equals":
            results.append(
                {
                    "description": description,
                    "passed": lookup.found and json_equal(lookup.value, a.get("expected")),
                    "expected": a.get("expected"),
                    "actual": lookup.value if lookup.found else None,
                }
            )
        else:
            results.append(
                {"description": description, "passed": False, "expected": None, "actual": None}
            )
    outcome = "passed" if all(r["passed"] for r in results) else "failed"
    return outcome, results
