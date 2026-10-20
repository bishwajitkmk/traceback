"""Behavior of examples/sample_app (buggy and fixed), instrumented with a mock transport."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest
from conftest import API_KEY, Recorder
from fastapi.testclient import TestClient

from traceback_sdk import Traceback

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "sample_app"

pytestmark = pytest.mark.skipif(not SAMPLE_DIR.exists(), reason="sample app not present")


def load_sample(monkeypatch, fixed: bool):
    monkeypatch.setenv("SAMPLE_APP_FIXED", "1" if fixed else "0")
    monkeypatch.delenv("TRACEBACK_API_KEY", raising=False)
    monkeypatch.syspath_prepend(str(SAMPLE_DIR))
    name = f"sample_app_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SAMPLE_DIR / "app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_buggy_version(monkeypatch):
    sample = load_sample(monkeypatch, fixed=False)
    rec = Recorder()
    tb = Traceback(sample.app, api_key=API_KEY, transport=rec.transport, environment="demo")
    c = TestClient(sample.app, raise_server_exceptions=False)
    res = c.post("/checkout", json={"cart_id": "c1", "quantity": 0, "card_number": "4242"})
    assert res.status_code == 500
    assert c.get("/orders/nope").status_code == 500
    res = c.post("/checkout", json={"cart_id": "c1", "quantity": 2, "coupon": None})
    assert res.status_code == 201
    assert res.json() == {
        "order_id": "ord_7c1e",
        "status": "confirmed",
        "quantity": 2,
        "total": 39.98,
    }
    assert c.get("/cart").json() == {"items": [], "currency": "USD", "total": 0}
    assert c.get("/health").json() == {"status": "ok"}
    tb.flush(2)
    tb.close()
    checkout, order = rec.events
    top = checkout["exception"]["frames"][-1]
    assert checkout["exception"]["type"] == "ZeroDivisionError"
    assert top["filename"].endswith("pricing.py") and top["function"] == "unit_price"
    assert top["context_line"] == "return round(total / quantity, 2)" and top["in_app"]
    assert checkout["request"]["body"]["card_number"] == "[REDACTED]"
    assert order["exception"]["type"] == "KeyError"
    assert order["request"]["route"] == "/orders/{order_id}"


def test_fixed_version(monkeypatch):
    sample = load_sample(monkeypatch, fixed=True)
    assert sample.RELEASE == "1.0.1"
    c = TestClient(sample.app)
    res = c.post("/checkout", json={"cart_id": "c1", "quantity": 0})
    assert res.status_code == 422
    assert res.json() == {
        "error": {"code": "invalid_quantity", "message": "quantity must be at least 1"}
    }
    res = c.get("/orders/nope")
    assert res.status_code == 404
    assert res.json() == {"error": {"code": "not_found", "message": "Order not found"}}
