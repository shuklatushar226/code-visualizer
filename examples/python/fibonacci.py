# Naive recursive Fibonacci. Picks the smallest n that still exercises the
# recursion tree well — fib(6) has 25 calls and 8 distinct subproblems, which
# is a sweet spot for visualization without overflowing the trace cap.

def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


if __name__ == "__main__":
    print(fib(6))
