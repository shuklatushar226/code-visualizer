"""Smoke tests for the Python tracer."""
import json

from dsa_tracer import trace_source


def test_simple_assignment():
    src = "a = 1\nb = 2\nc = a + b\n"
    res = trace_source(src)
    assert res["exit"]["status"] == "ok"
    # At least one event per line.
    assert len(res["events"]) >= 3
    # Last event should see all three locals.
    last = res["events"][-1]
    names = {k for f in last["stack"] for k in f["locals"]}
    assert {"a", "b", "c"} <= names


def test_list_appears_on_heap():
    src = "xs = [1, 2, 3]\nxs.append(4)\n"
    res = trace_source(src)
    # Find an event where xs has 4 items.
    found = False
    for ev in res["events"]:
        for f in ev["stack"]:
            xs_ref = f["locals"].get("xs")
            if xs_ref and xs_ref.get("kind") == "ref":
                obj = ev["heap"][xs_ref["id"]]
                if obj["kind"] == "list" and len(obj["items"]) == 4:
                    found = True
    assert found, "expected to see xs grow to 4 items"


def test_runtime_error_captured():
    src = "a = 1\nb = 1 / 0\n"
    res = trace_source(src)
    assert res["exit"]["status"] == "error"
    # At least one event should have kind == "exception".
    kinds = [e["kind"] for e in res["events"]]
    assert "exception" in kinds


def test_max_events_truncates():
    src = "x = 0\nfor i in range(100000):\n    x += 1\n"
    res = trace_source(src, max_events=50)
    assert len(res["events"]) <= 50
    assert res["exit"].get("truncated") is True


def test_function_call_and_return():
    src = (
        "def add(a, b):\n"
        "    return a + b\n"
        "r = add(2, 3)\n"
    )
    res = trace_source(src)
    kinds = [e["kind"] for e in res["events"]]
    assert "call" in kinds
    assert "return" in kinds


def test_serialisable():
    src = "a = {'k': [1, 2, 3]}\n"
    res = trace_source(src)
    # Must round-trip through JSON.
    json.dumps(res)
