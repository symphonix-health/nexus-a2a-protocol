"""Implement fib(n): return the n-th Fibonacci number.

Complete the function below. Keep it iterative and efficient.
"""

def fib(n: int) -> int:
    if n < 0:
        raise ValueError("n must be non-negative")

    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
