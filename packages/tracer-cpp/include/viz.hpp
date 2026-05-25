// viz.hpp — opt-in hints for the DSA Code Visualizer's C++ tracer.
//
// Include this header and use the VIZ_REGISTER_* macros to tell the tracer
// which struct fields hold recursive pointers, so it can render the right
// data-structure widget (linked list, binary tree, etc.).
//
// Without these annotations the tracer falls back to a generic object view.

#ifndef DSA_VIZ_HPP
#define DSA_VIZ_HPP

// The tracer scans the produced binary for symbols named __viz_<...> and uses
// them as metadata. We deliberately use static const char* so the symbol
// survives -O0 without being optimised away.

#define VIZ_REGISTER_LINKED_LIST(TYPE, VAL_FIELD, NEXT_FIELD) \
    static const char* __viz_##TYPE##_kind = "linked_list"; \
    static const char* __viz_##TYPE##_val  = #VAL_FIELD;     \
    static const char* __viz_##TYPE##_next = #NEXT_FIELD;

#define VIZ_REGISTER_TREE(TYPE, VAL_FIELD, LEFT_FIELD, RIGHT_FIELD) \
    static const char* __viz_##TYPE##_kind  = "tree";              \
    static const char* __viz_##TYPE##_val   = #VAL_FIELD;          \
    static const char* __viz_##TYPE##_left  = #LEFT_FIELD;         \
    static const char* __viz_##TYPE##_right = #RIGHT_FIELD;

#define VIZ_REGISTER_GRAPH_ADJ(TYPE, ADJ_FIELD) \
    static const char* __viz_##TYPE##_kind = "graph"; \
    static const char* __viz_##TYPE##_adj  = #ADJ_FIELD;

#endif // DSA_VIZ_HPP
