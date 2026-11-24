from collections import Counter

def word_frequencies(text: str) -> dict:
    # BUG: case-sensitive
    words = text.split()
    return dict(Counter(words))

def top_words(text: str, n: int) -> list:
    # BUG: nondeterministic tie-break
    freq = word_frequencies(text)
    return sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:n]

def letter_frequency(text: str) -> dict:
    # BUG: counts whitespace/punctuation too
    return dict(Counter(text))
