"""``traceback`` command-line tool.

    traceback check --api-key tb_...            send a synthetic test event
    traceback run --target http://localhost:9101  run saved regression cases (CI)

Exit codes: 0 success, 1 a case failed or errored (or ``check`` was rejected),
2 configuration / authentication / API errors.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, TextIO

import httpx

from . import __version__
from .assertions import evaluate_assertions, to_json_text
from .client import DEFAULT_ENDPOINT, SDK_INFO
from .redaction import REDACTED, Redactor
from .transport import USER_AGENT

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 2

MAX_RESPONSE_BYTES = 256 * 1024

# Same lists as frontend/src/lib/request.ts safeReplayHeaders.
CREDENTIAL_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "x-csrf-token",
    }
)
TRANSPORT_HEADERS = frozenset({"host", "content-length", "connection", "accept-encoding"})


class CliError(Exception):
    def __init__(self, message: str, code: int = EXIT_CONFIG) -> None:
        super().__init__(message)
        self.code = code


def safe_replay_headers(headers: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, value in (headers or {}).items():
        lower = str(name).lower()
        if lower in CREDENTIAL_HEADERS or lower in TRANSPORT_HEADERS or value == REDACTED:
            continue
        out[str(name)] = str(value)
    return out


# ---------------------------------------------------------------- API helpers


def _api_client(
    api_key: str, timeout: float, transport: httpx.BaseTransport | None
) -> httpx.Client:
    return httpx.Client(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT},
    )


def _error_message(response: httpx.Response) -> str:
    try:
        err = response.json()["error"]
        return f"{err.get('code')}: {err.get('message')}"
    except Exception:
        return response.text[:200] or response.reason_phrase


def _check_auth(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise CliError(
            f"authentication failed ({_error_message(response)}). "
            "Check --api-key / TRACEBACK_API_KEY."
        )
    if response.status_code == 403:
        raise CliError(f"access denied ({_error_message(response)})")


# ---------------------------------------------------------------- check


def cmd_check(args: argparse.Namespace, out: TextIO, api_transport: Any) -> int:
    api_key, endpoint = _credentials(args)
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "exception",
        "occurred_at": now,
        "environment": args.environment,
        "correlation_id": "req_" + uuid.uuid4().hex[:12],
        "duration_ms": 0,
        "request": {
            "method": "GET",
            "route": "/traceback/check",
            "path": "/traceback/check",
            "query": {},
            "headers": {"user-agent": USER_AGENT},
            "body_captured": False,
            "body": None,
            "body_truncated": False,
        },
        "response": {"status": 500, "headers": {}, "body": None},
        "exception": {
            "type": "TracebackTestEvent",
            "message": "Test event sent by `traceback check`",
            "frames": [
                {
                    "filename": "traceback_sdk/cli.py",
                    "lineno": 1,
                    "function": "cmd_check",
                    "context_line": "traceback check",
                    "in_app": True,
                }
            ],
        },
        "sdk": dict(SDK_INFO),
    }
    url = endpoint.rstrip("/") + "/ingest/events"
    with _api_client(api_key, args.timeout, api_transport) as client:
        try:
            response = client.post(url, json=event)
        except httpx.HTTPError as exc:
            raise CliError(
                f"could not reach Traceback at {endpoint}: {_describe_error(exc)}"
            ) from None
    _check_auth(response)
    if response.status_code != 202:
        print(
            f"error: ingestion rejected the test event with HTTP {response.status_code} "
            f"({_error_message(response)})",
            file=sys.stderr,
        )
        return EXIT_FAILED
    try:
        incident_id = response.json().get("incident_id")
    except ValueError:
        incident_id = None
    print(f"Test event {event['event_id']} accepted.", file=out)
    print(f"Incident: {incident_id}", file=out)
    return EXIT_OK


# ---------------------------------------------------------------- run


def _describe_error(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return f"timeout ({type(exc).__name__})"
    if isinstance(exc, httpx.ConnectError):
        return f"connection failed: {exc}" if str(exc) else "connection failed"
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


def build_target_request(target: str, definition: dict[str, Any]) -> dict[str, Any]:
    method = str(definition.get("method") or "GET").upper()
    path = str(definition.get("path") or "/")
    if not path.startswith("/"):
        path = "/" + path
    params: list[tuple[str, str]] = []
    for key, value in (definition.get("query") or {}).items():
        for v in value if isinstance(value, list) else [value]:
            params.append((str(key), "" if v is None else str(v)))
    headers = safe_replay_headers(definition.get("headers") or {})
    body = definition.get("body")
    content: bytes | None = None
    if body is not None:
        if isinstance(body, str):
            content = body.encode("utf-8")
        else:
            content = to_json_text(body).encode("utf-8")
            if not any(h.lower() == "content-type" for h in headers):
                headers["content-type"] = "application/json"
    return {
        "method": method,
        "url": target.rstrip("/") + path,
        "params": params,
        "headers": headers,
        "content": content,
    }


def execute_case(
    target: str,
    definition: dict[str, Any],
    timeout: float,
    transport: httpx.BaseTransport | None,
) -> dict[str, Any]:
    """Send a case's request to the target. Returns the run report body."""
    req = build_target_request(target, definition)
    started = time.perf_counter()
    response_summary: dict[str, Any] | None = None
    error: str | None = None
    try:
        with httpx.Client(transport=transport, timeout=timeout, follow_redirects=False) as client:
            with client.stream(
                req["method"],
                req["url"],
                params=req["params"],
                headers=req["headers"],
                content=req["content"],
            ) as response:
                chunks: list[bytes] = []
                size = 0
                truncated = False
                for chunk in response.iter_bytes():
                    room = MAX_RESPONSE_BYTES - size
                    if len(chunk) > room:
                        chunks.append(chunk[:room])
                        truncated = True
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                raw = b"".join(chunks)
                headers: dict[str, str] = {}
                for name, value in response.headers.multi_items():
                    key = name.lower()
                    headers[key] = f"{headers[key]}, {value}" if key in headers else value
                text = raw.decode(response.encoding or "utf-8", errors="replace")
                body: Any = text if raw else None
                if raw and not truncated:
                    try:
                        body = json.loads(text)
                    except ValueError:
                        body = text
                response_summary = {
                    "status": response.status_code,
                    "headers": Redactor().redact(headers),
                    "body": body,
                    "body_truncated": truncated,
                }
    except httpx.HTTPError as exc:
        error = _describe_error(exc)
    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        "target_url": target,
        "duration_ms": duration_ms,
        "response": response_summary,
        "error": error,
    }


