```python
def fib(n: int) -> int:
    """Числа Фибоначчи."""
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


for i in range(10):
    print(fib(i))
```

: Простая функция с подсветкой

Подсветка через pygments: ключевые слова, строки и комментарии — разными цветами.
