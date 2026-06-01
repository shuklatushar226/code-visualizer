"""Encode live Python values into Trace Event Protocol primitives.

The encoder produces:
  * a `value` dict (a primitive or a reference to a heap object)
  * mutations to a `heap` dict keyed by Python `id()`

This deliberately matches the v0.1 protocol in docs/TRACE_FORMAT.md.
Anything not recognised is rendered as { "kind": "str", "v": repr(x) }.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

MAX_STR_LEN = 1024

# JS parses JSON numbers as IEEE-754 doubles, so integers with magnitude beyond
# 2**53 - 1 lose precision on the frontend. Larger ints are emitted as exact
# decimal strings (with a ``big`` flag) so the value round-trips losslessly.
MAX_SAFE_INT = 2 ** 53 - 1


class HeapEncoder:
    """Encodes Python objects into a shareable heap and references.

    The heap is a `dict[str, dict]` keyed by string ids (we stringify
    ``id(obj)`` so it round-trips through JSON cleanly).
    """

    def __init__(self) -> None:
        self.heap: Dict[str, dict] = {}
        # Track objects currently being encoded to break cycles.
        self._in_progress: set[int] = set()

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def encode(self, value: Any) -> dict:
        """Encode a single value, returning either a primitive Value
        or a ref Value pointing into ``self.heap``."""
        # Primitives ----------------------------------------------------
        if value is None:
            return {"kind": "none"}
        if isinstance(value, bool):
            return {"kind": "bool", "v": bool(value)}
        if isinstance(value, int):
            # Beyond the JS safe-integer range, emit an exact decimal string so
            # the browser doesn't round it when parsing the JSON.
            if abs(value) > MAX_SAFE_INT:
                return {"kind": "int", "v": str(value), "big": True}
            return {"kind": "int", "v": int(value)}
        if isinstance(value, float):
            # inf / -inf / nan are not valid strict JSON; FastAPI serializes
            # responses with allow_nan=False and would raise. Encode them as a
            # JSON-safe sentinel that the frontend renders explicitly.
            if math.isnan(value):
                return {"kind": "float", "v": None, "special": "nan"}
            if math.isinf(value):
                return {"kind": "float", "v": None, "special": "inf" if value > 0 else "-inf"}
            return {"kind": "float", "v": float(value)}
        if isinstance(value, str):
            return {"kind": "str", "v": _truncate(value)}

        # Composite -----------------------------------------------------
        oid = id(value)
        sid = f"h_{oid}"

        # Already encoded? return ref immediately.
        if sid in self.heap:
            return {"kind": "ref", "id": sid}
        # Cycle?
        if oid in self._in_progress:
            # Insert a placeholder so subsequent encodes return a ref.
            self.heap.setdefault(sid, {"kind": "object", "type": type(value).__name__, "fields": {}})
            return {"kind": "ref", "id": sid}

        self._in_progress.add(oid)
        try:
            obj = self._encode_composite(value)
            self.heap[sid] = obj
        finally:
            self._in_progress.discard(oid)

        return {"kind": "ref", "id": sid}

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    def _encode_composite(self, value: Any) -> dict:
        # Tuple
        if isinstance(value, tuple):
            return {"kind": "tuple", "items": [self.encode(x) for x in value]}
        # List
        if isinstance(value, list):
            return {"kind": "list", "items": [self.encode(x) for x in value]}
        # Set / frozenset
        if isinstance(value, (set, frozenset)):
            return {"kind": "set", "items": [self.encode(x) for x in value]}
        # Dict
        if isinstance(value, dict):
            entries: List[List[dict]] = []
            for k, v in value.items():
                entries.append([self.encode(k), self.encode(v)])
            return {"kind": "dict", "entries": entries}
        # collections.deque
        try:
            from collections import deque

            if isinstance(value, deque):
                return {
                    "kind": "list",
                    "items": [self.encode(x) for x in value],
                    "subkind": "deque",
                }
        except Exception:
            pass

        # Generic object — walk __dict__ / __slots__
        fields: Dict[str, dict] = {}
        attr_names = _public_attrs(value)
        for name in attr_names:
            try:
                fields[name] = self.encode(getattr(value, name))
            except Exception:
                fields[name] = {"kind": "str", "v": "<unreadable>"}
        return {
            "kind": "object",
            "type": type(value).__name__,
            "fields": fields,
        }


# ---------------------------------------------------------------------- #
# helpers
# ---------------------------------------------------------------------- #

def _truncate(s: str) -> str:
    if len(s) <= MAX_STR_LEN:
        return s
    return s[: MAX_STR_LEN - 3] + "..."


def _public_attrs(obj: Any) -> List[str]:
    """Return a list of attribute names worth showing for a generic object.

    We prefer __slots__ when present, else __dict__, skipping dunder names
    and callables.
    """
    names: List[str] = []
    slots = getattr(type(obj), "__slots__", None)
    if slots:
        names = list(slots)
    else:
        d = getattr(obj, "__dict__", None)
        if isinstance(d, dict):
            names = list(d.keys())
    # Filter
    out: List[str] = []
    for name in names:
        if name.startswith("_"):
            continue
        try:
            val = getattr(obj, name)
        except Exception:
            continue
        if callable(val):
            continue
        out.append(name)
    return out


def encode_frame_locals(locals_dict: Dict[str, Any], encoder: HeapEncoder) -> Dict[str, dict]:
    """Encode a frame's locals into Value dicts, skipping noise."""
    out: Dict[str, dict] = {}
    for name, val in locals_dict.items():
        if name.startswith("__") and name.endswith("__"):
            continue
        # Skip imported modules to keep noise down.
        import types
        if isinstance(val, types.ModuleType):
            continue
        if isinstance(val, type):
            continue
        try:
            out[name] = encoder.encode(val)
        except Exception:
            out[name] = {"kind": "str", "v": "<encode-error>"}
    return out
