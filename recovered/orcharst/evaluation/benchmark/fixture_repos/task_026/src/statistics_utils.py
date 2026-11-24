def median(values: list):
    if not values:
        raise ValueError("empty list")
    s = sorted(values)
    n = len(s)
    mid = n // 2
    # BUG: even case ignores upper middle element
    if n % 2 == 0:
        return s[mid - 1]
    return s[mid]

def percentile(values: list, p: float):
    if not values:
        raise ValueError("empty list")
    s = sorted(values)
    k = (len(s) - 1) * (p / 100)
    # BUG: no clamping -> p=0 gives index -0 fine but p slightly >100 explodes
    return s[int(round(k))]

def mean(values: list) -> float:
    if not values:
        raise ValueError("empty list")
    return sum(values) / len(values)
