# Examples

End-to-end demos you can paste into the standalone web app, the browser
extension overlay, or the VS Code extension.

## Python (`examples/python/`)

| File                          | Demonstrates                                |
|-------------------------------|---------------------------------------------|
| `two_sum.py`                  | Growing hashmap, array index pointer        |
| `linked_list_reverse.py`      | LinkedListView: pointer rewiring per step   |
| `bst_inorder.py`              | TreeView + StackView (iterative traversal)  |
| `graph_bfs.py`                | GraphView (adjacency dict) + QueueView      |
| `min_heap.py`                 | HeapTreeView (array-backed binary heap)     |

## C++ (`examples/cpp/`)

| File                          | Demonstrates                                |
|-------------------------------|---------------------------------------------|
| `reverse_array.cpp`           | ArrayView with i / j pointer locals         |
| `linked_list_reverse.cpp`     | LinkedListView via `viz.hpp` annotation     |
| `bst_inorder.cpp`             | TreeView + std::vector-backed stack         |

## Annotations

Use `# @viz:TypeName=structure` (Python) or `// @viz TypeName => structure`
(C++) to override the auto-detected structure for a given type. Supported
structure kinds:

```
array | linked_list | tree | graph | stack | queue | heap |
dict  | set         | object | scalar
```

If you don't annotate, the detector will guess from field names — e.g.
any object with `next` looks like a linked-list node, anything with
`left`/`right` looks like a tree node, and a dict whose values are all
lists looks like an adjacency graph.
