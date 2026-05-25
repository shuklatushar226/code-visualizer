// In-place array reversal. The C++ tracer will step through the loop and
// the visualizer will render `a` as an ArrayView with the i / j pointers
// taken from the local-variable table.
#include <iostream>
#include <vector>

void reverse_in_place(std::vector<int>& a) {
    int i = 0;
    int j = static_cast<int>(a.size()) - 1;
    while (i < j) {
        std::swap(a[i], a[j]);
        ++i;
        --j;
    }
}

int main() {
    std::vector<int> a = {1, 2, 3, 4, 5};
    reverse_in_place(a);
    for (int x : a) std::cout << x << " ";
    std::cout << std::endl;
    return 0;
}
