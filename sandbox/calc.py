def add(a: float, b: float) -> float:
    return a + b


def multiply(a: float, b: float) -> float:
    return a * b


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("division by zero")
    return a / b


def power(base: float, exp: int) -> float:
    if not isinstance(exp, int) or exp < 0:
        raise ValueError("exponent must be a non-negative integer")
    return base**exp


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("mean of empty list")
    return sum(values) / len(values)
