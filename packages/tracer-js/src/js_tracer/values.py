"""V8 RemoteObject → Trace Event Protocol Value encoder.

V8 Inspector returns values as `RemoteObject` JSON. For primitives the
value is inlined (`{type:"number", value:42}`); for objects, an
`objectId` is returned and we walk its properties via
`Runtime.getProperties` / `Runtime.callFunctionOn`.

This module is async because walking object properties requires a
roundtrip to the Inspector session. The session is passed in (a duck-
typed protocol below) so unit tests can substitute a `FakeSession`
without spawning Node.
"""
from __future__ import annotations

import math
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol


# ────────────────────────────────────────────────────────────────────
# Session protocol — what encode_remote_object needs from the
# InspectorSession to walk objects. Defined as a Protocol so tests can
# pass a stub that returns canned RemoteObject responses.
# ────────────────────────────────────────────────────────────────────


class _SessionLike(Protocol):
    async def get_properties(
        self,
        object_id: str,
        own_properties: bool = True,
        accessor_properties_only: bool = False,
    ) -> list: ...

    async def call_function_on(
        self, object_id: str, function_declaration: str
    ) -> Dict[str, Any]: ...


# ────────────────────────────────────────────────────────────────────
# Heap id allocation (cycle-safe)
# ────────────────────────────────────────────────────────────────────


def alloc_id(object_id: str, addr_to_id: Dict[str, str]) -> str:
    """Allocate (or reuse) a stable trace heap id for a V8 objectId.

    Identical machinery to the C++ tracer's `_alloc_id` so traces from
    every language use the same `h_<n>` id format. Cycle break: a
    repeated objectId returns its existing id without triggering a
    re-walk.
    """
    if object_id in addr_to_id:
        return addr_to_id[object_id]
    new_id = f"h_{len(addr_to_id)}"
    addr_to_id[object_id] = new_id
    return new_id


# ────────────────────────────────────────────────────────────────────
# Primitive helpers
# ────────────────────────────────────────────────────────────────────


def _encode_number(n: Any) -> Dict[str, Any]:
    """JavaScript numbers are all IEEE-754 doubles, but the trace
    protocol distinguishes int from float. Bucket integers (with a
    safe-int check) as `int`, everything else as `float`. NaN and
    ±Infinity round-trip as string sentinels because the JSON schema
    doesn't admit raw NaN / Infinity."""
    if isinstance(n, str):
        # V8 sometimes encodes NaN/Infinity as literal strings in the
        # RemoteObject; preserve those as float sentinels.
        return {"kind": "float", "v": n}
    if not isinstance(n, (int, float)):
        return {"kind": "float", "v": str(n)}
    if isinstance(n, float):
        if math.isnan(n):
            return {"kind": "float", "v": "NaN"}
        if math.isinf(n):
            return {"kind": "float", "v": "Infinity" if n > 0 else "-Infinity"}
        if n.is_integer() and abs(n) < 2 ** 53:
            return {"kind": "int", "v": int(n)}
        return {"kind": "float", "v": n}
    return {"kind": "int", "v": int(n)}


def _truncate_string(s: str, cap: int = 1024) -> str:
    return s if len(s) <= cap else s[:cap - 1] + "…"


# ────────────────────────────────────────────────────────────────────
# Main encoder
# ────────────────────────────────────────────────────────────────────


MAX_DEPTH = 4
ELIDED_TYPE = "…(elided)…"


async def encode_remote_object(
    ro: Dict[str, Any],
    session: Optional[_SessionLike],
    addr_to_id: Dict[str, str],
    heap: Dict[str, Dict[str, Any]],
    depth: int = 0,
    max_depth: int = MAX_DEPTH,
) -> Dict[str, Any]:
    """Convert one V8 RemoteObject into a Trace Value.

    For container types, the function ALSO populates `heap` with a
    HeapObject keyed by the allocated id. The returned Value is either
    a primitive (`{kind:"int", v:…}`) or a `{kind:"ref", id:…}` whose
    target lives in `heap`.

    Args:
        ro: a RemoteObject as returned by V8 Inspector.
        session: live Inspector session for walking objects. May be
            None for already-resolved primitives.
        addr_to_id: maps V8 objectId → trace heap id. Mutated.
        heap: trace heap. Mutated for non-primitive values.
        depth: current recursion depth.
        max_depth: cap; deeper objects are elided.
    """
    if ro is None:
        return {"kind": "none"}

    t = ro.get("type")
    subtype = ro.get("subtype")

    # ── primitives ──
    if t == "undefined":
        return {"kind": "none"}
    if t == "boolean":
        return {"kind": "bool", "v": bool(ro.get("value"))}
    if t == "string":
        return {"kind": "str", "v": _truncate_string(str(ro.get("value", "")))}
    if t == "number":
        if "unserializableValue" in ro:
            return _encode_number(ro["unserializableValue"])
        return _encode_number(ro.get("value"))
    if t == "bigint":
        # BigInt: encode as int when small, else as a string sentinel.
        raw = ro.get("unserializableValue") or str(ro.get("value", ""))
        s = raw.rstrip("n")
        try:
            return {"kind": "int", "v": int(s)}
        except (TypeError, ValueError):
            return {"kind": "str", "v": s}

    # ── objects ──
    if t == "object":
        if subtype == "null":
            return {"kind": "none"}
        object_id = ro.get("objectId")
        if not object_id or session is None:
            # No way to walk this; surface as a generic object marker.
            return {"kind": "str", "v": ro.get("description", str(ro))[:1024]}

        # Cycle / repeat reference: return the existing ref without
        # re-walking the object's properties.
        if object_id in addr_to_id:
            return {"kind": "ref", "id": addr_to_id[object_id]}

        heap_id = alloc_id(object_id, addr_to_id)

        # Depth cap — emit a stub object so the protocol stays valid
        # but skip the recursive walk.
        if depth >= max_depth:
            heap[heap_id] = {
                "kind": "object",
                "type": ELIDED_TYPE,
                "fields": {},
            }
            return {"kind": "ref", "id": heap_id}

        # Reserve the heap slot before recursing so a cycle hitting
        # this same objectId during the walk returns a ref to us.
        heap[heap_id] = {"kind": "object", "type": ro.get("className") or "object", "fields": {}}

        if subtype == "array":
            heap[heap_id] = await _encode_array(ro, session, addr_to_id, heap, depth + 1, max_depth)
        elif ro.get("className") == "Map":
            heap[heap_id] = await _encode_map(ro, session, addr_to_id, heap, depth + 1, max_depth)
        elif ro.get("className") == "Set":
            heap[heap_id] = await _encode_set(ro, session, addr_to_id, heap, depth + 1, max_depth)
        else:
            heap[heap_id] = await _encode_user_object(
                ro, session, addr_to_id, heap, depth + 1, max_depth
            )

        return {"kind": "ref", "id": heap_id}

    # ── functions / symbols / unknown ──
    if t == "function":
        return {"kind": "str", "v": f"<function {ro.get('className') or ''}>"[:1024]}
    return {"kind": "str", "v": str(ro.get("description") or ro.get("value") or t)[:1024]}


