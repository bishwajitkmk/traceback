"""Turn an exception into the contract's ``exception`` object."""

from __future__ import annotations

import builtins
import linecache
import os
import site
import sys
import sysconfig
import traceback
from collections.abc import Sequence
from typing import Any

MAX_FRAMES = 100
MAX_MESSAGE_CHARS = 4096
MAX_CONTEXT_CHARS = 500

_SDK_DIR = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))


def _library_dirs() -> list[str]:
    dirs: set[str] = set()
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        try:
            path = sysconfig.get_paths().get(key)
        except Exception:  # pragma: no cover - defensive
            path = None
        if path:
            dirs.add(path)
    for prefix in {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix}:
        dirs.add(os.path.join(prefix, "lib"))
        dirs.add(os.path.join(prefix, "Lib"))
    try:
        dirs.update(site.getsitepackages())
    except Exception:  # pragma: no cover - virtualenv quirks
        pass
    try:
        dirs.add(site.getusersitepackages())
    except Exception:  # pragma: no cover
        pass
    return sorted({os.path.normcase(os.path.abspath(d)) for d in dirs if d}, key=len, reverse=True)


_LIBRARY_DIRS = _library_dirs()


def exception_type_name(exc: BaseException) -> str:
    """``ZeroDivisionError`` for builtins, ``httpx.ReadTimeout`` otherwise."""
    cls = type(exc)
    module = getattr(cls, "__module__", None) or ""
    qualname = getattr(cls, "__qualname__", cls.__name__)
    if module in ("builtins", "__builtin__") or getattr(builtins, qualname, None) is cls:
        return qualname
    return f"{module}.{qualname}" if module else qualname


def _is_library_file(abs_path: str) -> bool:
    norm = os.path.normcase(abs_path)
    if "site-packages" in norm or "dist-packages" in norm:
        return True
    return any(norm == d or norm.startswith(d + os.sep) for d in _LIBRARY_DIRS)


def _display_filename(filename: str) -> str:
    """Stable, host-independent filename: relative to cwd, or to site-packages."""
    if filename.startswith("<"):
        return filename
    abs_path = os.path.abspath(filename)
    norm = os.path.normcase(abs_path)
    for marker in ("site-packages", "dist-packages"):
        idx = norm.rfind(marker + os.sep)
        if idx != -1:
            return abs_path[idx + len(marker) + 1 :].replace("\\", "/")
    cwd = os.path.normcase(os.getcwd())
    if norm.startswith(cwd + os.sep):
        return os.path.relpath(abs_path, os.getcwd()).replace("\\", "/")
    return abs_path.replace("\\", "/")


class FrameClassifier:
    """Decides whether a frame belongs to the application (``in_app``)."""

    def __init__(self, in_app_include: Sequence[str] | None = None) -> None:
        self._include = [p.replace("\\", "/") for p in in_app_include] if in_app_include else None

    def in_app(self, filename: str, module: str | None, display: str) -> bool:
        if filename.startswith("<"):
            return False
        abs_norm = os.path.normcase(os.path.abspath(filename))
        if abs_norm.startswith(_SDK_DIR + os.sep):
            return False
        if self._include is not None:
            candidates = [display, filename.replace("\\", "/")]
            if module:
                candidates.append(module)
            return any(c.startswith(p) for c in candidates for p in self._include)
        return not _is_library_file(filename)


def serialize_exception(exc: BaseException, classifier: FrameClassifier) -> dict[str, Any]:
    frames: list[dict[str, Any]] = []
    for frame, lineno in traceback.walk_tb(exc.__traceback__):
        code = frame.f_code
        filename = code.co_filename
        display = _display_filename(filename)
        module = frame.f_globals.get("__name__") if isinstance(frame.f_globals, dict) else None
        line = linecache.getline(filename, lineno, frame.f_globals).strip()
        frames.append(
            {
                "filename": display,
                "lineno": lineno,
                "function": getattr(code, "co_qualname", code.co_name),
                "context_line": line[:MAX_CONTEXT_CHARS] or None,
                "in_app": classifier.in_app(filename, module, display),
            }
        )
    try:
        message = str(exc)
    except Exception:  # pragma: no cover - broken __str__
        message = "<unprintable exception>"
    return {
        "type": exception_type_name(exc),
        "message": message[:MAX_MESSAGE_CHARS],
        "frames": frames[-MAX_FRAMES:],
    }
