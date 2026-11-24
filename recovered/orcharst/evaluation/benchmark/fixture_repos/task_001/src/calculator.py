"""Calculator module - performs basic arithmetic operations."""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    # BUG: No check for b == 0 -> raises ZeroDivisionError
    return a / b

def percentage(value, percent):
    # BUG: Wrong formula -> divides by 10 instead of 100
    return (value * percent) / 10

def power(base, exp):
    return base ** exp

def factorial(n):
    # BUG: Missing base case for n == 0
    if n == 1:
        return 1
    return n * factorial(n - 1)
