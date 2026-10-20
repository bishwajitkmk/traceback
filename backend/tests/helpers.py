import uuid
from datetime import UTC, datetime
from typing import Any


def event_payload(**overrides: Any) -> dict[str, Any]:
    """A realistic SDK event (docs/contracts.md) for POST /ingest/events."""
    event: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "event_type": "exception",
        "occurred_at": datetime.now(UTC).isoformat(),
        "environment": "production",
        "release": "2.14.0",
        "correlation_id": "req_abc123",
        "duration_ms": 37,
        "request": {
            "method": "POST",
            "route": "/checkout",
            "path": "/checkout",
            "query": {"tag": ["a", "b"], "debug": "1"},
            "headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer prod-secret",
                "Cookie": "session=abc",
                "X-Request-ID": "req_abc123",
            },
            "body_captured": True,
            "body": {
                "cart_id": "c1",
                "quantity": 0,
                "card_number": "4111111111111111",
                "nested": {"password": "pw"},
            },
            "body_truncated": False,
        },
        "response": {
            "status": 500,
            "headers": {"content-type": "application/json"},
            "body": {"detail": "Internal Server Error"},
        },
        "exception": {
            "type": "ZeroDivisionError",
            "message": "division by zero",
            "frames": [
                {
                    "filename": "starlette/routing.py",
                    "lineno": 74,
                    "function": "app",
                    "context_line": "await func()",
                    "in_app": False,
                },
                {
                    "filename": "app/routes/checkout.py",
                    "lineno": 41,
                    "function": "create_checkout",
                    "context_line": "price = unit_price()",
                    "in_app": True,
                },
                {
                    "filename": "app/services/pricing.py",
                    "lineno": 18,
                    "function": "unit_price",
                    "context_line": "return total / quantity",
                    "in_app": True,
                },
            ],
        },
        "sdk": {"name": "traceback-sdk", "version": "0.1.0"},
    }
    for key, value in overrides.items():
        if value is None:
            event.pop(key, None)
        else:
            event[key] = value
    return event