# ────────────────────────────────────────────────────────────────────
# Container walkers — each returns a HeapObject (not a Value).
# ────────────────────────────────────────────────────────────────────


async def _encode_array(
    ro: Dict[str, Any],
    session: _SessionLike,
    addr_to_id: Dict[str, str],
    heap: Dict[str, Dict[str, Any]],
    depth: int,
    max_depth: int,
) -> Dict[str, Any]:
    props = await session.get_properties(ro["objectId"], own_properties=True)
    items: List[Dict[str, Any]] = []
    # Numeric-index properties only; `length` and accessors are filtered.
    indexed: List[tuple[int, Dict[str, Any]]] = []
    for p in props:
        name = p.get("name", "")
        if not name.isdigit():
            continue
        value = p.get("value")
        if value is None:
            continue
        indexed.append((int(name), value))
    indexed.sort(key=lambda kv: kv[0])
    for _, value in indexed:
        items.append(
            await encode_remote_object(value, session, addr_to_id, heap, depth, max_depth)
        )
    return {"kind": "list", "items": items}


async def _encode_map(
    ro: Dict[str, Any],
    session: _SessionLike,
    addr_to_id: Dict[str, str],
    heap: Dict[str, Dict[str, Any]],
    depth: int,
    max_depth: int,
) -> Dict[str, Any]:
    entries_ro = await session.call_function_on(
        ro["objectId"], "function(){return [...this.entries()];}"
    )
    # entries_ro is a RemoteObject for an Array of [k, v] pairs. Walk it.
    if not entries_ro.get("objectId"):
        return {"kind": "dict", "entries": []}
    pairs_props = await session.get_properties(entries_ro["objectId"], own_properties=True)
    entries: List[List[Dict[str, Any]]] = []
    for p in pairs_props:
        if not p.get("name", "").isdigit():
            continue
        pair_ro = p.get("value")
        if not pair_ro or not pair_ro.get("objectId"):
            continue
        pair_props = await session.get_properties(pair_ro["objectId"], own_properties=True)
        kv = [None, None]
        for pp in pair_props:
            n = pp.get("name", "")
            if n == "0":
                kv[0] = pp.get("value")
            elif n == "1":
                kv[1] = pp.get("value")
        if kv[0] is None or kv[1] is None:
            continue
        entries.append(
            [
                await encode_remote_object(kv[0], session, addr_to_id, heap, depth, max_depth),
                await encode_remote_object(kv[1], session, addr_to_id, heap, depth, max_depth),
            ]
        )
    return {"kind": "dict", "entries": entries}


async def _encode_set(
    ro: Dict[str, Any],
    session: _SessionLike,
    addr_to_id: Dict[str, str],
    heap: Dict[str, Dict[str, Any]],
    depth: int,
    max_depth: int,
) -> Dict[str, Any]:
    arr_ro = await session.call_function_on(
        ro["objectId"], "function(){return [...this];}"
    )
    if not arr_ro.get("objectId"):
        return {"kind": "set", "items": []}
    props = await session.get_properties(arr_ro["objectId"], own_properties=True)
    items: List[Dict[str, Any]] = []
    indexed: List[tuple[int, Dict[str, Any]]] = []
    for p in props:
        if not p.get("name", "").isdigit():
            continue
        value = p.get("value")
        if value is None:
            continue
        indexed.append((int(p["name"]), value))
    indexed.sort(key=lambda kv: kv[0])
    for _, value in indexed:
        items.append(
            await encode_remote_object(value, session, addr_to_id, heap, depth, max_depth)
        )
    return {"kind": "set", "items": items}


async def _encode_user_object(
    ro: Dict[str, Any],
    session: _SessionLike,
    addr_to_id: Dict[str, str],
    heap: Dict[str, Dict[str, Any]],
    depth: int,
    max_depth: int,
) -> Dict[str, Any]:
    props = await session.get_properties(ro["objectId"], own_properties=True)
    fields: Dict[str, Dict[str, Any]] = {}
    for p in props:
        name = p.get("name")
        if not name or name == "__proto__":
            continue
        value = p.get("value")
        if value is None:
            continue
        fields[name] = await encode_remote_object(
            value, session, addr_to_id, heap, depth, max_depth
        )
    return {
        "kind": "object",
        "type": ro.get("className") or "object",
        "fields": fields,
    }
