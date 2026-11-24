from datetime import date

def days_between(d1: date, d2: date) -> int:
    # BUG: negative when d1 > d2
    return (d2 - d1).days

def is_weekend(d: date) -> bool:
    # BUG: Friday (4) reported True, Sunday (6) reported False
    return d.weekday() > 5

def add_days(d: date, days: int) -> date:
    delta = days % 7
    if delta:
        return date.fromordinal(d.toordinal() + delta)
    return d

def days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days
