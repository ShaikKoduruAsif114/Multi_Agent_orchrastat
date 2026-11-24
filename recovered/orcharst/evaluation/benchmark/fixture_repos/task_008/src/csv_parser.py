def parse_csv(text: str) -> list:
    rows = []
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        # BUG: naive split breaks quoted fields containing commas
        rows.append(line.split(","))
    return rows

def parse_int_list(text: str) -> list:
    # BUG: no whitespace stripping -> ValueError on '1, 2'
    return [int(x) for x in text.split(",")]

def to_csv_row(row) -> str:
    return ",".join(str(c) for c in row)
