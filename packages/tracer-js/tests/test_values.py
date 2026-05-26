"""Unit tests for the V8 RemoteObject → Trace Value encoder.

A FakeSession returns canned `Runtime.getProperties` and
`Runtime.callFunctionOn` responses so every encoder branch exercises
without spawning Node. Mirrors the test layout of tracer-cpp's
test_values.py.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from js_tracer.values import alloc_id, encode_remote_object


# ────────────────────────────────────────────────────────────────────
# FakeSession — duck-typed _SessionLike
# ────────────────────────────────────────────────────────────────────


class FakeSession:
    """Returns pre-canned getProperties / callFunctionOn payloads keyed
    by objectId. Tests register response shapes upfront."""

    def __init__(self) -> None:
        self.properties: Dict[str, List[Dict[str, Any]]] = {}
        self.call_results: Dict[str, Dict[str, Any]] = {}

    def register_properties(self, object_id: str, props: List[Dict[str, Any]]) -> None:
        self.properties[object_id] = props

    def register_call(self, object_id: str, result_ro: Dict[str, Any]) -> None:
        self.call_results[object_id] = result_ro

    async def get_properties(self, object_id, own_properties=True, accessor_properties_only=False):
        return self.properties.get(object_id, [])

    async def call_function_on(self, object_id, function_declaration):
        return self.call_results.get(object_id, {})


def ro_int(n: int) -> Dict[str, Any]:
    return {"type": "number", "value": n}


def ro_float(n: float) -> Dict[str, Any]:
    return {"type": "number", "value": n}


def ro_str(s: str) -> Dict[str, Any]:
    return {"type": "string", "value": s}


def ro_bool(b: bool) -> Dict[str, Any]:
    return {"type": "boolean", "value": b}


def ro_null() -> Dict[str, Any]:
    return {"type": "object", "subtype": "null", "value": None}


def ro_undefined() -> Dict[str, Any]:
    return {"type": "undefined"}


def ro_object(object_id: str, class_name: str = "Object", subtype: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {"type": "object", "objectId": object_id, "className": class_name}
    if subtype:
        out["subtype"] = subtype
    return out


# ────────────────────────────────────────────────────────────────────
# Primitives
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_integer_number_is_kind_int():
    out = await encode_remote_object(ro_int(42), None, {}, {})
    assert out == {"kind": "int", "v": 42}


@pytest.mark.asyncio
async def test_non_integer_number_is_kind_float():
    out = await encode_remote_object(ro_float(3.14), None, {}, {})
    assert out == {"kind": "float", "v": 3.14}


@pytest.mark.asyncio
async def test_nan_and_infinity_become_string_sentinels():
    nan = await encode_remote_object(
        {"type": "number", "unserializableValue": "NaN"}, None, {}, {}
    )
    assert nan == {"kind": "float", "v": "NaN"}
    inf = await encode_remote_object(
        {"type": "number", "unserializableValue": "Infinity"}, None, {}, {}
    )
    assert inf == {"kind": "float", "v": "Infinity"}


@pytest.mark.asyncio
async def test_string_value():
    out = await encode_remote_object(ro_str("hello"), None, {}, {})
    assert out == {"kind": "str", "v": "hello"}


@pytest.mark.asyncio
async def test_long_string_truncated_to_1k():
    s = "x" * 2000
    out = await encode_remote_object(ro_str(s), None, {}, {})
    assert out["kind"] == "str"
    assert len(out["v"]) <= 1024


@pytest.mark.asyncio
async def test_boolean():
    assert (await encode_remote_object(ro_bool(True), None, {}, {})) == {"kind": "bool", "v": True}
    assert (await encode_remote_object(ro_bool(False), None, {}, {})) == {"kind": "bool", "v": False}


@pytest.mark.asyncio
async def test_null_and_undefined_both_become_none():
    assert (await encode_remote_object(ro_null(), None, {}, {})) == {"kind": "none"}
    assert (await encode_remote_object(ro_undefined(), None, {}, {})) == {"kind": "none"}


@pytest.mark.asyncio
async def test_bigint_round_trips_as_int():
    out = await encode_remote_object(
        {"type": "bigint", "unserializableValue": "12345n"}, None, {}, {}
    )
    assert out == {"kind": "int", "v": 12345}


# ────────────────────────────────────────────────────────────────────
# Containers
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_array_walks_numeric_indices():
    sess = FakeSession()
    sess.register_properties("arr1", [
        {"name": "0", "value": ro_int(1)},
        {"name": "1", "value": ro_int(2)},
        {"name": "2", "value": ro_int(3)},
        {"name": "length", "value": ro_int(3)},        # filtered out
        {"name": "constructor", "value": ro_object("ctor")},  # filtered (non-numeric)
    ])
    addr_to_id: Dict[str, str] = {}
    heap: Dict[str, Dict[str, Any]] = {}
    out = await encode_remote_object(
        ro_object("arr1", class_name="Array", subtype="array"),
        sess, addr_to_id, heap,
    )
    assert out["kind"] == "ref"
    target = heap[out["id"]]
    assert target == {
        "kind": "list",
        "items": [
            {"kind": "int", "v": 1},
            {"kind": "int", "v": 2},
            {"kind": "int", "v": 3},
        ],
    }


@pytest.mark.asyncio
async def test_plain_object_emits_kind_object_with_class_name():
    sess = FakeSession()
    sess.register_properties("o1", [
        {"name": "x", "value": ro_int(1)},
        {"name": "y", "value": ro_str("hi")},
        {"name": "__proto__", "value": ro_object("proto")},  # filtered
    ])
    out = await encode_remote_object(
        ro_object("o1", class_name="MyShape"), sess, {}, (heap := {}),
    )
    assert out["kind"] == "ref"
    assert heap[out["id"]] == {
        "kind": "object",
        "type": "MyShape",
        "fields": {
            "x": {"kind": "int", "v": 1},
            "y": {"kind": "str", "v": "hi"},
        },
    }


@pytest.mark.asyncio
async def test_map_uses_call_function_on_then_walks_entries_array():
    sess = FakeSession()
    # The Map's entries() returns an Array whose elements are [k,v] pair arrays.
    sess.register_call("m1", ro_object("entries-arr", class_name="Array", subtype="array"))
    sess.register_properties("entries-arr", [
        {"name": "0", "value": ro_object("pair1", class_name="Array", subtype="array")},
        {"name": "1", "value": ro_object("pair2", class_name="Array", subtype="array")},
    ])
    sess.register_properties("pair1", [
        {"name": "0", "value": ro_str("a")},
        {"name": "1", "value": ro_int(1)},
    ])
    sess.register_properties("pair2", [
        {"name": "0", "value": ro_str("b")},
        {"name": "1", "value": ro_int(2)},
    ])
    heap: Dict[str, Dict[str, Any]] = {}
    out = await encode_remote_object(
        ro_object("m1", class_name="Map"), sess, {}, heap,
    )
    assert out["kind"] == "ref"
    target = heap[out["id"]]
    assert target["kind"] == "dict"
    assert target["entries"] == [
        [{"kind": "str", "v": "a"}, {"kind": "int", "v": 1}],
        [{"kind": "str", "v": "b"}, {"kind": "int", "v": 2}],
    ]


@pytest.mark.asyncio
async def test_set_uses_spread_then_walks():
    sess = FakeSession()
    sess.register_call("s1", ro_object("spread", class_name="Array", subtype="array"))
    sess.register_properties("spread", [
        {"name": "0", "value": ro_int(10)},
        {"name": "1", "value": ro_int(20)},
    ])
    heap: Dict[str, Dict[str, Any]] = {}
    out = await encode_remote_object(
        ro_object("s1", class_name="Set"), sess, {}, heap,
    )
    target = heap[out["id"]]
    assert target == {
        "kind": "set",
        "items": [{"kind": "int", "v": 10}, {"kind": "int", "v": 20}],
    }


@pytest.mark.asyncio
async def test_cycle_break_returns_existing_id_without_re_walking():
    sess = FakeSession()
    # Build an object whose `child` property points back to itself.
    sess.register_properties("o1", [
        {"name": "self", "value": ro_object("o1")},
        {"name": "n", "value": ro_int(7)},
    ])
    addr_to_id: Dict[str, str] = {}
    heap: Dict[str, Dict[str, Any]] = {}
    out = await encode_remote_object(ro_object("o1"), sess, addr_to_id, heap)
    assert out["kind"] == "ref"
    assert heap[out["id"]]["fields"]["self"] == {"kind": "ref", "id": out["id"]}
    assert heap[out["id"]]["fields"]["n"] == {"kind": "int", "v": 7}


@pytest.mark.asyncio
async def test_depth_cap_elides_deep_nesting():
    sess = FakeSession()
    sess.register_properties("a", [{"name": "b", "value": ro_object("b")}])
    sess.register_properties("b", [{"name": "c", "value": ro_object("c")}])
    sess.register_properties("c", [{"name": "d", "value": ro_object("d")}])
    sess.register_properties("d", [{"name": "e", "value": ro_object("e")}])
    sess.register_properties("e", [{"name": "leaf", "value": ro_int(99)}])
    heap: Dict[str, Dict[str, Any]] = {}
    out = await encode_remote_object(
        ro_object("a"), sess, {}, heap, depth=0, max_depth=2,
    )
    assert out["kind"] == "ref"
    # Somewhere down the chain we hit max_depth and emitted the elided sentinel.
    elided_count = sum(
        1 for obj in heap.values()
        if obj.get("kind") == "object" and obj.get("type") == "…(elided)…"
    )
    assert elided_count >= 1


# ────────────────────────────────────────────────────────────────────
# alloc_id
# ────────────────────────────────────────────────────────────────────


def test_alloc_id_returns_stable_id_for_same_object():
    addr_to_id: Dict[str, str] = {}
    a = alloc_id("oid-x", addr_to_id)
    b = alloc_id("oid-x", addr_to_id)
    assert a == b == "h_0"


def test_alloc_id_increments_for_new_objects():
    addr_to_id: Dict[str, str] = {}
    assert alloc_id("o-a", addr_to_id) == "h_0"
    assert alloc_id("o-b", addr_to_id) == "h_1"
    assert alloc_id("o-c", addr_to_id) == "h_2"
