"""Implement is_anagram(a, b): True if a and b are anagrams.

Ignore case and non-letter characters. Use only stdlib.
"""

from collections import Counter


def is_anagram(a: str, b: str) -> bool:
    normalized_a = [char.lower() for char in a if char.isalpha()]
    normalized_b = [char.lower() for char in b if char.isalpha()]
    return Counter(normalized_a) == Counter(normalized_b)
