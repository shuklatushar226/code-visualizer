"""Tests for the JDI-driven Java tracer.

Integration tests need a JDK (javac + java) on PATH; they skip otherwise,
mirroring the C++ tracer's gdb/g++ gating.
"""
from __future__ import annotations

import json
import shutil

import pytest

from java_tracer import trace_source

jdk_available = shutil.which("javac") is not None and shutil.which("java") is not None
needs_jdk = pytest.mark.skipif(not jdk_available, reason="requires javac and java on PATH")


def _locals_of_last(res):
    out = {}
    for ev in res["events"]:
        for f in ev["stack"]:
            out.update(f.get("locals", {}))
    return out


def _find_heap_object(res, type_name):
    for ev in res["events"]:
        for obj in ev["heap"].values():
            if obj.get("kind") == "object" and obj.get("type") == type_name:
                return obj, ev["heap"]
    return None, None


@needs_jdk
def test_simple_assignment_ok():
    src = (
        "public class Main {\n"
        "  public static void main(String[] a){\n"
        "    int x = 1;\n"
        "    int y = x + 1;\n"
        "    System.out.println(y);\n"
        "  }\n"
        "}\n"
    )
    res = trace_source(src)
    assert res["language"] == "java"
    assert res["exit"]["status"] == "ok", res["exit"]
    assert len(res["events"]) >= 2
    names = {k for e in res["events"] for f in e["stack"] for k in f["locals"]}
    assert {"x", "y"} <= names
    assert "2" in res["stdout"]


@needs_jdk
def test_recursion_emits_call_and_return():
    src = (
        "public class Main {\n"
        "  static int fact(int n){ if(n<=1) return 1; return n*fact(n-1); }\n"
        "  public static void main(String[] a){ System.out.println(fact(4)); }\n"
        "}\n"
    )
    res = trace_source(src)
    kinds = {e["kind"] for e in res["events"]}
    assert "call" in kinds
    assert "return" in kinds
    assert "24" in res["stdout"]


@needs_jdk
def test_linked_list_decodes_as_object_with_next():
    src = (
        "public class Main {\n"
        "  static class ListNode { int val; ListNode next; ListNode(int v){val=v;} }\n"
        "  public static void main(String[] a){\n"
        "    ListNode head = new ListNode(1);\n"
        "    head.next = new ListNode(2);\n"
        "  }\n"
        "}\n"
    )
    res = trace_source(src)
    obj, heap = _find_heap_object(res, "ListNode")
    assert obj is not None, "expected a ListNode heap object"
    assert "val" in obj["fields"] and "next" in obj["fields"]


@needs_jdk
def test_array_decodes_as_list():
    src = (
        "public class Main {\n"
        "  public static void main(String[] a){\n"
        "    int[] arr = {5, 6, 7};\n"
        "    int s = arr[0];\n"
        "    System.out.println(s);\n"
        "  }\n"
        "}\n"
    )
    res = trace_source(src)
    found = False
    for ev in res["events"]:
        for obj in ev["heap"].values():
            if obj.get("kind") == "list" and [i.get("v") for i in obj.get("items", [])] == [5, 6, 7]:
                found = True
    assert found, "expected int[] to decode to a list [5,6,7]"


@needs_jdk
def test_collections_decode_to_structures():
    src = (
        "import java.util.*;\n"
        "public class Main {\n"
        "  public static void main(String[] a){\n"
        "    List<Integer> xs = new ArrayList<>(); xs.add(10); xs.add(20);\n"
        "    Map<String,Integer> m = new HashMap<>(); m.put(\"k\", 5);\n"
        "    Set<Integer> s = new HashSet<>(); s.add(7);\n"
        "  }\n"
        "}\n"
    )
    res = trace_source(src)
    kinds = set()
    for ev in res["events"]:
        for obj in ev["heap"].values():
            kinds.add(obj.get("kind"))
    assert "list" in kinds and "dict" in kinds and "set" in kinds
    # the ArrayList items should be unwrapped ints, not object refs
    saw_list_of_ints = False
    for ev in res["events"]:
        for obj in ev["heap"].values():
            if obj.get("kind") == "list":
                vals = [i.get("v") for i in obj.get("items", []) if i.get("kind") == "int"]
                if 10 in vals and 20 in vals:
                    saw_list_of_ints = True
    assert saw_list_of_ints


@needs_jdk
def test_uncaught_exception_surfaces():
    src = (
        "public class Main {\n"
        "  public static void main(String[] a){ int[] x = new int[1]; int y = x[5]; }\n"
        "}\n"
    )
    res = trace_source(src)
    assert res["exit"]["status"] == "error"
    kinds = [e["kind"] for e in res["events"]]
    assert "exception" in kinds


@needs_jdk
def test_big_long_and_non_finite_are_strict_json():
    src = (
        "public class Main {\n"
        "  public static void main(String[] a){\n"
        "    long big = 1L << 60;\n"
        "    double inf = 1.0 / 0.0;\n"
        "    int z = 0;\n"
        "    System.out.println(z);\n"
        "  }\n"
        "}\n"
    )
    res = trace_source(src)
    assert res["exit"]["status"] == "ok"
    json.dumps(res, allow_nan=False)  # would raise if inf/nan leaked through
    loc = _locals_of_last(res)
    assert loc["big"] == {"kind": "int", "v": str(1 << 60), "big": True}
    assert loc["inf"] == {"kind": "float", "v": None, "special": "inf"}


@needs_jdk
def test_stdin_is_forwarded():
    src = (
        "import java.util.Scanner;\n"
        "public class Main {\n"
        "  public static void main(String[] a){ Scanner sc=new Scanner(System.in); int n=sc.nextInt(); System.out.println(n*2); }\n"
        "}\n"
    )
    res = trace_source(src, stdin="21\n")
    assert res["exit"]["status"] == "ok", res["exit"]
    assert "42" in res["stdout"]


@needs_jdk
def test_compile_error_surfaces():
    # Has a main (so detection passes and we reach javac) but a body syntax error.
    src = (
        "public class Main {\n"
        "  public static void main(String[] a){ int x = ; }\n"
        "}\n"
    )
    res = trace_source(src)
    assert res["exit"]["status"] == "error"
    assert "compil" in res["exit"]["message"].lower() or "error" in res["stderr"].lower()


@needs_jdk
def test_missing_main_is_a_clean_error():
    src = "public class Main { int x = 1; }\n"
    res = trace_source(src)
    assert res["exit"]["status"] == "error"
    assert "main" in res["exit"]["message"].lower()


@needs_jdk
def test_max_events_truncates():
    src = (
        "public class Main {\n"
        "  public static void main(String[] a){\n"
        "    int x = 0;\n"
        "    for (int i = 0; i < 100000; i++) {\n"
        "      x += i;\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
    res = trace_source(src, max_events=40)
    assert len(res["events"]) <= 40
    assert res["exit"]["truncated"] is True
