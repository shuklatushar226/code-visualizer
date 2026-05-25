"""Decode GDB/MI value strings into Trace Event Protocol Value/HeapObject.

The interesting work in M3 is shaped by GDB's stringly-typed output for
``-data-evaluate-expression``. For primitives this is a regular grammar
(``42``, ``"hello"``, ``3.14``); for structs and pointers GDB returns
``{field1 = val1, field2 = val2, ...}`` and ``0xADDR <symbol>``.

This module deliberately stays small: it covers the primitives and the
annotated-struct case that ``<viz.hpp>`` macros generate metadata for.
Unannotated structs are exposed as a generic ``object`` so the front-end
can fall back to a plain key/value view.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------- #
# Annotation metadata produced by VIZ_REGISTER_* macros
# ---------------------------------------------------------------------- #

@dataclass(frozen=True)
class VizAnnotation:
    kind: str                      # "linked_list", "tree", "graph"
    val_field: Optional[str] = None
    next_field: Optional[str] = None
    left_field: Optional[str] = None
    right_field: Optional[str] = None
    adj_field: Optional[str] = None


@dataclass
class VizCatalog:
    """type_name -> VizAnnotation parsed from `nm <binary>`."""
    by_type: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def get(self, type_name: str) -> Optional[VizAnnotation]:
        entry = self.by_type.get(type_name)
        if not entry or "kind" not in entry:
            return None
        return VizAnnotation(
            kind=entry["kind"],
            val_field=entry.get("val"),
            next_field=entry.get("next"),
            left_field=entry.get("left"),
            right_field=entry.get("right"),
            adj_field=entry.get("adj"),
        )

    @classmethod
    def from_symbol_strings(cls, symbols: list[str]) -> "VizCatalog":
        """Parse symbols like ``__viz_Node_kind`` / ``__viz_Node_val``.

        Each VIZ_REGISTER_* macro emits a `static const char* __viz_<TYPE>_<KEY>`
        whose *value* we don't have here — we only have the symbol *names*. The
        macros use a parallel naming convention (kind, val, next, left, right,
        adj) that we mirror in the keys of the catalog. The actual string
        values are recovered via `evaluate(symbol)` at trace time.
        """
        out: Dict[str, Dict[str, str]] = {}
        for sym in symbols:
            m = re.match(r"^__viz_([A-Za-z_][A-Za-z0-9_]*)_(kind|val|next|left|right|adj)$", sym)
            if not m:
                continue
            type_name, key = m.group(1), m.group(2)
            out.setdefault(type_name, {})[key] = ""
        cat = cls()
        cat.by_type = out
        return cat


# ---------------------------------------------------------------------- #
# Primitive parsing
# ---------------------------------------------------------------------- #

_HEX_PTR = re.compile(r"^(0x[0-9a-fA-F]+)(?:\s+.*)?$")
_INT_LIT = re.compile(r"^-?\d+$")
_FLOAT_LIT = re.compile(r"^-?\d+\.\d+(?:[eE][+-]?\d+)?$")
_STRING_LIT = re.compile(r'^(0x[0-9a-fA-F]+\s+)?"(.*)"$', re.DOTALL)
_STD_STRING = re.compile(r'^\{\s*static .* (npos|kind).*\}|^"(.*)"$')


def parse_scalar(raw: str) -> Optional[Dict[str, Any]]:
    """Best-effort parse of a primitive GDB value string into a Value.

    Returns None for things we don't know how to decode; callers can fall
    back to ``{"kind": "str", "v": raw}`` for opaque values.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if s == "true":
        return {"kind": "bool", "v": True}
    if s == "false":
        return {"kind": "bool", "v": False}
    if _INT_LIT.match(s):
        return {"kind": "int", "v": int(s)}
    if _FLOAT_LIT.match(s):
        return {"kind": "float", "v": float(s)}
    m = _STRING_LIT.match(s)
    if m:
        return {"kind": "str", "v": m.group(2)}
    if s == "nullptr" or s == "0x0":
        return {"kind": "none"}
    return None


def parse_pointer(raw: str) -> Optional[str]:
    """Return the hex address from a GDB pointer string like ``0xADDR <sym>``."""
    m = _HEX_PTR.match(raw.strip())
    if not m:
        return None
    addr = m.group(1)
    if addr == "0x0":
        return None
    return addr


# ---------------------------------------------------------------------- #
# Struct field parsing (best-effort)
# ---------------------------------------------------------------------- #

def parse_struct_fields(raw: str) -> Optional[Dict[str, str]]:
    """Crack ``{field1 = "x", field2 = 0x123, field3 = {nested = ...}}``.

    This is a single-level parse: nested structs come back as raw strings
    that the caller can re-parse if they care.
    """
    s = raw.strip()
    if not s.startswith("{") or not s.endswith("}"):
        return None
    inner = s[1:-1].strip()
    out: Dict[str, str] = {}
    pos = 0
    depth = 0
    in_str = False
    key_start = 0
    eq_at: Optional[int] = None
    while pos < len(inner):
        ch = inner[pos]
        if in_str:
            if ch == '"' and inner[pos - 1] != "\\":
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        elif depth == 0 and ch == "=" and eq_at is None:
            eq_at = pos
        elif depth == 0 and ch == "," and eq_at is not None:
            key = inner[key_start:eq_at].strip()
            value = inner[eq_at + 1 : pos].strip()
            if key:
                out[key] = value
            key_start = pos + 1
            eq_at = None
        pos += 1
    if eq_at is not None:
        key = inner[key_start:eq_at].strip()
        value = inner[eq_at + 1 :].strip()
        if key:
            out[key] = value
    return out or None
