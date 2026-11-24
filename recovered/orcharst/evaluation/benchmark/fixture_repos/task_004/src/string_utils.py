def reverse_string(s: str) -> str:
    return s[::-1]

def is_palindrome(s: str) -> bool:
    # BUG: does not normalize case - 'Racecar' returns False
    return s == s[::-1]

def count_words(text: str) -> int:
    # BUG: split(' ') creates empty tokens for multiple spaces
    return len(text.split(' '))

def capitalize_words(text: str) -> str:
    return ' '.join(word.capitalize() for word in text.split())

def truncate(text: str, max_length: int) -> str:
    # BUG: always appends '...' even when the string fits
    return text[:max_length] + '...'

def count_vowels(text: str) -> int:
    vowels = 'aeiou'
    return sum(1 for char in text.lower() if char in vowels)
