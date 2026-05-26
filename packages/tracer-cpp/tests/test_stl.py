"""Unit + integration tests for the STL decoder.

The classifier is pure Python and runs everywhere. The end-to-end
trace test requires g++ + gdb on PATH — gated for macOS dev boxes.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cpp_tracer import trace_source
from cpp_tracer.stl import classify_stl


gdb_available = shutil.which("gdb") is not None and shutil.which("g++") is not None
needs_toolchain = pytest.mark.skipif(
    not gdb_available, reason="requires g++ and gdb on PATH"
)


# ────────────────────────────────────────────────────────────────────
# classify_stl — pure-Python, runs everywhere
# ────────────────────────────────────────────────────────────────────

class TestClassifyStl:
    def test_vector(self):
        assert classify_stl("std::vector<int, std::allocator<int> >") == "vector"
        assert classify_stl("std::vector<MyType*>") == "vector"
        # libstdc++ debug-mode variants are accepted.
        assert classify_stl("std::__debug::vector<int>") == "vector"

    def test_list_and_deque(self):
        assert classify_stl("std::list<int>") == "list"
        assert classify_stl("std::deque<double>") == "deque"
        assert classify_stl("std::forward_list<int>") == "forward_list"

    def test_map_and_set(self):
        assert classify_stl("std::map<int, std::string>") == "map"
        assert classify_stl("std::unordered_map<std::string, int>") == "unordered_map"
        assert classify_stl("std::set<int>") == "set"
        assert classify_stl("std::unordered_set<long>") == "unordered_set"
        # Multimap and multiset normalize to their plain cousins.
        assert classify_stl("std::multimap<int, int>") == "map"
        assert classify_stl("std::multiset<int>") == "set"

    def test_string(self):
        assert classify_stl("std::__cxx11::basic_string<char, std::char_traits<char>, std::allocator<char> >") == "string"
        assert classify_stl("std::basic_string<char>") == "string"

    def test_pair(self):
        assert classify_stl("std::pair<int, std::string>") == "pair"

    def test_cxx11_variant(self):
        # The dual-ABI prefix must be tolerated.
        assert classify_stl("std::__cxx11::list<int>") == "list"

    def test_negatives(self):
        assert classify_stl(None) is None
        assert classify_stl("") is None
        assert classify_stl("int") is None
        assert classify_stl("MyClass *") is None
        assert classify_stl("std::shared_ptr<int>") is None  # not in scope
        # Avoid false-match on substring; this isn't a vector.
        assert classify_stl("my::vector<int>") is None


# ────────────────────────────────────────────────────────────────────
# End-to-end trace — gated on g++ + gdb
# ────────────────────────────────────────────────────────────────────

@needs_toolchain
def test_stl_demo_produces_valid_trace():
    """End-to-end smoke: compile examples/cpp/stl_demo.cpp, trace it,
    assert the schema shape holds across every event.

    We deliberately do NOT pin specific decoded values for STL containers
    here. Gdb step placement, libstdc++ pretty-printer auto-load timing,
    and -var-list-children child-name conventions all vary by distro and
    version. The fidelity of decoded values for annotated user structs
    is already covered by test_values.py / test_tracer_cpp.py; the
    classifier above carries the type-detection contract. The role of
    THIS test is just "the gdb plumbing doesn't crash on STL containers
    and the resulting trace validates."
    """
    src_path = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "examples" / "cpp" / "stl_demo.cpp"
    )
    if not src_path.exists():
        pytest.skip(f"example missing: {src_path}")

    res = trace_source(src_path.read_text(), max_events=500)
    assert res["language"] == "cpp"
    assert res["version"] == "0.1"
    assert res["exit"]["status"] in {"ok", "error"}
    assert isinstance(res["events"], list)
    for ev in res["events"]:
        assert {"t", "kind", "line", "file", "stack", "heap"} <= set(ev)
        # Every heap object must carry a recognised protocol kind, so
        # silent shape-corruption regresses CI immediately.
        for obj in ev.get("heap", {}).values():
            assert obj.get("kind") in {
                "list", "dict", "set", "tuple", "object", "str",
            }, f"unexpected heap kind: {obj.get('kind')}"
