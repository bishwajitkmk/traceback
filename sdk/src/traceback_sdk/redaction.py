"""Redaction of sensitive keys in headers, query parameters and JSON bodies.

Mirrors the server rule in ``docs/contracts.md``: a key is sensitive when its
lower-cased name *contains* one of :data:`DEFAULT_SENSITIVE_KEYS`, or *equals*
(case-insensitively) one of the user-configured extra fields.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

REDACTED = "[REDACTED]"

DEFAULT_SENSITIVE_KEYS: tuple[str, ...] = (
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "x-api-key",
    "session",
    "csrf",
    "credit_card",
    "card_number",
    "cvv",
    "ssn",
)


class Redactor:
    """Replaces values of sensitive keys with ``"[REDACTED]"``, recursively."""

    def __init__(self, extra_fields: Iterable[str] = ()) -> None:
        self._contains = DEFAULT_SENSITIVE_KEYS
        self._exact = frozenset(f.lower() for f in extra_fields if f)

    def is_sensitive(self, key: str) -> bool:
        lower = key.lower()
        return lower in self._exact or any(s in lower for s in self._contains)

    def redact(self, value: Any) -> Any:
        """Return a redacted copy of ``value`` (dicts and lists are walked recursively)."""
        if isinstance(value, dict):
            return {
                k: (REDACTED if isinstance(k, str) and self.is_sensitive(k) else self.redact(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self.redact(v) for v in value]
        return value
