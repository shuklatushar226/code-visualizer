# tracer-cpp (skeleton)

C++ tracer for the DSA Code Visualizer. Compiles user C++ code with `g++ -g -O0`
and steps through it via the GDB Machine Interface (GDB/MI), emitting the same
Trace Event Protocol JSON that `tracer-python` produces.

> Status: **skeleton**. The Python driver scaffolds the GDB session and lays
> out the architecture. The hard work — turning GDB's textual variable dumps
> into protocol Values for `std::vector`, `std::string`, user `struct`s, and
> linked-list / tree nodes — is roadmapped in `docs/ROADMAP.md` M3.

## Why GDB?

Instrumenting C++ source (a la Python's `sys.settrace`) requires a Clang AST
transform, which is heavy. GDB is already installed everywhere `g++` is, knows
about debug symbols, and can be driven programmatically via its MI protocol.

## Pipeline

```
   user.cpp ──▶ g++ -g -O0 -o user.bin ──▶ gdb --interpreter=mi3 user.bin
                                                    │
                                                    ▼
                              pygdbmi → step → -stack-list-frames
                                              -stack-list-locals
                                              -data-evaluate-expression
                                                    │
                                                    ▼
                                          cpp_tracer.py
                                                    │
                                                    ▼
                                       Trace Event Protocol JSON
```

## Encoding C++ values

| C++ type                  | Protocol kind                   | Notes                                       |
|---------------------------|---------------------------------|---------------------------------------------|
| `int`, `long`, `unsigned` | `int`                           |                                             |
| `double`, `float`         | `float`                         |                                             |
| `bool`                    | `bool`                          |                                             |
| `char`, `std::string`     | `str`                           | `std::string` via libstdc++ pretty-printer  |
| `std::vector<T>`          | `object` ref to `list`          | iterate `_M_start` … `_M_finish`            |
| `std::array<T,N>`         | `list`                          |                                             |
| `std::pair`, `std::tuple` | `tuple`                         |                                             |
| `std::map`, `unordered_map` | `dict`                        | iterate via libstdc++ pretty-printer        |
| `std::set`                | `set`                           |                                             |
| user struct/class         | `object` with public fields     | walk struct members via GDB `ptype`         |
| pointers                  | `ref` (if non-null) or `none`   |                                             |

## A `<viz.hpp>` helper

To make struct detection deterministic, students can `#include <viz.hpp>` and
mark their structs:

```cpp
#include <viz.hpp>

struct ListNode {
    int val;
    ListNode* next;
};
VIZ_REGISTER_LINKED_LIST(ListNode, val, next);

struct TreeNode {
    int val;
    TreeNode* left;
    TreeNode* right;
};
VIZ_REGISTER_TREE(TreeNode, val, left, right);
```

These expand into specially-named static variables that the GDB driver can
read out, so it knows which struct fields hold the recursive pointers.

## Status of files

* `src/gdb_driver.py` — minimal `pygdbmi` wrapper, can step a program
* `src/cpp_tracer.py` — translates GDB events into Trace Event Protocol
                          *(stubbed; throws NotImplementedError on most types)*
* `src/cli.py`        — `dsa-trace-cpp file.cpp -o trace.json` (stub)
* `examples/`         — small C++ programs to test against
