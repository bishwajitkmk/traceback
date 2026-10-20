from __future__ import annotations

import logging

import httpx
import pytest
from conftest import API_KEY, make_app
from fastapi import FastAPI
from fastapi.testclient import TestClient

from traceback_sdk import Traceback


def client_for(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_exception_capture_contents(make_tb, recorder):
    app, tb = make_tb(environment="production", release="2.0.0")
    res = client_for(app).post(
        "/orders/12?tag=a&tag=b&page=2",
        json={"quantity": 0, "note": "x"},
        headers={"X-Request-ID": "req_from_client"},
    )
    assert res.status_code == 500
    assert tb.flush(2)
    [event] = recorder.events
    req = recorder.requests[0]
    assert req.url.path == "/api/v1/ingest/events"
    assert req.headers["authorization"] == f"Bearer {API_KEY}"

    assert event["event_type"] == "exception"
    assert len(event["event_id"]) == 36
    assert event["occurred_at"].endswith("Z")
    assert event["environment"] == "production"
    assert event["release"] == "2.0.0"
    assert event["correlation_id"] == "req_from_client"
    assert event["duration_ms"] >= 0
    assert event["sdk"] == {"name": "traceback-sdk", "version": "0.1.0"}
    r = event["request"]
    assert r["method"] == "POST"
    assert r["route"] == "/orders/{order_id}"
    assert r["path"] == "/orders/12"
    assert r["query"] == {"tag": ["a", "b"], "page": "2"}
    assert r["headers"]["content-type"] == "application/json"
    assert r["body_captured"] is True
    assert r["body"] == {"quantity": 0, "note": "x"}
    assert r["body_truncated"] is False
    assert event["response"]["status"] == 500

    exc = event["exception"]
    assert exc["type"] == "ZeroDivisionError"
    assert exc["message"] == "float division by zero"
    top = exc["frames"][-1]
    assert top["function"] == "compute"
    assert top["context_line"] == "return round(total / quantity, 2)"
    assert top["in_app"] is True
    assert top["filename"].endswith("conftest.py")
    assert isinstance(top["lineno"], int)
    assert exc["frames"][-2]["function"].endswith("create")
    assert exc["frames"][-2]["in_app"] is True
    lib = [f for f in exc["frames"] if "starlette" in f["filename"]]
    assert lib and not any(f["in_app"] for f in lib)
    assert not any(f["in_app"] for f in exc["frames"] if "traceback_sdk" in f["filename"])
    assert len(exc["frames"]) <= 100


def test_qualified_exception_type(make_tb, recorder):
    app = FastAPI()

    @app.get("/upstream")
    async def upstream():
        raise httpx.ReadTimeout("read timed out")

    app, tb = make_tb(app)
    assert client_for(app).get("/upstream").status_code == 500
    tb.flush(2)
    assert recorder.events[0]["exception"]["type"] == "httpx.ReadTimeout"


def test_in_app_include(make_tb, recorder):
    app, tb = make_tb(in_app_include=["somewhere_else"])
    client_for(app).get("/boom")
    tb.flush(2)
    assert not any(f["in_app"] for f in recorder.events[0]["exception"]["frames"])


def test_http_error_capture_without_exception(make_tb, recorder):
    app, tb = make_tb()
    res = client_for(app).get("/http500")
    assert res.status_code == 503
    tb.flush(2)
    [event] = recorder.events
    assert event["event_type"] == "http_error"
    assert "exception" not in event
    assert event["request"]["route"] == "/http500"
    assert event["response"]["status"] == 503
    assert event["response"]["body"] == {"error": {"code": "db_down", "message": "db down"}}
    assert event["response"]["headers"]["x-custom"] == "1"
    assert event["response"]["headers"]["set-cookie"] == "[REDACTED]"


def test_http_exception_5xx_and_below_threshold(make_tb, recorder):
    app, tb = make_tb()
    c = client_for(app)
    assert c.get("/http-exc").status_code == 502
    assert c.get("/notfound").status_code == 404
    assert c.get("/ok").status_code == 200
    tb.flush(2)
    assert [e["response"]["status"] for e in recorder.events] == [502]


def test_capture_status_min(make_tb, recorder):
    app, tb = make_tb(capture_status_min=400)
    client_for(app).get("/notfound")
    tb.flush(2)
    assert recorder.events[0]["response"]["status"] == 404


def test_successful_delivery(make_tb, recorder, caplog):
    app, tb = make_tb()
    with caplog.at_level(logging.WARNING, logger="traceback_sdk"):
        client_for(app).get("/boom")
        client_for(app).get("/boom")
        assert tb.flush(2)
    ids = [e["event_id"] for e in recorder.events]
    assert len(ids) == 2 and len(set(ids)) == 2
    assert all(r.headers["content-type"] == "application/json" for r in recorder.requests)
    assert not caplog.records


def test_request_body_still_readable(make_tb, recorder):
    app, tb = make_tb(max_body_bytes=10)
    payload = b"x" * 5000 + b"fail" + b"y" * 5000
    res = client_for(app).post("/echo", content=payload)
    assert res.status_code == 500
    assert res.content == payload  # the app saw the full, unchanged body
    tb.flush(2)
    event = recorder.events[0]
    assert event["request"]["body"] == "x" * 10
    assert event["request"]["body_truncated"] is True
    assert event["response"]["body"] == "x" * 10


def test_request_body_readable_streamed(make_tb, recorder):
    app, tb = make_tb(max_body_bytes=6)

    def gen():
        yield b"abc"
        yield b"def"
        yield b"ghi-fail"

    res = client_for(app).post("/echo", content=gen())
    assert res.content == b"abcdefghi-fail"
    tb.flush(2)
    assert recorder.events[0]["request"]["body"] == "abcdef"
    assert recorder.events[0]["request"]["body_truncated"] is True


def test_capture_body_disabled(make_tb, recorder):
    app, tb = make_tb(capture_body=False)
    client_for(app).post("/orders/1", json={"quantity": 0})
    tb.flush(2)
    r = recorder.events[0]["request"]
    assert r["body_captured"] is False and r["body"] is None


def test_correlation_id_generated_and_propagated(make_tb, recorder):
    app, tb = make_tb()
    c = client_for(app)
    cid = c.get("/ok").headers["x-correlation-id"]
    assert cid.startswith("req_") and len(cid) == 16
    res = c.get("/ok", headers={"x-correlation-id": "abc-123"})
    assert res.headers["x-correlation-id"] == "abc-123"
    res = c.get("/http500", headers={"x-request-id": "rid-9"})
    assert res.headers["x-correlation-id"] == "rid-9"
    tb.flush(2)
    assert recorder.events[0]["correlation_id"] == "rid-9"


def test_redaction(make_tb, recorder):
    app, tb = make_tb(redact_fields=["Internal_Note"])
    client_for(app).post(
        "/orders/1?api_key=k&access_token=t&q=keep",
        json={
            "quantity": 0,
            "card_number": "4242424242424242",
            "user": {"Password": "p", "name": "ann", "items": [{"cvv": "123", "sku": "s"}]},
            "internal_note": "custom",
            "internal_notes": "not an exact match",
        },
        headers={
            "Authorization": "Bearer x",
            "Cookie": "sid=1",
            "X-API-Key": "k",
            "X-Session-Id": "s",
            "Accept": "application/json",
        },
    )
    tb.flush(2)
    r = recorder.events[0]["request"]
    h = r["headers"]
    for name in ("authorization", "cookie", "x-api-key", "x-session-id"):
        assert h[name] == "[REDACTED]"
    assert h["accept"] == "application/json"
    assert r["query"] == {"api_key": "[REDACTED]", "access_token": "[REDACTED]", "q": "keep"}
    b = r["body"]
    assert b["card_number"] == "[REDACTED]"
    assert b["user"]["Password"] == "[REDACTED]"
    assert b["user"]["name"] == "ann"
    assert b["user"]["items"] == [{"cvv": "[REDACTED]", "sku": "s"}]
    assert b["internal_note"] == "[REDACTED]"
    assert b["internal_notes"] == "not an exact match"
    raw = recorder.requests[0].content
    assert b"4242424242424242" not in raw and b"Bearer x" not in raw


def test_form_body_redaction(make_tb, recorder):
    app, tb = make_tb()
    client_for(app).post("/echo", data={"user": "a", "password": "hunter2", "x": "fail"})
    tb.flush(2)
    body = recorder.events[0]["request"]["body"]
    assert "hunter2" not in body and "password=%5BREDACTED%5D" in body


@pytest.mark.parametrize(
    "kwargs",
    [
        {"enabled": False},
        {"environment": "development", "environments": ["production"]},
        {"environments": ["production"]},
        {"api_key": ""},
    ],
)
def test_disabled_sends_nothing(make_tb, recorder, kwargs):
    app, tb = make_tb(**kwargs)
    assert tb.enabled is False
    res = client_for(app).get("/boom")
    assert res.status_code == 500
    assert "x-correlation-id" not in res.headers
    tb.flush(1)
    assert recorder.requests == []


def test_environment_allow_list_enabled(make_tb, recorder):
    app, tb = make_tb(environment="production", environments=["production", "staging"])
    client_for(app).get("/boom")
    tb.flush(2)
    assert len(recorder.events) == 1


def test_ignore_routes(make_tb, recorder):
    app, tb = make_tb(ignore_routes=["/health", "/internal/*"])
    c = client_for(app)
    assert c.get("/health").status_code == 500
    assert c.get("/internal/x").status_code == 500
    assert c.get("/boom").status_code == 500
    tb.flush(2)
    assert [e["request"]["path"] for e in recorder.events] == ["/boom"]


def test_ignore_routes_by_template(make_tb, recorder):
    app, tb = make_tb(ignore_routes=["/internal/{name}"])
    client_for(app).get("/internal/abc")
    tb.flush(2)
    assert recorder.events == []


def test_raw_exception_propagates_to_server(make_tb):
    app, tb = make_tb()
    with pytest.raises(RuntimeError, match="kaboom"):
        TestClient(app).get("/boom")


def test_not_a_starlette_app():
    async def raw_app(scope, receive, send):  # pragma: no cover
        pass

    with pytest.raises(TypeError):
        Traceback(raw_app, api_key=API_KEY)


def test_lifespan_shutdown_flushes(make_tb, recorder):
    app, tb = make_tb()
    with TestClient(app, raise_server_exceptions=False) as c:
        c.get("/boom")
    # Leaving the context runs lifespan shutdown, which flushes the queue.
    assert len(recorder.events) == 1
    assert not tb._worker._closed  # flushed, still usable if the app starts again


def test_server_error_response_is_observed_and_tagged(make_tb, recorder):
    app, tb = make_tb()
    res = client_for(app).get("/boom", headers={"x-request-id": "rid-500"})
    assert res.status_code == 500 and res.text == "Internal Server Error"
    assert res.headers["x-correlation-id"] == "rid-500"
    tb.flush(2)
    event = recorder.events[0]
    assert event["response"]["status"] == 500
    assert event["response"]["body"] == "Internal Server Error"


def test_user_middleware_added_later_still_works(make_tb, recorder):
    app, tb = make_tb()

    class Tag:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            async def wrapped(message):
                if message["type"] == "http.response.start":
                    message["headers"] = [*message.get("headers", []), (b"x-tag", b"1")]
                await send(message)

            await self.app(scope, receive, wrapped)

    app.add_middleware(Tag)
    res = client_for(app).get("/http500")
    assert res.headers["x-tag"] == "1" and "x-correlation-id" in res.headers
    tb.flush(2)
    assert len(recorder.events) == 1


def test_attach_after_start_is_rejected(recorder):
    app = make_app()
    client_for(app).get("/ok")  # builds the middleware stack
    with pytest.raises(RuntimeError):
        Traceback(app, api_key=API_KEY, transport=recorder.transport)


def test_raw_asgi_app_with_middleware_class(recorder):
    from starlette.applications import Starlette
    from starlette.routing import Route

    from traceback_sdk import TracebackMiddleware

    def explode(request):
        raise ValueError("raw")

    inner = Starlette(routes=[Route("/x/{id}", explode)])
    holder = Starlette()  # only used to build a Traceback client
    tb = Traceback(holder, api_key=API_KEY, transport=recorder.transport)
    wrapped = TracebackMiddleware(inner, client=tb)
    res = TestClient(wrapped, raise_server_exceptions=False).get("/x/5")
    assert res.status_code == 500
    tb.flush(2)
    assert recorder.events[0]["request"]["route"] == "/x/{id}"
    assert recorder.events[0]["exception"]["type"] == "ValueError"
    tb.close()
