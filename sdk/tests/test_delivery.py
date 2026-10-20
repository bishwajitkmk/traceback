"""Delivery: retries, timeouts, 4xx, queue overflow, fail-open behavior."""

from __future__ import annotations

import json
import logging
import threading
import time

import httpx
import pytest
from conftest import API_KEY, Recorder, make_app
from fastapi.testclient import TestClient

from traceback_sdk import Traceback
from traceback_sdk.transport import BackgroundWorker, EventSender

EVENT = {"event_id": "11111111-1111-4111-8111-111111111111", "event_type": "http_error"}


def sender_for(handler, **kwargs) -> tuple[EventSender, list[float]]:
    sleeps: list[float] = []
    sender = EventSender(
        API_KEY,
        "http://tb.test/api/v1",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        **kwargs,
    )
    return sender, sleeps


def test_timeout_retries_then_gives_up(caplog):
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("timed out", request=request)

    sender, sleeps = sender_for(handler, max_retries=3, backoff_base=0.5)
    with caplog.at_level(logging.WARNING, logger="traceback_sdk"):
        assert sender.send(EVENT) is None
    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]  # exponential backoff between attempts
    # retries reuse the same idempotency key
    assert {json.loads(c.content)["event_id"] for c in calls} == {EVENT["event_id"]}
    assert "giving up" in caplog.text
    assert "ReadTimeout" in caplog.text


def test_5xx_retried_then_success():
    statuses = iter([503, 500, 202])

    def handler(request):
        return httpx.Response(next(statuses), json={"incident_id": "inc"})

    sender, sleeps = sender_for(handler, max_retries=3, backoff_base=0.1)
    response = sender.send(EVENT)
    assert response is not None and response.status_code == 202
    assert len(sleeps) == 2


def test_backoff_is_capped():
    sender, sleeps = sender_for(
        lambda r: httpx.Response(500), max_retries=5, backoff_base=1.0, max_backoff=3.0
    )
    sender.send(EVENT)
    assert sleeps == [1.0, 2.0, 3.0, 3.0]


def test_429_honors_retry_after_with_cap():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        if len(calls) == 2:
            return httpx.Response(429, headers={"Retry-After": "3600"})
        return httpx.Response(202, json={})

    sender, sleeps = sender_for(handler, max_retries=3, max_backoff=10.0)
    assert sender.send(EVENT).status_code == 202
    assert sleeps == [2.0, 10.0]


@pytest.mark.parametrize("status", [400, 401, 413, 422])
def test_4xx_not_retried(status, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"code": "nope", "message": "no"}})

    sender, sleeps = sender_for(handler, max_retries=3)
    with caplog.at_level(logging.WARNING, logger="traceback_sdk"):
        sender.send(EVENT)
    assert len(calls) == 1 and sleeps == []
    assert "not retrying" in caplog.text and "nope" in caplog.text


def test_queue_overflow_drops(caplog):
    gate = threading.Event()

    def handler(request):
        gate.wait(2)
        return httpx.Response(202, json={})

    sender = EventSender(API_KEY, "http://tb.test/api/v1", transport=httpx.MockTransport(handler))
    worker = BackgroundWorker(sender, queue_size=2)
    with caplog.at_level(logging.WARNING, logger="traceback_sdk"):
        results = [worker.submit({"event_id": str(i)}) for i in range(10)]
    # One may already be in flight; at most queue_size + 1 accepted.
    assert results.count(True) <= 3
    assert worker.dropped == results.count(False) >= 7
    assert "queue full" in caplog.text
    gate.set()
    assert worker.flush(2)
    worker.close(1)


def test_close_drains_and_stops():
    rec = Recorder()
    sender = EventSender(API_KEY, "http://tb.test/api/v1", transport=rec.transport)
    worker = BackgroundWorker(sender, queue_size=10)
    for i in range(5):
        worker.submit({"event_id": str(i)})
    worker.close(2)
    assert len(rec.requests) == 5
    assert worker.submit({"event_id": "late"}) is False


def test_close_interrupts_backoff_sleep():
    sender = EventSender(
        API_KEY,
        "http://tb.test/api/v1",
        transport=httpx.MockTransport(lambda r: httpx.Response(503)),
        max_retries=3,
        backoff_base=30.0,
        max_backoff=30.0,
    )
    worker = BackgroundWorker(sender)
    worker.submit(EVENT)
    started = time.monotonic()
    worker.close(0.1)
    assert time.monotonic() - started < 2.0


def _capture(app, path="/ok", **kwargs):
    res = TestClient(app, raise_server_exceptions=False).get(path, **kwargs)
    return (
        res.status_code,
        res.content,
        {k: v for k, v in res.headers.items() if k != "x-correlation-id"},
    )


@pytest.mark.parametrize(
    "failure",
    [
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused", request=r)),
        lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=r)),
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(401, json={"error": {"code": "invalid_api_key"}}),
        lambda r: (_ for _ in ()).throw(RuntimeError("transport exploded")),
    ],
)
@pytest.mark.parametrize("path", ["/ok", "/http500", "/boom", "/notfound"])
def test_original_response_preserved_when_telemetry_fails(failure, path):
    baseline = _capture(make_app(), path)
    app = make_app()
    tb = Traceback(
        app,
        api_key=API_KEY,
        transport=httpx.MockTransport(failure),
        backoff_base=0.0,
        max_retries=2,
    )
    try:
        started = time.perf_counter()
        observed = _capture(app, path)
        assert time.perf_counter() - started < 1.0  # delivery is off the request path
        assert observed == baseline
    finally:
        tb.close(1)


def test_exception_reaches_server_error_handling_when_telemetry_fails():
    app = make_app()
    tb = Traceback(
        app,
        api_key=API_KEY,
        transport=httpx.MockTransport(lambda r: httpx.Response(503)),
        backoff_base=0.0,
    )
    try:
        with pytest.raises(RuntimeError, match="kaboom"):
            TestClient(app).get("/boom")
        res = TestClient(app, raise_server_exceptions=False).get("/boom")
        assert res.status_code == 500
        assert res.text == "Internal Server Error"
    finally:
        tb.close(1)


def test_slow_ingestion_does_not_block_requests():
    def slow(request):
        time.sleep(0.15)
        return httpx.Response(202, json={})

    app = make_app()
    tb = Traceback(app, api_key=API_KEY, transport=httpx.MockTransport(slow))
    try:
        c = TestClient(app, raise_server_exceptions=False)
        started = time.perf_counter()
        for _ in range(5):
            assert c.get("/boom").status_code == 500
        assert time.perf_counter() - started < 0.5
    finally:
        tb.close(2)


def test_endpoint_from_env(monkeypatch):
    monkeypatch.setenv("TRACEBACK_ENDPOINT", "http://env.test/api/v1")
    rec = Recorder()
    app = make_app()
    tb = Traceback(app, api_key=API_KEY, transport=rec.transport)
    TestClient(app, raise_server_exceptions=False).get("/boom")
    tb.flush(2)
    tb.close()
    assert str(rec.requests[0].url) == "http://env.test/api/v1/ingest/events"
