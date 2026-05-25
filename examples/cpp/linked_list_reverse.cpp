// Reverse a singly linked list using a hand-written Node struct.
// Pair this with viz.hpp annotations so the tracer knows `Node*` should
// be visualized as a linked list.
//
//   // @viz Node => linked_list
//
// The visualizer follows `next` pointers and renders the list with arrows.
#include <iostream>

struct Node {
    int val;
    Node* next;
    Node(int v, Node* n = nullptr) : val(v), next(n) {}
};

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
