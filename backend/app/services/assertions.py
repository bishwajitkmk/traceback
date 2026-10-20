"""Regression assertions. Same semantics as frontend/src/lib/{jsonPath,assertions}.ts
and the CLI (docs/contracts.md); the server's evaluation is authoritative."""

import json
import re
from typing import Any

_TOKEN = re.compile(r'^(?:\.([A-Za-z_$][\w$-]*)|\[(\d+)\]|\["((?:[^"\\]|\\.)*)"\])')
_MISSING = object()


def parse_path(path: str) -> list[str | int] | None:
    rest = path.strip()
    if rest.startswith("$"):
        rest = rest[1:]
    if rest and not rest.startswith((".", "[")):
        rest = "." + rest
    tokens: list[str | int] = []
    while rest:
        m = _TOKEN.match(rest)
        if not m:
            return None
        if m.group(1) is not None:
            tokens.append(m.group(1))
        elif m.group(2) is not None:
            tokens.append(int(m.group(2)))
        else:
            tokens.append(json.loads(f'"{m.group(3)}"'))
        rest = rest[m.end() :]
    return tokens


def get_path(value: Any, path: str) -> tuple[bool, Any]:
    tokens = parse_path(path)
    if tokens is None:
        return False, None
    current = value
    for token in tokens:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                return False, None
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                return False, None
            current = current[token]
    return True, current


def describe(assertion: dict[str, Any]) -> str:
    kind = assertion["type"]
    if kind == "json_path_equals":
        return f"{assertion['path']} equals {json.dumps(assertion.get('expected'))}"
    if kind == "json_path_exists":
        return f"{assertion['path']} exists"
    return f"body contains {json.dumps(assertion['expected'])}"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def evaluate(
    definition: dict[str, Any], status: int, body: Any
) -> tuple[str, list[dict[str, Any]]]:
    """Return (outcome, results) for a response."""
    expected_status = definition["expected_status"]
    results: list[dict[str, Any]] = [
        {
            "description": f"status is {expected_status}",
            "passed": status == expected_status,
            "expected": expected_status,
            "actual": status,
        }
    ]
    for a in definition.get("assertions", []):
        description = describe(a)
        if a["type"] == "body_contains":
            text = body if isinstance(body, str) else json.dumps(body)
            results.append(
                {
                    "description": description,
                    "passed": a["expected"] in text,
                    "expected": a["expected"],
                    "actual": None,
                }
            )
            continue
        found, value = get_path(body, a["path"])
        if a["type"] == "json_path_exists":
            results.append(
                {"description": description, "passed": found, "expected": True, "actual": found}
            )
        else:
            passed = found and _canonical(value) == _canonical(a.get("expected"))
            results.append(
                {
                    "description": description,
                    "passed": passed,
                    "expected": a.get("expected"),
                    "actual": value if found else None,
                }
            )
    outcome = "passed" if all(r["passed"] for r in results) else "failed"
    return outcome, results
