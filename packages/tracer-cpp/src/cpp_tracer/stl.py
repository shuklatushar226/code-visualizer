"""STL container classifier + walker.

Reads GDB's `whatis` output to detect a C++ standard-library type, then
uses GDB's variable-object MI commands (-var-create / -var-list-children)
to walk the container's logical children. The result is a HeapObject in
the Trace Event Protocol shape — `{kind: "list", items: [...]}` for
vectors, `{kind: "dict", entries: [...]}` for maps, and so on.

Why var-objects (not pretty-printer text parsing)? Pretty-printers print
nice strings ("std::vector of length 4 = {1, 2, 3, 4}"), but parsing
those strings back into structured data is brittle across libstdc++
versions. Var-objects expose every child as a typed sub-expression that
the SAME `_decode_value` pipeline already handles for primitives,
pointers, and user structs. Recursive containers (vector<vector<int>>,
map<string, MyStruct>) require no additional code — the recursion is
free.

Pretty-printers are still loaded; they're what make var-objects expose
`std::vector` as N children of type T instead of three internal
`_M_impl.*` fields.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .gdb_driver import GdbDriver
    from .values import VizCatalog


StlKind = str  # one of: "vector", "list", "deque", "map", "set",
               # "unordered_map", "unordered_set", "string", "pair"


# Match `std::vector<...>` and the libstdc++ dual-ABI variant
# `std::__cxx11::list<...>`. Whitespace inside the template parameters is
# tolerated (gdb sometimes emits `vector<int, std::allocator<int> >`).
_STL_PATTERN = re.compile(
    r"""^
    std::
    (?:__cxx11::|__debug::)?
    (?P<kind>vector|list|deque|map|set|unordered_map|unordered_set|basic_string|pair|forward_list|multimap|multiset)
    <.*>
    \s*$""",
    re.VERBOSE,
)


def classify_stl(type_str: Optional[str]) -> Optional[StlKind]:
    """Return the STL kind for a type string, or None if not STL.

    Examples:
        classify_stl("std::vector<int, std::allocator<int> >") == "vector"
        classify_stl("std::__cxx11::basic_string<char, ...>")  == "string"
        classify_stl("MyClass *")                              is None
    """
    if not type_str:
        return None
    type_str = type_str.strip()
    m = _STL_PATTERN.match(type_str)
    if not m:
        return None
    kind = m.group("kind")
    # Normalize: basic_string -> string, forward_list / list / multiset
    # all map onto their richer protocol cousins; treat multimap as a dict
    # (entries may have duplicate keys, which the Trace `dict` allows
    # because `entries` is a list, not a JSON object).
    if kind == "basic_string":
        return "string"
    if kind in ("forward_list", "list", "deque"):
        return kind
    if kind in ("multimap",):
        return "map"
    if kind in ("multiset",):
        return "set"
    return kind


def decode_stl(
    drv: "GdbDriver",
    expr: str,
    type_str: str,
    heap: Dict[str, Dict[str, Any]],
    addr_to_id: Dict[str, str],
    catalog: "VizCatalog",
    decode_value: Callable[..., Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Walk an STL container and return its protocol HeapObject.

    `decode_value` is a back-reference to ``cpp_tracer._decode_value`` so
    children loop through the same value-decoder used by primitives,
    pointers, and user structs. We pass it in (rather than importing) to
    avoid a circular import — cpp_tracer.py imports this module.

    Returns None if the container can't be walked (var-create failed,
    numchild==0 for an unrecognised internal layout, etc.); caller falls
    back to its existing string-default path.
    """
    kind = classify_stl(type_str)
    if kind is None:
        return None

    # std::string is a leaf: don't walk, just take the pretty-printed value.
    if kind == "string":
        raw = drv.evaluate(expr)
        # Pretty-printer output looks like `"hello"` (quoted); strip quotes.
        m = re.match(r'^"(.*)"$', raw.strip(), flags=re.DOTALL)
        return {"kind": "str", "v": (m.group(1) if m else raw)[:1024]}

    var = drv.var_create(expr)
    if not var:
        return None
    name = var["name"]
    try:
        try:
            numchild = int(var.get("numchild", "0"))
        except (TypeError, ValueError):
            numchild = 0
        if numchild == 0:
            return _empty_container(kind)

        children = drv.var_list_children(name)
        return _build_heap_object(
            kind=kind,
            children=children,
            drv=drv,
            heap=heap,
            addr_to_id=addr_to_id,
            catalog=catalog,
            decode_value=decode_value,
        )
    finally:
        drv.var_delete(name)