def _credentials(args: argparse.Namespace) -> tuple[str, str]:
    api_key = args.api_key or os.environ.get("TRACEBACK_API_KEY")
    if not api_key:
        raise CliError("an API key is required (--api-key or TRACEBACK_API_KEY)")
    endpoint = args.endpoint or os.environ.get("TRACEBACK_ENDPOINT") or DEFAULT_ENDPOINT
    if not endpoint.startswith(("http://", "https://")):
        raise CliError(f"invalid endpoint {endpoint!r}; expected http(s)://.../api/v1")
    return api_key, endpoint


def cmd_run(
    args: argparse.Namespace,
    out: TextIO,
    api_transport: httpx.BaseTransport | None,
    target_transport: httpx.BaseTransport | None,
) -> int:
    api_key, endpoint = _credentials(args)
    target = args.target
    if not target.startswith(("http://", "https://")):
        raise CliError(f"invalid --target {target!r}; expected http(s)://host:port")
    base = endpoint.rstrip("/")

    with _api_client(api_key, max(args.timeout, 5.0), api_transport) as api:
        try:
            response = api.get(base + "/ci/regression-cases")
        except httpx.HTTPError as exc:
            raise CliError(
                f"could not reach Traceback at {endpoint}: {_describe_error(exc)}"
            ) from None
        _check_auth(response)
        if response.status_code != 200:
            raise CliError(
                f"listing regression cases failed with HTTP {response.status_code} "
                f"({_error_message(response)})"
            )
        try:
            cases = response.json()
            assert isinstance(cases, list)
        except Exception:
            raise CliError("unexpected response from GET /ci/regression-cases") from None

        if args.case:
            by_id = {c.get("id"): c for c in cases}
            missing = [cid for cid in args.case if cid not in by_id]
            if missing:
                raise CliError(f"unknown regression case id(s): {', '.join(missing)}")
            cases = [by_id[cid] for cid in args.case]

        if not cases:
            print("No regression cases to run.", file=out)
            if args.junit:
                write_junit(args.junit, [])
            return EXIT_OK

        print(f"Running {len(cases)} regression case(s) against {target}", file=out)
        results: list[dict[str, Any]] = []
        for case in cases:
            results.append(_run_one(api, base, target, case, args.timeout, target_transport))

    print_table(results, out)
    if args.junit:
        write_junit(args.junit, results)
        print(f"JUnit report written to {args.junit}", file=out)
    if any(r["result"] != "passed" for r in results):
        return EXIT_FAILED
    return EXIT_OK


