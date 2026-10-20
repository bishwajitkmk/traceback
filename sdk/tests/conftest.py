from __future__ import annotations

import json
import threading
from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from traceback_sdk import Traceback

API_KEY = "tb_" + "ab" * 24


class Recorder:
    """httpx MockTransport handler that records ingestion requests."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.handler = handler
        self.lock = threading.Lock()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        with self.lock:
            self.requests.append(request)
        if self.handler is not None:
            return self.handler(request)
        body = json.loads(request.content)
        return httpx.Response(
            202, json={"event_id": body["event_id"], "incident_id": "inc_1", "duplicate": False}
        )

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    @property
    def events(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]


def compute(total: float, quantity: int) -> float:
    return round(total / quantity, 2)


def make_app() -> FastAPI:
    app = FastAPI()

    @app.post("/orders/{order_id}")
    async def create(order_id: str, request: Request):
        data = await request.json()
        return {"order_id": order_id, "unit": compute(10.0, data["quantity"]), "echo": data}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    @app.get("/http500")
    async def http500():
        return JSONResponse(
            {"error": {"code": "db_down", "message": "db down"}},
            status_code=503,
            headers={"x-custom": "1", "set-cookie": "sid=abc"},
        )

    @app.get("/http-exc")
    async def http_exc():
        raise HTTPException(status_code=502, detail="upstream")

    @app.get("/ok")
    async def ok():
        return PlainTextResponse("fine", headers={"x-app": "yes"})

    @app.get("/notfound")
    async def notfound():
        return JSONResponse({"detail": "nope"}, status_code=404)

    @app.get("/health")
    async def health():
        raise RuntimeError("health broke")

    @app.get("/internal/{name}")
    async def internal(name: str):
        raise RuntimeError("internal broke")

    @app.post("/echo")
    async def echo(request: Request):
        raw = await request.body()
        return PlainTextResponse(raw, status_code=500 if b"fail" in raw else 200)

    return app


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def make_tb(recorder: Recorder):
    created: list[Traceback] = []

    def factory(app: FastAPI | None = None, **kwargs) -> tuple[FastAPI, Traceback]:
        app = app or make_app()
        kwargs.setdefault("transport", recorder.transport)
        kwargs.setdefault("backoff_base", 0.0)
        tb = Traceback(app, api_key=kwargs.pop("api_key", API_KEY), **kwargs)
        created.append(tb)
        return app, tb

    yield factory
    for tb in created:
        tb.close(timeout=1.0)