def _empty_container(kind: StlKind) -> Dict[str, Any]:
    if kind in ("vector", "list", "deque", "forward_list"):
        return {"kind": "list", "items": []}
    if kind in ("map", "unordered_map"):
        return {"kind": "dict", "entries": []}
    if kind in ("set", "unordered_set"):
        return {"kind": "set", "items": []}
    if kind == "pair":
        return {"kind": "tuple", "items": []}
    return {"kind": "list", "items": []}


def _build_heap_object(
    *,
    kind: StlKind,
    children: List[Dict[str, Any]],
    drv: "GdbDriver",
    heap: Dict[str, Dict[str, Any]],
    addr_to_id: Dict[str, str],
    catalog: "VizCatalog",
    decode_value: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    if kind in ("vector", "list", "deque", "forward_list"):
        items = [
            decode_value(drv, child.get("exp", ""), child.get("value", ""), heap, addr_to_id, catalog)
            for child in children
        ]
        return {"kind": "list", "items": items}

    if kind in ("set", "unordered_set"):
        items = [
            decode_value(drv, child.get("exp", ""), child.get("value", ""), heap, addr_to_id, catalog)
            for child in children
        ]
        return {"kind": "set", "items": items}

    if kind in ("map", "unordered_map"):
        # Each child is a std::pair<K, V>. Expand each child to grab the
        # `first` (key) and `second` (value) sub-children.
        entries: List[List[Dict[str, Any]]] = []
        for child in children:
            cname = child.get("name")
            if not cname:
                continue
            sub = drv.var_list_children(cname)
            key = _find_member(sub, "first")
            val = _find_member(sub, "second")
            if key is None or val is None:
                continue
            entries.append([
                decode_value(drv, key.get("exp", ""), key.get("value", ""), heap, addr_to_id, catalog),
                decode_value(drv, val.get("exp", ""), val.get("value", ""), heap, addr_to_id, catalog),
            ])
        return {"kind": "dict", "entries": entries}

    if kind == "pair":
        first = _find_member(children, "first")
        second = _find_member(children, "second")
        items = []
        if first is not None:
            items.append(decode_value(drv, first.get("exp", ""), first.get("value", ""), heap, addr_to_id, catalog))
        if second is not None:
            items.append(decode_value(drv, second.get("exp", ""), second.get("value", ""), heap, addr_to_id, catalog))
        return {"kind": "tuple", "items": items}

    # Fallback: treat as a list.
    return {
        "kind": "list",
        "items": [
            decode_value(drv, child.get("exp", ""), child.get("value", ""), heap, addr_to_id, catalog)
            for child in children
        ],
    }


def _find_member(children: List[Dict[str, Any]], member: str) -> Optional[Dict[str, Any]]:
    """Find the child whose displayed expression ends in `.member` or `->member`.

    GDB's `-var-list-children` returns each child's `exp` as the textual
    sub-expression (e.g. `pair.first`, `*node`, `[0]`). We match on suffix
    rather than equality because the prefix path is invocation-specific.
    """
    for child in children:
        exp = child.get("exp") or ""
        if exp == member or exp.endswith(f".{member}") or exp.endswith(f"->{member}"):
            return child
    return None
