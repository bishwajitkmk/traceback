from __future__ import annotations

import io
import json
import xml.etree.ElementTree as ET

import httpx
import pytest
from conftest import API_KEY

from traceback_sdk.assertions import evaluate_assertions
from traceback_sdk.cli import main

ENDPOINT = "http://tb.test/api/v1"
TARGET = "http://target.test:9101"

CASES = [
    {
        "id": "case_qty",
        "name": "quantity 0 is rejected",
        "request_definition": {
            "method": "POST",
            "path": "/checkout",
            "query": {"tag": ["a", "b"], "v": "1"},
            "headers": {
                "content-type": "application/json",
                "Authorization": "Bearer secret",
                "Cookie": "sid=1",
                "x-api-key": "k",
                "X-Trace": "keep",
                "x-masked": "[REDACTED]",
                "host": "prod.example",
            },
            "body": {"cart_id": "c1", "quantity": 0},
        },
        "assertion_definition": {
            "expected_status": 422,
            "assertions": [
                {"type": "json_path_equals", "path": "$.error.code", "expected": "invalid_quantity"}
            ],
        },
    },
    {
        "id": "case_order",
        "name": "unknown order is 404",
        "request_definition": {
            "method": "GET",
            "path": "/orders/nope",
            "query": {},
            "headers": {},
            "body": None,
        },
        "assertion_definition": {"expected_status": 404, "assertions": []},
    },
]


