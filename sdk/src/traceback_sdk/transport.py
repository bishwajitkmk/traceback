"""Background delivery of events to the ingestion API.

Events are put on a bounded in-memory queue and sent by one daemon thread, so
the request path never waits on the network. Delivery failures are logged at
WARNING and never raised.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from . import __version__

logger = logging.getLogger("traceback_sdk")

USER_AGENT = f"traceback-sdk/{__version__}"

_STOP = object()


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


class EventSender:
    """Synchronous single-event sender with bounded retries (used by the worker and CLI)."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        *,
        timeout: float = 2.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        max_backoff: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], Any] = time.sleep,
    ) -> None:
        self.url = endpoint.rstrip("/") + "/ingest/events"
        self.max_attempts = max(1, int(max_retries))
        self.backoff_base = max(0.0, backoff_base)
        self.max_backoff = max(0.0, max_backoff)
        self.sleep = sleep
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )

    def close(self) -> None:
        self._client.close()

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, self.max_backoff)
        return min(self.backoff_base * (2 ** (attempt - 1)), self.max_backoff)

    def send(self, event: dict[str, Any]) -> httpx.Response | None:
        """Send one event. Returns the final response, or ``None`` if every attempt failed.

        Retries (reusing the same ``event_id``) only on network errors, 5xx and 429.
        """
        event_id = event.get("event_id")
        try:
            payload = json.dumps(event, default=str, ensure_ascii=False).encode("utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("traceback: could not serialize event %s: %s", event_id, exc)
            return None
        last: httpx.Response | None = None
        for attempt in range(1, self.max_attempts + 1):
            retry_after: float | None = None
            try:
                response = self._client.post(self.url, content=payload)
            except httpx.HTTPError as exc:
                reason = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                logger.warning(
                    "traceback: delivery of event %s failed (attempt %d/%d): %s",
                    event_id,
                    attempt,
                    self.max_attempts,
                    reason,
                )
            else:
                last = response
                status = response.status_code
                if status < 400:
                    return response
                if status != 429 and status < 500:
                    logger.warning(
                        "traceback: event %s rejected with HTTP %d (%s); not retrying",
                        event_id,
                        status,
                        _error_code(response),
                    )
                    return response
                retry_after = _retry_after_seconds(response) if status == 429 else None
                logger.warning(
                    "traceback: delivery of event %s got HTTP %d (attempt %d/%d)",
                    event_id,
                    status,
                    attempt,
                    self.max_attempts,
                )
            if attempt < self.max_attempts:
                self.sleep(self._delay(attempt, retry_after))
        logger.warning(
            "traceback: giving up on event %s after %d attempts", event_id, self.max_attempts
        )
        return last if last is not None and last.status_code < 400 else None


def _error_code(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"]["code"])
    except Exception:
        return "no error code"


class BackgroundWorker:
    """Bounded queue drained by a daemon thread."""

    def __init__(self, sender: EventSender, queue_size: int = 1000) -> None:
        self._sender = sender
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=max(1, int(queue_size)))
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._stopping = threading.Event()
        self.dropped = 0
        # Backoff waits are interruptible so close() does not hang on a sleeping retry.
        sender.sleep = self._interruptible_sleep

    def _interruptible_sleep(self, seconds: float) -> None:
        if seconds > 0:
            self._stopping.wait(seconds)

    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run, name="traceback-sdk-worker", daemon=True
                )
                self._thread.start()

    def submit(self, event: dict[str, Any]) -> bool:
        """Enqueue without blocking. Returns False (and drops the event) when full or closed."""
        if self._closed:
            return False
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 100 == 0:
                logger.warning(
                    "traceback: event queue full, dropped %d event(s) so far", self.dropped
                )
            return False
        try:
            self._ensure_thread()
        except Exception as exc:  # pragma: no cover - thread start failure
            logger.warning("traceback: could not start delivery thread: %s", exc)
        return True

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _STOP:
                    return
                try:
                    self._sender.send(item)
                except Exception as exc:  # never let the worker die
                    logger.warning("traceback: unexpected delivery error: %s", exc)
            finally:
                self._queue.task_done()

    def pending(self) -> int:
        return self._queue.unfinished_tasks

    def flush(self, timeout: float = 2.0) -> bool:
        """Wait until every queued event was handled. Returns True if the queue drained."""
        deadline = time.monotonic() + max(0.0, timeout)
        while self._queue.unfinished_tasks > 0:
            if self._thread is None or not self._thread.is_alive():
                return False
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.005)
        return True

    def close(self, timeout: float = 2.0) -> None:
        if self._closed:
            return
        drained = self.flush(timeout)
        self._closed = True
        self._stopping.set()
        if self._thread is not None and self._thread.is_alive():
            try:
                self._queue.put_nowait(_STOP)
            except queue.Full:
                pass
            self._thread.join(timeout=0.5 if drained else 0.1)
        left = self._queue.qsize()
        if left and not drained:
            logger.warning("traceback: %d event(s) not delivered before shutdown", left)
        self._sender.close()
