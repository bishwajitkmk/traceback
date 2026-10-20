from __future__ import annotations

import pytest

from traceback_sdk.assertions import evaluate_assertions, json_equal
from traceback_sdk.jsonpath import get_path, parse_path


@pytest.mark.parametrize(
    "path,tokens",
    [
        ("$", []),
        ("", []),
        ("$.error.code", ["error", "code"]),
        ("error.code", ["error", "code"]),
        ('$["weird key"][0]', ["weird key", 0]),
        ("items[2].sku", ["items", 2, "sku"]),
        ('$["a\\"b"]', ['a"b']),
        ("$.x-y", ["x-y"]),
        ("  $.a  ", ["a"]),
    ],
)
def test_parse_path(path, tokens):
    assert parse_path(path) == tokens


@pytest.mark.parametrize("path", ["$..a", "$.[0]", "$[-1]", "$.1a", "$['a']", "a b"])
def test_parse_path_invalid(path):
    assert parse_path(path) is None


def test_get_path():
    body = {"error": {"code": "x", "nil": None}, "items": [{"sku": "a"}, {"sku": "b"}]}
    assert get_path(body, "$") == (True, body)
    assert get_path(body, "error.code") == (True, "x")
    assert get_path(body, "$.error.nil") == (True, None)
    assert get_path(body, "$.items[1].sku") == (True, "b")
    assert get_path(body, "$.items[2]").found is False
    assert get_path(body, "$.items.sku").found is False
    assert get_path(body, "$.error[0]").found is False
    assert get_path(body, "$.missing").found is False
    assert get_path("text", "$.a").found is False
    assert get_path(body, "$..bad").found is False


def test_json_equal():
    assert json_equal({"a": [1, {"b": None}]}, {"a": [1, {"b": None}]})
    assert json_equal({"a": 1, "b": 2}, {"b": 2, "a": 1})
    assert json_equal(1, 1.0)
    assert not json_equal(1, True)
    assert not json_equal(0, False)
    assert not json_equal("1", 1)
    assert not json_equal([1, 2], [2, 1])
    assert not json_equal(None, {})


def test_evaluate_assertions():
    definition = {
        "expected_status": 422,
        "assertions": [
            {"type": "json_path_equals", "path": "$.error.code", "expected": "invalid_quantity"},
            {"type": "json_path_exists", "path": "$.error.message"},
            {"type": "json_path_exists", "path": "$.error.details"},
            {"type": "body_contains", "expected": '"code":"invalid_quantity"'},
            {"type": "json_path_equals", "path": "$.missing", "expected": None},
        ],
    }
    response = {
        "status": 422,
        "headers": {},
        "body": {"error": {"code": "invalid_quantity", "message": "m", "details": None}},
        "body_truncated": False,
    }
    outcome, results = evaluate_assertions(definition, response)
    assert outcome == "failed"
    assert [r["description"] for r in results] == [
        "status is 422",
        '$.error.code equals "invalid_quantity"',
        "$.error.message exists",
        "$.error.details exists",
        'body contains "\\"code\\":\\"invalid_quantity\\""',
        "$.missing equals null",
    ]
    assert [r["passed"] for r in results] == [True, True, True, True, True, False]
    assert results[0] == {
        "description": "status is 422",
        "passed": True,
        "expected": 422,
        "actual": 422,
    }
    assert results[2]["expected"] is True and results[2]["actual"] is True
    assert results[5]["actual"] is None


def test_status_first_and_text_body():
    outcome, results = evaluate_assertions(
        {"expected_status": 200, "assertions": [{"type": "body_contains", "expected": "ok"}]},
        {"status": 500, "headers": {}, "body": "not ok", "body_truncated": False},
    )
    assert outcome == "failed"
    assert results[0]["passed"] is False and results[0]["actual"] == 500
    assert results[1]["passed"] is True


def test_all_pass():
    outcome, _ = evaluate_assertions(
        {"expected_status": 404, "assertions": []},
        {"status": 404, "headers": {}, "body": None, "body_truncated": False},
    )
    assert outcome == "passed"
