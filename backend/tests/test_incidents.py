from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.helpers import event_payload


def seed(client: TestClient, key: str) -> None:
    now = datetime.now(UTC)
    specs = [
        ("ZeroDivisionError", "/checkout", "division by zero", 0, 3),
        ("KeyError", "/orders/{order_id}", "'ord_missing'", 1, 2),
        ("TypeError", "/reports/daily", "unsupported operand 100%_off", 3, 1),
        ("ValueError", "/old", "ancient", 40, 1),
    ]
    for etype, route, message, days_ago, count in specs:
        for n in range(count):
            e = event_payload(occurred_at=(now - timedelta(days=days_ago, minutes=n)).isoformat())
            e["request"]["route"] = route
            e["exception"].update(type=etype, message=message)
            r = client.post(
                "/api/v1/ingest/events", json=e, headers={"Authorization": f"Bearer {key}"}
            )
            assert r.status_code == 202


def test_list_filter_search_and_paginate(
    user_client: TestClient, project: dict, api_key: str
) -> None:
    seed(user_client, api_key)
    url = f"/api/v1/projects/{project['id']}/incidents"
    page = user_client.get(url).json()
    assert page["total"] == 4
    assert [i["error_type"] for i in page["items"]] == [
        "ZeroDivisionError",
        "KeyError",
        "TypeError",
        "ValueError",
    ]

    assert user_client.get(url, params={"error_type": "KeyError"}).json()["total"] == 1
    assert (
        user_client.get(url, params={"q": "ORDERS"}).json()["total"] == 1
    )  # route, case-insensitive
    assert user_client.get(url, params={"q": "zero"}).json()["total"] == 1  # message
    # LIKE wildcards in the search text are literal, not patterns.
    assert user_client.get(url, params={"q": "100%_off"}).json()["total"] == 1
    assert user_client.get(url, params={"q": "%"}).json()["total"] == 1
    assert user_client.get(url, params={"since_days": 7}).json()["total"] == 3

    p1 = user_client.get(url, params={"page_size": 3}).json()
    p2 = user_client.get(url, params={"page_size": 3, "page": 2}).json()
    assert len(p1["items"]) == 3 and len(p2["items"]) == 1
    assert {i["id"] for i in p1["items"]}.isdisjoint({i["id"] for i in p2["items"]})

    bad = user_client.get(url, params={"status": "ignored", "page_size": 1000})
    assert bad.status_code == 422


def test_resolve_keeps_history(user_client: TestClient, project: dict, api_key: str) -> None:
    seed(user_client, api_key)
    base = f"/api/v1/projects/{project['id']}/incidents"
    incident = user_client.get(base, params={"error_type": "ZeroDivisionError"}).json()["items"][0]
    resolved = user_client.patch(f"{base}/{incident['id']}", json={"status": "resolved"}).json()
    assert resolved["status"] == "resolved" and resolved["resolved_at"]
    events = user_client.get(f"{base}/{incident['id']}/events").json()
    assert events["total"] == 3  # history preserved
    assert user_client.get(base, params={"status": "open"}).json()["total"] == 3
    reopened = user_client.patch(f"{base}/{incident['id']}", json={"status": "open"}).json()
    assert reopened["resolved_at"] is None


def test_event_detail_shapes(user_client: TestClient, project: dict, api_key: str) -> None:
    seed(user_client, api_key)
    base = f"/api/v1/projects/{project['id']}"
    incident = user_client.get(f"{base}/incidents", params={"error_type": "KeyError"}).json()[
        "items"
    ][0]
    events = user_client.get(f"{base}/incidents/{incident['id']}/events").json()["items"]
    assert events[0]["occurred_at"] > events[1]["occurred_at"]  # newest first
    event = user_client.get(f"{base}/events/{events[0]['id']}").json()
    assert event["exception_data"]["frames"][-1]["function"] == "unit_price"
    assert event["request_method"] == "POST" and event["correlation_id"] == "req_abc123"
    assert event["occurred_at"].endswith("Z")
    assert user_client.get(f"{base}/events/{incident['id']}").status_code == 404


def test_stats_come_from_stored_data(user_client: TestClient, project: dict, api_key: str) -> None:
    seed(user_client, api_key)
    stats = user_client.get(f"/api/v1/projects/{project['id']}/stats", params={"days": 14}).json()
    assert stats["days"] == 14 and len(stats["daily"]) == 14
    assert stats["open_incidents"] == 4
    assert stats["events_in_range"] == 6  # the 40-day-old event is outside the range
    assert sum(d["events"] for d in stats["daily"]) == 6
    assert stats["daily"][-1]["date"] == datetime.now(UTC).date().isoformat()
    assert stats["new_incidents_in_range"] == 3
    assert [t["events"] for t in stats["top_incidents"]] == [3, 2, 1]
    assert stats["top_incidents"][0]["incident"]["error_type"] == "ZeroDivisionError"
    assert stats["regression"] == {"total": 0, "passing": 0, "failing": 0, "never_run": 0}
    assert (
        user_client.get(f"/api/v1/projects/{project['id']}/stats", params={"days": 0}).status_code
        == 422
    )