class FakeApi:
    def __init__(self, cases=CASES, list_status=200, run_status=200, auth_ok=True):
        self.cases = cases
        self.list_status = list_status
        self.run_status = run_status
        self.auth_ok = auth_ok
        self.reports: dict[str, dict] = {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.auth_ok or request.headers.get("authorization") != f"Bearer {API_KEY}":
            return httpx.Response(
                401, json={"error": {"code": "invalid_api_key", "message": "Invalid API key"}}
            )
        path = request.url.path
        if request.method == "GET" and path == "/api/v1/ci/regression-cases":
            if self.list_status != 200:
                return httpx.Response(
                    self.list_status, json={"error": {"code": "x", "message": "y"}}
                )
            return httpx.Response(200, json=self.cases)
        if request.method == "POST" and path.endswith("/runs"):
            case_id = path.split("/")[-2]
            report = json.loads(request.content)
            self.reports[case_id] = report
            if self.run_status != 200:
                return httpx.Response(self.run_status)
            case = next(c for c in self.cases if c["id"] == case_id)
            if report["error"]:
                return httpx.Response(
                    200,
                    json={
                        "id": "ex",
                        "status": "error",
                        "outcome": None,
                        "assertion_results": None,
                        "error_summary": report["error"],
                    },
                )
            outcome, results = evaluate_assertions(case["assertion_definition"], report["response"])
            return httpx.Response(
                200,
                json={
                    "id": "ex",
                    "status": "completed",
                    "outcome": outcome,
                    "assertion_results": results,
                },
            )
        if request.method == "POST" and path == "/api/v1/ingest/events":
            event = json.loads(request.content)
            return httpx.Response(
                202,
                json={"event_id": event["event_id"], "incident_id": "inc_42", "duplicate": False},
            )
        return httpx.Response(404)


class FakeTarget:
    """Plays the sample app; ``fixed`` toggles the bug fixes."""

    def __init__(self, fixed=True, fail_with: Exception | None = None, big=False):
        self.fixed = fixed
        self.fail_with = fail_with
        self.big = big
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        if self.big:
            return httpx.Response(200, content=b"a" * (300 * 1024))
        if request.url.path == "/checkout":
            if not self.fixed:
                return httpx.Response(500, text="Internal Server Error")
            return httpx.Response(
                422,
                json={
                    "error": {"code": "invalid_quantity", "message": "quantity must be at least 1"}
                },
                headers={"set-cookie": "s=1"},
            )
        if request.url.path.startswith("/orders/"):
            return httpx.Response(404 if self.fixed else 500, json={"error": {"code": "not_found"}})
        return httpx.Response(302, headers={"location": "/elsewhere"})


def run_cli(argv, api, target=None, env_key=True, monkeypatch=None):
    out = io.StringIO()
    args = list(argv)
    if env_key and "--api-key" not in args:
        args += ["--api-key", API_KEY]
    code = main(
        args,
        out=out,
        api_transport=httpx.MockTransport(api),
        target_transport=httpx.MockTransport(target) if target else None,
    )
    return code, out.getvalue()


def test_run_all_pass_and_reports(tmp_path):
    api, target = FakeApi(), FakeTarget(fixed=True)
    junit = tmp_path / "report.xml"
    code, out = run_cli(
        ["run", "--target", TARGET, "--endpoint", ENDPOINT, "--junit", str(junit)], api, target
    )
    assert code == 0, out
    assert "PASS" in out and "2 passed, 0 failed, 0 errored" in out

    sent = target.requests[0]
    assert sent.method == "POST"
    assert str(sent.url) == f"{TARGET}/checkout?tag=a&tag=b&v=1"
    lowered = {k.lower() for k in sent.headers}
    for banned in ("authorization", "cookie", "x-api-key", "x-masked"):
        assert banned not in lowered
    assert sent.headers["x-trace"] == "keep"
    assert sent.headers["host"] == "target.test:9101"
    assert json.loads(sent.content) == {"cart_id": "c1", "quantity": 0}

    report = api.reports["case_qty"]
    assert report["target_url"] == TARGET
    assert report["error"] is None
    assert report["duration_ms"] >= 0
    assert report["response"]["status"] == 422
    assert report["response"]["body"]["error"]["code"] == "invalid_quantity"
    assert report["response"]["body_truncated"] is False
    assert report["response"]["headers"]["set-cookie"] == "[REDACTED]"

    root = ET.parse(junit).getroot()
    suite = root.find("testsuite")
    assert suite.get("tests") == "2" and suite.get("failures") == "0"
    assert len(suite.findall("testcase")) == 2


def test_run_failures_exit_1_and_junit(tmp_path):
    api, target = FakeApi(), FakeTarget(fixed=False)
    junit = tmp_path / "r.xml"
    code, out = run_cli(
        ["run", "--target", TARGET, "--endpoint", ENDPOINT, "--junit", str(junit)], api, target
    )
    assert code == 1
    assert "FAIL" in out and "0 passed, 2 failed" in out
    assert "status is 422: expected 422, got 500" in out
    suite = ET.parse(junit).getroot().find("testsuite")
    assert suite.get("failures") == "2"
    failure = suite.find("testcase").find("failure")
    assert "status is 422" in failure.get("message")


def test_run_target_unreachable_is_error():
    api = FakeApi()
    target = FakeTarget(fail_with=httpx.ConnectError("refused"))
    code, out = run_cli(["run", "--target", TARGET, "--endpoint", ENDPOINT], api, target)
    assert code == 1
    assert "ERROR" in out and "2 errored" in out
    assert api.reports["case_qty"]["response"] is None
    assert "connection failed" in api.reports["case_qty"]["error"]


def test_run_timeout_is_error(tmp_path):
    api = FakeApi()
    target = FakeTarget(fail_with=httpx.ReadTimeout("slow"))
    junit = tmp_path / "r.xml"
    code, _ = run_cli(
        [
            "run",
            "--target",
            TARGET,
            "--endpoint",
            ENDPOINT,
            "--case",
            "case_order",
            "--junit",
            str(junit),
        ],
        api,
        target,
    )
    assert code == 1
    assert "timeout" in api.reports["case_order"]["error"]
    suite = ET.parse(junit).getroot().find("testsuite")
    assert suite.get("errors") == "1"
    assert suite.find("testcase").find("error") is not None


def test_run_case_filter():
    api, target = FakeApi(), FakeTarget(fixed=True)
    code, out = run_cli(
        ["run", "--target", TARGET, "--endpoint", ENDPOINT, "--case", "case_order"], api, target
    )
    assert code == 0
    assert list(api.reports) == ["case_order"]
    assert len(target.requests) == 1 and target.requests[0].content == b""


def test_run_unknown_case_is_config_error():
    code, _ = run_cli(
        ["run", "--target", TARGET, "--endpoint", ENDPOINT, "--case", "zzz"],
        FakeApi(),
        FakeTarget(),
    )
    assert code == 2


def test_run_bad_key_exit_2(capsys):
    code, _ = run_cli(
        ["run", "--target", TARGET, "--endpoint", ENDPOINT], FakeApi(auth_ok=False), FakeTarget()
    )
    assert code == 2
    assert "authentication failed" in capsys.readouterr().err


def test_run_missing_key_exit_2(monkeypatch, capsys):
    monkeypatch.delenv("TRACEBACK_API_KEY", raising=False)
    code, _ = run_cli(["run", "--target", TARGET], FakeApi(), FakeTarget(), env_key=False)
    assert code == 2
    assert "API key is required" in capsys.readouterr().err


def test_run_env_config(monkeypatch):
    monkeypatch.setenv("TRACEBACK_API_KEY", API_KEY)
    monkeypatch.setenv("TRACEBACK_ENDPOINT", ENDPOINT)
    api = FakeApi()
    code, _ = run_cli(["run", "--target", TARGET], api, FakeTarget(), env_key=False)
    assert code == 0
    assert str(api.requests[0].url) == f"{ENDPOINT}/ci/regression-cases"


def test_run_api_unreachable_exit_2():
    def down(request):
        raise httpx.ConnectError("refused")

    code, _ = run_cli(["run", "--target", TARGET, "--endpoint", ENDPOINT], down, FakeTarget())
    assert code == 2


def test_run_report_failure_falls_back_to_local_evaluation():
    api = FakeApi(run_status=503)
    code, out = run_cli(
        ["run", "--target", TARGET, "--endpoint", ENDPOINT], api, FakeTarget(fixed=False)
    )
    assert code == 1
    assert "evaluated locally" in out and "2 failed" in out
    code, out = run_cli(
        ["run", "--target", TARGET, "--endpoint", ENDPOINT],
        FakeApi(run_status=503),
        FakeTarget(fixed=True),
    )
    assert code == 0


def test_run_does_not_follow_redirects_and_caps_body():
    cases = [
        {
            "id": "r",
            "name": "redirect",
            "request_definition": {
                "method": "GET",
                "path": "/old",
                "query": {},
                "headers": {},
                "body": None,
            },
            "assertion_definition": {"expected_status": 302, "assertions": []},
        }
    ]
    api = FakeApi(cases=cases)
    target = FakeTarget()
    code, _ = run_cli(["run", "--target", TARGET, "--endpoint", ENDPOINT], api, target)
    assert code == 0 and len(target.requests) == 1

    api = FakeApi(
        cases=[{**cases[0], "assertion_definition": {"expected_status": 200, "assertions": []}}]
    )
    code, _ = run_cli(
        ["run", "--target", TARGET, "--endpoint", ENDPOINT], api, FakeTarget(big=True)
    )
    assert code == 0
    response = api.reports["r"]["response"]
    assert response["body_truncated"] is True
    assert len(response["body"]) == 256 * 1024


def test_run_no_cases(tmp_path):
    junit = tmp_path / "r.xml"
    code, out = run_cli(
        ["run", "--target", TARGET, "--endpoint", ENDPOINT, "--junit", str(junit)],
        FakeApi(cases=[]),
        FakeTarget(),
    )
    assert code == 0 and "No regression cases" in out and junit.exists()


def test_run_invalid_target():
    code, _ = run_cli(["run", "--target", "localhost:9101", "--endpoint", ENDPOINT], FakeApi())
    assert code == 2


def test_check_success():
    api = FakeApi()
    code, out = run_cli(["check", "--endpoint", ENDPOINT], api)
    assert code == 0
    assert "inc_42" in out
    event = json.loads(api.requests[0].content)
    assert event["event_type"] == "exception"
    assert event["exception"]["type"] == "TracebackTestEvent"
    assert event["occurred_at"].endswith("Z")


def test_check_bad_key():
    code, _ = run_cli(["check", "--endpoint", ENDPOINT], FakeApi(auth_ok=False))
    assert code == 2


def test_check_rejected():
    def reject(request):
        return httpx.Response(422, json={"error": {"code": "validation_error", "message": "bad"}})

    code, _ = run_cli(["check", "--endpoint", ENDPOINT], reject)
    assert code == 1


def test_check_unreachable():
    def down(request):
        raise httpx.ConnectError("refused")

    code, _ = run_cli(["check", "--endpoint", ENDPOINT], down)
    assert code == 2


@pytest.mark.parametrize("argv", [[], ["run"], ["bogus"]])
def test_usage_errors(argv):
    assert main(argv) == 2
