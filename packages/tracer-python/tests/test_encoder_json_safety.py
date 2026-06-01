"""Regression tests: the encoder must emit strict-JSON-safe, precision-safe values.

Two bugs motivated these:

* Non-finite floats (inf / -inf / nan) flowed verbatim into the trace document.
  FastAPI re-serializes responses with ``json.dumps(allow_nan=False)``, which
  raises ``ValueError: Out of range float values are not JSON compliant`` — so
  *any* program using ``float('inf')`` (Dijkstra, Bellman-Ford, min/max init)
  returned HTTP 500 and rendered nothing in the visualizer.

* Python ints are arbitrary precision, but the browser parses JSON numbers as
  IEEE-754 doubles, so any int beyond 2**53 silently lost precision (e.g.
  ``2**70`` displayed as ``1.1805916207174113e+21``).
"""
import json

from dsa_tracer import trace_source
from dsa_tracer.encoder import HeapEncoder


def _last_local(res, name):
    for ev in reversed(res["events"]):
        for f in ev["stack"]:
            if name in f["locals"]:
                return f["locals"][name]
    raise AssertionError(f"local {name!r} not found in any event")


# --------------------------- non-finite floats --------------------------- #

def test_trace_with_infinity_is_strict_json_serializable():
    src = "a = float('inf')\nb = float('-inf')\nc = float('nan')\nprint(a, b, c)\n"
    res = trace_source(src)
    assert res["exit"]["status"] == "ok"
    # This is exactly what FastAPI's JSONResponse does; it raised before the fix.
    json.dumps(res, allow_nan=False)


def test_encoder_encodes_non_finite_floats_as_sentinels():
    enc = HeapEncoder()
    assert enc.encode(float("inf")) == {"kind": "float", "v": None, "special": "inf"}
    assert enc.encode(float("-inf")) == {"kind": "float", "v": None, "special": "-inf"}
    nan = enc.encode(float("nan"))
    assert nan["kind"] == "float" and nan["v"] is None and nan["special"] == "nan"


def test_finite_float_unchanged():
    enc = HeapEncoder()
    assert enc.encode(3.5) == {"kind": "float", "v": 3.5}


# ------------------------------ big ints ------------------------------ #

def test_large_int_emitted_as_exact_decimal_string():
    enc = HeapEncoder()
    big = 2 ** 70
    out = enc.encode(big)
    assert out["kind"] == "int"
    assert out["v"] == str(big)  # exact, no rounding
    assert out["big"] is True


def test_small_int_stays_a_json_number():
    enc = HeapEncoder()
    assert enc.encode(42) == {"kind": "int", "v": 42}
    # 2**53 - 1 is the largest integer exactly representable as a double.
    assert enc.encode(2 ** 53 - 1) == {"kind": "int", "v": 2 ** 53 - 1}


def test_big_int_round_trips_through_trace():
    src = "x = 2 ** 70\nprint(x)\n"
    res = trace_source(src)
    x = _last_local(res, "x")
    assert x["kind"] == "int"
    assert x["v"] == str(2 ** 70)
    json.dumps(res, allow_nan=False)
