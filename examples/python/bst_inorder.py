# Binary search tree: build a tree then do an iterative inorder traversal
# using an explicit stack. The visualizer will render both the tree
# (because of `left`/`right` fields) and the auxiliary stack.

# @viz:TreeNode=tree
# @viz:stack=stack


class TreeNode:
    def __init__(self, val, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


def insert(root, val):
    if root is None:
        return TreeNode(val)
    if val < root.val:
        root.left = insert(root.left, val)
    else:
        root.right = insert(root.right, val)
    return root


def inorder(root):
    out = []
    stack = []
    cur = root
    while cur is not None or stack:
        while cur is not None:
            stack.append(cur)
            cur = cur.left
        cur = stack.pop()
        out.append(cur.val)
        cur = cur.right
    return out


if __name__ == "__main__":
    root = None
    for v in [5, 3, 7, 1, 4, 6, 8]:
        root = insert(root, v)
    print(inorder(root))
