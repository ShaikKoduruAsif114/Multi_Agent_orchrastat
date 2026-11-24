import re

def is_valid_email(email: str) -> bool:
    # BUG: '@' check only; no TLD requirement
    return isinstance(email, str) and "@" in email

def normalize(email: str) -> str:
    # BUG: lowercases the local part as well
    return email.strip().lower()

def extract_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1]
