"""Create (or reset) the synthetic demo account (PRD §16 week 4, §19 synthetic data).

    python -m app.jobs.seed_demo [--target http://127.0.0.1:9101]

Signs in as demo@traceback.dev / traceback-demo. Events go through the real
ingestion service, so redaction, fingerprinting and grouping are exercised
exactly as for SDK traffic. Prints the project's ingestion key so the sample
app can send real failures into the same project.
"""

import argparse
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Incident, Project, RegressionCase, ReplayTarget, User
from app.schemas.cases import CiRunReport
from app.schemas.ingest import IngestEvent
from app.services import executions, projects
from app.services.ingestion import ingest

DEMO_EMAIL = "demo@traceback.dev"
DEMO_PASSWORD = "traceback-demo"  # noqa: S105 — public demo credentials, synthetic data only

SPECS: list[dict[str, Any]] = [
    {
        "type": "ZeroDivisionError",
        "message": "division by zero",
        "method": "POST",
        "route": "/checkout",
        "path": "/checkout",
        "status": 500,
        "count": 47,
        "span": 6,
        "resolved": False,
        "body": {
            "cart_id": "cart_19f2",
            "quantity": 0,
            "coupon": None,
            "card_number": "4111111111111111",
        },
        "frames": [
            ("starlette/routing.py", 74, "app", "response = await func(request)", False),
            (
                "app.py",
                41,
                "create_checkout",
                "price = pricing.unit_price(cart_total, body.quantity)",
                True,
            ),
            ("pricing.py", 9, "unit_price", "return round(total / quantity, 2)", True),
        ],
    },
    {
        "type": "KeyError",
        "message": "'ord_missing'",
        "method": "GET",
        "route": "/orders/{order_id}",
        "path": "/orders/ord_missing",
        "status": 500,
        "count": 12,
        "span": 9,
        "resolved": False,
        "query": {"expand": ["items", "customer"]},
        "frames": [("app.py", 58, "get_order", "order = ORDERS[order_id]", True)],
    },
    {
        "type": "TypeError",
        "message": "unsupported operand type(s) for +: 'int' and 'str'",
        "method": "GET",
        "route": "/reports/daily",
        "path": "/reports/daily",
        "status": 500,
        "count": 21,
        "span": 3,
        "resolved": False,
        "query": {"date": "2026-10-13"},
        "frames": [("reports.py", 52, "build_report", "revenue = sum(amounts) + adjustment", True)],
    },
    {
        "type": "httpx.ReadTimeout",
        "message": "timed out",
        "method": "POST",
        "route": "/payments/charge",
        "path": "/payments/charge",
        "status": 504,
        "count": 8,
        "span": 12,
        "resolved": False,
        "body_captured": False,
        "frames": [
            ("payments.py", 64, "charge", "resp = await client.post(PSP_URL, json=payload)", True),
            ("httpx/_client.py", 1617, "send", "response = await self._send_handling_auth(", False),
        ],
    },
    {
        "type": None,
        "message": None,
        "method": "GET",
        "route": "/inventory/{sku}",
        "path": "/inventory/TB-001",
        "status": 503,
        "count": 5,
        "span": 2,
        "resolved": False,
        "frames": [],
    },
    {
        "type": "AttributeError",
        "message": "'NoneType' object has no attribute 'currency'",
        "method": "GET",
        "route": "/cart",
        "path": "/cart",
        "status": 500,
        "count": 16,
        "span": 11,
        "resolved": True,
        "frames": [("cart.py", 30, "from_cart", "currency=cart.pricing.currency,", True)],
    },
]


