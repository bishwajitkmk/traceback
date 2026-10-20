"""The ``Traceback`` integration object and its pure-ASGI middleware."""

from __future__ import annotations

import atexit
import fnmatch
import json
import logging
import os
import re
import time
import uuid
import weakref
from collections.abc import Awaitable, Callable, Iterable, MutableMapping, Sequence
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode

import httpx

from . import __version__
from .frames import FrameClassifier, serialize_exception
from .redaction import Redactor
from .transport import BackgroundWorker, EventSender

logger = logging.getLogger("traceback_sdk")

DEFAULT_ENDPOINT = "http://localhost:8100/api/v1"
SDK_INFO = {"name": "traceback-sdk", "version": __version__}

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_CORRELATION_ID_RE = re.compile(r"^[\x21-\x7e]{1,128}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _new_correlation_id() -> str:
    return "req_" + uuid.uuid4().hex[:12]


def _decode_headers(raw: Iterable[tuple[bytes, bytes]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, value in raw:
        key = name.decode("latin-1").lower()
        text = value.decode("latin-1")
        out[key] = f"{out[key]}, {text}" if key in out else text
    return out


def _parse_query(query_string: bytes) -> dict[str, str | list[str]]:
    out: dict[str, str | list[str]] = {}
    text = query_string.decode("utf-8", errors="replace")
    for key, value in parse_qsl(text, keep_blank_values=True):
        existing = out.get(key)
        if existing is None:
            out[key] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            out[key] = [existing, value]
    return out


def _decode_body(data: bytes, truncated: bool, content_type: str, redactor: Redactor) -> Any:
    """JSON when it parses, a (redacted) form string for urlencoded bodies, else text."""
    if not data:
        return None
    text = data.decode("utf-8", errors="replace")
    if not truncated:
        try:
            return redactor.redact(json.loads(text))
        except ValueError:
            pass
    if "application/x-www-form-urlencoded" in content_type:
        pairs = parse_qsl(text, keep_blank_values=True)
        if pairs:
            return urlencode(
                [(k, "[REDACTED]" if redactor.is_sensitive(k) else v) for k, v in pairs]
            )
    return text


class _BoundedBuffer:
    def __init__(self, limit: int) -> None:
        self.limit = max(0, limit)
        self.parts: list[bytes] = []
        self.size = 0
        self.truncated = False

    def add(self, chunk: bytes) -> None:
        if not chunk:
            return
        room = self.limit - self.size
        if room <= 0:
            self.truncated = True
            return
        if len(chunk) > room:
            self.truncated = True
            chunk = chunk[:room]
        self.parts.append(chunk)
        self.size += len(chunk)

    def value(self) -> bytes:
        return b"".join(self.parts)


class Traceback:
    """Attach Traceback failure capture to a FastAPI / Starlette application.

    >>> Traceback(app, api_key=os.environ["TRACEBACK_API_KEY"], environment="production")
    """

    def __init__(
        self,
        app: Any,
        api_key: str,
        endpoint: str | None = None,
        environment: str | None = None,
        release: str | None = None,
        enabled: bool = True,
        environments: Sequence[str] | None = None,
        capture_status_min: int = 500,
        capture_body: bool = True,
        max_body_bytes: int = 16384,
        ignore_routes: Sequence[str] = (),
        redact_fields: Sequence[str] = (),
        timeout: float = 2.0,
        max_retries: int = 3,
        queue_size: int = 1000,
        in_app_include: Sequence[str] | None = None,
        transport: httpx.BaseTransport | None = None,
        backoff_base: float = 0.5,
        max_backoff: float = 10.0,
    ) -> None:
        self.app = app
        self.endpoint = endpoint or os.environ.get("TRACEBACK_ENDPOINT") or DEFAULT_ENDPOINT
        self.environment = environment
        self.release = release
        self.capture_status_min = int(capture_status_min)
        self.capture_body = bool(capture_body)
        self.max_body_bytes = max(0, int(max_body_bytes))
        self.ignore_routes = list(ignore_routes or ())
        self.redactor = Redactor(redact_fields or ())
        self.classifier = FrameClassifier(in_app_include)
        self._worker: BackgroundWorker | None = None

        self.enabled = bool(enabled)
        if self.enabled and environments is not None and environment not in environments:
            logger.info(
                "traceback: disabled because environment %r is not in %r",
                environment,
                list(environments),
            )
            self.enabled = False
        if self.enabled and not api_key:
            logger.warning("traceback: no api_key given; capture is disabled")
            self.enabled = False
        if not self.enabled:
            return

        build = getattr(app, "build_middleware_stack", None)
        if build is None or not callable(build):
            raise TypeError(
                "Traceback(app) needs a Starlette/FastAPI app; "
                "wrap other ASGI apps with TracebackMiddleware(app, client=...)"
            )
        if getattr(app, "middleware_stack", None) is not None:
            raise RuntimeError("Traceback(app) must be called before the application starts")

        sender = EventSender(
            api_key,
            self.endpoint,
            timeout=timeout,
            max_retries=max_retries,
            backoff_base=backoff_base,
            max_backoff=max_backoff,
            transport=transport,
        )
        self._worker = BackgroundWorker(sender, queue_size=queue_size)

        self._attach(app)

        ref = weakref.ref(self)

        def _atexit_close() -> None:
            obj = ref()
            if obj is not None:
                obj.close()

        atexit.register(_atexit_close)

    def _attach(self, app: Any) -> None:
        """Wrap the app's whole middleware stack, outside Starlette's ServerErrorMiddleware.

        Being outermost lets the SDK observe the 500 that the server error handler
        sends for an unhandled exception (and tag it with ``x-correlation-id``),
        while the exception itself still propagates to the server unchanged.
        """
        original_build = app.build_middleware_stack

        def build_middleware_stack() -> ASGIApp:
            return TracebackMiddleware(original_build(), client=self)

        app.build_middleware_stack = build_middleware_stack

    # ------------------------------------------------------------------ public API

    def flush(self, timeout: float = 2.0) -> bool:
        """Block until queued events are delivered (or ``timeout``). True if drained."""
        if self._worker is None:
            return True
        return self._worker.flush(timeout)

    def close(self, timeout: float = 2.0) -> None:
        """Drain the queue (up to ``timeout``) and stop the delivery thread."""
        if self._worker is not None:
            self._worker.close(timeout)

    @property
    def dropped_events(self) -> int:
        return self._worker.dropped if self._worker else 0

    def capture_event(self, event: dict[str, Any]) -> bool:
        """Queue an already-built event (redaction is the caller's job). Never raises."""
        if self._worker is None:
            return False
        try:
            return self._worker.submit(event)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("traceback: could not queue event: %s", exc)
            return False

    # ------------------------------------------------------------------ helpers

    def is_ignored(self, *candidates: str | None) -> bool:
        for value in candidates:
            if not value:
                continue
            for pattern in self.ignore_routes:
                if value == pattern or fnmatch.fnmatchcase(value, pattern):
                    return True
        return False

    def build_event(
        self,
        *,
        scope: Scope,
        correlation_id: str,
        occurred_at: str,
        duration_ms: int,
        request_body: _BoundedBuffer | None,
        status: int | None,
        response_headers: dict[str, str],
        response_body: _BoundedBuffer | None,
        exc: BaseException | None,
    ) -> dict[str, Any]:
        r = self.redactor
        headers = _decode_headers(scope.get("headers") or [])
        route_obj = scope.get("route")
        route_path = getattr(route_obj, "path", None)
        path = scope.get("path") or "/"
        route = route_path if isinstance(route_path, str) and route_path else path

        request: dict[str, Any] = {
            "method": scope.get("method", "GET"),
            "route": route,
            "path": path,
            "query": r.redact(_parse_query(scope.get("query_string") or b"")),
            "headers": r.redact(headers),
            "body_captured": request_body is not None,
            "body": None,
            "body_truncated": False,
        }
        if request_body is not None:
            request["body"] = _decode_body(
                request_body.value(),
                request_body.truncated,
                headers.get("content-type", ""),
                r,
            )
            request["body_truncated"] = request_body.truncated

        event: dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "event_type": "exception" if exc is not None else "http_error",
            "occurred_at": occurred_at,
            "correlation_id": correlation_id,
            "duration_ms": max(0, duration_ms),
            "request": request,
            "sdk": dict(SDK_INFO),
        }
        if self.environment:
            event["environment"] = self.environment[:64]
        if self.release:
            event["release"] = self.release[:128]

        if status is not None:
            body = None
            if response_body is not None:
                body = _decode_body(
                    response_body.value(),
                    response_body.truncated,
                    response_headers.get("content-type", ""),
                    r,
                )
            event["response"] = {
                "status": status,
                "headers": r.redact(response_headers),
                "body": body,
            }
        elif exc is not None:
            # No response was started (non-Starlette stack); the server will answer 500.
            event["response"] = {"status": 500, "headers": {}, "body": None}

        if exc is not None:
            event["exception"] = serialize_exception(exc, self.classifier)
        return event


class TracebackMiddleware:
    """Pure ASGI middleware. Observes requests; never alters what the app does."""

    def __init__(self, app: ASGIApp, client: Traceback) -> None:
        self.app = app
        self.client = client

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(scope, receive, send)
            return
        if scope["type"] != "http" or not self.client.enabled:
            await self.app(scope, receive, send)
            return
        if self.client.is_ignored(scope.get("path")):
            await self.app(scope, receive, send)
            return
        await self._http(scope, receive, send)

    async def _lifespan(self, scope: Scope, receive: Receive, send: Send) -> None:
        client = self.client

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "lifespan.shutdown.complete":
                try:
                    import anyio.to_thread

                    await anyio.to_thread.run_sync(client.flush)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("traceback: error while flushing on shutdown: %s", exc)
            await send(message)

        await self.app(scope, receive, send_wrapper)

    async def _http(self, scope: Scope, receive: Receive, send: Send) -> None:
        client = self.client
        started = time.perf_counter()
        occurred_at = _now_iso()

        try:
            headers = _decode_headers(scope.get("headers") or [])
            incoming = headers.get("x-correlation-id") or headers.get("x-request-id") or ""
            incoming = incoming.strip()
            correlation_id = (
                incoming if _CORRELATION_ID_RE.match(incoming) else _new_correlation_id()
            )
        except Exception:  # pragma: no cover - defensive
            correlation_id = _new_correlation_id()

        # Pre-read up to max_body_bytes so the body is available even when the app
        # fails before reading it; the exact same messages are replayed to the app.
        request_buffer: _BoundedBuffer | None = None
        replay: list[Message] = []
        if client.capture_body:
            request_buffer = _BoundedBuffer(client.max_body_bytes)
            while True:
                message = await receive()
                replay.append(message)
                if message.get("type") != "http.request":
                    break
                request_buffer.add(message.get("body", b""))
                if not message.get("more_body", False):
                    break
                if request_buffer.size >= client.max_body_bytes:
                    request_buffer.truncated = True  # more body follows that we will not keep
                    break

        async def receive_wrapper() -> Message:
            if replay:
                return replay.pop(0)
            return await receive()

        status: int | None = None
        response_headers: dict[str, str] = {}
        response_buffer: _BoundedBuffer | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status, response_headers, response_buffer
            mtype = message.get("type")
            if mtype == "http.response.start":
                try:
                    status = int(message.get("status", 200))
                    raw = list(message.get("headers") or [])
                    if not any(n.lower() == b"x-correlation-id" for n, _ in raw):
                        raw.append((b"x-correlation-id", correlation_id.encode("latin-1")))
                        message = {**message, "headers": raw}
                    response_headers = _decode_headers(raw)
                    if status >= client.capture_status_min and client.capture_body:
                        response_buffer = _BoundedBuffer(client.max_body_bytes)
                except Exception:  # pragma: no cover - never break the response
                    pass
            elif mtype == "http.response.body" and response_buffer is not None:
                response_buffer.add(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except BaseException as exc:
            if isinstance(exc, Exception):
                self._report(
                    scope,
                    correlation_id,
                    occurred_at,
                    started,
                    request_buffer,
                    status,
                    response_headers,
                    response_buffer,
                    exc,
                )
            raise
        else:
            if status is not None and status >= client.capture_status_min:
                self._report(
                    scope,
                    correlation_id,
                    occurred_at,
                    started,
                    request_buffer,
                    status,
                    response_headers,
                    response_buffer,
                    None,
                )

    def _report(
        self,
        scope: Scope,
        correlation_id: str,
        occurred_at: str,
        started: float,
        request_buffer: _BoundedBuffer | None,
        status: int | None,
        response_headers: dict[str, str],
        response_buffer: _BoundedBuffer | None,
        exc: BaseException | None,
    ) -> None:
        client = self.client
        try:
            route_obj = scope.get("route")
            if client.is_ignored(getattr(route_obj, "path", None)):
                return
            event = client.build_event(
                scope=scope,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
                duration_ms=int((time.perf_counter() - started) * 1000),
                request_body=request_buffer,
                status=status,
                response_headers=response_headers,
                response_body=response_buffer,
                exc=exc,
            )
            client.capture_event(event)
        except Exception as err:  # telemetry must never affect the app
            logger.warning("traceback: failed to build event: %s", err)
