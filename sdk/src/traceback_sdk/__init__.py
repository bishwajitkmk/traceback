"""Traceback Python SDK.

The import name is ``traceback_sdk`` (not ``traceback``) to avoid shadowing
the standard-library ``traceback`` module.
"""

__version__ = "0.1.0"

from .client import Traceback, TracebackMiddleware  # noqa: E402
from .redaction import DEFAULT_SENSITIVE_KEYS, REDACTED  # noqa: E402

__all__ = ["DEFAULT_SENSITIVE_KEYS", "REDACTED", "Traceback", "TracebackMiddleware", "__version__"]
