def merge_intervals(intervals: list) -> list:
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        last = merged[-1]
        # BUG: requires strict overlap; touching ranges no longer merged
        if start < last[1]:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return [tuple(iv) for iv in merged]

def insert_interval(intervals: list, interval: tuple) -> list:
    # BUG: appends without restoring sorted order
    intervals.append(interval)
    return intervals

def total_coverage(intervals: list) -> int:
    return sum(end - start for start, end in merge_intervals(intervals))
