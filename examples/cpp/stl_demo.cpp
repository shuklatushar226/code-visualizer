// Exercises the STL decoding path in the C++ tracer. Each container
// below should round-trip through gdb's variable-object interface into
// a Trace Event Protocol HeapObject — `kind:"list"` for the vector and
// list, `kind:"dict"` for the map, `kind:"set"` for the set, and
// `kind:"str"` for the std::string.
//
// No viz.hpp annotations needed; STL types are detected by their
// fully-qualified name in `whatis`.

#include <iostream>
#include <list>
#include <map>
#include <set>
#include <string>
#include <vector>

int main() {
    std::vector<int> v = {1, 2, 3, 4, 5};
    std::list<int> l = {10, 20, 30};
    std::map<std::string, int> m = {{"a", 1}, {"b", 2}};
    std::set<int> s = {3, 1, 4, 1, 5, 9};
    std::string name = "DSV";

    int total = 0;
    for (int x : v) total += x;
    std::cout << total << " " << name << " " << s.size() << " " << l.size() << " " << m.size() << "\n";
    return 0;
}
