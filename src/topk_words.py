"""Top-k words: case-insensitive, ignore punctuation, tie-break by word."""

from typing import List, Tuple
import re
from collections import Counter


def top_k_words(text: str, k: int) -> List[Tuple[str, int]]:
    if k <= 0:
        return []
    words = re.findall(r"[A-Za-z]+", text.lower())
    counts = Counter(words)
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return items[:k]
