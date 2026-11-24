def celsius_to_fahrenheit(c: float) -> float:
    # BUG: missing +32
    return c * 1.8

def fahrenheit_to_celsius(f: float) -> float:
    # BUG: subtracts 32 after scaling
    return (f * 5 / 9) - 32

def is_freezing(c: float) -> bool:
    return c <= 0

def is_boiling(c: float) -> bool:
    return c >= 100
