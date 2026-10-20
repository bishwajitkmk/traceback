"""Server-side redaction, applied before anything is persisted (PRD §12).

The SDK redacts too, but the server never trusts that it did.
"""

from collections.abc import Iterable
from typing import Any

REDACTED = "[REDACTED]"

# A key is sensitive when its lower-cased name CONTAINS any of these.
BUILT_IN_FRAGMENTS: tuple[str, ...] = (
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "session",
    "csrf",
    "credit_card",
    "card_number",
    "cvv",
    "ssn",
)

MAX_DEPTH = 32


class Redactor:
    def __init__(self, extra_fields: Iterable[str] = ()) -> None:
        # Project rules match exact field names, case-insensitively.
        self.exact = {f.strip().lower() for f in extra_fields if f.strip()}

    def is_sensitive(self, key: str) -> bool:
        lower = key.lower()
        return lower in self.exact or any(fragment in lower for fragment in BUILT_IN_FRAGMENTS)

    def redact(self, value: Any, depth: int = 0) -> Any:
        """Return a copy of `value` with sensitive keys' values replaced, recursively."""
        if depth > MAX_DEPTH:
            return REDACTED  # pathological nesting: refuse rather than keep unchecked data
        if isinstance(value, dict):
            return {
                k: (
                    REDACTED
                    if self.is_sensitive(str(k)) and v is not None
                    else self.redact(v, depth + 1)
                )
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self.redact(v, depth + 1) for v in value]
        return value