def _run_one(
    api: httpx.Client,
    base: str,
    target: str,
    case: dict[str, Any],
    timeout: float,
    target_transport: httpx.BaseTransport | None,
) -> dict[str, Any]:
    case_id = str(case.get("id"))
    definition = case.get("request_definition") or {}
    assertion_def = case.get("assertion_definition") or {"expected_status": 200, "assertions": []}
    report = execute_case(target, definition, timeout, target_transport)

    outcome: str | None = None
    assertion_results: list[dict[str, Any]] | None = None
    reported = False
    report_error: str | None = None
    try:
        resp = api.post(f"{base}/ci/regression-cases/{case_id}/runs", json=report)
    except httpx.HTTPError as exc:
        report_error = _describe_error(exc)
    else:
        _check_auth(resp)
        if resp.status_code == 200:
            try:
                execution = resp.json()
                outcome = execution.get("outcome")
                assertion_results = execution.get("assertion_results")
                reported = True
            except ValueError:
                report_error = "invalid JSON from server"
        else:
            report_error = f"HTTP {resp.status_code} ({_error_message(resp)})"

    if report["error"] is not None:
        result = "error"
    elif reported and outcome in ("passed", "failed"):
        result = outcome
    else:
        local_outcome, local_results = evaluate_assertions(assertion_def, report["response"])
        result = local_outcome
        if not reported or assertion_results is None:
            assertion_results = local_results
    return {
        "id": case_id,
        "name": str(case.get("name") or case_id),
        "method": str(definition.get("method") or "GET").upper(),
        "path": str(definition.get("path") or "/"),
        "expected_status": assertion_def.get("expected_status"),
        "status": (report["response"] or {}).get("status"),
        "duration_ms": report["duration_ms"],
        "error": report["error"],
        "result": result,
        "assertion_results": assertion_results or [],
        "reported": reported,
        "report_error": report_error,
    }


# ---------------------------------------------------------------- output


