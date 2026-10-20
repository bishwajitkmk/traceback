"""Sample "checkout" API for the Traceback demo and end-to-end tests.

Run from this folder:  uvicorn app:app --port 9101
Set SAMPLE_APP_FIXED=1 to run the version with the bugs fixed.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import pricing

FIXED = os.environ.get("SAMPLE_APP_FIXED") == "1"
RELEASE = "1.0.1" if FIXED else "1.0.0"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sample_app")

app = FastAPI(title="Sample checkout API", version=RELEASE)

ORDERS: dict[str, dict] = {
    "ord_1001": {"order_id": "ord_1001", "status": "shipped", "quantity": 1, "total": 19.99},
}


class CheckoutRequest(BaseModel):
    cart_id: str
    quantity: int
    card_number: str | None = None
    coupon: str | None = None


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@app.post("/checkout", status_code=201)
async def checkout(payload: CheckoutRequest):
    if FIXED and payload.quantity < 1:
        return error(422, "invalid_quantity", "quantity must be at least 1")
    total = pricing.cart_total(payload.quantity)
    unit = pricing.unit_price(total, payload.quantity)  # ZeroDivisionError when quantity == 0
    order = {
        "order_id": "ord_7c1e",
        "status": "confirmed",
        "quantity": payload.quantity,
        "total": round(payload.quantity * pricing.UNIT_PRICE, 2),
    }
    ORDERS[order["order_id"]] = {**order, "unit_price": unit}
    return order


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    if FIXED and order_id not in ORDERS:
        return error(404, "not_found", "Order not found")
    order = ORDERS[order_id]  # KeyError for unknown ids in the buggy version
    return {k: order[k] for k in ("order_id", "status", "quantity", "total")}


@app.get("/cart")
async def cart():
    return {"items": [], "currency": "USD", "total": 0}


@app.get("/health")
async def health():
    return {"status": "ok"}


_api_key = os.environ.get("TRACEBACK_API_KEY")
if _api_key:
    from traceback_sdk import Traceback

    traceback_client = Traceback(
        app,
        api_key=_api_key,
        endpoint=os.environ.get("TRACEBACK_ENDPOINT", "http://localhost:8100/api/v1"),
        environment="demo",
        release=RELEASE,
        ignore_routes=["/health"],
    )
    log.info("Traceback enabled (release %s, endpoint %s)", RELEASE, traceback_client.endpoint)
else:
    traceback_client = None
    log.warning("TRACEBACK_API_KEY is not set; running without Traceback instrumentation")
