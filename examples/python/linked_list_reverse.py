# Reverse a singly linked list in place.
# The visualizer will detect the `next` field and render this as a
# linked-list chain that rewires every iteration.

# @viz:Node=linked_list


class Node:
    def __init__(self, val, next=None):
        self.val = val
        self.next = next


def reverse(head):
    prev = None
    cur = head
    while cur is not None:
        nxt = cur.next   # save
        cur.next = prev  # rewire
        prev = cur       # advance prev
        cur = nxt        # advance cur
    return prev


def to_list(head):
    out = []
    while head is not None:
        out.append(head.val)
        head = head.next
    return out


if __name__ == "__main__":
    head = Node(1, Node(2, Node(3, Node(4, Node(5)))))
    new_head = reverse(head)
    print(to_list(new_head))