def print_table(results: list[dict[str, Any]], out: TextIO) -> None:
    labels = {"passed": "PASS", "failed": "FAIL", "error": "ERROR"}
    rows = [
        (
            labels.get(r["result"], r["result"].upper()),
            r["name"],
            f"{r['method']} {r['path']}",
            f"{r['status'] if r['status'] is not None else '-'} (want {r['expected_status']})",
            f"{r['duration_ms']} ms",
        )
        for r in results
    ]
    header = ("RESULT", "CASE", "REQUEST", "STATUS", "TIME")
    widths = [max(len(header[i]), *(len(row[i]) for row in rows)) for i in range(len(header))]
    widths = [min(w, 48) for w in widths]

    def fmt(row: tuple[str, ...]) -> str:
        cells = [
            (c if len(c) <= widths[i] else c[: widths[i] - 1] + "...").ljust(widths[i])
            for i, c in enumerate(row)
        ]
        return "  ".join(cells).rstrip()

    print("", file=out)
    print(fmt(header), file=out)
    print("  ".join("-" * w for w in widths), file=out)
    for row, r in zip(rows, results, strict=True):
        print(fmt(row), file=out)
        if r["error"]:
            print(f"    error: {r['error']}", file=out)
        for a in r["assertion_results"]:
            if not a.get("passed"):
                print(
                    f"    x {a.get('description')}: expected {to_json_text(a.get('expected'))}, "
                    f"got {to_json_text(a.get('actual'))}",
                    file=out,
                )
        if not r["reported"]:
            print(
                f"    warning: result not reported to Traceback ({r['report_error']}); "
                "evaluated locally",
                file=out,
            )
    passed = sum(r["result"] == "passed" for r in results)
    failed = sum(r["result"] == "failed" for r in results)
    errored = sum(r["result"] == "error" for r in results)
    print("", file=out)
    print(f"{passed} passed, {failed} failed, {errored} errored", file=out)


def write_junit(path: str, results: list[dict[str, Any]]) -> None:
    suite = ET.Element(
        "testsuite",
        name="traceback",
        tests=str(len(results)),
        failures=str(sum(r["result"] == "failed" for r in results)),
        errors=str(sum(r["result"] == "error" for r in results)),
        time=f"{sum(r['duration_ms'] for r in results) / 1000:.3f}",
    )
    for r in results:
        case = ET.SubElement(
            suite,
            "testcase",
            classname="traceback.regression",
            name=f"{r['name']} [{r['id']}]",
            time=f"{r['duration_ms'] / 1000:.3f}",
        )
        if r["result"] == "error":
            node = ET.SubElement(case, "error", message=r["error"] or "error", type="RequestError")
            node.text = f"{r['method']} {r['path']}: {r['error']}"
        elif r["result"] == "failed":
            failed = [a for a in r["assertion_results"] if not a.get("passed")]
            message = "; ".join(str(a.get("description")) for a in failed) or "case failed"
            node = ET.SubElement(case, "failure", message=message, type="AssertionError")
            node.text = "\n".join(
                f"{a.get('description')}: expected {to_json_text(a.get('expected'))}, "
                f"got {to_json_text(a.get('actual'))}"
                for a in failed
            )
    tree = ET.ElementTree(ET.Element("testsuites"))
    tree.getroot().append(suite)
    ET.indent(tree)
    tree.write(path, encoding="utf-8", xml_declaration=True)


# ---------------------------------------------------------------- entry point


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="traceback", description="Traceback SDK command-line tool"
    )
    parser.add_argument("--version", action="version", version=f"traceback-sdk {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--api-key", help="project ingestion key (default: $TRACEBACK_API_KEY)")
        p.add_argument(
            "--endpoint",
            help=f"Traceback API base URL (default: $TRACEBACK_ENDPOINT or {DEFAULT_ENDPOINT})",
        )
        p.add_argument("--timeout", type=float, default=10.0, help="request timeout in seconds")

    check = sub.add_parser("check", help="send a synthetic test event and print the incident id")
    common(check)
    check.add_argument("--environment", default="development", help="environment of the test event")

    run = sub.add_parser("run", help="run saved regression cases against a target (for CI)")
    common(run)
    run.add_argument("--target", required=True, help="base URL of the service under test")
    run.add_argument(
        "--case", action="append", metavar="ID", help="only run this case (repeatable)"
    )
    run.add_argument("--junit", metavar="PATH", help="write a JUnit XML report")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    out: TextIO | None = None,
    api_transport: httpx.BaseTransport | None = None,
    target_transport: httpx.BaseTransport | None = None,
) -> int:
    out = out or sys.stdout
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_CONFIG if exc.code not in (0, None) else EXIT_OK
    try:
        if args.command == "check":
            return cmd_check(args, out, api_transport)
        return cmd_run(args, out, api_transport, target_transport)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
