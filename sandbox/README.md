# sandbox

Funciones aritméticas básicas en `calc.py`.

```python
from sandbox.calc import add, multiply, divide, power, mean

add(2, 3)          # 5
power(2, 10)       # 1024
mean([1, 2, 3])    # 2.0
```

## `add(a, b)`

Devuelve `a + b`.

## `multiply(a, b)`

Devuelve `a * b`.

## `divide(a, b)`

Devuelve `a / b`. Lanza `ValueError("division by zero")` si `b == 0`.

## `power(base, exp)`

Devuelve `base ** exp`. `exp` debe ser un entero no negativo; en otro caso
lanza `ValueError("exponent must be a non-negative integer")`.

## `mean(values)`

Devuelve la media aritmética de una lista de números. Una lista vacía lanza
`ValueError("mean of empty list")`.
