"""Bounded, guarded HTTP client used for replays and regression runs."""

import json
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

import httpcore
import httpx

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.netguard import BlockedDestination, GuardedBackend

USER_AGENT = "Traceback-Replay/0.1"
MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_REDIRECTS = 3

# Captured credentials are never forwarded; transport headers are set by the client.
CREDENTIAL_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-csrf-token",
}
TRANSPORT_HEADERS = {
    "host",
    "content-length",
    "connection",
    "accept-encoding",
    "transfer-encoding",
    "te",
    "upgrade",
}

_slots = threading.BoundedSemaphore(get_settings().replay_max_concurrency)


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        name: value
        for name, value in headers.items()
        if name.lower() not in CREDENTIAL_HEADERS
        and name.lower() not in TRANSPORT_HEADERS
        and value != "[REDACTED]"
    }


class GuardedTransport(httpx.HTTPTransport):
    """httpx transport whose connections all pass through GuardedBackend.

    Proxies from the environment are deliberately ignored (trust_env=False):
    a proxy would make the guard check the proxy's address instead of the target's.
    """

    def __init__(self, allow_private: bool, timeout: float) -> None:
        super().__init__(trust_env=False, retries=0)
        self._pool = httpcore.ConnectionPool(
            ssl_context=httpx.create_ssl_context(trust_env=False),
            max_connections=4,
            network_backend=GuardedBackend(allow_private),
        )


@dataclass
class Outcome:
    url: str
    method: str
    sent_headers: dict[str, str]
    status: int | None = None
    response_headers: dict[str, str] | None = None
    body: Any = None
    body_truncated: bool = False
    duration_ms: int | None = None
    error: str | None = None


def build_url(base_url: str, path: str, query: dict[str, str | list[str]]) -> str:
    qs = urlencode(query, doseq=True)
    return f"{base_url.rstrip('/')}{path}{'?' + qs if qs else ''}"


def _origin(url: str) -> tuple[str, str, int | None]:
    p = urlsplit(url)
    return p.scheme, (p.hostname or "").lower(), p.port or (443 if p.scheme == "https" else 80)


def _decode(raw: bytes, content_type: str, truncated: bool) -> Any:
    text = raw.decode("utf-8", errors="replace")
    if "json" in content_type and not truncated:
        try:
            return json.loads(text)
        except ValueError:
            return text
    return text


def send(
    *,
    base_url: str,
    method: str,
    path: str,
    query: dict[str, str | list[str]],
    headers: dict[str, str],
    body: Any,
    allow_private: bool,
) -> Outcome:
    """Send one request to a registered target. Never raises for network failures."""
    settings = get_settings()
    url = build_url(base_url, path, query)
    sent = safe_headers(headers)
    sent["User-Agent"] = USER_AGENT
    sent["X-Traceback-Replay"] = "1"

    content: bytes | None = None
    if body is not None:
        has_non_json_type = any(
            k.lower() == "content-type" and "json" not in v for k, v in sent.items()
        )
        if isinstance(body, str) and has_non_json_type:
            content = body.encode()
        else:
            content = json.dumps(body).encode()
            if not any(k.lower() == "content-type" for k in sent):
                sent["Content-Type"] = "application/json"
        if len(content) > MAX_REQUEST_BODY_BYTES:
            raise AppError(413, "payload_too_large", "Replay bodies are limited to 64 KB.")

    if not _slots.acquire(blocking=False):
        raise AppError(429, "replay_busy", "Too many replays are running. Try again in a moment.")
    outcome = Outcome(url=url, method=method, sent_headers=sent)
    started = time.monotonic()
    try:
        timeout = settings.replay_timeout_seconds
        transport = GuardedTransport(allow_private, timeout)
        with httpx.Client(transport=transport, timeout=timeout, follow_redirects=False) as client:
            current, current_method, current_content = url, method, content
            for _ in range(MAX_REDIRECTS + 1):
                with client.stream(
                    current_method, current, headers=sent, content=current_content
                ) as resp:
                    if resp.is_redirect and "location" in resp.headers:
                        nxt = urljoin(current, resp.headers["location"])
                        # Redirects are only followed within the registered target's origin.
                        if _origin(nxt) != _origin(url):
                            outcome.error = (
                                f"Redirect to {nxt} not followed: it leaves the target's origin."
                            )
                            outcome.status = resp.status_code
                            outcome.response_headers = dict(resp.headers)
                            return outcome
                        if resp.status_code == 303 or (
                            resp.status_code in (301, 302) and current_method == "POST"
                        ):
                            current_method, current_content = "GET", None
                        current = nxt
                        continue
                    limit = settings.replay_max_response_bytes
                    buf = bytearray()
                    truncated = False
                    for chunk in resp.iter_bytes():
                        buf.extend(chunk)
                        if len(buf) > limit:
                            truncated = True
                            del buf[limit:]
                            break
                        if time.monotonic() - started > timeout:
                            raise httpx.ReadTimeout("response took too long")
                    outcome.status = resp.status_code
                    outcome.response_headers = dict(resp.headers)
                    outcome.body = _decode(
                        bytes(buf), resp.headers.get("content-type", ""), truncated
                    )
                    outcome.body_truncated = truncated
                    return outcome
            outcome.error = f"Stopped after {MAX_REDIRECTS} redirects."
            return outcome
    except BlockedDestination as exc:
        outcome.error = f"Destination blocked: {exc}."
    except httpx.TimeoutException:
        outcome.error = f"Timed out after {settings.replay_timeout_seconds:g} s."
    except (httpx.HTTPError, httpcore.ConnectError) as exc:
        cause = exc.__cause__ if isinstance(exc.__cause__, BlockedDestination) else None
        outcome.error = f"Destination blocked: {cause}." if cause else f"Request failed: {exc}"
    finally:
        outcome.duration_ms = round((time.monotonic() - started) * 1000)
        _slots.release()
    return outcome
