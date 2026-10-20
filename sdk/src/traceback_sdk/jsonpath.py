"""Simple JSONPath subset, ported from ``frontend/src/lib/jsonPath.ts``.

Supported: ``$``, ``.key``, ``["key"]``, ``[0]``; the leading ``$`` is optional,
so ``error.code`` and ``$.error.code`` are equivalent.
"""

from __future__ import annotations

import json
import re
from typing import Any, NamedTuple

_TOKEN = re.compile(r'^(?:\.([A-Za-z_$][\w$-]*)|\[(\d+)\]|\["((?:[^"\\]|\\.)*)"\])', re.ASCII)


class PathLookup(NamedTuple):
    found: bool
    value: Any


def parse_path(path: str) -> list[str | int] | None:
    tokens: list[str | int] = []
    rest = path.strip()
    if rest.startswith("$"):
        rest = rest[1:]
    if rest and not rest.startswith(".") and not rest.startswith("["):
        rest = "." + rest
    while rest:
        m = _TOKEN.match(rest)
        if not m:
            return None
        if m.group(1) is not None:
            tokens.append(m.group(1))
        elif m.group(2) is not None:
            tokens.append(int(m.group(2)))
        else:
            try:
                tokens.append(json.loads(f'"{m.group(3)}"'))
            except ValueError:
                return None
        rest = rest[m.end() :]
    return tokens


def get_path(value: Any, path: str) -> PathLookup:
    tokens = parse_path(path)
    if tokens is None:
        return PathLookup(False, None)
    current = value
    for token in tokens:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                return PathLookup(False, None)
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                return PathLookup(False, None)
            current = current[token]
    return PathLookup(True, current)