def _event(spec: dict[str, Any], occurred: datetime, rand: random.Random) -> IngestEvent:
    correlation = f"req_{rand.getrandbits(48):012x}"
    captured = spec.get("body_captured", spec["method"] != "GET")
    payload: dict[str, Any] = {
        "event_id": str(uuid.UUID(int=rand.getrandbits(128), version=4)),
        "event_type": "exception" if spec["type"] else "http_error",
        "occurred_at": occurred.isoformat(),
        "environment": "production",
        "release": "2.14.0" if rand.random() > 0.3 else "2.13.2",
        "correlation_id": correlation,
        "duration_ms": 10_000 + rand.randint(0, 50)
        if spec["status"] == 504
        else rand.randint(18, 160),
        "request": {
            "method": spec["method"],
            "route": spec["route"],
            "path": spec["path"],
            "query": spec.get("query", {}),
            "headers": {
                "authorization": "Bearer live-token",
                "cookie": "session=abc",
                "content-type": "application/json",
                "user-agent": "checkout-web/2.14.0",
                "x-request-id": correlation,
            },
            "body_captured": captured,
            "body": spec.get("body") if captured else None,
            "body_truncated": False,
        },
        "response": {
            "status": spec["status"],
            "headers": {"content-type": "application/json", "x-correlation-id": correlation},
            "body": {
                "detail": "Internal Server Error" if spec["status"] == 500 else "Upstream error"
            },
        },
        "sdk": {"name": "traceback-seed", "version": "0.1.0"},
    }
    if spec["type"]:
        payload["exception"] = {
            "type": spec["type"],
            "message": spec["message"],
            "frames": [
                {"filename": f, "lineno": ln, "function": fn, "context_line": ctx, "in_app": app}
                for f, ln, fn, ctx, app in spec["frames"]
            ],
        }
    return IngestEvent.model_validate(payload)


def seed(db: Session, target_url: str) -> tuple[Project, str]:
    existing = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if existing is not None:
        db.execute(delete(User).where(User.id == existing.id))  # cascades to all demo data
        db.flush()
    user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
    db.add(user)
    db.flush()
    project = projects.create(db, user, "Checkout API")
    project.redaction_rules = [{"field": "card_number"}]
    key = projects.create_key(db, project).key

    rand = random.Random(42)  # noqa: S311 — deterministic synthetic demo data
    now = datetime.now(UTC)
    for spec in SPECS:
        times = sorted(
            now
            - timedelta(
                days=(0.35 + rand.random() * 0.65 if spec["resolved"] else rand.random() ** 1.6)
                * spec["span"]
            )
            for _ in range(spec["count"])
        )
        for t in times:
            ingest(db, project, _event(spec, t, rand))
        if spec["resolved"]:
            incident = db.scalar(
                select(Incident).where(
                    Incident.project_id == project.id, Incident.error_type == spec["type"]
                )
            )
            assert incident is not None
            incident.status, incident.resolved_at = "resolved", times[-1] + timedelta(hours=2)

    db.add_all(
        [
            ReplayTarget(
                project_id=project.id,
                name="Sample app (local)",
                base_url=target_url,
                environment="local",
            ),
            ReplayTarget(
                project_id=project.id,
                name="Staging",
                base_url="https://staging.checkout.example.com",
                environment="staging",
                enabled=False,
            ),
        ]
    )
    case = RegressionCase(
        project_id=project.id,
        name="Empty cart returns currency",
        description="Guards the AttributeError when a cart had no pricing record.",
        request_definition={
            "method": "GET",
            "path": "/cart",
            "query": {},
            "headers": {"accept": "application/json"},
            "body": None,
        },
        assertion_definition={
            "expected_status": 200,
            "assertions": [{"type": "json_path_equals", "path": "$.currency", "expected": "USD"}],
        },
        created_by=user.id,
    )
    db.add(case)
    db.flush()
    for days_ago in (4, 2, 0.3):
        run = executions.record_cli_run(
            db,
            project,
            case,
            CiRunReport(
                target_url=target_url,
                duration_ms=31,
                response={
                    "status": 200,
                    "headers": {"content-type": "application/json"},
                    "body": {"items": [], "currency": "USD", "total": 0},
                },
            ),
        )
        run.started_at = now - timedelta(days=days_ago)
        run.completed_at = run.started_at + timedelta(milliseconds=31)
    return project, key


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--target", default="http://127.0.0.1:9101", help="Base URL of the sample app"
    )
    args = parser.parse_args()
    with SessionLocal() as db:
        project, key = seed(db, args.target)
        db.commit()
    print(f"Demo account: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"Project:      {project.name} ({project.id})")
    print(f"Ingestion key (shown once): {key}")


if __name__ == "__main__":
    main()
