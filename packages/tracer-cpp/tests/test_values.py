"""Pure-Python tests for the C++ value decoders. No gdb required."""
from __future__ import annotations

from cpp_tracer.values import (
    VizCatalog,
    parse_pointer,
    parse_scalar,
    parse_struct_fields,
)


class TestParseScalar:
    def test_int(self):
        assert parse_scalar("42") == {"kind": "int", "v": 42}
        assert parse_scalar("-7") == {"kind": "int", "v": -7}

    def test_float(self):
        v = parse_scalar("3.14")
        assert v == {"kind": "float", "v": 3.14}

    def test_bool(self):
        assert parse_scalar("true") == {"kind": "bool", "v": True}
        assert parse_scalar("false") == {"kind": "bool", "v": False}

    def test_string_literal(self):
        assert parse_scalar('"hello"') == {"kind": "str", "v": "hello"}

    def test_nullptr(self):
        assert parse_scalar("nullptr") == {"kind": "none"}
        assert parse_scalar("0x0") == {"kind": "none"}

    def test_unknown_returns_none(self):
        assert parse_scalar("0x600003ee0080 <typeinfo for Node>") is None
        assert parse_scalar("{val = 1, next = 0x0}") is None


class TestParsePointer:
    def test_address_only(self):
        assert parse_pointer("0xdeadbeef") == "0xdeadbeef"

    def test_address_with_symbol(self):
        assert parse_pointer("0x7fff5fbff8c0 <main+12>") == "0x7fff5fbff8c0"

    def test_null_address(self):
        assert parse_pointer("0x0") is None

    def test_non_pointer(self):
        assert parse_pointer("42") is None
        assert parse_pointer('"hello"') is None


class TestParseStructFields:
    def test_simple_struct(self):
        out = parse_struct_fields("{val = 1, next = 0x0}")
        assert out == {"val": "1", "next": "0x0"}

    def test_nested_struct_keeps_inner_raw(self):
        out = parse_struct_fields("{a = 1, b = {x = 2, y = 3}, c = 4}")
        assert out == {"a": "1", "b": "{x = 2, y = 3}", "c": "4"}

    def test_string_field_with_comma(self):
        out = parse_struct_fields('{name = "foo, bar", n = 7}')
        assert out == {"name": '"foo, bar"', "n": "7"}

    def test_invalid_no_braces_returns_none(self):
        assert parse_struct_fields("not a struct") is None


class TestVizCatalog:
    def test_from_symbol_strings_groups_by_type(self):
        cat = VizCatalog.from_symbol_strings([
            "__viz_Node_kind",
            "__viz_Node_val",
            "__viz_Node_next",
            "__viz_TreeNode_kind",
            "__viz_TreeNode_val",
            "__viz_TreeNode_left",
            "__viz_TreeNode_right",
            "_ZSt8__find_ifIPiZNSt6vector",  # noise the regex must ignore
        ])
        assert set(cat.by_type) == {"Node", "TreeNode"}
        assert set(cat.by_type["Node"]) == {"kind", "val", "next"}
        assert set(cat.by_type["TreeNode"]) == {"kind", "val", "left", "right"}

    def test_get_returns_none_without_kind(self):
        cat = VizCatalog()
        cat.by_type["X"] = {"val": "v"}  # missing 'kind'
        assert cat.get("X") is None
