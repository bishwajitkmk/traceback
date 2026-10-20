# Sample FastAPI app

A small "checkout" API with two deliberate bugs, used for the Traceback demo
and end-to-end tests. It is instrumented with `traceback-sdk`.

## Run

```bash
cd examples/sample_app
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt      # installs ../../sdk in editable mode

export TRACEBACK_API_KEY=tb_...                               # from Project settings
export TRACEBACK_ENDPOINT=http://localhost:8100/api/v1        # default
uvicorn app:app --port 9101
```

If `TRACEBACK_API_KEY` is not set, the app runs without instrumentation and
logs a warning.

| Env | Effect |
| --- | --- |
| `SAMPLE_APP_FIXED=1` | Bugs fixed; release `1.0.1` (default: buggy, release `1.0.0`) |
| `TRACEBACK_API_KEY` | Enables the SDK (environment `demo`) |
| `TRACEBACK_ENDPOINT` | Ingestion API base URL |

## Endpoints

| Request | Buggy (default) | Fixed (`SAMPLE_APP_FIXED=1`) |
| --- | --- | --- |
| `POST /checkout` `{"cart_id": "c1", "quantity": 0}` | 500, `ZeroDivisionError` raised in `pricing.unit_price` | 422 `{"error": {"code": "invalid_quantity", ...}}` |
| `POST /checkout` `{"cart_id": "c1", "quantity": 2}` | 201 `{"order_id": "ord_7c1e", "status": "confirmed", "quantity": 2, "total": 39.98}` | same |
| `GET /orders/unknown` | 500, `KeyError` | 404 `{"error": {"code": "not_found", "message": "Order not found"}}` |
| `GET /orders/ord_1001` | 200 | 200 |
| `GET /cart` | 200 `{"items": [], "currency": "USD", "total": 0}` | same |
| `GET /health` | 200 `{"status": "ok"}` (ignored by Traceback) | same |

The checkout body also accepts `card_number` and `coupon`. `card_number` is
redacted by the SDK before anything is sent.

## Demo flow

```bash
curl -X POST localhost:9101/checkout -H 'content-type: application/json' \
  -d '{"cart_id": "c1", "quantity": 0, "card_number": "4242424242424242"}'   # -> 500, incident created
# fix: restart with SAMPLE_APP_FIXED=1, save the request as a regression case, then
traceback run --target http://localhost:9101
```
