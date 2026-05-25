// Iterative inorder traversal of a BST using an explicit stack.
// Annotate the TreeNode struct so the visualizer renders the tree:
//
//   // @viz TreeNode => tree
//
#include <iostream>
#include <vector>

struct TreeNode {
    int val;
    TreeNode* left;
    TreeNode* right;
    TreeNode(int v) : val(v), left(nullptr), right(nullptr) {}
};

TreeNode* insert(TreeNode* root, int val) {
    if (root == nullptr) return new TreeNode(val);
    if (val < root->val) root->left = insert(root->left, val);
    else root->right = insert(root->right, val);
    return root;
}

std::vector<int> inorder(TreeNode* root) {
    std::vector<int> out;
    std::vector<TreeNode*> stack;
    TreeNode* cur = root;
    while (cur != nullptr || !stack.empty()) {
        while (cur != nullptr) {
            stack.push_back(cur);
            cur = cur->left;
        }
        cur = stack.back();
        stack.pop_back();
        out.push_back(cur->val);
        cur = cur->right;
    }
    return out;
}

int main() {
    TreeNode* root = nullptr;
    for (int v : {5, 3, 7, 1, 4, 6, 8}) root = insert(root, v);
    auto out = inorder(root);
    for (int x : out) std::cout << x << " ";
    std::cout << std::endl;
    return 0;
}
