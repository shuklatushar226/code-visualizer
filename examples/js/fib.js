// Naive recursive Fibonacci. Mirrors examples/python/fibonacci.py so the
// JS tracer exercises the recursion-tree path: fib(5) has 15 calls and
// 6 distinct subproblems — small enough to render comfortably.

function fib(n) {
    if (n < 2) return n;
    return fib(n - 1) + fib(n - 2);
}

console.log(fib(5));
