// Reverse a singly linked list. The VIZ_REGISTER_LINKED_LIST macro from
// viz.hpp tells the C++ tracer that `Node` is a linked-list node with
// fields `val` (the payload) and `next` (the recursive pointer). The
// tracer then emits `{kind: "object", type: "Node", fields: {val, next}}`
// for each node so the front-end renders the list with arrows.

#include <iostream>
#include "viz.hpp"

struct Node {
    int val;
    Node* next;
    Node(int v, Node* n = nullptr) : val(v), next(n) {}
};
VIZ_REGISTER_LINKED_LIST(Node, val, next)

Node* reverse(Node* head) {
    Node* prev = nullptr;
    Node* cur = head;
    while (cur != nullptr) {
        Node* nxt = cur->next;
        cur->next = prev;
        prev = cur;
        cur = nxt;
    }
    return prev;
}

int main() {
    Node* head = new Node(1, new Node(2, new Node(3, new Node(4))));
    Node* r = reverse(head);
    for (Node* p = r; p; p = p->next) std::cout << p->val << " ";
    std::cout << std::endl;
    return 0;
}
